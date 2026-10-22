"""
title: Unit — the practice refactor's model step runs on an injected backend
kind: tests
layer: n/a
summary: practice_refactor.propose(practice, practice_def, node, backend=b) sends b the agent's real per-chunk prompt (its prompt.md preamble, the practice's registry row and the chunk) and returns the reply parsed into a bounded edit spec carrying the practice, or None for a decline, an unparseable reply or a reply that names its own gate; a chunk with no path is declined without calling b. The plan's propose step calls the same function, so the eval harness judges the code refactor() runs.
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
