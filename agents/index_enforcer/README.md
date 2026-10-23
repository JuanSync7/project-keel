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
updated: 2026-10-23
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
comes from `models/`. The entry point is `enforce(...)`, returning an
`EnforceReport`. The second public symbol, `summarize_gap(node, backend=b)`, is
the one model call per gap: the one-sentence summary the fill step writes. The eval harness (`evals/_doers.py`) drives it on a recording backend, so a replayed case judges the real prompt and parser and calls no model. It **defaults to dry-run**: `enforce()` reports the plan + gaps
and writes nothing; `enforce(execute=True)` runs the deterministic build/link;
gap-fill additionally needs `fix_gaps=True` and `max_model_calls`, the approved
count of model calls (a `ValueError` without it). Every fill goes through one
run's `models.ModelMeter`, so the call past the count raises
`models.CallCapReached` and is never made, and a saved run resumes only on the
same model with no more gaps left than the count (`models.approve_resume`,
else `models.RunNotApproved`); `tests/integration/test_index_enforcer_durability.py`
holds all three.
