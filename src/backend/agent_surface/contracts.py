"""
title: Agent surface contract
layer: backend
public_api: yes
summary: The vendor-neutral AgentSurface interface a wire adapter (AAD, A2A, ...) renders.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ._models import AgentCard, AgentReply

__all__ = ["AgentSurface"]


@runtime_checkable
class AgentSurface(Protocol):
    """A service that can be reached as an agent.

    Implement these three methods and any wire dialect can expose you:
    `card()` self-describes, `ask()` answers a single question, `health()`
    reports liveness. Depend on THIS, never on a concrete wire format — the
    dialect (AAD today; A2A / a plugin manifest tomorrow) is a thin adapter
    that serializes a surface, registered alongside, never baked in here.
    """

    def card(self) -> AgentCard:
        """Return this service's vendor-neutral self-description."""
        ...

    def ask(self, question: str) -> AgentReply:
        """Answer one question; return a neutral reply (answer + optional meta/html/error)."""
        ...

    def health(self) -> dict:
        """Return a liveness payload, e.g. ``{"status": "ok"}``."""
        ...
