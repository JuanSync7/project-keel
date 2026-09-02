"""
title: Unit — export_openapi --check (skip vs fail)
kind: tests
layer: n/a
summary: The OpenAPI drift guard may legitimately no-op — the ambient python3 can be too old to parse the app, or FastAPI can be absent — but it must no-op ONLY for those environment reasons. A genuine breakage in the app raises too (a duplicate operation id, a bad response_model, a NameError in the import graph), and every exception used to collapse into the same `return 0`, so a check inside `make verify` reported success while checking nothing — inherited by every generated project, since copier.yml does not exclude it. Pins the environment/defect split in both --check and write modes, mirroring tests/unit/scripts/test_generate_aad_schema.py.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "api" / "rest_fastapi"))

import export_openapi as eo  # noqa: E402

pytestmark = pytest.mark.unit

# The environment cannot run the check: nothing is known about the contract, so a
# pre-commit hook on an arbitrary host must stay out of the way.
ENVIRONMENT = [
    ImportError("No module named 'fastapi'"),
    ModuleNotFoundError("No module named 'fastapi'"),
    SyntaxError("invalid syntax (app.py, line 12)"),
]

# The environment ran the check and the APP is broken. Every one of these means
# `make check-openapi` would fail too — the committed contract is unverifiable and
# the gate must say so rather than launder it into a green run.
DEFECT = [
    TypeError("unhashable type"),
    AttributeError("'FastAPI' object has no attribute 'openapi'"),
    ValueError("Duplicate Operation ID read_thing for function read_thing"),
    RuntimeError("route registration failed"),
    KeyError("paths"),
    NameError("name 'Thing' is not defined"),
]


def _raise(exc):
    def _boom():
        raise exc

    return _boom


def _ids(excs):
    return [type(e).__name__ for e in excs]


# --- MUST-FAIL: the check ran and found the app broken ------------------------


@pytest.mark.parametrize("exc", DEFECT, ids=_ids(DEFECT))
def test_check_fails_when_the_app_itself_is_broken(monkeypatch, capsys, exc):
    """The defect this file exists for: `--check` returned 0 for every one of
    these, inside `make verify`, in keel and in every project generated from it."""
    monkeypatch.setattr(eo, "_spec", _raise(exc))
    rc = eo.main(["--check"])
    err = capsys.readouterr().err
    assert rc != 0, "a broken app reported a passing OpenAPI check"
    assert type(exc).__name__ in err, err


@pytest.mark.parametrize("exc", DEFECT, ids=_ids(DEFECT))
def test_write_mode_fails_when_the_app_is_broken(monkeypatch, tmp_path, exc):
    """Write mode already failed on everything; it must keep doing so."""
    monkeypatch.setattr(eo, "_spec", _raise(exc))
    assert eo.main(["--out", str(tmp_path / "openapi.json")]) != 0


# --- MUST-SKIP: the environment cannot run the check at all -------------------


@pytest.mark.parametrize("exc", ENVIRONMENT, ids=_ids(ENVIRONMENT))
def test_check_skips_when_the_environment_cannot_run_it(monkeypatch, capsys, exc):
    """A `language: system` pre-commit hook execs the ambient python3, which may
    be old or FastAPI-less. Absent is not broken (ADR-0007): say so, exit 0."""
    monkeypatch.setattr(eo, "_spec", _raise(exc))
    rc = eo.main(["--check"])
    err = capsys.readouterr().err
    assert rc == 0, err
    assert "skip" in err.lower(), err


@pytest.mark.parametrize("exc", ENVIRONMENT, ids=_ids(ENVIRONMENT))
def test_write_mode_still_fails_when_deps_are_absent(monkeypatch, tmp_path, exc):
    """Skipping is a --check affordance only: `make check-openapi` writing
    nothing and reporting success would be the same defect one target over."""
    monkeypatch.setattr(eo, "_spec", _raise(exc))
    assert eo.main(["--out", str(tmp_path / "openapi.json")]) != 0
