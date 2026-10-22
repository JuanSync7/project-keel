"""
title: Unit — the doc reviewer's model step runs on an injected backend
kind: tests
layer: n/a
summary: doc_reviewer.propose(rules, chunk, backend=b) sends b the agent's real per-chunk prompt (its prompt.md preamble, the guide's rules and the chunk's kind, path, line, finding and text) and returns the reply parsed into a bounded edit spec, or None for a decline, an unparseable reply or a reply that names its own gate; it is built from the same prompt builder and parser the plan's propose step calls.
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from agents.doc_reviewer import propose  # noqa: E402
from models import ModelBackend  # noqa: E402

pytestmark = pytest.mark.unit

_RULES = [
    {"title": "Rosters", "text_excerpt": "A Not for cell names the sibling that is."}
]
_CHUNK = {
    "id": "roster:docs/README.md:x",
    "kind": "roster",
    "path": "docs/README.md",
    "line": 12,
    "finding": "Not for: n/a",
    "text": "12: | `x.md` | X | n/a |",
}
_EDIT = {
    "file": "docs/README.md",
    "find": "| `x.md` | X | n/a |",
    "replace": "| `x.md` | X | Y — `y.md` |",
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
    assert propose(_RULES, _CHUNK, backend=seen) == {"edits": [_EDIT]}
    (prompt,) = seen.prompts
    preamble = (_ROOT / "agents" / "doc_reviewer" / "prompt.md").read_text("utf-8")
    assert prompt.startswith(preamble)
    assert "## Rosters\nA Not for cell names the sibling that is." in prompt
    assert (
        "kind: roster\npath: docs/README.md\nline: 12\nfinding: Not for: n/a\n---\n"
        "12: | `x.md` | X | n/a |" in prompt
    )


@pytest.mark.parametrize(
    "reply",
    ['{"edits": []}', "Looks fine.", json.dumps({"edits": [_EDIT], "gate": "lint"})],
    ids=["decline", "prose", "names-a-gate"],
)
def test_propose_returns_none_for_a_reply_it_cannot_apply(reply):
    assert propose(_RULES, _CHUNK, backend=_Seen(reply)) is None
