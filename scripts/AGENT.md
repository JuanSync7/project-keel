---
title: scripts — agent rules
kind: rules
layer: n/a
status: template
owner: TBD
summary: Local agent rules inside scripts/.
id: scripts-agent
created: 2026-06-17
updated: 2026-10-11
visibility: internal
canonical: true
---

# Agent rules — `scripts/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- Scripts are entrypoints, not libraries — if `src/` needs it, it moves to `src/`.
  `check_structure.py` and `child_env.py` are the two shared modules here;
  `child_env.py` is imported from `models/`, `agents/` and `mcp/` as
  `scripts.child_env` because it must run under the 3.6 hook interpreter,
  which cannot import `src/`. `jobs/conflict_guard.py` is the third, and
  `git_tree.py` the fourth; neither is ever run, so neither has `--help`.
  The `copier update` jobs in `jobs/` import `conflict_guard.py` before
  anything else from the project, to refuse a job over a conflicted module it
  imports and the data files the job's modules declare reading.
  `git_tree.py` is the one definition of what git lists, imported by
  `run_make_target.py`, `gate_evidence.py` and `run_evals.py`; it stays 3.6-safe so the
  evidence writer can import it under an interpreter older than
  requires-python and still leave a red record.
- Each script is self-describing (`--help`) and safe to run twice — which
  here means declared: `effect: writes` plus a `rerun:` its header can be held
  to (check_V), built and proven as `docs/guides/idempotency.md` sets out.
