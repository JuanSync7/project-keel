---
title: API — HTTP/HTTPS edge (nginx)
kind: api
layer: n/a
status: template
owner: TBD
public_api: none
tags: []
summary: Reverse proxy: TLS termination + HTTP->HTTPS in front of the app.
id: api-edge-nginx-readme
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# API — HTTP/HTTPS edge (nginx)

Reverse proxy: TLS termination + HTTP->HTTPS in front of the app.

The HTTP/HTTPS **edge** that sits in front of the transports above:
terminates TLS, forces HTTP->HTTPS, and reverse-proxies to the
FastAPI/uvicorn upstream. This is deployment **config**, not app code
— in production it often lives in `ops/`. Real certs/keys are never
committed (see the placeholder paths).

- `nginx.conf` — HTTP->HTTPS redirect + TLS server + `proxy_pass`.
  A commented `grpc_pass` block shows the gRPC variant.
