"""
title: Model registry
layer: backend
public_api: yes
summary: name -> backend, plus the default. Add a provider here.
"""
from __future__ import annotations

from .claude_code_headless import ClaudeCodeHeadless
from .contracts import ModelBackend
from .fake import FakeModel
from .openai_compatible import OpenAICompatible

__all__ = ["get_model", "list_models", "DEFAULT_MODEL"]

DEFAULT_MODEL = "claude-code-headless"

# name -> factory. To add a provider, write an adapter implementing
# ModelBackend and register it here; callers select it by name via get_model,
# never by importing a concrete class.
_REGISTRY = {
    "claude-code-headless": ClaudeCodeHeadless,   # shells out to the Claude Code CLI
    "openai-compatible": OpenAICompatible,        # any OpenAI-style HTTP endpoint
    "fake": FakeModel,                            # deterministic, offline (tests/dev)
}


def list_models() -> list[str]:
    """Return the registered model names, sorted."""
    return sorted(_REGISTRY)


def get_model(name: str | None = None, **kwargs) -> ModelBackend:
    """Return a model backend by name (defaults to DEFAULT_MODEL)."""
    key = name or DEFAULT_MODEL
    if key not in _REGISTRY:
        raise KeyError(f"unknown model {key!r}; have {list_models()}")
    return _REGISTRY[key](**kwargs)
