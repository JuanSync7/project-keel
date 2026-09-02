---
title: Agent tools
kind: doc
layer: cross-cutting
status: template
owner: TBD
public_api: none
tags: [tools, agents, adapters]
summary: Shared, thin TOOL.md tool-use specs — how an agent invokes a scripts/ doer.
id: agents-tools-readme
created: 2026-06-17
updated: 2026-09-02
visibility: internal
canonical: true
---

# Agent tools

Shared, thin TOOL.md tool-use specs — how an agent invokes a scripts/ doer.

Each `*.tool.md` is a **thin adapter**: it tells any LLM agent *how to
invoke* a doer in `scripts/` — the tool's logic stays in the script,
never here (same rule as transports in §7 and third-party tools in §9).
Tools live here because they are **shared across agents**; an agent
declares which it may use in its own `tools.md` manifest.

Each spec carries `kind: tool` frontmatter with `public_api` (the
wrapped script, validated to exist), `tool_command` (the exact argv),
and `tool_effect` (`read-only` | `writes` | `model-call`). Adding a
tool = add a `*.tool.md` here AND list it in the using agent's
`tools.md` (`## Used by` and the manifest row are bidirectional).

## What ships here

| Member | Delegates to | Effect | Not for |
|--------|--------------|--------|---------|
| `accountability_report.tool.md` | `scripts/accountability_report.py` | `read-only` — lists every node of the built corpus whose owner resolves to nothing (`owner_source: none`, which includes the `TBD` placeholder), as text or `--json`; always exits 0, so it is a report, never a gate (rides `make advise`) | Not for gating the tree: it reads `wiki/corpus.json`, not the files, and passes whatever it finds — `structure_check.tool.md` is the gate, and its own accountability WARN covers only `kind: tool`/`agent` docs, not the doc, section and symbol nodes this lists. Not for producing the corpus it reads: without one it prints a notice and reports nothing — run `build_corpus.tool.md` first |
| `apply_refactor.tool.md` | `scripts/apply_refactor.py` | `writes` — applies one JSON edit spec inside `--root` (each `find` must match its file exactly once, or `content` replaces a whole file), runs one make gate, and restores every file's original bytes if the gate is red or never returns; exit 0 applied, 1 rolled back, 2 bad spec | Not for a gate-only verdict on an unedited tree — that is `run_make_target.tool.md`; this member always takes an edit spec, `--gate none` makes it write ungated, and `--dry-run` validates the spec without running the gate at all. Not for choosing the edit: the spec is the calling agent's model step, and the corpus it walks to find candidates comes from `query_corpus.tool.md` |
| `build_corpus.tool.md` | `scripts/jobs/build_corpus.py` | `writes` — walks the tree into `wiki/corpus.json`: one node per frontmatter doc, code module, `##`/`###` section and `__all__` symbol, with its authored summary, tree edges, tags, resolved owner and provenance; an unauthored summary is emitted as a gap, never invented; plus the AUTHORED edges — every relative link, `§N` citation and backticked repository path a document makes becomes an edge of `kind` link / citation / mention from the section that wrote it; deterministic and idempotent | Not for the keyword edges: `link_corpus.tool.md` adds those after every build and keeps the authored ones. Not for retrieval, which is `query_corpus.tool.md`. Not the same job as `scripts/jobs/rebuild_index.py` (no spec here), which only lists README titles |
| `link_corpus.tool.md` | `scripts/jobs/link_corpus.py` | `writes` — adds the `keyword` edges to each node's `links` in place: two nodes sharing a tag or entity (both carry `AXI`, say) get an edge holding the shared token (`via`), a Jaccard `score` and `source: deterministic`; at most `--max-links` (8) keyword edges per node, recomputed from scratch on every run, the authored edges kept | Not for creating or refreshing nodes or the authored reference edges (both `build_corpus.tool.md`): it links only the tags already assigned, and with no corpus present it prints a notice and exits 0 instead of building one. Not for reading the graph, which is `query_corpus.tool.md` |
| `query_corpus.tool.md` | `scripts/query_corpus.py` | `read-only` — scores nodes by stemmed query-token overlap with their tags, title and summary (and, below those, their body excerpt), pulls in each hit's parent and linked nodes, and prints up to `--max-nodes` (8) node objects as JSON, best first, each carrying `summary_source` and `owner_source` so an answer can cite provenance | Not for producing or updating the corpus it reads — `build_corpus.tool.md` makes the nodes and `link_corpus.tool.md` the edges it follows; with no corpus it prints `[]` at exit 0, so an empty result can mean not built yet rather than no match. Not for the answer itself: synthesis is the calling agent's model step |
| `run_make_target.tool.md` | `scripts/run_make_target.py` | `read-only` — runs one make target (a plain token checked against an allowlist pattern, passed as argv, never a shell string) and reports `{target, ok, returncode, output}`; exit 0 pass, 1 fail or timeout, 2 unsafe target; how the refactor loop establishes its green baseline | Not for applying an edit — `apply_refactor.tool.md` runs this same gate itself after each edit and rolls back on red. Not for the conventions findings — `structure_check.tool.md` runs `check_structure.py` directly and yields its `WARN`/`ERROR` lines to parse, where `make check` through this member returns one `ok` verdict with those lines buried in an `output` blob |
| `structure_check.tool.md` | `scripts/check_structure.py` | `read-only` — runs the 3.6-safe conventions gate (checks A–S: frontmatter and unique ids, labelled dirs, package and private-import boundaries, tool/agent governance, project facts, practice boundaries, ruleset/twin/help/catalogue parity, cross-references); prints `WARN`/`ERROR` lines and exits 1 on any error | Not for owner gaps across the corpus — its accountability WARN covers only `kind: tool`/`agent` docs read from disk; `accountability_report.tool.md` lists every unowned node of the built corpus. Not for a pass/fail on any other make target, which is `run_make_target.tool.md`. It builds nothing: the corpus is `build_corpus.tool.md` |
