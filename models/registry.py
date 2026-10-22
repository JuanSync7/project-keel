"""
title: Model registry
layer: backend
public_api: yes
summary: name -> backend, plus the default. choose_model is the one rule a name resolves by (absent or empty is DEFAULT_MODEL, and the choice says it defaulted, so a caller can tell its user which model runs and why); get_model builds the chosen backend. Add a provider here.
"""

from __future__ import annotations

from typing import NamedTuple

from .claude_code_headless import ClaudeCodeHeadless
from .contracts import ModelBackend
from .fake import FakeModel
from .openai_compatible import OpenAICompatible

__all__ = ["get_model", "list_models", "choose_model", "ModelChoice", "DEFAULT_MODEL"]

DEFAULT_MODEL = "claude-code-headless"

# name -> factory. To add a provider, write an adapter implementing
# ModelBackend and register it here; callers select it by name via get_model,
# never by importing a concrete class.
_REGISTRY = {
    "claude-code-headless": ClaudeCodeHeadless,  # shells out to the Claude Code CLI
    "openai-compatible": OpenAICompatible,  # any OpenAI-style HTTP endpoint
    "fake": FakeModel,  # deterministic, offline (tests/dev)
}


def list_models() -> list[str]:
    """Return the registered model names, sorted."""
    return sorted(_REGISTRY)


class ModelChoice(NamedTuple):
    """The model name a run resolves to, and whether no name was given so the
    registry default was taken."""

    name: str
    defaulted: bool


def choose_model(name: str | None = None) -> ModelChoice:
    """The model *name* resolves to: an absent or empty name is DEFAULT_MODEL
    and defaulted, any other name is itself. It does not check the name is
    registered; get_model does."""
    if name:
        return ModelChoice(name, False)
    return ModelChoice(DEFAULT_MODEL, True)


def get_model(name: str | None = None, **kwargs) -> ModelBackend:
    """Return a model backend by name (defaults to DEFAULT_MODEL)."""
    key = choose_model(name).name
    if key not in _REGISTRY:
        raise KeyError(f"unknown model {key!r}; have {list_models()}")
    return _REGISTRY[key](**kwargs)
