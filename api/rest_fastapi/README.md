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
updated: 2026-10-23
visibility: internal
canonical: true
---

# API — REST (FastAPI)

Thin FastAPI REST transport; auto-generates the OpenAPI contract.

A FastAPI app that exposes the domain over REST and auto-generates
the OpenAPI document. Run: `pip install -r requirements.txt` then
`python3 serve.py --port 8000 --reload` (what `make run-api` runs); docs at
`/docs`. In a checkout, the project's
`transport` extra holds the same packages and `pip install -e ".[dev]"` brings
it; `make check-venv` fails a venv without them, and
tests/unit/scripts/test_check_venv.py holds the extra and `requirements.txt`
equal.

- `app.py` — routes; each calls `backend.do_thing` (thin).
- `schemas.py` — Pydantic HTTP DTOs that MIRROR `src/shared/`.
- `openapi.json` — checked-in contract snapshot.
- `export_openapi.py` — regenerates `openapi.json` from the app.
- `serve.py` — the server entry: caps the process's memory and owns its stop
  signals through `scripts/resource_limits.py`, so SIGTERM drains the calls in
  flight for config/project.json `transports.serve.shutdown_grace_seconds` and
  exits 0.
- `aad/` — optional **agent-surface adapter**: exposes a neutral
  `AgentSurface` (`src/backend/agent_surface/`) as a discoverable agent over
  the AAD wire format (one dialect; see `docs/guides/agent-surface.md`).
