"""
title: Unit — script module identity across import spellings
summary: Both import orders share a module, its classes and its package attribute; all imports and package attributes are restored for the next test on the worker.
"""

import importlib
import importlib.util
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit
_ROOT = Path(__file__).resolve().parents[3]
_MODULES = (
    "config_loader",
    "child_env",
    "bounded_match",
    "corpus_level",
    "doc_review",
    "pytest_markers",
    "refactor_practice",
)


@pytest.fixture
def fresh_imports(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Restore even dependency imports and their bindings on existing packages."""
    saved_modules = sys.modules.copy()
    packages = {
        name: (module, vars(module).copy())
        for name, module in saved_modules.items()
        if module is not None and hasattr(module, "__path__")
    }
    monkeypatch.syspath_prepend(str(_ROOT))
    monkeypatch.syspath_prepend(str(_ROOT / "scripts"))
    try:
        yield
    finally:
        for name in set(sys.modules) - set(saved_modules):
            del sys.modules[name]
        sys.modules.update(saved_modules)
        for module, attributes in packages.values():
            for name in set(vars(module)) - set(attributes):
                delattr(module, name)
            vars(module).update(attributes)


@pytest.mark.parametrize("module_name", _MODULES)
@pytest.mark.parametrize("first_prefix", ["", "scripts."])
def test_both_spellings_share_module_and_class(
    fresh_imports: None,
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
    first_prefix: str,
) -> None:
    package = importlib.import_module("scripts")
    for name in (module_name, "scripts." + module_name):
        sys.modules.pop(name, None)
    monkeypatch.delattr(package, module_name, raising=False)
    loaded = importlib.import_module(first_prefix + module_name)
    # Some CLI modules define functions only. A test class defined in their
    # namespace proves class and mutable state identity without adding API.
    exec("class IdentityProbe:\n    pass\n", loaded.__dict__)
    bare = importlib.import_module(module_name)
    dotted = importlib.import_module("scripts." + module_name)
    assert loaded is bare is dotted
    assert bare.IdentityProbe is dotted.IdentityProbe
    assert getattr(package, module_name) is loaded


@pytest.mark.parametrize("module_name", _MODULES)
def test_exec_module_requires_registration(
    fresh_imports: None, module_name: str
) -> None:
    spec = importlib.util.spec_from_file_location(
        "unregistered_script", _ROOT / "scripts" / (module_name + ".py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with pytest.raises(ImportError, match="register the module before exec_module"):
        spec.loader.exec_module(module)


@pytest.mark.parametrize("package_state", ["absent", "foreign", "unresolvable"])
def test_package_binding_respects_its_directory(
    fresh_imports: None, monkeypatch: pytest.MonkeyPatch, package_state: str
) -> None:
    from scripts.module_identity import register_module

    module = ModuleType("identity_example")
    monkeypatch.setitem(sys.modules, module.__name__, module)
    foreign = ModuleType("scripts")
    foreign.__path__ = [str(_ROOT / "other_scripts")]
    states: dict[str, Callable[[], object]] = {
        "absent": lambda: sys.modules.pop("scripts", None),
        "foreign": lambda: monkeypatch.setitem(sys.modules, "scripts", foreign),
        "unresolvable": lambda: sys.modules.pop("scripts", None),
    }
    states[package_state]()
    paths = {"absent": sys.path, "foreign": sys.path, "unresolvable": []}
    monkeypatch.setattr(sys, "path", paths[package_state])
    register_module(module.__name__, str(_ROOT / "scripts" / "identity_example.py"))
    package = sys.modules.get("scripts")
    expected = {"absent": module, "foreign": None, "unresolvable": None}
    assert getattr(package, "identity_example", None) is expected[package_state]
    assert sys.modules["scripts.identity_example"] is module
