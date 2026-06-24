---
title: mcp — agent rules
kind: rules
layer: backend
status: template
owner: TBD
summary: Local agent rules inside mcp/.
id: mcp-agent
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Agent rules — `mcp/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- Keep servers thin: validate + delegate into `src/`/`agents/`. No domain logic.
- Separate Q&A (read-only) from action (state-changing) servers; action defaults to dry-run.
- Every tool gets a schema and a one-line description.
