"""
title: Model-call budget — a backend that counts its calls and refuses past the approved count
layer: backend
public_api: yes
summary: CountedModel wraps any ModelBackend and passes each call through until the approved count is reached, then raises CallCapReached without calling the backend, so a count of 0 lets no call through; ModelMeter is one run's counted backend, built from a name on the first call only, so a run that never reaches a model step builds none. approve_resume raises RunNotApproved, carrying report()'s three parts, for a saved run that would resume on another model than the one approved or with more calls left than approved. approved_cap reads config/project.json `agents.max_model_calls` through scripts/config_loader.py and raises its ConfigError for a value it cannot use. SessionBudget is the total a long-lived caller (the MCP Q&A server) is held to across all its runs: admit raises SessionCapReached, a CallCapReached, for a run whose bound added to the calls made so far would pass the total, before any model is called, and the backends its counted() factory builds add every call they pass on to that count; approved_session_cap reads that total from `agents.max_session_model_calls`, absent being the declared default 0, which admits no run that may make a call; check_session_total raises config_loader.WrongValue, naming both keys and values, for a per-run cap over a nonzero total, a pair under which no run could ever be admitted. Shared by the agents, the eval harness and the MCP server, which sit above models in config/project.json `import_layers.order`.
"""

from __future__ import annotations

from collections.abc import Callable

from scripts import config_loader

from .contracts import ModelBackend
from .registry import choose_model

__all__ = [
    "CAP_KEY",
    "CallCapReached",
    "CountedModel",
    "ModelMeter",
    "RunNotApproved",
    "SESSION_CAP_KEY",
    "SessionBudget",
    "SessionCapReached",
    "approve_resume",
    "approved_cap",
    "approved_session_cap",
    "check_session_total",
]

CAP_KEY = ("agents", "max_model_calls")
SESSION_CAP_KEY = ("agents", "max_session_model_calls")


class CallCapReached(Exception):
    """A call past the approved count: *calls* were made of the *cap* approved."""

    def __init__(self, cap: int, calls: int, message: str | None = None) -> None:
        super().__init__(
            message
            or "the run reached its approved %d model call(s) (%d made)" % (cap, calls)
        )
        self.cap = cap
        self.calls = calls


class SessionCapReached(CallCapReached):
    """A run refused before it starts: *calls* were made of the *total*
    approved, and the run's *bound* would take the count past it."""

    def __init__(
        self, total: int, calls: int, bound: int, message: str | None = None
    ) -> None:
        super().__init__(
            total,
            calls,
            message
            or "the session has made %d of its approved %d model call(s), and "
            "the next run may make %d more, which would pass %d"
            % (calls, total, bound, total),
        )
        self.total = total
        self.bound = bound


class RunNotApproved(Exception):
    """A saved run the approval does not cover, as report()'s three parts."""

    def __init__(self, what: str, on: str, next_step: str) -> None:
        super().__init__("%s: %s; %s" % (what, on, next_step))
        self.parts = (what, on, next_step)


class CountedModel(ModelBackend):
    """The backend *inner*, held to *cap* calls: the call after the last
    approved one raises CallCapReached and never reaches *inner*."""

    def __init__(self, inner: ModelBackend, cap: int) -> None:
        if cap < 0:
            raise ValueError("a model-call cap is 0 or more, not %d" % cap)
        self.inner = inner
        self.name = inner.name
        self.cap = cap
        self.calls = 0

    def refusal(self) -> CallCapReached:
        """The exception the first call past the cap raises; a subclass that
        reports the cap in its own terms overrides this."""
        return CallCapReached(self.cap, self.calls)

    def run(self, prompt: str, **opts: object) -> str:
        if self.calls >= self.cap:
            raise self.refusal()
        # Counted before the call: a call that raises still spent what it sent.
        self.calls += 1
        return self.inner.run(prompt, **opts)


class ModelMeter:
    """One run's model calls: the backend *factory* builds for *name*, wrapped
    in a CountedModel of *cap*, built on the first backend() and kept."""

    def __init__(
        self,
        name: str | None,
        cap: int,
        factory: Callable[[str | None], ModelBackend],
    ) -> None:
        self.name = name
        self.cap = cap
        self._factory = factory
        self._counted: CountedModel | None = None

    def backend(self) -> CountedModel:
        """The run's counted backend, built from the name the first time."""
        if self._counted is None:
            self._counted = CountedModel(self._factory(self.name), self.cap)
        return self._counted

    @property
    def calls(self) -> int:
        """The model calls the run has made, 0 before the backend is built."""
        return 0 if self._counted is None else self._counted.calls


def _not_negative(what: str, value: int) -> int:
    if value < 0:
        raise ValueError("a %s is 0 or more, not %d" % (what, value))
    return value


class _SessionCounted(ModelBackend):
    """The backend *inner*, each call it passes on added to *session*."""

    def __init__(self, inner: ModelBackend, session: SessionBudget) -> None:
        self.inner = inner
        self.name = inner.name
        self.session = session

    def run(self, prompt: str, **opts: object) -> str:
        # Counted before the call: a call that raises still spent what it sent.
        self.session.calls += 1
        return self.inner.run(prompt, **opts)


class SessionBudget:
    """The model calls one long-lived caller may make over its lifetime,
    across every run it starts: *total* approved, *calls* made so far."""

    def __init__(self, total: int) -> None:
        self.total = _not_negative("session model-call total", total)
        self.calls = 0

    def admit(self, bound: int) -> None:
        """Pass a run that may make up to *bound* calls when the calls made so
        far plus *bound* stay within the total, or raise SessionCapReached.
        The whole bound must fit, so no run the session admits can take the
        count past the total, however many of its calls it makes."""
        _not_negative("model-call bound", bound)
        if self.calls + bound > self.total:
            raise SessionCapReached(self.total, self.calls, bound)

    def counted(
        self, factory: Callable[[str | None], ModelBackend]
    ) -> Callable[[str | None], ModelBackend]:
        """A factory like *factory* whose backends add each call they pass on
        to this session's count."""

        def build(name: str | None) -> ModelBackend:
            return _SessionCounted(factory(name), self)

        return build


def approve_resume(
    *, where: str, saved_model: str | None, model: str | None, left: int, cap: int
) -> None:
    """Pass a saved run, at *where*, that resumes on *model* with at most *cap*
    model calls *left*. Raises RunNotApproved when its *saved_model* resolves
    to another model than *model* does, or when *left* is over *cap*: a resume
    takes its state from the snapshot, so without this check it would run on
    the saved model and to the saved bound, not the approved ones."""
    saved, approved = choose_model(saved_model).name, choose_model(model).name
    if saved != approved:
        raise RunNotApproved(
            "the saved run resumes on model %r, not the %r this run approves"
            % (saved, approved),
            where,
            "run again with --model %r, or remove %s to start afresh" % (saved, where),
        )
    if left > cap:
        raise RunNotApproved(
            "the saved run has %d model call(s) left, over the %d this run approves"
            % (left, cap),
            where,
            "approve %d or more, or remove %s to start afresh" % (left, where),
        )


def approved_cap(root: str) -> int:
    """The model calls config/project.json at *root* approves for one run.
    Raises config_loader.ConfigError when the file or the value cannot be used."""
    values = config_loader.resolve(
        config_loader.read(root),
        config_loader.rows(CAP_KEY),
        config_loader.CONFIG_FILE,
    )
    approved: int = values[CAP_KEY]
    return approved


def approved_session_cap(root: str) -> int:
    """The model calls config/project.json at *root* approves for one
    long-lived caller over its lifetime. Raises config_loader.ConfigError when
    the file or the value cannot be used."""
    values = config_loader.resolve(
        config_loader.read(root),
        config_loader.rows(SESSION_CAP_KEY),
        config_loader.CONFIG_FILE,
    )
    total: int = values[SESSION_CAP_KEY]
    return total


def check_session_total(per_run: int, total: int) -> None:
    """Pass a per-run cap (`agents.max_model_calls`) that fits within the
    session *total* (`agents.max_session_model_calls`), or a total of 0, which
    approves no run. Raises config_loader.WrongValue naming both keys and
    values otherwise: no run could ever be admitted, so a caller that started
    anyway would refuse every run with none made."""
    if total > 0 and per_run > total:
        raise config_loader.WrongValue(
            config_loader.CONFIG_FILE,
            [
                "%s: %s is %d, over %s is %d, so no question could be admitted; "
                "accepted: %s at most %s, or %s 0 to approve none"
                % (
                    config_loader.CONFIG_FILE,
                    ".".join(CAP_KEY),
                    per_run,
                    ".".join(SESSION_CAP_KEY),
                    total,
                    ".".join(CAP_KEY),
                    ".".join(SESSION_CAP_KEY),
                    ".".join(SESSION_CAP_KEY),
                )
            ],
        )
