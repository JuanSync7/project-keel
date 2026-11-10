"""
title: Unit — scorer refusals stay within their eval case
kind: tests
layer: n/a
summary: ScoringRefused becomes a case error while a plain scorer ValueError stops replay and run_live; a live regex child failure preserves every paid reply's candidate and lets later cases score.
"""

import json
import subprocess
from collections.abc import Mapping

import pytest
from evals import (
    SCORERS,
    Case,
    EvalConfig,
    Scorer,
    ScoringRefused,
    Suite,
    prompt_sha256,
    replay,
    run_live,
    sha256_text,
)
from models import ModelBackend

pytestmark = pytest.mark.unit


def _suite() -> Suite:
    cases = []
    for case_id in ("before", "refused", "after"):
        regex = case_id == "refused"
        cases.append(
            Case(
                id=case_id,
                suite="unit",
                source="evals/datasets/unit.jsonl:1",
                doer="prompt",
                text="Reply ACK.",
                scorer_name="regex" if regex else "exact",
                params={"pattern": "(a+)+$"} if regex else {"expected": "ACK"},
                response="a" * 25 + "b" if regex else "ACK",
                response_sha256=sha256_text("a" * 25 + "b" if regex else "ACK"),
                prompt_sha256=prompt_sha256("prompt", "Reply ACK."),
                rec_source="authored",
                rec_model=None,
            )
        )
    return Suite("unit", "evals/datasets/unit.jsonl", cases)


def test_replay_propagates_scorer_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    error = ValueError("scorer bug")
    scored: list[str] = []

    def broken_score(
        self: Scorer, response: str, params: Mapping[str, object]
    ) -> tuple[bool, str]:
        scored.append(response)
        raise error

    monkeypatch.setattr(Scorer, "score", broken_score)
    with pytest.raises(ValueError, match="scorer bug") as raised:
        replay([_suite()], 0.5)
    assert raised.value is error
    assert scored == ["ACK"]


def test_live_propagates_scorer_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    error = ValueError("scorer bug")

    def broken_score(
        self: Scorer, response: str, params: Mapping[str, object]
    ) -> tuple[bool, str]:
        raise error

    class Backend(ModelBackend):
        name = "fake"

        def __init__(self) -> None:
            self.calls = 0

        def run(self, prompt: str, **opts: object) -> str:
            self.calls += 1
            return "ACK"

    monkeypatch.setattr(Scorer, "score", broken_score)
    backend = Backend()
    cfg = EvalConfig(
        case_schema="config/evals/eval-case.schema.json",
        report_schema="config/evals/eval-report.schema.json",
        dataset_dir="evals/datasets",
        report_dir=".evidence/evals",
        threshold=0.5,
        live_model="fake",
        live_max_calls=3,
    )
    with pytest.raises(ValueError, match="scorer bug") as raised:
        run_live([_suite()], cfg, backend_factory=lambda *a, **kw: backend, secrets=())
    assert raised.value is error
    assert backend.calls == 1


def test_replay_records_regex_timeout_and_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def timeout(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired("regex-child", 0.01)

    monkeypatch.setattr(subprocess, "run", timeout)
    (result,) = replay([_suite()], 0.5)
    outcomes = {o.id: o for o in result.cases}
    assert [outcomes[i].outcome for i in ("before", "refused", "after")] == [
        "pass",
        "error",
        "pass",
    ]
    assert (
        "ScoringRefused: regex.pattern: regex child timeout"
        in outcomes["refused"].detail
    )
    assert outcomes["refused"].response_sha256 is None
    assert (result.passed, result.total, result.result, result.reasons) == (
        2,
        3,
        "fail",
        ["case-error"],
    )
    with pytest.raises(ScoringRefused, match="regex.pattern: regex child timeout"):
        SCORERS["regex"].score("response", {"pattern": "pattern"})


def test_live_records_regex_child_failure_and_keeps_every_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replies = ["ACK\n", "a" * 28 + "b\n", "ACK"]
    seen: list[object] = []

    def broken_child(
        *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        seen.append(json.loads(str(kwargs["input"])))
        return subprocess.CompletedProcess(["regex-child"], 1, "", "private")

    class Backend(ModelBackend):
        name = "fake"

        def __init__(self) -> None:
            self.calls = 0

        def run(self, prompt: str, **opts: object) -> str:
            reply = replies[self.calls]
            self.calls += 1
            return reply

    monkeypatch.setattr(subprocess, "run", broken_child)
    backend = Backend()
    suite = _suite()
    cfg = EvalConfig(
        case_schema="config/evals/eval-case.schema.json",
        report_schema="config/evals/eval-report.schema.json",
        dataset_dir="evals/datasets",
        report_dir=".evidence/evals",
        threshold=0.5,
        live_model="fake",
        live_max_calls=3,
    )
    run = run_live([suite], cfg, backend_factory=lambda *a, **kw: backend, secrets=())
    (result,) = run.results
    outcomes = {o.id: o for o in result.cases}
    assert [outcomes[i].outcome for i in ("before", "refused", "after")] == [
        "pass",
        "error",
        "pass",
    ]
    assert (
        "ScoringRefused: regex.pattern: regex child exited nonzero"
        in outcomes["refused"].detail
    )
    assert outcomes["refused"].response_sha256 is None
    assert (result.passed, result.total, result.result, result.reasons) == (
        2,
        3,
        "fail",
        ["case-error"],
    )
    assert run.calls == backend.calls == 3
    assert seen == [["(a+)+$", [replies[1]], "search"]]
    assert run.candidates == [
        (
            "unit",
            [
                {
                    "schema_version": 1,
                    "id": case.id,
                    "input": {"doer": case.doer, "text": case.text},
                    "scorer": {"name": case.scorer_name, "params": dict(case.params)},
                    "recorded": {
                        "response": reply,
                        "sha256": sha256_text(reply),
                        "prompt_sha256": prompt_sha256(case.doer, case.text),
                        "source": "model",
                        "model": "fake",
                    },
                }
                for case, reply in zip(suite.cases, replies, strict=True)
            ],
        )
    ]
    with pytest.raises(
        ScoringRefused, match="regex.pattern: regex child exited nonzero"
    ):
        SCORERS["regex"].score("response", {"pattern": "pattern"})
