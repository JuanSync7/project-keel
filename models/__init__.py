"""
title: Models public API
layer: backend
public_api: yes
summary: get_model(name) -> a ModelBackend the agents/app run on; choose_model(name) says which model that is and whether it was the registry default.
"""

from .contracts import ModelBackend, ModelUnavailable
from .registry import ModelChoice, choose_model, get_model, list_models

__all__ = [
    "ModelBackend",
    "ModelChoice",
    "ModelUnavailable",
    "choose_model",
    "get_model",
    "list_models",
]
