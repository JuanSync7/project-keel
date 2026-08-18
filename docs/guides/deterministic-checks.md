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
  dependencies: `check_structure.py`. It never uses
  f-strings/`from __future__ import annotations`, so it parses under 3.6.
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
| Structure & frontmatter | `scripts/check_structure.py` | error | 3.6-safe | Labels, taxonomy, package boundaries, tool/agent governance, project facts, agent-rules symlinks, owned-exception & frozen-config boundaries, naked-tensor domain warn, lint/type ruleset parity, template twin parity (checks A–O) |
| Corpus integrity | `scripts/jobs/check_corpus.py` | error | ≥3.7 | the fresh build is a valid, acyclic, reproducible graph **and** the local `wiki/corpus.json` (what agents query) is current when present — absent is a loud pass, stale is an error naming `make site-data` (ADR-0008) |
| OpenAPI drift | `api/rest_fastapi/export_openapi.py --check` | error | FastAPI | Committed `openapi.json` matches the live routes |
| AAD schema drift | `scripts/agent_surface/generate_aad_schema.py --check` | error | pydantic | Committed AAD JSON Schema matches the model |
| Code-doc drift | `scripts/cdmon_sync.py --check` | error* | any | cdmon code↔doc drift (*no-op until cdmon is installed) |
| Accountability | `scripts/accountability_report.py` | report | ≥3.7 | Lists corpus nodes that resolve to no owner (informational) |
| Generic-solution advisor | `scripts/check_generic.py` | report | 3.6-safe | Distinctive literals asserted as golden in tests **and** hardcoded in `src/` logic (the "answer-key" overfit smell, §18). Advisory only — never fails the build |
| Coding-practices advisor | `scripts/check_practices.py` | report | 3.6-safe | Coding-practice smells (a provider constructed inline instead of injected, a ≥3-branch `isinstance` chain, a `# hot-path` class without `__slots__`, a resource acquired outside a `with`). Reads `config/practices.json`; advisory only — never fails the build (see [coding-practices](coding-practices.md)) |

All gates exit **0 = clean, 1 = failure**. Warnings (e.g. a missing `owner`)
print but never fail the build.

---

### 1. Structure & frontmatter — `scripts/check_structure.py`

**Purpose.** The core enforcer of `CONVENTIONS.md`. Checks A–O:

- **A. Frontmatter** — every `README.md` / `AGENT.md` / `CLAUDE.md`, `docs/**`,
  `test-docs/**` markdown, and `agents/**/*.tool.md` has the required keys with
  valid `kind` / `layer` / `status` / `visibility`; `id` is unique; a path-like
  `canonical` resolves; `deprecated` requires `superseded_by`.
- **B. Documented dirs** — every taxonomy directory has `README.md` + `CLAUDE.md`.
- **C. Package boundary** — every `src/` dir with `.py` has an `__init__.py`
  defining `__all__`.
- **D. `__init__` is the API** — no absolute import of another package's
  `_private` module.
- **E. Authored coverage** — every `__all__`-exported symbol defined in-file has
  a docstring: the corpus's symbol summaries (warn until ADR-0008).
- **F. Tool specs governed** (error) + **accountability** (warn).
- **G. Tool↔agent binding** — `tools.md` ↔ each spec's `## Used by` agree.
- **H. Project facts** — `config/project.json` agrees with the tree (§15).
- **I. Agent-rules symlink** — every `CLAUDE.md` is a symlink to its sibling
  `AGENT.md`, and every `AGENT.md` has that sibling (§5).
- **J. Owned-exception boundary** — in `src`/`models`/`runtimes`/`agents`, no
  `raise` of an exception type imported from a foreign (non-local, non-stdlib)
  module; wrap it in an owned error or waive with `# practice-ok: <reason>` (§18).
- **K. Frozen-config gate** — a class carrying the declared marker
  (`config/practices.json` `tokens.config_marker`, `# practice: frozen-config`)
  must be provably immutable (frozen dataclass / `NamedTuple` / attrs-frozen).
  Keyed on the author-written marker, never a `*Config` name suffix (§18); it
  resolves aliased imports and honours the 3.6-vs-3.8 class-line model; waivable.
- **L. Naked-tensor domain** (warn) — only when the `cuda` profile is enabled
  (`config/project.json` `practices.profiles`), a parameter annotated with a bare
  tensor base type (`tokens.tensor_base_types`) and no shape comment **warns**.
  An advisory heuristic (a token may name a local class) — never an error.
- **M. Ruleset parity** — `pyproject.toml` must not silently loosen the lint/type
  policy declared in `config/practices.json` `rulesets`: every ruff
  `extend_select` family is selected, every mypy flag is enforced, no `deferred`
  (policy-off) family is selected. Reads `pyproject.toml` as text (no `tomllib`
  on 3.6); multi-line arrays, dotted-key/header forms, `# practice-ok` all handled.
  Also enforces the two declarations that used to have no consumer: every ruff
  `per-file-ignores` pattern must be declared in `rulesets.ruff.per_file_ignores`
  (one `"**/*.py"` line could otherwise silence a family corpus-wide), and every
  `[[tool.mypy.overrides]]` relaxation — including switching off a *component* of
  `strict` rather than `strict` itself — must be declared in
  `rulesets.mypy.overrides` for that module.
- **N. Template twin parity** — keel is a copier template, and every `*.jinja`
  twin must be declared in `config/project.json` `template.twins` with its kind:
  `parity` (reproduces keel's own file except where templated), `divergence`
  (deliberately does not — `.gitignore.jinja` drops the `.copier-answers.yml`
  ignore so a generated project keeps its upgrade channel), or `generated`
  (copier writes it; keel commits none of its own). Render-free by necessity —
  this script is stdlib-only and 3.6-safe, so it cannot import jinja2 — which
  bounds the claim: it proves no twin is undeclared, no parity twin carries a
  non-templated line the plain file has lost (the drift that shipped a weaker
  gate to every descendant), and no divergence twin has quietly stopped
  diverging. The byte-exact rendered comparison stays in
  `tests/integration/test_copier_generation.py`, where jinja2 exists. Silent in a
  generated project, which has no twins.

- **O. Module header contract** — every code-root module docstring carries
  explicit, non-empty `title:` and `summary:` lines, in exactly the grammar
  `build_corpus` reads (pinned by a parity test, not a shared import — this
  script stays 3.6-safe). Without them the corpus falls back to
  filename/first-prose-line and labels the result `authored`, and an
  undocumented module is silently dropped from the index (ADR-0008).

**When to run.** Every commit (pre-commit) and in CI; any time you add a
directory, package, doc, tool, or agent.

**Run.** `make check` · `python3 scripts/check_structure.py`

**Changing it.** If you change the scheme or a check, update **both** this
script and `CONVENTIONS.md`.

### 2. Corpus integrity & reproducibility — `scripts/jobs/check_corpus.py`

**Purpose.** `wiki/corpus.json` is the generated "one-brain" index (CONVENTIONS
§11). This check validates the graph — unique `node_id`s, resolvable
`parent`/`children`/`links`, valid `kind`/`owner_source`/`visibility`, owner
coherence, sorted tags, **acyclic** parent chains — and proves the build is
**deterministic** (builds twice, asserts byte-identical output). It also gates
the **local** corpus — the file the agents actually query: absent is a loud
pass (a fresh clone, CI, and a day-one generated project have none), while
present-but-stale is an **error** naming `make site-data`. Staleness is judged
on the *deterministic projection* — `index_enforcer`'s `"generated"` summary
fills and semantic links are enrichment, not rot (ADR-0008).

**When to run.** In CI, and after any change to the corpus builders or to
content that feeds the corpus.

**Run.**
- `python scripts/jobs/check_corpus.py` — fresh build, validate + determinism.
- `python scripts/jobs/check_corpus.py --corpus wiki/corpus.json` — validate the
  on-disk file (and warn if it is stale vs a fresh build; the file is gitignored).

### 3. OpenAPI drift — `api/rest_fastapi/export_openapi.py --check`

**Purpose.** The committed `api/rest_fastapi/openapi.json` is the published REST
contract; keep it generated from the live FastAPI app so it cannot drift from
the routes (the `api/` rules). `--check` exits 1 if the committed file is stale.

**When to run.** Whenever routes/schemas change; in CI. Regenerate with the same
script (no `--check`).

**Run.** `python api/rest_fastapi/export_openapi.py [--check]` · `make check-openapi`
Skips gracefully (exit 0) when FastAPI is absent.

### 4. AAD schema drift — `scripts/agent_surface/generate_aad_schema.py --check`

**Purpose.** Keep the committed AAD wire schema
(`config/agent_surface/aad-v1.0.schema.json`) generated from the `AadDescriptor`
model (CONVENTIONS §14), so the published contract can't drift from the code.

**Run.** `python scripts/agent_surface/generate_aad_schema.py [--check]` ·
`make check-aad` — skips gracefully when pydantic is absent.

### 5. Code-doc drift — `scripts/cdmon_sync.py --check`

**Purpose.** Thin adapter over the optional cdmon code↔doc drift monitor
(CONVENTIONS §9). A no-op until cdmon is installed, then it flags docs that
have drifted from the code they describe.

**Run.** `python3 scripts/cdmon_sync.py --check`

### 6. Accountability report — `scripts/accountability_report.py`

**Purpose.** A *report*, not a gate: lists corpus nodes that resolve to no owner
(CONVENTIONS §12), so ownership gaps are visible. Does not fail the build.

**Run.** `python scripts/accountability_report.py`

### 7. Generic-solution advisor — `scripts/check_generic.py`

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
| `openapi` | `python3 api/rest_fastapi/export_openapi.py --check` (skips if FastAPI absent) |
| `aad-schema` | `python3 scripts/agent_surface/generate_aad_schema.py --check` (skips if pydantic absent) |
| `cdmon` | `python3 scripts/cdmon_sync.py --check` (no-op until installed) |
| `eslint` / `ruff` | frontend + Python style |

Enable once: `pip install pre-commit && pre-commit install`.

### CI (event trigger)

`.github/workflows/ci.yml` runs under Python 3.11 and Node 22:

```yaml
- run: make check-all   # structure, corpus, openapi, aad
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
   hook and/or a CI step. New projects generated with `copier` get the file
   automatically (copier ships the real `scripts/` tree — see
   [ADR 0004](../adr/0004-project-templating-copier.md)).
4. Document it in this file.
