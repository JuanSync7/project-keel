"""
title: Model backend contract
layer: backend
public_api: yes
summary: The ABC every model adapter implements.
"""
from __future__ import annotations
from abc import ABC, abstractmethod

__all__ = ["ModelBackend"]


class ModelBackend(ABC):
    """A runnable model. Agents depend on THIS, not on a provider."""

    name: str

    @abstractmethod
    def run(self, prompt: str, **opts) -> str:
        """Run the prompt on the model and return the text response."""
        raise NotImplementedError
