"""
title: Eval runs — replay recorded responses, or a capped live run through the model registry
layer: n/a
public_api: no
summary: replay drives every case's real doer against a backend that answers with the case's recorded response, so the prompt the code sends today is hashed and compared with the recording (a mismatch is stale, never scored) and no model is called. run_live checks the null model and the call cap before it constructs a backend, builds the one config/project.json `evals.live` names through models.get_model, counts every call and stops at the cap (a models.CountedModel subclass), marks the rest of the run not-run once the backend is absent, lets a scripts/config_loader.py ConfigError raised by the backend (such as a models.timeout_seconds entry read at the call) stop the run, since it would fail every case alike, records any other exception as that case's error, and returns a candidate case line for each answer, recording the model's reply (which replay hands back to the doer) rather than the doer's output; it never edits a dataset. An option the adapter refuses (a ValueError, such as a credential variable config/project.json `models.credential_env` does not declare) is a config refusal before any call, and the value of each variable declared there for the model is replaced by `<hidden>` in every live case detail, since a backend's exception text may echo it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from models import (
    CallCapReached,
    CountedModel,
    ModelBackend,
    ModelUnavailable,
    get_model,
)
from scripts import config_loader
from scripts.child_env import load_policy

from ._config import ConfigError, EvalConfig
from ._dataset import Case, Suite
from ._doers import DOERS, Doer, sha256_text
from ._report import Outcome, SuiteResult, verdict
from ._scorers import SCORERS

__all__ = ["LiveRun", "SpendCapExceeded", "replay", "run_live"]

# An exception message is cut to this many characters in a case detail: enough
# to name the failure, short enough that one stack of HTML cannot fill a report.
_DETAIL = 200
# What stands in a case detail where a credential's value was.
_HIDDEN = "<hidden>"

BackendFactory = Callable[..., ModelBackend]


class SpendCapExceeded(CallCapReached):
    """A live run would make, or tried to make, more model calls than
    config/project.json `evals.live.max_calls` allows."""

    def __init__(self, cases: int, cap: int, calls: int) -> None:
        super().__init__(
            cap,
            calls,
            "%d case(s) against evals.live.max_calls = %d (%d call(s) made)"
            % (cases, cap, calls),
        )
        self.cases = cases


@dataclass(frozen=True)
class LiveRun:
    """What a live run produced: per-suite results, the model calls it made,
    and a candidate case line per answered case, grouped by suite name."""

    results: list[SuiteResult]
    calls: int
    candidates: list[tuple[str, list[dict[str, object]]]] = field(default_factory=list)


class _Recording(ModelBackend):
    """Replays one case: records the prompt sent and answers with the recorded
    response; a second call is an error, since a case judges one answer."""

    name = "replay"

    def __init__(self, response: str) -> None:
        self.response = response
        self.prompts: list[str] = []

    def run(self, prompt: str, **opts: object) -> str:
        if self.prompts:
            raise RuntimeError("doer called the model twice")
        self.prompts.append(prompt)
        return self.response


class _Counting(CountedModel):
    """The live backend held to the cap (models.CountedModel), keeping the
    prompts sent, and the replies received, for the current case."""

    def __init__(self, inner: ModelBackend, cases: int, cap: int) -> None:
        super().__init__(inner, cap)
        self.cases = cases
        self.prompts: list[str] = []
        self.replies: list[str] = []

    def refusal(self) -> SpendCapExceeded:
        return SpendCapExceeded(self.cases, self.cap, self.calls)

    def run(self, prompt: str, **opts: object) -> str:
        reply = super().run(prompt, **opts)
        # Kept after the call: a call that raised is that case's error, and
        # its prompt is never read.
        self.prompts.append(prompt)
        self.replies.append(reply)
        return reply


def _error(case: Case, exc: BaseException, secrets: Sequence[str] = ()) -> Outcome:
    detail = "%s: %s" % (type(exc).__name__, _detail(exc, secrets))
    return Outcome(case.id, "error", case.scorer_name, detail, None)


def _detail(exc: BaseException, secrets: Sequence[str]) -> str:
    # Cut before truncating, so a value split by the cut cannot survive as a
    # prefix; longest first, so one value inside another leaves no remainder.
    text = str(exc)
    for secret in sorted(secrets, key=len, reverse=True):
        text = text.replace(secret, _HIDDEN)
    return text[:_DETAIL]


def _declared_secrets(model: str) -> tuple[str, ...]:
    """The values this process holds for the credential variables
    config/project.json `models.credential_env` declares for *model*, each
    read through scripts/config_loader.py `env`."""
    names = load_policy().credentials.get(model, ())
    return tuple(v for v in (config_loader.env(n) for n in names) if v)


def _scored(case: Case, response: str) -> Outcome:
    ok, detail = SCORERS[case.scorer_name].score(response, case.params)
    return Outcome(
        case.id,
        "pass" if ok else "fail",
        case.scorer_name,
        detail,
        sha256_text(response),
    )


def _suite_result(
    suite: Suite, outcomes: list[Outcome], threshold: float
) -> SuiteResult:
    names = [o.outcome for o in outcomes]
    passed = names.count("pass")
    result, reasons = verdict(passed, len(outcomes), threshold, names)
    return SuiteResult(
        suite.name,
        suite.dataset,
        len(outcomes),
        passed,
        result,
        reasons,
        sorted(outcomes, key=lambda o: o.id),
    )


def _one_prompt(prompts: Sequence[str]) -> str:
    if len(prompts) != 1:
        raise RuntimeError(
            "doer sent %d prompts; a case judges exactly one" % len(prompts)
        )
    return prompts[0]


def _replay_case(case: Case, doers: Mapping[str, Doer]) -> Outcome:
    rec = _Recording(case.response)
    try:
        response = doers[case.doer](case.text, rec)
        prompt = _one_prompt(rec.prompts)
    except Exception as exc:  # noqa: BLE001 — any doer failure is this case's error
        return _error(case, exc)
    sent = sha256_text(prompt)
    if sent != case.prompt_sha256:
        return Outcome(
            case.id,
            "stale",
            case.scorer_name,
            "prompt is now %s, recorded %s; re-record the case"
            % (sent, case.prompt_sha256),
            None,
        )
    return _scored(case, response)


def replay(
    suites: Sequence[Suite], threshold: float, *, doers: Mapping[str, Doer] = DOERS
) -> list[SuiteResult]:
    """Judge every case's recorded response through its real doer; makes no
    model call."""
    return [
        _suite_result(s, [_replay_case(c, doers) for c in s.cases], threshold)
        for s in suites
    ]


def _candidate(
    case: Case, response: str, prompt: str, model: str, version: int
) -> dict[str, object]:
    return {
        "schema_version": version,
        "id": case.id,
        "input": {"doer": case.doer, "text": case.text},
        "scorer": {"name": case.scorer_name, "params": dict(case.params)},
        "recorded": {
            "response": response,
            "sha256": sha256_text(response),
            "prompt_sha256": sha256_text(prompt),
            "source": "model",
            "model": model,
        },
    }


def _backend(cfg: EvalConfig, model: str, factory: BackendFactory) -> ModelBackend:
    try:
        return factory(model, **cfg.live_model_options)
    except KeyError as exc:
        raise ConfigError(
            "config/project.json: `evals.live.model` %r is not a registered model (%s)"
            % (model, exc)
        ) from exc
    except (TypeError, ValueError) as exc:
        # TypeError: an option the adapter does not take. ValueError: one it
        # takes and refuses, such as an undeclared credential variable.
        raise ConfigError(
            "config/project.json: `evals.live.model_options` do not fit %r (%s)"
            % (model, exc)
        ) from exc


def run_live(
    suites: Sequence[Suite],
    cfg: EvalConfig,
    *,
    backend_factory: BackendFactory = get_model,
    doers: Mapping[str, Doer] = DOERS,
    secrets: Sequence[str] | None = None,
) -> LiveRun:
    """Run every case on the model config/project.json `evals.live` names.
    Raises ConfigError for a null, unknown or misconfigured model and
    SpendCapExceeded for a run above `evals.live.max_calls`, the count check
    happening before any backend is built. *secrets* are the values cut from
    every case detail (default: what the environment holds for the model's
    declared credential variables)."""
    model = cfg.live_model
    if model is None:
        raise ConfigError(
            "config/project.json: `evals.live.model` is null; name a model to run live"
        )
    total = sum(len(s.cases) for s in suites)
    if total > cfg.live_max_calls:
        raise SpendCapExceeded(total, cfg.live_max_calls, 0)
    counting = _Counting(
        _backend(cfg, model, backend_factory), total, cfg.live_max_calls
    )
    if secrets is None:
        secrets = _declared_secrets(model)
    results: list[SuiteResult] = []
    candidates: list[tuple[str, list[dict[str, object]]]] = []
    absent = False
    for suite in suites:
        outcomes: list[Outcome] = []
        lines: list[dict[str, object]] = []
        for case in suite.cases:
            if absent:
                outcomes.append(
                    Outcome(
                        case.id,
                        "not-run",
                        case.scorer_name,
                        "backend absent earlier in the run",
                        None,
                    )
                )
                continue
            counting.prompts = []
            counting.replies = []
            try:
                response = doers[case.doer](case.text, counting)
                prompt = _one_prompt(counting.prompts)
            except (SpendCapExceeded, config_loader.ConfigError):
                # The run's fault, not this case's: a refused setting (such as
                # a models.timeout_seconds entry read at the call) would fail
                # every case the same way, so it stops the run.
                raise
            except ModelUnavailable as exc:
                absent = True
                outcomes.append(
                    Outcome(
                        case.id,
                        "absent",
                        case.scorer_name,
                        _detail(exc, secrets),
                        None,
                    )
                )
                continue
            except Exception as exc:  # noqa: BLE001 — any other failure is this case's error
                outcomes.append(_error(case, exc, secrets))
                continue
            outcomes.append(_scored(case, response))
            # The candidate records the model's reply, not the doer's output:
            # replay hands recorded.response to the doer as that reply, and a
            # doer that parses or strips it would otherwise record its own.
            (reply,) = counting.replies
            lines.append(_candidate(case, reply, prompt, model, cfg.schema_version))
        results.append(_suite_result(suite, outcomes, cfg.threshold))
        if lines:
            candidates.append((suite.name, lines))
    return LiveRun(results, counting.calls, candidates)
