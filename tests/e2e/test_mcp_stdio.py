"""
title: E2E — MCP stdio JSON-RPC journey
kind: tests
layer: backend
summary: A client starts each MCP server as its own process and speaks JSON-RPC to it over its real stdio - initialize, list tools, call a tool - and checks the Q&A server, under the shipped config/project.json `agents.max_model_calls` of 0, answers a question with a tool error naming that key rather than a model call (the answer it gives once a call is approved, cited from the corpus, is tests/integration/test_mcp_servers.py's); that one server process, started by a launcher under a scratch root whose config approves one call a question and `agents.max_session_model_calls` of 2, answers two questions from the corpus and refuses the third and fourth with a tool error naming the total key and the calls made, over the same stdio; and the action server's default is a dry run that leaves the tree as it was.
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


@pytest.mark.endpoint("mcp keel-wiki-qa/wiki_answer")
def test_wiki_answer_over_real_stdio(mcp_session):
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

    # The shipped count approves no model call, so the question is refused.
    result = by_id[3]["result"]
    assert result["isError"] is True
    assert "agents.max_model_calls" in result["content"][0]["text"]


def _qa_launcher(scratch, config):
    """A script that serves the real Q&A server's main under *scratch*, whose
    config/project.json is *config*: the shipped config approves no call, and
    main reads its limits from the root it is given, the one thing changed."""
    (scratch / "config").mkdir()
    (scratch / "config" / "project.json").write_text(json.dumps(config), "utf-8")
    launcher = scratch / "serve_qa.py"
    launcher.write_text(
        "import sys\n"
        "sys.path.insert(0, %r)\n"
        "import qa_server\n"
        "from exit_codes import finish\n"
        "finish(qa_server.main(root=%r))\n"
        % (str(_server("qa_server.py").parent), str(scratch)),
        "utf-8",
    )
    return launcher


@pytest.mark.endpoint("mcp keel-wiki-qa/wiki_answer")
def test_wiki_answer_is_refused_past_the_session_total_over_real_stdio(
    mcp_session, real_corpus, tmp_path
):
    total = 2
    launcher = _qa_launcher(
        tmp_path,
        {"agents": {"max_model_calls": 1, "max_session_model_calls": total}},
    )
    questions = [
        _call(n, "wiki_answer", {"question": "how is a child process started"})
        for n in range(2, 6)
    ]
    replies = mcp_session(
        launcher,
        [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}] + questions,
    )
    by_id = _by_id(replies)
    assert sorted(by_id) == [1, 2, 3, 4, 5]
    for answered in (2, 3):
        result = by_id[answered]["result"]
        assert result["isError"] is False, result
        assert result["structuredContent"]["citations"], result
    for refused in (4, 5):
        text = by_id[refused]["result"]["content"][0]["text"]
        assert by_id[refused]["result"]["isError"] is True
        assert text.startswith("SessionCapReached: "), text
        assert "made %d of its approved %d" % (total, total) in text
        assert "agents.max_session_model_calls (now %d)" % total in text


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
