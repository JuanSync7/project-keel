---
title: Apply refactor
kind: tool
layer: cross-cutting
status: stable
owner: platform-team
public_api: scripts/apply_refactor.py
tags: [tool, refactor, gate, apply, rollback]
summary: Apply one bounded edit spec atomically, run a make gate, and roll back every file unless it stays green.
id: tool-apply-refactor
created: 2026-07-07
updated: 2026-10-23
visibility: internal
canonical: true
tool_command: python3 scripts/apply_refactor.py --spec - --root . --gate verify --json
tool_effect: writes
---

# Apply refactor

## Command
`python3 scripts/apply_refactor.py --spec - --root . [--gate TARGET] [--allow FILE]... [--dry-run] [--json]`
> Requires Python ≥3.10 (per `pyproject.toml`); an agent invokes it via its own interpreter (`sys.executable`), not a bare `python3`.

## Purpose
The refactor loop's **hands + safety net**. Given a JSON edit spec on stdin it
applies each edit atomically (each `find` must match its file exactly once),
runs a make gate through `scripts/run_make_target.py`, and — if the gate goes
red — **rolls back every file** to its original bytes. The runner refuses a gate
labelled wider than `config/project.json` `make_targets.gate_effects` (`--gate
fmt` is red, not a pass) and fails a gate run that changed the tree, naming the
paths in `gate_output`. So a chunk is *accepted* only when the tree stays green; a chunk
that would break the build is reverted, never left half-applied. This is how
`agents/practice_refactor` cannot mark a chunk done unless it satisfies the very
`make verify` the gate encodes.

## When to use
- To apply one proposed, bounded refactor and keep the tree green either way.
- NOT to decide *which* edit to make (that is the agent's model step) and NOT to
  gate without editing (that is `run_make_target`).
- NOT for editing a check, a test, the Makefile, config, an ADR or an AGENT.md:
  those are refused; propose the change to their owner instead (R-AGT-33).
- NOT for creating a file, or editing one git does not track (git's own state,
  `.venv`, `node_modules`, an ignored file): those are refused; a person adds a
  new file with `git add` first.

## Args
| Flag | Required | Default | Meaning |
|------|----------|---------|---------|
| `--spec` | no | `-` (stdin) | path to the JSON edit spec, or `-` for stdin |
| `--root` | no | `.` | repo root the edit paths are relative to |
| `--gate` | no | `verify` | make target to gate on; `none` skips the gate and is a human caller's flag, never an agent's |
| `--allow` | no | none (repeatable) | a file this run may edit; an edit to any other file is refused before any write |
| `--dry-run` | no | off | validate + list the files, write nothing |
| `--timeout` | no | `make_targets.gate_timeout_seconds` | gate timeout in seconds, passed to `run_make_target`; a whole number from 1 to 604800, else refused (exit 2) before any edit |
| `--json` | no | off | emit the result as JSON |

Spec shape: `{"practice": "...", "edits": [{"file": "p", "find": "...", "replace": "..."}] }` (an edit may use `"content"` for a whole-file replacement). The gate is the caller's `--gate`, never the spec's.

Before any write, and so in a dry run too, an edit is refused when its path:
- escapes `--root`;
- has a `..` part or is absolute;
- is protected by config/project.json `agents`, judged on the path as written
  and again on its realpath, so a symlink cannot launder a judge file: a name
  or glob in `agents.protected_names` refuses in any directory, else a name or
  glob in `agents.editable_names` (a `README.md`) is allowed, else a path under
  `agents.protected_paths` refuses;
- is not named by an `--allow` flag, when the run passed any;
- does not exist;
- has more than one hard link;
- names a file git does not track, or a root where git cannot say, whatever
  `agents` lists.

Two spellings of one file (`src/m.py`, `./src/m.py`) are planned as one file,
so their edits compose in order.

A spec is refused whole when it, or one of its edits, carries an unknown key,
and when it names a `gate`: a spec that still names one is an old caller, and
dropping the key silently would let the reply believe it chose the gate.

## Output
With `--json`, a result object: `{practice, gate, applied, rolled_back, files, gate_output}`. Exit 0 when applied (or dry-run), 1 when rolled back, 2 on a bad or refused spec, 14 when config/project.json `agents` is a config fault (the message names the key).

## Side effects
WRITES the files named in the spec — but **transactionally**: if the gate goes red
*or never returns a verdict* (a timeout, a hang, a killed `make`), every file is
restored to its original bytes, so a failed run leaves the tree exactly as it
found it. Runs the gate through `run_make_target` (`make <target>` as a subprocess); no model call. The one
window it cannot itself undo is a hard external kill (SIGKILL/OOM) of the doer
mid-write — that partial edit is surfaced by the next gate run, never kept as done.

## Used by
- agents/practice_refactor
- agents/doc_reviewer
