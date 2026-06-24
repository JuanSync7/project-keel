---
title: app — agent rules
kind: rules
layer: app
status: template
owner: TBD
summary: Local agent rules inside src/app/.
id: src-app-agent
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Agent rules — `src/app/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- OPTIONAL. If frontend and backend are separate deployables (client-server web), there is no single-process root — delete this dir.
- Wiring only — construct concretes, inject them via `contracts`, start the process. No domain logic.
- This is the ONLY layer allowed to import from both `frontend` and `backend`.
- Read config from `config/`; never hardcode environment specifics.
