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
updated: 2026-10-28
visibility: internal
canonical: true
tool_command: python3 scripts/query_corpus.py "QUESTION" --corpus wiki/corpus.json
tool_effect: read-only
---

# Query corpus

## Command
`python3 scripts/query_corpus.py "QUESTION" [--root DIR | --corpus PATH] [--max-nodes N]`
> Requires Python ≥3.10 (per `pyproject.toml`); an agent invokes it via its own interpreter (`sys.executable`), not a bare `python3`.

## Purpose
The `wiki_navigator`'s retrieval step: scores nodes by query-token overlap with
their tags/title/summary, then pulls in each hit's parent and linked nodes so
the caller receives a connected tree+link neighbourhood to reason over. Each
node carries `summary_source` and `owner`/`owner_source` so the answer can cite
provenance and accountability.

## When to use
- To gather candidate context before synthesizing an answer.
- NOT to build or mutate the corpus. Tokens are lightly stemmed on both
  sides (`idempotency` finds `idempotent`) and the body excerpt counts below
  the title and summary.

## Args
| Flag | Required | Default | Meaning |
|------|----------|---------|---------|
| `QUESTION` | yes | — | the question / keywords |
| `--corpus` | no | the `--root` checkout's `wiki/corpus.json` | the corpus to read, only at its checkout's `wiki/corpus.json`: the directory that keeps it is the checkout whose files are read with it; a relative path is taken from the caller's directory; never with `--root` |
| `--max-nodes` | no | 8 | retrieval budget |
| `--root` | no | the project the script ships in | the checkout whose `wiki/corpus.json` is read and whose files are read for their level now; never with `--corpus` |

## Output
A JSON array of node objects on stdout, best match first, drawn only from the
nodes at a level in `config/project.json` `corpus.served_visibilities`: a node
at any other level, or a corpus row with no `visibility` field, is neither a hit
nor a neighbour. A document that states no level is built as `internal`, so the
default serves it.
`scripts/config_loader.py` `is_served` makes that decision. Each node's file
under `--root` is also read again (`scripts/corpus_level.py` `stated_now`, once
per file): `config_loader.is_served_now` keeps a node only when the stricter of
its corpus level and the level its file states now is served, so a file
reclassified after the corpus was built, deleted, or whose level cannot be read
is neither a hit nor a neighbour. A printed node's
`links`, `children` and `parent` name only other served nodes, because
`cut_hidden` drops every hidden id from them.
When nodes are withheld because their file now states a stricter level, or
none that can be read, stderr says how many.
`tests/unit/scripts/test_query_corpus.py` holds these rules.
The checkout and its corpus are one: `scripts/corpus_level.py` `checkout`
derives the corpus from `--root` (`<root>/wiki/corpus.json`) or the checkout
from `--corpus` (the directory that keeps its `wiki/corpus.json`). No rule can
tell a stale copy or another project from the real checkout by the files it
holds, so a corpus is never paired with a root chosen beside it: `--root` and
`--corpus` together, or a `--corpus` that is not some directory's
`wiki/corpus.json`, print nothing to stdout and exit 2. A copy of a corpus
inside another checkout's `wiki/` is that checkout's corpus, read with that
checkout's files.
A checkout with no corpus prints `[]`, exits 0 and names on stderr where the
corpus would be. A root that does not exist prints nothing to stdout and exits
2 with stderr naming it. A served level outside the vocabulary prints nothing
to stdout and exits 14.

## Side effects
READ-ONLY. Reads the corpus and the files its nodes name; writes nothing; no model call (retrieval is
deterministic — the model step is the agent's, not this tool's).

## Used by
- agents/wiki_navigator
- agents/practice_refactor
- agents/doc_reviewer
