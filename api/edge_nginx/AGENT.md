---
title: api/edge_nginx — agent rules
kind: rules
layer: n/a
status: template
owner: TBD
summary: Local agent rules inside api/edge_nginx/.
id: api-edge-nginx-agent
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Agent rules — `api/edge_nginx/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- Edge config only — TLS, redirects, proxy. No application logic.
- Never commit real certificates or private keys; reference paths only.
- Keep the upstream host/port in sync with how the app transport is run.
