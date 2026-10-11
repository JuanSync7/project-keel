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
  `run_make_target.py`, `gate_evidence.py`, `run_evals.py` and
  `trace_requirements.py`; it stays 3.6-safe so the
  evidence writer can import it under an interpreter older than
  requires-python and still leave a red record.
  `traceability.py` is the fifth and `pytest_markers.py` the sixth; neither is
  ever run. `traceability.py` is the one home of the requirement-id grammar
  and the verdict rule, imported by `trace_requirements.py` and
  `tests/integration/test_requirement_traceability.py` so the command and the
  gate test cannot judge by different rules. `pytest_markers.py` is the one
  reader of marker calls from test source, imported by `traceability.py` and
  `tests/integration/test_e2e_coverage.py`. Both need the project interpreter
  and are not 3.6-safe. A second parser of an id anywhere else is a defect.
- Each script is self-describing (`--help`) and safe to run twice — which
  here means declared: `effect: writes` plus a `rerun:` its header can be held
  to (check_V), built and proven as `docs/guides/idempotency.md` sets out.
