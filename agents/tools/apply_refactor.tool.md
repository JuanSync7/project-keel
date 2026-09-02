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
updated: 2026-09-02
visibility: internal
canonical: true
tool_command: python3 scripts/apply_refactor.py --spec - --root . --gate verify --json
tool_effect: writes
---

# Apply refactor

## Command
`python3 scripts/apply_refactor.py --spec - --root . [--gate TARGET] [--dry-run] [--json]`
> Requires Python ≥3.10 (per `pyproject.toml`); an agent invokes it via its own interpreter (`sys.executable`), not a bare `python3`.

## Purpose
The refactor loop's **hands + safety net**. Given a JSON edit spec on stdin it
applies each edit atomically (each `find` must match its file exactly once),
runs a make gate, and — if the gate goes red — **rolls back every file** to its
original bytes. So a chunk is *accepted* only when the tree stays green; a chunk
that would break the build is reverted, never left half-applied. This is how
`agents/practice_refactor` cannot mark a chunk done unless it satisfies the very
`make verify` the gate encodes.

## When to use
- To apply one proposed, bounded refactor and keep the tree green either way.
- NOT to decide *which* edit to make (that is the agent's model step) and NOT to
  gate without editing (that is `run_make_target`).

## Args
| Flag | Required | Default | Meaning |
|------|----------|---------|---------|
| `--spec` | no | `-` (stdin) | path to the JSON edit spec, or `-` for stdin |
| `--root` | no | `.` | repo root the edit paths are relative to |
| `--gate` | no | spec `gate` or `verify` | make target to gate on (`none` skips) |
| `--dry-run` | no | off | validate + list the files, write nothing |
| `--timeout` | no | 1800 | gate timeout in seconds |
| `--json` | no | off | emit the result as JSON |

Spec shape: `{"practice": "...", "gate": "verify", "edits": [{"file": "p", "find": "...", "replace": "..."}] }` (an edit may use `"content"` for a whole-file replacement). A path that escapes `--root` is rejected before any write.

## Output
With `--json`, a result object: `{practice, gate, applied, rolled_back, files, gate_output}`. Exit 0 when applied (or dry-run), 1 when rolled back, 2 on a bad spec.

## Side effects
WRITES the files named in the spec — but **transactionally**: if the gate goes red
*or never returns a verdict* (a timeout, a hang, a killed `make`), every file is
restored to its original bytes, so a failed run leaves the tree exactly as it
found it. Runs the gate as a subprocess (`make <target>`); no model call. The one
window it cannot itself undo is a hard external kill (SIGKILL/OOM) of the doer
mid-write — that partial edit is surfaced by the next gate run, never kept as done.

## Used by
- agents/practice_refactor
- agents/doc_reviewer
