"""
title: Unit — the agent step doers a case drives
kind: tests
layer: n/a
summary: Each agent doer in evals.DOERS reads its case text as one JSON object holding exactly the step's named inputs, runs that agent's real model step on the backend it is handed, and returns the step's result as text; a text that is not JSON, is not an object, lacks a key, carries an extra one or gives a key the wrong type is a ValueError naming the doer, so a malformed case is that case's error, never a silent pass.
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from evals import DOERS, prompt_sha256  # noqa: E402
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


_NODE = {
    "node_id": "docs/a.md",
    "path": "docs/a.md",
    "summary": "Alpha ingests events.",
    "summary_source": "authored",
    "visibility": "internal",
}

# doer -> (a valid input object, the model's reply, the doer's expected text)
_EDIT = {
    "file": "src/a.py",
    "find": "raise ValueError('x')",
    "replace": "raise ValueError('x') from exc",
}

_VALID = {
    "doc_reviewer": (
        {
            "rules": [
                {
                    "title": "Rosters",
                    "text_excerpt": "A Not for cell names the sibling.",
                }
            ],
            "chunk": {
                "kind": "mention",
                "path": "docs/a.md",
                "line": 3,
                "finding": "bare section sign",
                "text": "3: see §4",
            },
        },
        json.dumps({"edits": [_EDIT]}),
        json.dumps({"edits": [_EDIT]}, sort_keys=True, separators=(",", ":")),
    ),
    "practice_refactor": (
        {
            "practice": "exception-chaining",
            "practice_def": {"id": "exception-chaining", "title": "Chain exceptions"},
            "node": {
                "node_id": "src/a.py",
                "path": "src/a.py",
                "text_excerpt": "raise ValueError('x')",
                "visibility": "internal",
            },
        },
        json.dumps({"edits": [_EDIT]}),
        json.dumps(
            {"edits": [_EDIT], "practice": "exception-chaining"},
            sort_keys=True,
            separators=(",", ":"),
        ),
    ),
    "index_enforcer": (
        {
            "node": {
                "title": "Ingest",
                "path": "src/ingest.py",
                "text_excerpt": "def ingest(): ...",
            }
        },
        "Reads events into the queue.\n",
        "Reads events into the queue.",
    ),
    "wiki_navigator": (
        {"question": "What is alpha?", "nodes": [_NODE]},
        " Alpha ingests events [docs/a.md].\n",
        "Alpha ingests events [docs/a.md].",
    ),
}


@pytest.mark.parametrize("doer", sorted(_VALID))
def test_an_agent_doer_runs_the_agent_step_on_the_backend(doer):
    inputs, reply, expected = _VALID[doer]
    seen = _Seen(reply)
    assert DOERS[doer](json.dumps(inputs), seen) == expected
    assert len(seen.prompts) == 1
    assert prompt_sha256(doer, json.dumps(inputs)).startswith("sha256:")


def _faults(inputs):
    key = sorted(inputs)[0]
    missing = dict(inputs)
    del missing[key]
    return {
        "not-json": "What is alpha?",
        "not-an-object": json.dumps([inputs]),
        "missing-key": json.dumps(missing),
        "extra-key": json.dumps(dict(inputs, extra=1)),
        "wrong-type": json.dumps(dict(inputs, **{key: 7})),
    }


@pytest.mark.parametrize(
    "doer, fault",
    [(d, f) for d in sorted(_VALID) for f in sorted(_faults(_VALID[d][0]))],
)
def test_an_agent_doer_refuses_a_malformed_case_text(doer, fault):
    text = _faults(_VALID[doer][0])[fault]
    seen = _Seen("x")
    with pytest.raises(ValueError, match=doer):
        DOERS[doer](text, seen)
    assert seen.prompts == []
