"""
title: Unit — check_structure check_D (the __init__.py boundary)
kind: tests
layer: n/a
summary: check_D's rule, pinned over a scratch root: an absolute import whose dotted path holds a `_private` segment is an error, and so is `from pkg import _sub` when `pkg/_sub.py` or `pkg/_sub/__init__.py` is a submodule and the importer lies outside `pkg/`, wherever the package sits (at the root or under src/); the same import from inside the package, a relative one that stays inside it, and a private function imported from a public module are allowed, and a relative import that climbs out of the package is judged like an absolute one. Each error names the file, the line and the public name to import instead.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """An empty root with the gate's module state isolated (as test_check_w)."""
    monkeypatch.setattr(cs, "ROOT", str(tmp_path))
    monkeypatch.setattr(cs, "errors", [])
    monkeypatch.setattr(cs, "warnings", [])
    return tmp_path


def _write(root, files):
    for relpath, text in files.items():
        path = root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


_PACKAGE = {
    "src/pkg/__init__.py": '__all__ = ["run"]\nfrom ._sub import run\n',
    "src/pkg/_sub.py": "def run():\n    return 1\n",
    "src/pkg/mod.py": "def _helper():\n    return 2\n",
}


def test_a_private_submodule_imported_from_outside_its_package_errors(repo):
    _write(repo, dict(_PACKAGE, **{"src/other/user.py": "from pkg import _sub\n"}))
    cs.check_D()
    assert len(cs.errors) == 1, cs.errors
    assert cs.errors[0].startswith(
        "src/other/user.py:1: imports the private submodule pkg._sub"
    )
    assert "import the name the package's __init__.py exports" in cs.errors[0]


def test_a_private_subpackage_imported_from_outside_errors(repo):
    files = {
        "agents/thing/__init__.py": "",
        "agents/thing/_inner/__init__.py": "",
        "agents/other.py": "from agents.thing import _inner\n",
    }
    _write(repo, files)
    cs.check_D()
    assert len(cs.errors) == 1 and cs.errors[0].startswith("agents/other.py:1:"), (
        cs.errors
    )


def test_inside_the_package_it_is_allowed(repo):
    files = dict(
        _PACKAGE,
        **{"src/pkg/mod2.py": "from pkg import _sub\nfrom . import _sub as s\n"},
    )
    _write(repo, files)
    cs.check_D()
    assert cs.errors == []


def test_a_private_function_is_not_a_submodule(repo):
    _write(
        repo, dict(_PACKAGE, **{"src/other/user.py": "from pkg.mod import _helper\n"})
    )
    cs.check_D()
    assert cs.errors == []


def test_a_relative_import_that_climbs_out_is_judged_like_an_absolute_one(repo):
    files = dict(
        _PACKAGE,
        **{
            "src/pkg2/__init__.py": "",
            "src/pkg2/inner/__init__.py": "",
            "src/pkg2/inner/user.py": "from ..sibling import _priv\n",
            "src/pkg2/sibling/__init__.py": "",
            "src/pkg2/sibling/_priv.py": "",
        },
    )
    _write(repo, files)
    cs.check_D()
    assert len(cs.errors) == 1, cs.errors
    assert cs.errors[0].startswith(
        "src/pkg2/inner/user.py:1: imports the private submodule pkg2.sibling._priv"
    )


def test_an_absolute_private_dotted_path_still_errors(repo):
    _write(repo, dict(_PACKAGE, **{"src/other/user.py": "from pkg._sub import run\n"}))
    cs.check_D()
    assert len(cs.errors) == 1 and "src/other/user.py:1:" in cs.errors[0], cs.errors


def test_keel_tree_has_no_private_submodule_crossing(monkeypatch):
    monkeypatch.setattr(cs, "errors", [])
    monkeypatch.setattr(cs, "warnings", [])
    cs.check_D()
    assert cs.errors == []
