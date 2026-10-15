---
title: Frontend — React + Vite
kind: package
layer: frontend
status: template
owner: TBD
public_api: src/frontend/react-vite/src/index.ts
tags: []
summary: Type-strict Vite + React 19 + Tailwind v4 + ESLint SPA.
id: src-frontend-react-vite-readme
created: 2026-06-17
updated: 2026-10-15
visibility: internal
canonical: true
---

# Frontend — React + Vite

Type-strict Vite + React 19 + Tailwind v4 + ESLint SPA.

Interactive SPA that talks to `backend/`. Commands: `npm run dev`
(Vite dev server), `npm run build` (`tsc -b && vite build`),
`npm run lint`, `npm run typecheck`, `npm run test:unit` (Vitest over
`src/**/*.test.{ts,tsx}`), `npm run test:e2e` (builds the app, serves it with
`vite preview` and clicks the counter in headless chromium, `e2e/counter.spec.ts`),
`npm run test:e2e:browsers` (downloads the chromium `test:e2e` drives; run it
once before the journey, or `make fe-browsers` for every app).
Both test scripts fail on zero tests.

- **Boundary:** `src/index.ts` re-exports the app's public surface;
  `src/main.tsx` mounts via that barrel.
- **Contract:** `src/types.ts` mirrors the backend `shared` contract
  (`Thing`). Generate these from the contract/OpenAPI in a real app.
- **Type-strict:** see `tsconfig.app.json`.
- **Lint:** flat `eslint.config.js` with `typescript-eslint`
  `strictTypeChecked` + React Hooks rules.
- **Tailwind v4:** via `@tailwindcss/vite`; `@import "tailwindcss"`
  in `src/index.css`.
