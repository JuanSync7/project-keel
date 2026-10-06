---
title: Run make target
kind: tool
layer: cross-cutting
status: stable
owner: platform-team
public_api: scripts/run_make_target.py
tags: [tool, gate, make, verify]
summary: Run one make target a gate may run (by its effect label) and report a structured pass/fail that also fails a run which changed the tree — the refactor loop's gate.
id: tool-run-make-target
created: 2026-07-07
updated: 2026-10-06
visibility: internal
canonical: true
tool_command: python3 scripts/run_make_target.py verify --json
tool_effect: read-only
---

# Run make target

## Command
`python3 scripts/run_make_target.py TARGET [--json] [--dir DIR] [--timeout S] [--make-arg NAME=VALUE]`
> Requires Python ≥3.10 (per `pyproject.toml`); an agent invokes it via its own interpreter (`sys.executable`), not a bare `python3`.

## Purpose
The refactor loop's **read-only gate**. It runs a single make target only when
that target's effect label, closed over its prerequisites and `$(MAKE)` calls,
is inside `config/project.json` `make_targets.gate_effects` (`[local]` and
`[read]` in keel). Before make runs it refuses an unknown or unlabelled target,
a `[tree]` or `[write]` one, an extra argument that is not `NAME=VALUE` (so `-f`
cannot point make at another makefile), a variable that
`make_targets.gate_vars` does not name (`PY` in keel; never `MAKEFILES`,
`MAKEFLAGS`, `SHELL`, `WRITE_GUARD` or an unattended variable) or whose value is
not one path-like word, and a tree without git. It passes the
`make_targets.gate_runner_var` variable (`RALPH=1` in keel) last, so a `[write]`
recipe's `$(WRITE_GUARD)` refuses whatever the caller supplied. It snapshots
what git lists before and after the run, each path's status and content, and a
green run that changed either is red, naming the paths. `agents/practice_refactor` runs `make verify` through it once
up front to establish a **green baseline**: a dirty tree yields a dirty
refactor, so if the gate is already red the agent stops and surfaces it instead
of editing on top of failures. The labels are defined in
`docs/adr/0011-make-target-effect-labels.md`.

## When to use
- To verify the tree is green *before* refactoring (the baseline gate).
- To check a `[local]` or `[read]` make target's pass/fail as data, with proof
  that it left the tree alone.
- NOT to apply edits (that is `apply_refactor`, which gates each edit through
  this same runner).
- NOT to run a `[tree]` or `[write]` target such as `make fmt`; it refuses them,
  and a person runs those with plain `make`.

## Args
| Flag | Required | Default | Meaning |
|------|----------|---------|---------|
| `TARGET` | yes | — | the make target to run (e.g. `verify`, `check`) |
| `--dir` | no | `.` | directory to run `make` in |
| `--json` | no | off | emit the result as JSON |
| `--timeout` | no | 1800 | gate timeout in seconds |
| `--make-arg` | no | — | extra `NAME=VALUE` make variable (repeatable, e.g. `PY=.venv/bin/python`); NAME must be in `make_targets.gate_vars` and VALUE one path-like word (no spaces, `;`, `$`, quotes, or leading `-`/`+`/`@`); anything else is refused |

## Output
With `--json`, `{target, ok, returncode, output, effects, changed, refused}` on
stdout. `effects` is the target's closed label; `changed` lists the paths a run
changed; `refused` is the reason when the runner did not run make, and `null`
otherwise. Exit 0 when the target passed and changed nothing, 1 when it was red,
timed out or changed the tree, 2 when it was refused or the name was unsafe.

## Side effects
READ-ONLY: it never edits a file itself, and it refuses any target whose label
says it rewrites the tree or changes shared state. A target it runs may write
files git ignores (test caches, `wiki/corpus.json`); a write git would list
turns the run red. No model call.

## Used by
- agents/practice_refactor
- agents/doc_reviewer
