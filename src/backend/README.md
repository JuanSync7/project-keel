---
title: Backend
kind: package
layer: backend
status: template
owner: TBD
public_api: src/backend/__init__.py
tags: []
summary: Server / domain / services.
id: src-backend-readme
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Backend

Server / domain / services.

The worked exemplar of the conventions. Structure:

| Path | Role |
|------|------|
| `__init__.py` | **public API** — the only thing callers import |
| `contracts.py` | ABCs / Protocols (the cross-package interfaces) |
| `example_feature/` | a sample feature package (rename me) |
| `shared/` | domain-shared types/models |
| `util/` | generic, domain-agnostic helpers |

Note how `example_feature/__init__.py` re-exports `do_thing` and
`Thing` and hides `_impl.py`. Callers do
`from backend import do_thing` — never `from backend.example_feature._impl import ...`.
