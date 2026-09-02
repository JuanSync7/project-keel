---
title: API transports
kind: doc
layer: n/a
status: template
owner: TBD
tags: [api, transport, architecture]
summary: How clients reach the domain: the edge + transport layers in api/.
id: docs-architecture-transports
created: 2026-06-17
updated: 2026-09-02
visibility: internal
canonical: true
---
# API transports

Clients never touch the domain directly. Requests flow inward through
thin layers; only `src/` holds business logic.

```
client ──HTTP/HTTPS──> edge (nginx)  ──> transport ──> src/ (domain)
                       TLS, redirect       │
                                           ├─ REST/OpenAPI  (api/rest_fastapi)
                                           └─ gRPC          (api/grpc)
```

| Layer | Lives in | Responsibility | Must NOT |
|-------|----------|----------------|----------|
| Edge | `api/edge_nginx/` (or `ops/`) | TLS termination, HTTP->HTTPS, reverse proxy | hold app logic |
| Transport | `api/rest_fastapi/`, `api/grpc/` | (de)serialize the wire, validate, delegate | hold domain logic |
| Domain | `src/` | the actual behavior | know about HTTP/gRPC |

## Choosing a transport
- **REST + OpenAPI (FastAPI)** — public/3rd-party HTTP clients, browsers,
  self-documenting JSON. The default.
- **gRPC** — service-to-service, low latency, streaming, strict schemas.
- **GraphQL / WebSockets / queues** — add a sibling `api/<style>/`
  following the same thin-over-`src/` rule.

## At generation time
`copier` (ADR 0004) tailors which transports a new project ships. **REST + MCP are
the always-shipped foundation** — the skeleton's own `/things` route, the AAD
reference implementation and the MCP servers all run on them. The bundled showcase
also mounts a router here, but it is a *tenant*, not a reason: the `showcase`
question (ADR 0007) prunes that router and its read model while REST stays, and
`api/rest_fastapi/app.py` mounts it only when the file is present. The
**add-ons `grpc` and `edge_nginx`** are self-contained
(no code/test imports them), so the `transports` question keeps each only when
selected and drops it — along with its `transports.available` entry — otherwise.
`config/project.json` `transports.enabled`/`available` are rendered to match, so
`check_H` stays green with no undeclared `api/` dir.

## The contract is single-sourced
HTTP DTOs (`schemas.py`) and proto messages (`thing.proto`) **mirror**
`src/shared/`. Don't redefine the contract per transport — generate or
derive it, and keep the OpenAPI doc / `.proto` checked in and in sync.
