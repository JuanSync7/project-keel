"""
title: Shared tool-report reader
kind: script
layer: n/a
summary: Reads an agent tool's JSON object or list of objects; malformed, deeply nested or wrong-shaped output raises ToolReportUnreadable with the tool, status, root, stderr and remedy. Never ends the process.
effect: read-only
"""

import importlib
import importlib.util
import json
import os
import sys
from types import ModuleType
from typing import Any, Dict, List, Type, Union, overload

__all__ = ["read_report", "ToolReportUnreadable"]


class ToolReportUnreadable(RuntimeError):
    """A tool report that cannot be read, as report()'s three message parts."""

    def __init__(self, what: str, on: str, next_step: str) -> None:
        super().__init__("%s: %s; %s" % (what, on, next_step))
        self.parts = (what, on, next_step)


@overload
def read_report(
    tool: str,
    rc: int,
    out: str,
    err: str,
    root: str,
    *,
    container: Type[Dict[str, Any]],
) -> Dict[str, Any]: ...


@overload
def read_report(
    tool: str,
    rc: int,
    out: str,
    err: str,
    root: str,
    *,
    container: Type[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]: ...


def read_report(
    tool: str,
    rc: int,
    out: str,
    err: str,
    root: str,
    *,
    container: Union[Type[Dict[str, Any]], Type[List[Dict[str, Any]]]],
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """Read *tool*'s object or list of objects, or raise ToolReportUnreadable.

    Status accompanies the report rather than choosing its verdict: a red
    gate or a declined edit can return a readable report with nonzero status.
    Callers decide which tools must also succeed. Individual fields are not
    validated here.
    """

    def unreadable(why: str) -> ToolReportUnreadable:
        return ToolReportUnreadable(
            "%s gave the agent no readable report" % tool,
            "%s exited %d under %s with %s; its stderr: %s"
            % (tool, rc, root, why, err.strip() or "(empty)"),
            "run %s on that checkout to see its output, then rerun" % tool,
        )

    try:
        report = json.loads(out)
    except (ValueError, RecursionError) as exc:
        raise unreadable("output that cannot be read as JSON (%s)" % exc) from exc
    if container is dict:
        if isinstance(report, dict):
            return report
        raise unreadable("a JSON %s, not an object" % type(report).__name__)
    if not isinstance(report, list) or not all(
        isinstance(node, dict) for node in report
    ):
        raise unreadable("a JSON %s, not a list of objects" % type(report).__name__)
    return report


# Both entry-point and package imports must catch one error class.
_SELF = sys.modules.get(__name__)
if _SELF is None:
    raise ImportError(
        "tool_reports was executed without being registered in sys.modules; "
        "import it, or register the module before exec_module"
    )
sys.modules.setdefault("tool_reports", _SELF)
sys.modules.setdefault("scripts.tool_reports", _SELF)


def _bind_to_package(module: ModuleType) -> None:
    """Bind the alias to the scripts package that holds this file, if found."""
    here = os.path.realpath(os.path.dirname(os.path.abspath(__file__)))
    package: Any = sys.modules.get("scripts")
    if package is None:
        spec = importlib.util.find_spec("scripts")
        locations = [] if spec is None else spec.submodule_search_locations or []
        if here not in [os.path.realpath(path) for path in locations]:
            return
        package = importlib.import_module("scripts")
    if here in [os.path.realpath(path) for path in getattr(package, "__path__", [])]:
        package.tool_reports = module


_bind_to_package(_SELF)
