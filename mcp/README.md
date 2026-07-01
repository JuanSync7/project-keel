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
updated: 2026-06-17
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

| File | Server | Tools | Delegates to |
|------|--------|-------|--------------|
| `qa_server.py` | `keel-wiki-qa` (read-only) | `wiki_answer` | `agents/wiki_navigator` (cited answers) |
| `action_server.py` | `keel-actions` (state-changing, dry-run) | `rebuild_index` | `scripts/jobs/rebuild_index.py` |
| `protocol.py` | — | — | the neutral `Tool`/`ToolServer` model + a JSON-RPC stdio loop |

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
