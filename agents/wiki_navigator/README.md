---
title: Wiki navigator
kind: agent
layer: backend
status: template
owner: TBD
public_api: agents/wiki_navigator/__init__.py
tags: [agent, wiki, retrieval, qa]
summary: Answers questions from the wiki corpus with citations and provenance.
id: agents-wiki-navigator-readme
created: 2026-06-17
updated: 2026-10-24
visibility: internal
canonical: true
---

# Wiki navigator

Answers questions from the wiki corpus with citations and provenance.

An example agent that answers a question by traversing the wiki corpus the
`index_enforcer` built. It retrieves a connected neighbourhood of nodes (tree +
entity/keyword links) with the read-only `query_corpus` tool, then synthesizes
an answer via `models/` -- citing every source.

It is thin: policy + prompt only. The entry point is `answer(...)`,
returning an `Answer` whose `citations` carry each source's `summary_source`
(authored vs generated) and `owner`/`owner_source`, so a reader can weight trust
and see accountability; a node that names no `owner_source` gives `None`,
unknown, never `none`, which claims nothing owns it. It **defaults to dry-run**: retrieval always runs (so
`citations` is populated), but `answer(question)` returns the prompt it *would*
send; pass `execute=True` to call the model. `answer(backend_factory=f)` builds the one backend with `f` from the model name instead of `models.get_model`, so a caller that counts calls across answers, as `mcp/qa_server.py` does with `models.SessionBudget`, sees each one. It never surfaces
`confidential`/`restricted` nodes. The second public symbol, `synthesize(question, nodes,
backend=b)`, is the one model call: it drops those nodes itself, so a caller
cannot hand the model one. The eval harness (`evals/_doers.py`) drives it on a
recording backend, so a replayed case judges the real prompt and calls no model.
