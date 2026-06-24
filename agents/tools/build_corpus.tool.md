---
title: Build corpus
kind: tool
layer: cross-cutting
status: stable
owner: platform-team
public_api: scripts/jobs/build_corpus.py
tags: [tool, corpus, index, AXI]
summary: Walk the repo into wiki/corpus.json (doc/module/section/symbol nodes); writes.
id: tool-build-corpus
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
tool_command: python3 scripts/jobs/build_corpus.py --out wiki/corpus.json
tool_effect: writes
---

# Build corpus

## Command
`python3 scripts/jobs/build_corpus.py [--root DIR] [--out PATH]`
> Requires Python ≥3.10 (per `pyproject.toml`); an agent invokes it via its own interpreter (`sys.executable`), not a bare `python3`.

## Purpose
Deterministically extracts the one-brain index: every frontmatter doc, code
module, doc section, and `__all__` symbol becomes a node with its AUTHORED
summary (frontmatter/docstring), tree edges (parent/children), tags, resolved
owner, and provenance. Nodes lacking an authored summary are emitted as gaps
(`summary_source: ""`) for the agent to fill — it never invents prose itself.

## When to use
- To (re)build the corpus after `structure_check` passes.
- NOT for retrieval (that is `query_corpus`) and NOT to fill gaps (that is the
  agent's model step).

## Args
| Flag | Required | Default | Meaning |
|------|----------|---------|---------|
| `--root` | no | repo root | tree to index |
| `--out` | no | `wiki/corpus.json` | output path |

## Output
Writes `wiki/corpus.json` (`{schema_version, root, nodes:[...]}`); prints a
node/gap/unowned count. Exit non-zero on failure.

## Side effects
WRITES `wiki/corpus.json` (generated, gitignored — a view, never a source).
Deterministic + idempotent: same tree → same file. No model call.

## Used by
- agents/index_enforcer
