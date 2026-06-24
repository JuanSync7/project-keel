---
title: API — AAD agent-surface adapter
kind: api
layer: backend
status: template
owner: TBD
public_api: api/rest_fastapi/aad/__init__.py
tags: [api, agent, surface, aad, adapter]
summary: Thin FastAPI adapter exposing a neutral AgentSurface over the AAD wire format.
id: api-rest-fastapi-aad-readme
created: 2026-06-18
updated: 2026-06-18
visibility: internal
canonical: true
---

# API — AAD agent-surface adapter

Thin FastAPI adapter exposing a neutral AgentSurface over the AAD wire format.

A FastAPI router that makes any service implementing the vendor-neutral
`AgentSurface` (`src/backend/agent_surface/`) discoverable as an agent over
**AAD** (the Aion Agent Discovery wire format). AAD is ONE dialect of the
agent-surface concept; it lives here, in the transport layer, exactly as a
model provider lives behind `models/`. To add another dialect (A2A, an
MCP-native descriptor, a plugin manifest), drop a sibling router next to this
one — the neutral contract in `src/` does not change.

## Mount it

```python
from backend.agent_surface import AgentSurface   # the neutral contract
from aad import build_aad_router                  # this adapter

app.include_router(build_aad_router(my_surface))
```

## The 4-endpoint contract it serves

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/.well-known/aion-agent.json` | GET | the **AAD descriptor** — card + how to call you (fallback `/aion-agent.json` for servers that can't serve a dot-directory) |
| `/openapi.json` | GET | FastAPI emits this for free; the descriptor's `ask` binds to an `operationId` in it |
| `/ask` | POST | `{question}` → `{answer, meta, html, error}` (field names declared in the descriptor's `io` map) |
| `/health` | GET | liveness |

## Files

- `descriptor.py` — the AAD wire model (`AadDescriptor`) + `card_to_aad`, the
  renderer that maps a neutral `AgentCard` to AAD JSON. The AAD-specific shape
  (version envelope, transport binding, `io` map) is confined here.
- `router.py` — `build_aad_router(surface)`; wires the four endpoints.

## Versioning & auth

`aad_version` is `MAJOR.MINOR`: a new minor is additive-only (older readers
ignore unknown fields); a major is breaking; a shipped field is never mutated.
`auth.kind: none` is a **dev** default — a production agent declares real auth,
and the secret stays on the consumer side (the descriptor only says *that* a
header is needed). See `docs/guides/agent-surface.md` and the ADR.

> Out of scope here: *discovering* others' agents (fetch + SSRF allowlist +
> version normalization). A template service only **serves** its own
> descriptor; the consumer side is the chat platform's concern.
