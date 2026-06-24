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
updated: 2026-06-17
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
model from `models/`). `on_stop_triage.py` is the LLM example.
