"""
title: Unit — conflict_guard (a job never runs over a conflicted import)
kind: tests
layer: n/a
summary: scripts/jobs/conflict_guard.py pinned. The grammar: a hunk is an opening marker line, then a separator line, then a closing marker line, labels allowed on the outer two and a diff3 base section between; a lone separator (a Markdown setext underline), marker characters inside a line, and an opening marker with no close are not conflicts. `conflicted_imports` follows `import` and `from ... import` (packages, submodules and relative imports included) from an entry file through every module it resolves under the root, terminates on a cycle, ignores what resolves outside the root or nowhere (the standard library), and returns each conflicted file with the line of each hunk. `exit_if_conflicted` is silent over a clean closure and otherwise names the job, the files and lines and the command to rerun on stderr and exits 2, with no traceback.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))

import conflict_guard  # noqa: E402

pytestmark = pytest.mark.unit

# Spelled as repetitions so this file holds no marker text: the leftover-marker
# tree scans read it too.
_OPEN, _BASE, _SPLIT, _CLOSE = "<" * 7, "|" * 7, "=" * 7, ">" * 7


def _merge(label=True):
    o = _OPEN + (" before updating" if label else "")
    c = _CLOSE + (" after updating" if label else "")
    return "a\n%s\nours\n%s\ntheirs\n%s\nz\n" % (o, _SPLIT, c)


def _diff3():
    return (
        "a\n%s before updating\nours\n%s last update\nbase\n%s\ntheirs\n%s "
        % (
            _OPEN,
            _BASE,
            _SPLIT,
            _CLOSE,
        )
        + "after updating\n"
    )


def test_has_conflict_grammar():
    assert conflict_guard.has_conflict(_merge())
    assert conflict_guard.has_conflict(_merge(label=False))
    assert conflict_guard.has_conflict(_diff3())
    assert conflict_guard.has_conflict(_merge().replace("\n", "\r\n"))
    assert conflict_guard.conflict_line(_merge()) == 2
    assert conflict_guard.conflict_lines(_merge() + _merge()) == [2, 9]

    setext = "Title\n%s\n\nBody\n" % _SPLIT
    assert not conflict_guard.has_conflict(setext)
    inline = "x = '%s'\n%s\ny\n%s\n" % (_OPEN, _SPLIT, _CLOSE)
    assert not conflict_guard.has_conflict(inline)
    glued = "%sx\nours\n%s\ntheirs\n%s\n" % (_OPEN, _SPLIT, _CLOSE)
    assert not conflict_guard.has_conflict(glued)
    no_close = "%s ours\nours\n%s\ntheirs\n" % (_OPEN, _SPLIT)
    assert not conflict_guard.has_conflict(no_close)
    assert conflict_guard.conflict_line(no_close) is None
    assert not conflict_guard.has_conflict("")


def _write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_conflicted_imports_transitive(tmp_path):
    root = tmp_path / "proj"
    outside = tmp_path / "elsewhere"
    entry = _write(root, "entry.py", "import os\nimport a\nimport far\n")
    _write(root, "a.py", "import json\nimport entry\nfrom b import thing\n")
    _write(root, "b/__init__.py", "x = 1\ny = 2\nz = 3\n" + _merge(label=True))
    _write(outside, "far.py", _merge())
    _write(root, "unrelated.py", _merge())
    found = conflict_guard.conflicted_imports(
        str(entry), str(root), search_path=[str(root), str(outside)]
    )
    assert found == [("b/__init__.py", 5)]


def test_conflicted_imports_follows_submodules_and_relative_imports(tmp_path):
    root = tmp_path / "proj"
    entry = _write(root, "entry.py", "from pkg import sub\nimport pkg.deep.leaf\n")
    _write(root, "pkg/__init__.py", "from . import sibling\n")
    _write(root, "pkg/sibling.py", "from .inner import x\n")
    _write(root, "pkg/inner.py", _merge())
    _write(root, "pkg/sub.py", _merge())
    _write(root, "pkg/deep/__init__.py", "")
    _write(root, "pkg/deep/leaf.py", "\n" + _merge())
    found = conflict_guard.conflicted_imports(str(entry), str(root))
    assert found == [
        ("pkg/deep/leaf.py", 3),
        ("pkg/inner.py", 2),
        ("pkg/sub.py", 2),
    ]


def test_exit_if_conflicted_message(tmp_path, capsys):
    root = tmp_path / "proj"
    entry = _write(root, "scripts/jobs/job.py", "import dep\n")
    _write(root, "scripts/dep.py", "import os\n" + _merge())
    search = [str(root / "scripts" / "jobs"), str(root / "scripts")]

    with pytest.raises(SystemExit) as stop:
        conflict_guard.exit_if_conflicted(
            str(entry), str(root), "job", "make job", search_path=search
        )
    assert stop.value.code == 2
    err = capsys.readouterr().err
    assert err.startswith("job: ")
    assert "scripts/dep.py (line 3)" in err
    assert "`make job`" in err
    assert "Traceback" not in err

    _write(root, "scripts/dep.py", "import os\n")
    assert (
        conflict_guard.exit_if_conflicted(
            str(entry), str(root), "job", "make job", search_path=search
        )
        is None
    )
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize(
    "job, rerun",
    [
        ("restamp_docs", "`make restamp-docs`"),
        ("resolve_stamp_conflicts", "scripts/jobs/resolve_stamp_conflicts.py --quiet"),
        ("keep_edited_retired", "scripts/jobs/keep_edited_retired.py --quiet"),
        ("declare_no_app", "scripts/jobs/declare_no_app.py --quiet"),
    ],
)
def test_every_after_migration_job_refuses_a_conflicted_import(tmp_path, job, rerun):
    """Each `after` migration in copier.yml imports review_docs; a conflict there
    stops the job before the import, exit 2, naming the file and the rerun."""
    proj = tmp_path / "proj"
    shutil.copytree(
        str(_ROOT / "scripts"),
        str(proj / "scripts"),
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    target = proj / "scripts" / "jobs" / "review_docs.py"
    target.write_text(
        target.read_text(encoding="utf-8") + _merge(label=True), encoding="utf-8"
    )
    proc = subprocess.run(
        [sys.executable, "scripts/jobs/%s.py" % job, "--quiet"],
        cwd=str(proj),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert proc.stderr.startswith(job + ": "), proc.stderr
    assert "scripts/jobs/review_docs.py (line" in proc.stderr
    assert rerun in proc.stderr
    assert "Traceback" not in proc.stderr and "SyntaxError" not in proc.stderr
    # The audit reads this very line back (scripts/audit_project.py), so each
    # real job's refusal must parse to its job, its file and its rerun.
    (refusal,) = conflict_guard.read_refusals(proc.stderr)
    assert refusal[0] == job
    assert [path for path, _line in refusal[1]] == ["scripts/jobs/review_docs.py"]
    assert "`%s`" % refusal[2] in proc.stderr


def _refusal_text(tmp_path, capsys, dep_text):
    """What exit_if_conflicted writes for a job whose one import holds *dep_text*."""
    root = tmp_path / "proj"
    entry = _write(root, "scripts/jobs/job.py", "import dep\n")
    _write(root, "scripts/dep.py", dep_text)
    search = [str(root / "scripts" / "jobs"), str(root / "scripts")]
    with pytest.raises(SystemExit):
        conflict_guard.exit_if_conflicted(
            str(entry), str(root), "job", "make job", search_path=search
        )
    return capsys.readouterr().err


def test_read_refusals_inverts_exit_if_conflicted(tmp_path, capsys):
    """The parser reads back exactly what the guard writes: the audit tells a
    migration's refusal from any other copier failure by this round trip."""
    err = _refusal_text(tmp_path, capsys, "import os\n" + _merge())
    assert conflict_guard.REFUSAL in err
    assert conflict_guard.read_refusals(err) == [
        ("job", [("scripts/dep.py", 3)], "make job")
    ]
    # Inside copier's own output, one line among others.
    noisy = "left x.py: not a Markdown document\n" + err + "Task [...] returned 2.\n"
    assert conflict_guard.read_refusals(noisy) == [
        ("job", [("scripts/dep.py", 3)], "make job")
    ]


def test_read_refusals_reads_every_hunk_in_order(tmp_path, capsys):
    err = _refusal_text(tmp_path, capsys, "import os\n" + _merge() + _merge())
    assert conflict_guard.read_refusals(err) == [
        ("job", [("scripts/dep.py", 3), ("scripts/dep.py", 10)], "make job")
    ]
    line = (
        "restamp_docs: %s: a.py (line 4), a.py (line 95), b.py (line 2); resolve "
        "them, then run `make restamp-docs`\n" % conflict_guard.REFUSAL
    )
    assert conflict_guard.read_refusals(line) == [
        ("restamp_docs", [("a.py", 4), ("a.py", 95), ("b.py", 2)], "make restamp-docs")
    ]


@pytest.mark.parametrize(
    "text",
    [
        "copier update failed: something else entirely\n",
        # restamp_docs's other refusal (a conflicted manifest): not this grammar.
        "restamp_docs: cannot start git: config/project.json line 3; resolve it, "
        "then run `make restamp-docs`\n",
        # An item without its line: the whole line is not a refusal.
        "job: cannot run while modules it imports are conflicted: scripts/dep.py; "
        "resolve them, then run `make job`\n",
        "job: cannot run while modules it imports are conflicted: a.py (line 3), "
        "b.py; resolve them, then run `make job`\n",
        "",
    ],
    ids=["noise", "manifest-refusal", "no-line", "one-item-without-line", "empty"],
)
def test_read_refusals_ignores_lines_that_are_not_a_refusal(text):
    assert conflict_guard.read_refusals(text) == []
