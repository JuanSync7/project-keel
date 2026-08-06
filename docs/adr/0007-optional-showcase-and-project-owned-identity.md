---
title: "ADR-0007: Make the bundled showcase optional, and derive the project's identity from its manifest, amending ADR-0004"
kind: adr
layer: n/a
status: accepted
owner: TBD
tags: [adr, template, copier, showcase, branding, identity, manifest]
summary: "The showcase demo was 84% of a generated project's Python with no way to decline it, and the running app served the template's own name; keel adds a `showcase` answer that prunes and retires the whole demo surface, and reads its display title from config/project.json instead of hardcoding it."
id: docs-adr-0007-optional-showcase-and-project-owned-identity
created: 2026-08-06
updated: 2026-08-06
visibility: internal
canonical: true
---

# ADR-0007: An optional showcase, and identity from the manifest

**Status:** accepted — supersedes ADR-0004's "no-showcase mode is out of scope"
and its claim that the showcase is inseparable from the REST/MCP transports.
ADR-0004 stands otherwise. Retirement mechanics are [ADR-0006](0006-answer-retirement-via-migrations.md).

## Context

Two defects with one observable.

**The showcase could not be declined.** `src/backend/showcase` is 1,205 of a
generated project's 1,433 Python lines — 84% — against a 30-line
`example_feature`. Everyone who generated a project got a product tour of keel
whether they wanted one or not, and ADR-0004 explicitly deferred the question.

**The generated project served keel's name.** `api/rest_fastapi/app.py` was
`FastAPI(title="Project Keel API")` and the showcase overview hardcoded
`title="project_keel"` — one line below a `name` field that was correctly
tailored, which is why neither was noticed. `make check-openapi` kept the wrong
title green downstream, because keel's own `openapi.json` shipped verbatim and
matched it.

The second is only *observable* once someone declines the first: a project that
keeps the showcase is at least presenting a demo that is honestly keel's. A
project that declines it and still answers to `Project Keel API` is simply wrong.
So they are one decision, not two.

### What the showcase actually couples to

ADR-0004 asserted that REST and MCP "back the bundled showcase & AAD reference
implementation" and that removing the demo was therefore a distinct template
mode. Measured, that is false. Nothing under `api/rest_fastapi/aad/`, `mcp/`,
`agents/` or `scripts/query_corpus.py` imports `backend.showcase`. They read
`wiki/corpus.json`, which the showcase reads *too* but does not own — and which
`mcp/qa_server.py` and three of the four bundled agents need.

| Surface | Depends on `backend.showcase` | Fate |
|---|---|---|
| `api/rest_fastapi/showcase_api.py` | imports it | pruned + retired |
| `scripts/jobs/export_showcase_static.py`, `build_llms_txt.py` | import it | pruned + retired |
| `src/frontend/astro` | 7 pages, all fetching `/api/*` | pruned via `frontend_stack` |
| `src/frontend/react-vite` | no `api/` reference at all | kept |
| `api/rest_fastapi/aad/`, `mcp/`, `agents/`, corpus jobs | no | kept |

## Decision

**1. A `showcase` boolean answer, defaulting to `true`.** It prunes the whole
demo surface at generation (`_exclude`) and retires it on update
(`_migrations`), which the pairing gate from ADR-0006 enforces for free. The
`llms.txt` renderer goes with it — it renders the read model — but the corpus
does not.

**2. `showcase: false` + `frontend_stack: astro` is refused, not coerced.** Astro
*is* the showcase UI; `pages.yml` builds it and `make site-static` snapshots it
through the exporter this answer prunes. A `validator` on `frontend_stack`
rejects the pair with a message naming the working answers. Silent coercion would
hand the user a project that does not match the answers they gave — the defect
class the surrounding passes exist to close.

**3. Display identity is derived from `config/project.json`, not from a copier
answer.** `backend.shared.display_title` applies the same slug-to-title rule
copier's computed `project_title` uses; `project_identity(root)` reads the name
from the manifest. The REST app titles itself from it, and so does the showcase
overview.

**4. `api/rest_fastapi/openapi.json` is a generated view and does not ship.** It
names keel and lists the showcase routes, so shipping it verbatim makes
`make check-openapi` stale — red on arrival — in any project with a different
name or without the showcase. `export_openapi.py --check` now distinguishes *no
contract published yet* (exit 0, with the command to publish one) from *the
committed contract has drifted* (exit 1).

## Consequences

- The largest single knob in `copier.yml`: declining the showcase removes 84% of
  a generated project's Python.
- **A copier answer is not a source of truth for identity.** It is fixed at
  generation and silently wrong after the first rename. The manifest is the one
  place a rename is already obliged to touch (CONVENTIONS §15, `check_H`), so
  `check-openapi` stays a real drift gate with no exception carved for it.
- Keel's own `openapi.json` title is unchanged (`project_keel` →
  `Project Keel` → `Project Keel API`), so self-parity holds and the diff is
  behaviour-only.
- A no-showcase project has no committed REST contract until it runs the
  exporter once. Accepted: an absent contract cannot drift, and the check says so
  out loud rather than passing quietly.
- `Makefile`'s `site-data` and `site-static` now test for the pruned scripts
  before calling them. They ship verbatim and cannot be answer-aware any other
  way; the alternative was an eighth `.jinja` twin over a file that changes often.
- The setup steps and product copy the showcase renders are parameterised
  (`SUMMARY_TEMPLATE`, `copier copy <template-url>`), so a generated project's
  own demo describes that project. `SUMMARY` was renamed to `SUMMARY_TEMPLATE` —
  a deliberate public-API break, because a constant that must be formatted should
  not be named as if it were finished text.

## Alternatives considered

- **Templating `openapi.json` as a `.jinja` twin.** Rejected: only the title is
  templatable, while the *routes* also differ by answer, so the twin would be
  stale exactly when the showcase is declined.
- **A copier task regenerating `openapi.json` at generation.** Rejected: copier
  tasks are unsafe, so `make new` would need `--trust`. Generation is deliberately
  trust-free (ADR-0006).
- **Coercing `astro` to `react-vite` under `showcase: false`.** Rejected — see
  decision 2.
- **Pruning the corpus tooling along with the showcase.** Rejected on the
  measurement above; it would break `mcp/` and three agents to tidy an unrelated
  surface. Pinned by a test asserting no migration names a path every project
  needs.
