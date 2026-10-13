---
title: scripts — agent rules
kind: rules
layer: n/a
status: template
owner: TBD
summary: Local agent rules inside scripts/.
id: scripts-agent
created: 2026-06-17
updated: 2026-10-13
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
  `trace_requirements.py`. It raises `NoGitError` only when git is not
  installed or there is no repository, and `GitFailedError` for every other
  git failure: catch the first to take a no-git path, and never catch the
  second to take one. It stays 3.6-safe so the
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
  `exit_codes.py` is the seventh, and is never run: the closed list of exit
  codes (`ExitCode`) and the one place a process ends. Import it by its bare
  name, never as `scripts.exit_codes`; it stays stdlib-only and 3.6-safe,
  because the hook interpreter runs scripts that import it.
  `run_date.py` is the eighth, and is never run: the one definition of the
  date a gate run calls today, imported by `gate_evidence.py`, which fixes it,
  `jobs/review_docs.py`, which reads it, and `check_structure.py`, whose
  check X reads its `policy` before any run. It stays stdlib-only and
  3.6-safe for the reason `git_tree.py` does. A second reader of the variable
  config/project.json `evidence.run_date.env` names anywhere else is a defect.
  `launch.py` is the one place that decides where a long script runs and
  the one writer of `launcher.durations_file`; `long_scripts.py` imports its
  config loader and record reader, so the proposal and the decision cannot
  read the block by different rules. A second reader of the `launcher` block
  anywhere else is a defect. Both stay stdlib-only and 3.6-safe.
- End every script through `exit_codes.py`. The entry line is
  `finish(main())`. `main` returns `ExitCode.SUCCESS`, or
  `report(<member>, <what failed>, <on which input>, <what to do next>)` for a
  failure, or `passthrough(<a wrapped tool's status>)`; code that is not
  `main` calls `fail(...)` with the same four arguments. Never write
  `sys.exit`, `raise SystemExit`, `os._exit`, `exit`, `quit` or an argparse
  `.exit(...)`: `tests/integration/test_exit_gate.py` fails each. A name
  `main` returns is bound by plain assignment only (`rc = report(...)`), never
  by a parameter, an unpacking, a loop or `+=`: the same test fails a return
  it cannot follow to a member. After
  adding a member, or a script to `make verify`, run `make exit-codes`;
  `make check-exit-codes` fails a stale table.
- Each script is self-describing (`--help`) and safe to run twice — which
  here means declared: `effect: writes` plus a `rerun:` its header can be held
  to (check_V), built and proven as `docs/guides/idempotency.md` sets out.
