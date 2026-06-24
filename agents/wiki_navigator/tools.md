---
title: wiki_navigator — toolset
kind: agent
layer: backend
status: template
owner: TBD
public_api: none
tags: [agent, toolset, manifest]
summary: The shared tools agents/wiki_navigator is permitted to invoke.
id: agents-wiki-navigator-tools
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# wiki_navigator — toolset

This agent may invoke ONLY the tools below. Each row points at a shared spec in
`agents/tools/`. Adding a tool = add a row here AND add this agent to that
spec's `## Used by` (the binding is bidirectional).

| Tool spec | Effect | Used for |
|-----------|--------|----------|
| `../tools/query_corpus.tool.md` | read-only | retrieve candidate nodes for a question |
