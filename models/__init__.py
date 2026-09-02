"""
title: Models public API
layer: backend
public_api: yes
summary: get_model(name) -> a ModelBackend the agents/app run on.
"""

from .contracts import ModelBackend, ModelUnavailable
from .registry import get_model, list_models

__all__ = ["ModelBackend", "ModelUnavailable", "get_model", "list_models"]
