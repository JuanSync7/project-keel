---
title: demo/aad_reference_agent — agent rules
kind: rules
layer: backend
status: template
owner: TBD
summary: Local agent rules inside demo/aad_reference_agent/.
id: demo-aad-reference-agent-agent
created: 2026-06-18
updated: 2026-06-18
visibility: internal
canonical: true
---

# Agent rules — `demo/aad_reference_agent/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- This is a runnable demo, not the adapter: keep it thin. Implement `AgentSurface` and mount `build_aad_router`; do not reimplement the AAD wire shape here.
- Keep it runnable with no deps beyond FastAPI/uvicorn (already in `api/rest_fastapi/requirements.txt`). A broken demo is a bug.
- Keep the served descriptor conformant: the `slug` must match `[a-z0-9][a-z0-9-]{0,63}`, and the `ask` binding must resolve in the app's own `/openapi.json`. The conformance test enforces both — keep it passing.
- `auth.kind: none` here is dev-only; never present this demo as a production-ready default.
