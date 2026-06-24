---
title: Shared (the FE<->BE contract)
kind: package
layer: shared
status: template
owner: TBD
public_api: src/shared/__init__.py
tags: []
summary: The data contract both frontend and backend agree on.
id: src-shared-readme
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Shared (the FE<->BE contract)

The data contract both frontend and backend agree on.

This is the **contract between frontend and backend** — the shapes
both sides must agree on: DTOs / request-response models, enums,
error codes, validation rules. It is the *vocabulary*, not the wire.

Distinguish carefully:

- `shared/` (here) — the agreed **data shapes**. "A Thing has
  `{name, value}`." Framework-free.
- `api/` (top-level) — the **transport** that carries those shapes
  over HTTP. Imports `shared/`; `shared/` never imports it.
- `util/` — generic helpers with no domain meaning. Not this.

Must not import from `frontend/`, `backend/`, `app/`, or any
framework. Both sides depend on it; it depends on nothing in `src/`.
