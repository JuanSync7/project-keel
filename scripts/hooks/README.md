---
title: Hooks
kind: script
layer: n/a
status: template
owner: TBD
public_api: none
tags: [hooks, automation, triggers]
summary: Event-triggered doers — the scripts a hook fires. The trigger lives elsewhere.
id: scripts-hooks-readme
created: 2026-06-17
updated: 2026-09-02
visibility: internal
canonical: true
---

# Hooks

Event-triggered doers — the scripts a hook fires. The trigger lives elsewhere.

Event-triggered **doers**: the scripts that run *when something
happens*. The script here is the doer; the **trigger** is a thin,
vendor-specific adapter (`.pre-commit-config.yaml`, `.github/`,
`.claude/settings.json`, …) that only says "on event → call this
script" and holds no logic. Deterministic hooks are self-contained
here; LLM-backed hooks call an agent in `agents/` (which gets its
model from `models/`). `on_stop_triage.py` is the LLM example;
`on_stop_doc_review.py` is the one a trigger actually fires: `.claude/settings.json`
runs it when a turn ends, dry-run (deterministic, no model), and it prints the
doc reviewer's one-line report. Both treat an unavailable model as a stated skip.
