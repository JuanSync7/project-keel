---
title: api/grpc — agent rules
kind: rules
layer: backend
status: template
owner: TBD
summary: Local agent rules inside api/grpc/.
id: api-grpc-agent
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Agent rules — `api/grpc/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- The `.proto` is the contract — edit it first, regenerate stubs (`make gen`), keep messages mirroring `src/shared/`.
- Servicers are thin: unpack request -> call `src/` -> pack response.
- Generated `*_pb2.py` are build artifacts — don't hand-edit; gitignore them or generate in CI.
