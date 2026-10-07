"""
title: Integration — keep_edited_retired restores a retired file the project edited
kind: tests
layer: n/a
summary: scripts/jobs/keep_edited_retired.py run as copier's first `after` migration runs it, in a real git project against a synthetic template whose tag v2 moves an ADR into docs/adr/keel/ as a K- file and drops a script, a symlink and a rendered document. A file the update deleted that the project had edited (any byte but the frontmatter `updated:` value) is put back from HEAD with HEAD's mode, an executable and a symlink included, and named on stderr with its successor; an unedited one stays deleted; one the template renders from a `.jinja` source, or one the template does not hold at --from, cannot be judged, so it is kept and named; a path something else now occupies is a failure, never overwritten. The index is never touched. A second run changes no byte of the tree (the fixed point check_V's rerun_proof names). An unresolvable --from ref puts back every deleted file and exits 2.
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
