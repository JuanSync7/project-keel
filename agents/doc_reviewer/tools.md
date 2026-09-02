---
title: doc_reviewer — toolset
kind: agent
layer: backend
status: template
owner: TBD
public_api: none
tags: [agent, toolset, manifest]
summary: The shared tools agents/doc_reviewer is permitted to invoke.
id: agents-doc-reviewer-tools
created: 2026-09-02
updated: 2026-09-02
visibility: internal
canonical: true
---

# doc_reviewer — toolset

This agent may invoke ONLY the tools below. Each row points at a shared spec in
`agents/tools/`. Adding a tool = add a row here AND add this agent to that
spec's `## Used by` (the binding is bidirectional).

| Tool spec | Effect | Used for |
|-----------|--------|----------|
| `../tools/review_docs.tool.md` | read-only | the deterministic findings: stale stamps, unresolved mentions, roster rows |
| `../tools/query_corpus.tool.md` | read-only | the style guide's rule nodes, from the corpus |
| `../tools/run_make_target.tool.md` | read-only | gate a green `check-docs` baseline before editing |
| `../tools/apply_refactor.tool.md` | writes | apply one bounded edit, gated on `check-docs` + rolled back |
