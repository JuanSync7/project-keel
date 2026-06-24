---
title: test-docs — agent rules
kind: rules
layer: n/a
status: template
owner: TBD
summary: Local agent rules inside test-docs/.
id: test-docs-agent
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Agent rules — `test-docs/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- Plans describe intent and acceptance criteria; they don't duplicate test code.
- Keep the coverage register in sync when you add/remove scenarios.
- Organize by test level and feature, not by source file.
