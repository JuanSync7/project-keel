"""
title: One script module under sibling and package import names
summary: Registers a loaded module under both names and binds it on this directory's scripts package; execution without a sys.modules entry raises ImportError. Stdlib-only and Python 3.6-safe.
"""

import importlib
import importlib.util
import os
import sys
from typing import Any

__all__ = ["register_module"]


def register_module(module_name: str, filename: str) -> None:
    """Share a module and its classes between hook and package imports.

    The caller must already be in sys.modules, as normal imports arrange.
    A dotted name already present there skips Python's package binding, so
    bind it explicitly when scripts resolves to the directory holding it.
    A different scripts package on the path is left alone.
    """
    name = os.path.splitext(os.path.basename(filename))[0]
    module = sys.modules.get(module_name)
    if module is None:
        raise ImportError(
            "%s was executed without being registered in sys.modules; "
            "import it, or register the module before exec_module" % name
        )
    sys.modules.setdefault(name, module)
    sys.modules.setdefault("scripts." + name, module)
    here = os.path.realpath(os.path.dirname(os.path.abspath(filename)))
    # A namespace package has no declared module attributes to type against.
    package: Any = sys.modules.get("scripts")
    if package is None:
        spec = importlib.util.find_spec("scripts")
        locations = [] if spec is None else spec.submodule_search_locations or []
        if here not in [os.path.realpath(p) for p in locations]:
            return
        package = importlib.import_module("scripts")
    if here in [os.path.realpath(p) for p in getattr(package, "__path__", [])]:
        setattr(package, name, module)


register_module(__name__, __file__)
