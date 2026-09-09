---
title: docs — agent rules
kind: rules
layer: n/a
status: template
owner: TBD
summary: Local agent rules inside docs/.
id: docs-agent
created: 2026-06-17
updated: 2026-09-09
visibility: internal
canonical: true
---

# Agent rules — `docs/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- Write to `docs/guides/doc-style.md` — it is canonical for prose here, as `python-style.md` is for code. Read it before writing a document, not after the gate rejects one.
- Organize by purpose/audience, never by source file — except `reference/`, which may thinly mirror packages.
- ADRs are immutable once accepted: supersede, don't edit. A cross-reference inside an accepted ADR may be maintained in a one-clause edit; the decision text may not.
- Each doc carries frontmatter (`kind: doc|spec|design|adr`), and `updated:` means touched — set it to today in the same change (`make check-docs`).
