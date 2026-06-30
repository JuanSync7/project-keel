"""
title: E2E — MCP stdio JSON-RPC journey
kind: tests
layer: backend
summary: A client speaks JSON-RPC to the MCP server — initialize, list tools, call a tool — end to end.
"""
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "mcp"))

from protocol import handle_message  # noqa: E402
from qa_server import build_qa_server  # noqa: E402

pytestmark = pytest.mark.e2e


def _corpus(tmp_path: Path) -> str:
    node = {
        "node_id": "keel", "kind": "doc", "title": "Project Keel",
        "path": "README.md", "summary": "a project skeleton that stays honest",
        "text_excerpt": "", "owner": "", "owner_source": "none",
        "summary_source": "authored", "tags": ["keel", "template"],
        "visibility": "public", "parent": None, "children": [], "links": [],
    }
    p = tmp_path / "corpus.json"
    p.write_text(json.dumps({"schema_version": 1, "nodes": [node]}), encoding="utf-8")
    return str(p)


def test_full_jsonrpc_session(tmp_path):
    server = build_qa_server(model="fake", corpus=_corpus(tmp_path))

    # 1. initialize — server announces its tool capability + identity.
    init = handle_message(server, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                   "params": {}})
    assert init["id"] == 1
    assert init["result"]["capabilities"]["tools"] == {}
    assert init["result"]["serverInfo"]["name"] == server.name

    # 2. initialized notification — no id, so NO response is sent.
    assert handle_message(server, {"jsonrpc": "2.0",
                                   "method": "notifications/initialized"}) is None

    # 3. tools/list — the wire form carries name + description + inputSchema.
    listed = handle_message(server, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = listed["result"]["tools"]
    assert any(t["name"] == "wiki_answer" for t in tools)
    assert all("inputSchema" in t and t["description"] for t in tools)

    # 4. tools/call — the answer comes back as MCP content, no error flag.
    called = handle_message(server, {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "wiki_answer", "arguments": {"question": "what is keel"}}})
    assert called["id"] == 3
    assert called["result"]["isError"] is False
    assert called["result"]["content"][0]["type"] == "text"
    assert called["result"]["content"][0]["text"]   # non-empty answer payload


def test_unknown_method_is_a_jsonrpc_error(tmp_path):
    server = build_qa_server(model="fake", corpus=_corpus(tmp_path))
    resp = handle_message(server, {"jsonrpc": "2.0", "id": 9, "method": "nope/nope"})
    assert resp["error"]["code"] == -32601    # method not found
    assert "result" not in resp
