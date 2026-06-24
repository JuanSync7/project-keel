---
title: Source
kind: package
layer: n/a
status: template
owner: TBD
public_api: none
tags: []
summary: All production source, split by layer.
id: src-readme
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Source

All production source, split by layer.

Layers (see `CONVENTIONS.md`):

- `frontend/` — UI / client.
- `backend/` — server, domain, services.
- `shared/` — contracts/types used by both FE and BE.
- `app/` — composition root: entrypoints, wiring, CLI/`__main__`.

Dependency direction: `app/` → (`frontend/`, `backend/`) → `shared/`.
`shared/` depends on nothing else here. `frontend/` and `backend/`
never import each other directly — they meet through `shared/`
contracts and the `app/` wiring.
