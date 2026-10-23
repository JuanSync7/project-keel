"""
title: Unit — every agent CLI holds an --execute run to the model-call cap and says which model it chose
kind: tests
layer: n/a
summary: scripts/doc_review.py, scripts/refactor_practice.py, scripts/hooks/on_stop_doc_review.py and scripts/hooks/on_stop_triage.py each check, before the agent runs, that the run's upper bound of model calls (--max-chunks, --max-nodes, or the one call triage makes) is within config/project.json `agents.max_model_calls` (read through scripts/model_budget.py): a bound over the cap, or a negative bound that sets none, returns USAGE with the agent never called, a cap the config cannot give returns CONFIG, and a dry run is never refused, since it calls no model. An approved run hands the agent its bound as `max_model_calls`, the count its counted backend stops at; the agent stopping at that count (models.CallCapReached) returns FAILURE and a saved run the approval does not cover (models.RunNotApproved) returns USAGE, each naming what to do next. With --execute and no --model, each writes to stderr which model the registry default chose and why; with --model it writes no such line. The agent function is replaced by a recorder, so no model is built and nothing is written.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "hooks"))

import config_loader  # noqa: E402
import doc_review  # noqa: E402
import model_budget  # noqa: E402
import on_stop_doc_review  # noqa: E402
import on_stop_triage  # noqa: E402
import refactor_practice  # noqa: E402
from agents.doc_reviewer import DocReviewReport  # noqa: E402
from agents.practice_refactor import RefactorReport  # noqa: E402
from exit_codes import ExitCode  # noqa: E402
from models import CallCapReached, RunNotApproved  # noqa: E402
from models.registry import DEFAULT_MODEL  # noqa: E402

pytestmark = pytest.mark.unit

_DOC = DocReviewReport(True, 0, 0, 0, (), (), (), "", False)
_REF = RefactorReport("p", True, (), (), (), "", False)

# name -> (module, agent attribute, argv before flags, bound flag, what it returns)
_CLIS = {
    "doc_review": (doc_review, "review", [], "--max-chunks", _DOC),
    "refactor_practice": (refactor_practice, "refactor", ["p"], "--max-nodes", _REF),
    "on_stop_doc_review": (on_stop_doc_review, "review", ["x"], "--max-chunks", _DOC),
    "on_stop_triage": (on_stop_triage, "triage", ["x"], None, "answer"),
}


def _wire(monkeypatch, name, approved):
    module, attr, argv, flag, result = _CLIS[name]
    calls = []

    def agent(*args, **kwargs):
        calls.append(kwargs)
        return result

    monkeypatch.setattr(module, attr, agent)
    monkeypatch.setattr(model_budget, "cap", lambda root: approved)
    return module, argv, flag, calls


@pytest.mark.parametrize("name", sorted(_CLIS))
def test_a_cap_of_zero_refuses_an_execute_run_before_the_agent_runs(
    name, monkeypatch, capsys
):
    module, argv, flag, calls = _wire(monkeypatch, name, 0)
    assert module.main(argv + ["--execute"]) is ExitCode.USAGE
    assert calls == []
    err = capsys.readouterr().err
    assert "agents.max_model_calls" in err
    # The next step names the bound's flag only where the run has one.
    assert ("or lower %s" % flag in err) if flag else ("or lower" not in err)


@pytest.mark.parametrize("name", sorted(_CLIS))
def test_a_dry_run_is_never_refused_and_names_no_model(name, monkeypatch, capsys):
    module, argv, _flag, calls = _wire(monkeypatch, name, 0)
    assert module.main(argv) is ExitCode.SUCCESS
    assert len(calls) == 1 and not calls[0].get("execute")
    assert "registry default" not in capsys.readouterr().err


@pytest.mark.parametrize("name", sorted(_CLIS))
def test_an_approved_run_without_model_says_which_model_and_why(
    name, monkeypatch, capsys
):
    module, argv, _flag, calls = _wire(monkeypatch, name, 8)
    assert module.main(argv + ["--execute"]) is ExitCode.SUCCESS
    assert len(calls) == 1 and calls[0]["execute"] is True
    err = capsys.readouterr().err
    assert repr(DEFAULT_MODEL) in err and "registry default" in err


@pytest.mark.parametrize("name", sorted(_CLIS))
def test_a_named_model_is_not_announced(name, monkeypatch, capsys):
    module, argv, _flag, calls = _wire(monkeypatch, name, 8)
    assert module.main(argv + ["--execute", "--model", "fake"]) is ExitCode.SUCCESS
    assert calls[0]["model"] == "fake"
    assert "registry default" not in capsys.readouterr().err


@pytest.mark.parametrize("name", sorted(n for n in _CLIS if _CLIS[n][3]))
def test_a_bound_over_the_cap_is_refused_and_the_bound_is_what_runs(
    name, monkeypatch, capsys
):
    module, argv, flag, calls = _wire(monkeypatch, name, 3)
    assert module.main(argv + ["--execute", flag, "4"]) is ExitCode.USAGE
    assert calls == [] and flag in capsys.readouterr().err
    assert module.main(argv + ["--execute", flag, "3"]) is ExitCode.SUCCESS
    bound = {"--max-chunks": "max_chunks", "--max-nodes": "max_nodes"}[flag]
    assert calls[0][bound] == 3 and calls[0]["max_model_calls"] == 3


def test_triage_is_approved_its_one_call(monkeypatch):
    module, argv, _flag, calls = _wire(monkeypatch, "on_stop_triage", 8)
    assert module.main(argv + ["--execute"]) is ExitCode.SUCCESS
    assert calls[0]["max_model_calls"] == 1


def _raising(monkeypatch, name, exc):
    module, argv, _flag, _calls = _wire(monkeypatch, name, 8)
    _module, attr = _CLIS[name][:2]

    def agent(*args, **kwargs):
        raise exc

    monkeypatch.setattr(module, attr, agent)
    return module, argv


@pytest.mark.parametrize("name", sorted(_CLIS))
def test_a_run_stopped_at_its_count_is_a_failure_naming_the_count(
    name, monkeypatch, capsys
):
    module, argv = _raising(monkeypatch, name, CallCapReached(3, 3))
    assert module.main(argv + ["--execute"]) is ExitCode.FAILURE
    err = capsys.readouterr().err
    assert "approved 3 model call(s)" in err and "agents.max_model_calls" in err


@pytest.mark.parametrize("name", sorted(n for n in _CLIS if _CLIS[n][3]))
def test_a_saved_run_the_approval_does_not_cover_is_refused(name, monkeypatch, capsys):
    refusal = RunNotApproved("the saved run differs", "s.json", "remove s.json")
    module, argv = _raising(monkeypatch, name, refusal)
    assert module.main(argv + ["--execute"]) is ExitCode.USAGE
    err = capsys.readouterr().err
    assert "the saved run differs" in err and "remove s.json" in err


@pytest.mark.parametrize("name", sorted(n for n in _CLIS if _CLIS[n][3]))
def test_a_negative_bound_cannot_be_estimated_and_is_refused(name, monkeypatch, capsys):
    module, argv, flag, calls = _wire(monkeypatch, name, 10**6)
    assert module.main(argv + ["--execute", flag, "-1"]) is ExitCode.USAGE
    assert calls == [] and "cannot be estimated" in capsys.readouterr().err


@pytest.mark.parametrize("name", sorted(_CLIS))
def test_a_cap_the_config_cannot_give_is_a_config_refusal(name, monkeypatch, capsys):
    module, argv, _flag, calls = _wire(monkeypatch, name, 8)

    def broken(root):
        raise config_loader.WrongValue(
            "config/project.json", ["agents.max_model_calls is -1"]
        )

    monkeypatch.setattr(model_budget, "cap", broken)
    assert module.main(argv + ["--execute"]) is ExitCode.CONFIG
    assert calls == []
