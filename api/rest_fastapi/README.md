---
title: API — REST (FastAPI)
kind: api
layer: backend
status: template
owner: TBD
public_api: api/rest_fastapi/openapi.json
tags: []
summary: Thin FastAPI REST transport; auto-generates the OpenAPI contract.
id: api-rest-fastapi-readme
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# API — REST (FastAPI)

Thin FastAPI REST transport; auto-generates the OpenAPI contract.

A FastAPI app that exposes the domain over REST and auto-generates
the OpenAPI document. Run: `pip install -r requirements.txt` then
`uvicorn app:app --reload`; docs at `/docs`.

- `app.py` — routes; each calls `backend.do_thing` (thin).
- `schemas.py` — Pydantic HTTP DTOs that MIRROR `src/shared/`.
- `openapi.json` — checked-in contract snapshot.
- `export_openapi.py` — regenerates `openapi.json` from the app.
- `aad/` — optional **agent-surface adapter**: exposes a neutral
  `AgentSurface` (`src/backend/agent_surface/`) as a discoverable agent over
  the AAD wire format (one dialect; see `docs/guides/agent-surface.md`).
