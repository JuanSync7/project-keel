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
updated: 2026-11-14
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
same model with no more fills left than the count (`models.approve_resume`,
else `models.RunNotApproved`), counted under the root the saved run fills;
`tests/integration/test_index_enforcer_durability.py` holds all three. The fill
sends only gaps that `scripts/config_loader.py` `is_served_now` serves: the
stricter of the corpus level and the level the gap's file states on disk now,
read by `scripts/corpus_level.py` `stated_now`, must be in `config/project.json`
`corpus.served_visibilities`. A confidential gap, one that states no level,
or one whose file is now stricter or cannot be read is reported but never
filled, so its text reaches no prompt (the same test file holds it). A nonzero
`build_corpus.py` or `link_corpus.py` raises `ToolReportUnreadable` before the
report step, so no run fills from a corpus that failed to build.

The commit writes into the corpus on disk, never over it. At commit time it
reads `wiki/corpus.json` under the run's root and copies each summary the run
generated onto the node with the same `node_id`, only while that node is still
a gap that the fill would send now and has the same `path` and `text_excerpt`
the summary was made from. Any other filled summary is dropped, an authored
summary is never touched, and no node or edge is added or removed. A resumed run
therefore keeps a corpus built after the crash, and a second commit of the same
inputs writes the same bytes. `EnforceReport.gaps_filled` counts only the
summaries written. If the corpus is absent at commit, the run raises
`ToolReportUnreadable` before any write and keeps its snapshot, so the summaries
it paid for resume once the corpus is rebuilt. The durability test file holds
these cases.

Owner reports pass through `scripts/tool_reports.py` `read_report`: blank,
non-JSON, deeply nested output or anything but a list of objects raises
`ToolReportUnreadable`, a `RuntimeError` with the exit helper's three parts,
naming the tool, status, root, stderr and remedy. A nonzero owner status is
refused before decoding, fill or commit. A nonzero structure-gate status with
no `ERROR ` lines raises the same error before build. Any nonzero status with
at least one `ERROR ` line is read as a negative verdict, so a crash that
prints one still reads as a tree that is not clean and stops build and fill.
With no corpus, the owner tool returns
`[]` and the dry run reports no owner gaps without writing.
`tests/integration/test_index_enforcer_durability.py` holds these cases.
