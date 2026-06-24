---
title: Link corpus
kind: tool
layer: cross-cutting
status: stable
owner: platform-team
public_api: scripts/jobs/link_corpus.py
tags: [tool, corpus, links, entity, AXI]
summary: Add deterministic keyword/entity link edges to wiki/corpus.json in place; writes.
id: tool-link-corpus
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
tool_command: python3 scripts/jobs/link_corpus.py --corpus wiki/corpus.json
tool_effect: writes
---

# Link corpus

## Command
`python3 scripts/jobs/link_corpus.py [--corpus PATH] [--max-links N]`
> Requires Python ≥3.10 (per `pyproject.toml`); an agent invokes it via its own interpreter (`sys.executable`), not a bare `python3`.

## Purpose
Adds the cross-references that make the corpus a graph, not just a tree: two
nodes that share entities/keywords (e.g. both mention "AXI") get a link edge
carrying the shared token (`via`) and a Jaccard `score`, with
`source: deterministic`. The agent may later add richer `semantic` edges
(`source: generated`) — kept distinguishable so a reviewer can distrust them.

## When to use
- Right after `build_corpus`, before the navigator answers.
- NOT to create the nodes (that is `build_corpus`).

## Args
| Flag | Required | Default | Meaning |
|------|----------|---------|---------|
| `--corpus` | no | `wiki/corpus.json` | corpus to augment |
| `--max-links` | no | 8 | max edges per node |

## Output
Rewrites the `links` of every node in place; prints an edge/node count.
No corpus present → prints a notice and exits 0.

## Side effects
WRITES `wiki/corpus.json` (in place). Deterministic + idempotent: re-running
recomputes the same edges. No model call.

## Used by
- agents/index_enforcer
