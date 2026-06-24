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
updated: 2026-06-17
visibility: internal
canonical: true
---

# Wiki navigator

Answers questions from the wiki corpus with citations and provenance.

An example agent that answers a question by traversing the wiki corpus the
`index_enforcer` built. It retrieves a connected neighbourhood of nodes (tree +
entity/keyword links) with the read-only `query_corpus` tool, then synthesizes
an answer via `models/` -- citing every source.

It is thin: policy + prompt only. The single public symbol is `answer(...)`,
returning an `Answer` whose `citations` carry each source's `summary_source`
(authored vs generated) and `owner`/`owner_source`, so a reader can weight trust
and see accountability. It **defaults to dry-run**: retrieval always runs (so
`citations` is populated), but `answer(question)` returns the prompt it *would*
send; pass `execute=True` to call the model. It never surfaces
`confidential`/`restricted` nodes.
