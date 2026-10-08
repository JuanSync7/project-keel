"""
title: Unit — check_structure check_H (layers.app names a runnable composition root)
kind: tests
layer: n/a
summary: check_H's layers.app rule, pinned: an absent key is silent (a project from before the key arrives through `copier update`), null declares that the project has no composition root, and an object must carry a string `path` that exists as a package with `__main__.py` or as a `.py` file, and a string `module` that is the dotted form of that path's trailing components, which is what scripts/run_app.py imports. A non-object value, a missing path, a package without `__main__.py` and a module that does not match its path are each one error naming the key.
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit

_ABSENT = object()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """An empty root with the gate's module state isolated (as test_check_w)."""
    (tmp_path / "config").mkdir()
    monkeypatch.setattr(cs, "ROOT", str(tmp_path))
    monkeypatch.setattr(cs, "errors", [])
    monkeypatch.setattr(cs, "warnings", [])
    monkeypatch.setattr(cs, "_CONFIG_READ", {})
    monkeypatch.setattr(cs, "_READ_REPORTED", set())
    return tmp_path


def _package(root, relpath, main=True):
    pkg = root / relpath
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    if main:
        (pkg / "__main__.py").write_text("raise SystemExit(0)\n", encoding="utf-8")


def _check(root, app):
    layers = {} if app is _ABSENT else {"app": app}
    (root / "config" / "project.json").write_text(
        json.dumps({"layers": layers}), encoding="utf-8"
    )
    cs.check_H()
    return [e for e in cs.errors if "layers.app" in e], cs.errors


def test_an_absent_layers_app_is_silent(repo):
    mine, errs = _check(repo, _ABSENT)
    assert mine == [] and errs == [], errs


def test_a_null_layers_app_declares_no_composition_root(repo):
    mine, errs = _check(repo, None)
    assert mine == [] and errs == [], errs


def test_a_runnable_package_is_clean(repo):
    _package(repo, "src/app")
    mine, errs = _check(
        repo, {"language": "python", "path": "src/app", "module": "app"}
    )
    assert mine == [] and errs == [], errs


def test_a_nested_package_and_a_module_file_are_clean(repo):
    _package(repo, "src/pkg/app")
    mine, _ = _check(repo, {"path": "src/pkg/app", "module": "pkg.app"})
    assert mine == [], mine
    (repo / "src" / "tool.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    mine, _ = _check(repo, {"path": "src/tool.py", "module": "tool"})
    assert mine == [], mine


def test_a_path_that_does_not_exist_is_an_error(repo):
    mine, _ = _check(repo, {"path": "src/app", "module": "app"})
    assert len(mine) == 1 and "layers.app.path" in mine[0], mine
    # A project that deleted its composition root is told the remedy, not only
    # the symptom: null, and the document that names the edits made with it
    # (src/app/README.md is gone along with the directory).
    assert "null" in mine[0] and "CONVENTIONS.md" in mine[0], mine


def test_a_package_without_a_main_is_an_error(repo):
    _package(repo, "src/app", main=False)
    mine, _ = _check(repo, {"path": "src/app", "module": "app"})
    assert len(mine) == 1 and "__main__.py" in mine[0], mine
    assert "layers.app.path" in mine[0], mine


def test_a_module_that_is_not_the_paths_dotted_form_is_an_error(repo):
    _package(repo, "src/app")
    mine, _ = _check(repo, {"path": "src/app", "module": "pkg.app"})
    assert len(mine) == 1 and "layers.app.module" in mine[0], mine


@pytest.mark.parametrize(
    "app, expect",
    [
        ("src/app", "layers.app"),
        (["src/app"], "layers.app"),
        ({"module": "app"}, "layers.app.path"),
        ({"path": "src/app"}, "layers.app.module"),
        ({"path": 3, "module": "app"}, "layers.app.path"),
        ({"path": "src/app", "module": ""}, "layers.app.module"),
    ],
)
def test_a_malformed_layers_app_is_one_error_naming_the_key(repo, app, expect):
    _package(repo, "src/app")
    mine, _ = _check(repo, app)
    assert len(mine) == 1 and expect in mine[0], mine


def test_keels_own_layers_app_is_declared_and_valid(monkeypatch):
    """Vacuity control: keel declares its composition root, and it checks clean."""
    manifest = json.loads((_ROOT / "config" / "project.json").read_text("utf-8"))
    assert "app" in manifest["layers"], "keel declares no layers.app"
    monkeypatch.setattr(cs, "ROOT", str(_ROOT))
    monkeypatch.setattr(cs, "errors", [])
    monkeypatch.setattr(cs, "warnings", [])
    monkeypatch.setattr(cs, "_CONFIG_READ", {})
    monkeypatch.setattr(cs, "_READ_REPORTED", set())
    cs.check_H()
    assert cs.errors == [], cs.errors
