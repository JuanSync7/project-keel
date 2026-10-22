"""
title: Unit — the index enforcer's model step runs on an injected backend
kind: tests
layer: n/a
summary: index_enforcer.summarize_gap(node, backend=b) sends b the agent's real gap prompt (its prompt.md preamble, the one-sentence task and the node's title, path and text excerpt) and returns b's reply stripped; the plan's fill step calls the same function, so the eval harness judges the code enforce() runs.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from agents.index_enforcer import summarize_gap  # noqa: E402
from models import ModelBackend  # noqa: E402

pytestmark = pytest.mark.unit


class _Seen(ModelBackend):
    name = "seen"

    def __init__(self, reply):
        self.reply = reply
        self.prompts = []

    def run(self, prompt, **opts):
        self.prompts.append(prompt)
        return self.reply


def test_summarize_gap_sends_the_real_prompt_and_strips_the_reply():
    node = {
        "title": "Ingest",
        "path": "src/ingest.py",
        "text_excerpt": "def ingest(): ...",
    }
    seen = _Seen("\n Reads events into the queue.  \n")
    assert summarize_gap(node, backend=seen) == "Reads events into the queue."
    (prompt,) = seen.prompts
    preamble = (_ROOT / "agents" / "index_enforcer" / "prompt.md").read_text("utf-8")
    assert prompt.startswith(preamble)
    assert "Write ONE plain sentence" in prompt
    assert "title: Ingest\npath: src/ingest.py\n---\ndef ingest(): ..." in prompt
