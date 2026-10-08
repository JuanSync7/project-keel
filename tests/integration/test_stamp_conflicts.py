"""
title: Integration — resolve_stamp_conflicts settles a stamp-only conflict and leaves the rest
kind: tests
layer: n/a
summary: scripts/jobs/resolve_stamp_conflicts.py run as copier's `after` migration runs it (cwd the project, its own interpreter), over a git repository left exactly as copier 9.x's inline update leaves a conflict -- `git merge-file -L "before updating" -L "last update" -L "after updating"` writes the markers (default and diff3 styles), and `update-index --index-info` records stage 2 as the project's blob and stages 1 and 3 as the base and template blobs. A document whose one hunk is the frontmatter `updated:` line ends merged: no marker, the later date, stage 0 at stage 2's sha, ` M` in status. A document with a content hunk too, a non-Markdown file, a stamp that is not a date, a path deleted on one side, a symlink and an absent path keep their bytes and their stages and are named on stderr with a reason; an unconflicted file keeps its bytes and mtime. A second run changes no byte of the tree or .git/index (the fixed point check_V's rerun_proof names), a clean repository is a silent exit 0, and a directory git refuses is exit 2 with nothing written. Needs no copier, so it ships into every generated project.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

import hermetic_git

pytestmark = pytest.mark.integration

_ROOT = Path(__file__).resolve().parents[2]
_JOB = _ROOT / "scripts" / "jobs" / "resolve_stamp_conflicts.py"

# copier 9.x's labels for `git merge-file -L` (copier/_main.py, _apply_update).
_LABELS = ("before updating", "last update", "after updating")
# Spelled as repetitions so this file holds no marker text, which a tree scan
# for leftover conflicts would read as one.
_MARKERS = tuple(ch * 7 for ch in (b"<", b"|", b"=", b">"))


def _doc(date, body="body line"):
    """A governed document whose stamp and body line sit far enough apart that
    `git merge-file` keeps them as two hunks when both change."""
    return (
        "---\ntitle: t\nowner: TBD\nupdated: %s\n---\n\n# t\n\n"
        "First paragraph.\n\nSecond paragraph.\n\nThird paragraph.\n\n"
        "%s\n" % (date, body)
    )


# path: (base, ours, theirs). Ours is what the project committed; base is the
# template at the project's `_commit`; theirs is the template being applied.
_STAMP_ONLY = {
    "docs/a.md": (_doc("2026-01-01"), _doc("2026-02-02"), _doc("2026-03-03")),
}
_CONTENT = {
    "docs/b.md": (
        _doc("2026-01-01"),
        _doc("2026-02-02", "body line, the project's way"),
        _doc("2026-03-03", "body line, the template's way"),
    ),
    "scripts/tool.py": ("x = 1\n", "x = 2\n", "x = 3\n"),
}
_UNPARSABLE = {
    "docs/c.md": (_doc("2026-01-01"), _doc("2026-02-02"), _doc("TBD")),
}
_CLEAN = {"docs/keep.md": _doc("2026-01-01", "never conflicted")}


def _git(cwd, env, *argv, **kw):
    r = subprocess.run(
        ["git"] + list(argv),
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **kw,
    )
    assert r.returncode == 0, "git %s: %s" % (" ".join(argv), r.stderr)
    return r.stdout


def _write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _conflict(project, sides_dir, env, rel, base, theirs, style):
    """Merge *base* -> *theirs* into the committed file at *rel* the way copier
    does, then record the conflict stages the way copier does."""
    stem = rel.replace("/", "__")
    base_path = sides_dir / (stem + ".base")
    theirs_path = sides_dir / (stem + ".theirs")
    base_path.write_bytes(base.encode("utf-8"))
    theirs_path.write_bytes(theirs.encode("utf-8"))
    argv = ["git", "merge-file"]
    if style != "merge":
        argv.append("--" + style)
    for label in _LABELS:
        argv += ["-L", label]
    argv += [rel, str(base_path), str(theirs_path)]
    r = subprocess.run(argv, cwd=str(project), env=env, stderr=subprocess.PIPE)
    assert r.returncode > 0, "no conflict for %s: %r" % (rel, r.stderr)
    staged = _git(project, env, "ls-files", "--stage", "--", rel).decode()
    mode, sha, _ = staged.split("\t")[0].split()
    lines = ["0 %s\t%s" % ("0" * 40, rel), "%s %s 2\t%s" % (mode, sha, rel)]
    for stage, path in ((1, base_path), (3, theirs_path)):
        blob = _git(project, env, "hash-object", "-w", str(path)).decode().strip()
        lines.append("%s %s %d\t%s" % (mode, blob, stage, rel))
    _git(
        project,
        env,
        "update-index",
        "--index-info",
        input=("\n".join(lines) + "\n").encode(),
    )


def _repo(tmp_path, conflicts, style="merge"):
    """(project, env): a committed project, then *conflicts* applied as copier's
    inline update leaves them."""
    work = tmp_path / "gitwork"
    work.mkdir()
    env = hermetic_git.git_env(work)
    project = tmp_path / "project"
    project.mkdir()
    sides = tmp_path / "sides"
    sides.mkdir()
    _git(project, env, "init", "-q", "-b", "main")
    for rel, text in _CLEAN.items():
        _write(project, rel, text)
    for rel, (_, ours, _) in sorted(conflicts.items()):
        _write(project, rel, ours)
    _git(project, env, "add", "-A")
    _git(project, env, "commit", "-qm", "the project as it stands")
    for rel, (base, _, theirs) in sorted(conflicts.items()):
        _conflict(project, sides, env, rel, base, theirs, style)
    return project, env


def _job(project, env, *argv):
    return subprocess.run(
        [sys.executable, str(_JOB)] + list(argv),
        cwd=str(project),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )


def _unmerged(project, env):
    out = _git(project, env, "ls-files", "-u", "-z").decode()
    return sorted({e.split("\t", 1)[1] for e in out.split("\0") if "\t" in e})


def _stages(project, env, rel):
    return _git(project, env, "ls-files", "--stage", "--", rel).decode()


def _has_markers(data):
    return any(line.startswith(_MARKERS) for line in data.splitlines())


def _state(root):
    """Every path under *root* but .git, with its mode and bytes or link target."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(str(root)):
        dirnames[:] = sorted(d for d in dirnames if d != ".git")
        for name in sorted(dirnames + filenames):
            full = os.path.join(dirpath, name)
            st = os.lstat(full)
            if os.path.islink(full):
                body = os.readlink(full)
            elif os.path.isfile(full):
                with open(full, "rb") as fh:
                    body = fh.read()
            else:
                body = None
            out[os.path.relpath(full, str(root))] = (st.st_mode, body)
    return out


@pytest.mark.parametrize("style", ["merge", "diff3", "zdiff3"])
def test_a_stamp_only_conflict_ends_merged_and_a_content_conflict_keeps_its_markers(
    tmp_path, style
):
    conflicts = dict(_STAMP_ONLY, **_CONTENT)
    project, env = _repo(tmp_path, conflicts, style)
    a_stage2 = [
        ln for ln in _stages(project, env, "docs/a.md").splitlines() if "\t" in ln
    ]
    a_stage2 = [ln.split()[1] for ln in a_stage2 if ln.split()[2] == "2"]
    assert len(a_stage2) == 1
    a_before = (project / "docs/a.md").read_bytes()
    assert _has_markers(a_before), "the fixture must start conflicted"
    # 0o664, not the 0o644 a checkout leaves nor the 0o600 a bare mkstemp
    # writes, so a mode the job dropped shows; git ignores group-write.
    os.chmod(str(project / "docs/a.md"), 0o100664)
    a_mode = (project / "docs/a.md").stat().st_mode
    assert a_mode == 0o100664, oct(a_mode)
    b_before = (project / "docs/b.md").read_bytes()
    assert b_before.count(_MARKERS[0] + b" before updating") == 2, "two hunks"
    b_stages = _stages(project, env, "docs/b.md")
    tool_before = (project / "scripts/tool.py").read_bytes()
    keep = project / "docs/keep.md"
    keep_before = (keep.read_bytes(), keep.stat().st_mtime_ns)

    r = _job(project, env)
    assert r.returncode == 0, r.stdout + r.stderr

    a_after = (project / "docs/a.md").read_bytes()
    assert not _has_markers(a_after), a_after
    assert a_after == _doc("2026-03-03").encode("utf-8")
    a_mode_after = (project / "docs/a.md").stat().st_mode
    assert a_mode_after == a_mode, "the resolved file lost its mode: " + oct(
        a_mode_after
    )
    assert _unmerged(project, env) == ["docs/b.md", "scripts/tool.py"]
    stage0 = _stages(project, env, "docs/a.md").split()
    assert stage0[1:3] == [a_stage2[0], "0"], stage0

    assert (project / "docs/b.md").read_bytes() == b_before
    assert _stages(project, env, "docs/b.md") == b_stages
    assert (project / "scripts/tool.py").read_bytes() == tool_before
    assert (keep.read_bytes(), keep.stat().st_mtime_ns) == keep_before

    assert "resolved 1 stamp-only conflict(s)" in r.stderr, r.stderr
    assert "left docs/b.md: more than one hunk\n" in r.stderr, r.stderr
    assert "left scripts/tool.py: not a Markdown document\n" in r.stderr, r.stderr
    assert "docs/a.md" not in r.stderr, r.stderr
    assert r.stdout == ""

    # Last: `git status` refreshes .git/index.
    status = _git(project, env, "status", "--porcelain").decode().splitlines()
    assert " M docs/a.md" in status, status


def test_a_second_run_is_a_fixed_point(tmp_path):
    project, env = _repo(tmp_path, dict(_STAMP_ONLY, **_CONTENT))
    first = _job(project, env, "--quiet")
    assert first.returncode == 0, first.stderr
    # The fixed point below is over a run that did resolve something.
    assert "docs/a.md" not in _unmerged(project, env)
    assert "resolved" not in first.stderr, "--quiet drops only the count"
    assert "left docs/b.md: more than one hunk" in first.stderr, first.stderr

    index = project / ".git" / "index"
    tree = _state(project)
    index_before = (index.read_bytes(), index.stat().st_mtime_ns)
    again = _job(project, env, "--quiet")
    assert again.returncode == 0, again.stderr
    assert again.stderr == first.stderr, "the left paths are re-reported identically"
    assert _state(project) == tree, "a second run changed the tree"
    assert (index.read_bytes(), index.stat().st_mtime_ns) == index_before


def test_an_unparsable_stamp_is_left_and_named(tmp_path):
    project, env = _repo(tmp_path, _UNPARSABLE)
    before = (project / "docs/c.md").read_bytes()
    stages = _stages(project, env, "docs/c.md")
    r = _job(project, env)
    assert r.returncode == 0, r.stderr
    assert "left docs/c.md: unparsable date\n" in r.stderr, r.stderr
    assert "resolved 0 stamp-only conflict(s)" in r.stderr, r.stderr
    assert (project / "docs/c.md").read_bytes() == before
    assert _stages(project, env, "docs/c.md") == stages


def test_a_path_the_job_cannot_read_is_left_with_a_reason(tmp_path):
    """A path deleted on one side has no stage to restore from; a symlink or an
    absent path is never read. Each keeps its stages and is named."""
    conflicts = {
        "docs/gone.md": _STAMP_ONLY["docs/a.md"],
        "docs/link.md": _STAMP_ONLY["docs/a.md"],
        "docs/ours-deleted.md": _STAMP_ONLY["docs/a.md"],
        "docs/theirs-deleted.md": _STAMP_ONLY["docs/a.md"],
    }
    project, env = _repo(tmp_path, conflicts)
    os.unlink(str(project / "docs/gone.md"))
    os.unlink(str(project / "docs/link.md"))
    os.symlink("keep.md", str(project / "docs/link.md"))
    for rel, drop in (("docs/ours-deleted.md", "2"), ("docs/theirs-deleted.md", "3")):
        kept = [
            ln
            for ln in _stages(project, env, rel).splitlines()
            if ln.split()[2] != drop
        ]
        info = ["0 %s\t%s" % ("0" * 40, rel)] + kept
        _git(
            project,
            env,
            "update-index",
            "--index-info",
            input=("\n".join(info) + "\n").encode(),
        )
    before = {rel: _stages(project, env, rel) for rel in conflicts}
    tree = _state(project)

    r = _job(project, env)
    assert r.returncode == 0, r.stderr
    for line in (
        "left docs/gone.md: absent from the work tree",
        "left docs/link.md: a symlink",
        "left docs/ours-deleted.md: no project side",
        "left docs/theirs-deleted.md: no template side",
    ):
        assert line + "\n" in r.stderr, r.stderr
    assert {rel: _stages(project, env, rel) for rel in conflicts} == before
    assert _state(project) == tree


def test_a_repository_with_nothing_unmerged_is_a_silent_no_op(tmp_path):
    project, env = _repo(tmp_path, {})
    index = project / ".git" / "index"
    index_before = (index.read_bytes(), index.stat().st_mtime_ns)
    r = _job(project, env)
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")
    assert (index.read_bytes(), index.stat().st_mtime_ns) == index_before


def test_a_git_failure_exits_2(tmp_path):
    work = tmp_path / "gitwork"
    work.mkdir()
    env = hermetic_git.git_env(work)
    env["GIT_CEILING_DIRECTORIES"] = str(tmp_path)
    nowhere = tmp_path / "not-a-repo"
    nowhere.mkdir()
    (nowhere / "a.md").write_text(_doc("2026-01-01"))
    tree = _state(nowhere)
    r = _job(nowhere, env, "--root", str(nowhere))
    assert r.returncode == 2, r.stdout + r.stderr
    assert r.stderr.startswith("resolve_stamp_conflicts: "), r.stderr
    assert _state(nowhere) == tree
