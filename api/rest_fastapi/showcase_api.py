"""
title: Showcase REST routes
layer: backend
public_api: no
summary: Thin FastAPI router exposing backend.showcase as JSON + the agent llms.txt files.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Query, Response

from backend.showcase import load_showcase, to_jsonable

_MD = "text/markdown; charset=utf-8"


def build_showcase_router(root: str) -> APIRouter:
    """Return a router that serves the live showcase read model.

    Thin transport only (api/ rules): every handler validates input, calls into
    ``backend.showcase``, and shapes the response. The model is reloaded whenever
    config/project.json or wiki/corpus.json changes on disk, so both the human
    wiki (/api/*) and the agent front door (/llms.txt) stay in sync with the repo.
    """
    router = APIRouter()
    _watched = (os.path.join(root, "config", "project.json"),
                os.path.join(root, "wiki", "corpus.json"))
    _cache: dict = {}

    def current():
        sig = tuple(os.path.getmtime(f) if os.path.exists(f) else 0.0
                    for f in _watched)
        if _cache.get("sig") != sig:
            _cache["sig"] = sig
            _cache["showcase"] = load_showcase(root)
        return _cache["showcase"]

    # -- human/agent JSON API ------------------------------------------------
    @router.get("/api/overview")
    def overview():
        return to_jsonable(current().overview())

    @router.get("/api/features")
    def features():
        return to_jsonable(list(current().features()))

    @router.get("/api/principles")
    def principles():
        return to_jsonable(list(current().principles()))

    @router.get("/api/models")
    def models():
        return to_jsonable(list(current().model_adapters()))

    @router.get("/api/checks")
    def checks():
        return to_jsonable(list(current().checks()))

    @router.get("/api/setup")
    def setup():
        return to_jsonable(list(current().setup_steps()))

    @router.get("/api/wiki/tree")
    def wiki_tree():
        return to_jsonable(list(current().doc_tree()))

    @router.get("/api/wiki/node")
    def wiki_node(id: str = Query(..., description="corpus node_id")):
        sc = current()
        detail = sc.node(id)
        if detail is None:
            raise HTTPException(status_code=404, detail="unknown node %r" % id)
        payload = to_jsonable(detail)
        payload["markdown"] = sc.markdown(id)   # renderable body, live from the file
        return payload

    @router.get("/api/search")
    def search(q: str = Query("", description="free-text query"),
               limit: int = Query(10, ge=1, le=50)):
        return to_jsonable(list(current().search(q, limit)))

    # -- agent front door (llms.txt convention), served at the site root -----
    @router.get("/llms.txt")
    def llms_txt():
        return Response(current().llms_index(), media_type=_MD)

    @router.get("/llms-full.txt")
    def llms_full_txt():
        return Response(current().llms_full(), media_type=_MD)

    return router


__all__ = ["build_showcase_router"]
