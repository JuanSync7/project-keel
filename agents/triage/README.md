---
title: Triage agent
kind: agent
layer: backend
status: template
owner: TBD
public_api: agents/triage/__init__.py
tags: [agent, example, llm]
summary: Example LLM 'brain' that triages an event payload into a short summary.
id: agents-triage-readme
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Triage agent

Example LLM 'brain' that triages an event payload into a short summary.

An example agent **brain**: it triages an event payload (a failure, a
diff, a log) into a short summary. A thin doer in `scripts/hooks/` or
`scripts/jobs/` calls `triage(...)` — the only public symbol.

It holds reasoning/prompt only: it asks `models/` for a backend by
name and never hardcodes a provider. Per the repo rules it **defaults
to a dry run** — `triage(payload)` returns the prompt it *would* send;
pass `execute=True` to actually run a model.
