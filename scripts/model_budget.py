"""
title: model_budget — the approved model-call cap an agent run is held to
kind: script
layer: n/a
summary: Shared by the agents' thin CLIs (scripts/doc_review.py, scripts/refactor_practice.py and the two hooks under scripts/hooks/). cap(root) reads config/project.json `agents.max_model_calls` through scripts/config_loader.py, so an absent key is the default 0, which approves no call, and a wrong value is a ConfigError. approve(needed, cap, flag) returns None for a run whose upper bound of model calls is within the cap and raises SpendRefused, carrying the three report() parts, for a bound over the cap or a run with no bound (None or negative); the unit is the model call, since the cost of one call depends on the model and is not known before the run. announce(prog, model) is the line naming the registry default and why, when no model was named, from models.choose_model. It ends no process: the entry point returns report(...) for a refusal.
effect: read-only
"""

from __future__ import annotations

import config_loader
from models import choose_model

__all__ = ["CAP_KEY", "SpendRefused", "announce", "approve", "cap"]

CAP_KEY = ("agents", "max_model_calls")
_DOTTED = ".".join(CAP_KEY)


class SpendRefused(Exception):
    """A run the cap does not approve, as report()'s three parts."""

    def __init__(self, what: str, on: str, next_step: str) -> None:
        super().__init__("%s: %s; %s" % (what, on, next_step))
        self.what = what
        self.on = on
        self.next_step = next_step

    @property
    def parts(self) -> tuple[str, str, str]:
        return (self.what, self.on, self.next_step)


def cap(root: str) -> int:
    """The model calls config/project.json at *root* approves for one run.
    Raises config_loader.ConfigError when the file or the value cannot be
    used."""
    values = config_loader.resolve(
        config_loader.read(root),
        config_loader.rows(CAP_KEY),
        config_loader.CONFIG_FILE,
    )
    approved: int = values[CAP_KEY]
    return approved


def approve(needed: int | None, cap: int, flag: str | None) -> None:
    """Pass a run that makes at most *needed* model calls under *cap*. Raises
    SpendRefused when *needed* is over *cap*, or is None or negative, which is
    a run with no upper bound; *flag* names the option that sets the bound,
    or is None for a run whose bound is fixed."""
    if needed is None or needed < 0:
        raise SpendRefused(
            "the run's model calls cannot be estimated, so it is refused",
            "%s %s sets no upper bound"
            % (flag or "the run", "unset" if needed is None else needed),
            "give %s a whole number of 0 or more" % (flag or "the run's bound"),
        )
    if needed > cap:
        raise SpendRefused(
            "the run may make %d model call(s), over the approved cap" % needed,
            "config/project.json %s = %d" % (_DOTTED, cap),
            "raise %s to %d or more%s"
            % (_DOTTED, needed, "" if flag is None else ", or lower " + flag),
        )


def announce(prog: str, model: str | None) -> str | None:
    """The line telling the user which model runs and why, when *model* names
    none; None when the user named one, since they already know."""
    choice = choose_model(model)
    if not choice.defaulted:
        return None
    return (
        "%s: no --model given; using %r, the registry default "
        "(models/registry.py DEFAULT_MODEL)" % (prog, choice.name)
    )
