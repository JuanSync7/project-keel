"""
title: MCP Q&A server
layer: backend
public_api: no
summary: Read-only MCP tools that answer questions from the corpus via the wiki_navigator agent.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Thin transport: reach the agent via the repo's package public API. Insert the
# repo root (for `agents`/`models`/`runtimes`) and this dir (for `protocol`).
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agents.wiki_navigator import answer  # noqa: E402

from protocol import Tool, ToolServer, serve_stdio  # noqa: E402

__all__ = ["build_qa_server"]

_ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "question": {"type": "string", "description": "the question to answer"},
    },
    "required": ["question"],
    "additionalProperties": False,
}


def build_qa_server(model: str | None = None, corpus: str | None = None) -> ToolServer:
    """Build the read-only Q&A server.

    ``model`` selects the backend by name (``None`` = the registry default);
    tests pass ``"fake"`` for a deterministic, offline answer. ``corpus`` is an
    optional corpus path (``None`` = the live ``wiki/corpus.json``). The single
    tool delegates to ``wiki_navigator.answer`` and surfaces its citations — no
    retrieval or synthesis logic lives here.
    """
    def wiki_answer(args: dict) -> dict:
        ans = answer(args["question"], execute=True, model=model, corpus=corpus)
        return {
            "text": ans.text,
            "dry_run": ans.dry_run,
            "citations": [
                {"node_id": c.node_id, "path": c.path,
                 "summary_source": c.summary_source,
                 "owner": c.owner, "owner_source": c.owner_source}
                for c in ans.citations
            ],
        }

    return ToolServer("keel-wiki-qa", (
        Tool(name="wiki_answer",
             description="Answer a question from the project corpus, with citations.",
             input_schema=_ANSWER_SCHEMA, handler=wiki_answer),
    ))


if __name__ == "__main__":   # pragma: no cover — launched by an MCP client
    serve_stdio(build_qa_server(model=os.environ.get("KEEL_MCP_MODEL")))
