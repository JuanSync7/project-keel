---
title: tmp — agent rules
kind: rules
layer: n/a
status: draft
owner: TBD
summary: Local agent rules inside tmp/.
id: tmp-agent
created: 2026-08-06
updated: 2026-08-06
visibility: internal
canonical: false
---

# Agent rules — `tmp/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- Scratch only. Nothing here is a source of truth — `docs/` and the gate are. Re-derive from the repo before trusting a note here, and correct or delete it when it turns out to be stale.
- No code, no fixtures, no configuration anything else reads. A file here must be safe to delete at any moment.
- Say what is *in flight*, not what is settled. Anything durable belongs in `docs/` (a design doc, an ADR, or a guide) — write it there and link, rather than growing a second history here.
