"""
title: Gate state — what scripts/check_structure.py's run_checks leaves behind, saved and put back around each test
summary: run_checks rebinds module globals (ROOT, the config memo, the error and warning lists and the reported sets) and leaves them pointing at the tree it last judged, so a test that calls it on a temporary tree hands every later test in the process that tree's root and memo. `rebound_names` reads the names from run_checks' own `global` statements, so a global a later change adds is covered without a list to keep in step, and refuses a module with no run_checks, one whose source cannot be read, or one that declares no global. `snapshot` keeps each value, a list, set or dict as a shallow copy so an in-place append is undone too, and `restore` puts them back. tests/conftest.py applies the pair to every test while check_structure is imported; tests/unit/test_gate_state.py holds each case.
"""

import ast
import copy
import inspect
import textwrap
from types import ModuleType
from typing import Dict, FrozenSet

# Keyed by module identity: the source is read once per imported module, not
# once per test, because the fixture runs around every test in the suite.
_NAMES: Dict[int, FrozenSet[str]] = {}


class GateStateError(Exception):
    """run_checks could not be read for the globals it rebinds."""


def rebound_names(module: ModuleType) -> FrozenSet[str]:
    """The globals *module*.run_checks declares with `global`; raises
    GateStateError when it has no run_checks or declares none."""
    key = id(module)
    if key in _NAMES:
        return _NAMES[key]
    func = getattr(module, "run_checks", None)
    if func is None:
        raise GateStateError("%s has no run_checks to read" % module.__name__)
    try:
        source = inspect.getsource(func)
    except (OSError, TypeError) as exc:
        raise GateStateError(
            "cannot read %s.run_checks for the globals it rebinds: %s"
            % (module.__name__, exc)
        ) from exc
    tree = ast.parse(textwrap.dedent(source))
    names = frozenset(
        name
        for node in ast.walk(tree)
        if isinstance(node, ast.Global)
        for name in node.names
    )
    if not names:
        # An empty set would restore nothing and pass every test: refuse it.
        raise GateStateError(
            "%s.run_checks declares no global; the state guard would restore"
            " nothing" % module.__name__
        )
    _NAMES[key] = names
    return names


def snapshot(module: ModuleType) -> Dict[str, object]:
    """Each rebound global of *module* by name, containers copied."""
    return {name: copy.copy(getattr(module, name)) for name in rebound_names(module)}


def restore(module: ModuleType, saved: Dict[str, object]) -> None:
    """Put back every global *saved* holds."""
    for name, value in saved.items():
        setattr(module, name, value)
