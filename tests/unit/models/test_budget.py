"""
title: Unit — the model-call budget a run's backend is held to
kind: tests
layer: backend
summary: models.CountedModel passes a call to the backend it wraps until the approved count is reached and then raises CallCapReached without calling it, so a count of 0 lets no call through; ModelMeter builds the named backend only on the first call, once, wrapped in that count; approve_resume passes a saved run whose model and remaining calls are what the run approves and raises RunNotApproved, naming the saved value, the approved one and the snapshot to remove, for a different model (the registry default and its name are the same model) or more calls left than approved; approved_cap reads config/project.json `agents.max_model_calls` through the config loader. SessionBudget admits a question only while the calls made so far plus the question's bound stay within its total, and raises SessionCapReached (a CallCapReached) naming the total, the calls made and the bound otherwise, so a total of 0 admits only a question that may make none; the backend its counted() factory builds adds every call it passes on, one that raises included, to that count, so the total is the calls made, not the bounds admitted; approved_session_cap reads `agents.max_session_model_calls` through the loader, absent being its declared default 0. No model outside this file is built.
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
    SessionBudget,
    SessionCapReached,
    approve_resume,
    approved_cap,
    approved_session_cap,
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


def test_one_call_left_past_the_approved_count_is_refused():
    # The boundary: as many left as approved passes (above), one more refuses.
    with pytest.raises(RunNotApproved):
        approve_resume(where="s.json", saved_model="fake", model="fake", left=3, cap=2)


def test_the_approved_cap_is_read_through_the_loader(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    path = tmp_path / "config" / "project.json"
    path.write_text(json.dumps({"agents": {"max_model_calls": 4}}), encoding="utf-8")
    assert approved_cap(str(tmp_path)) == 4
    path.write_text(json.dumps({"agents": {"max_model_calls": -1}}), encoding="utf-8")
    with pytest.raises(config_loader.ConfigError):
        approved_cap(str(tmp_path))


def test_a_session_admits_a_question_whose_bound_fits_what_is_left():
    session = SessionBudget(3)
    session.admit(3)  # the boundary: a bound equal to the total fits
    session.calls = 2
    session.admit(1)
    assert session.calls == 2  # admitting spends nothing; calls do


def test_a_session_refuses_a_question_one_call_past_its_total():
    session = SessionBudget(3)
    session.calls = 2
    with pytest.raises(SessionCapReached) as exc:
        session.admit(2)
    assert isinstance(exc.value, CallCapReached)
    assert (exc.value.total, exc.value.calls, exc.value.bound) == (3, 2, 2)
    assert "3" in str(exc.value) and "2 made" in str(exc.value)


def test_a_session_total_of_zero_admits_only_a_question_that_may_make_none():
    session = SessionBudget(0)
    session.admit(0)
    with pytest.raises(SessionCapReached):
        session.admit(1)


@pytest.mark.parametrize("bad", [(-1, 0), (0, -1)])
def test_a_negative_total_or_bound_is_refused(bad):
    total, bound = bad
    with pytest.raises(ValueError, match="0 or more"):
        SessionBudget(total).admit(bound)


class _Raises(ModelBackend):
    name = "raises"

    def run(self, prompt, **opts):
        raise RuntimeError("the backend failed after the request went out")


def test_the_session_counts_each_call_its_backends_pass_on():
    session = SessionBudget(5)
    built = []

    def factory(name):
        built.append(name)
        return _Echo() if name == "echo" else _Raises()

    make = session.counted(factory)
    backend = make("echo")
    assert backend.name == "echo" and built == ["echo"]
    assert backend.run("a") == "reply to a"
    make("echo").run("b")
    with pytest.raises(RuntimeError):
        make("raises").run("c")
    # A call that raises still spent what it sent, so it is counted too.
    assert session.calls == 3


def test_the_session_total_is_read_through_the_loader(tmp_path, capsys):
    (tmp_path / "config").mkdir()
    path = tmp_path / "config" / "project.json"
    path.write_text(json.dumps({"agents": {}}), encoding="utf-8")
    # The loader says a default once per process, so an earlier test that
    # took this one would leave nothing for this assert to see.
    config_loader._ANNOUNCED.clear()
    try:
        assert approved_session_cap(str(tmp_path)) == 0
        err = capsys.readouterr().err
        assert "[using default] agents.max_session_model_calls = 0" in err, err
    finally:
        config_loader._ANNOUNCED.clear()
    path.write_text(
        json.dumps({"agents": {"max_session_model_calls": 7}}), encoding="utf-8"
    )
    assert approved_session_cap(str(tmp_path)) == 7
    for bad in (-1, None, "7", 1.5):
        path.write_text(
            json.dumps({"agents": {"max_session_model_calls": bad}}), encoding="utf-8"
        )
        with pytest.raises(config_loader.ConfigError):
            approved_session_cap(str(tmp_path))
