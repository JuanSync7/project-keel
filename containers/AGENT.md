---
title: containers — agent rules
kind: rules
layer: n/a
status: template
owner: TBD
summary: Local agent rules inside containers/.
id: containers-agent
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Agent rules — `containers/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- Images install the package; don't copy source ad-hoc.
- Pin base images; keep build context small.
