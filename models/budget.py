"""
title: Model-call budget — a backend that counts its calls and refuses past the approved count
layer: backend
public_api: yes
summary: CountedModel wraps any ModelBackend and passes each call through until the approved count is reached, then raises CallCapReached without calling the backend, so a count of 0 lets no call through; ModelMeter is one run's counted backend, built from a name on the first call only, so a run that never reaches a model step builds none. approve_resume raises RunNotApproved, carrying report()'s three parts, for a saved run that would resume on another model than the one approved or with more calls left than approved. approved_cap reads config/project.json `agents.max_model_calls` through scripts/config_loader.py and raises its ConfigError for a value it cannot use. Shared by the agents, the eval harness and the MCP server, which sit above models in config/project.json `import_layers.order`.
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
    "approve_resume",
    "approved_cap",
]

CAP_KEY = ("agents", "max_model_calls")


class CallCapReached(Exception):
    """A call past the approved count: *calls* were made of the *cap* approved."""

    def __init__(self, cap: int, calls: int, message: str | None = None) -> None:
        super().__init__(
            message
            or "the run reached its approved %d model call(s) (%d made)" % (cap, calls)
        )
        self.cap = cap
        self.calls = calls


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
