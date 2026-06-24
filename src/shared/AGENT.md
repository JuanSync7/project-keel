---
title: shared — agent rules
kind: rules
layer: shared
status: template
owner: TBD
summary: Local agent rules inside src/shared/.
id: src-shared-agent
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Agent rules — `src/shared/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- This is the FE<->BE data contract (DTOs/enums/error codes), NOT transport (that's `api/`) and NOT generic helpers (that's `util/`).
- Framework-free and dependency-free w.r.t. the rest of `src/`. Other layers import it; it imports nothing here.
- Only put things BOTH frontend and backend need. If only one needs it, it belongs in that layer's own `shared/`.
- Public surface via `__init__.py`/`__all__`.
