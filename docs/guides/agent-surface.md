---
title: Exposing a service as an agent (the agent surface)
kind: doc
layer: n/a
status: template
owner: TBD
tags: [agent, surface, aad, discovery, guide]
summary: When and how to make a service discoverable as an agent — the neutral surface + a wire adapter (AAD).
id: docs-guides-agent-surface
created: 2026-06-18
updated: 2026-06-18
visibility: internal
canonical: true
---

# Exposing a service as an agent (the agent surface)

A chat/agent platform that onboards services wants the inverse of hand-wiring
each one: every service **describes itself**, and the platform connects it from
a single base URL. This template encodes that contract the way it encodes every
integration — **neutral concept first, vendor wiring in a thin adapter.**

## The one rule

| Your service… | Becomes an agent via | Why |
|---------------|----------------------|-----|
| **crosses a process boundary** (its own port/URL) | an **agent surface** (self-describe + ask + health), published in a wire dialect | it already has a network contract; publishing a descriptor is cheap and removes per-agent platform code |
| **is compiled in-process** (a brain the host imports) | nothing — stay an in-process function | there is no URL to discover and no wire to version; adding HTTP would be pure cost |

Do **not** add a network boundary just to be uniform. Uniformity is the
*interface* (card + ask + health), not the *transport*.

## The neutral concept vs the dialect

The **agent surface** is vendor-neutral: a service self-describes (a card:
slug/name/kind/capabilities), answers a question (`ask`), and reports liveness
(`health`). That is the whole concept, stated with no vendor in it.

- **Contract** — [`src/backend/agent_surface/`](../../src/backend/agent_surface/):
  the `AgentSurface` protocol + neutral `AgentCard` / `AgentReply`. No wire
  format, no version envelope, no well-known path. This is what your code
  implements.
- **Dialect (adapter)** — [`api/rest_fastapi/aad/`](../../api/rest_fastapi/aad/):
  **AAD** (Aion Agent Discovery) is *one* wire format that serializes a surface
  — descriptor at `/.well-known/aion-agent.json`, `ask`/`health`, OpenAPI for
  free. It lives in the transport layer, exactly as a model provider lives
  behind `models/`. A second dialect (A2A, an MCP-native descriptor, an
  OpenAI-style plugin manifest) is a **sibling adapter over the same surface**,
  never a change to the contract.
- **Demo** — [`demo/aad_reference_agent/`](../../demo/aad_reference_agent/):
  the copy-paste path — implement a surface, mount the adapter, run.
- **Schema + test** — the committed `config/agent_surface/aad-v1.0.schema.json`
  (generated from the model) and `tests/integration/test_aad_conformance.py`
  (a CI gate proving an agent onboards before it ships).

## Make a service an agent (3 steps)

```python
from backend.agent_surface import AgentCard, AgentReply, AgentSurface
from aad import build_aad_router   # the AAD adapter

class MyService(AgentSurface):
    def card(self):   return AgentCard(slug="my-svc", name="My Service")
    def ask(self, q): return AgentReply(answer=do_real_work(q))
    def health(self): return {"status": "ok"}

app.include_router(build_aad_router(MyService()))   # now discoverable
```

## Versioning

`aad_version` is `MAJOR.MINOR`. A **minor** is additive-only — a reader that
knows an older minor ignores unknown fields, so old descriptors keep onboarding.
A **major** is breaking. A shipped field is never renamed or repurposed. The
committed JSON Schema is generated from the model (`make agent-surface-schema`)
so the published contract can't silently drift from the code.

## Auth

A descriptor declares *that* auth is required (`auth.kind`), **never the
secret** — the secret stays on the consumer side. `auth.kind: none` is a **dev**
default; a production agent must declare real auth before it is exposed. (This
mirrors the upstream auth-before-prod decision the AAD format came from.)

## Out of scope for this template

*Discovering* other agents — fetching arbitrary descriptor URLs, the SSRF/
trusted-host allowlist, redirect refusal, cross-version normalization — is the
**consumer** (platform) side. A template-derived service only **serves** its own
descriptor; do not vendor a discovery client here.
