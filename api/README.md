---
title: Api
kind: api
layer: backend
status: template
owner: TBD
public_api: none
tags: []
summary: API transports over the domain — REST/OpenAPI (FastAPI), gRPC, and the nginx edge. All thin over src/.
id: api-readme
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Api

API transports over the domain — REST/OpenAPI (FastAPI), gRPC, and the nginx edge. All thin over src/.

The network surface. Every transport here is a **thin adapter** that
translates a wire protocol into calls on the `src/` public API; the
request/response shapes mirror `src/shared/` (the contract), never
redefined. Pick the transport(s) you need:

| Subdir | Style | Use it for |
|--------|-------|-----------|
| `rest_fastapi/` | REST + auto OpenAPI (FastAPI/ASGI) | browser/3rd-party HTTP clients; self-documenting JSON API |
| `grpc/` | gRPC (HTTP/2 + protobuf) | low-latency service-to-service, streaming, strict schemas |
| `edge_nginx/` | HTTP/HTTPS reverse proxy | TLS termination + HTTP->HTTPS in front of the app |

REST *is* the RESTful example (FastAPI generates the OpenAPI doc).
For others not scaffolded — GraphQL, WebSockets, message queues —
add a sibling subdir following the same thin-over-`src/` rule.
`edge_nginx/` is edge **config**, not app code; in production it
often lives in `ops/`.
