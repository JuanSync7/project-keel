---
title: "ADR-0002: A vendor-neutral agent surface, with AAD as the first adapter"
kind: adr
layer: n/a
status: accepted
owner: TBD
tags: [adr, agent, surface, aad, discovery]
summary: Services become discoverable agents via a neutral AgentSurface contract; AAD is one thin wire adapter, not the standard.
id: docs-adr-0002-agent-surface
created: 2026-06-18
updated: 2026-06-18
visibility: internal
canonical: true
---

# ADR-0002: A vendor-neutral agent surface, with AAD as the first adapter

**Status:** accepted

## Context
A chat/agent platform wants to onboard a template-derived service as an agent
from a single base URL, with no per-agent platform code. A proven format for
this exists upstream — the **Aion Agent Descriptor (AAD)**: a service serves a
versioned JSON descriptor at `/.well-known/aion-agent.json`, the platform
fetches it and registers the agent. (Upstream: Aion Chat ADR-0009 defines the
AAD format and its versioning; ADR-0008 makes real auth a prerequisite before
any agent is exposed to production.)

The naïve adoption — "make AAD the standard agent surface of the template" —
**violates this template's cardinal, enforced rule**: *state features
vendor-neutrally; name the neutral concept first; a vendor is one interchangeable
option confined to a thin adapter* (root `AGENT.md`, checked by
`scripts/check_structure.py`). AAD is one vendor's (Aion Chat's) wire dialect.
Baking it in as "the standard" is exactly what `models/` refuses for a model
provider and what triggers refuse for cron-vs-systemd.

## Decision
Adopt the **capability**, invert the **framing**.

1. **Neutral concept = an "agent surface."** A service reachable as an agent
   self-describes (`card`), answers (`ask`), and reports liveness (`health`).
   This is the `AgentSurface` protocol + neutral `AgentCard`/`AgentReply` in
   `src/backend/agent_surface/`. It carries no wire format, version envelope, or
   well-known path. This is the standard.
2. **AAD is the first adapter, in the transport layer.** `api/rest_fastapi/aad/`
   renders any `AgentSurface` into the AAD descriptor + endpoints (FastAPI emits
   `/openapi.json` for free). The vendor name lives only here. A second dialect
   (A2A, MCP-native, plugin manifest) is a sibling adapter over the same
   surface, registered alongside — never an edit to the contract.
3. **Copy-paste demo + CI conformance.** `demo/aad_reference_agent/` is the
   runnable "implement a surface, mount the adapter" path. The committed
   `config/agent_surface/aad-v1.0.schema.json` is **generated** from the model
   (`scripts/agent_surface/generate_aad_schema.py`), and
   `tests/integration/test_aad_conformance.py` proves a service onboards
   (descriptor validates against the committed schema; the `ask` binding
   resolves against the agent's own OpenAPI).
4. **In-process agents stay `function`.** Brains the host imports (no port/URL)
   are not discovered and not given a descriptor — discovery is for
   boundary-crossing services only. The module is opt-in.
5. **Serve, don't discover.** A template service only *serves* its own
   descriptor. The consumer-side discovery stack (URL fetch, SSRF/trusted-host
   allowlist, redirect refusal, version normalization) is the platform's
   concern and is deliberately **not** vendored here.

## Consequences
- Becoming a discoverable agent = implement three methods + mount one router.
  Adding a new wire dialect is a new adapter, not a re-plumb — the neutral
  contract is paid for at N=1 (as `models/` ships one backend behind an ABC).
- The published schema is generated, so the wire contract can't drift from the
  code; a `--check` mode guards it in pre-commit/CI.
- Auth: descriptors declare `auth.kind` only (never the secret). `none` is
  dev-only; production must declare real auth before exposure (per upstream
  ADR-0008).
- The template gains FastAPI/pydantic as the reference adapter's deps — already
  present for `api/rest_fastapi/`. The conformance test degrades gracefully
  where `jsonschema` is absent (structural checks still run).

## Alternatives considered
- **Make AAD the standard (the original proposal).** Rejected: inverts the
  template's enforced vendor-neutrality rule and couples a generic scaffold to
  one platform.
- **Raw OpenAPI as the descriptor, no neutral card.** Rejected: OpenAPI carries
  no card (icon, tagline, capabilities) and no "which field is the answer"
  semantics; you'd need `x-` extensions everywhere.
- **Ship the discovery consumer too.** Rejected as out of scope: a template
  serves a descriptor; it does not fetch others'.
