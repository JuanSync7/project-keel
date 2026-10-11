"""
title: Unit — eval replay and the capped live run
kind: tests
layer: n/a
summary: replay drives each case's real doer against a recording backend, so a case whose prompt hash matches is scored, a case whose prompt changed is stale with the new hash named, and a doer that calls the model twice is an error; run_live refuses a null model and a case count above evals.live.max_calls before the backend factory runs, turns an unknown model name or a bad option into a config refusal, stops at an absent backend and marks the rest not-run, so a later suite is absent too, records any other exception as that case's error, and raises SpendCapExceeded when a doer breaches the cap mid-run. No disk, no network: backends are small in-memory classes.
"""

import hashlib
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from evals import (  # noqa: E402
    DOERS,
    ConfigError,
    SpendCapExceeded,
    Suite,
    parse_cases,
    parse_config,
    prompt_sha256,
    replay,
    run_live,
)
from models import ModelBackend, ModelUnavailable  # noqa: E402

pytestmark = pytest.mark.unit

SOURCE = "evals/datasets/unit.jsonl"


def _sha(text):
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _line(case_id, text, response, prompt_hash=None, expected="ACK"):
    return json.dumps(
        {
            "schema_version": 1,
            "id": case_id,
            "input": {"doer": "prompt", "text": text},
            "scorer": {"name": "exact", "params": {"expected": expected}},
            "recorded": {
                "response": response,
                "sha256": _sha(response),
                "prompt_sha256": prompt_hash or prompt_sha256("prompt", text),
                "source": "authored",
                "model": None,
            },
        },
        sort_keys=True,
    )


def _suite(*lines):
    cases = parse_cases("\n".join(lines) + "\n", source=SOURCE, schema_version=1)
    return Suite("unit", SOURCE, cases)


def _config(model="fake", max_calls=10, options=None):
    manifest = {
        "evals": {
            "case_schema": "config/evals/eval-case.schema.json",
            "report_schema": "config/evals/eval-report.schema.json",
            "dataset_dir": "evals/datasets",
            "report_dir": ".evidence/evals",
            "threshold": 1.0,
            "live": {
                "model": model,
                "max_calls": max_calls,
                "model_options": options or {},
            },
        }
    }
    schema = {"properties": {"schema_version": {"const": 1}}}
    return parse_config(manifest, lambda _rel: schema)


def test_prompt_hash_runs_the_real_doer():
    assert prompt_sha256("prompt", "Reply ACK.") == _sha("Reply ACK.")
    triage_hash = prompt_sha256("triage", "disk full")
    assert triage_hash != _sha("disk full")
    assert triage_hash == prompt_sha256("triage", "disk full")


def test_replay_drives_the_real_doer_and_flags_a_stale_prompt():
    good = _line("good", "Reply ACK.", "ACK\n")
    stale = _line("stale", "Reply ACK now.", "ACK", prompt_hash=_sha("Reply ACK."))
    low = _line("low", "Reply ACK.", "NAK")
    (result,) = replay([_suite(good, stale, low)], 1.0)
    by_id = {o.id: o for o in result.cases}
    assert by_id["good"].outcome == "pass", by_id["good"]
    assert by_id["low"].outcome == "fail", by_id["low"]
    assert by_id["stale"].outcome == "stale", by_id["stale"]
    assert _sha("Reply ACK now.") in by_id["stale"].detail
    assert result.result == "fail"
    assert result.reasons == ["below-threshold", "stale-recording"]
    assert (result.passed, result.total) == (1, 3)

    twice = dict(DOERS, prompt=lambda text, b: b.run(text) + b.run(text))
    (result,) = replay([_suite(good)], 1.0, doers=twice)
    assert result.cases[0].outcome == "error", result.cases[0]
    assert "twice" in result.cases[0].detail

    never = dict(DOERS, prompt=lambda text, b: "ACK")
    (result,) = replay([_suite(good)], 1.0, doers=never)
    assert result.cases[0].outcome == "error", result.cases[0]


class _Factory:
    """Records each backend construction and hands out *backend*."""

    def __init__(self, backend=None, exc=None):
        self.backend = backend
        self.exc = exc
        self.calls = []

    def __call__(self, name, **options):
        self.calls.append((name, options))
        if self.exc is not None:
            raise self.exc
        return self.backend


class _Scripted(ModelBackend):
    """Answers prompts from a script; an exception in the script is raised."""

    name = "scripted"

    def __init__(self, script):
        self.script = list(script)
        self.prompts = []

    def run(self, prompt, **opts):
        self.prompts.append(prompt)
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def _three():
    return [
        _suite(
            _line("a", "Reply ACK a.", "ACK"),
            _line("b", "Reply ACK b.", "ACK"),
            _line("c", "Reply ACK c.", "ACK"),
        )
    ]


def test_live_refuses_over_cap_before_constructing_a_backend():
    factory = _Factory(_Scripted(["ACK"] * 3))
    with pytest.raises(SpendCapExceeded) as info:
        run_live(_three(), _config(max_calls=2), backend_factory=factory)
    assert factory.calls == []
    assert (info.value.cases, info.value.cap, info.value.calls) == (3, 2, 0)

    with pytest.raises(ConfigError) as info:
        run_live(_three(), _config(model=None), backend_factory=factory)
    assert "evals.live.model" in str(info.value)
    assert factory.calls == []

    with pytest.raises(ConfigError) as info:
        run_live(_three(), _config(), backend_factory=_Factory(exc=KeyError("x")))
    assert "evals.live.model" in str(info.value)
    assert "model_options" not in str(info.value)

    with pytest.raises(ConfigError) as info:
        run_live(_three(), _config(), backend_factory=_Factory(exc=TypeError("x")))
    assert "evals.live.model_options" in str(info.value)

    factory = _Factory(_Scripted(["ACK"] * 3))
    run = run_live(
        _three(), _config(max_calls=3, options={"k": 1}), backend_factory=factory
    )
    assert factory.calls == [("fake", {"k": 1})]
    assert run.calls == 3
    assert [o.outcome for o in run.results[0].cases] == ["pass", "pass", "pass"]


def test_live_absent_stops_and_marks_the_rest_not_run():
    backend = _Scripted([ModelUnavailable("gone"), "ACK", "ACK"])
    run = run_live(_three(), _config(), backend_factory=_Factory(backend))
    assert [o.outcome for o in run.results[0].cases] == ["absent", "not-run", "not-run"]
    assert run.calls == 1
    assert run.candidates == [] or all(not lines for _s, lines in run.candidates)
    assert run.results[0].result == "absent"

    # The absence carries into every later suite: a suite none of whose cases
    # ran is absent too, never a pass over zero judged cases.
    first, *rest = _three()[0].cases
    suites = [Suite("a-suite", SOURCE, [first]), Suite("b-suite", SOURCE, rest)]
    backend = _Scripted([ModelUnavailable("gone"), "ACK", "ACK"])
    run = run_live(suites, _config(), backend_factory=_Factory(backend))
    assert [(r.name, r.passed, r.total, r.result, r.reasons) for r in run.results] == [
        ("a-suite", 0, 1, "absent", ["backend-absent"]),
        ("b-suite", 0, 2, "absent", ["backend-absent"]),
    ]
    assert [o.outcome for o in run.results[1].cases] == ["not-run", "not-run"]
    assert run.calls == 1

    backend = _Scripted(["ACK", RuntimeError("boom"), "NAK"])
    run = run_live(_three(), _config(), backend_factory=_Factory(backend))
    outcomes = {o.id: o for o in run.results[0].cases}
    assert [outcomes[i].outcome for i in "abc"] == ["pass", "error", "fail"]
    assert "RuntimeError" in outcomes["b"].detail
    ((suite, lines),) = run.candidates
    assert suite == "unit"
    assert [c["id"] for c in lines] == ["a", "c"]
    rec = lines[1]["recorded"]
    assert rec == {
        "response": "NAK",
        "sha256": _sha("NAK"),
        "prompt_sha256": _sha("Reply ACK c."),
        "source": "model",
        "model": "fake",
    }
    assert lines[1]["input"] == {"doer": "prompt", "text": "Reply ACK c."}
    assert lines[1]["schema_version"] == 1

    twice = dict(DOERS, prompt=lambda text, b: b.run(text) + b.run(text))
    backend = _Scripted(["A", "CK"] * 3)
    with pytest.raises(SpendCapExceeded) as info:
        run_live(
            _three(),
            _config(max_calls=3),
            backend_factory=_Factory(backend),
            doers=twice,
        )
    assert info.value.calls == 3
    assert len(backend.prompts) == 3
