"""
title: Example feature implementation (private)
layer: backend
public_api: no
summary: Private impl. Never imported across the package boundary.
"""
from dataclasses import dataclass

__all__ = ["Thing", "do_thing"]


@dataclass(frozen=True)
class Thing:
    """An example domain value object. Replace with your real type."""
    name: str
    value: int = 0


def do_thing(name: str, value: int = 0) -> Thing:
    """Create a Thing. Replace with your real feature logic."""
    return Thing(name=name, value=value)
