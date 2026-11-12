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


def test_every_transport_extra_the_config_names_is_a_known_surface():
    """A transport extra missing from SURFACES makes required_extras raise the
    moment that transport is enabled, so the pair is held at rest."""
    import config_loader

    named = config_loader.read(optional_deps._ROOT)["transports"]["extras"]
    assert named, "transports.extras names nothing -- zero items"
    assert set(named.values()) <= set(optional_deps.SURFACES)


def test_an_enabled_grpc_transport_owes_the_grpc_surface(monkeypatch):
    monkeypatch.delenv(optional_deps.ENV_VAR, raising=False)
    loaded = {
        "transports": {
            "enabled": ["rest", "grpc"],
            "extras": {"rest": "transport", "grpc": "grpc"},
        }
    }
    assert optional_deps.required_extras(loaded) == {"transport", "grpc"}
    loaded["transports"]["enabled"] = ["rest"]
    assert optional_deps.required_extras(loaded) == {"transport"}
