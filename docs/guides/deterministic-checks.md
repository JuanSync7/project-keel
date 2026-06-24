---
title: Deterministic checks (the template linter)
kind: doc
layer: n/a
status: template
owner: TBD
tags: [checks, ci, linter, determinism, pre-commit, hooks, guide]
summary: Catalogue of every deterministic check that keeps a project-template repo honest — purpose, when to run, and how to wire as a hook.
id: docs-guides-deterministic-checks
created: 2026-06-19
updated: 2026-06-24
visibility: internal
canonical: true
---

# Deterministic checks (the template linter)

This template is meant to stay **structurally honest** as it grows and as
agents edit it. A normal linter checks *code style*; the scripts catalogued
here check the **conventions of the template itself** — labeling, package
boundaries, the doc/code corpus, and the published contracts — so that any
project created from this template keeps a guaranteed level of structure.

Every check here is **deterministic**: same inputs → same verdict, no model,
no network, reproducible in CI and on a teammate's laptop. They are *doers*
(CONVENTIONS §7): the logic lives in `scripts/` and thin triggers (pre-commit,
CI) call them. Each script is self-describing (`--help`) and safe to re-run.

## TL;DR

```bash
make check        # fast structural gate — runs anywhere, incl. Python 3.6
make check-all    # the full deterministic suite (needs the project interpreter)
make verify       # check-all + lint + typecheck + test (the everything gate)
```

Wire them once and forget:

```bash
pip install pre-commit && pre-commit install   # run the fast checks on every commit
# CI already runs `make check-all` (.github/workflows/ci.yml)
```

## Two interpreters, on purpose

The host's pre-commit `python3` may be **old** (this repo's is 3.6), so the
checks split in two:

- **3.6-safe, stdlib-only** — run on *every commit* via pre-commit and need no
  dependencies: `check_structure.py`, `check_scaffold_sync.py`. These never
  use f-strings/`from __future__ import annotations`, so they parse under 3.6.
- **Project-interpreter (≥3.10 / app deps)** — the corpus jobs (need ≥3.7) and
  the contract checks (need FastAPI/pydantic). They run in **CI** (Python 3.11)
  and locally under your venv. The contract checks **skip gracefully** (exit 0
  with a note) when their dependency is absent, so they are safe in pre-commit
  too; the corpus check is CI-only because it imports the ≥3.7 corpus builder.

`make check` only runs the 3.6-safe set; `make check-all`/`make verify` run
everything and therefore expect the project interpreter.

## The checks

| Check | Script | Gate? | Interpreter | What it guarantees |
|-------|--------|:-----:|-------------|--------------------|
| Structure & frontmatter | `scripts/check_structure.py` | error | 3.6-safe | Labels, taxonomy, package boundaries, tool/agent governance, project facts, agent-rules symlinks (checks A–I) |
| Scaffold-embed sync | `scripts/check_scaffold_sync.py` | error | 3.6-safe | `scaffold.py`'s embedded scripts are byte-identical to the live files |
| Corpus integrity | `scripts/jobs/check_corpus.py` | error | ≥3.7 | `wiki/corpus.json` is a valid, acyclic graph **and** the build is reproducible |
| OpenAPI drift | `api/rest_fastapi/export_openapi.py --check` | error | FastAPI | Committed `openapi.json` matches the live routes |
| AAD schema drift | `scripts/agent_surface/generate_aad_schema.py --check` | error | pydantic | Committed AAD JSON Schema matches the model |
| Code-doc drift | `scripts/cdmon_sync.py --check` | error* | any | cdmon code↔doc drift (*no-op until cdmon is installed) |
| Accountability | `scripts/accountability_report.py` | report | ≥3.7 | Lists corpus nodes that resolve to no owner (informational) |
| Generic-solution advisor | `scripts/check_generic.py` | report | 3.6-safe | Distinctive literals asserted as golden in tests **and** hardcoded in `src/` logic (the "answer-key" overfit smell, §18). Advisory only — never fails the build |

All gates exit **0 = clean, 1 = failure**. Warnings (e.g. a missing `owner`)
print but never fail the build.

---

### 1. Structure & frontmatter — `scripts/check_structure.py`

**Purpose.** The core enforcer of `CONVENTIONS.md`. Checks A–I:

- **A. Frontmatter** — every `README.md` / `AGENT.md` / `CLAUDE.md`, `docs/**`,
  `test-docs/**` markdown, and `agents/**/*.tool.md` has the required keys with
  valid `kind` / `layer` / `status` / `visibility`; `id` is unique; a path-like
  `canonical` resolves; `deprecated` requires `superseded_by`.
- **B. Documented dirs** — every taxonomy directory has `README.md` + `CLAUDE.md`.
- **C. Package boundary** — every `src/` dir with `.py` has an `__init__.py`
  defining `__all__`.
- **D. `__init__` is the API** — no absolute import of another package's
  `_private` module.
- **E. Authored coverage** (warn) — every `__all__`-exported symbol has a docstring.
- **F. Tool specs governed** (error) + **accountability** (warn).
- **G. Tool↔agent binding** — `tools.md` ↔ each spec's `## Used by` agree.
- **H. Project facts** — `config/project.json` agrees with the tree (§15).
- **I. Agent-rules symlink** — every `CLAUDE.md` is a symlink to its sibling
  `AGENT.md`, and every `AGENT.md` has that sibling (§5).

**When to run.** Every commit (pre-commit) and in CI; any time you add a
directory, package, doc, tool, or agent.

**Run.** `make check` · `python3 scripts/check_structure.py`

**Changing it.** If you change the scheme or a check, update **both** this
script and `CONVENTIONS.md`, then `python3 scripts/check_scaffold_sync.py
--write` to resync the scaffold embed (check 2 enforces it).

### 2. Scaffold-embed sync — `scripts/check_scaffold_sync.py`

**Purpose.** `scripts/scaffold.py` regenerates a project skeleton and ships
several scripts embedded as raw-string constants (`w("path", _NAME_SRC)`).
CONVENTIONS §6 requires those embeds to stay **byte-identical** to the live
files — otherwise a freshly scaffolded project ships tooling that has silently
diverged. This check discovers every embed and diffs it against its live file.

**When to run.** Every commit; always after editing any embedded script
(`check_structure.py`, `check_scaffold_sync.py`, `scripts/jobs/check_corpus.py`).

**Run.**
- `python3 scripts/check_scaffold_sync.py` — fail on drift (default), print diffs.
- `python3 scripts/check_scaffold_sync.py --write` — resync every embed (the fix).

Gracefully no-ops (exit 0) when `scripts/scaffold.py` is absent (a derived
project that dropped the generator has nothing to guard).

### 3. Corpus integrity & reproducibility — `scripts/jobs/check_corpus.py`

**Purpose.** `wiki/corpus.json` is the generated "one-brain" index (CONVENTIONS
§11). This check validates the graph — unique `node_id`s, resolvable
`parent`/`children`/`links`, valid `kind`/`owner_source`/`visibility`, owner
coherence, sorted tags, **acyclic** parent chains — and proves the build is
**deterministic** (builds twice, asserts byte-identical output).

**When to run.** In CI, and after any change to the corpus builders or to
content that feeds the corpus.

**Run.**
- `python scripts/jobs/check_corpus.py` — fresh build, validate + determinism.
- `python scripts/jobs/check_corpus.py --corpus wiki/corpus.json` — validate the
  on-disk file (and warn if it is stale vs a fresh build; the file is gitignored).

### 4. OpenAPI drift — `api/rest_fastapi/export_openapi.py --check`

**Purpose.** The committed `api/rest_fastapi/openapi.json` is the published REST
contract; keep it generated from the live FastAPI app so it cannot drift from
the routes (the `api/` rules). `--check` exits 1 if the committed file is stale.

**When to run.** Whenever routes/schemas change; in CI. Regenerate with the same
script (no `--check`).

**Run.** `python api/rest_fastapi/export_openapi.py [--check]` · `make check-openapi`
Skips gracefully (exit 0) when FastAPI is absent.

### 5. AAD schema drift — `scripts/agent_surface/generate_aad_schema.py --check`

**Purpose.** Keep the committed AAD wire schema
(`config/agent_surface/aad-v1.0.schema.json`) generated from the `AadDescriptor`
model (CONVENTIONS §14), so the published contract can't drift from the code.

**Run.** `python scripts/agent_surface/generate_aad_schema.py [--check]` ·
`make check-aad` — skips gracefully when pydantic is absent.

### 6. Code-doc drift — `scripts/cdmon_sync.py --check`

**Purpose.** Thin adapter over the optional cdmon code↔doc drift monitor
(CONVENTIONS §9). A no-op until cdmon is installed, then it flags docs that
have drifted from the code they describe.

**Run.** `python3 scripts/cdmon_sync.py --check`

### 7. Accountability report — `scripts/accountability_report.py`

**Purpose.** A *report*, not a gate: lists corpus nodes that resolve to no owner
(CONVENTIONS §12), so ownership gaps are visible. Does not fail the build.

**Run.** `python scripts/accountability_report.py`

### 8. Generic-solution advisor — `scripts/check_generic.py`

**Purpose.** A *report*, not a gate: the advisory backstop for the "solve the
general case" discipline (CONVENTIONS §18). It flags an **answer key in source** —
a distinctive literal that a test asserts as its expected value (an `==` operand
or `assertEqual` argument) **and** that is also hardcoded in non-data `src/`
logic. It excludes data/registry modules (`*_data.py`, fixtures, `conftest.py`),
literals named as `ALL_CAPS` constants, and trivial literals, honours a
`# generic-ok: <reason>` pragma, and **always exits 0** — it draws attention, it
never gates.

**When to run.** Anytime, especially after making a failing eval/golden/case
pass; advisory and outside `make verify`.

**Run.** `make advise` · `python3 scripts/check_generic.py [--json] [--strict]`

---

## How the hooks are wired

### Pre-commit (event trigger)

`.pre-commit-config.yaml` runs the fast, dependency-light checks on every
commit (each hook is a thin trigger that calls a `scripts/` doer):

| Hook id | Calls |
|---------|-------|
| `structure` | `python3 scripts/check_structure.py` |
| `scaffold-sync` | `python3 scripts/check_scaffold_sync.py --check` |
| `openapi` | `python3 api/rest_fastapi/export_openapi.py --check` (skips if FastAPI absent) |
| `aad-schema` | `python3 scripts/agent_surface/generate_aad_schema.py --check` (skips if pydantic absent) |
| `cdmon` | `python3 scripts/cdmon_sync.py --check` (no-op until installed) |
| `eslint` / `ruff` | frontend + Python style |

Enable once: `pip install pre-commit && pre-commit install`.

### CI (event trigger)

`.github/workflows/ci.yml` runs under Python 3.11 and Node 22:

```yaml
- run: make check-all   # structure, scaffold-sync, corpus, openapi, aad
- run: make lint
- run: make typecheck
- run: make test
```

### Scheduled (time trigger)

A corpus rebuild + integrity check fits a nightly job: put the cadence in
`ops/scheduled/` (cron/systemd/CI) and have it call
`scripts/jobs/rebuild_index.py` then `scripts/jobs/check_corpus.py` — keep the
*doer* in `scripts/`, the *schedule* in `ops/` (CONVENTIONS §7).

## Adding a new deterministic check

1. Write the doer in `scripts/` (or `scripts/jobs/` for unattended jobs).
   Stdlib-only + 3.6-safe if it must run in pre-commit; otherwise it may use
   the project interpreter and **skip gracefully** when a dependency is absent.
2. Give it `--help` and a `--check` mode if it guards a committed artifact.
3. Add a `make` target and, if it should gate commits, a `.pre-commit-config.yaml`
   hook and/or a CI step.
4. If `scaffold.py` should ship it to new projects, embed it as a
   `w("scripts/your_check.py", _YOUR_CHECK_SRC)` pair (no triple-single-quote in
   the source) and run `check_scaffold_sync.py --write`.
5. Document it in this file.
