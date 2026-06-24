---
title: frontend — agent rules
kind: rules
layer: frontend
status: template
owner: TBD
summary: Local agent rules inside src/frontend/.
id: src-frontend-agent
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Agent rules — `src/frontend/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- No business rules here — call the backend/API; render results.
- Each app's public surface is its `src/index.ts` barrel (the `__init__.py` analog). Import from the barrel, never deep paths.
- Keep TypeScript strict: do not weaken `tsconfig` (`strict`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`) to silence errors — fix the types.
- FE types that mirror the backend `shared` contract should be generated from it (or OpenAPI), not hand-drifted. One source of truth.
- A real project keeps ONE of `react-vite/` / `astro/`; delete the other.
