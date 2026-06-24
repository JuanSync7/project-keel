---
title: config — agent rules
kind: rules
layer: n/a
status: template
owner: TBD
summary: Local agent rules inside config/.
id: config-agent
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Agent rules — `config/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- Never commit secrets — only defaults and `*.example.*`.
- Config is data, not code; the `app/` layer reads it, the domain layers receive values via injection.
