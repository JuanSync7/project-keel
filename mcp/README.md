---
title: MCP
kind: mcp
layer: backend
status: template
owner: TBD
public_api: none
tags: []
summary: Model Context Protocol servers — tool gateways over the app.
id: mcp-readme
created: 2026-06-17
updated: 2026-09-02
visibility: internal
canonical: true
---

# MCP

Model Context Protocol servers — tool gateways over the app.

Thin MCP servers that expose `src/`/`agents/` capabilities as tools.
Split read-only (Q&A) from state-changing (action) servers; the
action server defaults to dry-run. No business logic here — validate,
translate, and delegate.

## What ships here

| Member | Server | Tools | Delegates to | Not for |
|--------|--------|-------|--------------|---------|
| `action_server.py` | `keel-actions` (state-changing, dry-run) | `rebuild_index` | `scripts/jobs/rebuild_index.py` | Not for answering questions or reading the corpus — that is `qa_server.py` (`wiki_answer`); not for the wire or the tool registry — that is `protocol.py`. Its one tool shells out to the doer and regenerates the README-title index (`wiki/INDEX.md` by default), never `wiki/corpus.json` (that is `scripts/jobs/build_corpus.py` via `make site-data`); it writes only with `execute: true` and refuses an `out` that resolves outside the indexed tree. |
| `protocol.py` | — | — | the neutral `Tool`/`ToolServer` model + a JSON-RPC stdio loop | Not for hosting a tool: it registers none and has no `__main__` — a read-only tool goes in `qa_server.py`, a state-changing one in `action_server.py`, and both import this module. Not for HTTP or any other wire — that is `api/`; a second MCP host (the official `mcp` SDK, say) is a sibling binding over `ToolServer`, never an edit to `handle_message`. |
| `qa_server.py` | `keel-wiki-qa` (read-only) | `wiki_answer` | `agents/wiki_navigator` (cited answers) | Not for anything that writes or needs a dry run: read-only means no write to the tree, but it always makes the model call (`answer(..., execute=True)`) and has no `execute` gate — a state-changing or dry-run-gated tool belongs in `action_server.py`. Not for retrieval or synthesis logic — that stays in `agents/wiki_navigator`; not for JSON-RPC parsing — that is `protocol.py`. |

The wire is **JSON-RPC 2.0 over stdio**, implemented in pure stdlib in
`protocol.py` — the base install stays dependency-free (the official `mcp`
SDK is one optional way to host the same tools, never required). All behaviour
lives in `ToolServer`/`handle_message`, which the tests drive directly; the
stdio loop is the thin binding.

## Running it

An MCP client (e.g. Claude Code) launches a server as a subprocess and speaks
JSON-RPC on its stdin/stdout. Point the client at the server module run with
the project interpreter, for example:

```json
{
  "mcpServers": {
    "keel-wiki-qa": { "command": ".venv/bin/python", "args": ["mcp/qa_server.py"] },
    "keel-actions": { "command": ".venv/bin/python", "args": ["mcp/action_server.py"] }
  }
}
```

Select the Q&A model with `KEEL_MCP_MODEL` (e.g. `fake` for offline dev, or any
name from `models/`). The action server never writes unless a tool is called
with `execute: true`.
