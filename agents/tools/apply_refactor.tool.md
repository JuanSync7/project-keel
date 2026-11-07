---
title: Apply refactor
kind: tool
layer: cross-cutting
status: stable
owner: platform-team
public_api: scripts/apply_refactor.py
tags: [tool, refactor, gate, apply, rollback]
summary: Recover interrupted refactors, then journal one bounded spec and commit it after a green gate; retain failed restores for replay.
id: tool-apply-refactor
created: 2026-07-07
updated: 2026-11-07
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
validates each edit before writing (each `find` must match its file exactly once).
It recovers pending originals under an exclusive nonblocking lock before reading
stdin or a spec file, then plans and applies that proposal in the same run.
The required `refactor.journal_path` names an ignored, untracked journal
(default manifest: `.evidence/refactor-journal.json`); its sibling `.lock` stays
in place. Contention refuses with exit 1, `lock_busy: true` and a retry action; both agents stop.
The journal records raw prior bytes or absence, modes, prior and intended SHA-256,
checkout identity and `.refactor-tmp-` directories. Planning uses universal
newlines: a `find` containing LF matches a CRLF original, and output keeps its
uniform newline convention. Mixed conventions are refused.
Prepared publication precedes every target write. Each publication writes a
sibling temporary, fsyncs it, replaces the destination and fsyncs its directory.
The states are prepared, applied after all targets, and committed after a green
`scripts/run_make_target.py` gate. A red gate or apply error restores originals;
startup replays any pre-commit interruption, including one after a green gate.
If committed publication fails, the journal is re-saved as applied before restoration.
Restoration still runs if that re-save also fails.
A committed journal is cleaned without undo and its cleanup is logged to stderr. Replay removes orphan temporaries
and only removes the journal after all restores succeed. A failed restore raises
`RollbackError` after trying every target and retains the evidence for retry.
The gate waits on a stdin pipe until its process-group id is durably journalled.
A live recorded gate process group (named by id), conflicting bytes or corrupt evidence
refuses recovery with `journal_conflict: true`. Both agents stop and surface it.
The gate runner refuses wider effect labels and fails a green gate that changed
the tree. A chunk is accepted only after committed is durable.

`--recover` replays or cleans the journal and exits without reading a spec or stdin.
A human may abandon even corrupt evidence with `--discard-journal --yes`; this
unlinks only the configured journal and leaves every target untouched. Without
`--yes`, discard refuses before creating artifacts. These modes and `--dry-run`
are mutually exclusive. Both agents keep their existing argument sets.

## When to use
- To apply one proposed, bounded refactor with a durable journal and restoration
  on red; inspect any restore failure before another run.
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
| `--dry-run` | no | off | open existing evidence and lock read-only; create neither, clean no temporaries; report pending recovery without applying a proposal, otherwise validate and list files |
| `--timeout` | no | `make_targets.gate_timeout_seconds` | gate timeout in seconds, passed to `run_make_target`; a whole number from 1 to 604800, else refused (exit 2) before any edit |
| `--recover` | no | off | replay or clean the journal and exit without reading a spec or stdin |
| `--discard-journal` | no | off | human only: delete the journal without touching targets; requires `--yes` |
| `--yes` | no | off | human confirmation for `--discard-journal`; refused alone |
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
With `--json`, a result object: `{practice, gate, applied, rolled_back, files, gate_output, recovered}`.
`recovered` lists paths restored at startup, independently of `applied`.
`rolled_back: true` means every planned original was restored byte for byte.
Recovery/discard JSON carries `{files: [], recovered, recovery_only, discarded_journal}`.
A repeated recovery restores no paths and changes no target bytes or modes.
Exit 0 when applied (or dry-run, recovery or confirmed discard), 1 on a red gate, restore failure, lock contention
or journal conflict, 2 on a refused spec, and 14 on a config fault.
A conflicting-journal refusal carries `journal_conflict: true` and an `error` naming the
configured journal and `--discard-journal --yes`. Preserve the evidence and
reconcile it before retrying, or explicitly abandon recovery while keeping targets. Lock contention carries `lock_busy: true`; both agents stop on either flag.
Failed restores report `RollbackError` and retain the journal.
Error reports retain `recovered` if reading or planning the next spec fails.

## Side effects
WRITES the journal, its persistent lock and planned targets. Replacement preserves
file modes; it promises neither owner nor ACL preservation. Recovery can unlink
an interrupted creation or recreate a deleted original from saved bytes, though
proposals still refuse creation and deletion. No timestamps or permanent process
ids are stored; the gate process-group id is transient while it runs.
Journal, target and recovery fsyncs consume `agents.tool_gate_margin_seconds`.
The transaction provides replay of planned targets, without reader isolation or
restoration of unrelated gate writes. Runs one make gate through
`run_make_target`; no model call.

## Used by
- agents/practice_refactor
- agents/doc_reviewer
