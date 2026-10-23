"""
title: Unit — the triage doer runs on an injected backend
kind: tests
layer: n/a
summary: triage(payload, execute=True, backend=b) sends the real triage prompt (its preamble and the payload) to b and returns b's reply, which is how evals replay and live drive the shipped prompt; passing both model= and backend= is a ValueError, and the default dry run returns the rendered prompt without calling either. An execute run on a named model needs max_model_calls (ValueError without), and is held to it, so a count of 0 makes no call.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from agents.triage import triage  # noqa: E402
from models import (  # noqa: E402
    CallCapReached,
    ModelBackend,
    get_model,
    registry,  # noqa: E402
)

pytestmark = pytest.mark.unit


class _Seen(ModelBackend):
    name = "seen"

    def __init__(self, reply="x", fail=False):
        self.reply = reply
        self.fail = fail
        self.prompts = []

    def run(self, prompt, **opts):
        if self.fail:
            raise AssertionError("the dry run called the backend")
        self.prompts.append(prompt)
        return self.reply


def test_triage_runs_on_an_injected_backend():
    seen = _Seen(reply="x")
    assert triage("disk full on /var", execute=True, backend=seen) == "x"
    (prompt,) = seen.prompts
    assert "disk full on /var" in prompt
    assert "You are a triage assistant" in prompt
    dry = triage("disk full on /var")
    assert dry.endswith(prompt), "the dry run and the executed prompt differ"

    assert triage("p", execute=True, backend=get_model("fake", reply="y")) == "y"

    with pytest.raises(ValueError):
        triage("p", execute=True, model="fake", backend=_Seen())

    out = triage("p", backend=_Seen(fail=True))
    assert out.startswith("[dry-run]"), out


def test_an_execute_run_on_a_model_is_held_to_its_approved_count(monkeypatch):
    built = []

    class _Fake(_Seen):
        def __init__(self, **kwargs):
            super().__init__()
            built.append(self)

    monkeypatch.setitem(registry._REGISTRY, "fake", _Fake)
    with pytest.raises(ValueError, match="max_model_calls"):
        triage("p", execute=True, model="fake")
    with pytest.raises(CallCapReached):
        triage("p", execute=True, model="fake", max_model_calls=0)
    assert triage("p", execute=True, model="fake", max_model_calls=1) == "x"
    assert [len(b.prompts) for b in built] == [0, 1]
