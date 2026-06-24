---
title: frontend/react-vite — agent rules
kind: rules
layer: frontend
status: template
owner: TBD
summary: Local agent rules inside src/frontend/react-vite/.
id: src-frontend-react-vite-agent
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Agent rules — `src/frontend/react-vite/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- Import the app's public symbols from `src/index.ts`, not deep paths.
- Keep `tsconfig.app.json` strict; fix types rather than loosening flags.
- Components are typed (`interface Props`) and presentational — no domain logic; call the API.
- Style with Tailwind utility classes; don't add a second CSS system.
