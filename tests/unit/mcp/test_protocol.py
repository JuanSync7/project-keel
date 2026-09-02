"""
title: Unit — MCP protocol boundary (malformed input is an error, not a crash)
kind: tests
layer: backend
summary: handle_message took `msg.get(...)` and `params.get("name")` on faith, so one malformed JSON-RPC line ended the session: a non-object message raised AttributeError, and a `name` that was a JSON array or object raised TypeError (unhashable) out of call_tool. serve_stdio wraps only json.loads, so either killed the loop for every subsequent request from that client. A transport must reject what it cannot parse with the error code JSON-RPC defines for it (-32600 invalid request, -32602 invalid params) and keep serving — validate at the boundary you own, and never let a caller's bad input take the server down.
"""

import io
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "mcp"))

import protocol as p  # noqa: E402

pytestmark = pytest.mark.unit

_INVALID_REQUEST = -32600
_INVALID_PARAMS = -32602


@pytest.fixture()
def server():
    return p.ToolServer(name="probe", tools=[])


def _call(name, arguments=None):
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments or {}},
    }


# --- a message that is not a JSON-RPC object ---------------------------------


@pytest.mark.parametrize(
    "msg", [5, [1, 2], "hi", None, True], ids=["int", "list", "str", "null", "bool"]
)
def test_non_object_message_is_an_invalid_request_not_an_exception(server, msg):
    """Reproduced before the fix: AttributeError: 'int' object has no attribute
    'get'. Any JSON value is a legal line on the wire; only an object is a legal
    JSON-RPC request, and saying so is the transport's job."""
    response = p.handle_message(server, msg)
    assert response is not None, "a malformed request must be answered, not ignored"
    assert response["error"]["code"] == _INVALID_REQUEST, response
    assert response["id"] is None, "an unparseable request has no id to echo"


# --- a name the tool registry cannot look up ---------------------------------


@pytest.mark.parametrize(
    "name", [["x"], {"a": 1}, 5, True], ids=["list", "dict", "int", "bool"]
)
def test_unhashable_or_non_string_tool_name_is_invalid_params(server, name):
    """Reproduced before the fix: TypeError: unhashable type: 'list', raised out
    of handle_message and through serve_stdio, ending the session."""
    response = p.handle_message(server, _call(name))
    assert response["error"]["code"] == _INVALID_PARAMS, response


def test_params_that_are_not_an_object_are_invalid_params(server):
    """`msg.get("params") or {}` kept a list as a list, so the very next
    `.get` raised."""
    msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": [1, 2]}
    assert p.handle_message(server, msg)["error"]["code"] == _INVALID_PARAMS


def test_a_missing_name_is_still_a_tool_result_not_a_protocol_error(server):
    """The one shape that always behaved: an ABSENT name is a well-formed request
    for a tool that does not exist, which is a tool-level isError, not -32602.
    Kept so the fix does not over-reach into working behaviour."""
    msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {}}
    result = p.handle_message(server, msg)["result"]
    assert result["isError"] is True
    assert "unknown tool" in result["content"][0]["text"]


# --- the loop must survive it ------------------------------------------------


def test_serve_stdio_keeps_serving_after_a_malformed_line(server):
    """The consequence that made this a blocker rather than a wart: one bad line
    from any client silently ended the session for every request after it."""
    lines = [
        json.dumps(5),  # not an object
        json.dumps(_call(["x"])),  # unhashable name
        "{not json at all",  # unparseable
        json.dumps({"jsonrpc": "2.0", "id": 9, "method": "tools/list"}),  # valid
    ]
    out = io.StringIO()
    p.serve_stdio(server, stdin=io.StringIO("\n".join(lines) + "\n"), stdout=out)

    replies = [json.loads(line) for line in out.getvalue().splitlines() if line.strip()]
    assert replies[-1]["id"] == 9, (
        "the valid request after the malformed ones was never answered: %s" % replies
    )
    assert "tools" in replies[-1]["result"]


def test_valid_traffic_is_unchanged(server):
    """Regression guard: the boundary check must not alter well-formed calls."""
    init = p.handle_message(
        server, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    )
    assert init["result"]["serverInfo"]["name"] == "probe"
    assert p.handle_message(server, {"jsonrpc": "2.0", "method": "note"}) is None
    unknown = p.handle_message(server, {"jsonrpc": "2.0", "id": 2, "method": "nope"})
    assert unknown["error"]["code"] == -32601
