"""
title: Models public API
layer: backend
public_api: yes
summary: get_model(name) -> a ModelBackend the agents/app run on; choose_model(name) says which model that is and whether it was the registry default; CountedModel and ModelMeter hold a run's backend to its approved model-call count, approve_resume holds a saved run to the approved model and count, and approved_cap reads that count from config/project.json; SessionBudget holds a long-lived caller to a total across all its runs, read by approved_session_cap.
"""

from .budget import (
    CAP_KEY,
    SESSION_CAP_KEY,
    CallCapReached,
    CountedModel,
    ModelMeter,
    RunNotApproved,
    SessionBudget,
    SessionCapReached,
    approve_resume,
    approved_cap,
    approved_session_cap,
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
    "SESSION_CAP_KEY",
    "SessionBudget",
    "SessionCapReached",
    "approve_resume",
    "approved_cap",
    "approved_session_cap",
    "choose_model",
    "get_model",
    "list_models",
]
