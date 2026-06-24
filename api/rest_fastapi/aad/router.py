"""
title: AAD FastAPI router
layer: backend
public_api: yes
summary: Mount any AgentSurface as an AAD-discoverable agent (descriptor + ask + health).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .descriptor import card_to_aad

if TYPE_CHECKING:
    from backend.agent_surface import AgentSurface

__all__ = ["build_aad_router"]


class _AskBody(BaseModel):
    """Request body for the AAD ask endpoint (the `io.question` field)."""

    question: str


def build_aad_router(surface: AgentSurface, *, ask_path: str = "/ask",
                     health_path: str = "/health",
                     auth_kind: str = "none") -> APIRouter:
    """Return a FastAPI router that exposes ``surface`` over the AAD wire contract.

    Wires the four AAD endpoints by adapting the neutral ``AgentSurface``:
    the well-known descriptor (+ the dot-less ``/aion-agent.json`` fallback for
    servers that can't serve a dot-directory), ``POST`` ask, and ``GET`` health.
    ``/openapi.json`` is emitted by FastAPI itself, so the descriptor's ``ask``
    operationId resolves against the app's own generated spec — no hand-written
    OpenAPI. Mount with ``app.include_router(build_aad_router(MySurface()))``.

    The vendor (AAD) shape is confined to this adapter; the surface stays
    neutral, so a second dialect is a sibling router, not a change here.
    """
    router = APIRouter()
    descriptor = card_to_aad(surface.card(), ask_operation_id="ask",
                             health_path=health_path, auth_kind=auth_kind)

    @router.get("/.well-known/aion-agent.json")
    def aad_descriptor() -> JSONResponse:
        return JSONResponse(descriptor)

    # RFC 8615 dot-directory fallback: some servers (e.g. Astro file-routing)
    # cannot serve `/.well-known/...`; the consumer tries this path next.
    @router.get("/aion-agent.json")
    def aad_descriptor_fallback() -> JSONResponse:
        return JSONResponse(descriptor)

    @router.post(ask_path, operation_id="ask")
    def ask(body: _AskBody) -> dict:
        reply = surface.ask(body.question)
        return {"answer": reply.answer, "meta": reply.meta,
                "html": reply.html, "error": reply.error}

    @router.get(health_path)
    def health() -> dict:
        return surface.health()

    return router
