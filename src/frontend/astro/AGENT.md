---
title: frontend/astro — agent rules
kind: rules
layer: frontend
status: template
owner: TBD
summary: Local agent rules inside src/frontend/astro/.
id: src-frontend-astro-agent
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Agent rules — `src/frontend/astro/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- Pages in `src/pages/` are routes — keep them thin; push markup into `src/components/` and `src/layouts/`.
- Keep it static-first: no client JS unless a component genuinely needs interactivity (then use an island explicitly).
- Keep TS strict (`astro/tsconfigs/strict`); type `Astro.props` via a `Props` interface in each component.
- Style with Tailwind utilities; global CSS only imports Tailwind.
