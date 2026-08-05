---
title: Project Keel
kind: readme
layer: n/a
status: template
owner: TBD
tags: [template, scaffold, project_keel]
summary: A generic, polyglot-aware, agent-friendly project skeleton that stays honest.
id: readme
created: 2026-06-17
updated: 2026-06-22
visibility: internal
canonical: true
---
# Project Keel

Project Keel is a generic project skeleton with a strict, documented structure
that is friendly to both humans and coding agents (Claude Code). Every directory
carries a `README.md` (what + frontmatter labels) and a `CLAUDE.md`
(local rules). The single source of truth for the labeling scheme and
the directory taxonomy is **[`CONVENTIONS.md`](CONVENTIONS.md)** — read
it first.

## Top-level layout

```
.
├── src/            # all production source
│   ├── frontend/   #   UI / client (TS/JS-leaning)
│   ├── backend/    #   server / domain / services (Python-leaning)
│   ├── shared/     #   FE<->BE data contract (DTOs/enums/error codes)
│   └── app/        #   OPTIONAL composition root (single-process apps only)
├── tests/          # unit (mirrors src/) + integration/e2e/smoke (by scenario)
├── test-docs/      # test plans, coverage register, test strategy
├── docs/           # architecture / specs / design / guides / reference / adr
├── agents/         # autonomous/LLM agents
├── mcp/            # Model Context Protocol servers (tool gateways)
├── api/            # transports: REST/OpenAPI (FastAPI), gRPC, nginx edge
├── wiki/           # (optional) browsable knowledge/index site
├── scripts/        # dev + CI automation (deterministic checks, corpus jobs)
├── config/         # configuration (committed defaults + examples)
├── demo/           # runnable demos / examples
├── containers/     # Dockerfiles, compose, image build context
├── evals/          # eval suites (esp. for agents/models)
├── ops/            # deploy, IaC, runbooks, observability
├── models/         # model backends the agents/app run on (adapters + registry)
├── pyproject.toml  # Python src-layout packaging + tool config
├── Makefile        # task runner (test, lint, fmt, run, ...)
└── CONVENTIONS.md  # frontmatter schema + taxonomy (READ FIRST)
```

## The three load-bearing conventions

1. **`__init__.py` is the API.** Nothing leaves a package except through
   its `__init__.py` (`__all__`). Private modules are `_underscore`d.
   (TS analog: an `index.ts` barrel; Rust: `pub` in `mod.rs`.)
2. **Every dir is labeled.** `README.md` + `CLAUDE.md` with YAML
   frontmatter (`kind`, `layer`, `status`, `public_api`, `tags`) so
   files sort and route mechanically.
3. **Tests mirror only where it helps.** `tests/unit/` mirrors `src/`
   1:1; integration/e2e/smoke are organized by scenario.

## Getting started

Generate a **tailored** project in one command — an interactive Q&A (name, frontend
stack, transports, domain profiles) writes only the parts you chose, fills in
`config/project.json`, and records your answers so you can pull future template
improvements with `copier update --trust`:

```bash
pipx install copier                                 # once
copier copy gh:JuanSync7/project-keel my-project    # interactive Q&A -> tailored skeleton
```

Later, from inside the generated project, pull template improvements:

```bash
copier update --trust    # re-runs the Q&A with your recorded answers as defaults
```

`--trust` is required, not optional politeness: re-answering a question has to
*remove* what you declined (the frontend stack you switched away from, a transport
you turned off), and copier can only delete through `_migrations`, which run
commands — so it refuses to update an unattended template without it. Generation
never needs the flag. Changing an answer deletes that directory, so commit your work
first; `git checkout -- <path>` brings it back.

In a checkout of this repo you can also run `make new DEST=../my-project` — but note
that records the template's **absolute local path** as the update origin, so
`copier update` then works on that machine only. Generate from `gh:JuanSync7/project-keel`
(as above) for a project you intend to share. Then:

```bash
make help          # list tasks
make check         # fast structural gate (or: make verify)
```

Delete any optional dirs you don't need (`wiki/`, `models/`, `evals/`, `containers/`)
and rename `src/backend/example_feature/` to your first real package. Project
generation is `copier`-based (see [ADR 0004](docs/adr/0004-project-templating-copier.md)).

## Showcase demo (synced docs site)

A minimalist docs/wiki site presents this template as a product and
renders **live from the backend** — overview, features, the
deterministic-check catalogue, and a browsable index of every
doc/module/script:

```bash
make site-data   # build the wiki corpus the site reads
make run-api     # FastAPI on :8000  (project interpreter / venv)
make run-web     # Astro on :4321, pointed at the API
```

See [`docs/guides/showcase-site.md`](docs/guides/showcase-site.md).
