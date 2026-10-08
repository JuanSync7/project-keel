"""
title: Unit — check_structure runs the project's own checks
kind: tests
layer: n/a
summary: The `structure.project_checks` extension point, pinned. Off (absent or null) is silent; a value that is not a name declared in `structure.extra_toplevel` is a check_B error, and so is a declared directory holding no top-level `*.py`. Each module is run after every lettered check, in sorted filename order, as `check(root)`, and each pair it returns becomes `("project:<stem>", tier, "<dir>/<file>.py: <message>")`, warnings before errors and each tier sorted by message. A project check only adds: the template findings are snapshotted before any project code runs, so a check that empties `check_structure.errors` hides nothing, and what a check reports through the gate's err()/warn() is its own finding at that tier, in-process and run as a script (it was dropped, and the gate exited 0, before). A `*.py` name that is a dangling symlink is an ERROR naming it, never a silent skip; a symlink to a regular file runs. Every failure is closed: a module that does not decode, holds a conflict hunk (never executed), has a SyntaxError, raises or exits on load or on call, has no callable `check`, or returns anything but an iterable of (tier, str) pairs is an ERROR naming it. Run as a script, a check's `import check_structure` gets the running module and its live ROOT; every run loads the modules afresh and leaves none in `sys.modules`; `run_checks(root, project_checks=False)` runs none. That the template's shipped manifest never carries the key is a template fact, pinned in tests/integration/test_copier_project_checks.py, because a generated project that adopts the extension point carries it by design.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit

_FM = (
    "---\ntitle: %s\nkind: %s\nlayer: n/a\nstatus: stable\nsummary: s\nid: %s\n"
    "created: 2026-01-01\nupdated: 2026-01-01\nvisibility: internal\n"
    "canonical: true\nowner: me\n---\n\n# t\n"
)
# Spelled as repetitions so this file holds no marker text: the leftover-marker
# tree scans read it too.
_OPEN, _SPLIT, _CLOSE = "<" * 7, "=" * 7, ">" * 7
_DECLARED = {"structure": {"extra_toplevel": ["checks"], "project_checks": "checks"}}


def _label(root, name):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    slug = name.replace("/", "-")
    (d / "README.md").write_text(_FM % (name, "readme", slug + "-readme"))
    (d / "AGENT.md").write_text(_FM % (name, "rules", slug + "-rules"))
    if not (d / "CLAUDE.md").is_symlink():
        os.symlink("AGENT.md", str(d / "CLAUDE.md"))
    return d


def _tree(root, manifest=None, checks=None):
    """The smallest tree every lettered check passes, a config/project.json
    (default `{}`), and, when *checks* is given, a labelled `checks/` holding
    those modules ({filename: source text or bytes})."""
    for name in ("src", "tests", "docs", "config"):
        _label(root, name)
    (root / "config" / "project.json").write_text(
        json.dumps({} if manifest is None else manifest), encoding="utf-8"
    )
    if checks is not None:
        d = _label(root, "checks")
        for name, body in checks.items():
            if isinstance(body, bytes):
                (d / name).write_bytes(body)
            else:
                (d / name).write_text(body, encoding="utf-8")
    return root


def _returns(expr):
    return "def check(root):\n    return %s\n" % expr


def _project(found):
    return [f for f in found if f[0].startswith("project:")]


def _letters(found):
    return [f for f in found if not f[0].startswith("project:")]


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    """run_checks rebinds module state; monkeypatch restores keel's afterwards
    so no other test module sees a tmp root or a stale memo."""
    for name in ("ROOT", "errors", "warnings", "GOVERNED"):
        monkeypatch.setattr(cs, name, getattr(cs, name))
    monkeypatch.setattr(cs, "_CONFIG_READ", dict(cs._CONFIG_READ))
    monkeypatch.setattr(cs, "_READ_REPORTED", set(cs._READ_REPORTED))
    if hasattr(cs, "_PROJECT_CHECKS"):
        monkeypatch.setattr(cs, "_PROJECT_CHECKS", cs._PROJECT_CHECKS)


@pytest.mark.parametrize(
    "manifest",
    [{}, {"structure": {"extra_toplevel": [], "project_checks": None}}],
    ids=["absent", "null"],
)
def test_off_by_default_is_silent(tmp_path, manifest):
    assert cs.run_checks(str(_tree(tmp_path, manifest))) == []


def test_runs_modules_in_sorted_order_with_contract(tmp_path, capsys):
    """Sorted by filename, after every lettered finding; within a module the
    warnings first and each tier sorted by message, so a check returning a set
    cannot make the output order vary. A newline in a message is kept as-is."""
    root = _tree(
        tmp_path,
        _DECLARED,
        {
            "b.py": _returns("{('error', 'E2'), ('error', 'E1'), ('warning', 'W')}"),
            "a.py": _returns("[('error', 'Ea'), ('warning', 'two\\nlines')]"),
        },
    )
    (root / "stray").mkdir()  # an undeclared top-level dir: a check_B error
    found = cs.run_checks(str(root))
    letters = _letters(found)
    assert letters and all(f[0] == "B" for f in letters), found
    assert found[: len(letters)] == letters
    assert found[len(letters) :] == [
        ("project:a", "warning", "checks/a.py: two\nlines"),
        ("project:a", "error", "checks/a.py: Ea"),
        ("project:b", "warning", "checks/b.py: W"),
        ("project:b", "error", "checks/b.py: E1"),
        ("project:b", "error", "checks/b.py: E2"),
    ]

    assert cs.main(["--root", str(root)]) == 1
    out = capsys.readouterr().out.splitlines()
    assert "WARN  checks/b.py: W" in out
    assert "ERROR checks/a.py: Ea" in out
    assert "ERROR checks/b.py: E2" in out


@pytest.mark.parametrize(
    "value",
    ["checks", 3, ["checks"], "scripts", ""],
    ids=["undeclared", "int", "list", "taxonomy-name", "empty"],
)
def test_key_must_name_declared_toplevel(tmp_path, value):
    """Only a name already in `structure.extra_toplevel` reuses check_B's
    guarantees (top level, outside the taxonomy, labelled), so anything else is
    an error naming the key, and nothing is run."""
    root = _tree(
        tmp_path,
        {"structure": {"extra_toplevel": [], "project_checks": value}},
        {"x.py": _returns("[('error', 'ran')]")},
    )
    found = cs.run_checks(str(root))
    named = [f for f in found if f[:2] == ("B", "error") and "project_checks" in f[2]]
    assert len(named) == 1, found
    assert "extra_toplevel" in named[0][2] or "not a directory name" in named[0][2]
    assert _project(found) == []


def test_a_declared_dir_that_is_missing_is_reported_once(tmp_path):
    """check_B already errors on a declared directory that does not exist; the
    project_checks reading adds no second error and does not crash."""
    root = _tree(tmp_path, _DECLARED)
    found = cs.run_checks(str(root))
    assert found == [
        (
            "B",
            "error",
            "config/project.json: structure.extra_toplevel declares 'checks/' but "
            "it does not exist; delete the declaration",
        )
    ]


def test_declared_dir_with_zero_modules_fails(tmp_path):
    """A pass over zero items is a failure: a nested module, a .pyc and a
    dot-file are not top-level modules, so the directory still holds none."""
    root = _tree(tmp_path, _DECLARED, {})
    (root / "checks" / "sub").mkdir()
    (root / "checks" / "sub" / "x.py").write_text(_returns("[]"))
    (root / "checks" / "x.pyc").write_bytes(b"\0")
    (root / "checks" / ".hidden.py").write_text(_returns("[]"))
    found = cs.run_checks(str(root))
    assert [f for f in found if f[1] == "error"] == [
        (
            "B",
            "error",
            "config/project.json: structure.project_checks 'checks/' declares no "
            "check module; add one or set it to null",
        )
    ], found


def test_raising_check_is_error_naming_module(tmp_path):
    """A raise, SystemExit included, is an ERROR naming the module; the modules
    after it still run and the template findings are intact."""
    root = _tree(
        tmp_path,
        _DECLARED,
        {
            "a.py": "def check(root):\n    raise ValueError('boom')\n",
            "b.py": "import sys\n\ndef check(root):\n    sys.exit(0)\n",
            "c.py": _returns("[('warning', 'still ran')]"),
        },
    )
    (root / "stray").mkdir()
    found = cs.run_checks(str(root))
    assert any(f[:2] == ("B", "error") and "stray/" in f[2] for f in found), found
    project = _project(found)
    assert [(f[0], f[1]) for f in project] == [
        ("project:a", "error"),
        ("project:b", "error"),
        ("project:c", "warning"),
    ], project
    assert project[0][2].startswith("checks/a.py: ")
    assert "ValueError" in project[0][2] and "boom" in project[0][2]
    assert project[1][2].startswith("checks/b.py: ") and "SystemExit" in project[1][2]
    assert project[2][2] == "checks/c.py: still ran"


def _sentinel_then(tail):
    """A module whose first line writes a sentinel next to itself, so the test
    can tell whether its body was executed at all."""
    return (
        "import os\n"
        "open(os.path.join(os.path.dirname(__file__), 'ran.txt'), 'w').close()\n" + tail
    )


@pytest.mark.parametrize(
    "body, needles, executed",
    [
        ("x = 1\ndef check(root) return []\n", ["SyntaxError", "line 2"], False),
        ("X = 1\n", ["no callable check"], None),
        ("check = 3\n", ["no callable check"], None),
        (
            _sentinel_then(
                "%s ours\nA = 1\n%s\nA = 2\n%s theirs\n" % (_OPEN, _SPLIT, _CLOSE)
            ),
            ["conflict markers at line 3", "resolve"],
            False,
        ),
        (_sentinel_then("raise RuntimeError('at import')\n"), ["RuntimeError"], True),
        (_sentinel_then("raise SystemExit(0)\n"), ["SystemExit"], True),
        (b"X = '\xff\xfe'\n", ["UTF-8"], None),
    ],
    ids=[
        "syntax",
        "no-check",
        "check-not-callable",
        "conflict",
        "raises-on-load",
        "exits-on-load",
        "not-utf8",
    ],
)
def test_load_failures_fail_closed(tmp_path, body, needles, executed):
    root = _tree(tmp_path, _DECLARED, {"x.py": body})
    found = cs.run_checks(str(root))
    # check_Q reads every text file, so it reports undecodable bytes too.
    assert [f for f in _letters(found) if not f[2].startswith("checks/x.py")] == []
    project = _project(found)
    assert len(project) == 1, project
    letter, tier, message = project[0]
    assert (letter, tier) == ("project:x", "error")
    assert message.startswith("checks/x.py: "), message
    for needle in needles:
        assert needle in message, message
    if executed is not None:
        assert (root / "checks" / "ran.txt").exists() is executed


@pytest.mark.parametrize(
    "expr",
    ["None", "'oops'", "[('info', 'm')]", "[('error', 5)]", "[('error',)]"],
    ids=["none", "str", "bad-tier", "non-str-message", "one-tuple"],
)
def test_bad_return_shapes_are_errors(tmp_path, expr):
    root = _tree(tmp_path, _DECLARED, {"x.py": _returns(expr)})
    project = _project(cs.run_checks(str(root)))
    assert len(project) == 1, project
    assert project[0][:2] == ("project:x", "error")
    assert project[0][2].startswith("checks/x.py: ")


def test_a_generator_of_valid_pairs_is_accepted(tmp_path):
    root = _tree(
        tmp_path,
        _DECLARED,
        {"x.py": _returns("(p for p in [('warning', 'w'), ('error', 'e')])")},
    )
    assert _project(cs.run_checks(str(root))) == [
        ("project:x", "warning", "checks/x.py: w"),
        ("project:x", "error", "checks/x.py: e"),
    ]


def test_project_check_cannot_hide_template_finding(tmp_path, capsys):
    root = _tree(
        tmp_path,
        _DECLARED,
        {
            "x.py": "import check_structure\n\n"
            "def check(root):\n"
            "    del check_structure.errors[:]\n"
            "    check_structure.warnings[:] = []\n"
            "    return []\n"
        },
    )
    (root / "stray").mkdir()
    found = cs.run_checks(str(root))
    assert any(f[:2] == ("B", "error") and "stray/" in f[2] for f in found), found
    assert cs.main(["--root", str(root)]) == 1
    assert "stray/" in capsys.readouterr().out


def test_import_check_structure_sees_running_root_via_cli(tmp_path):
    """Run as a script, the gate is `__main__`; without the alias a check's
    `import check_structure` loads a second copy whose ROOT is this checkout."""
    root = _tree(
        tmp_path,
        _DECLARED,
        {
            "x.py": "import check_structure\n\n"
            "def check(root):\n"
            "    return [('warning', 'ROOT=' + check_structure.ROOT)]\n"
        },
    )
    proc = subprocess.run(
        [sys.executable, str(_ROOT / "scripts" / "check_structure.py")]
        + ["--root", str(root)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "WARN  checks/x.py: ROOT=%s" % os.path.abspath(str(root)) in (
        proc.stdout.splitlines()
    ), proc.stdout


def test_fresh_load_each_run(tmp_path):
    root = _tree(tmp_path, _DECLARED, {"x.py": _returns("[('warning', 'one')]")})
    assert _project(cs.run_checks(str(root))) == [
        ("project:x", "warning", "checks/x.py: one")
    ]
    (root / "checks" / "x.py").write_text(_returns("[('warning', 'two')]"))
    assert _project(cs.run_checks(str(root))) == [
        ("project:x", "warning", "checks/x.py: two")
    ]
    assert not [m for m in sys.modules if m.startswith("keel_project_check")]
    assert not (root / "checks" / "__pycache__").exists()


def test_project_checks_false_runs_none(tmp_path):
    root = _tree(
        tmp_path,
        _DECLARED,
        {"x.py": _sentinel_then("def check(root):\n    raise ValueError('no')\n")},
    )
    assert _project(cs.run_checks(str(root), project_checks=False)) == []
    assert not (root / "checks" / "ran.txt").exists()


# --- a check that reports through the gate's own err()/warn() ------------------
#
# A check may `import check_structure` and reuse its helpers, and every helper
# reports through err()/warn(). Those appends land after run_checks has frozen
# the template's findings, so before this they were printed by nothing and the
# gate exited 0 over them (measured, fail-open).

_THROUGH_GATE = (
    "import check_structure\n\n"
    "def check(root):\n"
    "    check_structure.err('via err')\n"
    "    check_structure.warn('via warn')\n"
    "    return [('error', 'via return')]\n"
)


def test_err_and_warn_during_a_check_are_its_findings(tmp_path):
    """What a module reports through err()/warn() is its own finding, at that
    tier, merged with what it returns and sorted with it; a module that rebinds
    the gate's lists still has what it appends after counted, and one that
    leaves something that is not a list there is an ERROR naming it."""
    root = _tree(
        tmp_path,
        _DECLARED,
        {
            "a.py": _THROUGH_GATE,
            "b.py": "import check_structure\n\n"
            "def check(root):\n"
            "    check_structure.errors = []\n"
            "    check_structure.err('after a rebind')\n"
            "    return []\n",
            "c.py": "import check_structure\n\n"
            "def check(root):\n"
            "    check_structure.warnings = None\n"
            "    return []\n",
            "d.py": _returns("[]"),
        },
    )
    (root / "stray").mkdir()
    found = cs.run_checks(str(root))
    assert any(f[:2] == ("B", "error") and "stray/" in f[2] for f in found), found
    project = _project(found)
    assert project[:4] == [
        ("project:a", "warning", "checks/a.py: via warn"),
        ("project:a", "error", "checks/a.py: via err"),
        ("project:a", "error", "checks/a.py: via return"),
        ("project:b", "error", "checks/b.py: after a rebind"),
    ], project
    assert [f[:2] for f in project[4:]] == [("project:c", "error")], project
    assert "check_structure.warnings" in project[4][2], project
    # The template's lists are the template's again once the modules ran.
    assert any("stray/" in m for m in cs.errors), cs.errors
    assert not [m for m in cs.errors if "via" in m or "rebind" in m], cs.errors


def test_err_during_a_check_fails_the_gate_via_cli(tmp_path):
    """Run as a script: the alias hands the module the running gate, so an
    err() it calls is printed and fails the run."""
    root = _tree(tmp_path, _DECLARED, {"x.py": _THROUGH_GATE})
    proc = subprocess.run(
        [sys.executable, str(_ROOT / "scripts" / "check_structure.py")]
        + ["--root", str(root)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    lines = proc.stdout.splitlines()
    assert "ERROR checks/x.py: via err" in lines, proc.stdout
    assert "WARN  checks/x.py: via warn" in lines, proc.stdout


# --- a module name that is not a readable regular file --------------------------


def test_a_dangling_module_symlink_is_an_error_naming_it(tmp_path):
    """A `*.py` name that is a symlink to nothing was dropped from the run, so
    the gate went green with that check off whenever another module existed."""
    root = _tree(tmp_path, _DECLARED, {"a.py": _returns("[]")})
    os.symlink("missing_target.py", str(root / "checks" / "c.py"))
    project = _project(cs.run_checks(str(root)))
    assert [f[:2] for f in project] == [("project:c", "error")], project
    assert project[0][2].startswith("checks/c.py: "), project
    assert "missing" in project[0][2], project


def test_a_lone_dangling_module_is_named_not_counted_as_none(tmp_path):
    root = _tree(tmp_path, _DECLARED, {})
    os.symlink("missing_target.py", str(root / "checks" / "c.py"))
    found = cs.run_checks(str(root))
    assert not [f for f in found if "declares no check module" in f[2]], found
    assert [f[:2] for f in _project(found)] == [("project:c", "error")], found


def test_a_module_symlink_to_a_regular_file_runs(tmp_path):
    root = _tree(tmp_path, _DECLARED, {"real.txt": _returns("[('warning', 'w')]")})
    os.symlink("real.txt", str(root / "checks" / "x.py"))
    assert _project(cs.run_checks(str(root))) == [
        ("project:x", "warning", "checks/x.py: w")
    ]
