"""
title: Agent surface models
layer: backend
public_api: no
summary: Vendor-neutral value objects an agent surface speaks: card, reply, capability.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

__all__ = ["AgentKind", "Capability", "AgentCard", "AgentReply"]


class AgentKind(str, Enum):
    """The single role dimension that classifies an agent surface."""

    WIKI = "wiki"
    WORKER = "worker"
    TEAMMATE = "teammate"
    AMBIENT = "ambient"


@dataclass(frozen=True)
class Capability:
    """One named action a surface advertises (rendered on its card)."""

    command: str          # e.g. "/ask"
    title: str            # human label
    arg_hint: str = ""    # e.g. "<question>"
    description: str = ""


@dataclass(frozen=True)
class AgentCard:
    """Vendor-neutral self-description of a service reachable as an agent.

    This is the *vocabulary* every wire dialect (AAD, A2A, an MCP-native
    descriptor, ...) renders from; it carries no dialect-specific fields (no
    well-known path, no version envelope, no transport binding) — those belong
    to an adapter, never here.
    """

    slug: str
    name: str
    kind: AgentKind = AgentKind.WORKER
    tagline: str = ""
    description: str = ""
    owner: str = ""
    tags: tuple[str, ...] = ()
    capabilities: tuple[Capability, ...] = ()
    example_prompts: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentReply:
    """A single answer from a surface, plus optional presentation/meta/error.

    Field names are neutral; a wire adapter maps them onto its own payload
    (e.g. AAD's `io` map) so the surface never hard-codes a dialect's keys.
    """

    answer: str
    meta: str = ""
    html: str = ""
    error: str = ""
