---
title: backend — agent rules
kind: rules
layer: backend
status: template
owner: TBD
summary: Local agent rules inside src/backend/.
id: src-backend-agent
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Agent rules — `src/backend/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- The public API is `__init__.py`/`__all__`. Implementation lives in `_*` modules and is never imported across package boundaries.
- Define interfaces as ABCs/Protocols in `contracts.py`; depend on the contract, not the concrete class. Add new ABCs here, not inline.
- No transport concerns (HTTP/MCP/CLI) in here — those live in `api/`, `mcp/`, `app/` and call into this package.
