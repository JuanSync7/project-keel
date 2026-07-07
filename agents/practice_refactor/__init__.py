"""
title: Practice refactor agent
layer: backend
public_api: yes
summary: Walks the corpus KG and refactors each chunk toward a named practice, gating every edit on make verify.
"""
from ._brain import RefactorReport, refactor

__all__ = ["refactor", "RefactorReport"]
