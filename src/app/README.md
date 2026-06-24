---
title: App (composition root) — OPTIONAL
kind: package
layer: app
status: template
owner: TBD
public_api: src/app/__init__.py
tags: []
summary: OPTIONAL single-process composition root. Delete it for client-server web apps.
id: src-app-readme
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# App (composition root) — OPTIONAL

OPTIONAL single-process composition root. Delete it for client-server web apps.

**Optional. Keep it only if one process wires the layers together.**

`app/` is a *composition root*: dependency injection, config loading,
CLI/`__main__`, server bootstrap. **No business logic** — it only
wires `backend`/`frontend`/`shared` and starts them.

Two archetypes decide whether you need it:

| Project | Entrypoint | Keep `app/`? |
|---------|-----------|--------------|
| **Client-server web** (separate FE build + BE server) | FE = its own build; BE = its server (`api/`/`backend/`) | **No** — nothing imports both in one process. Delete this dir. |
| **Single-process** (CLI, service, library) | one `__main__`/`bin` that wires everything | **Yes** — that wiring *is* this dir. |

genbuild is the single-process kind (a CLI, no `frontend/`), so it
has an `app/`-equivalent in `bin/`. A React+API product is the first
kind, so it has no `app/`. `make run` calls `python -m app`.
