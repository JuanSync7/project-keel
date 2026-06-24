"""
title: REST API schemas
layer: backend
public_api: no
summary: Pydantic HTTP DTOs. Mirror the src/shared contract — one source of truth.
"""
from pydantic import BaseModel

__all__ = ["ThingIn", "ThingOut"]


class ThingIn(BaseModel):
    """Request body for creating a Thing (mirrors src/shared)."""
    name: str
    value: int = 0


class ThingOut(BaseModel):
    """Response body for a created Thing (mirrors src/shared)."""
    name: str
    value: int
