"""
title: Triage brain
layer: backend
public_api: no
summary: Builds a triage prompt and (only when authorized) runs it on a model, held to the approved count of model calls (models.CountedModel) when it builds the backend itself.
"""

from __future__ import annotations

from models import CountedModel, ModelBackend, get_model

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
    max_model_calls: int | None = None,
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

    ``max_model_calls`` is the approved count, held by a
    ``models.CountedModel``, so a count of 0 raises ``models.CallCapReached``
    with no call made. An execute run on a ``model`` needs it (ValueError
    without); a caller handing in ``backend`` holds that backend to its own
    count, as the eval harness does.
    """
    if model is not None and backend is not None:
        raise ValueError("pass model or backend, not both")
    prompt = _PROMPT.format(payload=payload)
    if not execute:
        return "[dry-run] would run on a model:\n" + prompt
    if backend is None and max_model_calls is None:
        raise ValueError(
            "triage(execute=True) on a model needs max_model_calls, the approved count"
        )
    chosen = backend or get_model(model)
    if max_model_calls is not None:
        chosen = CountedModel(chosen, max_model_calls)
    return chosen.run(prompt)
