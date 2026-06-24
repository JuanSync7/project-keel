---
title: agents/triage — agent rules
kind: rules
layer: backend
status: template
owner: TBD
summary: Local agent rules inside agents/triage/.
id: agents-triage-agent
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Agent rules — `agents/triage/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- This package is reasoning/prompt only. Get the model from `models/` (`get_model`); never name a provider here.
- `triage()` is the only public symbol — keep prompt/policy in `_brain.py` private behind `__init__.py`.
- Default to dry-run (`execute=False`); calling a model is the authorized path, not the default.
