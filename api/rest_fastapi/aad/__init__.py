"""
title: AAD adapter
layer: backend
public_api: yes
summary: Expose a neutral AgentSurface over the AAD wire format (descriptor + ask + health).
"""
from .descriptor import AAD_VERSION, AadDescriptor, card_to_aad
from .router import build_aad_router

__all__ = ["build_aad_router", "card_to_aad", "AadDescriptor", "AAD_VERSION"]
