"""
title: Unit — the wiki navigator's model step runs on an injected backend
kind: tests
layer: n/a
summary: wiki_navigator.synthesize(question, nodes, backend=b) sends b the agent's real answer prompt (its prompt.md preamble, the question and each visible node cited by node_id), never a confidential or restricted node, and returns b's reply stripped; the plan's synthesize step calls the same function, so the eval harness judges the code answer() runs.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from agents.wiki_navigator import synthesize  # noqa: E402
from models import ModelBackend  # noqa: E402

pytestmark = pytest.mark.unit

_NODES = [
    {
        "node_id": "docs/a.md",
        "path": "docs/a.md",
        "summary": "Alpha is the ingest service.",
        "summary_source": "authored",
        "visibility": "internal",
    },
    {
        "node_id": "docs/secret.md",
        "path": "docs/secret.md",
        "summary": "The vault key.",
        "summary_source": "authored",
        "visibility": "confidential",
    },
    {
        "node_id": "docs/r.md",
        "path": "docs/r.md",
        "summary": "Restricted plan.",
        "summary_source": "authored",
        "visibility": "restricted",
    },
]


class _Seen(ModelBackend):
    name = "seen"

    def __init__(self, reply):
        self.reply = reply
        self.prompts = []

    def run(self, prompt, **opts):
        self.prompts.append(prompt)
        return self.reply


def test_synthesize_sends_the_real_prompt_and_strips_the_reply():
    seen = _Seen("  Alpha ingests events [docs/a.md].\n")
    assert synthesize("What is alpha?", _NODES, backend=seen) == (
        "Alpha ingests events [docs/a.md]."
    )
    (prompt,) = seen.prompts
    assert "# Question\nWhat is alpha?" in prompt
    assert "- [authored] docs/a.md (docs/a.md): Alpha is the ingest service." in prompt
    preamble = (_ROOT / "agents" / "wiki_navigator" / "prompt.md").read_text("utf-8")
    assert prompt.startswith(preamble)


def test_synthesize_never_sends_a_confidential_or_restricted_node():
    seen = _Seen("x")
    synthesize("What is the vault key?", _NODES, backend=seen)
    (prompt,) = seen.prompts
    assert "docs/secret.md" not in prompt and "The vault key." not in prompt
    assert "docs/r.md" not in prompt


def test_synthesize_with_nothing_visible_says_so():
    seen = _Seen("x")
    synthesize("q", _NODES[1:], backend=seen)
    assert "(nothing retrieved)" in seen.prompts[0]
