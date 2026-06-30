"""
title: Showcase
layer: backend
public_api: yes
summary: Read model that presents project_keel as a product (overview, features, checks, corpus).
"""
from __future__ import annotations

from ._data import (
    CHECKS,
    CONVENTIONS,
    FEATURES,
    PRINCIPLES,
    SETUP_STEPS,
    SUMMARY,
    TAGLINE,
)
from ._models import (
    Check,
    DocGroup,
    Feature,
    Layer,
    Link,
    NodeDetail,
    NodeRef,
    Overview,
    Principle,
    SearchHit,
    Stats,
    Step,
    Transport,
    to_jsonable,
)
from ._repo import Showcase, load_showcase

__all__ = [
    # facade + loader
    "Showcase", "load_showcase",
    # value objects
    "Overview", "Layer", "Transport", "Stats", "Feature", "Principle", "Check",
    "Step", "Link", "NodeRef", "DocGroup", "NodeDetail", "SearchHit", "to_jsonable",
    # curated constants (re-exported for direct use/tests)
    "FEATURES", "PRINCIPLES", "CHECKS", "SETUP_STEPS", "CONVENTIONS", "TAGLINE",
    "SUMMARY",
]
