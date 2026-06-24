---
title: Models
kind: model
layer: backend
status: template
owner: TBD
public_api: none
tags: []
summary: Model backends the app/agents run on — adapters + registry behind one contract.
id: models-readme
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Models

Model backends the app/agents run on — adapters + registry behind one contract.

The catalog of **model backends** the system can run on. An agent is
reasoning/policy; it needs a *model* to actually run — this is where
those models live and how each is launched.

| Path | Role |
|------|------|
| `__init__.py` | public API — `get_model(name=None)` returns a backend |
| `contracts.py` | the `ModelBackend` ABC every adapter implements |
| `registry.py` | name -> adapter + the default model |
| `claude_code_headless.py` | adapter that runs Claude Code headless |
| `config/` | per-model config (default model name, launch flags) |

`agents/` depend on this dir: an agent asks the registry for a
backend by name and calls `.run(prompt)`. To add a provider (an
Anthropic API client, a local model), drop in an adapter that
implements `ModelBackend` and register it — no agent code changes.
