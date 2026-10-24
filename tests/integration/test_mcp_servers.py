"""
title: Integration — MCP servers (Q&A + action)
kind: tests
layer: backend
summary: The thin MCP servers expose schema'd tools that delegate to wiki_navigator and a jobs doer; the action tool defaults to dry-run. Each wiki_answer is held to the server's approved model-call count, config/project.json `agents.max_model_calls` read by configured_cap: a count of 0, the default and the shipped value, answers with a tool error naming the key and makes no model call, a FakeModel subclass in models.registry._REGISTRY counting the calls. The Q&A server's `main` reads that count from the root it is given: under a root that approves one call a question reaches the model once, which the 0 this checkout ships would refuse. Each server's entry `main` turns a refused setting (a serve limit out of its bound, a blank KEEL_MCP_MODEL) into exit CONFIG through the exit helper with the key on stderr, before it caps memory or serves. Each server's `main` refuses a tool limit (config/project.json `agents.tool_timeout_seconds`) as CONFIG the same way, and hands its root's tool limits to the child it starts: under a 64-byte `agents.tool_max_output_bytes` the action server's dry-run index build, and the Q&A server's corpus query for a question, are each a tool error naming that key, the question with no model call made.
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "mcp"))
sys.path.insert(0, str(_ROOT / "scripts"))

import action_server  # noqa: E402
import protocol  # noqa: E402
import qa_server  # noqa: E402
from action_server import build_action_server  # noqa: E402
from exit_codes import ExitCode  # noqa: E402
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
        model="fake",
        corpus=_tiny_corpus(tmp_path),
        max_model_calls=1,
        max_session_model_calls=1,
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

    server = build_qa_server(
        model="fake", corpus=str(p), max_model_calls=1, max_session_model_calls=1
    )
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
        model="fake",
        corpus=_tiny_corpus(tmp_path),
        max_model_calls=1,
        max_session_model_calls=2,
    )
    for _ in range(2):
        assert server.call_tool("wiki_answer", {"question": "q"})["isError"] is False
    assert len(_Counted.prompts) == 2


def _ask(server, times):
    return [
        server.call_tool("wiki_answer", {"question": "what is keel"})
        for _ in range(times)
    ]


@pytest.mark.parametrize("total", [None, 0])
def test_a_session_with_no_approved_total_refuses_and_calls_no_model(
    total, tmp_path, monkeypatch
):
    monkeypatch.setitem(registry._REGISTRY, "fake", _Counted)
    monkeypatch.setattr(_Counted, "prompts", [])
    kwargs = {} if total is None else {"max_session_model_calls": total}
    server = build_qa_server(
        model="fake", corpus=_tiny_corpus(tmp_path), max_model_calls=1, **kwargs
    )
    for result in _ask(server, 2):
        assert result["isError"] is True
        text = result["content"][0]["text"]
        assert "agents.max_session_model_calls (now 0)" in text, text
        assert "made 0 of its approved 0" in text and "may make 1 more" in text
    assert _Counted.prompts == []


def test_a_session_answers_until_its_total_then_refuses_with_no_model_call(
    tmp_path, monkeypatch
):
    monkeypatch.setitem(registry._REGISTRY, "fake", _Counted)
    monkeypatch.setattr(_Counted, "prompts", [])
    server = build_qa_server(
        model="fake",
        corpus=_tiny_corpus(tmp_path),
        max_model_calls=1,
        max_session_model_calls=3,
    )
    results = _ask(server, 5)
    assert [r["isError"] for r in results] == [False, False, False, True, True]
    for refused in results[3:]:
        text = refused["content"][0]["text"]
        assert text.startswith("SessionCapReached: "), text
        assert "made 3 of its approved 3 model call(s)" in text
        assert "agents.max_session_model_calls (now 3)" in text
    assert len(_Counted.prompts) == 3


def test_the_session_counts_the_calls_made_not_the_bounds_admitted(
    tmp_path, monkeypatch
):
    """A question may make 2 calls but makes 1: a total of 3 admits a second
    question (1 made + 2 fits) and refuses a third (2 made + 2 does not)."""
    monkeypatch.setitem(registry._REGISTRY, "fake", _Counted)
    monkeypatch.setattr(_Counted, "prompts", [])
    server = build_qa_server(
        model="fake",
        corpus=_tiny_corpus(tmp_path),
        max_model_calls=2,
        max_session_model_calls=3,
    )
    results = _ask(server, 3)
    assert [r["isError"] for r in results] == [False, False, True]
    assert "made 2 of its approved 3" in results[2]["content"][0]["text"]
    assert len(_Counted.prompts) == 2


def test_a_per_question_cap_of_zero_is_refused_under_its_own_key(tmp_path):
    """Both caps at 0, the shipped values: a question that may make no call
    fits any total, so the refusal names agents.max_model_calls, the key the
    owner raises first."""
    server = build_qa_server(model="fake", corpus=_tiny_corpus(tmp_path))
    (result,) = _ask(server, 1)
    text = result["content"][0]["text"]
    assert "agents.max_model_calls (now 0)" in text
    assert "max_session_model_calls" not in text


@pytest.mark.parametrize("per_question, total", [(2, 1), (5, 4)])
def test_a_per_question_cap_over_the_session_total_is_config_before_serving(
    per_question, total, tmp_path, capsys, nothing_served
):
    """No question could ever be admitted, so the server refuses to start
    rather than serve a refusal to every question."""
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.json").write_text(
        json.dumps(
            {
                "agents": {
                    "max_model_calls": per_question,
                    "max_session_model_calls": total,
                }
            }
        ),
        encoding="utf-8",
    )
    assert qa_server.main(root=str(tmp_path)) is ExitCode.CONFIG
    assert nothing_served == []
    err = capsys.readouterr().err
    assert "agents.max_model_calls is %d" % per_question in err
    assert "agents.max_session_model_calls is %d" % total in err


@pytest.mark.parametrize("per_question, total", [(3, 3), (3, 0)])
def test_a_per_question_cap_equal_to_the_total_or_a_zero_total_serves(
    per_question, total, tmp_path, nothing_served
):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.json").write_text(
        json.dumps(
            {
                "agents": {
                    "max_model_calls": per_question,
                    "max_session_model_calls": total,
                }
            }
        ),
        encoding="utf-8",
    )
    assert qa_server.main(root=str(tmp_path)) is ExitCode.SUCCESS
    assert nothing_served[-1] == "served"


def test_the_server_session_total_is_read_from_config(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.json").write_text(
        json.dumps({"agents": {"max_session_model_calls": 5}}), encoding="utf-8"
    )
    assert qa_server.configured_session_cap(str(tmp_path)) == 5


def test_a_refused_session_total_is_config_before_the_qa_server_serves(
    tmp_path, capsys, nothing_served
):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.json").write_text(
        json.dumps({"agents": {"max_session_model_calls": -1}}), encoding="utf-8"
    )
    assert qa_server.main(root=str(tmp_path)) is ExitCode.CONFIG
    assert nothing_served == []
    assert "agents.max_session_model_calls" in capsys.readouterr().err


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


def _serve_block(tmp_path, block):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.json").write_text(
        json.dumps({"transports": {"serve": block}}), encoding="utf-8"
    )
    return str(tmp_path)


@pytest.fixture
def nothing_served(monkeypatch):
    """Records each memory cap and served loop, so no test caps this process
    or reads its stdin."""
    seen = []
    monkeypatch.setattr(
        protocol.resource_limits, "cap_memory", lambda mb: seen.append(mb) or "cap"
    )
    monkeypatch.setattr(protocol, "serve_stdio", lambda *a, **k: seen.append("served"))
    monkeypatch.delenv("KEEL_MCP_MODEL", raising=False)
    return seen


@pytest.mark.parametrize("server", [action_server, qa_server])
def test_a_refused_serve_limit_is_config_before_the_server_serves(
    server, tmp_path, capsys, nothing_served
):
    root = _serve_block(tmp_path, {"memory_cap_mb": 0})
    assert server.main(root=root) is ExitCode.CONFIG
    assert nothing_served == []
    assert "transports.serve.memory_cap_mb" in capsys.readouterr().err


@pytest.mark.parametrize("server", [action_server, qa_server])
def test_a_server_within_its_limits_serves_then_succeeds(
    server, tmp_path, nothing_served
):
    root = _serve_block(tmp_path, {"memory_cap_mb": 256})
    assert server.main(root=root) is ExitCode.SUCCESS
    assert nothing_served == [256, "served"]


def test_a_blank_model_variable_is_config_before_the_qa_server_serves(
    tmp_path, capsys, monkeypatch, nothing_served
):
    monkeypatch.setenv("KEEL_MCP_MODEL", " ")
    root = _serve_block(tmp_path, {"memory_cap_mb": 256})
    assert qa_server.main(root=root) is ExitCode.CONFIG
    assert nothing_served == []
    assert "KEEL_MCP_MODEL" in capsys.readouterr().err


def test_main_holds_each_question_to_the_cap_its_root_configures(
    tmp_path, monkeypatch, nothing_served
):
    """main reads the count from the root it is given: under a root that
    approves one call, a question reaches the model once; this checkout ships
    0, so a main that read any other config would refuse it."""
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.json").write_text(
        json.dumps(
            {
                "agents": {"max_model_calls": 1, "max_session_model_calls": 1},
                "transports": {"serve": {"memory_cap_mb": 256}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setitem(registry._REGISTRY, "fake", _Counted)
    monkeypatch.setattr(_Counted, "prompts", [])
    monkeypatch.setenv("KEEL_MCP_MODEL", "fake")
    corpus = _tiny_corpus(tmp_path)
    built = []

    def build(**kwargs):
        # The corpus is the one thing changed; the count is main's own.
        built.append(build_qa_server(**dict(kwargs, corpus=corpus)))
        return built[-1]

    monkeypatch.setattr(qa_server, "build_qa_server", build)
    assert qa_server.main(root=str(tmp_path)) is ExitCode.SUCCESS
    assert nothing_served == [256, "served"]
    (server,) = built
    result = server.call_tool("wiki_answer", {"question": "what is keel"})
    assert result["isError"] is False, result
    assert len(_Counted.prompts) == 1
    # The root's total of 1 is spent, so the next question is refused unasked.
    again = server.call_tool("wiki_answer", {"question": "what is keel"})
    assert again["isError"] is True
    assert "agents.max_session_model_calls (now 1)" in again["content"][0]["text"]
    assert len(_Counted.prompts) == 1


def _tool_block(tmp_path, agents):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.json").write_text(
        json.dumps({"agents": agents, "transports": {"serve": {"memory_cap_mb": 256}}}),
        encoding="utf-8",
    )
    return str(tmp_path)


@pytest.mark.parametrize("server", [action_server, qa_server])
def test_a_refused_tool_limit_is_config_before_the_server_serves(
    server, tmp_path, capsys, nothing_served
):
    root = _tool_block(tmp_path, {"tool_timeout_seconds": 0})
    assert server.main(root=root) is ExitCode.CONFIG
    assert nothing_served == []
    assert "agents.tool_timeout_seconds" in capsys.readouterr().err


def test_the_action_doer_is_held_to_the_tool_limits_its_root_configures(
    tmp_path, monkeypatch, nothing_served
):
    """main hands its root's tool limits to the doer: a 64-byte cap ends the
    dry-run index build, whose preview this checkout's shipped cap allows."""
    root = _tool_block(tmp_path, {"tool_max_output_bytes": 64})
    built = []

    def build(**kwargs):
        built.append(build_action_server(**kwargs))
        return built[-1]

    monkeypatch.setattr(action_server, "build_action_server", build)
    assert action_server.main(root=root) is ExitCode.SUCCESS
    (server,) = built
    result = server.call_tool("rebuild_index", {})
    assert result["isError"] is True, result
    assert "agents.tool_max_output_bytes" in json.dumps(result)


def test_each_question_is_held_to_the_tool_limits_its_root_configures(
    tmp_path, monkeypatch, nothing_served
):
    """main hands its root's tool limits to the navigator's retrieval: a
    64-byte cap ends the corpus query, whose hit this checkout's shipped cap
    allows, before any model call."""
    # A session total of 1, so the question reaches retrieval at all: the
    # default of 0 refuses it before the tool limit could be what stops it.
    root = _tool_block(
        tmp_path,
        {
            "max_model_calls": 1,
            "max_session_model_calls": 1,
            "tool_max_output_bytes": 64,
        },
    )
    monkeypatch.setitem(registry._REGISTRY, "fake", _Counted)
    monkeypatch.setattr(_Counted, "prompts", [])
    monkeypatch.setenv("KEEL_MCP_MODEL", "fake")
    corpus = _tiny_corpus(tmp_path)
    built = []

    def build(**kwargs):
        built.append(build_qa_server(**dict(kwargs, corpus=corpus)))
        return built[-1]

    monkeypatch.setattr(qa_server, "build_qa_server", build)
    assert qa_server.main(root=root) is ExitCode.SUCCESS
    (server,) = built
    result = server.call_tool("wiki_answer", {"question": "what is keel"})
    assert result["isError"] is True, result
    assert "agents.tool_max_output_bytes" in json.dumps(result)
    assert _Counted.prompts == []
