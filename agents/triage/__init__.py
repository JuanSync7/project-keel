"""
title: Triage agent
layer: backend
public_api: yes
summary: An LLM 'brain' that triages an event payload into a short summary.
"""
from ._brain import triage

__all__ = ["triage"]
