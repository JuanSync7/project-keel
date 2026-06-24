---
title: Frontend
kind: package
layer: frontend
status: template
owner: TBD
public_api: each app's src/index.ts barrel
tags: []
summary: UI / client code. Two reference apps — keep one, delete the other.
id: src-frontend-readme
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Frontend

UI / client code. Two reference apps — keep one, delete the other.

UI only — no domain/server logic (that lives in `backend/`, shared
contracts in `shared/`). Two complete, type-strict reference apps
ship here; a real project keeps **one** and deletes the other:

| App | Use it for | Stack |
|-----|-----------|-------|
| `react-vite/` | an interactive SPA that talks to `backend/` | Vite + React 19 + TS (strict) + Tailwind v4 + ESLint |
| `astro/` | a content/marketing site, mostly static pages | Astro 5 + TS (strict) + Tailwind v4 + ESLint |

Both are wired to be **type-strict** (`strict` + `noUncheckedIndexedAccess`
+ `exactOptionalPropertyTypes` etc.) and linted with a flat
`eslint.config.js`. The **public-API boundary** is each app's
`src/index.ts` **barrel** — the TS analog of Python's `__init__.py`:
other code imports from the barrel, never from deep paths. The
React app shows importing the FE-side mirror of the backend `shared`
contract (`src/types.ts`).
