"""
title: Unit — optional imports explain their owning extra
summary: Missing optional modules skip with the module, extra and registered install command; required imports still propagate ImportError and installed modules return normally.
"""

import sys

import pytest

import optional_deps

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("extra", sorted(optional_deps.SURFACES))
def test_missing_optional_import_names_module_extra_and_install(monkeypatch, extra):
    monkeypatch.setattr(optional_deps, "required_extras", lambda loaded: set())
    module = "keel_missing_optional_dependency"
    with pytest.raises(pytest.skip.Exception) as skipped:
        optional_deps.importorskip(module, extra=extra)
    reason = str(skipped.value)
    assert module in reason
    assert "%s extra" % extra in reason
    assert optional_deps.SURFACES[extra] in reason


def test_required_import_still_raises(monkeypatch):
    monkeypatch.setattr(optional_deps, "required_extras", lambda loaded: {"template"})
    with pytest.raises(ModuleNotFoundError, match="keel_missing_optional_dependency"):
        optional_deps.importorskip("keel_missing_optional_dependency", extra="template")


def test_available_optional_import_returns_module(monkeypatch):
    monkeypatch.setattr(optional_deps, "required_extras", lambda loaded: set())
    assert optional_deps.importorskip("sys", extra="template") is sys
