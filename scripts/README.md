---
title: Scripts
kind: script
layer: n/a
status: template
owner: TBD
public_api: none
tags: []
summary: Dev and CI automation, one-shots, and the deterministic checks.
id: scripts-readme
created: 2026-06-17
updated: 2026-09-02
visibility: internal
canonical: true
---

# Scripts

Dev and CI automation, one-shots, and the deterministic checks.

Executable helpers, not importable library code. Anything reused by the app
belongs in `src/`, not here. Project generation is `copier`-based (the repo root
is the template; see [ADR 0004](../docs/adr/0004-project-templating-copier.md)).

## What ships here

| Member | Purpose | Not for | Run by |
|--------|---------|---------|--------|
| `accountability_report.py` | Reads `wiki/corpus.json` and lists every node (doc, section, module, symbol) whose `owner_source` is `none` after frontmatter, marker and inheritance resolution; text or `--json`; always exit 0, a one-line note when there is no corpus | Failing the build on a missing owner — `check_structure.py` check F is the per-file gate (error on a malformed tool spec, WARN on a tool or agent doc whose `owner` is missing or TBD); building the corpus it reads — `jobs/build_corpus.py` | `make advise`; `agents/tools/accountability_report.tool.md` (index_enforcer) |
| `agent_surface/` | Doers for the agent-surface contract (§14): `agent_surface/generate_aad_schema.py` writes `config/agent_surface/aad-v1.0.schema.json` from the `AadDescriptor` model; `--check` exits 1 when the committed schema is stale, a stated skip (exit 0) when pydantic or the adapter cannot be imported, exit 1 when the model itself fails to build | The REST contract — `api/rest_fastapi/export_openapi.py --check` is its twin; the surface protocol or the AAD adapter code — `src/backend/agent_surface/` and `api/rest_fastapi/aad/`; the repo's own conventions — `check_structure.py` | `make check-aad` (from `check-all`), `make agent-surface-schema`; pre-commit hook `aad-schema` |
| `apply_refactor.py` | Applies one JSON edit spec (`find`/`replace` matching exactly once, or full `content`) to files under `--root`, runs `make <gate>` and rolls every file back when the gate is red or never returns; `--dry-run` plans without writing; exit 1 = rolled back, 2 = bad spec | Running a gate on a tree you did not just edit — `run_make_target.py` (this one writes first); choosing what to edit — `refactor_practice.py` and `agents/practice_refactor` produce the spec | `agents/tools/apply_refactor.tool.md` (practice_refactor) |
| `cdmon_sync.py` | Thin adapter (§9) that runs the external `cdmon` binary (`lint`, `heal`, `build`; `--check` is `lint`) with `config/cdmon/cdmon.yaml`; a stated skip (exit 0) when cdmon is not on PATH or the config is absent; no drift logic lives here | The repo's own conventions — `check_structure.py`; corpus integrity — `jobs/check_corpus.py`; any other external tool — a sibling adapter, never logic in this one | `make check-cdmon` (from `check-all`); pre-commit hook `cdmon` |
| `check_generic.py` | Advisory (§18): flags an answer key — a distinctive literal a test asserts with `==` or `assertEqual` that is also hardcoded in non-data `src/` logic; `# generic-ok: <reason>` waives; 3.6-safe; always exit 0 | Coding-practice smells (inline provider, isinstance chain, `__slots__`, `with`) — `check_practices.py`; anything that must fail the build — `check_structure.py`, since this never exits 1 | `make advise` (alias `make check-generic`) |
| `check_practices.py` | Advisory: flags the `advisory`-tier practices of `config/practices.json` over `src/` and `agents/` — a provider constructed inline, a three-or-more-branch isinstance chain, a `# hot-path` class without `__slots__`, a resource acquired outside `with` (cuda profile); `# practice-ok: <reason>` waives; 3.6-safe; always exit 0 | The `gate`-tier practices — `check_structure.py` enforces owned-exception boundary (J), frozen-config (K), naked-tensor (L) and ruleset parity (M); test-versus-src answer keys — `check_generic.py` | `make advise` |
| `check_python_version.py` | Reads `requires-python` from `pyproject.toml` (3.6-safe, no tomllib) and exits 1 with a plain message when the running interpreter is older, so a newer-syntax check fails with a sentence instead of a traceback | Skipping when the host is old — the contract checks (`agent_surface/generate_aad_schema.py`, `cdmon_sync.py`) carry their own stated skips, this one refuses; checking anything in the tree — `check_structure.py` | `make check-python` (prerequisite of `check-corpus` and `test`, hence of `check-all` and `verify`) |
| `check_structure.py` | The stdlib, 3.6-safe conventions gate — checks A–S: frontmatter, taxonomy, package boundary, module headers, tool-agent binding, project facts, agent-rules symlinks, gate-tier practices, ruleset, twin, help and catalogue parity, cross-references; exit 1 on any error, warnings never fail | The corpus graph — `jobs/check_corpus.py`; advisory smells — `check_generic.py` and `check_practices.py`; owner gaps across corpus nodes — `accountability_report.py`; external code-doc drift — `cdmon_sync.py`; the published contracts — `agent_surface/generate_aad_schema.py --check` | `make check` (from `check-all` and `verify`); pre-commit hook `structure`; `agents/tools/structure_check.tool.md` (index_enforcer); `jobs/build_corpus.py` imports its `CODE_ROOTS` and `IGNORE_DIRS` |
| `hooks/` | Event-triggered doers (§7): `hooks/on_stop_triage.py` hands an event payload (argument or stdin) to `agents.triage`; dry-run unless `--execute`, model named by `--model` from `models/` | Time-triggered work — `jobs/`; the trigger itself (which event fires it) — the ecosystem adapter (`.pre-commit-config.yaml`, `.github/workflows/`, `.claude/settings.json`); the reasoning — `agents/triage` | No in-tree trigger yet: `.claude/settings.json` declares no hooks and no workflow or pre-commit entry names `hooks/on_stop_triage.py` |
| `jobs/` | Time-triggered doers (§7): `jobs/build_corpus.py` then `jobs/link_corpus.py` then `jobs/build_llms_txt.py` (showcase only) produce `wiki/corpus.json` and `llms.txt`; `jobs/check_corpus.py` gates the graph; `jobs/export_showcase_static.py` snapshots the showcase API to static files; `jobs/rebuild_index.py` writes a flat markdown list of README titles (`wiki/INDEX.md`) and never touches the corpus | Event-triggered work — `hooks/`; the cadence — `ops/scheduled/crontab.example` and `.github/workflows/scheduled.yml`; retrieval over the corpus — `query_corpus.py`; owner gaps — `accountability_report.py` | `make site-data`, `make site-static`, `make check-corpus`; `agents/tools/build_corpus.tool.md` and `agents/tools/link_corpus.tool.md` (index_enforcer); `mcp/action_server.py` (`rebuild_index`); the cron and workflow schedules |
| `query_corpus.py` | Read-only retrieval over `wiki/corpus.json`: scores nodes by stemmed token overlap with tags, title and summary (then, below those, the body excerpt), then fills the budget with each hit's parent and linked nodes; prints JSON, `[]` when there is no corpus | The answer itself — `agents/wiki_navigator` reasons over the returned nodes; owner gaps — `accountability_report.py`; building or linking the corpus — `jobs/build_corpus.py` and `jobs/link_corpus.py` | `agents/tools/query_corpus.tool.md` (wiki_navigator, practice_refactor) |
| `refactor_practice.py` | Thin CLI over `agents.practice_refactor.refactor()`: walks the corpus neighbourhood of one named practice, gates a green baseline and (only with `--execute`) proposes and applies gated edits; dry-run by default; `--json` report | The reasoning, prompt or model choice — `agents/practice_refactor` and `models/`; applying one edit with rollback — `apply_refactor.py`; running a gate — `run_make_target.py`; the trigger — `.claude/skills/practice-refactor` | The `practice-refactor` skill (`.claude/skills/practice-refactor/SKILL.md`); by hand per `docs/guides/coding-practices.md` |
| `review_docs.py` | The deterministic documentation review (§1 freshness): every governed Markdown file's `updated:` is no earlier than its last commit, and a file modified in the working tree carries today's date; text or `--json`; exit 0 as a report, `--strict` exits 1 | Structure, links or citations — `check_structure.py` (checks A–S) reads those without git; owner gaps — `accountability_report.py`; anything needing a model — a doc-review agent, not this | `make advise`; `tests/integration/test_doc_freshness.py` (as the gate, via `--strict` semantics) |
| `run_make_target.py` | Runs one `make <target>` (a validated plain token, optional repeatable `--make-arg`) and reports a structured pass or fail, `--json` or text; writes nothing itself; exit 1 on a red gate | Editing files and rolling back on red — `apply_refactor.py`; being the gate — it wraps `make verify` (or a smaller target), it does not replace it | `agents/tools/run_make_target.tool.md` (practice_refactor) |

## Deterministic checks (the template linter)

These scripts keep the template structurally honest — labeling, package
boundaries, the doc/code corpus, and the published contracts:

- `check_structure.py` — conventions validator (checks A–S); `make check`.
- `jobs/check_corpus.py` — `wiki/corpus.json` integrity + build reproducibility.
- `agent_surface/generate_aad_schema.py --check` / `cdmon_sync.py --check` — contract drift.

Run them all with `make check-all` (or `make verify` for checks + lint +
types + tests). Each one's purpose, when to run it, and how to wire it as a
pre-commit / CI / scheduled hook is catalogued in
**[`docs/guides/deterministic-checks.md`](../docs/guides/deterministic-checks.md)**.
