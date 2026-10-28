"""
title: Integration — keep_edited_retired restores a retired file the project edited
kind: tests
layer: n/a
summary: scripts/jobs/keep_edited_retired.py run as copier's first `after` migration runs it, in a real git project against a synthetic template whose tag v2 moves an ADR into docs/adr/keel/ as a K- file and drops a script, a symlink and a rendered document. A file the update deleted that the project had edited (any byte but the frontmatter `updated:` value) is put back from HEAD with HEAD's mode, an executable and a symlink included, and named on stderr with its successor; an unedited one stays deleted; one the template renders from a `.jinja` source, or one the template does not hold at --from, cannot be judged, so it is kept and named; a path something else now occupies is a failure, never overwritten. The index is never touched. A second run changes no byte of the tree (the fixed point check_V's rerun_proof names). An unresolvable --from ref puts back every deleted file and exits 2. A `--retire NAME:PATH` CI adapter, plain or rendered from a `.jinja` twin with `--answers`, is removed when it is what keel rendered and otherwise kept with one stderr line naming its marker state and `git rm PATH`, twice over, and so is one that is a symlink; one whose adapter the `--answer-key` answer at HEAD did not choose is left alone and unnamed, even byte-equal to keel's, and under answers that record no such key the kept line says the answer does not choose it, never that it no longer does; a `--retire` without `--answer-key` exits 2; an empty `--retire` retires nothing and a malformed one exits 2.
"""

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

import hermetic_git

pytestmark = pytest.mark.integration

_ROOT = Path(__file__).resolve().parents[2]
_GUARD = _ROOT / "scripts" / "jobs" / "keep_edited_retired.py"


def _doc(title, owner="TBD", updated="2026-01-01"):
    return '---\ntitle: "%s"\nkind: adr\nowner: %s\nupdated: %s\n---\n\n# %s\n' % (
        title,
        owner,
        updated,
        title,
    )


# The template at v1, and the project's copy of each file as it stands: the
# edited ones differ from v1 by more than the stamp.
_V1 = {
    "docs/adr/0002-edited.md": _doc("ADR-0002: Edited"),
    "docs/adr/0003-stamp-only.md": _doc("ADR-0003: Stamp only"),
    "scripts/tool.sh": "#!/bin/sh\necho v1\n",
    "docs/gen.md.jinja": "# {{ project_name }}\n",
}
_PROJECT = {
    "docs/adr/0002-edited.md": _doc("ADR-0002: Edited", owner="us"),
    "docs/adr/0003-stamp-only.md": _doc("ADR-0003: Stamp only", updated="2026-09-09"),
    "scripts/tool.sh": "#!/bin/sh\necho ours\n",
    "docs/gen.md": "# demo\n",
    "docs/keep.md": "untouched by the update\n",
    # The project's own file, which the template has never held: nothing to
    # judge it against.
    "docs/ours.md": "the project's own\n",
}
_RETIRED = sorted(
    [
        "docs/adr/0002-edited.md",
        "docs/adr/0003-stamp-only.md",
        "scripts/tool.sh",
        "docs/gen.md",
        "docs/link.md",
        "docs/ours.md",
    ]
)


def _git(cwd, env, *argv):
    r = subprocess.run(
        ["git"] + list(argv), cwd=str(cwd), env=env, capture_output=True, text=True
    )
    assert r.returncode == 0, "git %s: %s" % (" ".join(argv), r.stderr)
    return r.stdout


def _write(root, files):
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


@pytest.fixture
def setup(tmp_path):
    """(template, project, env): the template tagged v1 then v2, and a
    committed project whose files the update to v2 has just deleted, as
    copier's `_remove_old_files` leaves them."""
    work = tmp_path / "gitwork"
    work.mkdir()
    env = hermetic_git.git_env(work)
    template = tmp_path / "template"
    template.mkdir()
    _git(template, env, "init", "-q", "-b", "main")
    _write(template, _V1)
    os.chmod(str(template / "scripts" / "tool.sh"), 0o755)
    os.symlink("0002-edited.md", str(template / "docs" / "link.md"))
    _git(template, env, "add", "-A")
    _git(template, env, "commit", "-qm", "v1")
    _git(template, env, "tag", "v1")
    (template / "docs" / "adr" / "keel").mkdir()
    _git(
        template, env, "mv", "docs/adr/0002-edited.md", "docs/adr/keel/K-0002-edited.md"
    )
    _git(
        template,
        env,
        "mv",
        "docs/adr/0003-stamp-only.md",
        "docs/adr/keel/K-0003-stamp-only.md",
    )
    _git(
        template,
        env,
        "rm",
        "-q",
        "scripts/tool.sh",
        "docs/gen.md.jinja",
        "docs/link.md",
    )
    _git(template, env, "commit", "-qm", "v2")
    _git(template, env, "tag", "v2")

    project = tmp_path / "project"
    project.mkdir()
    _git(project, env, "init", "-q", "-b", "main")
    _write(project, _PROJECT)
    os.chmod(str(project / "scripts" / "tool.sh"), 0o755)
    os.symlink("elsewhere.md", str(project / "docs" / "link.md"))
    _git(project, env, "add", "-A")
    _git(project, env, "commit", "-qm", "generated at v1, then edited")
    for rel in _RETIRED:
        os.unlink(str(project / rel))
    return template, project, env


def _guard(project, env, *argv):
    return subprocess.run(
        [sys.executable, str(_GUARD)] + list(argv),
        cwd=str(project),
        env=env,
        capture_output=True,
        text=True,
    )


def _state(root):
    """Every path under *root* but .git, with its bytes or link target and mode."""
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


def test_restores_an_edited_retired_file_and_reaches_a_fixed_point(setup):
    template, project, env = setup
    index = project / ".git" / "index"
    index_before = (index.read_bytes(), index.stat().st_mtime_ns)

    r = _guard(project, env, "--template", str(template), "--from", "v1")
    assert r.returncode == 0, r.stdout + r.stderr

    # Edited, so kept, with HEAD's bytes and HEAD's mode.
    assert (project / "docs/adr/0002-edited.md").read_text() == _PROJECT[
        "docs/adr/0002-edited.md"
    ]
    assert (project / "scripts/tool.sh").read_text() == _PROJECT["scripts/tool.sh"]
    assert os.stat(str(project / "scripts/tool.sh")).st_mode & stat.S_IXUSR
    assert os.readlink(str(project / "docs/link.md")) == "elsewhere.md"
    # Rendered from a .jinja source: unjudgeable, so kept.
    assert (project / "docs/gen.md").read_text() == _PROJECT["docs/gen.md"]
    # Only the stamp differs: the template's retirement stands.
    assert not (project / "docs/adr/0003-stamp-only.md").exists()
    assert (project / "docs/keep.md").read_text() == _PROJECT["docs/keep.md"]

    err = r.stderr
    assert (
        "kept docs/adr/0002-edited.md: the project edited it and the template "
        "retired it (now docs/adr/keel/K-0002-edited.md)" in err
    ), err
    assert "kept scripts/tool.sh: the project edited it" in err, err
    assert "kept docs/link.md: the project edited it" in err, err
    assert "kept docs/gen.md:" in err and "docs/gen.md.jinja" in err, err
    # Not in the template at --from: unjudgeable, so kept and named.
    assert (project / "docs/ours.md").read_text() == _PROJECT["docs/ours.md"]
    assert (
        "kept docs/ours.md: the template holds no docs/ours.md at v1, so "
        "whether the project edited it cannot be judged" in err
    ), err
    assert "0003-stamp-only" not in err, err
    # The index is the project's own: never written.
    assert (index.read_bytes(), index.stat().st_mtime_ns) == index_before

    first = _state(project)
    again = _guard(project, env, "--quiet", "--template", str(template), "--from", "v1")
    assert again.returncode == 0, again.stdout + again.stderr
    assert again.stdout == "", again.stdout
    assert _state(project) == first, "a second run changed the tree"
    assert (index.read_bytes(), index.stat().st_mtime_ns) == index_before


@pytest.mark.parametrize(
    "ref", ["no-such-ref", "--upload-pack=x"], ids=["unknown", "option"]
)
def test_an_unresolvable_ref_keeps_every_deleted_file_and_exits_2(setup, ref):
    """Without a base to judge against nothing may stay deleted: every file
    the update deleted is put back, and the run fails loudly."""
    template, project, env = setup
    r = _guard(project, env, "--template", str(template), "--from=" + ref)
    assert r.returncode == 2, r.stdout + r.stderr
    assert ref in r.stderr, r.stderr
    for rel in _RETIRED:
        assert os.path.lexists(str(project / rel)), rel
    assert (project / "docs/adr/0003-stamp-only.md").read_text() == _PROJECT[
        "docs/adr/0003-stamp-only.md"
    ]


def test_a_path_taken_since_the_deletion_is_a_failure_never_overwritten(setup):
    """When something now stands at a deleted path (a directory in place of
    the file), the guard refuses to put the file back over it: the path is
    named, the occupant is untouched, the other files are still judged, and
    the run exits 2."""
    template, project, env = setup
    (project / "scripts" / "tool.sh").mkdir()
    (project / "scripts" / "tool.sh" / "inside.txt").write_text("occupant\n")
    r = _guard(project, env, "--template", str(template), "--from", "v1")
    assert r.returncode == 2, r.stdout + r.stderr
    assert (
        "keep_edited_retired: scripts/tool.sh: cannot put back scripts/tool.sh: "
        "the path is taken" in r.stderr
    ), r.stderr
    assert (project / "scripts" / "tool.sh" / "inside.txt").read_text() == (
        "occupant\n"
    )
    assert "kept docs/adr/0002-edited.md:" in r.stderr, r.stderr


_MARKER = "# keel-adapter: {adapter}"
_CI = "# keel-adapter: hub\nsteps: [lint]\n"
_LAB_TWIN = "# keel-adapter: lab\nimage: py{{ python }}\n"
_LAB = "# keel-adapter: lab\nimage: py3.12\n"
_EDIT = "# a line the project added\n"


def _retire_setup(tmp_path, ci, lab, answers="python: '3.12'\nci_pipeline: both\n"):
    """(template, project, env): a template tagged v1 holding a hub adapter and
    a lab adapter's `.jinja` twin, and a committed project holding *ci* and
    *lab* (and *answers*, when not None) on disk, as an update leaves an
    adapter copier did not delete."""
    work = tmp_path / "gitwork"
    work.mkdir()
    env = hermetic_git.git_env(work)
    template = tmp_path / "template"
    template.mkdir()
    _git(template, env, "init", "-q", "-b", "main")
    _write(template, {"ci.yml": _CI, "lab.yml.jinja": _LAB_TWIN})
    _git(template, env, "add", "-A")
    _git(template, env, "commit", "-qm", "v1")
    _git(template, env, "tag", "v1")
    project = tmp_path / "project"
    project.mkdir()
    _git(project, env, "init", "-q", "-b", "main")
    files = {"ci.yml": ci, "lab.yml": lab}
    if answers is not None:
        files[".answers.yml"] = answers
    _write(project, files)
    _git(project, env, "add", "-A")
    _git(project, env, "commit", "-qm", "generated at v1")
    return template, project, env


def _retire(project, env, template, *retire):
    argv = ["--template", str(template), "--from", "v1", "--marker", _MARKER]
    argv += ["--answers", ".answers.yml", "--answer-key", "ci_pipeline"]
    argv += ["--answer-all", "both"]
    for value in retire:
        argv.append("--retire=" + value)
    return _guard(project, env, *argv)


def test_a_retired_adapter_left_as_keel_rendered_it_is_removed(tmp_path):
    """Byte-equal to the template's blob, or to its `.jinja` twin rendered with
    the answers HEAD holds: removed, nothing said, and a second run is a no-op."""
    template, project, env = _retire_setup(tmp_path, _CI, _LAB)
    for _ in range(2):
        r = _retire(project, env, template, "hub:ci.yml", "lab:lab.yml")
        assert r.returncode == 0, r.stdout + r.stderr
        assert not (project / "ci.yml").exists()
        assert not (project / "lab.yml").exists()
        assert r.stderr == "", r.stderr


@pytest.mark.parametrize("name, rel", [("hub", "ci.yml"), ("lab", "lab.yml")])
def test_an_edited_retired_adapter_is_kept_and_named_with_what_to_do(
    tmp_path, name, rel
):
    """An edit that keeps the marker line still keeps the file: one stderr
    line names it, says the project edited it and how to remove it, and the
    bytes are unchanged, twice."""
    ci = _CI + _EDIT if rel == "ci.yml" else _CI
    lab = _LAB + _EDIT if rel == "lab.yml" else _LAB
    template, project, env = _retire_setup(tmp_path, ci, lab)
    before = (project / rel).read_bytes()
    for _ in range(2):
        r = _retire(project, env, template, "%s:%s" % (name, rel))
        assert r.returncode == 0, r.stdout + r.stderr
        assert (project / rel).read_bytes() == before
        assert r.stderr == (
            "kept %s: it carries the line `# keel-adapter: %s`, so keel wrote it, "
            "and the project edited it; ci_pipeline no longer chooses %s, so CI "
            "runs this file's %s steps beside the job of the adapter it chooses "
            "now until you remove it (`git rm %s`)\n" % (rel, name, name, name, rel)
        ), r.stderr


def test_a_retired_adapter_keel_cannot_judge_is_kept(tmp_path):
    """No answers to render the twin with, and a path the template never held:
    each is kept and named, never removed."""
    template, project, env = _retire_setup(tmp_path, _CI, _LAB, answers=None)
    (project / "own.yml").write_text("# our own pipeline\n")
    _git(project, env, "add", "own.yml")
    _git(project, env, "commit", "-qm", "ours")
    r = _retire(project, env, template, "lab:lab.yml", "own:own.yml")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (project / "lab.yml").read_text() == _LAB
    assert (project / "own.yml").read_text() == "# our own pipeline\n"
    assert "kept lab.yml: the template renders it from lab.yml.jinja" in r.stderr
    assert (
        "kept own.yml: the template held no own.yml at v1, so keel did not write it"
        in r.stderr
    ), r.stderr


def test_a_retired_adapter_that_is_not_a_regular_file_is_kept_with_what_to_do(
    tmp_path,
):
    """A symlink where keel renders an adapter is not keel's file, so it is
    kept, and its one stderr line ends like every kept adapter's: CI runs it
    until `git rm`."""
    template, project, env = _retire_setup(tmp_path, _CI, _LAB)
    _git(project, env, "rm", "-q", "ci.yml")
    os.symlink("lab.yml", str(project / "ci.yml"))
    _git(project, env, "add", "ci.yml")
    _git(project, env, "commit", "-qm", "ours")
    r = _retire(project, env, template, "hub:ci.yml")
    assert r.returncode == 0, r.stdout + r.stderr
    assert os.readlink(str(project / "ci.yml")) == "lab.yml"
    assert r.stderr == (
        "kept ci.yml: it is not a regular file, so it is not keel's; ci_pipeline "
        "no longer chooses hub, so CI runs this file's hub steps beside the job "
        "of the adapter it chooses now until you remove it (`git rm ci.yml`)\n"
    ), r.stderr


@pytest.mark.parametrize("lab", [_LAB, _LAB + _EDIT], ids=["keel's bytes", "edited"])
def test_an_adapter_the_old_answer_did_not_choose_is_not_judged(tmp_path, lab):
    """An adapter copier did not delete, in a project whose answers at HEAD
    chose another one, was never in keel's render: it is the project's own
    file, so it is neither removed (even byte-equal to keel's) nor named."""
    template, project, env = _retire_setup(
        tmp_path, _CI, lab, answers="python: '3.12'\nci_pipeline: hub\n"
    )
    for _ in range(2):
        r = _retire(project, env, template, "lab:lab.yml")
        assert r.returncode == 0, r.stdout + r.stderr
        assert (project / "lab.yml").read_text() == lab
        assert r.stderr == "", r.stderr


def test_an_adapter_kept_under_an_unknown_old_answer_says_only_what_is_known(
    tmp_path,
):
    """Answers at HEAD that record no ci_pipeline cannot say whether keel
    rendered the file, so the kept line says the answer does not choose it,
    never that it no longer does."""
    template, project, env = _retire_setup(
        tmp_path, _CI, _LAB + _EDIT, answers="python: '3.12'\n"
    )
    r = _retire(project, env, template, "lab:lab.yml")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "kept lab.yml: " in r.stderr, r.stderr
    assert "ci_pipeline does not choose lab, so CI runs" in r.stderr, r.stderr
    assert "no longer" not in r.stderr, r.stderr


def test_a_retire_without_the_answer_key_exits_2(tmp_path):
    template, project, env = _retire_setup(tmp_path, _CI, _LAB)
    argv = ["--template", str(template), "--from", "v1", "--marker", _MARKER]
    r = _guard(project, env, *argv, "--retire=lab:lab.yml")
    assert r.returncode == 2 and "--answer-key" in r.stderr, r.stderr
    assert (project / "lab.yml").read_text() == _LAB


def test_an_empty_retire_retires_nothing_and_a_malformed_one_exits_2(tmp_path):
    """copier renders `--retire=` when the answer declines nothing; a value
    that is not NAME:PATH is a usage fault naming it."""
    template, project, env = _retire_setup(tmp_path, _CI, _LAB)
    r = _retire(project, env, template, "")
    assert r.returncode == 0 and (project / "ci.yml").exists(), r.stderr
    r = _retire(project, env, template, "ci.yml")
    assert r.returncode == 2 and "'ci.yml' is not NAME:PATH" in r.stderr, r.stderr
    assert (project / "ci.yml").exists()
