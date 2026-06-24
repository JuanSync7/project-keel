---
title: Index enforcer
kind: agent
layer: backend
status: template
owner: TBD
public_api: agents/index_enforcer/__init__.py
tags: [agent, enforcer, index, corpus]
summary: Enforces conventions and builds/maintains the accountable wiki corpus.
id: agents-index-enforcer-readme
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Index enforcer

Enforces conventions and builds/maintains the accountable wiki corpus.

An example agent that is both **enforcer** and **indexer**. It gates the repo
with the `structure_check` tool, (re)builds the wiki corpus with `build_corpus`
+ `link_corpus`, flags human-accountability gaps with `accountability_report`,
and fills *missing* summaries via `models/` -- never overwriting authored ones.

It is thin: policy + prompt only. The real work lives in `scripts/`, invoked as
**tools** (per the specs in `agents/tools/`, declared in `tools.md`); the model
comes from `models/`. The single public symbol is `enforce(...)`, returning an
`EnforceReport`. It **defaults to dry-run**: `enforce()` reports the plan + gaps
and writes nothing; `enforce(execute=True)` runs the deterministic build/link;
gap-fill additionally needs `fix_gaps=True`.
