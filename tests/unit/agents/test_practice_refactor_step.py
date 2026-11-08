"""
title: Unit — the practice refactor's model step runs on an injected backend
kind: tests
layer: n/a
summary: practice_refactor.propose(practice, practice_def, node, backend=b) sends b the agent's real per-chunk prompt (its prompt.md preamble, the practice's registry row and the chunk) and returns the reply parsed into a bounded edit spec carrying the practice, or None for a decline, an unparseable reply or a reply that names its own gate; a chunk with no path, or at a level outside config/project.json corpus.served_visibilities (one that states no level included), is declined without calling b. The plan's propose step calls the same function, so the eval harness judges the code refactor() runs.
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from agents.practice_refactor import propose  # noqa: E402
from models import ModelBackend  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "text", ["[1]", '{"practices": [1]}', "[" * 2000 + "0" + "]" * 2000]
)
def test_registry_decode_refusal_names_file_and_repair(tmp_path, text):
    import importlib

    from scripts import config_loader

    brain = importlib.import_module("agents.practice_refactor._brain")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "practices.json").write_text(text, encoding="utf-8")
    with pytest.raises(config_loader.ConfigUnreadable, match=r"practices.json.*repair"):
        brain._load_practice(str(tmp_path), "p")


def test_model_decode_refusal_names_reply_and_retry():
    with pytest.raises(RuntimeError, match=r"model reply.*retry"):
        propose("p", {}, _NODE, backend=_Seen("[" * 2000 + "0" + "]" * 2000))


@pytest.mark.parametrize(
    "step,tool",
    [
        ("_walk", "query_corpus"),
        ("_baseline", "run_make_target"),
        ("_apply", "apply_refactor"),
    ],
)
@pytest.mark.parametrize("text", ["[1]", "{", "[" * 2000 + "0" + "]" * 2000])
def test_tool_decode_refusal_names_tool_and_rerun(
    tmp_path, monkeypatch, step, tool, text
):
    import importlib

    brain = importlib.import_module("agents.practice_refactor._brain")
    monkeypatch.setattr(brain, "_run", lambda *args, **kwargs: (0, text, ""))
    state = {
        "root": str(tmp_path),
        "practice": "p",
        "max_nodes": 1,
        "gate": "check",
        "chunks": [_NODE],
        "cursor": 0,
        "spec": {"edits": [_EDIT]},
    }
    with pytest.raises(RuntimeError, match=tool + r".*rerun"):
        getattr(brain, step)(state)


_PDEF = {
    "id": "exception-chaining",
    "title": "Chain exceptions",
    "tier": "gate",
    "summary": "raise ... from exc inside an except block",
}
_NODE = {
    "node_id": "src/a.py",
    "path": "src/a.py",
    "tags": ["python"],
    "text_excerpt": "except KeyError:\n    raise ValueError('x')",
    "visibility": "internal",
}
_EDIT = {
    "file": "src/a.py",
    "find": "raise ValueError('x')",
    "replace": "raise ValueError('x') from exc",
}


class _Seen(ModelBackend):
    name = "seen"

    def __init__(self, reply):
        self.reply = reply
        self.prompts = []

    def run(self, prompt, **opts):
        self.prompts.append(prompt)
        return self.reply


def test_propose_sends_the_real_prompt_and_parses_the_spec():
    seen = _Seen("```json\n" + json.dumps({"edits": [_EDIT]}) + "\n```")
    spec = propose("exception-chaining", _PDEF, _NODE, backend=seen)
    assert spec == {"edits": [_EDIT], "practice": "exception-chaining"}
    (prompt,) = seen.prompts
    preamble = (_ROOT / "agents" / "practice_refactor" / "prompt.md").read_text("utf-8")
    assert prompt.startswith(preamble)
    assert "Chain exceptions (gate): raise ... from exc" in prompt
    assert (
        "node_id: src/a.py\npath: src/a.py\ntags: python\n---\nexcept KeyError:"
        in prompt
    )


@pytest.mark.parametrize(
    "reply",
    [
        '{"edits": []}',
        "I would chain it.",
        json.dumps({"edits": [_EDIT], "gate": "lint"}),
    ],
    ids=["decline", "prose", "names-a-gate"],
)
def test_propose_returns_none_for_a_reply_it_cannot_apply(reply):
    assert propose("exception-chaining", _PDEF, _NODE, backend=_Seen(reply)) is None


def test_a_chunk_with_no_path_is_declined_without_a_model_call():
    seen = _Seen(json.dumps({"edits": [_EDIT]}))
    assert (
        propose("exception-chaining", _PDEF, dict(_NODE, path=""), backend=seen) is None
    )
    assert seen.prompts == []


@pytest.mark.parametrize(
    "level",
    ["confidential", "restricted", None, "unreadable-readme"],
    ids=["confidential", "restricted", "unstated", "marker"],
)
def test_a_chunk_outside_the_served_levels_is_declined_without_a_model_call(level):
    """Its text_excerpt never reaches a prompt; a chunk that states no level is
    not assumed open."""
    node = dict(_NODE)
    if level is None:
        del node["visibility"]
    else:
        node["visibility"] = level
    seen = _Seen(json.dumps({"edits": [_EDIT]}))
    assert propose("exception-chaining", _PDEF, node, backend=seen) is None
    assert seen.prompts == []


def test_propose_reads_the_configured_levels(monkeypatch):
    """With `corpus.served_visibilities` read as `["public"]`, an internal chunk
    is declined too, so propose acts on the key rather than a literal."""
    from scripts import config_loader

    monkeypatch.setattr(
        config_loader, "served_visibilities", lambda root: frozenset({"public"})
    )
    seen = _Seen(json.dumps({"edits": [_EDIT]}))
    assert propose("exception-chaining", _PDEF, _NODE, backend=seen) is None
    assert seen.prompts == []


def test_checkout_refusal_names_the_folder_without_host_path(tmp_path):
    from agents.practice_refactor import refactor
    from scripts import corpus_level

    root = tmp_path / "reviewed-checkout"
    corpus = tmp_path / "read-checkout" / "wiki" / "corpus.json"
    with pytest.raises(corpus_level.NotACheckout) as raised:
        refactor("p", root=str(root), corpus=str(corpus))
    text = str(raised.value)
    assert "not both" in text
    assert "root reviewed-checkout, corpus read-checkout/wiki/corpus.json" in text
    assert str(tmp_path) not in text


def test_cli_checkout_refusal_names_the_folder_without_host_path(
    tmp_path, monkeypatch, capsys
):
    from scripts import refactor_practice as cli

    root = tmp_path / "reviewed-checkout"
    corpus = tmp_path / "read-checkout" / "wiki" / "corpus.json"
    assert (
        cli.main(["p", "--root", str(root), "--corpus", str(corpus)])
        is cli.exit_codes.ExitCode.USAGE
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "reviewed-checkout" in captured.err
    assert str(tmp_path) not in captured.err
