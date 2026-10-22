"""
title: Doc reviewer model step
layer: backend
public_api: no
summary: propose(rules, chunk, backend=b) is the doc reviewer's one model call, ONE bounded edit spec for a chunk or None, built from the prompt builder and reply parser the plan's propose step in _brain.py uses; the eval harness (evals/_doers.py) drives it on a recording backend.
"""

from __future__ import annotations

from models import ModelBackend

from ._brain import _parse_spec, _propose_prompt

__all__ = ["propose"]


def propose(rules: list[dict], chunk: dict, *, backend: ModelBackend) -> dict | None:
    """ONE bounded edit spec for *chunk* (a review_docs finding and the text it
    is about) under the guide's *rules* (corpus nodes), from *backend*; None
    when the model declines, the reply does not parse, or it names its own
    gate."""
    spec: dict | None = _parse_spec(backend.run(_propose_prompt(rules, chunk)))
    return spec
