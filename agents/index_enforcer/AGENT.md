---
title: agents/index_enforcer — agent rules
kind: rules
layer: backend
status: template
owner: TBD
summary: Local agent rules inside agents/index_enforcer/.
id: agents-index-enforcer-agent
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Agent rules — `agents/index_enforcer/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- Policy/prompt only. Invoke `scripts/` doers as **tools** via their CLI (per `agents/tools/` specs in `tools.md`); never `import` script logic.
- Get the model from `models/` (`get_model`); never name a provider. Keep prompt/policy in `_brain.py` private behind `__init__.py`; `enforce` is the only public symbol.
- Default to dry-run (`execute=False`): no writes, no model calls. Build/link need `execute=True`; gap-fill additionally needs `fix_gaps=True`.
- Control flow is a neutral `Plan` (steps + edges; see `runtimes/`) executed by a `Runtime` — the dry-run effect-guard (`writes`/`model-call` steps are skipped unless `execute=True`) lives in the runtime, not in inline `if`s. `enforce(runtime=...)` selects the engine; default is the stdlib `inprocess` engine, never a vendor.
- The fill loop is **durable**: one gap per step, recomputed from the corpus (idempotent), so a crash mid-fill (an EDR SIGKILL) resumes via the checkpointer and already-filled gaps are not re-run. `enforce` defaults to a `FileCheckpointer` under `wiki/.runtime` and auto-resumes a leftover snapshot.
- Authored summaries and owners are canonical -- generation is a fallback for gaps only, and is always marked `generated`.
