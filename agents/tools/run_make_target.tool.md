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
updated: 2026-10-23
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
not one path-like word or carries a credential (`carries_credential` in
`scripts/child_env.py`, which judges user information such as
`http://user:password@host` and any value a `child_env.credential_value_patterns`
regular expression matches, such as a bearer header or a JWT), an allowlist `scripts/child_env.py` cannot build
or that would copy a value carrying a credential, and a tree without git. Every
refusal names the variable, and the pattern label it matched, and never quotes
its value. It passes the
`make_targets.gate_runner_var` variable (`RALPH=1` in keel) last, so a `[write]`
recipe's `$(WRITE_GUARD)` refuses whatever the caller supplied. It snapshots
what git lists before and after the run, each path's status and content, and a
green run that changed either is red, naming the paths. `agents/practice_refactor` runs `make verify` through it once
up front to establish a **green baseline**: a dirty tree yields a dirty
refactor, so if the gate is already red the agent stops and surfaces it instead
of editing on top of failures. The labels are defined in
`docs/adr/keel/K-0011-make-target-effect-labels.md`.

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
| `--timeout` | no | `make_targets.gate_timeout_seconds` | gate timeout in seconds, a whole number >= 1; below 1 is refused (exit 2) |
| `--make-arg` | no | — | extra `NAME=VALUE` make variable (repeatable, e.g. `PY=.venv/bin/python`); NAME must be in `make_targets.gate_vars` and VALUE one path-like word (no spaces, `;`, `$`, quotes, or leading `-`/`+`/`@`) that carries no credential; anything else is refused, naming NAME and never VALUE |

## Output
With `--json`, `{target, ok, returncode, output, effects, changed, refused,
timed_out, leaked, escaped}` on stdout. `timed_out` is true when make did not
finish within the limit. `leaked` lists `<pid> <command>` for each process still
running in make's session after make exited; any entry makes the run red.
`escaped` lists `<pid> <command>` for each process outside make's session that
still held make's output when the run ended, or `(unlisted)` when `/proc` did
not show the holder; any entry makes the run red, and the runner signals none of
them. `effects` is the target's closed label; `changed` lists the paths a run
changed; `refused` is the reason when the runner did not run make, and `null`
otherwise. Exit 0 when the target passed and changed nothing, 1 when it was red,
timed out, changed the tree, leaked a process or left one holding its output, 2 when it was refused or the name was unsafe, 14
when `make_targets.gate_timeout_seconds` or `make_targets.gate_stop_grace_seconds`
is not a whole number >= 1, and 130 when it was interrupted.
A `make_targets.gate_vars` value present in the caller's environment and not
given as `--make-arg` is forwarded on make's command line under the same
one-word rule; one that is not a one-word path, or that carries a credential,
is refused (exit 2), even when `child_env.credentialed_values` opts the variable
in, because make hands its command line to every recipe.

## Time limit and stopping
make runs in a session of its own. When the limit passes, or the runner gets
Ctrl-C, SIGTERM or SIGHUP, it sends SIGTERM to every process in make's session
(make, and the pytest, copier or uvicorn it started), in make's process group
or in one a member moved to while staying in the session, as GNU `timeout`
does; it waits `make_targets.gate_stop_grace_seconds` (10 in keel), then sends
SIGKILL to whatever in the session is still alive. A second Ctrl-C or SIGTERM during that
wait cuts it short and still sends the SIGKILL. A signal the caller set to be
ignored (for example SIGHUP under `nohup`) stays ignored. The limit is
`--timeout`, else `make_targets.gate_timeout_seconds` (14400 s in keel: a full
`make verify` measured 3 h 12 min on the slowest host, and 4 h leaves a quarter
of that again as headroom).

The run ends when make exits, not when make's output closes: a background job
that still holds the output open does not hold the run to the limit, and make's
own status is kept. A process still in the session half a second after make
exits is ended the same way and listed in `leaked`: a make that exited 0 is then red,
naming each leftover, because a gate target must stop every process it starts;
a make that failed keeps its own status. A process that has exited but is not
yet reaped (a zombie) runs nothing and is not a leftover. Membership is read
from `/proc`; on a host without it, a group that answers signal 0 counts as
alive and its leftovers are listed as `(unlisted)`, and a process that moved
to a group of its own is not seen.

The runner signals only make's session, and only while make is unreaped. make
is kept as a zombie (`os.waitid` with `WNOWAIT`) until the session has been
ended and the output read, so its process id, which is the session and group
id, cannot pass to a new process while a signal can still go to it; once make
is reaped, a stop signal sends nothing. A group a member moved to is signalled
by the id `/proc` listed just before, which could pass to a new process only if
every member of that group exited and the id was handed out again in between.
Where Python has no `os.waitid`, make is reaped as it exits, so the runner
signals nothing after that: a leftover is named in `leaked` as still running,
with the `kill` command that ends it. A Ctrl-C, SIGTERM or SIGHUP that lands
while make is being started is held until the runner has make's process id,
and then acts, so it cannot leave make running. Output still
open after the session ends is held by a process that left the session (with
`setsid`, for example). The runner stops reading it, names each holder in
`escaped` and fails the run, exit 1, with the `kill` command that ends them,
even when make exited 0, because evidence that a target started a process no
one stops is not a pass. It never signals a holder itself: outside make's
session it cannot tell the target's process from the caller's.
A runner killed with SIGKILL cannot end the session, so make's session outlives
it.

## Side effects
READ-ONLY: it never edits a file itself, and it refuses any target whose label
says it rewrites the tree or changes shared state. A target it runs may write
files git ignores (test caches, `wiki/corpus.json`); a write git would list
turns the run red. No model call. make and git run with the allowlisted
environment from `scripts/child_env.py`, never the caller's whole environment.

## Used by
- agents/practice_refactor
- agents/doc_reviewer
