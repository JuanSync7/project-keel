"""
title: Eval verdicts and reports — the closed vocabularies, the threshold rule and canonical JSON
layer: n/a
public_api: no
summary: verdict turns one suite's outcomes into a result and its reasons, comparing the exact rational score with the threshold so a score equal to it passes; an errored or stale case fails a suite whatever its score, an absent backend is its own result unless the cases that ran already prove a fail, and so is a suite with a case not run because the backend went absent earlier, and zero cases is refused. aggregate folds suite results into the run's result, and render writes a Report as canonical JSON (sorted keys, suites by name, cases by id, two-space indent, one trailing newline) with no clock, host or absolute path, so two runs over the same tree write the same bytes. OUTCOMES, REASONS and RESULTS are the closed vocabularies config/evals/eval-report.schema.json is held equal to.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field, replace
from fractions import Fraction

__all__ = [
    "OUTCOMES",
    "REASONS",
    "RESULTS",
    "Outcome",
    "Report",
    "SuiteResult",
    "aggregate",
    "render",
    "verdict",
]

OUTCOMES = ("pass", "fail", "stale", "error", "absent", "not-run")
REASONS = (
    "below-threshold",
    "case-error",
    "stale-recording",
    "backend-absent",
    "cap-exceeded",
    "refused",
    "incomplete",
)
RESULTS = ("pass", "fail", "absent", "refused", "incomplete")

# Outcome -> the reason it adds to its suite; pass and fail add none (fail
# reaches the verdict through the score). not-run is a case skipped because the
# backend went absent earlier in the run, so it adds backend-absent: a later
# suite whose every case is not-run is absent, not a pass over zero judged cases.
_OUTCOME_REASON = {
    "error": "case-error",
    "stale": "stale-recording",
    "absent": "backend-absent",
    "not-run": "backend-absent",
}
_UNJUDGED = ("absent", "not-run")


@dataclass(frozen=True)
class Outcome:
    """How one case went: its id, outcome, scorer, a one-line detail, and the
    hash of the response judged (None when no response was judged)."""

    id: str
    outcome: str
    scorer: str
    detail: str
    response_sha256: str | None


@dataclass(frozen=True)
class SuiteResult:
    """One suite's verdict: counts, result, sorted reasons and its outcomes."""

    name: str
    dataset: str
    total: int
    passed: int
    result: str
    reasons: list[str]
    cases: list[Outcome] = field(default_factory=list)


@dataclass(frozen=True)
class Report:
    """One run of the harness, as written to `<evals.report_dir>/<mode>.json`."""

    schema: str
    schema_version: int
    mode: str
    model: str | None
    threshold: float
    calls: int
    result: str
    reasons: list[str]
    detail: str | None
    suites: list[SuiteResult] = field(default_factory=list)


def _below(score: Fraction, threshold: float) -> bool:
    # Fraction(repr(t)), not Fraction(t) or a float product: Fraction(0.07) is the
    # binary float 0.07000000000000000666..., and 0.07 * 100 == 7.000000000000001,
    # so either would fail 7 of 100 against a threshold of 0.07 that it meets.
    return score < Fraction(repr(threshold))


def verdict(
    passed: int, total: int, threshold: float, outcomes: Sequence[str]
) -> tuple[str, list[str]]:
    """(result, sorted reasons) for a suite of *total* cases, *passed* of them
    passing, whose per-case outcomes are *outcomes*."""
    if total == 0:
        # load_suites refuses an empty suite first; this keeps the rule local.
        return "refused", ["refused"]
    reasons = {_OUTCOME_REASON[o] for o in outcomes if o in _OUTCOME_REASON}
    unjudged = sum(1 for o in outcomes if o in _UNJUDGED)
    # A case the backend never answered might have passed: count it as passing
    # when deciding whether the suite is already below threshold, so an absent
    # backend fails a suite only when the cases that ran prove it.
    if _below(Fraction(passed + unjudged, total), threshold):
        reasons.add("below-threshold")
    if not reasons:
        return "pass", []
    if reasons == {"backend-absent"}:
        return "absent", ["backend-absent"]
    return "fail", sorted(reasons)


def aggregate(results: Iterable[SuiteResult]) -> tuple[str, list[str]]:
    """(result, sorted reasons) of a run over suites with *results*: refused
    with none, else the worst result any suite has, ranked refused, incomplete,
    fail, absent, pass; the reasons are every suite's, merged."""
    results = list(results)
    if not results:
        return "refused", ["refused"]
    seen = {r.result for r in results}
    reasons = sorted({reason for r in results for reason in r.reasons})
    for result in ("refused", "incomplete", "fail", "absent"):
        if result in seen:
            return result, reasons
    return "pass", reasons


def render(report: Report) -> str:
    """*report* as canonical JSON text: sorted keys, suites sorted by name and
    cases by id, two-space indent, one trailing newline."""
    suites = sorted(
        (replace(s, cases=sorted(s.cases, key=lambda o: o.id)) for s in report.suites),
        key=lambda s: s.name,
    )
    data = asdict(replace(report, suites=suites))
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
