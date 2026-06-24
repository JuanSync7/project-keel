---
title: agents — agent rules
kind: rules
layer: backend
status: template
owner: TBD
summary: Local agent rules inside agents/.
id: agents-agent
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Agent rules — `agents/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- Agents hold reasoning/policy/prompts only; they call `src/` for domain work and never embed transport code.
- Get the model from `models/` (`get_model`), never hardcode a provider or model id in the agent.
- State-changing actions default to dry-run; require explicit authorization to execute.
- Expose agents to the world via `mcp/` or `api/`, not by importing transport here.
