---
title: scripts/jobs — agent rules
kind: rules
layer: n/a
status: template
owner: TBD
summary: Local agent rules inside scripts/jobs/.
id: scripts-jobs-agent
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Agent rules — `scripts/jobs/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- A job script is a **doer**, never a schedule. The cadence is a thin, vendor-specific adapter in `ops/scheduled/` — keep the set vendor-agnostic.
- Jobs run unattended: idempotent and safe to re-run; a missed or doubled run must not corrupt state. Exit non-zero on failure so the scheduler alerts.
- LLM-backed jobs stay thin — call an agent in `agents/` (model from `models/`). No reasoning or provider names in the job itself.
