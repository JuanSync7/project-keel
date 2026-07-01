"""
title: MCP protocol core
layer: backend
public_api: no
summary: A dependency-free Tool/ToolServer model and a JSON-RPC-over-stdio loop for MCP servers.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

__all__ = ["Tool", "ToolServer", "handle_message", "serve_stdio"]

# MCP speaks JSON-RPC 2.0. We implement the small server side it needs
# (initialize / tools/list / tools/call) in pure stdlib, so the base install
# stays dependency-free — the official `mcp` SDK is one optional way to host
# these same tools, never a requirement (mirrors runtimes' inprocess vs
# langgraph). The neutral Tool registry below is the part worth testing; the
# stdio loop is the thin wire binding.
PROTOCOL_VERSION = "2024-11-05"
SERVER_VERSION = "0.1.0"
_METHOD_NOT_FOUND = -32601


@dataclass(frozen=True)
class Tool:
    """One callable tool: a name, a one-line description, an input JSON Schema,
    and a handler ``(arguments: dict) -> result``. The result is any JSON-able
    value (or a str); ``ToolServer`` wraps it into MCP content."""

    name: str
    description: str
    input_schema: dict
    handler: Callable[[dict], Any]


class ToolServer:
    """A named set of tools, plus the MCP shapes a transport needs.

    This is wire-agnostic: ``tools_list`` and ``call_tool`` return plain dicts,
    so they are exercised directly in tests with no I/O. ``serve_stdio`` (below)
    is the only part that touches stdin/stdout.
    """

    def __init__(self, name: str, tools: Tuple[Tool, ...]):
        self.name = name
        self.tools = tools
        self._by_name = {t.name: t for t in tools}

    def tools_list(self) -> list:
        """The MCP ``tools/list`` payload: name + description + inputSchema each."""
        return [{"name": t.name, "description": t.description,
                 "inputSchema": t.input_schema} for t in self.tools]

    def call_tool(self, name: str, arguments: Optional[dict] = None) -> dict:
        """Run a tool and return an MCP ``tools/call`` result.

        Unknown tools and handler exceptions become ``isError: True`` results
        (the protocol-level failure channel), never a transport crash. A
        non-string result is JSON-encoded into the text block and also returned
        verbatim under ``structuredContent`` for typed clients.
        """
        tool = self._by_name.get(name)
        if tool is None:
            return _error_result("unknown tool: %s" % name)
        try:
            result = tool.handler(arguments or {})
        except Exception as exc:   # noqa: BLE001 — surface as a protocol error, not a crash
            return _error_result("%s: %s" % (type(exc).__name__, exc))
        text = result if isinstance(result, str) else json.dumps(
            result, sort_keys=True, default=str)
        out = {"content": [{"type": "text", "text": text}], "isError": False}
        if not isinstance(result, str):
            out["structuredContent"] = result
        return out


def _error_result(message: str) -> dict:
    return {"content": [{"type": "text", "text": message}], "isError": True}


def handle_message(server: ToolServer, msg: dict) -> Optional[dict]:
    """Map one JSON-RPC request to a response (or ``None`` for a notification).

    Notifications (no ``id``) get no reply, per JSON-RPC. ``initialize``,
    ``tools/list`` and ``tools/call`` are handled; anything else is a
    ``-32601 method not found`` error.
    """
    msg_id = msg.get("id")
    method = msg.get("method", "")
    if msg_id is None:                      # a notification — acknowledge nothing
        return None
    if method == "initialize":
        return _ok(msg_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": server.name, "version": SERVER_VERSION},
        })
    if method == "tools/list":
        return _ok(msg_id, {"tools": server.tools_list()})
    if method == "tools/call":
        params = msg.get("params") or {}
        return _ok(msg_id, server.call_tool(params.get("name"),
                                            params.get("arguments")))
    return {"jsonrpc": "2.0", "id": msg_id,
            "error": {"code": _METHOD_NOT_FOUND,
                      "message": "method not found: %s" % method}}


def _ok(msg_id: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def serve_stdio(server: ToolServer, stdin=None, stdout=None) -> None:
    """Run the server over newline-delimited JSON-RPC on stdin/stdout.

    This is how an MCP client (e.g. Claude Code) launches the server as a
    subprocess. It is the thin wire binding — all behaviour lives in
    ``handle_message``/``ToolServer`` above, which tests drive directly.
    """
    rx = stdin or sys.stdin
    tx = stdout or sys.stdout
    for line in rx:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        response = handle_message(server, msg)
        if response is not None:
            tx.write(json.dumps(response) + "\n")
            tx.flush()
