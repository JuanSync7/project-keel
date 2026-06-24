"""
title: Model registry
layer: backend
public_api: yes
summary: name -> backend, plus the default. Add a provider here.
"""
from __future__ import annotations

from .claude_code_headless import ClaudeCodeHeadless
from .contracts import ModelBackend

__all__ = ["get_model", "list_models", "DEFAULT_MODEL"]

DEFAULT_MODEL = "claude-code-headless"

# name -> factory. To add a provider (Anthropic API client, local model),
# write an adapter implementing ModelBackend and register it here.
_REGISTRY = {
    "claude-code-headless": ClaudeCodeHeadless,
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
