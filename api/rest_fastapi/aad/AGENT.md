---
title: api/rest_fastapi/aad — agent rules
kind: rules
layer: backend
status: template
owner: TBD
summary: Local agent rules inside api/rest_fastapi/aad/.
id: api-rest-fastapi-aad-agent
created: 2026-06-18
updated: 2026-06-18
visibility: internal
canonical: true
---

# Agent rules — `api/rest_fastapi/aad/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- Thin adapter only: map a neutral `AgentSurface` (from `backend.agent_surface`) onto the AAD wire shape. No domain logic or business state here.
- The vendor (AAD) lives ONLY here. The neutral contract in `src/backend/agent_surface/` must never import or name AAD; a second dialect is a sibling adapter, not an edit to the contract.
- `auth.kind: none` is a DEV default; a production descriptor must declare real auth, and the secret stays consumer-side, never in the descriptor.
- The committed schema (`config/agent_surface/aad-v1.0.schema.json`) is generated from `AadDescriptor` — regenerate it (`make agent-surface-schema`) when the model changes; never hand-edit it.
