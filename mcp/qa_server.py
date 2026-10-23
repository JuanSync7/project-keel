"""
title: MCP Q&A server
layer: backend
public_api: no
summary: Read-only MCP tools that answer questions from the corpus via the wiki_navigator agent. The model it asks is the KEEL_MCP_MODEL variable, read by configured_model through scripts/config_loader.py; unset or empty is the declared null default, the registry's own model, written to stderr once, and a blank value is refused. Each question is held to config/project.json `agents.max_model_calls`, read once at start by configured_cap (models.approved_cap): a count of 0, the shipped value and the default of build_qa_server, answers every question with a tool error naming the key and makes no model call; the count is per question, so the server's total over its lifetime is not capped.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path
from typing import IO

# Thin transport: reach the agent via the repo's package public API. Insert the
# repo root (for `agents`/`models`/`runtimes`) and this dir (for `protocol`).
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agents.wiki_navigator import answer  # noqa: E402
from models import CallCapReached, approved_cap  # noqa: E402
from protocol import Tool, ToolServer, serve_stdio  # noqa: E402
from scripts import config_loader  # noqa: E402

__all__ = ["build_qa_server", "configured_cap", "configured_model"]

_MODEL = ("KEEL_MCP_MODEL",)

_ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "question": {"type": "string", "description": "the question to answer"},
    },
    "required": ["question"],
    "additionalProperties": False,
}


def configured_model(
    environ: Mapping[str, str] | None = None, stream: IO[str] | None = None
) -> str | None:
    """The model the server asks: the KEEL_MCP_MODEL variable, resolved through
    its scripts/config_loader.py KEYS row (*environ*: os.environ when None).
    Unset or empty is the row's null default, the registry's own model, which
    the loader writes to *stream* (stderr when None) once per process; a value
    the row refuses raises config_loader.WrongValue."""
    values = config_loader.resolve(
        {}, config_loader.rows(_MODEL), "the environment", environ, stream
    )
    model: str | None = values[_MODEL]
    return model


def configured_cap(root: str | None = None) -> int:
    """The model calls one question may make: config/project.json
    `agents.max_model_calls` at *root* (this repository when None). Raises
    config_loader.ConfigError for a value the loader refuses."""
    return approved_cap(root or str(_ROOT))


def build_qa_server(
    model: str | None = None, corpus: str | None = None, max_model_calls: int = 0
) -> ToolServer:
    """Build the read-only Q&A server.

    ``model`` selects the backend by name (``None`` = the registry default);
    tests pass ``"fake"`` for a deterministic, offline answer. ``corpus`` is an
    optional corpus path (``None`` = the live ``wiki/corpus.json``).
    ``max_model_calls`` is the count each question is held to (0, the
    default, approves none, so every question is a tool error). The single
    tool delegates to ``wiki_navigator.answer`` and surfaces its citations — no
    retrieval or synthesis logic lives here.
    """

    def wiki_answer(args: dict) -> dict:
        try:
            ans = answer(
                args["question"],
                execute=True,
                model=model,
                corpus=corpus,
                max_model_calls=max_model_calls,
            )
        except CallCapReached as exc:
            # Re-raised naming the key, since the protocol shows only this text.
            raise CallCapReached(
                exc.cap,
                exc.calls,
                "%s; raise config/project.json agents.max_model_calls (now %d) "
                "to approve each question's call" % (exc, max_model_calls),
            ) from exc
        return {
            "text": ans.text,
            "dry_run": ans.dry_run,
            "citations": [
                {
                    "node_id": c.node_id,
                    "path": c.path,
                    "summary_source": c.summary_source,
                    "owner": c.owner,
                    "owner_source": c.owner_source,
                }
                for c in ans.citations
            ],
        }

    return ToolServer(
        "keel-wiki-qa",
        (
            Tool(
                name="wiki_answer",
                description="Answer a question from the project corpus, with citations.",
                input_schema=_ANSWER_SCHEMA,
                handler=wiki_answer,
            ),
        ),
    )


if __name__ == "__main__":  # pragma: no cover — launched by an MCP client
    serve_stdio(
        build_qa_server(model=configured_model(), max_model_calls=configured_cap())
    )
