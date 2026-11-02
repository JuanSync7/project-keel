---
title: Shell style (how shell scripts are written here)
kind: doc
layer: n/a
status: template
owner: TBD
tags: [practices, style, readability, robustness, guide]
summary: The canonical statement of how a shell script is written in this project — the opening comment block the corpus reads, the re-exec line that puts the script under the child environment allowlist, the exit helper every ending goes through, a configured value read through scripts/config_get.py, the lint, format and test tools behind make targets, and what each of those gates cannot see. The provable floor is gated (check_O, check_V, check_X, test_exit_gate, test_config_reads_gate, scripts/shell_gate.py); this guide is the judgment above it.
id: docs-guides-shell-style
created: 2026-11-02
updated: 2026-11-02
visibility: internal
canonical: true
---

# Shell style — how shell scripts are written here

A shell script here obeys the contract a Python module obeys, as
[python-style](python-style.md) states it: readable before robust before fast,
a header a reader can trust, and no silent failure. Shell has no syntax tree
the gates can walk, so its rules are stated as lines a reader can match. This
guide says what each rule asks, which gate holds it, and what that gate cannot
see. Where a gate and this guide disagree, the gate wins and this guide is the
thing to fix.

## 0. When to write shell at all

Write shell for glue: a script that runs other tools in order and passes their
status on. Write Python once a script parses data, holds state across steps, or
needs a value with a type, because every gate in this project reads Python
more closely than shell. Keel's own gates are Python for that reason, and
config/project.json `shell.no_scripts` records it. This is judgment; no gate
decides it.

## 1. A script that passes every gate

```sh
#!/bin/sh
# title: pad_report — list the pads the pinmux spec leaves unassigned
# summary: Reads the pad CSV the KEYS row `pads.csv` names, prints each unassigned pad, and exits FAILURE when any is.
# effect: read-only
[ "${KEEL_CHILD_ENV-}" = "$$" ] || exec python3 "$(dirname "$0")/child_exec.py" "$0" "$@"
# shellcheck source=/dev/null
. "$(dirname "$0")/exit_codes.sh"

csv=$(python3 "$(dirname "$0")/config_get.py" pads.csv) || exit_passthrough "$?"
unassigned=$(awk -F, '$2 == "" { print $1 }' "$csv")
if [ -n "$unassigned" ]; then
    printf '%s\n' "$unassigned"
    exit_fail "$EXIT_FAILURE" "pad_report: pads are unassigned" "$csv" \
        "assign each pad printed above in the spec, then run it again"
fi
exit "$EXIT_SUCCESS"
```

The rest of this guide takes those lines one at a time. The sample lives in
`scripts/`, beside the two helpers it names; `pads.csv` is a row your project
adds to `scripts/config_loader.py` `KEYS`, not one keel ships.

## 2. The header (gated — `check_O`, `check_V`)

After the `#!` line, the file opens with a comment block, each line starting
with `#`, up to the first line that does not. `check_O` requires a non-empty
`title:` and `summary:` in that block, in every shell file under the code
roots, whatever `shell.enabled` says (CONVENTIONS §1). The block is read with
the grammar a Python module header uses, one field to a line, so a summary
wrapped onto a second line loses its tail.

Every shell script outside `tests/` also states `effect:`, one of
`read-only`, `writes` or `model-call`. `check_V` fails a script that does not
state one, because no detector reads shell, so the header is the one place a
reader learns whether the script writes. A script that writes adds `rerun:`
(`fixed-point`, `append-only` or `unsafe`), and a `fixed-point` claim names a
`rerun_proof:` that resolves, as [idempotency](idempotency.md) describes.

**What the gate cannot see.** Whether the claim is true. `check_V` checks a
Python module's `effect:` against the writes it finds in the code; for shell
it checks only that the field is present and in the vocabulary.

## 3. The first command (gated — `check_X`)

The first line that is neither blank nor a comment is the re-exec line
`REEXEC_LINE` from `scripts/child_exec.py`, character for character, except
that any path ending in `/child_exec.py` may stand for the helper's. That line
hands the script to `scripts/child_exec.py` unless `KEEL_CHILD_ENV` already
holds the script's own process id. The helper then starts the script again
under the environment `scripts/child_env.py` builds, so the body runs once,
under the allowlist, and every command it starts inherits that environment
rather than every credential its caller holds.
`docs/adr/keel/K-0012-child-process-environment-allowlist.md` is the decision.

A variable the script or its tools need goes in config/project.json
`child_env.names`, exactly as for a Python spawn. Do not export it from the
caller and expect it to arrive.

**What the gate cannot see.** `check_X` walks every top-level directory but
`tests/`, so a shell file at the repository root and anything under `tests/`
are not held to the line. The re-exec costs one Python start per script. It is
defence-in-depth, not a sandbox: a command the script runs can still read any
file the user can.

## 4. How a script ends (gated — `tests/integration/test_exit_gate.py`)

A script sources the generated helper `scripts/exit_codes.sh` (by a path ending
in `/exit_codes.sh`) before its first ending, and ends in one of three ways:

- `exit "$EXIT_<NAME>"`, with a member of `scripts/exit_codes.py` `ExitCode`;
- `exit_fail "$EXIT_<NAME>" WHAT ON NEXT` for a failure, which prints
  `WHAT: ON; NEXT` to stderr first; the code is never `SUCCESS` and no part is
  blank;
- `exit_passthrough "$?"` for a wrapped tool's status, or of a name that a
  bare `name=$?` bound earlier in the main shell and that is otherwise only
  read as `$name`.

The `# shellcheck source=/dev/null` line above the source line is what lets
`make lint-sh` pass. The linter runs without `-x`, so it does not follow a
sourced file, and it reports a source path it cannot follow, built from
`$(dirname "$0")`, as SC1091, which fails the target. The helper needs no
lint of its own here, because `make check-exit-codes` holds it to the enum.

The gate fails `exit 3`, `exit $?`, a bare `exit`, a `return` of a number,
`eval`, and a command named by an expansion (`$x 3`), each at its file and
line, because it cannot tell what they end with. It also fails a line that
ends with a carriage return: save the file with LF line endings. `make
check-exit-codes` keeps the helper in step with the enum, so never edit
`scripts/exit_codes.sh` by hand; `make exit-codes-sh` regenerates it.

**What the gate cannot see.** A `set -e`, `trap`, `exec`, `kill` or
`sh -c` string; a script that falls off its end after some other ending; a
held status name spelled in pieces. Whether `WHAT ON NEXT` helps its reader is
judgment: say what failed, on which input, and what to do next, as a Python
`report` does. `docs/guides/deterministic-checks.md` lists the gate's whole
reach.

## 5. A configured value (gated — `tests/integration/test_config_reads_gate.py`)

A script prints a value with `scripts/config_get.py KEY`, where KEY is the
dotted path of a `scripts/config_loader.py` `KEYS` row, and never names
config/project.json or config/practices.json itself. `scripts/config_get.py`
prints a string as written and anything else as canonical JSON, on one line of
stdout. It refuses a secret row without reading it, because a printed secret
lands in a log; the program that needs a secret reads it from its environment.
A key no row declares is exit 2, and a missing or wrong value is exit 14 with
the loader's own lines on stderr, so pass the status on with
`exit_passthrough "$?"` rather than continue with an empty value.
`docs/adr/keel/K-0022-one-config-loader.md` is the decision.

The gate fails a shell script under config/project.json `config_reads.roots`
whose code names a declared config file; `config_reads.allowed` is the one
excuse, with its reason.

**What the gate cannot see.** It cuts a line at a `#` that opens a word, so a
`#` inside quotes is cut too; that can hide a read but never invents one. A
path the script builds from parts is not seen.

## 6. Lint, format and test (gated — `scripts/shell_gate.py`)

| Target | Role | config/project.json key | Rides |
|---|---|---|---|
| `make lint-sh` | linter | `shell.linter` (shellcheck) | `make lint`, `make verify` |
| `make fmt-check-sh` | formatter, checking | `shell.formatter` (shfmt) | `make lint`, `make verify` |
| `make fmt-sh` | formatter, rewriting in place | `shell.formatter` (shfmt) | nothing; a `[tree]` target you run |
| `make test-sh` | test runner | `shell.test_runner` (bats) | `make verify` |

A file is a shell script when it ends in a `shell.script_suffixes` suffix or
opens with a shebang whose interpreter is one of `shell.shebang_shells`, and a
test when it ends in a `shell.test_suffixes` suffix. `shell.excluded_paths`
maps a path, such as a vendored script, to the reason it is never judged.
Shell scripts with no test file are exit 13, because a pass over zero tests
proves nothing; so is a project with no shell file at all, unless
`shell.no_scripts` gives the reason. `shell.enabled` false (the copier answer
`shell`) makes every shell target say so and run no tool. A tool named in
config that `scripts/shell_gate.py` has no adapter for is exit 14, and one it
cannot find is exit 11, never a skip.

Quote every expansion (`"$csv"`, not `$csv`); the linter flags the rest, and
its finding is the tool's own status.

## 7. What is enforced, advised, and judged

| Concern | Tier | Where |
|---|---|---|
| Header `title:` and `summary:` | gate | `check_O` |
| `effect:` stated; `rerun:` and a resolving `rerun_proof:` for a writer | gate | `check_V` |
| The re-exec line is the first command | gate | `check_X` |
| Endings go through `scripts/exit_codes.sh`; LF line endings | gate | `tests/integration/test_exit_gate.py` |
| A configured value is read through `scripts/config_get.py` | gate | `tests/integration/test_config_reads_gate.py` |
| Lint, format, tests exist and pass | gate | `scripts/shell_gate.py` (`make lint-sh`, `make fmt-check-sh`, `make test-sh`) |
| A held status that is not a bare `name=$?` | advisory (warns) | `tests/integration/test_exit_gate.py`, `exit-held-status` |
| Shell or Python; a useful `WHAT ON NEXT`; a true `effect:` | judgment | this guide + review |

The line between the tiers is the one [coding-practices](coding-practices.md)
draws: can a rule decide it with no model? Yes → gate. It flags ordinary code
too → advisory. It needs judgment → this guide, and a reviewer pointing at
the section that was not followed.
