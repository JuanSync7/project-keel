"""
title: Unit — eval verdict and report rendering
kind: tests
layer: n/a
summary: verdict compares the exact rational score Fraction(passed, total) with Fraction(repr(threshold)), so a score equal to the threshold passes, one case fewer fails, and 7 of 100 meets 0.07 although 0.07*100 is 7.000000000000001; an errored or stale case reddens a suite above the threshold, an absent backend is its own result unless the cases that did run already prove the suite fails, a suite whose cases were not run because the backend went absent earlier is absent rather than a pass over zero judged cases, and zero cases is refused; render writes canonical JSON (sorted keys, two-space indent, one newline) with suites and cases sorted and no clock, host or absolute path.
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from evals import Outcome, Report, SuiteResult, aggregate, render, verdict  # noqa: E402

pytestmark = pytest.mark.unit


def _outs(**counts):
    out = []
    for name, n in counts.items():
        out.extend([name.replace("_", "-")] * n)
    return out


@pytest.mark.parametrize(
    "passed, total, threshold, ok",
    [
        (4, 5, 0.8, True),
        (3, 5, 0.8, False),
        (7, 100, 0.07, True),
        (6, 100, 0.07, False),
        (10, 10, 1.0, True),
        (9, 10, 1.0, False),
        (10, 10, 1, True),
        (1, 3, 1 / 3, True),
    ],
)
def test_threshold_boundary_is_inclusive_and_exact(passed, total, threshold, ok):
    outcomes = _outs(**{"pass": passed, "fail": total - passed})
    result, reasons = verdict(passed, total, threshold, outcomes)
    if ok:
        assert (result, reasons) == ("pass", []), (result, reasons)
    else:
        assert (result, reasons) == ("fail", ["below-threshold"]), (result, reasons)


@pytest.mark.parametrize(
    "outcomes, threshold, want",
    [
        (_outs(**{"pass": 9, "error": 1}), 0.5, ("fail", ["case-error"])),
        (_outs(**{"pass": 9, "stale": 1}), 0.5, ("fail", ["stale-recording"])),
        (
            _outs(**{"pass": 8, "stale": 1, "error": 1}),
            0.5,
            ("fail", ["case-error", "stale-recording"]),
        ),
        (_outs(absent=1, not_run=9), 1.0, ("absent", ["backend-absent"])),
        # A later suite of a run whose backend went absent earlier: no case of
        # it was judged, so it is absent, never a pass over zero judged cases.
        (_outs(not_run=3), 1.0, ("absent", ["backend-absent"])),
        (_outs(not_run=3), 0.5, ("absent", ["backend-absent"])),
        (_outs(**{"pass": 2, "not_run": 1}), 0.5, ("absent", ["backend-absent"])),
        (_outs(**{"pass": 9, "absent": 1}), 1.0, ("absent", ["backend-absent"])),
        (
            _outs(**{"pass": 1, "fail": 1, "absent": 1, "not_run": 7}),
            1.0,
            ("fail", ["backend-absent", "below-threshold"]),
        ),
        (
            _outs(**{"pass": 1, "fail": 1, "absent": 1, "not_run": 7}),
            0.5,
            ("absent", ["backend-absent"]),
        ),
    ],
)
def test_error_stale_or_absent_reddens_even_above_threshold(outcomes, threshold, want):
    passed = outcomes.count("pass")
    assert verdict(passed, len(outcomes), threshold, outcomes) == want


def test_zero_cases_is_refused():
    assert verdict(0, 0, 1.0, []) == ("refused", ["refused"])


def test_aggregate_is_pass_only_when_every_suite_passes():
    def suite(name, result, reasons):
        return SuiteResult(name, "d/%s.jsonl" % name, 1, 1, result, reasons, [])

    assert aggregate([suite("a", "pass", []), suite("b", "pass", [])]) == ("pass", [])
    assert aggregate(
        [suite("a", "absent", ["backend-absent"]), suite("b", "pass", [])]
    ) == ("absent", ["backend-absent"])
    assert aggregate(
        [
            suite("a", "absent", ["backend-absent"]),
            suite("b", "fail", ["case-error"]),
        ]
    ) == ("fail", ["backend-absent", "case-error"])
    assert aggregate([]) == ("refused", ["refused"])


def test_aggregate_ranks_refused_then_incomplete_then_fail_then_absent():
    # A run that could not judge some input must not read as a plain fail: the
    # worse verdict wins whatever order the suites arrive in.
    def suite(name, result):
        return SuiteResult(name, "d/%s.jsonl" % name, 1, 0, result, [], [])

    ranked = ["refused", "incomplete", "fail", "absent", "pass"]
    for i, worse in enumerate(ranked[:-1]):
        for better in ranked[i + 1 :]:
            for order in ((worse, better), (better, worse)):
                got, _ = aggregate([suite("s%d" % n, r) for n, r in enumerate(order)])
                assert got == worse, (order, got)


def _report(suite_names, case_ids):
    suites = [
        SuiteResult(
            name,
            "evals/datasets/%s.jsonl" % name,
            len(case_ids),
            len(case_ids),
            "pass",
            [],
            [
                Outcome(i, "pass", "exact", "matched", "sha256:" + "a" * 64)
                for i in case_ids
            ],
        )
        for name in suite_names
    ]
    return Report(
        schema="config/evals/eval-report.schema.json",
        schema_version=1,
        mode="replay",
        model=None,
        threshold=1.0,
        calls=0,
        result="pass",
        reasons=[],
        detail=None,
        suites=suites,
    )


def _keys(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield key
            yield from _keys(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _keys(value)


def test_render_is_canonical_and_clockless():
    forward = render(_report(["a", "b"], ["x", "y"]))
    backward = render(_report(["b", "a"], ["y", "x"]))
    assert forward == backward
    data = json.loads(forward)
    assert (
        forward == json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )
    assert [s["name"] for s in data["suites"]] == ["a", "b"]
    assert [c["id"] for c in data["suites"][0]["cases"]] == ["x", "y"]
    keys = set(_keys(data))
    for banned in ("time", "date", "host", "user", "pid", "duration"):
        assert not any(banned in k for k in keys), (banned, keys)
    assert str(_ROOT) not in forward
