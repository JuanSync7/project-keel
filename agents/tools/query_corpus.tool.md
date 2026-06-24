---
title: Query corpus
kind: tool
layer: cross-cutting
status: stable
owner: platform-team
public_api: scripts/query_corpus.py
tags: [tool, corpus, retrieval, query]
summary: Read-only retrieval over wiki/corpus.json — candidate nodes for a question.
id: tool-query-corpus
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
tool_command: python3 scripts/query_corpus.py "QUESTION" --corpus wiki/corpus.json
tool_effect: read-only
---

# Query corpus

## Command
`python3 scripts/query_corpus.py "QUESTION" [--corpus PATH] [--max-nodes N]`
> Requires Python ≥3.10 (per `pyproject.toml`); an agent invokes it via its own interpreter (`sys.executable`), not a bare `python3`.

## Purpose
The `wiki_navigator`'s retrieval step: scores nodes by query-token overlap with
their tags/title/summary, then pulls in each hit's parent and linked nodes so
the caller receives a connected tree+link neighbourhood to reason over. Each
node carries `summary_source` and `owner`/`owner_source` so the answer can cite
provenance and accountability.

## When to use
- To gather candidate context before synthesizing an answer.
- NOT to build or mutate the corpus.

## Args
| Flag | Required | Default | Meaning |
|------|----------|---------|---------|
| `QUESTION` | yes | — | the question / keywords |
| `--corpus` | no | `wiki/corpus.json` | corpus to read |
| `--max-nodes` | no | 8 | retrieval budget |

## Output
A JSON array of node objects on stdout, best match first. No corpus present →
prints `[]` and exits 0.

## Side effects
READ-ONLY. Reads the corpus; writes nothing; no model call (retrieval is
deterministic — the model step is the agent's, not this tool's).

## Used by
- agents/wiki_navigator
