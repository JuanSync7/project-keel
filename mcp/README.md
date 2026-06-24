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
