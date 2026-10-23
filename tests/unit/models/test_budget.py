"""
title: Unit — the model-call budget a run's backend is held to
kind: tests
layer: backend
summary: models.CountedModel passes a call to the backend it wraps until the approved count is reached and then raises CallCapReached without calling it, so a count of 0 lets no call through; ModelMeter builds the named backend only on the first call, once, wrapped in that count; approve_resume passes a saved run whose model and remaining calls are what the run approves and raises RunNotApproved, naming the saved value, the approved one and the snapshot to remove, for a different model (the registry default and its name are the same model) or more calls left than approved; approved_cap reads config/project.json `agents.max_model_calls` through the config loader. No model outside this file is built.
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from models import (  # noqa: E402
    CallCapReached,
    CountedModel,
    ModelBackend,
    ModelMeter,
    RunNotApproved,
    approve_resume,
    approved_cap,
)
from models.registry import DEFAULT_MODEL  # noqa: E402
from scripts import config_loader  # noqa: E402

pytestmark = pytest.mark.unit


class _Echo(ModelBackend):
    name = "echo"

    def __init__(self):
        self.prompts = []

    def run(self, prompt, **opts):
        self.prompts.append(prompt)
        return "reply to " + prompt


def test_calls_pass_through_until_the_approved_count_then_refuse():
    inner = _Echo()
    counted = CountedModel(inner, 2)
    assert counted.run("a") == "reply to a"
    assert counted.run("b") == "reply to b"
    with pytest.raises(CallCapReached) as exc:
        counted.run("c")
    assert inner.prompts == ["a", "b"]
    assert (exc.value.cap, exc.value.calls) == (2, 2)
    assert counted.calls == 2 and counted.name == "echo"


def test_a_count_of_zero_lets_no_call_through():
    inner = _Echo()
    with pytest.raises(CallCapReached):
        CountedModel(inner, 0).run("a")
    assert inner.prompts == []


def test_a_negative_count_is_refused_at_construction():
    with pytest.raises(ValueError, match="0 or more"):
        CountedModel(_Echo(), -1)


def test_the_meter_builds_the_named_backend_once_on_first_use():
    built = []

    def factory(name):
        built.append(name)
        return _Echo()

    meter = ModelMeter("echo", 3, factory)
    assert built == [] and meter.calls == 0
    meter.backend().run("a")
    meter.backend().run("b")
    assert built == ["echo"] and meter.calls == 2
    meter.backend().run("c")
    with pytest.raises(CallCapReached):
        meter.backend().run("d")


def test_a_resume_on_the_approved_model_within_the_count_passes():
    approve_resume(where="s.json", saved_model="fake", model="fake", left=2, cap=2)
    # The registry default and its own name are the same model.
    approve_resume(where="s.json", saved_model=None, model=DEFAULT_MODEL, left=0, cap=0)


def test_a_resume_on_another_model_is_refused_naming_both():
    with pytest.raises(RunNotApproved) as exc:
        approve_resume(where="s.json", saved_model=None, model="fake", left=1, cap=5)
    text = " ".join(exc.value.parts)
    assert repr(DEFAULT_MODEL) in text and "'fake'" in text and "s.json" in text


def test_a_resume_with_more_calls_left_than_approved_is_refused():
    with pytest.raises(RunNotApproved) as exc:
        approve_resume(where="s.json", saved_model="fake", model="fake", left=5, cap=1)
    what, on, next_step = exc.value.parts
    assert "5" in what and "1" in what and on == "s.json" and "s.json" in next_step


def test_the_approved_cap_is_read_through_the_loader(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    path = tmp_path / "config" / "project.json"
    path.write_text(json.dumps({"agents": {"max_model_calls": 4}}), encoding="utf-8")
    assert approved_cap(str(tmp_path)) == 4
    path.write_text(json.dumps({"agents": {"max_model_calls": -1}}), encoding="utf-8")
    with pytest.raises(config_loader.ConfigError):
        approved_cap(str(tmp_path))
