---
title: AAD Reference Agent (copy-paste template)
kind: demo
layer: backend
status: template
owner: TBD
public_api: demo/aad_reference_agent/__init__.py
tags: [demo, agent, surface, aad, template]
summary: Runnable example — implement AgentSurface, mount the AAD adapter, become discoverable.
id: demo-aad-reference-agent-readme
created: 2026-06-18
updated: 2026-06-18
visibility: internal
canonical: true
---

# AAD Reference Agent (copy-paste template)

Runnable example — implement AgentSurface, mount the AAD adapter, become discoverable.

The shortest path from "a service" to "a discoverable agent". It implements the
vendor-neutral [`AgentSurface`](../../src/backend/agent_surface/) (three methods:
`card` / `ask` / `health`) and mounts the
[AAD adapter](../../api/rest_fastapi/aad/) — which serves the descriptor, the
`ask`/`health` endpoints, and (via FastAPI) `/openapi.json` for free.

## Run it

```bash
python demo/aad_reference_agent/app.py --host 127.0.0.1 --port 51000
# the descriptor is then served at:
#   GET http://127.0.0.1:51000/.well-known/aion-agent.json
```

A discovery-capable platform onboards it from the base URL alone (e.g. a
`POST /agents/discover {"base_url": "..."}`); no platform-side code per agent.

## Make it yours

1. Edit `EchoSurface.card()` — slug, name, kind, capabilities, example prompts.
2. Replace the body of `EchoSurface.ask()` with real logic (keep returning an
   `AgentReply`).
3. Production auth: pass `auth_kind="api_key"` (etc.) to `build_aad_router`; the
   secret stays on the consumer side, never in the descriptor.
4. Want a different wire dialect later (A2A, a plugin manifest)? Mount a sibling
   adapter over the *same* `EchoSurface` — the surface does not change.

The conformance test (`tests/integration/test_aad_conformance.py`) runs this
agent and asserts its served descriptor validates against the committed schema
and that its `ask` binding resolves against its own `/openapi.json`.
