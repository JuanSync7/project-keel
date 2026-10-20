---
title: agents/practice_refactor — agent rules
kind: rules
layer: backend
status: template
owner: TBD
summary: Local agent rules inside agents/practice_refactor/.
id: agents-practice-refactor-agent
created: 2026-07-07
updated: 2026-10-20
visibility: internal
canonical: true
---

# Agent rules — `agents/practice_refactor/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- Policy/prompt only. Invoke `scripts/` doers as **tools** via their CLI (per `agents/tools/` specs in `tools.md`); never `import` script logic. `refactor` is the only public symbol; keep prompt/policy in `_brain.py` private behind `__init__.py`.
- Get the model from `models/` (`get_model`); never name a provider. Read `config/practices.json` as DATA by path (json.load), never import it.
- Default to dry-run (`execute=False`): the read-only `walk` (query_corpus) and `baseline` (run_make_target) run so the report is real, but `propose` (model) and `apply` (writes) are skipped. Refactoring needs `execute=True`.
- Control flow is a neutral `Plan` (steps + edges; see `runtimes/`) executed by a `Runtime` — the dry-run effect-guard (`writes`/`model-call` steps are skipped unless `execute=True`) lives in the runtime, not in inline `if`s. `refactor(runtime=...)` selects the engine; default is the stdlib `inprocess` engine, never a vendor.
- **The gate is the definition of done.** A chunk is `refactored` only when `apply_refactor` keeps `make verify` green; a red gate rolls the edit back and the chunk is `skipped`. Never mark a chunk done on self-assessment (root `AGENT.md`; CONVENTIONS §17).
- **An edit cannot reach the judge.** `apply_refactor` refuses, before any write, an edit outside the chunk's own file (the run binds it with `--allow`) or to a path config/project.json `agents` protects (a check, a test, the Makefile, config, an ADR, an AGENT.md); the chunk is `skipped`. The gate is the run's `--gate` flag, never the reply's: a spec that names a gate is refused (`docs/guides/coding-practices.md` owns this policy).
- **Solve the practice, not the chunk.** Propose the smallest general edit toward the named practice; never hardcode to the one specimen (CONVENTIONS §18).
- The refactor loop is **durable**: one chunk per step, cursor-checkpointed, so a crash mid-refactor (an EDR SIGKILL) resumes via the checkpointer and accepted chunks are not re-proposed. `refactor` defaults to a `FileCheckpointer` under `wiki/.runtime` and auto-resumes a leftover snapshot.
