"""
title: Runtime registry
layer: backend
public_api: yes
summary: name -> runtime engine, plus the default. Add an engine adapter here.
"""
from __future__ import annotations

from ._inprocess import InProcessRuntime
from .contracts import Runtime

__all__ = ["get_runtime", "list_runtimes", "DEFAULT_RUNTIME"]

DEFAULT_RUNTIME = "inprocess"


def _load_langgraph():
    """Resolve the LangGraph engine lazily (import only when it is selected)."""
    from .langgraph_adapter import LangGraphRuntime
    return LangGraphRuntime


# name -> a thunk returning the engine class. The default is pure stdlib;
# 'langgraph' is LAZY so the default path (CI, pre-commit, the app) never
# imports langgraph or its dependency tree -- it is an optional extra
# (pyproject [project.optional-dependencies] langgraph). To add an engine, write
# an adapter implementing the Runtime contract and register its thunk here.
_REGISTRY = {
    "inprocess": lambda: InProcessRuntime,
    "langgraph": _load_langgraph,
}


def list_runtimes() -> list:
    """Return the registered runtime names, sorted (registered != installed)."""
    return sorted(_REGISTRY)


def get_runtime(name: str | None = None, **kwargs) -> Runtime:
    """Return a runtime engine by name (defaults to DEFAULT_RUNTIME).

    Raises KeyError for an unknown name; selecting an engine whose optional
    dependency is absent raises ImportError from its lazy loader (e.g.
    ``get_runtime("langgraph")`` without LangGraph installed).
    """
    key = name or DEFAULT_RUNTIME
    if key not in _REGISTRY:
        raise KeyError("unknown runtime %r; have %s" % (key, list_runtimes()))
    engine_cls = _REGISTRY[key]()
    return engine_cls(**kwargs)
