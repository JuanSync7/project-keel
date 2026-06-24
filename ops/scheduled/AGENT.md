---
title: ops/scheduled — agent rules
kind: rules
layer: n/a
status: template
owner: TBD
summary: Local agent rules inside ops/scheduled/.
id: ops-scheduled-agent
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Agent rules — `ops/scheduled/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- Thin **schedule adapters** (the cadence) only — the doer lives in `scripts/jobs/`. No app logic here.
- Keep the set vendor-agnostic: a new scheduler is a new thin file pointing at the same job, never a fork of the job.
- Examples only in the repo (`*.example`); real schedules carry environment-specific paths/users and are deployed, not committed.
