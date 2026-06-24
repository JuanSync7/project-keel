---
title: Frontend — Astro (showcase site)
kind: package
layer: frontend
status: template
owner: TBD
public_api: src/frontend/astro/src/pages
tags: [showcase, wiki, docs, frontend]
summary: Type-strict Astro 5 + Tailwind v4 docs/wiki site that renders the template live from the backend.
id: src-frontend-astro-readme
created: 2026-06-17
updated: 2026-06-19
visibility: internal
canonical: true
---

# Frontend — Astro (showcase site)

A minimalist, modern documentation/wiki site that **showcases
project_keel as a product** and stays **in sync with the backend**:
it fetches everything (overview, features, the deterministic-check
catalogue, the doc/code corpus) live from the REST API, so when the repo
changes the site reflects it on the next load. See the worked guide:
[`docs/guides/showcase-site.md`](../../../docs/guides/showcase-site.md).

## Run it (front + back, synced)

```bash
make site-data    # build wiki/corpus.json (the data the site reads)
make run-api      # FastAPI on :8000  (project interpreter / venv)
make run-web      # Astro on :4321; proxies /api to the backend
```

Same-origin by default: the client fetches relative `/api` and the dev server
proxies it to the backend, so nothing host-specific is baked into the bundle.
Env knobs — `API_PROXY_TARGET` (proxy destination, default
`http://localhost:8000`), `ASTRO_ALLOWED_HOSTS` (open the dev server by FQDN),
and `PUBLIC_API_BASE` (only to hit a cross-origin API directly, bypassing the
proxy).

## Pages (`src/pages/` — routes)

- `index.astro` — overview: live stats, the load-bearing conventions, layers/transports.
- `features.astro` — the product features.
- `checks.astro` — the deterministic-check catalogue (the "template linter").
- `wiki.astro` — browse the corpus: directory tree, search, node detail (deep-linkable via `?id=`).
- `setup.astro` — "use it in your own project".

## Internals (`src/lib/`)

- `api.ts` — the typed FE↔BE contract (interfaces mirror the backend payload) + fetch client.
- `dom.ts` / `components.ts` — small, XSS-safe client-render helpers (no framework).

- **Type-strict:** extends `astro/tsconfigs/strict`, plus
  `noUncheckedIndexedAccess` / `noImplicitOverride`. Commands:
  `npm run dev | build | preview | lint | typecheck`.
- **Tailwind v4:** via `@tailwindcss/vite`; `@import "tailwindcss"` in `src/styles/global.css`.
- **Client islands are explicit:** the live data fetch is genuine interactivity, done in small `<script>` islands that call `src/lib/api.ts`.
