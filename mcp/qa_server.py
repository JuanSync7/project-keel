"""
title: MCP Q&A server
layer: backend
public_api: no
summary: Read-only MCP tools that answer questions from the corpus via the wiki_navigator agent. The model it asks is the KEEL_MCP_MODEL variable, read by configured_model through scripts/config_loader.py; unset or empty is the declared null default, the registry's own model, written to stderr once, and a blank value is refused. Each question is held to config/project.json `agents.max_model_calls`, read once at start by configured_cap (models.approved_cap): a count of 0, the shipped value and the default of build_qa_server, answers every question with a tool error naming the key and makes no model call. The server's total over its lifetime is held to `agents.max_session_model_calls`, read once at start by configured_session_cap (models.approved_session_cap) and counted by a models.SessionBudget: a question whose per-question count, added to the calls the process has made, would pass that total is answered with a tool error naming the key, the total and the calls made, and makes no model call; 0, the shipped value and the default of build_qa_server, admits no question that may make a call. `main` is the entry: it serves through mcp/protocol.py run_stdio_server and exits 0 once the loop ends, or CONFIG through scripts/exit_codes.py report, naming the key or variable, when a setting it reads is refused before it serves.
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
# scripts/ itself, so the exit helper imports by its one bare name.
sys.path.insert(2, str(_ROOT / "scripts"))

from agents.wiki_navigator import answer  # noqa: E402
from exit_codes import ExitCode, finish, report  # noqa: E402
from models import (  # noqa: E402
    CallCapReached,
    SessionBudget,
    SessionCapReached,
    approved_cap,
    approved_session_cap,
    get_model,
)
from protocol import Tool, ToolServer, run_stdio_server  # noqa: E402
from scripts import config_loader  # noqa: E402

__all__ = [
    "build_qa_server",
    "configured_cap",
    "configured_model",
    "configured_session_cap",
    "main",
]

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


def configured_session_cap(root: str | None = None) -> int:
    """The model calls this server process may make across all its questions:
    config/project.json `agents.max_session_model_calls` at *root* (this
    repository when None). Raises config_loader.ConfigError for a value the
    loader refuses."""
    return approved_session_cap(root or str(_ROOT))


def build_qa_server(
    model: str | None = None,
    corpus: str | None = None,
    max_model_calls: int = 0,
    max_session_model_calls: int = 0,
) -> ToolServer:
    """Build the read-only Q&A server.

    ``model`` selects the backend by name (``None`` = the registry default);
    tests pass ``"fake"`` for a deterministic, offline answer. ``corpus`` is an
    optional corpus path (``None`` = the live ``wiki/corpus.json``).
    ``max_model_calls`` is the count each question is held to (0, the
    default, approves none, so every question is a tool error).
    ``max_session_model_calls`` is the total the server's questions may make
    together (0, the default, admits no question that may make a call). The
    single tool delegates to ``wiki_navigator.answer`` and surfaces its
    citations — no retrieval or synthesis logic lives here.
    """

    session = SessionBudget(max_session_model_calls)

    def wiki_answer(args: dict) -> dict:
        # Outside the try below: SessionCapReached is a CallCapReached, and
        # that handler would word it as the per-question cap.
        try:
            session.admit(max_model_calls)
        except SessionCapReached as exc:
            raise SessionCapReached(
                exc.total,
                exc.calls,
                exc.bound,
                "%s; raise config/project.json agents.max_session_model_calls "
                "(now %d) and restart the server to approve another question"
                % (exc, max_session_model_calls),
            ) from exc
        try:
            ans = answer(
                args["question"],
                execute=True,
                model=model,
                corpus=corpus,
                max_model_calls=max_model_calls,
                backend_factory=session.counted(get_model),
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


def main(root: str | None = None) -> ExitCode:
    """Serve the Q&A tools over stdio under *root*'s limits (this checkout
    when None) until stdin ends or a stop signal; CONFIG for a refused
    setting, the model variable included, before anything serves."""
    try:
        server = build_qa_server(
            model=configured_model(),
            max_model_calls=configured_cap(root),
            max_session_model_calls=configured_session_cap(root),
        )
        run_stdio_server(server, root=root)
    except config_loader.ConfigError as exc:
        return report(
            ExitCode.CONFIG,
            "the MCP Q&A server's settings are refused",
            "; ".join(exc.lines),
            "set each key or variable the line names inside its bound",
        )
    return ExitCode.SUCCESS


if __name__ == "__main__":  # pragma: no cover — launched by an MCP client
    finish(main())
