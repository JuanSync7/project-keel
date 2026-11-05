"""
title: Doc reviewer agent
layer: backend
public_api: yes
summary: Reviews the documentation against docs/guides/doc-style.md — the deterministic findings first, then one judged edit per chunk, each gated on make check-docs; re-exports the shared ToolReportUnreadable refusal for unreadable tool reports.
"""

from scripts.tool_reports import ToolReportUnreadable

from ._brain import DocReviewReport, RulesRefused, review
from ._step import propose

__all__ = [
    "review",
    "propose",
    "DocReviewReport",
    "RulesRefused",
    "ToolReportUnreadable",
]
