---
title: Run make target
kind: tool
layer: cross-cutting
status: stable
owner: platform-team
public_api: scripts/run_make_target.py
tags: [tool, gate, make, verify]
summary: Run one make target and report a structured pass/fail — the refactor loop's gate.
id: tool-run-make-target
created: 2026-07-07
updated: 2026-07-07
visibility: internal
canonical: true
tool_command: python3 scripts/run_make_target.py verify --json
tool_effect: read-only
---

# Run make target

## Command
`python3 scripts/run_make_target.py TARGET [--json] [--dir DIR] [--timeout S] [--make-arg K=V]`
> Requires Python ≥3.10 (per `pyproject.toml`); an agent invokes it via its own interpreter (`sys.executable`), not a bare `python3`.

## Purpose
The refactor loop's **gate**. It runs a single make target (the target name is
validated against an allowlist pattern — never a shell string) and reports a
structured `{target, ok, returncode, output}`. `agents/practice_refactor` runs
`make verify` through it once up front to establish a **green baseline**: a dirty
tree yields a dirty refactor, so if the gate is already red the agent stops and
surfaces it instead of editing on top of failures.

## When to use
- To verify the tree is green *before* refactoring (the baseline gate).
- To check any make target's pass/fail as data.
- NOT to apply edits (that is `apply_refactor`, which gates each edit itself).

## Args
| Flag | Required | Default | Meaning |
|------|----------|---------|---------|
| `TARGET` | yes | — | the make target to run (e.g. `verify`, `check`) |
| `--dir` | no | `.` | directory to run `make` in |
| `--json` | no | off | emit the result as JSON |
| `--timeout` | no | 1800 | gate timeout in seconds |
| `--make-arg` | no | — | extra `make` argument (repeatable, e.g. `PY=.venv/bin/python`) |

## Output
With `--json`, `{target, ok, returncode, output}` on stdout. Exit mirrors the
gate: 0 when the target passed, non-zero when it failed (2 for an unsafe target).

## Side effects
READ-ONLY with respect to tracked source: it runs a gate and reports the result;
it never edits source files. The target itself may touch generated/ignored
artifacts (test caches, build output) — never a source of truth. No model call.

## Used by
- agents/practice_refactor
