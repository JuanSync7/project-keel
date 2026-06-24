"""
title: Example feature
layer: backend
public_api: yes
summary: Sample feature package showing the __init__-as-API boundary.
"""
from ._impl import Thing, do_thing  # implementation hidden behind the barrel

__all__ = ["Thing", "do_thing"]
