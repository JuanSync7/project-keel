"""
title: Unit — long_scripts (which recorded runs say a script is long and unlisted)
kind: tests
layer: n/a
summary: The search script's judgement as a pure function over an injected config and durations dict, with no disk, process or network. A key is proposed only when its last measured run took longer than the threshold and launcher.long_scripts does not list it, whatever the run's outcome, because the duration is the fact. A run with no duration, an incomplete or no-capacity entry and a malformed entry are unjudged and count neither way, so a file holding only those, or nothing, is the verdict "nothing judged", which is distinct from "none is long".
"""

import copy
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import launch  # noqa: E402
import long_scripts  # noqa: E402

pytestmark = pytest.mark.unit


def _cfg():
    manifest = json.loads(
        (_ROOT / "config" / "project.json").read_text(encoding="utf-8")
    )
    return launch.load_launcher_config(copy.deepcopy(manifest))


def _record(outcome, seconds, status=0):
    return {
        "outcome": outcome,
        "seconds": seconds,
        "status": status,
        "where": "shared-host",
    }


def test_proposals_are_unlisted_keys_over_the_threshold_and_zero_records_is_not_nothing_long():
    cfg = _cfg()
    over = cfg.long_after_seconds + 1
    listed = sorted(cfg.long_scripts)
    assert listed, "the shipped config lists no long script -- zero items"
    assert len(set(long_scripts.VERDICTS)) == len(long_scripts.VERDICTS) == 3

    empty = long_scripts.judge(cfg, {})
    assert (empty.verdict, empty.judged, empty.proposals) == ("nothing-judged", 0, ())

    short = long_scripts.judge(cfg, {"make lint": _record("succeeded", 30)})
    assert (short.verdict, short.judged, short.proposals) == ("none", 1, ())

    found = long_scripts.judge(
        cfg,
        {
            "make x": _record("succeeded", over),
            listed[0]: _record("succeeded", over * 10),
            "make lint": _record("succeeded", 30),
            "make y": _record("failed", over, status=3),
        },
    )
    assert found.verdict == "proposals" and found.judged == 4, found
    # Sorted by key; a failed run over the threshold is proposed too.
    assert found.proposals == (
        ("make x", over, "succeeded"),
        ("make y", over, "failed"),
    ), found.proposals

    unmeasured = {
        "make a": _record("incomplete", None, status=None),
        "make b": _record("no-capacity", None, status=None),
        "make c": {"outcome": "succeeded"},
    }
    nothing = long_scripts.judge(cfg, unmeasured)
    assert nothing.verdict == "nothing-judged" and nothing.judged == 0, nothing
    assert [k for k, _why in nothing.unjudged] == ["make a", "make b", "make c"]
    assert all(why for _k, why in nothing.unjudged)

    mixed = long_scripts.judge(
        cfg, dict(unmeasured, **{"make lint": _record("succeeded", 1)})
    )
    assert (mixed.verdict, mixed.judged, len(mixed.unjudged)) == ("none", 1, 3)
