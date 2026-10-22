"""
title: Unit — the model-call cap an agent's --execute run is held to
kind: tests
layer: n/a
summary: scripts/model_budget.py reads config/project.json `agents.max_model_calls` through the config loader, so an absent key is the default 0, which approves no call, and a negative or non-integer value is a config fault; approve() passes a run whose upper bound of calls is within the cap, and refuses, naming the bound, the cap and the key, a run whose bound is over it or that has no bound (None or negative), so a cap of 0 refuses every run; announce() names the model a run will use and why only when no model was named. No model is built and no file outside a temporary root is read.
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts"))

import config_loader  # noqa: E402
import model_budget  # noqa: E402
from models.registry import DEFAULT_MODEL  # noqa: E402

pytestmark = pytest.mark.unit


def _root(tmp_path, agents):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.json").write_text(
        json.dumps({"agents": agents}), encoding="utf-8"
    )
    return str(tmp_path)


def test_the_cap_is_read_from_config(tmp_path):
    assert model_budget.cap(_root(tmp_path, {"max_model_calls": 5})) == 5


def test_an_absent_cap_is_zero_and_says_so(tmp_path, capsys, monkeypatch):
    # As a fresh process: the default is announced once per process.
    monkeypatch.setattr(config_loader, "_ANNOUNCED", set())
    assert model_budget.cap(_root(tmp_path, {})) == 0
    assert "[using default] agents.max_model_calls = 0" in capsys.readouterr().err


@pytest.mark.parametrize("value", [-1, "8", 2.5, None])
def test_a_cap_that_is_not_a_whole_number_of_zero_or_more_is_a_config_fault(
    tmp_path, value
):
    with pytest.raises(config_loader.ConfigError):
        model_budget.cap(_root(tmp_path, {"max_model_calls": value}))


@pytest.mark.parametrize("needed, cap", [(0, 0), (1, 1), (3, 8)])
def test_a_run_within_the_cap_is_approved(needed, cap):
    assert model_budget.approve(needed, cap, "--max-chunks") is None


@pytest.mark.parametrize("needed, cap", [(1, 0), (9, 8)])
def test_a_run_over_the_cap_is_refused_naming_bound_cap_and_key(needed, cap):
    with pytest.raises(model_budget.SpendRefused) as info:
        model_budget.approve(needed, cap, "--max-chunks")
    text = " ".join(info.value.parts)
    assert "%d model call" % needed in text
    assert "agents.max_model_calls" in text and str(cap) in text
    assert "--max-chunks" in info.value.next_step


def test_a_fixed_bound_names_only_the_key_to_raise():
    with pytest.raises(model_budget.SpendRefused) as info:
        model_budget.approve(1, 0, None)
    assert info.value.next_step == "raise agents.max_model_calls to 1 or more"


@pytest.mark.parametrize("needed", [None, -1])
def test_a_run_with_no_bound_is_refused_whatever_the_cap(needed):
    with pytest.raises(model_budget.SpendRefused) as info:
        model_budget.approve(needed, 10**6, "--max-nodes")
    assert "cannot be estimated" in info.value.what
    assert "--max-nodes" in info.value.next_step


def test_announce_names_the_default_and_why_only_when_no_model_was_named():
    line = model_budget.announce("doc_review", None)
    assert line is not None
    assert repr(DEFAULT_MODEL) in line and "--model" in line
    assert "models/registry.py DEFAULT_MODEL" in line
    assert model_budget.announce("doc_review", "fake") is None
