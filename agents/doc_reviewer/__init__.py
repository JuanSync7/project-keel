"""
title: Doc reviewer agent
layer: backend
public_api: yes
summary: Reviews the documentation against docs/guides/doc-style.md — the deterministic findings first, then one judged edit per chunk, each gated on make check-docs.
"""

from ._brain import DocReviewReport, review

__all__ = ["review", "DocReviewReport"]
