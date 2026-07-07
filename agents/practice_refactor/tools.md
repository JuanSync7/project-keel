---
title: practice_refactor — toolset
kind: agent
layer: backend
status: template
owner: TBD
public_api: none
tags: [agent, toolset, manifest]
summary: The shared tools agents/practice_refactor is permitted to invoke.
id: agents-practice-refactor-tools
created: 2026-07-07
updated: 2026-07-07
visibility: internal
canonical: true
---

# practice_refactor — toolset

This agent may invoke ONLY the tools below. Each row points at a shared spec in
`agents/tools/`. Adding a tool = add a row here AND add this agent to that
spec's `## Used by` (the binding is bidirectional).

| Tool spec | Effect | Used for |
|-----------|--------|----------|
| `../tools/query_corpus.tool.md` | read-only | walk the KG for the practice's neighbourhood |
| `../tools/run_make_target.tool.md` | read-only | gate a green baseline before refactoring |
| `../tools/apply_refactor.tool.md` | writes | apply one bounded edit, gated + rolled back |
