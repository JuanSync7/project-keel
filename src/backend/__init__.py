"""
title: Backend public API
layer: backend
public_api: yes
summary: The only import surface for the backend package.
"""
# Re-export the public surface. Callers import FROM HERE, never from
# private submodules. Keep __all__ tight and intentional.
from .contracts import Repository, Service
from .example_feature import Thing, do_thing

__all__ = ["Repository", "Service", "Thing", "do_thing"]
