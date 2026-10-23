"""
title: Unit — on_stop_triage hook doer (the model-absent path)
kind: tests
layer: n/a
summary: The event-hook doer over agents.triage. A hook fires where it fires — a laptop without Claude Code, a CI runner with no key — so an unavailable model is a stated skip at exit 0, never a failed event; a model that runs and fails still raises. Dry-run (the default) never touches a model at all.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts" / "hooks"))
sys.path.insert(0, str(_ROOT / "scripts"))

import model_budget  # noqa: E402
import on_stop_triage as hook  # noqa: E402
from models import ModelUnavailable  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _approved(monkeypatch):
    # These cases are about the model-absent path, so the run is approved;
    # tests/unit/scripts/test_agent_spend_cap.py holds the cap itself.
    monkeypatch.setattr(model_budget, "cap", lambda root: 1)


def test_an_unavailable_model_is_a_stated_skip_at_exit_zero(monkeypatch, capsys):
    def no_model(payload, execute, model, max_model_calls):
        raise ModelUnavailable("claude binary 'claude' is not on PATH")

    monkeypatch.setattr(hook, "triage", no_model)
    assert hook.main(["a failing job", "--execute"]) == 0
    out = capsys.readouterr().out
    assert "skipping" in out and "not on PATH" in out


def test_a_model_that_runs_and_fails_still_raises(monkeypatch):
    def broken(payload, execute, model, max_model_calls):
        raise RuntimeError("claude headless failed: boom")

    monkeypatch.setattr(hook, "triage", broken)
    with pytest.raises(RuntimeError):
        hook.main(["a failing job", "--execute"])


def test_dry_run_prints_the_preview_and_needs_no_model(monkeypatch, capsys):
    monkeypatch.setattr(
        hook,
        "triage",
        lambda payload, execute, model, max_model_calls: (
            "PREVIEW %s %s" % (payload, execute)
        ),
    )
    assert hook.main(["payload"]) == 0
    assert "PREVIEW payload False" in capsys.readouterr().out
