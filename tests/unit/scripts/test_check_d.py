"""
title: Unit — check_structure check_D (the __init__.py boundary)
kind: tests
layer: n/a
summary: check_D rejects private module imports and attribute access through imported package bindings, naming the file and line; shadowing, private attributes without submodules and a package's own access remain allowed. Every run asserts a positive count of parsed modules.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def scanned_modules(monkeypatch):
    """Require every check_D run to judge at least one parsed module."""
    scanned = []
    parse = cs._parse_python

    def counted_parse(full):
        result = parse(full)
        if result is not None:
            scanned.append(full)
        return result

    monkeypatch.setattr(cs, "_parse_python", counted_parse)
    yield scanned
    assert len(scanned) > 0


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


@pytest.mark.parametrize(
    ("source", "line", "submodule"),
    [
        ("import pkg\npkg._sub.run()\n", 2, "pkg._sub"),
        ("import pkg as p\np._sub\n", 2, "pkg._sub"),
        ("import pkg.public\npkg._sub\n", 2, "pkg._sub"),
        ("import pkg.public as p\np._inner.run()\n", 2, "pkg.public._inner"),
        ("import pkg\npkg.public._inner.run()\n", 2, "pkg.public._inner"),
        ("import pkg\npkg._namespace.run()\n", 2, "pkg._namespace"),
        ("def f():\n    import pkg as p\n    p._sub.run()\n", 3, "pkg._sub"),
        ("import pkg\ndef f():\n    return pkg._sub.run()\n", 3, "pkg._sub"),
        (
            "import pkg as p\ndef f():\n    global p\n    return p._sub\n",
            4,
            "pkg._sub",
        ),
        (
            "def f():\n    import pkg as p\n    def g():\n"
            "        nonlocal p\n        return p._sub\n",
            5,
            "pkg._sub",
        ),
    ],
)
def test_attribute_access_resolves_import_bindings_and_preserves_controls(
    repo, source, line, submodule
):
    files = dict(
        _PACKAGE,
        **{
            "src/pkg/public/__init__.py": "",
            "src/pkg/public/_inner/__init__.py": "",
            "src/pkg/_namespace/worker.py": "",
            "src/pkg/own.py": "import pkg as p\np._sub.run()\n",
            "src/other/controls.py": (
                "import pkg as p\n"
                "p._attribute\np._missing.run()\np.__name__\n"
                "def parameter(p):\n    return p._sub.run()\n"
                "def local():\n    p = object()\n    return p._sub\n"
                "def late_local():\n    p._sub\n    p = object()\n"
                "def closure(p):\n    return lambda: p._sub\n"
                "values = [p._sub for p in []]\n"
                "other = lambda p: p._sub\n"
                "def unrelated_import():\n    import other as p\n    p._sub\n"
            ),
            "src/other/user.py": source,
        },
    )
    _write(repo, files)
    cs.check_D()
    assert not any("controls.py:" in error or "own.py:" in error for error in cs.errors)
    assert len(cs.errors) == 1, cs.errors
    assert cs.errors[0].startswith(
        f"src/other/user.py:{line}: accesses the private submodule {submodule} "
    )
    assert "import the name the package's __init__.py exports" in cs.errors[0]


def test_keel_tree_has_no_private_submodule_crossing(monkeypatch):
    monkeypatch.setattr(cs, "ROOT", str(_ROOT))
    monkeypatch.setattr(cs, "errors", [])
    monkeypatch.setattr(cs, "warnings", [])
    cs.check_D()
    assert cs.errors == []
