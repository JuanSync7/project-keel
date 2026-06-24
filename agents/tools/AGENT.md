---
title: agents/tools — agent rules
kind: rules
layer: cross-cutting
status: template
owner: TBD
summary: Local agent rules inside agents/tools/.
id: agents-tools-agent
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Agent rules — `agents/tools/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- A `*.tool.md` is a **thin adapter**: it documents how to invoke a `scripts/` doer. Never put tool logic here — it belongs in the script.
- Frontmatter is governed: `kind: tool`, a real `owner` (not `TBD`), a `public_api` that resolves to the wrapped script, and a valid `tool_effect`.
- Keep `tool_command` consistent with `public_api`, and `## Used by` in sync with each agent's `tools.md` (the binding is bidirectional).
- Specs are vendor-agnostic: describe the tool so any agent/LLM can use it; never name a provider.
