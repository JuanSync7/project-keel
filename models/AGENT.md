---
title: models — agent rules
kind: rules
layer: backend
status: template
owner: TBD
summary: Local agent rules inside models/.
id: models-agent
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Agent rules — `models/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- Every adapter implements the `ModelBackend` contract; callers depend on the contract, never on a concrete provider.
- Selecting/adding a model is a `registry.py` change — agents pick a model by name, never hardcode a provider or launch flag.
- Read secrets (API keys) from the environment, never from `config/` here.
