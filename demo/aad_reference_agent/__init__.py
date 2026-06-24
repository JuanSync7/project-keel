"""
title: AAD reference agent package
kind: demo
layer: backend
public_api: yes
summary: Re-exports the runnable AAD reference agent (app + descriptor).
"""
from .app import DESCRIPTOR, EchoSurface, app, build_app

__all__ = ["app", "build_app", "EchoSurface", "DESCRIPTOR"]
