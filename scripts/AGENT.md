---
title: scripts — agent rules
kind: rules
layer: n/a
status: template
owner: TBD
summary: Local agent rules inside scripts/.
id: scripts-agent
created: 2026-06-17
updated: 2026-10-08
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
  which cannot import `src/`. `jobs/conflict_guard.py` is the third, and the
  only one that is never run: the `copier update` jobs in `jobs/` import it
  before anything else from the project, so it has no `--help`.
- Each script is self-describing (`--help`) and safe to run twice — which
  here means declared: `effect: writes` plus a `rerun:` its header can be held
  to (check_V), built and proven as `docs/guides/idempotency.md` sets out.
