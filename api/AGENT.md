---
title: api — agent rules
kind: rules
layer: backend
status: template
owner: TBD
summary: Local agent rules inside api/.
id: api-agent
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Agent rules — `api/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- Every transport is a thin adapter over `src/`; no domain logic in routes/handlers/servicers.
- HTTP DTOs / proto messages MIRROR `src/shared/`; keep one source of truth, don't redefine the contract per transport.
- Treat the OpenAPI doc and the `.proto` as contracts: keep them checked in and in sync; version them; don't break clients silently.
- `edge_nginx/` holds edge config only (TLS, proxy) — no app logic; never commit real certs/keys.
