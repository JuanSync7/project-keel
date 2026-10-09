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
updated: 2026-10-09
visibility: internal
canonical: true
---
# Project Keel

Project Keel is a generic project skeleton with a strict, documented structure
that is friendly to both humans and coding agents. It comes from the keel
template, which gives it three things. A structure gate:
`scripts/check_structure.py` runs checks A to Z, plus any checks the project
adds under `structure.project_checks`, on every commit and in `make verify`.
Agent-safety rails: every make target is labelled with its effect, a gate runner
refuses a target outside the labels it allows, and every child process starts
from an allowlisted environment. An update channel: `copier update` brings the
template's later fixes into the project. The source of truth for the labels and
the directory taxonomy is **[`CONVENTIONS.md`](CONVENTIONS.md)**; read it first.

## Who it is for

- **For** a team, with or without coding agents, that wants a Python backend
  whose layout, documents and make targets are checked by machine on every
  commit, and that will take the template's fixes as `copier update` delivers
  them.
- **Not for** a project with no Python, or one that cannot keep a fixed
  top-level layout; [the limits guide](docs/guides/limits-and-troubleshooting.md)
  says what adopting costs.

## What keel is not

- **Not a sandbox.** The child-process allowlist and the effect labels are
  defence in depth: a child still runs as your user
  ([ADR-K-0012](docs/adr/keel/K-0012-child-process-environment-allowlist.md),
  [ADR-K-0011](docs/adr/keel/K-0011-make-target-effect-labels.md)).
- **Not code review.** A green gate says the structure, the documents and the
  tests hold; it does not say the change is right.
- **Not a host.** keel generates and checks a repository; it does not deploy or
  run your service.
- **Not a requirements tracker.** Which requirement is met right now belongs
  in a companion ledger system; keel holds the code and the documents.

## Prerequisites

- GNU make, bash and git, on Linux or macOS (`Makefile`).
- A bare `python3` on the path: pre-commit runs the gate with it
  (`.pre-commit-config.yaml`).
- The project interpreter, at the version `pyproject.toml` `requires-python`
  sets.
- Node, at the version `.github/workflows/ci.yml` installs, for a frontend app;
  `make fe-install` installs its packages.
- copier, at the version floor
  [generate-and-upgrade.md](docs/guides/generate-and-upgrade.md) states, to
  generate or update a project.

## Quickstart

```bash
pipx install copier
copier copy --trust gh:JuanSync7/project-keel my-project
cd my-project
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"     # pytest, ruff and mypy: the gate's tools
.venv/bin/pip install pre-commit && .venv/bin/pre-commit install
make check                            # the structure gate
make verify                           # every gate: checks, lint, types, tests
```

copier accepts any git URL or local path in place of
`gh:JuanSync7/project-keel`. With no `--vcs-ref`, copier resolves the **newest
tag**, so the command above gives you the latest named release. Pin a specific
one with `--vcs-ref v0.2.2` when you need two projects generated from the same
keel.

In a checkout of keel, `make new DEST=../my-project` runs the same generation
against the checkout; it needs the `template` extra
(`pip install -e ".[dev,template]"`), and
[generate-and-upgrade.md](docs/guides/generate-and-upgrade.md) says what it
records and when it refuses.

If your system `python3` predates the project floor, pass the
interpreter explicitly — `make PY=.venv/bin/python verify` — which is what
`check_python_version.py` is telling you when it refuses.

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
├── wiki/           # generated knowledge/index site (read by mcp/ and agents/)
├── scripts/        # dev + CI automation (deterministic checks, corpus jobs)
├── config/         # configuration (committed defaults + examples)
├── demo/           # runnable demos / examples
├── containers/     # Dockerfiles, compose, image build context
├── evals/          # eval suites (esp. for agents/models)
├── ops/            # deploy, IaC, runbooks, observability
├── models/         # model backends the agents/app run on (adapters + registry)
├── runtimes/       # agent control flow: a neutral Plan, engines as adapters
├── .github/        # CI definitions (workflows)
├── .claude/        # agent config shared with the team (settings, skills)
├── pyproject.toml  # Python src-layout packaging + tool config
├── Makefile        # task runner (test, lint, fmt, run, ...)
└── CONVENTIONS.md  # frontmatter schema + taxonomy (READ FIRST)
```

## The three load-bearing conventions

1. **`__init__.py` is the API.** Nothing leaves a package except through
   its `__init__.py` (`__all__`). Private modules are `_underscore`d.
   (TS analog: an `index.ts` barrel; Rust: `pub` in `mod.rs`.)
2. **Every top-level dir is declared and labeled.** `README.md` + `CLAUDE.md` with YAML
   frontmatter (`kind`, `layer`, `status`, `public_api`, `tags`) so
   files sort and route mechanically.
3. **Tests mirror only where it helps.** `tests/unit/` mirrors `src/`
   1:1; integration/e2e/smoke are organized by scenario.

## Making it yours

Delete any optional dirs you don't need (`evals/`, `containers/`) and
rename `src/backend/example_feature/` to your first real package. Then drop
each deleted directory's line from the tree under Top-level layout:
`tests/integration/test_doc_drift.py` fails while the tree lists a directory
that does not exist.

`models/` is the exception: `config/project.json` **declares** the adapters that live
there, so deleting the directory alone leaves the manifest claiming adapters that no
longer exist and `make check` correctly reports one error per adapter. To drop it, clear
`models.available` and `models.credential_env` to `{}` and set `models.default` to
`null` in the same commit (a credential declaration for an adapter that is not
available is itself an error), then run `make check` once more: it lists every doc that still links into `models/`, by file
and line, so you can unlink or reword each one. That second step is the same for any
directory you remove — the gate holds every link to a target that exists. Project
generation is `copier`-based (see [ADR-K-0004](docs/adr/keel/K-0004-project-templating-copier.md)).

## Updating

From inside the project, with your work committed, pull the template's changes:

```bash
copier update --trust    # re-runs the Q&A with your recorded answers as defaults
```

An update removes what you declined, restamps the documents it changed, and
stops on a conflict it cannot settle.
[generate-and-upgrade.md](docs/guides/generate-and-upgrade.md) lists each step
it runs, with its exit codes and how to recover, and says how to preview an
update with `make audit-project` first.

## Showcase demo (synced docs site)

A minimalist docs/wiki site presents this template as a product and
renders **live from the backend** — overview, features, the
deterministic-check catalogue, and a browsable index of every
doc/module/script:

```bash
make site-data   # build the wiki corpus the site reads
make run-api     # FastAPI on :8000  (project interpreter / venv)
make run-web     # the dev server of the first app under src/frontend (it prints its URL)
```

See [`docs/guides/showcase-site.md`](docs/guides/showcase-site.md).

## Where to read next

- [docs/README.md](docs/README.md) says how the documentation is organised.
- [The guide index](docs/guides/README.md) lists every guide and who it is for.
- [CONTRIBUTING.md](CONTRIBUTING.md) is the steps for one change, and how a
  release is cut.
- [AGENT.md](AGENT.md) is the rules every coding agent here follows.
- [Generate and upgrade](docs/guides/generate-and-upgrade.md) covers
  generation, adoption and `copier update`.
- [Limits and troubleshooting](docs/guides/limits-and-troubleshooting.md) says
  where keel stops, every waiver and every exit code.
- [CONVENTIONS.md](CONVENTIONS.md) defines the labels and the taxonomy.
