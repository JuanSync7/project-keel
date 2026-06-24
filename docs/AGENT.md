---
title: docs — agent rules
kind: rules
layer: n/a
status: template
owner: TBD
summary: Local agent rules inside docs/.
id: docs-agent
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Agent rules — `docs/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- Organize by purpose/audience, never by source file — except `reference/`, which may thinly mirror packages.
- ADRs are immutable once accepted: supersede, don't edit.
- Each doc carries frontmatter (`kind: doc|spec|design|adr`).
