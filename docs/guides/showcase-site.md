---
title: The showcase site (product demo, synced front-to-back)
kind: doc
layer: n/a
status: template
owner: TBD
tags: [showcase, demo, frontend, astro, fastapi, wiki, guide]
summary: How the docs/wiki frontend presents the template as a product and stays in sync with the backend.
id: docs-guides-showcase-site
created: 2026-06-19
updated: 2026-06-19
visibility: internal
canonical: true
---

# The showcase site (product demo)

The repository ships a small **product demo**: a minimalist, modern
documentation/wiki site that presents project_keel as a product —
its features, its deterministic checks, and a browsable index of every
doc, module, config, and script in the repo. It is deliberately built the
way the template tells you to build things: **a thin frontend over a thin
transport over a domain package**, with the contract stated once.

## What it shows

- **Overview** — the pitch, live headline counts (docs / modules / sections
  / symbols / dirs / checks), the three load-bearing conventions, and the
  layers/transports straight from `config/project.json`.
- **Features** — what the template gives you.
- **Checks** — the deterministic-check catalogue (the "template linter";
  see [`deterministic-checks.md`](deterministic-checks.md)), each with its
  gate, interpreter, command, and whether the script is present on disk.
- **Wiki** — the one-brain corpus (`wiki/corpus.json`) as a browsable tree
  with search and per-node detail (parent / sections / related), deep-linkable.
- **Use it** — the setup steps for your own project.

## How it stays synced (front ↔ back)

```
Astro pages ──fetch──▶ FastAPI /api/* ──▶ backend.showcase ──reads──▶ config/project.json
 (src/frontend/astro)   (api/rest_fastapi)   (src/backend/showcase)        wiki/corpus.json
```

1. **Domain** — `src/backend/showcase/` is a pure read model that loads the
   live `config/project.json` and `wiki/corpus.json` and exposes overview,
   features, the check catalogue, the corpus tree, node detail, and search as
   framework-free value objects.
2. **Transport** — `api/rest_fastapi/showcase_api.py` is a thin router under
   `/api` that calls the domain and serialises the result. It **reloads the
   model when `project.json` or `corpus.json` changes on disk**, so a rebuilt
   corpus is served without a restart.
3. **Frontend** — `src/frontend/astro/` fetches *relative* `/api/*` at runtime
   via the typed client in `src/lib/api.ts`; the dev server's proxy
   (`astro.config.mjs`) forwards those to the backend, so the browser talks to
   one origin and no host:port is hardcoded in the bundle. A badge pings `/health`.

So the loop is real: change a doc → `make site-data` (rebuild the corpus) →
reload the page → the wiki, counts, and search reflect it. No frontend rebuild.

## Agent front door (`llms.txt`)

The same backend serves the **agent-facing** projection at the site root, following
the [`llms.txt` convention](https://llmstxt.org):

- **`/llms.txt`** — a curated map: an H1 + summary, then the corpus docs grouped by
  directory as markdown link lists (the agent reads this first).
- **`/llms-full.txt`** — every document's body inlined, so an agent can ingest the
  whole corpus in one fetch.

Both are rendered from the same corpus the wiki uses (`backend.showcase.llms_index`
/ `llms_full`), served live, and also written to `wiki/llms.txt` /
`wiki/llms-full.txt` by `make site-data` (job: `scripts/jobs/build_llms_txt.py`) for
static hosting. This is the "build the wiki for humans **and** agents" split: the
Astro pages are the human projection; `llms.txt` + the `/api/*` JSON + `corpus.json`
are the agent projection of the one source.

## Run it

```bash
make site-data    # build wiki/corpus.json (the data the site reads)
make run-api      # FastAPI on :8000  (run under the project interpreter / venv)
make run-web      # Astro dev on :4321; proxies /api to the backend
```

**Same-origin by default — nothing host-specific is baked in.** The client
fetches *relative* `/api/...`, and the dev server proxies those to the backend,
so the browser only ever talks to the Astro origin (no cross-port/CORS/firewall
surprises). The knobs, all via the environment:

- `API_PROXY_TARGET` — where the dev server forwards `/api` and `/health`
  (default `http://localhost:8000`). For the ports used above: `API_PROXY_TARGET=http://127.0.0.1:50004`.
- `ASTRO_ALLOWED_HOSTS` — comma-separated hostnames allowed to reach the dev
  server (or `true` for any); needed to open it by FQDN rather than localhost.
- `PUBLIC_API_BASE` — set this only to point the browser *directly* at a
  cross-origin API (bypassing the proxy); leave unset for same-origin.

## Deploy it statically (GitHub Pages)

GitHub Pages can't run the FastAPI backend, so the site ships in a **static
mode**: a build step snapshots the *same* read model the API serves into static
JSON, and the frontend reads those files instead of a live backend.

- **Snapshot** — `scripts/jobs/export_showcase_static.py` (run via `make
  site-static`) calls `load_showcase()` — the exact domain the REST router uses —
  and writes `src/frontend/astro/public/api/*.json`, a `wiki/nodes.json` (every
  node + rendered markdown, fetched once and cached — one corpus-bounded file),
  plus `llms.txt` + `llms-full.txt`. One source of truth; no logic duplicated.
- **Frontend** — `src/frontend/astro/src/lib/api.ts` has two modes: *live*
  (default; fetch `/api/*`) and *static* (`PUBLIC_DATA_MODE=static`; read the
  snapshot under the site base). Search runs client-side over `nodes.json` (a
  reduced mirror of the API's keyword search — the live API does full corpus-graph
  ranking). Internal links go through `lib/links.ts` `withBase()` so they work
  under a project-page base.
- **Base path** — a project site serves at `/<repo>/`, so the build needs
  `PUBLIC_BASE_PATH=/<repo>`, and the export's `--base-url` (Makefile `BASE_URL`)
  **must match it** so the `llms.txt` links resolve. The workflow derives both
  from the repo name; a user/org page (`<name>.github.io`) or a committed
  `public/CNAME` (a UI-set custom domain needs the file committed too) deploys at
  the root.
- **Trigger** — `.github/workflows/pages.yml` builds the corpus, exports the
  snapshot, runs `npm run build` in static mode, and deploys. It's a thin
  vendor adapter (the doers are the `scripts/jobs/` jobs + Astro).

One-time: repo **Settings → Pages → Source = "GitHub Actions"**. Build locally
with `make site-static BASE_URL=/<repo>` then
`PUBLIC_DATA_MODE=static PUBLIC_BASE_PATH=/<repo> npm --prefix src/frontend/astro run build`.
(`make site-static` outputs are gitignored — regenerated on each build.)

## Why this layout (and not a monolith)

The demo obeys the same rules it documents: the frontend holds **no business
logic** (it renders API results), the transport stays **thin** (no domain
logic in handlers), and the FE↔BE contract is **stated once** — Python value
objects in `src/backend/showcase/`, mirrored by TypeScript interfaces in
`src/frontend/astro/src/lib/api.ts`. Swapping Astro for another framework, or
REST for another transport, is a new thin adapter, not a rewrite.

## Tests

- `tests/unit/backend/test_showcase.py` — the read model, in-memory (no disk).
- `tests/integration/test_showcase_repo.py` — `load_showcase` over the real repo.
- `tests/integration/test_showcase_api.py` — the REST router via `TestClient`.
