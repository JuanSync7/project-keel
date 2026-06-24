---
title: api/rest_fastapi — agent rules
kind: rules
layer: backend
status: template
owner: TBD
summary: Local agent rules inside api/rest_fastapi/.
id: api-rest-fastapi-agent
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Agent rules — `api/rest_fastapi/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- Routes are thin: validate -> call `src/` -> shape response. No domain logic in handlers.
- Pydantic schemas mirror `src/shared/`; regenerate `openapi.json` (`python export_openapi.py`) whenever routes change.
- Version the path/prefix; don't break published routes silently.
