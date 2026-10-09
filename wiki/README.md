---
title: Wiki
kind: wiki
layer: n/a
status: template
owner: TBD
public_api: none
tags: []
summary: Generated browsable knowledge/index site over the repo.
id: wiki-readme
created: 2026-06-17
updated: 2026-10-09
visibility: internal
canonical: true
---

# Wiki

Generated browsable knowledge/index site over the repo.

A generated, browsable view of the code/docs (index, search, symbol
tree). It is a *view*, never a source of truth — regenerate it from
`src/`/`docs/`. Keep this dir: `mcp/qa_server.py` and the agents that
consult the corpus (wiki_navigator, index_enforcer, practice_refactor,
doc_reviewer) read `wiki/corpus.json`, and `make check-corpus`, which
`make check-all` runs, checks it.
