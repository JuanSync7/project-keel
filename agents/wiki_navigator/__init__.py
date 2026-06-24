"""
title: Wiki navigator agent
layer: backend
public_api: yes
summary: Answers a question by traversing the corpus tree+links; cited answer + provenance.
"""
from ._brain import Answer, Citation, answer

__all__ = ["answer", "Answer", "Citation"]
