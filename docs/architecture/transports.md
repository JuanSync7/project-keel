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
updated: 2026-06-17
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

## The contract is single-sourced
HTTP DTOs (`schemas.py`) and proto messages (`thing.proto`) **mirror**
`src/shared/`. Don't redefine the contract per transport — generate or
derive it, and keep the OpenAPI doc / `.proto` checked in and in sync.
