"""
title: Models public API
layer: backend
public_api: yes
summary: get_model(name) -> a ModelBackend the agents/app run on; choose_model(name) says which model that is and whether it was the registry default; CountedModel and ModelMeter hold a run's backend to its approved model-call count, approve_resume holds a saved run to the approved model and count, and approved_cap reads that count from config/project.json.
"""

from .budget import (
    CAP_KEY,
    CallCapReached,
    CountedModel,
    ModelMeter,
    RunNotApproved,
    approve_resume,
    approved_cap,
)
from .contracts import ModelBackend, ModelUnavailable
from .registry import ModelChoice, choose_model, get_model, list_models

__all__ = [
    "CAP_KEY",
    "CallCapReached",
    "CountedModel",
    "ModelBackend",
    "ModelChoice",
    "ModelMeter",
    "ModelUnavailable",
    "RunNotApproved",
    "approve_resume",
    "approved_cap",
    "choose_model",
    "get_model",
    "list_models",
]
