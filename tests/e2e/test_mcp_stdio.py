"""
title: E2E — MCP stdio JSON-RPC journey
kind: tests
layer: backend
summary: A client starts each MCP server as its own process and speaks JSON-RPC to it over its real stdio - initialize, list tools, call a tool - and checks the Q&A server cites the live corpus and the action server's default is a dry run that leaves the tree as it was.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import live_server

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from scripts.child_env import build_child_env  # noqa: E402

pytestmark = pytest.mark.e2e

_METHOD_NOT_FOUND = -32601  # JSON-RPC 2.0


def _server(name):
    _e2e, manifest = live_server.load_e2e_config(str(_ROOT))
    return _ROOT / manifest["transports"]["available"]["mcp"] / name


def _call(request_id, tool, arguments):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }


def _by_id(replies):
    return {reply["id"]: reply for reply in replies}


def _corpus_ids(path):
    with open(path, encoding="utf-8") as fh:
        return {node["node_id"] for node in json.load(fh)["nodes"]}


@pytest.mark.endpoint("mcp keel-wiki-qa/wiki_answer")
def test_wiki_answer_over_real_stdio(mcp_session, real_corpus):
    corpus_ids = _corpus_ids(real_corpus)
    replies = mcp_session(
        _server("qa_server.py"),
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            # A notification has no id, so the server sends nothing back.
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            _call(3, "wiki_answer", {"question": "how is a child process started"}),
        ],
    )
    assert [reply["id"] for reply in replies] == [1, 2, 3]
    by_id = _by_id(replies)
    assert by_id[1]["result"]["serverInfo"]["name"] == "keel-wiki-qa"
    assert by_id[1]["result"]["capabilities"]["tools"] == {}
    tools = by_id[2]["result"]["tools"]
    assert "wiki_answer" in {tool["name"] for tool in tools}
    assert all("inputSchema" in tool and tool["description"] for tool in tools)

    result = by_id[3]["result"]
    assert result["isError"] is False
    answer = json.loads(result["content"][0]["text"])
    assert answer["text"]
    cited = [citation["node_id"] for citation in answer["citations"]]
    assert cited, "the answer should cite the corpus"
    assert set(cited) <= corpus_ids, set(cited) - corpus_ids


@pytest.mark.endpoint("mcp keel-wiki-qa/wiki_answer")
def test_unknown_method_is_a_jsonrpc_error_over_real_stdio(mcp_session):
    replies = mcp_session(
        _server("qa_server.py"), [{"jsonrpc": "2.0", "id": 9, "method": "nope/nope"}]
    )
    assert len(replies) == 1
    assert replies[0]["error"]["code"] == _METHOD_NOT_FOUND
    assert "result" not in replies[0]


def _tree_state(index):
    """What a write would change: `git status` when the root is a git work
    tree (a generated project may not be one), and the index file itself."""
    status = None
    probe = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=str(_ROOT),
        env=build_child_env(root=str(_ROOT)),
        capture_output=True,
        text=True,
    )
    if probe.returncode == 0 and probe.stdout.strip() == "true":
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=str(_ROOT),
            env=build_child_env(root=str(_ROOT)),
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    if index.is_file():
        stat = os.stat(str(index))
        return status, index.read_bytes(), stat.st_mtime_ns
    return status, None, None


@pytest.mark.endpoint("mcp keel-actions/rebuild_index")
def test_rebuild_index_dry_runs_over_real_stdio(mcp_session):
    target = "wiki/INDEX.md"
    before = _tree_state(_ROOT / target)
    replies = mcp_session(
        _server("action_server.py"),
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            _call(2, "rebuild_index", {}),
        ],
    )
    by_id = _by_id(replies)
    assert by_id[1]["result"]["serverInfo"]["name"] == "keel-actions"
    result = by_id[2]["result"]
    assert result["isError"] is False
    report = json.loads(result["content"][0]["text"])
    assert report["executed"] is False
    assert report["target"] == target
    assert report["bytes"] > 0
    assert report["preview"]
    assert _tree_state(_ROOT / target) == before
