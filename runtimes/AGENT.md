---
title: runtimes — agent rules
kind: rules
layer: backend
status: template
owner: TBD
summary: Local agent rules inside runtimes/.
id: runtimes-agent
created: 2026-06-22
updated: 2026-06-22
visibility: internal
canonical: true
---

# Agent rules — `runtimes/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- Every engine implements the `Runtime` contract; agents depend on the contract and pick an engine by name via `get_runtime`, never import a concrete engine.
- An engine adapter changes **execution, never semantics**: the dry-run effect-guard (`writes`/`model-call` steps are no-ops unless `execute=True`) and edge order must match the `inprocess` reference. The equivalence is pinned by `tests/unit/runtimes/test_runtime_equivalence.py`.
- A vendor/engine name (e.g. `langgraph`) appears **only inside its one adapter file** and its lazy registry thunk — never in `contracts.py`, `_inprocess.py`, `__init__.py`, or in `agents/`.
- A new engine's dependency is an **optional extra** in `pyproject.toml`, imported lazily — the default install and the pre-commit/CI path stay dependency-free.
- A `Step.effect` reuses the `tool_effect` vocabulary (`read-only`/`writes`/`model-call`, CONVENTIONS §10); keep `_inprocess.py` pure stdlib so it parses/runs everywhere.
