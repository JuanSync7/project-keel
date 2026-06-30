"""
title: Integration — MCP servers (Q&A + action)
kind: tests
layer: backend
summary: The thin MCP servers expose schema'd tools that delegate to wiki_navigator and a jobs doer; the action tool defaults to dry-run.
"""
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "mcp"))

from action_server import build_action_server  # noqa: E402
from qa_server import build_qa_server  # noqa: E402

pytestmark = pytest.mark.integration


def _tiny_corpus(tmp_path: Path) -> str:
    """A one-node public corpus query_corpus.py can retrieve over (absolute path)."""
    node = {
        "node_id": "keel", "kind": "doc", "title": "Project Keel",
        "path": "README.md", "summary": "a project skeleton that stays honest",
        "text_excerpt": "", "owner": "alice", "owner_source": "frontmatter",
        "summary_source": "authored", "tags": ["keel", "template", "skeleton"],
        "visibility": "public", "anchor": None, "lineno": None,
        "parent": None, "children": [], "links": [],
    }
    p = tmp_path / "corpus.json"
    p.write_text(json.dumps({"schema_version": 1, "nodes": [node]}), encoding="utf-8")
    return str(p)


# --- shared invariant: every tool is well-formed -------------------------------

def test_every_tool_has_a_schema_and_a_one_line_description():
    for server in (build_qa_server(), build_action_server()):
        listed = server.tools_list()
        assert listed, "%s exposes no tools" % server.name
        for tool in listed:
            assert tool["name"]
            assert tool["description"] and "\n" not in tool["description"]
            assert tool["inputSchema"]["type"] == "object"


def test_unknown_tool_is_a_protocol_error_not_a_crash():
    result = build_qa_server().call_tool("does_not_exist", {})
    assert result["isError"] is True


# --- Q&A server: read-only, delegates to wiki_navigator ------------------------

def test_qa_tool_answers_with_citations_using_the_fake_model(tmp_path):
    server = build_qa_server(model="fake", corpus=_tiny_corpus(tmp_path))
    result = server.call_tool("wiki_answer", {"question": "what is keel"})

    assert result["isError"] is False
    answer = result["structuredContent"]
    assert answer["text"]                                   # the fake synthesised something
    assert answer["dry_run"] is False                       # Q&A actually answers
    assert any(c["node_id"] == "keel" for c in answer["citations"])  # cited its source


def test_qa_tool_filters_non_public_nodes(tmp_path):
    """A confidential node must never reach a citation (visibility honoured)."""
    corpus = json.loads(Path(_tiny_corpus(tmp_path)).read_text())
    corpus["nodes"][0]["visibility"] = "confidential"
    p = tmp_path / "corpus.json"
    p.write_text(json.dumps(corpus), encoding="utf-8")   # overwrite with the secret node

    server = build_qa_server(model="fake", corpus=str(p))
    answer = server.call_tool("wiki_answer", {"question": "what is keel"})["structuredContent"]
    assert all(c["node_id"] != "keel" for c in answer["citations"])


# --- action server: defaults to dry-run ----------------------------------------

def _repo_with_readme(tmp_path: Path) -> Path:
    (tmp_path / "README.md").write_text("---\ntitle: Sample\n---\n# Sample\n",
                                        encoding="utf-8")
    return tmp_path


def test_action_tool_dry_run_writes_nothing(tmp_path):
    root = _repo_with_readme(tmp_path)
    out = tmp_path / "INDEX.md"
    server = build_action_server(root=str(root))

    result = server.call_tool("rebuild_index", {"out": str(out)})   # execute omitted

    assert result["isError"] is False
    report = result["structuredContent"]
    assert report["executed"] is False
    assert report["bytes"] > 0                # it computed what it WOULD write…
    assert not out.exists()                   # …but wrote nothing


def test_action_tool_execute_true_writes_the_file(tmp_path):
    root = _repo_with_readme(tmp_path)
    out = tmp_path / "INDEX.md"
    server = build_action_server(root=str(root))

    result = server.call_tool("rebuild_index", {"out": str(out), "execute": True})

    assert result["isError"] is False
    assert result["structuredContent"]["executed"] is True
    assert out.exists() and "Sample" in out.read_text()
