---
title: Conventions
kind: doc
layer: n/a
status: template
owner: TBD
tags: [conventions, frontmatter, taxonomy]
summary: Single source of truth for labeling (frontmatter) and the directory taxonomy.
id: conventions
created: 2026-06-17
updated: 2026-06-24
visibility: internal
canonical: true
---
# Conventions

This file defines **how files are labeled** and **what each directory
means**. It is the contract that `README.md`/`CLAUDE.md` files and coding
agents follow. If you change the scheme, change it here first.

## 1. Frontmatter (labeling for sort/route)

Every Markdown doc (`README.md`, `CLAUDE.md`, design docs, specs) starts
with a YAML frontmatter block. This is what lets tools, agents, and
humans sort and route files without reading the body.

```yaml
---
# --- human core (for humans sorting/routing files) ---
title: Backend                       # human title
kind: package                        # see KINDS below
layer: backend                       # see LAYERS below
status: stable                       # draft|stable|deprecated|template (ADRs: proposed|accepted|superseded)
owner: team-or-person
public_api: src/backend/__init__.py  # the boundary file, or "none"
tags: [server, domain]
summary: One-line purpose, <=120 chars.
# --- corpus core (for the company "one brain": ingest/dedup/age/govern) ---
id: backend                          # stable, unique; keep it when you move the file
created: 2026-06-14
updated: 2026-06-14                  # ideally derived from git, not hand-kept
visibility: internal                 # public | internal | confidential | restricted
canonical: true                      # true = authoritative; or a path/id to the source of truth
---
```

**KINDS:** `readme` `rules` `package` `module` `tests` `test-doc` `doc`
`spec` `design` `adr` `config` `script` `agent` `mcp` `api` `wiki`
`demo` `model` `eval` `container` `ops` `tool`.

**LAYERS:** `frontend` `backend` `shared` `app` `cross-cutting` `n/a`.

### Corpus core fields (the "one brain" reads these)
These exist so a single company-wide retrieval/agent layer can ingest
every doc without producing garbage. Each one fixes a real corpus
failure mode:

| Field | Values | Why the brain needs it |
|-------|--------|------------------------|
| `id` | stable slug, unique | cite/track a doc across renames & moves (path is not stable) |
| `created` / `updated` | ISO dates | rank by recency; flag stale content (`updated` best derived from git) |
| `visibility` | `public`/`internal`/`confidential`/`restricted` | never surface a confidential doc to the wrong audience |
| `canonical` | `true` or a path/id | dedup: when the same fact lives in N places, point mirrors at the one source of truth |

Related (set when applicable, not required): `superseded_by` — **required
when `status: deprecated`** so the brain follows the chain to the live
version. The scaffold stamps `id`/dates/`visibility`/`canonical` with
safe defaults; **replace placeholder dates/owners**, and tighten
`visibility` on anything sensitive.

### Code files
Source files can't carry YAML, so the **module docstring** is the
label, and `__all__` is the machine-checkable public API:

```python
"""
title: Example feature
layer: backend
public_api: yes        # this module is re-exported from the package __init__
summary: Does the one thing this feature does.
"""
__all__ = ["do_thing", "Thing"]
```

## 2. Directory taxonomy

| Dir | kind | What goes in | What does NOT |
|-----|------|--------------|---------------|
| `src/frontend` | package | UI, client, view logic | server/domain logic |
| `src/backend`  | package | services, domain, persistence | UI rendering |
| `src/shared`   | package | contracts/types used by BOTH FE+BE | anything FE- or BE-only |
| `src/app`      | package | entrypoints, DI/wiring, CLI/`__main__` | business logic |
| `tests/unit`   | tests | fast, isolated; **mirrors `src/`** | network/disk/process |
| `tests/integration` | tests | 2+ real components, by scenario | full-stack journeys |
| `tests/e2e`    | tests | full system, user journeys | unit-level asserts |
| `tests/smoke`  | tests | "is it alive" post-deploy checks | exhaustive cases |
| `test-docs`    | test-doc | test plans, coverage register, strategy | the tests themselves |
| `docs`         | doc | architecture, specs, design, guides, ADRs | API code |
| `agents`       | agent | autonomous/LLM agent brains | the MCP/API transport |
| `mcp`          | mcp | MCP servers exposing tools | business logic (call into `src/`) |
| `api`          | api | HTTP handlers + OpenAPI specs | business logic (call into `src/`) |
| `wiki`         | wiki | browsable index/knowledge site (optional) | source of truth |
| `scripts`      | script | dev/CI automation, one-shots | importable library code |
| `config`       | config | committed defaults + `*.example.*` | secrets |
| `demo`         | demo | runnable examples | tests |
| `containers`   | container | Dockerfiles, compose, build context | app code |
| `evals`        | eval | eval datasets + harness for agents/models | unit tests |
| `ops`          | ops | deploy, IaC, runbooks, dashboards | app code |
| `models`       | model | model backends the app/agents run on (adapters + registry, e.g. Claude Code headless) | domain logic (that's `src/`) |
| `runtimes`     | package | agent control-flow engines: a neutral `Plan` + `Runtime` (adapters + registry, e.g. LangGraph) | domain/business logic (that's `src/`) |
| `agents/tools` | tool | shared, thin `*.tool.md` tool-use specs (markdown adapters over `scripts/`) | tool logic (stays in `scripts/`) |

Note: `agents/<name>/` holds **all** files for one agent — its
`prompt.md` (system prompt), code (`__init__.py` + private `_brain.py`),
`tools.md` (toolset manifest), and labels. Shared tools live one level
up in `agents/tools/` (see §10).

## 3. The `__init__.py` boundary rule (the important one)

A package's `__init__.py` **is its public API**. Callers import from the
package, never from a submodule:

```python
from myproj.backend import do_thing        # ✅ through the boundary
from myproj.backend._impl import do_thing  # ❌ reaching inside
```

- `__init__.py` lists `__all__` and re-exports only the public symbols.
- Implementation modules are prefixed `_` (e.g. `_impl.py`, `_service.py`).
- Cross-package contracts are **ABCs / `typing.Protocol`** in
  `contracts.py`, re-exported from `__init__.py`. Depend on the
  contract, not the concrete class.
- **Polyglot analogs:** TS → a single `index.ts` barrel; Go → package
  exports (capitalized identifiers); Rust → `pub` in `mod.rs`; Java →
  package-private by default + a public façade.

## 4. `shared/` vs `util/`

- **`shared/`** — domain-meaningful things shared across a section
  (types, models, contracts, constants).
- **`util/`** — generic, domain-agnostic helpers (string, fs, time,
  retry). If a helper "knows" about your domain, it belongs in `shared/`.
- Don't pre-create either in a tiny package. One of each per section,
  max. `util/` is not a junk drawer — review it like any other module.

## 5. Hidden (dot) files & directories

Split them into **committed config** (part of the project) vs
**generated/local** (gitignored). Scaffold the first kind, never the
second.

| Dot path | Commit? | Purpose |
|----------|---------|---------|
| `.gitignore` `.editorconfig` `.gitattributes` | ✅ | repo hygiene |
| `.github/workflows/` or `.gitlab-ci.yml` | ✅ | CI definitions |
| `.claude/` (`settings.json`, `skills/`, `commands/`) | ✅ | agent config shared with the team |
| `.env.example` | ✅ | documents required env vars (no real values) |
| `.vscode/` `.idea/` | ⚠️ optional | editor config — commit only a minimal shared subset |
| `.env` `.env.local` | ❌ | real secrets — gitignored |
| `.venv/` `.pytest_cache/` `.mypy_cache/` `.ruff_cache/` | ❌ | tool caches/venvs — generated, gitignored |

Rule: a dot-dir that holds **decisions** (CI, agent rules, editor norms)
is committed and may carry a `README.md`; a dot-dir that holds
**generated state or secrets** is gitignored and never scaffolded.

### Agent-rules file: `AGENT.md` is canonical, `CLAUDE.md` is a symlink

The per-directory agent-rules file is **`AGENT.md`** (the vendor-neutral
name). `CLAUDE.md` is a symlink to the sibling `AGENT.md` so Claude Code
and any other agent tool read the same rules. Edit `AGENT.md`; never edit
the symlink. The checker requires a readable `CLAUDE.md` — the symlink
satisfies it — so this is backward-compatible.

## 6. Enforcement (this is checked, not just documented)

`scripts/check_structure.py` (run via `make check`, in CI, and as a
pre-commit hook) fails the build if the conventions above drift:

| Rule | What it verifies |
|------|------------------|
| Frontmatter | every `README.md`/`CLAUDE.md` (+ `docs/**`, `test-docs/**` md) has the required keys with valid `kind`/`layer`/`status`/`visibility` |
| Corpus id | every `id` is unique across the corpus |
| Corpus canonical | a path-like `canonical` pointer resolves to a real file |
| Corpus lifecycle | `status: deprecated` requires `superseded_by` |
| Documented dirs (§2) | every taxonomy directory that exists has both `README.md` and `CLAUDE.md` |
| Package boundary (§3) | every `src/` dir with `.py` has an `__init__.py` that defines `__all__` |
| `__init__` is the API (§3) | no absolute import of another package's `_private` module |
| Authored coverage (warn) | every `__all__`-exported symbol defined in-file has a one-line docstring |
| Tool specs governed (error) | `agents/**/*.tool.md` carry valid `kind: tool` frontmatter + a resolvable `public_api` + a valid `tool_effect` |
| Accountability (warn) | tool/agent docs name a real `owner` (not missing or `TBD`) |
| Tool/agent binding (error) | each agent `tools.md` ↔ each spec's `## Used by` agree (both ways); `tool_command` invokes `public_api` |
| Project facts (§15) | `config/project.json` agrees with the tree: declared `path`/`stack`/`enabled` transport dirs exist, `enabled` ⊆ `available`, `backend.python` matches `pyproject`; an **undeclared** leftover stack/transport dir warns |
| Agent-rules symlink (§5) | every `CLAUDE.md` is a symlink to its sibling `AGENT.md`; every `AGENT.md` has that sibling |

Missing `owner` is a warning, not a failure. If you change the scheme
(KINDS / LAYERS / STATUSES / VISIBILITIES) or a check, update **both**
this file AND `scripts/check_structure.py`, then run `python3
scripts/check_scaffold_sync.py --write` to resync the embedded copy in
`scripts/scaffold.py` (the `scaffold-sync` check enforces that the live
checker and the embed stay byte-identical).

`check_structure.py` is the structural gate, but it is not the only
deterministic check. The **full suite** — scaffold-embed sync
(`check_scaffold_sync.py`), corpus integrity + reproducibility
(`scripts/jobs/check_corpus.py`), and OpenAPI / AAD contract drift — is
catalogued in **[`docs/guides/deterministic-checks.md`](docs/guides/deterministic-checks.md)**
(each check's purpose, when to run it, and how to wire it as a hook).

## 7. Triggers vs doers (hooks & scheduled jobs)

Automation has two halves; keep them in different places. A **trigger**
says *when* to run (an event, or a clock); a **doer** is *what* runs.
This mirrors the transport rule (`api/`/`mcp/` stay thin over `src/`).

| Half | Lives in | Holds |
|------|----------|-------|
| Doer — deterministic | `scripts/hooks/` (event), `scripts/jobs/` (time) | the actual stdlib logic; `--help`, idempotent |
| Doer — needs an LLM | `agents/` (brain) + a thin entrypoint in `scripts/` | reasoning/prompt; model comes from `models/` |
| Trigger — event | the ecosystem's own adapter (`.pre-commit-config.yaml`, `.github/workflows/`, `.claude/settings.json`, …) | "on event → call the doer" |
| Trigger — schedule | `ops/scheduled/` (cron/systemd/CI/cloud) | the cadence ("trigger in 2 days") |

Rules:
- **A trigger is a thin, vendor-specific adapter.** It records
  *when/what event* and points at a doer. It contains no logic.
- **The doer is vendor-agnostic.** Swapping cron→systemd, or one agent
  ecosystem for another, must not touch `scripts/` or `agents/`.
- **Keep the adapter set vendor-neutral.** Adding a second scheduler or
  hook ecosystem is a new thin adapter, never a fork of the doer.
- LLM doers stay thin: the `scripts/` entrypoint calls into `agents/`,
  which gets its model from `models/` — no provider names in the doer.

## 8. Configuration: where tunable values live

Configuration is **data the app reads**, never logic. Collate it by
*lifecycle + consumer* so each knob has exactly one home and is easy to
tune:

| Kind of value | Example | Home |
|---------------|---------|------|
| runtime, app-wide, language-neutral | RAG chunk size, top-k, max context, ports, timeouts | `config/` — committed `default.*` / `*.example.*`, grouped by concern (e.g. `config/rag.toml`) |
| model-backend selection / launch | which embedding model or reranker adapter + flags | `models/config/` — next to the registry that picks by name |
| build-time, component-coupled | frontend font, colours, footer (design tokens) | with the frontend package (`src/frontend/<app>/src/styles` / theme) — the build is the consumer |
| secret | API keys, tokens | the environment / `.env` (gitignored) — **never** `config/` |

Decision rule: *runtime + app-wide + neutral → `config/`; provider
launch → `models/config/`; build-time + package-coupled → with the
package; secret → env.* Keep one source of truth: if a container or the
`app/` layer needs a port, it reads the value from `config/` rather than
re-declaring it. Running code receives values via injection (the `app/`
layer loads config and passes it down) — domain code never reads files
itself.

## 9. Integrating a third-party tool (e.g. cdmon)

External tools (a code-doc monitor, a doc generator, a scanner) follow
the same thin-adapter rule as triggers (§7): **don't vendor the tool,
don't embed its logic.** Instead —
- **tool**: an external dependency, installed, not copied in;
- **config**: under `config/<tool>/` (committed defaults / examples);
- **adapter (doer)**: a thin wrapper in `scripts/` that only invokes it
  (no tool logic), e.g. `scripts/cdmon_sync.py`;
- **trigger**: a pre-commit/CI line (event) or `ops/scheduled/` (time);
- **output**: generated artifacts gitignored (e.g. `.cdmon/`).

**cdmon** is the worked example. This scheme is designed to **coexist**
with cdmon (the code-doc drift monitor) without either tool overwriting
the other.

| Concern | This template owns | cdmon owns |
|---------|--------------------|------------|
| Frontmatter keys | top-level keys (`title`, `kind`, `id`, `visibility`, …) | the `cdm:` mapping block (`schema_version`, `fingerprint`, `region_*`, its `audience`) |
| Doc body | prose you write | content inside `<!-- CDM:BEGIN x -->`…`<!-- CDM:END x -->` regions |
| Config | nothing | `config/cdmon/` (lives in our `config/` dir) + `cdmon.yaml` |
| Generated output | `wiki/` index | `.cdmon/` (gitignored) and `*.html` doc twins |

Why it's safe:
- cdmon **preserves foreign top-level frontmatter keys** and writes only
  under `cdm:`. Our keys survive its `heal`/`lint --fix`.
- cdmon **discovers docs by explicit registration**, not by scanning
  frontmatter — so it ignores our `README.md`/`CLAUDE.md` unless you
  register them in its config. No accidental management.
- Our validator **ignores nested frontmatter keys**, so the `cdm:` block
  never collides with our top-level keys.

Rules when both tools are in play:
- **Keep `id` in sync.** A doc's frontmatter `id` should equal the `id`
  it is registered under in cdmon's `documents:`. One identifier, two
  tools.
- **Do not hand-edit anything under `cdm:`** or inside `CDM:BEGIN/END`
  regions — those are machine-managed.
- **Reserve `cdm:` and `audience`** (in the cdmon sense: `user-guide` /
  `eng-guide`) for cdmon; don't repurpose them at top level.
- Pick one HTML source of truth: cdmon's `html: true` twins **or**
  `wiki/`, not both for the same docs.

## 10. Agent tools (`agents/tools/`) & toolset manifests

An agent's reasoning lives in its own dir; the **tools** it can use are
shared. A `kind: tool` spec (`agents/tools/<name>.tool.md`) is a **thin
adapter** that tells any LLM agent how to invoke a `scripts/` doer — the
tool's logic stays in the script (cross-ref §7/§9). Frontmatter:
`public_api` (the wrapped script, validated to exist), `tool_command`
(the exact argv), `tool_effect` (`read-only` | `writes` | `model-call`),
and a real `owner`. Body sections: Command, Purpose, When to use, Args,
Output, Side effects (begins with `READ-ONLY`/`WRITES`), Used by.

Each agent declares the tools it may invoke in `agents/<name>/tools.md`
(a one-table manifest). The binding is **bidirectional**: a tool's
`## Used by` lists the agents, and each agent's manifest rows point back
at the specs. An agent's reasoning prose lives only in its `prompt.md`
(a vendor-neutral system prompt, no frontmatter).

## 11. The wiki corpus (the one-brain index)

The repo is the *structured source* for a company wiki: source →
summarize → split into sections → summarize → link by entity/keyword
into a tree an agent traverses to answer. `scripts/jobs/build_corpus.py`
walks the repo into `wiki/corpus.json` — a flat list of **nodes**
(`doc` | `module` | `section` | `symbol`) with tree edges
(`parent`/`children`), `tags`, and authored summaries;
`scripts/jobs/link_corpus.py` adds entity/keyword **link edges**.

- **Provenance.** `summary_source` is `authored` | `generated`. For a
  repo source the authored docstring/frontmatter IS the canonical
  summary — extract it, never regenerate it. Generation is a **fallback
  for gaps only** (nodes with no authored summary), always marked
  `generated`, and never overwrites authored text. Link edges carry
  `source` (`deterministic` | `generated`) for the same reason.
- **Deterministic vs LLM.** `build_corpus`/`link_corpus`/`query_corpus`
  are pure stdlib and model-free (reproducible in CI/cron). Summary
  gap-fill is the `index_enforcer`'s LLM job (dry-run by default); rich
  `semantic` links (`source: generated`) are a planned extension it may
  add later. Answer synthesis is the `wiki_navigator`'s LLM job.
- `wiki/corpus.json` is **generated and gitignored** — a view over the
  repo, never a source of truth (like the rest of `wiki/`).

## 12. Accountability & ownership granularity

Every corpus node resolves to an `owner`, carried by one of three
markers (one token, `owner:`, grammar `[A-Za-z0-9._@-]+`):
- **doc/module** — frontmatter `owner` (a module inherits its nearest
  package `README.md` owner);
- **section** — an HTML comment under the heading: `<!-- owner: x -->`;
- **symbol** — an `owner: x` line in the docstring.

Resolution is **finest-wins, then inherit**: a marker beats frontmatter
beats the parent's resolved owner; `owner_source` records which
(`marker` | `frontmatter` | `inherited` | `none`). The `TBD` placeholder
counts as unowned. Corpus nodes that resolve to `owner_source: none` are
reported by `scripts/accountability_report.py`. Independently, at commit
time `check_F` warns when a `kind: tool`/`agent` frontmatter doc has a
missing/`TBD` owner (it inspects frontmatter only, not corpus nodes).

## 13. Authoring a new agent

A new `agents/<name>/` is done when it has: `__init__.py` (defines
`__all__`, re-exports the public entrypoint), a private `_brain.py`
(policy/prompt; gets its model from `models.get_model`, never a
provider), a markdown `prompt.md` (system prompt), a `tools.md`
manifest, and `README.md` + `AGENT.md` (+ `CLAUDE.md` symlink). Default
any model call / state change to **dry-run** (`execute=False`). The
`index_enforcer`/`wiki_navigator` examples return frozen dataclasses
(not a bare `str` like `triage`) because retrieval needs structured
citations + provenance — a deliberate, documented exception.

An agent here is an **in-process** brain (the host imports it; it gets its
model from `models/`). A service that crosses a **process boundary** to be
reached as an agent does not belong in `agents/` — it publishes an **agent
surface** (§14) instead.

## 14. Exposing a service as an agent (the agent surface)

A service that crosses a process boundary can be made discoverable as an
agent. Like every integration here, the **neutral concept comes first and the
vendor wiring is a thin adapter** (mirrors `models/` hiding a provider, §7
triggers hiding cron-vs-systemd, §9 third-party tools).

- **Neutral concept — the *agent surface*.** A service self-describes
  (`card`), answers (`ask`), and reports liveness (`health`). That contract is
  the `AgentSurface` protocol + neutral `AgentCard`/`AgentReply` in
  `src/backend/agent_surface/`. It carries no wire format, version envelope, or
  well-known path. **This is the standard**, and the root rules point at it.
- **Dialect — a thin adapter.** A wire format that serializes a surface is one
  interchangeable option. The shipped reference is **AAD** (Aion Agent
  Discovery) in `api/rest_fastapi/aad/`: it renders any `AgentSurface` to a
  descriptor (`/.well-known/aion-agent.json` + fallback), `ask`/`health`, and
  FastAPI's free `/openapi.json`. A second dialect (A2A, MCP-native, a plugin
  manifest) is a **sibling adapter over the same surface** — never an edit to
  the contract. The vendor name appears only inside the adapter, never in the
  contract or the root rules.
- **The opt-in rule.** Cross a process boundary ⇒ publish an agent surface
  (AAD is the default dialect). Compiled in-process ⇒ stay `function` (no
  port, no descriptor; §13). Do not add a network boundary just to be uniform.
- **Serve, don't discover.** A template service only **serves** its own
  descriptor. The consumer side (fetching arbitrary descriptor URLs, the SSRF/
  trusted-host allowlist, version normalization) is the platform's concern and
  is deliberately not vendored here.
- **Generated schema, versioned.** `config/agent_surface/aad-v1.0.schema.json`
  is **generated** from the `AadDescriptor` model
  (`make agent-surface-schema`), so the published wire contract can't drift
  from the code; `tests/integration/test_aad_conformance.py` is the CI gate.
  `aad_version` is `MAJOR.MINOR` — minor is additive-only, major is breaking, a
  shipped field is never mutated. `auth.kind` declares *that* auth is needed,
  never the secret; `none` is dev-only.

See `docs/guides/agent-surface.md` (how-to) and `docs/adr/0002-agent-surface-and-discovery.md` (the decision).

## 15. Project facts manifest (`config/project.json`)

The repo is **polyglot by design** (Python backend, a TypeScript frontend,
protobuf + nginx at the edges), so "what is this project made of" is not a
single language — it is a set of **per-layer facts**. Those facts live in one
machine-readable manifest, `config/project.json`, enforced by
`check_structure.py` (`check_H`) so they cannot silently drift from the tree.

It is keyed **by layer/concern, never one global `language`**:

- `layers.<layer>` — per layer: a `language`, plus a `path` (backend) or a
  `root` + `available` stack list (frontend) and the chosen `stack` (`null`
  while the template still ships more than one — pick one, delete the rest).
- `transports` — `enabled` ⊆ `available`, a name→dir map of the shipped
  transports (REST / gRPC / nginx-edge / MCP).

`check_H` **errors** on a hard contradiction (a declared `path`/`stack`/
`enabled` transport dir that is missing; `enabled` not in `available`; a
`backend.python` that disagrees with `pyproject.toml`'s `requires-python`) and
**warns** on an *undeclared leftover* — a stack dir under the frontend `root`,
or a transport dir under `api/`, that the manifest doesn't list. So a stack you
forgot to record (or meant to delete) is surfaced, not blocked.

Why JSON here, and why this and not prose: a manifest is read by **code** (a
deterministic gate), whereas `AGENT.md` prose is read by a **model**
(advisory) — they're complementary, not rivals. JSON specifically because the
checker must run under the host's old `python3` in pre-commit, where `tomllib`
(3.11+) is absent; stdlib `json` parses everywhere. TOML stays right for
runtime tunables (§8). `config/project.json` is a committed **decision** (like
the generated agent-surface schema, §14) — read by the checker, not the app.

## 16. Agent control flow (`runtimes/`): a neutral Plan, engines are adapters

An agent's reasoning is a *policy*; the order its steps run in is *control
flow*. Keep control flow a **neutral concept** and make the execution engine
one interchangeable adapter — the same rule as `models/` (providers), triggers
(cron vs systemd, §7), and the agent surface (dialects, §14). LangGraph being
open-source does **not** exempt it from this (§9): the coupling the rule bans
lives at the import/API boundary, not the licence.

- **Neutral concept — the `Plan`.** An agent declares its flow as a `Plan`: a
  flowchart of typed `Step`s and `Edge`s, defined in `runtimes/` alongside the
  `Runtime` ABC. A `Step` carries an `effect` from the §10 `tool_effect`
  vocabulary (`read-only` | `writes` | `model-call`); an `Edge` may carry a pure
  `when(state)` predicate. This makes branching **inspectable data**, not nested
  `if`s, and puts the **dry-run effect-guard in one place**: a `writes` or
  `model-call` step is skipped — its `run` is never invoked — unless the run is
  authorized with `execute=True`.
- **Default engine — stdlib, reproducible.** The default `Runtime` is the
  pure-stdlib `inprocess` walker; it is the *reference semantics* and is what
  CI, pre-commit, and the app always get — no dependency, no install.
- **Vendor engine — one adapter, lazily loaded.** A graph engine such as
  **LangGraph** is *one* `Runtime` adapter (`runtimes/langgraph_adapter.py`),
  selected by name (`get_runtime("langgraph")`) and registered **lazily** so the
  default path imports nothing extra. Its dependency is an **optional extra** in
  `pyproject.toml` (`[project.optional-dependencies] langgraph`), never in
  `dependencies`. The vendor name appears only inside that adapter and its
  registry thunk — never in `contracts.py`, the default engine, or any `agents/`
  brain. A second engine (Burr, pydantic-graph, a durable executor) is a sibling
  adapter over the same contract.
- **Adapters change execution, never semantics.** Every engine produces the same
  final state and honours the same dry-run guard and edge order as the
  `inprocess` reference — machine-checked by
  `tests/unit/runtimes/test_runtime_equivalence.py` (skipped when the optional
  engine isn't installed).
- **The opt-in rule.** Default to `inprocess`. Adopt a heavier engine **per
  agent** only when a real trigger arrives — durable resume across a crash
  (checkpointer), mid-flow human approval (`interrupt()`), or a genuine
  cycle/fan-out — not for uniformity. A linear 1–2 step agent stays a Plan on the
  default engine (or need not adopt one at all).
- **Manifest.** `config/project.json` carries an optional `runtimes` block
  (`default` + `available`), validated by `check_structure.py` (`check_H`).

See `docs/guides/agent-runtimes.md` (how-to) and
`docs/adr/0003-agent-control-flow-runtime.md` (the decision).

## 17. Development loops (how to work in this repo)

Code here is produced by **bounded, gated loops**, not one-shot edits — and any
agent working in the repo follows them by default (the imperative form is in the
root `AGENT.md`; the playbook with examples is `docs/guides/dev-loops.md`). These
govern *how you work*; their executable analog — a loop a program runs unattended
— is a `Plan` on a `Runtime` (§16, `runtimes/`), the same shape expressed as data.

- **Slice work vertically.** The tree is layered (`app → {frontend, backend} →
  shared`, plus transports/agents/runtimes), but decompose *work* across those
  layers into vertical slices: each unit is one capability end-to-end, not one
  whole layer at a time. A slice is independently verifiable, so it maps to one
  convergence pass and one TDD cycle (+ an e2e scenario if user-facing). Splitting
  by layer or dimension is for read-only review/research sweeps, not for building.
- **Test-first (TDD).** New or changed `src/` behavior is driven by its mirror
  unit test (root `AGENT.md`; `tests/AGENT.md`): red (a test that fails for the
  right reason) → green (smallest change that passes) → refactor (with the suite
  green). A public symbol without a test is unfinished.
- **Bounded convergence loop.** When a change spans more than one file or can't
  be finished and verified in one edit, write the plan down, then work it in
  passes: each pass does the next slice (one capability end-to-end), runs
  `make verify`, and commits.
  Re-derive the worklist from the repo each pass (search before assuming
  something is unbuilt) so progress lives in the tree and the commits, not in one
  ever-growing context; delegate heavy reads to a subagent. Stop at the written
  done-condition, or at a pass cap (default 5 when the task gives none) — then
  report done-vs-remaining instead of starting another pass.
- **End-to-end coverage.** A new user-facing flow (route, page, transport
  endpoint) gets a `tests/e2e/` scenario that exercises it through its public
  surface; name it by scenario, not by a source file.
- **The gate is the judge.** "Done" means `make verify` (`check-all` + `lint` +
  `typecheck` + `test`) is green; phase transitions and completion gate on the
  real exit code, never on a model's self-report.

These are conventions an agent follows, not gated by a structural check today: no
check verifies the test mirror, that a test came first, or that it exercises the
code. The real gate is `make verify` (a red suite fails it); TDD itself is a
behavioral discipline, not something a static check can certify.

## 18. Generic solutions (solve the class, not the case)

Code here is meant to stay **generic**: this is a *template*, and everything
built from it should solve the broader problem, not the one example in front of
you. The recurring failure mode — for humans and for an LLM alike — is
**overfitting to the sample**: given an eval, a golden file, or one failing test,
you make *that* case pass by hardcoding its expected answer, special-casing its
specimen value, or pasting its datum into the code, instead of deriving the
result from the inputs. The example is evidence of the rule; it is not the rule.
This is the same neutral-concept-first instinct the rest of these conventions
take — a provider behind `models/` (§7), a tool behind a thin adapter (§9), a
wire dialect behind the agent surface (§14), an engine behind a `Plan` (§16):
**name the general thing first; the concrete instance is one interchangeable
case of it.** It is the discipline sibling of the development loops (§17): there
the test is the pressure that keeps you honest, here it is the rule the test only
samples. The playbook with worked examples is `docs/guides/generic-solution.md`.

- **The eval is a sample, not the spec.** A golden set, a fixture, or a failing
  case *illustrates* the behavior; it does not *define* it. Read a row as "the
  rule must also produce this", never as "the rule is this row". Generalize from
  the example to the property it demonstrates, then satisfy the property.
- **Name the general rule before you special-case.** Before adding
  `if x == "<specimen>"`, state the rule the specimen is an instance of and
  implement *that*. A special-case branch is justified only when the general rule
  genuinely has a discontinuity there — and then it is documented as such, not as
  a way to turn one test green. An enum-style dispatch over a fixed, documented
  set of kinds *is* the general rule; a lone branch that exists only to pass one
  case is not.
- **Derive, don't hardcode the answer key.** Compute outputs from inputs. A
  literal lifted verbatim from a test's expected value and embedded in `src/`
  logic is an *answer key*: it makes the sample pass while teaching the code
  nothing. A value that genuinely is content — a slug, a catalogue row, a curated
  title — belongs in a declared registry (`*_data.py`, fixtures, a `kind: config`
  module per §8), not in a branch; logic reads data, it does not memorize it.
- **Name the constant, or annotate the literal.** A meaningful literal in logic
  is either promoted to an `ALL_CAPS` named constant (naming *is* the general
  move) or, when it is deliberately a fixed token, annotated
  `# generic-ok: <reason>` so the next reader knows it was a choice.
- **When a golden test fails, fix the generator — not the golden.** If output
  drifted from a committed golden, ask *which is right*: change the producing
  logic if the golden is correct, or regenerate the golden (and say why in the
  commit) if the behavior legitimately changed — never tweak the code so it emits
  exactly the stored bytes for that one input.
- **A patch is not a fix.** If a change only makes the named failing case pass —
  and a slightly different input of the same class would still fail — you patched
  the symptom. The fix is the smallest change that makes the *whole class* pass,
  with a test (§17) that samples more than the original case.

A *backstop*, not a gate: `scripts/check_generic.py` (run via `make advise`,
gate `report`) flags the highest-confidence smell — a distinctive literal that a
test asserts as an expected value (an `==` operand or `assertEqual` argument)
**and** that also appears hardcoded in non-data `src/` logic (an "answer key in
source"). It excludes data/registry modules (`*_data.py`, fixtures, `conftest`),
literals named as `ALL_CAPS` constants, and trivial literals, honours a
`# generic-ok: <reason>` pragma, and **always exits 0**. It is catalogued with gate `report` in §6's suite and in
`docs/guides/deterministic-checks.md`.

This is a convention an agent follows, not gated by a structural check: the
advisory linter never fails the build, and a static check cannot *prove* code is
generic — genericity is a property of the input space, not of the source text. So
`check_generic.py` only points at one specific, high-confidence smell (a memorized
answer key) and stays silent on legitimate data. The real pressure is behavioral:
behavior-asserting tests (§17) and review. Treat a flag as a question to answer,
and the rule above as the actual standard — never a green checkmark labelled
"generic".
