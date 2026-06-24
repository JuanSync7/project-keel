---
title: Agent tools
kind: doc
layer: cross-cutting
status: template
owner: TBD
public_api: none
tags: [tools, agents, adapters]
summary: Shared, thin TOOL.md tool-use specs — how an agent invokes a scripts/ doer.
id: agents-tools-readme
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Agent tools

Shared, thin TOOL.md tool-use specs — how an agent invokes a scripts/ doer.

Each `*.tool.md` is a **thin adapter**: it tells any LLM agent *how to
invoke* a doer in `scripts/` — the tool's logic stays in the script,
never here (same rule as transports in §7 and third-party tools in §9).
Tools live here because they are **shared across agents**; an agent
declares which it may use in its own `tools.md` manifest.

Each spec carries `kind: tool` frontmatter with `public_api` (the
wrapped script, validated to exist), `tool_command` (the exact argv),
and `tool_effect` (`read-only` | `writes` | `model-call`). Adding a
tool = add a `*.tool.md` here AND list it in the using agent's
`tools.md` (`## Used by` and the manifest row are bidirectional).
