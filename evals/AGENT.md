---
title: evals — agent rules
kind: rules
layer: n/a
status: template
owner: TBD
summary: Local agent rules inside evals/.
id: evals-agent
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Agent rules — `evals/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- Evals score quality on a dataset; they are not pass/fail unit tests — keep them out of `tests/`.
- Version datasets and record metrics over time.
