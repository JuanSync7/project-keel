"""
title: Backend contracts
layer: backend
public_api: yes
summary: ABCs / Protocols that define cross-package interfaces.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable

__all__ = ["Repository", "Service"]


@runtime_checkable
class Repository(Protocol):
    """A storage boundary. Structural: anything with these methods qualifies."""

    def get(self, key: str) -> object | None: ...
    def put(self, key: str, value: object) -> None: ...


class Service(ABC):
    """A unit of backend behavior. Depend on this, not on concretes."""

    @abstractmethod
    def handle(self, request: object) -> object:
        """Process a request and return a result."""
        raise NotImplementedError
