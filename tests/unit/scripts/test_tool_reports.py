"""
title: Unit — shared tool-report reader
kind: tests
layer: n/a
summary: Tool reports require the requested object or list of objects, refuse malformed and deeply nested JSON with useful diagnostics, and share one error under both import names in either import order.
"""

import importlib
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts"))

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "container, out",
    [(dict, "{}"), (dict, '{"ok":false}'), (list, "[]"), (list, '[{"a":1}, {}]')],
)
@pytest.mark.parametrize("rc", [0, 1, 2])
def test_readable_reports_keep_their_verdict_even_with_nonzero_status(
    container, out, rc
):
    from scripts import tool_reports

    got = tool_reports.read_report(
        "scripts/tool.py", rc, out, "", "/checkout", container=container
    )
    assert got == json.loads(out)


@pytest.mark.parametrize(
    "container, out",
    [
        (dict, ""),
        (dict, " \n\t"),
        (dict, "not json"),
        (dict, "[]"),
        (dict, "[1]"),
        (dict, "null"),
        (dict, '"x"'),
        (dict, "1"),
        (list, ""),
        (list, " \n\t"),
        (list, "not json"),
        (list, "{}"),
        (list, '{"a":1}'),
        (list, '"x"'),
        (list, "[1]"),
        (list, "[{}, null]"),
    ],
)
def test_unreadable_reports_name_the_tool_status_root_stderr_and_remedy(container, out):
    from scripts import tool_reports

    tool = "scripts/jobs/review_docs.py"
    with pytest.raises(tool_reports.ToolReportUnreadable) as raised:
        tool_reports.read_report(
            tool, 7, out, " diagnostic \n", "/checkout", container=container
        )
    what, on, next_step = raised.value.parts
    assert tool in what and tool in on and tool in next_step
    assert "exited 7" in on and "/checkout" in on and "diagnostic" in on
    assert all(part.strip() for part in raised.value.parts)
    assert isinstance(raised.value, RuntimeError)


def _nested_report():
    """The shallowest array nesting json.loads refuses at this call depth."""
    out = "0"
    while True:
        out = "[" + out + "]"
        try:
            json.loads(out)
        except RecursionError:
            return out


@pytest.mark.parametrize("container", [dict, list])
def test_nested_reports_raise_the_named_refusal(container):
    from scripts import tool_reports

    with pytest.raises(tool_reports.ToolReportUnreadable) as raised:
        tool_reports.read_report(
            "scripts/query_corpus.py",
            0,
            _nested_report(),
            "",
            "/checkout",
            container=container,
        )
    assert "(empty)" in raised.value.parts[1]
    assert isinstance(raised.value.__cause__, RecursionError)


@pytest.mark.parametrize("first", ["tool_reports", "scripts.tool_reports"])
def test_both_import_orders_share_one_module_and_error(monkeypatch, first):
    """A bare CLI import and an agent's package import raise the same class."""
    monkeypatch.syspath_prepend(str(_ROOT))
    monkeypatch.syspath_prepend(str(_ROOT / "scripts"))
    names = ("tool_reports", "scripts.tool_reports", "scripts")
    saved = {name: sys.modules.pop(name) for name in names if name in sys.modules}
    try:
        initial = importlib.import_module(first)
        bare = importlib.import_module("tool_reports")
        dotted = importlib.import_module("scripts.tool_reports")
        package = importlib.import_module("scripts")
        assert initial is bare and bare is dotted
        assert package.tool_reports is bare
        assert bare.__all__ == ["read_report", "ToolReportUnreadable"]
        with pytest.raises(dotted.ToolReportUnreadable):
            bare.read_report("scripts/tool.py", 0, "", "", "/checkout", container=dict)
        with pytest.raises(bare.ToolReportUnreadable):
            dotted.read_report(
                "scripts/tool.py", 0, "", "", "/checkout", container=list
            )
    finally:
        for name in names:
            sys.modules.pop(name, None)
        sys.modules.update(saved)
