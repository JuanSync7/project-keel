"""
title: Index enforcer agent
layer: backend
public_api: yes
summary: Enforces conventions, builds/maintains the wiki corpus, flags owner gaps.
"""

from ._brain import EnforceReport, enforce, summarize_gap

__all__ = ["enforce", "summarize_gap", "EnforceReport"]
