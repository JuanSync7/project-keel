---
title: ops — agent rules
kind: rules
layer: n/a
status: template
owner: TBD
summary: Local agent rules inside ops/.
id: ops-agent
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Agent rules — `ops/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- Infra and runbooks only — no app logic.
- Runbooks are kept current with reality; stale runbooks are incidents waiting to happen.
