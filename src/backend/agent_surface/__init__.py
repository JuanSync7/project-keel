"""
title: Agent surface (vendor-neutral)
layer: backend
public_api: yes
summary: AgentSurface contract + neutral card/reply a service implements to be reachable as an agent.
"""
from ._models import AgentCard, AgentKind, AgentReply, Capability
from .contracts import AgentSurface

__all__ = ["AgentSurface", "AgentCard", "AgentReply", "Capability", "AgentKind"]
