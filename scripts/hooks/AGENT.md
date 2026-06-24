---
title: scripts/hooks — agent rules
kind: rules
layer: n/a
status: template
owner: TBD
summary: Local agent rules inside scripts/hooks/.
id: scripts-hooks-agent
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Agent rules — `scripts/hooks/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- A hook script is a **doer**, never a trigger. The trigger (which event fires it) is a thin, vendor-specific adapter in that ecosystem's config — keep it out of here and vendor-agnostic across the set.
- Hooks fire unattended, possibly on every edit/commit: be fast, idempotent, safe to run twice; never assume an interactive terminal.
- LLM-backed hooks stay thin — call an agent in `agents/` (model from `models/`). No reasoning or provider names in the hook itself.
