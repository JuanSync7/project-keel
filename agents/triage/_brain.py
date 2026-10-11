"""
title: Triage brain
layer: backend
public_api: no
summary: Builds a triage prompt and (only when authorized) runs it on a model.
"""

from __future__ import annotations

from models import ModelBackend, get_model

__all__ = ["triage"]

_PROMPT = """\
You are a triage assistant. Given the event payload below, produce a 3-line
summary: (1) what happened, (2) likely cause, (3) suggested next action.

--- payload ---
{payload}
"""


def triage(
    payload: str,
    *,
    execute: bool = False,
    model: str | None = None,
    backend: ModelBackend | None = None,
) -> str:
    """Triage an event payload into a short summary.

    The agent holds only reasoning/policy: it builds the prompt and asks
    ``models/`` for a backend by name — it never hardcodes a provider. Per
    the repo rules a model-calling action defaults to a dry run: with
    ``execute=False`` (the default) we return the rendered prompt and never
    call a model. Pass ``execute=True`` to actually run.

    ``backend`` hands in an already-built backend instead of a name, so the
    eval harness can drive this real prompt through a recording backend
    (replay) or a counted, capped one (live). Pass ``model`` or ``backend``,
    not both: ValueError.
    """
    if model is not None and backend is not None:
        raise ValueError("pass model or backend, not both")
    prompt = _PROMPT.format(payload=payload)
    if not execute:
        return "[dry-run] would run on a model:\n" + prompt
    return (backend or get_model(model)).run(prompt)
