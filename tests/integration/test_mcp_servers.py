"""
title: Integration — MCP servers (Q&A + action)
kind: tests
layer: backend
summary: The thin MCP servers expose schema'd tools that delegate to wiki_navigator and a jobs doer; the action tool defaults to dry-run. Each wiki_answer is held to the server's approved model-call count, config/project.json `agents.max_model_calls` read by configured_cap: a count of 0, the default and the shipped value, answers with a tool error naming the key and makes no model call, a FakeModel subclass in models.registry._REGISTRY counting the calls.
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "mcp"))

import qa_server  # noqa: E402
from action_server import build_action_server  # noqa: E402
from models import registry  # noqa: E402
from models.fake import FakeModel  # noqa: E402
from qa_server import build_qa_server  # noqa: E402
from scripts import config_loader  # noqa: E402

pytestmark = pytest.mark.integration


def _tiny_corpus(tmp_path: Path) -> str:
    """A one-node public corpus query_corpus.py can retrieve over (absolute path)."""
    node = {
        "node_id": "keel",
        "kind": "doc",
        "title": "Project Keel",
        "path": "README.md",
        "summary": "a project skeleton that stays honest",
        "text_excerpt": "",
        "owner": "alice",
        "owner_source": "frontmatter",
        "summary_source": "authored",
        "tags": ["keel", "template", "skeleton"],
        "visibility": "public",
        "anchor": None,
        "lineno": None,
        "parent": None,
        "children": [],
        "links": [],
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
    server = build_qa_server(
        model="fake", corpus=_tiny_corpus(tmp_path), max_model_calls=1
    )
    result = server.call_tool("wiki_answer", {"question": "what is keel"})

    assert result["isError"] is False
    answer = result["structuredContent"]
    assert answer["text"]  # the fake synthesised something
    assert answer["dry_run"] is False  # Q&A actually answers
    assert any(c["node_id"] == "keel" for c in answer["citations"])  # cited its source


def test_qa_tool_filters_non_public_nodes(tmp_path):
    """A confidential node must never reach a citation (visibility honoured)."""
    corpus = json.loads(Path(_tiny_corpus(tmp_path)).read_text())
    corpus["nodes"][0]["visibility"] = "confidential"
    p = tmp_path / "corpus.json"
    p.write_text(json.dumps(corpus), encoding="utf-8")  # overwrite with the secret node

    server = build_qa_server(model="fake", corpus=str(p), max_model_calls=1)
    answer = server.call_tool("wiki_answer", {"question": "what is keel"})[
        "structuredContent"
    ]
    assert all(c["node_id"] != "keel" for c in answer["citations"])


class _Counted(FakeModel):
    prompts: list = []

    def run(self, prompt, **opts):
        _Counted.prompts.append(prompt)
        return super().run(prompt, **opts)


@pytest.mark.parametrize("approved", [None, 0])
def test_qa_tool_with_no_approved_call_refuses_and_calls_no_model(
    approved, tmp_path, monkeypatch
):
    monkeypatch.setitem(registry._REGISTRY, "fake", _Counted)
    monkeypatch.setattr(_Counted, "prompts", [])
    kwargs = {} if approved is None else {"max_model_calls": approved}
    server = build_qa_server(model="fake", corpus=_tiny_corpus(tmp_path), **kwargs)
    for _ in range(3):
        result = server.call_tool("wiki_answer", {"question": "what is keel"})
        assert result["isError"] is True
        assert "agents.max_model_calls" in result["content"][0]["text"]
    assert _Counted.prompts == []


def test_qa_tool_makes_one_call_per_question_within_its_count(tmp_path, monkeypatch):
    monkeypatch.setitem(registry._REGISTRY, "fake", _Counted)
    monkeypatch.setattr(_Counted, "prompts", [])
    server = build_qa_server(
        model="fake", corpus=_tiny_corpus(tmp_path), max_model_calls=1
    )
    for _ in range(2):
        assert server.call_tool("wiki_answer", {"question": "q"})["isError"] is False
    assert len(_Counted.prompts) == 2


def test_the_server_count_is_read_from_config(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.json").write_text(
        json.dumps({"agents": {"max_model_calls": 3}}), encoding="utf-8"
    )
    assert qa_server.configured_cap(str(tmp_path)) == 3


# --- action server: defaults to dry-run ----------------------------------------


def _repo_with_readme(tmp_path: Path) -> Path:
    (tmp_path / "README.md").write_text(
        "---\ntitle: Sample\n---\n# Sample\n", encoding="utf-8"
    )
    return tmp_path


def test_action_tool_dry_run_writes_nothing(tmp_path):
    root = _repo_with_readme(tmp_path)
    out = tmp_path / "INDEX.md"
    server = build_action_server(root=str(root))

    result = server.call_tool("rebuild_index", {"out": str(out)})  # execute omitted

    assert result["isError"] is False
    report = result["structuredContent"]
    assert report["executed"] is False
    assert report["bytes"] > 0  # it computed what it WOULD write…
    assert not out.exists()  # …but wrote nothing


def test_action_tool_execute_true_writes_the_file(tmp_path):
    root = _repo_with_readme(tmp_path)
    out = tmp_path / "INDEX.md"
    server = build_action_server(root=str(root))

    result = server.call_tool("rebuild_index", {"out": str(out), "execute": True})

    assert result["isError"] is False
    assert result["structuredContent"]["executed"] is True
    assert out.exists() and "Sample" in out.read_text()


def test_action_tool_rejects_out_escaping_the_tree(tmp_path):
    """Defence in depth: MCP args may come from an LLM on untrusted input, so an
    'out' that resolves outside the indexed tree must be refused, not written."""
    root = _repo_with_readme(tmp_path)
    escape = tmp_path.parent / "escaped.md"  # one level above the tree
    server = build_action_server(root=str(root))

    result = server.call_tool(
        "rebuild_index", {"out": "../escaped.md", "execute": True}
    )

    assert result["isError"] is True  # refused at the boundary
    assert not escape.exists()  # and nothing was written


def test_the_server_model_is_the_declared_variable_or_its_declared_default(capsys):
    """KEEL_MCP_MODEL is a scripts/config_loader.py KEYS row: set, it names the
    model; unset or empty, the row's null default (the registry's own) is
    taken and said once; a blank value is refused, never passed on."""
    config_loader._ANNOUNCED.clear()
    try:
        assert qa_server.configured_model({"KEEL_MCP_MODEL": "fake"}) == "fake"
        assert capsys.readouterr().err == ""
        assert qa_server.configured_model({}) is None
        assert qa_server.configured_model({"KEEL_MCP_MODEL": ""}) is None
        err = capsys.readouterr().err
        assert err.count("[using default] KEEL_MCP_MODEL = null") == 1, err
        with pytest.raises(config_loader.WrongValue):
            qa_server.configured_model({"KEEL_MCP_MODEL": "  "})
    finally:
        config_loader._ANNOUNCED.clear()
