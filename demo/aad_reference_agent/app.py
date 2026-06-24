"""
title: AAD reference agent
kind: demo
layer: backend
summary: Minimal runnable service that implements AgentSurface and is AAD-discoverable.
"""
from __future__ import annotations

import argparse
import os
import sys

# This demo plays a real consumer: it imports the neutral contract from src/
# and the AAD adapter from api/ via the same path shim the api app uses. A
# real, installed service (`pip install -e .`) drops these two lines.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "src"))
sys.path.insert(0, os.path.join(_ROOT, "api", "rest_fastapi"))

from fastapi import FastAPI  # noqa: E402

from aad import build_aad_router, card_to_aad  # noqa: E402
from backend.agent_surface import (  # noqa: E402
    AgentCard,
    AgentKind,
    AgentReply,
    AgentSurface,
    Capability,
)

__all__ = ["EchoSurface", "build_app", "app", "DESCRIPTOR"]


class EchoSurface(AgentSurface):
    """The whole job of "becoming an agent": implement card/ask/health.

    Swap the body of `ask` for real logic; everything else — the descriptor,
    the wire endpoints, the OpenAPI doc — is supplied by the AAD adapter.
    """

    def card(self) -> AgentCard:
        """Self-describe: the slug/name/kind/capabilities the agents UI renders."""
        return AgentCard(
            slug="aad-reference-agent",
            name="AAD Reference Agent",
            kind=AgentKind.WIKI,
            tagline="A minimal self-describing agent you can copy.",
            description="Template showing the agent-surface + AAD adapter; echoes the question.",
            owner="you@example.com",
            tags=("template", "reference"),
            capabilities=(Capability(command="/ask", title="Ask a question",
                                     arg_hint="<question>"),),
            example_prompts=("ping", "what can you do?"),
        )

    def ask(self, question: str) -> AgentReply:
        """Answer one question. Replace this body with your real logic."""
        answer = ("You asked: %s\n\n(This is the reference agent — replace "
                  "`ask` with real logic.)" % question)
        return AgentReply(answer=answer, meta="turns: 1 · reference",
                          html="<p>%s</p>" % answer)

    def health(self) -> dict:
        """Liveness."""
        return {"status": "ok"}


def build_app() -> FastAPI:
    """Build the FastAPI app: mount the AAD adapter over the EchoSurface."""
    application = FastAPI(title="AAD Reference Agent", version="1.0.0")
    application.include_router(build_aad_router(EchoSurface()))
    return application


# The descriptor this agent serves (handy for tests/inspection); the adapter
# also serves it live at /.well-known/aion-agent.json.
DESCRIPTOR: dict = card_to_aad(EchoSurface().card())
app = build_app()


def main() -> int:
    """Run the agent with uvicorn; then POST /agents/discover its base URL."""
    ap = argparse.ArgumentParser(description="AAD reference agent")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=51000)
    opts = ap.parse_args()
    import uvicorn

    uvicorn.run(app, host=opts.host, port=opts.port)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
