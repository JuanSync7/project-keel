---
title: Agents
kind: agent
layer: backend
status: template
owner: TBD
public_api: none
tags: []
summary: Autonomous / LLM agents (the 'brains') — reasoning, policy, prompts.
id: agents-readme
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Agents

Autonomous / LLM agents (the 'brains') — reasoning, policy, prompts.

Each agent is the decision-making core: prompts, policy, tool-use
logic. An agent needs a *model* to run on — it gets one from
`models/` (`get_model(name).run(prompt)`), so it never hardcodes a
provider. Keep transport (how the agent is *reached*) out of here —
that's `mcp/` and `api/`. Agents call into `src/` for real work and
into `evals/` for scoring. Default any state-changing action to a
dry run unless explicitly authorized.
