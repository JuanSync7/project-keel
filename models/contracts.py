"""
title: Model backend contract
layer: backend
public_api: yes
summary: The ABC every model adapter implements, and ModelUnavailable — the owned error for a backend that cannot run here (absent), distinct from one that failed (broken).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

__all__ = ["ModelBackend", "ModelUnavailable"]


class ModelUnavailable(RuntimeError):
    """The backend cannot run HERE: its binary is not on PATH, its endpoint is
    unreachable. Absent, not broken — distinct from a run that failed, so a
    caller can say "no model, skipping" (exit 0) instead of tracing back.
    Raised by adapters; caught by the doers that call them."""


class ModelBackend(ABC):
    """A runnable model. Agents depend on THIS, not on a provider."""

    name: str

    @abstractmethod
    def run(self, prompt: str, **opts) -> str:
        """Run the prompt on the model and return the text response."""
        raise NotImplementedError
