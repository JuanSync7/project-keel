---
title: Jobs
kind: script
layer: n/a
status: template
owner: TBD
public_api: none
tags: [jobs, scheduled, automation, triggers]
summary: Time-triggered doers — the scripts a scheduler fires. The schedule lives in ops/.
id: scripts-jobs-readme
created: 2026-06-17
updated: 2026-09-02
visibility: internal
canonical: true
---

# Jobs

Time-triggered doers — the scripts a scheduler fires. The schedule lives in ops/.

Time-triggered **doers**: the scripts that run *on a schedule*. The
script is the doer; the **schedule** is a thin, vendor-specific
adapter in `ops/scheduled/` (cron/systemd/CI/cloud) that records only
*when* to fire it. Every job here is deterministic and self-contained (no
model, no network); an LLM-backed job would call an agent in `agents/`, and
none does today. Only `rebuild_index.py` has a schedule adapter — the rest are
fired by `make site-data`, `make site-static` and `make check-corpus`.

## What ships here

| Member | Purpose | Not for | Trigger |
|--------|---------|---------|---------|
| `build_corpus.py` | Walks every frontmatter-bearing `.md` and every documented `.py` under the code roots (scope imported from `scripts/check_structure.py`, never re-typed) into `wiki/corpus.json`: doc, section, module and symbol nodes with tree edges, authored summaries, owner provenance, and the authored reference edges — every relative link, `§N` citation and backticked repository path a document makes, as `kind` link / citation / mention from the section that wrote it, computed with `check_structure.py`'s own reference grammar. Exits 1 on a duplicate `node_id`. | Keyword edges: `link_corpus.py` adds those in place afterwards and keeps these. A human TOC of README titles is `rebuild_index.py`. It never validates what it wrote; `check_corpus.py` does. | `make site-data` (step 1; reached by `make site-static` and by CI `ci.yml`). `tests/conftest.py` builds the test corpus with it. |
| `build_llms_txt.py` | Renders the showcase read model (`backend.showcase.load_showcase`) over the corpus into `wiki/llms.txt` and `wiki/llms-full.txt`, the in-repo agent front door; its corpus-graph link points at the live route `/api/wiki/tree`. Prints a stated skip and exits 0 when `backend.showcase` is absent. | The corpus itself: it only reads what `build_corpus.py` and `link_corpus.py` wrote, so it runs after them. The copy a static site serves is written by `export_showcase_static.py`, which emits its own `llms.txt` beside the snapshot with the tree link rewritten to `api/wiki/tree.json`. | `make site-data` (step 3, behind `[ -f ]`, so a project that declined the showcase prints a stated skip). Pruned by `copier.yml` when `showcase=false`. |
| `check_corpus.py` | The gate. Builds a fresh corpus twice in memory (`build_corpus` then `link_corpus`), validates the graph contract (schema, enums, owner coherence, tree edges, acyclicity, link targets and scores), proves the two builds are byte-identical, then compares the deterministic projection of the local `wiki/corpus.json` with the fresh build: absent is a loud pass, unreadable or stale is an error naming `make site-data`. `--corpus FILE` validates an existing file instead, with staleness downgraded to a WARN. | Regenerating anything: a check that writes is not a check, and the repair it names is `make site-data`, i.e. `build_corpus.py` plus `link_corpus.py`. Labeling and taxonomy belong to `scripts/check_structure.py`; unowned nodes are reported advisorily by `scripts/accountability_report.py`. | `make check-corpus` (inside `make check-all`, hence `make verify` and CI `ci.yml`). Catalogued at the error tier in `docs/guides/deterministic-checks.md`. |
| `export_showcase_static.py` | Snapshots the showcase read model into the declared frontend's `public/` (derived from `config/project.json` `layers.frontend`, or `--out-dir`): `api/*.json` mirroring `api/rest_fastapi/showcase_api.py` endpoint for endpoint, `api/wiki/nodes.json` (every corpus node with rendered markdown, for client-side search), and `llms.txt` plus `llms-full.txt` whose tree link points at `api/wiki/tree.json`. Stated skip when `backend.showcase` is absent or no frontend is declared. | The in-repo `wiki/llms.txt`: `build_llms_txt.py` writes that one, for a live backend. Building the corpus: it reads `wiki/corpus.json` raw and requires `build_corpus.py` and `link_corpus.py` to have run first. Serving: `api/rest_fastapi/showcase_api.py` is the live transport over the same `load_showcase()`. | `make site-static` (depends on `site-data`; passes `--out-dir` from `FE_APPS` and `--base-url`), and GitHub Pages via `.github/workflows/pages.yml`. Pruned by `copier.yml` when `showcase=false`. |
| `link_corpus.py` | Rewrites `wiki/corpus.json` in place, giving every node up to `--max-links` (8) keyword edges to the nodes that share a tag: Jaccard `score`, the shared token as `via`, `kind: keyword`, `source: deterministic`. Idempotent (keyword edges are recomputed from scratch each run; the authored edges are kept); a missing corpus is a stated skip. | Creating nodes, tree edges or the authored reference edges: `build_corpus.py` does that, this only adds keyword edges. Semantic or LLM edges: those would come from an agent in `agents/` and carry `source: generated`, a value `check_corpus.py` already admits, but nothing in the tree emits them yet. | `make site-data` (step 2, straight after `build_corpus.py`). `check_corpus.py` imports its `link_corpus()` for the fresh build; `tests/conftest.py` runs it. |
| `rebuild_index.py` | Writes `# Doc index`, a flat sorted Markdown list of every `README.md` under `--root` with its frontmatter `title:`, to `--out` (default stdout; the schedule adapters use `wiki/INDEX.md`). Pure stdlib, pure and idempotent: the template's worked example of a time-triggered doer. | The corpus: `build_corpus.py` indexes every labeled `.md`, every section and every documented module and symbol into the JSON graph that the agents, `mcp/qa_server.py` and `scripts/query_corpus.py` query; this lists README titles only, and nothing in the tree reads its output. The agent front door (`wiki/llms.txt`) is written by the showcase's `build_llms_txt.py`, when the showcase ships. Unrelated to `agents/index_enforcer` despite the name: that agent fills corpus summaries. | `ops/scheduled/crontab.example` and `.github/workflows/scheduled.yml` (daily 02:00, `--out wiki/INDEX.md`); the `rebuild_index` tool of `mcp/action_server.py` (dry-run unless `execute: true`). No `make` target. |
