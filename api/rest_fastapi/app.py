"""
title: REST API (FastAPI)
layer: backend
public_api: no
summary: Thin FastAPI transport over the backend domain; auto OpenAPI.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Transport calls into the domain via the package public API. In an
# installed project (`pip install -e .`) `backend` is importable and this
# sys.path shim goes away.
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from schemas import ThingIn, ThingOut  # noqa: E402

from backend import do_thing  # noqa: E402
from backend.shared import project_identity  # noqa: E402

# Titled after THIS project, read from config/project.json (the manifest check_H
# already keeps true). Not a copier answer: an answer is fixed at generation and
# goes stale on the first rename, and a literal here means every generated project
# serves the template's name — which is what it did.
_NAME, _TITLE = project_identity(str(_ROOT))
app = FastAPI(title="%s API" % _TITLE, version="0.0.0")

# The docs frontend is served from a different origin in dev (Astro on :4321),
# and the showcase endpoints are read-only/public, so allow cross-origin GETs.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Mount the read-only showcase API (overview/features/checks/wiki/search) when this
# project kept the showcase. `copier.yml`'s `showcase` answer prunes the read model
# and this router together, so decide on the FILE's presence rather than catching
# ImportError: a showcase that is present but broken must still fail loudly instead
# of the app quietly starting with fewer routes than it should have.
if (Path(__file__).resolve().parent / "showcase_api.py").is_file():
    from showcase_api import build_showcase_router  # noqa: E402

    app.include_router(build_showcase_router(str(_ROOT)))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/things", response_model=ThingOut)
def create_thing(body: ThingIn) -> ThingOut:
    thing = do_thing(body.name, body.value)  # delegate to the domain
    return ThingOut(name=thing.name, value=thing.value)
