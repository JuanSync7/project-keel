"""
title: Unit — generate_aad_schema --check (skip vs fail)
kind: tests
layer: n/a
summary: The AAD-schema pre-commit hook may legitimately no-op — the ambient python3 can be too old to parse the adapter, or pydantic can be absent — but it must no-op ONLY for those environment reasons. A genuine breakage in the descriptor model raises too, and today every exception collapses into the same `return 0`, so the drift guard reports success while checking nothing. Pins the environment/defect split in both --check and write modes.
"""
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts" / "agent_surface"))

import generate_aad_schema as gas  # noqa: E402

pytestmark = pytest.mark.unit

# The environment cannot run the check: nothing is known about the schema, so a
# pre-commit hook on an arbitrary host must stay out of the way.
ENVIRONMENT = [
    ImportError("No module named 'pydantic'"),
    ModuleNotFoundError("No module named 'pydantic'"),
    SyntaxError("future feature annotations is not defined (descriptor.py, line 7)"),
]

# The environment ran the check and the MODEL is broken. Every one of these means
# `make agent-surface-schema` would fail too — the committed contract is
# unverifiable and the gate must say so.
DEFECT = [
    TypeError("unhashable type"),
    AttributeError("'AadDescriptor' has no attribute 'model_json_schema'"),
    ValueError("invalid field default"),
    RuntimeError("pydantic core panicked"),
    KeyError("title"),
]


def _raise(exc):
    def _boom():
        raise exc
    return _boom


def _ids(excs):
    return [type(e).__name__ for e in excs]


# --- MUST-FAIL: the check ran and found the model broken ---------------------

@pytest.mark.parametrize("exc", DEFECT, ids=_ids(DEFECT))
def test_check_fails_when_the_model_itself_is_broken(monkeypatch, capsys, exc):
    monkeypatch.setattr(gas, "_schema", _raise(exc))
    rc = gas.main(["--check"])
    err = capsys.readouterr().err
    assert rc != 0, "a broken descriptor model reported success"
    assert type(exc).__name__ in err, err


@pytest.mark.parametrize("exc", DEFECT, ids=_ids(DEFECT))
def test_write_mode_fails_when_the_model_is_broken(monkeypatch, tmp_path, exc):
    """Write mode already failed on everything; it must keep doing so."""
    monkeypatch.setattr(gas, "_schema", _raise(exc))
    assert gas.main(["--out", str(tmp_path / "s.json")]) != 0


# --- MUST-SKIP: the environment cannot run the check at all ------------------

@pytest.mark.parametrize("exc", ENVIRONMENT, ids=_ids(ENVIRONMENT))
def test_check_skips_when_the_environment_cannot_run_it(monkeypatch, capsys, exc):
    """The documented contract: a pre-commit `python3` entry parses under an old
    interpreter and skips gracefully (docs/guides/deterministic-checks.md:232)."""
    monkeypatch.setattr(gas, "_schema", _raise(exc))
    rc = gas.main(["--check"])
    err = capsys.readouterr().err
    assert rc == 0, err
    assert "skip" in err.lower(), err


@pytest.mark.parametrize("exc", ENVIRONMENT, ids=_ids(ENVIRONMENT))
def test_write_mode_still_fails_when_deps_are_absent(monkeypatch, tmp_path, exc):
    """Skipping is a --check affordance only: `make agent-surface-schema` must
    never silently write nothing."""
    monkeypatch.setattr(gas, "_schema", _raise(exc))
    assert gas.main(["--out", str(tmp_path / "s.json")]) != 0


# --- the happy paths stay exactly as they were -------------------------------

def test_check_reports_a_stale_committed_schema(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(gas, "_schema", lambda: {"title": "fresh"})
    monkeypatch.setattr(gas, "_ROOT", str(tmp_path))
    (tmp_path / "s.json").write_text("stale\n", encoding="utf-8")
    assert gas.main(["--check", "--out", "s.json"]) == 1
    assert "stale" in capsys.readouterr().err


def test_check_passes_on_a_fresh_committed_schema(monkeypatch, tmp_path):
    monkeypatch.setattr(gas, "_schema", lambda: {"title": "fresh"})
    monkeypatch.setattr(gas, "_ROOT", str(tmp_path))
    gas.main(["--out", "s.json"])
    assert gas.main(["--check", "--out", "s.json"]) == 0
