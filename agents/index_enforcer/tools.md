---
title: index_enforcer — toolset
kind: agent
layer: backend
status: template
owner: TBD
public_api: none
tags: [agent, toolset, manifest]
summary: The shared tools agents/index_enforcer is permitted to invoke.
id: agents-index-enforcer-tools
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# index_enforcer — toolset

This agent may invoke ONLY the tools below. Each row points at a shared spec in
`agents/tools/`. Adding a tool = add a row here AND add this agent to that
spec's `## Used by` (the binding is bidirectional).

| Tool spec | Effect | Used for |
|-----------|--------|----------|
| `../tools/structure_check.tool.md` | read-only | gate the repo before indexing |
| `../tools/build_corpus.tool.md` | writes | (re)build the wiki corpus tree |
| `../tools/link_corpus.tool.md` | writes | add deterministic entity/keyword links |
| `../tools/accountability_report.tool.md` | read-only | enumerate owner gaps to flag |
