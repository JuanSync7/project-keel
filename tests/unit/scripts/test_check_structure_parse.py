"""
title: Unit — check_structure, a Python source no check can parse
kind: tests
layer: n/a
summary: A .py file that a check reads but cannot parse is never skipped in silence. It is one error per file, however many checks read it, naming the file and the fix, when this interpreter meets config/project.json layers.backend.python's floor or no floor can be read. When this interpreter is older than that floor, as the pre-commit hook's host python3 can be, a SyntaxError is not a finding: the run prints one warning that counts the files, names both versions and says `make check-all` and `make verify` judge them. A file that cannot be decoded is an error under any interpreter.
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit

_BROKEN = "def broken(:\n    pass\n"
# A floor no interpreter meets, so this one is always the older; and one every
# interpreter that runs this suite meets.
_FUTURE = ">=99.0"
_PAST = ">=3.0"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """An empty root with the gate's module state isolated (as test_check_h)."""
    (tmp_path / "config").mkdir()
    monkeypatch.setattr(cs, "ROOT", str(tmp_path))
    monkeypatch.setattr(cs, "errors", [])
    monkeypatch.setattr(cs, "warnings", [])
    monkeypatch.setattr(cs, "_CONFIG_READ", {})
    monkeypatch.setattr(cs, "_READ_REPORTED", set())
    monkeypatch.setattr(cs, "_PARSE_REPORTED", set())
    monkeypatch.setattr(cs, "_PARSE_DEFERRED", set())
    return tmp_path


def _floor(root, spec):
    backend = {} if spec is None else {"python": spec}
    (root / "config" / "project.json").write_text(
        json.dumps({"layers": {"backend": backend}}), encoding="utf-8"
    )


def _write(root, relpath, text):
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _mine(name):
    return [e for e in cs.errors if e.startswith(name)]


@pytest.mark.parametrize("check", ["check_D", "check_E", "check_J"])
def test_a_syntax_error_is_an_error_from_any_check_that_reads_it(repo, check):
    _floor(repo, _PAST)
    _write(repo, "src/pkg/bad.py", _BROKEN)
    getattr(cs, check)()
    mine = _mine("src/pkg/bad.py")
    assert len(mine) == 1 and "cannot be parsed" in mine[0], cs.errors
    assert "py_compile" in mine[0], mine
    assert cs.warnings == [], cs.warnings


def test_the_frozen_config_and_tensor_checks_report_it_too(repo, monkeypatch):
    _floor(repo, _PAST)
    (repo / "config" / "practices.json").write_text(
        json.dumps(
            {"tokens": {"config_marker": "# m", "tensor_base_types": ["Tensor"]}}
        ),
        encoding="utf-8",
    )
    _write(repo, "src/bad.py", _BROKEN)
    cs.check_K()
    assert len(_mine("src/bad.py")) == 1, cs.errors
    cs._PARSE_REPORTED.clear()
    del cs.errors[:]
    monkeypatch.setattr(cs, "_profiles_on", lambda: {"cuda"})
    cs.check_L()
    assert len(_mine("src/bad.py")) == 1, cs.errors


def test_a_file_outside_the_code_roots_is_reported_by_check_x(repo):
    """check_X reads every top-level directory but tests/, wider than check_D."""
    _floor(repo, _PAST)
    _write(repo, "ops/tool.py", _BROKEN)
    cs.check_X()
    assert len(_mine("ops/tool.py")) == 1, cs.errors


def test_one_file_read_by_several_checks_is_one_error(repo):
    _floor(repo, _PAST)
    _write(repo, "src/bad.py", _BROKEN)
    for check in (cs.check_D, cs.check_E, cs.check_J, cs.check_X):
        check()
    assert len(_mine("src/bad.py")) == 1, cs.errors


def test_an_undecodable_file_is_an_error_under_an_older_interpreter(repo):
    _floor(repo, _FUTURE)
    (repo / "src").mkdir()
    (repo / "src" / "bin.py").write_bytes(b"x = '\xff'\n")
    cs.check_D()
    mine = _mine("src/bin.py")
    assert len(mine) == 1 and "cannot be parsed" in mine[0], cs.errors
    assert not cs._PARSE_DEFERRED, cs._PARSE_DEFERRED


def test_a_syntax_error_under_an_older_interpreter_is_deferred(repo):
    _floor(repo, _FUTURE)
    _write(repo, "src/new.py", _BROKEN)
    cs.check_D()
    cs.check_J()
    assert cs.errors == [] and cs.warnings == [], (cs.errors, cs.warnings)
    assert sorted(cs._PARSE_DEFERRED) == ["src/new.py"], cs._PARSE_DEFERRED


def test_an_interpreter_exactly_at_the_floor_judges_the_file(repo):
    """The floor is the oldest Python the project supports, so an interpreter
    that is that release is the project's own and defers nothing."""
    _floor(repo, ">=%d.%d" % sys.version_info[:2])
    _write(repo, "src/bad.py", _BROKEN)
    cs.check_D()
    assert len(_mine("src/bad.py")) == 1, cs.errors
    assert not cs._PARSE_DEFERRED, cs._PARSE_DEFERRED


def test_the_parse_error_names_the_interpreter_that_ran(repo):
    _floor(repo, _PAST)
    _write(repo, "src/bad.py", _BROKEN)
    cs.check_D()
    assert "`%s -m py_compile src/bad.py`" % sys.executable in cs.errors[0], cs.errors


@pytest.mark.parametrize("spec", [None, "<4", "", 3.1, ">3.9"])
def test_no_readable_floor_fails_closed(repo, spec):
    """With no floor to compare against, an old interpreter cannot be told from
    a broken file, so the file is the error."""
    _floor(repo, spec)
    _write(repo, "src/bad.py", _BROKEN)
    cs.check_D()
    assert len(_mine("src/bad.py")) == 1, cs.errors
    assert not cs._PARSE_DEFERRED, cs._PARSE_DEFERRED


@pytest.mark.parametrize(
    "spec, floor",
    [
        (">=3.10", (3, 10)),
        ("3.11", (3, 11)),
        (">=3.10,<4", (3, 10)),
        ("<4, >= 3.9", (3, 9)),
        ("~=3.12", (3, 12)),
        ("==3.8.1", (3, 8)),
    ],
)
def test_the_floor_is_read_from_the_declared_specifier(repo, spec, floor):
    _floor(repo, spec)
    assert cs._declared_python_floor() == floor


def test_a_run_prints_the_deferral_once_and_says_why(tmp_path):
    """Through run_checks: two deferred files, one warning, nothing else about
    them, and the warning names the count, both versions and `make check-all`."""
    (tmp_path / "config").mkdir()
    _floor(tmp_path, _FUTURE)
    _write(tmp_path, "src/a.py", _BROKEN)
    _write(tmp_path, "ops/b.py", _BROKEN)
    found = cs.run_checks(str(tmp_path), project_checks=False)
    about = [f for f in found if "a.py" in f[2] or "b.py" in f[2]]
    assert len(about) == 1 and about[0][1] == "warning", about
    note = about[0][2]
    here = "%d.%d" % sys.version_info[:2]
    for part in (
        "2 Python file(s)",
        here,
        _FUTURE,
        "make check-all",
        "make verify",
        "src/a.py",
    ):
        assert part in note, note


def test_a_clean_tree_prints_no_deferral(tmp_path):
    (tmp_path / "config").mkdir()
    _floor(tmp_path, _FUTURE)
    _write(tmp_path, "src/ok.py", "X = 1\n")
    found = cs.run_checks(str(tmp_path), project_checks=False)
    assert not [f for f in found if "Python file(s)" in f[2]], found


def test_keel_parses_whole_under_this_interpreter(monkeypatch):
    """Vacuity control: keel's own tree reports and defers nothing."""
    found = cs.run_checks(str(_ROOT), project_checks=False)
    assert not [f for f in found if "cannot be parsed" in f[2]], found
    assert not cs._PARSE_DEFERRED, cs._PARSE_DEFERRED
