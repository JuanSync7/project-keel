---
title: Make next steps — one route table, a footer printed from it, and a walk that proves it
kind: design
layer: n/a
status: draft
owner: TBD
tags: [design, make, exit-codes, footer, graph, orphans, gate]
summary: The design pass for queue item KEEL-NEXT-1. Every annotated make target gets a route for each outcome it can end with, kept in one table in config/project.json `make_targets.next`; a recipe shell that sees each recipe line's real status prints a footer from that table naming the next target or command; a static check holds the table and the recipes to the Makefile and the exit-code list, a walk test drives each declared edge once from the entry targets, a costly, networked or shared-state edge is checked on paper, and a target no entry reaches is an orphan only with a reason. It names the incumbents and where each falls short, records what was measured and what is inferred, answers the hard questions per effect class, and lists the build steps by intent. Nothing here is built.
id: docs-design-make-next-steps
created: 2026-10-22
updated: 2026-10-23
visibility: internal
canonical: true
---

# Make next steps — one route table, a footer printed from it, and a walk that proves it

This is a design record, not a build. It answers queue item KEEL-NEXT-1. It is
keel-only (copier.yml `_exclude` names it), because it is about building keel's
gate, not about using a generated project. No code in `scripts/`, `src/`, the
Makefile or `tests/` changes with it.

The queue row is not on this branch yet. It is row 10 of the queue table in
`docs/design/downstream-feedback.md` on the keel-plan-intake branch (commit
409243c), and it reads:

> A `make` target's next step is prose: a failure's `report()` line says what
> to do in words, a success prints no next step, and nothing checks that a
> named next step exists or moves the work on. Proposed: one table maps a
> target and its outcome to the next target or command, the footer is printed
> from it, and a test walks each declared edge once from the entry targets; a
> costly edge is checked on paper, and a target no entry reaches is an orphan
> only with a reason

This document merges after keel-plan-intake, so the row it answers is on
`main` when it lands.

## The idea, and the question it reframes

The maintainer's idea, in short: each make target ends with a footer that says
what to do next given how it ended; the footers together form a graph of all
make targets; a test starts from the entry targets and proves each step leads
somewhere real; a target nothing leads to is an orphan only with a stated
reason; and so every target has a defined exit and a defined next step.

The old question was "can we build a DAG of the make targets from their
footers". The design below answers a reframed one: **can every outcome of
every target name a next step that exists, and can a test prove each named
step is reachable and runs?** The reframe matters for two reasons:

- **The graph is not acyclic** (by construction, not measured). The common
  failure route is a repair loop: `check-docs` fails, `restamp-docs` fixes the
  stamps, `check-docs` runs again. Only the success edges can be held acyclic
  (a success chain that loops would print "next" forever); failure edges are
  expected to close loops.
- **Orphans are not rare** (inferred). A first sketch of routes for keel's 51
  targets, listed in full in
  [the appendix](#appendix-the-reachability-sketch-inferred), reaches 37 of
  them from `make help`, even after counting prerequisites and `verify`'s goals
  as reachable; 14 stay unreached. The routes are guesses; the count of 14 is
  computed from those guesses, so it is only as good as they are. The
  unreached ones are leaves a person starts by name (`run`, `demo`, `run-api`),
  narrower runs of a wider target (`unit`, `smoke`), template maintenance
  (`canary`, `audit-project`), and one paid run (`eval-live`). The reason
  column is not the exception path; it is about a quarter of the table.

## What exists today (measured 2026-10-22, on this branch)

| What | Where | What it gives | Where it falls short |
|---|---|---|---|
| 51 `## `-annotated targets, each with an effect label | `Makefile`, `docs/adr/keel/K-0011-make-target-effect-labels.md`, `check_W` | what a target touches: 41 `[local]`, 4 `[tree]`, 3 `[read]`, 1 `[tree,cost]`, 1 `[read,cost]`, 1 `[tree,read]`, 0 `[write]` | says what a target is, not what follows it |
| `make help` | `scripts/make_help.py` | every target, grouped, with its label and a legend | a menu, not a route: nothing per outcome |
| `ExitCode` | `scripts/exit_codes.py` | 9 members (0, 1, 2, 10–14, 130), each with `meaning` and a generic `action` | `action` is the same for every target ("read the last stderr line … run it again") |
| `report(code, what, on, next_step)` | `scripts/exit_codes.py`; 106 calls and 1 `fail` in 28 files under `scripts/` (counted by AST: a `report`/`fail` call whose first argument is an attribute) | the one failure line, with an input-specific repair | 86 `next_step` arguments are literal (78 plain constants and 8 `%` templates) and 20 are computed. 11 literals name a backticked `make` step, and one of them sets a variable first (`scripts/check_python_version.py`: `` `make PY=python3.11 test` ``). Nothing checks that a named target exists or is the right route, and no check reads the computed ones |
| Three hard-coded `next:` lines | `scripts/check_structure.py` `main`; `scripts/doc_review.py`; `scripts/hooks/on_stop_doc_review.py` | a success hint | `check_structure` prints its line whether it passed or failed. `scripts/doc_review.py` prints its line only on a dry run that found candidates. The hook prints its line only on a dry run with stale or unresolved docs, and it is a Stop hook, not a make target. None of the three is checked against the Makefile |
| Recipe echo strings | `Makefile` | 8 lines that say "run 'make fe-install'" | prose in a shell line; unchecked |
| The [local] sweep | `tests/integration/test_make_target_effects.py` | runs every exactly-`[local]` target in a hermetic clone through `scripts/run_make_target.py`: 29 targets, 12 skipped by name and reason in `make_targets.effect_proof_skip` | asserts tree and HOME are untouched, not what the target printed next |
| Name-and-reason exemptions | `make_targets.effect_proof_skip`, `e2e.exempt`, `traceability.gaps` | the house shape for "this one is excused, and why", with staleness checks | none exists for routes or orphans |
| Coverage by marker | `@pytest.mark.endpoint` (`tests/integration/test_e2e_coverage.py`), `@pytest.mark.req` (`make trace`) | a test names what it is evidence for; a gate fails what no test names | no marker for a route |
| The evidence record | `scripts/gate_evidence.py` | `verify`'s goals, each run as its own child make, with each goal's result and exit code | records the code make returned, not the script's |

One measured fact shapes the mechanism more than any other. **GNU make
collapses a recipe's exit status to 2.** A scratch makefile whose recipe runs
`exit 13` prints `make: *** [Makefile:2: a] Error 13` and exits 2, as goal and
as prerequisite (GNU Make 4.4.1, 2026-10-22). So `make check` failing with
`FAILURE` (1), `CONFIG` (14) or `BACKEND_ABSENT` (11) reaches its caller as 2,
and so does each failing goal `scripts/gate_evidence.py` runs. As
`scripts/exit_codes.py` says, 10–14 let a caller act on the number alone only
when it runs a script directly, not through make
(`tests/integration/test_exit_codes_through_make.py`). A footer keyed
on the outcome must therefore be resolved **inside make, per recipe line**,
where the line's own status is still visible.

### The incumbent tools, and where they stop

The maintainer's standing rule is to name the incumbent before pitching a
mechanism. Rows marked *documented* are from each tool's own documentation as
recalled, not run for this pass.

| Incumbent | What it does for "what next" | Where it stops |
|---|---|---|
| GNU make prerequisites and `.PHONY` | a *before* graph: what must run first | no *after* edge; outcome lost to status 2 (measured above) |
| `make help` / `scripts/make_help.py` | lists every target and its effect | no outcome, no route |
| just (`just --list`, recipe dependencies, `[confirm]`) *documented* | a nicer menu and a before graph; a confirm prompt on a recipe | no outcome-keyed next step; switching runners rewrites 347 Makefile lines and every doc that says `make` |
| Task (go-task: `deps`, `preconditions` with `msg`, `status`, `summary`) *documented* | a failure message for a failed precondition, the nearest thing to a failure footer | one message per precondition, nothing on success, nothing walks it |
| Nx / Bazel graphs *documented* | a build dependency graph, visualised | the same before graph at larger scale |
| git's `hint:` lines and `git status` "(use … to …)" | per-outcome next steps, the closest UX precedent | hard-coded strings; nothing proves the named command exists |

No incumbent keys a next step on how a target ended, and none proves the step
it names is reachable. Changing runner would cost the most and solve none of
it, so the design stays inside make and keel's existing gates.

## The design

### The route table: schema

One block, `make_targets.next` in `config/project.json`.

```json
"next": {
  "entries": {
    "help": "the default goal: what a newcomer types first",
    "new": "the template's first command"
  },
  "commands": {
    "commit": {"run": ["git add -A", "git commit"], "why": "the gate is green; record the change"}
  },
  "routes": {
    "check": {
      "ok": [
        {"to": "check-docs", "why": "the structure passes; the doc gate adds freshness"},
        {"to": "advise", "why": "what this gate does not fail on"}
      ]
    },
    "check-docs": {
      "ok": [{"to": "check-all", "why": "the rest of the deterministic checks"}],
      "FAILURE": [{"to": "restamp-docs", "why": "a stale `updated:` is what --strict adds over check"}]
    },
    "verify": {
      "ok": [{"to": "command:commit", "why": "every gate is green"}],
      "FAILURE": [{"to": "stop", "why": "a goal failed; that goal's own footer above names the next step"}]
    },
    "fe-browsers": {
      "ok": [{"to": "test-fe", "why": "the browsers are installed"}],
      "status:2": [{"to": "fe-install", "why": "the recipe refused because the frontend packages are absent"}]
    }
  },
  "orphans": {
    "demo": "a showcase run a person starts by name; no gate's outcome leads to it"
  }
}
```

- **`routes.<target>`** has one key per outcome: `ok`, an `ExitCode` member
  name other than `SUCCESS`, `status:<n>`, or `guard`. Which of these a
  target may use depends on what the failing line speaks (see
  [Which name a status gets](#which-name-a-status-gets)). The vocabulary is
  closed; any other key is an error.
- **Each outcome holds an ordered list of steps**, the first the usual one.
  A step's `to` is an annotated target, `command:<id>` from `commands`, or
  `stop`. `why` is required and non-blank. A chain is not written in one row:
  each target's own row carries it on, so the walk follows it.
- **`ok` is required for every annotated target.** A success that leads
  nowhere says so with `stop` and a reason; an absent `ok` is an error, so "no
  next step" is never the silent default.
- **A failure outcome is optional.** Without a row, the footer prints the
  default route: rerun this target after the repair the line above names, with
  the member's `action` from `ExitCode` as the reason. A row equal to the
  default is an error (a redundant row hides which routes are real), and so is
  a row for an outcome the target cannot end with, where that is decidable (see
  [The walk](#the-walk-test-which-edges-run-which-are-checked-on-paper)).
- **`commands`** is the closed list of terminal steps outside make: each has
  the lines a person types and a reason. A footer never prints a command the
  list does not hold.
- **`entries` and `orphans`** are name-to-reason maps, the shape of
  `effect_proof_skip`. Every annotated target is reachable from an entry or is
  an orphan with a reason; an orphan that is reachable, or names no target, is
  stale and an error.

The `verify` row's `FAILURE` key depends on open decision 4: today
`scripts/gate_evidence.py` passes a failed goal's 2 through, and 2 is
`USAGE`, the number its own refusals also use. Until that decision lands,
`verify` has no failure override (see the `[local]` defence below).

### Where it lives: config, not a `*_data.py` registry

Chosen: `config/project.json` `make_targets.next`. The reasons, in order of
weight:

1. **A generated project owns its targets.** It adds targets to its Makefile
   and to `<area>.mk` files (`make_targets.area_dir`), so it must add their
   routes. `config/project.json` is the project-facts manifest a project edits
   (§15); a `scripts/*_data.py` module is template code that `copier update`
   merges over, so a project's rows would sit in a file the template rewrites.
2. **The house already keeps exemptions there.** `effect_proof_skip`,
   `e2e.exempt` and `traceability.gaps` are name-to-reason maps in this file
   with staleness checks; `orphans` and `entries` are the same shape, and
   `make_targets` is already the block `check_W` validates.
3. **A `*_data.py` registry is for a literal that would otherwise sit in
   logic** (§18, `docs/guides/generic-solution.md`): an answer key, a fixture.
   A route is a tunable project fact, not a datum the code computes with.
4. **The reader must run under 3.6.** The footer prints after `check`, which is
   3.6-safe; `scripts/config_loader.py` and `scripts/check_structure.py` are
   3.6-safe already (their headers), so the config route costs no new reader.

**One home for the keys' types: `make_targets_policy`.** Every other
`make_targets` key (`gate_effects`, `effect_proof_skip`, `unattended_vars` and
the rest) is typed and validated in one place, `make_targets_policy` in
`scripts/check_structure.py`. It requires every key, refuses an unknown one,
and returns no policy at all when any value is bad. `check_W` and
`scripts/run_make_target.py` both read the block through it. `next` becomes one
more required key there, and `scripts/config_loader.py` gets no `KEYS` row for
it. A `KEYS` row would give the same key a second type and a default, which is
two sources for one rule. The printer reads the manifest with
`scripts/config_loader.py` `read`, so the file is opened by the one reader
(K-0022), and then hands the block to `make_targets_policy`. A generated
project with no `next` key fails the policy; that is the red-on-update choice
described under [How a generated project gets it](#how-a-generated-project-gets-it).

Rejected alternatives:

- **A separate `config/next_steps.json`.** It would keep `project.json`
  smaller (54,061 bytes measured), at the price of a second file the loader and
  `config/project.json.jinja` must each learn. Reopen it if the block passes
  roughly 150 rows; the sketch in the appendix has 48 edges.
- **Comments beside each target in the Makefile** (`#> ok: check-docs`), the
  way the effect label sits in the `## ` help. Co-location is its strength; it
  loses because a route is not one target's property (it joins two), the table
  must be read whole to compute reachability, and a second grammar inside
  Makefile comments is a regex-parsed format where JSON already has a reader.
- **A generated `next.mk` of make variables** so the footer is an `echo` with
  no Python. It needs its own writer and `--check` twin to save about 0.04 to
  0.08 s per target run (measured below).

### How a footer is printed, on success and on each code

The first draft of this design put a `$(call step,<command>)` macro around each
recipe line. That is broken, and was measured broken: make splits a `$(call)`
argument at every comma, so `b: ; @$(call step,echo one, two; false)` prints
`one` and exits 0, and 12 recipe lines in the Makefile contain a comma. An
`exit N` inside a wrapped command also leaves the shell before the wrapper's
`||` runs, and the Makefile has 26 recipe-line `exit`s (7 `exit 0`, 6 `exit 1`,
13 `exit 2`). So the command is not passed as a macro argument at all.

**The recipe shell.** Make runs every recipe line with `$(SHELL)
$(.SHELLFLAGS) <line>`. The design sets both:

```make
# Every recipe line runs through the footer shell. It runs the line with /bin/sh,
# keeps the line's own status, and prints the route for ($@, that status) when the
# status is not 0. The status is read here because make itself reports only 2.
SHELL       := scripts/recipe_shell.sh
.SHELLFLAGS  = $@ -c
# The last recipe line of an annotated target; make reaches it only when every line above passed.
next_ok      = @$(PY) scripts/next_step.py --target $@ --status 0 --goals '$(MAKECMDGOALS)' --level '$(MAKELEVEL)' --success '$(NEXT_SUCCESS)' --flags '$(firstword -$(MAKEFLAGS))'
```

`scripts/recipe_shell.sh` (the name is a proposal) is POSIX sh, about ten
lines. It takes the target, drops the `-c`, runs the line with `/bin/sh -c`,
and keeps the status. On a non-zero status it calls `scripts/next_step.py`
with the target, the status and the line text, then exits with the status it
kept. Three measurements on a scratch makefile under GNU Make 4.4.1
(2026-10-22):

- `$@` expands inside `.SHELLFLAGS`, so the wrapper is told which target the
  line belongs to.
- A line `echo "a, b" && exit 13` reaches the wrapper whole, comma included,
  and the wrapper sees 13. The `exit` ends the inner shell, not the wrapper.
- 100 wrapper runs of a no-op line took 0.21 s in total, about 2 ms each.

It is shell, not Python, so a broken interpreter cannot stop every recipe in
the Makefile from running; only the footer is lost. The hazard it carries:
keel has no shell lint yet (queue item KEEL-SHELL-1 is planned), so until that
lands the wrapper's own tests are its only check.

Two make behaviours the wrapper must handle, both measured:

- **A parse-time `$(shell …)`** also runs through `$(SHELL)`, with an empty
  `$@`. The wrapper treats a call with no target as plain `sh -c` and prints
  nothing. The Makefile has no `$(shell` today; a project's `.mk` file may.
- **A sub-make.** A `$(MAKE)` line inside a recipe sees the inner target's
  failure as 2. The inner make's own wrapper has already printed the inner
  target's footer by then. So a line that runs `$(MAKE)` speaks `status:`, and
  its 2 routes to `stop` ("the target above failed and named its step").

**Recipe rules** the wrapper needs, each held by the static half:

- **No `-` prefix on a line of an annotated recipe.** Make strips the `-`
  before the shell sees the line, so the wrapper cannot tell an ignored line
  from a failing one and would print a failure footer for a line that cannot
  end the target. The line is written `cmd || true`, with a comment saying why
  its failure does not count. Measured: the 4 lines of `advise` carry `-`
  today.
- **A line that runs a keel script runs nothing that changes its status.** A
  line runs a keel script when it holds `$(PY) scripts/<path>.py`. Such a line
  may wrap the script in an `if … then …; fi` guard, which passes the
  script's status through. It may not hold `exit <n>` with n not 0, `||` or a
  second command, because then the status is no longer the script's. Measured:
  33 recipe lines run a keel script, 2 of them inside an `if` guard and none
  with an `exit` or `||`. The two lines that name a script inside
  `[ -f scripts/… ] || { …; exit 2; }` (`audit-project`, `canary`) test for
  the file and do not run it, so they are shell lines.
- **No recipe line is a `$(call)` argument.** The comma hazard returns with
  any macro that takes a command, so the static half refuses one.
- **A `|| exit 0` skip reaches `ok`.** A recipe that skips on purpose ends 0,
  so its `ok` steps print; its `why` says "or skipped" where a skip is
  possible.

#### Success

`next_ok` is the last line of every annotated recipe, so it runs only when
every line above it passed. It prints the `ok` steps only when all four of
these hold:

- the target is a goal on the command line, or the default goal, so
  `make check-all` prints one success footer, not six;
- `MAKELEVEL` is 0, so a recipe's own `$(MAKE)` line prints no success footer
  for its inner targets;
- `NEXT_SUCCESS` is not `off`;
- make is not ignoring errors (the `-i` test in `--flags`, the same
  `$(findstring i,$(firstword -$(MAKEFLAGS)))` idiom `WRITE_GUARD` uses).
  Under `make -i` a failed line does not stop the recipe, so `next_ok` would
  run after a failure. It prints "no success footer: make is ignoring errors"
  instead.

A prerequisite-only target (`check-all`, `lint`, `typecheck`, `test-fe`,
`check-generic`: 5 measured) gains this one line as its recipe.

**Why `scripts/gate_evidence.py` passes `NEXT_SUCCESS=off`, and why
`MAKELEVEL` is not enough.** `verify` runs each of its 8 goals as its own
child make. Without a switch, each child would print its goal's success
footer, so a green `verify` would print 8 success footers and then its own.
`MAKELEVEL` cannot tell those children apart from a top-level run:
`scripts/child_env.py` drops `MAKEFLAGS`, `MAKELEVEL` and the other make
control variables across the Python hop (its `_MAKE_CONTROL`), so each child
starts at level 0 again. Passing `MAKELEVEL` through would also pass
`MAKEFLAGS`, which K-0012 refuses on purpose. So `scripts/gate_evidence.py`
adds `NEXT_SUCCESS=off` to each child's make arguments, the way it already
adds `JUNIT_XML=` per goal. It suppresses success footers only; a failing
goal still prints its failure footer, because that goal is the one to act on.
`NEXT_SUCCESS` gets a row in `docs/reference/settings.md`, beside `JUNIT_XML`.
Its only consumer is `scripts/gate_evidence.py`; it is not an off switch for
people.

#### A failure

The wrapper prints the route for the failing line's status and exits with that
status; make then stops and reports 2 as before. A failure footer prints
whether or not the target was a goal: the target that failed is the one the
reader must act on, prerequisite or not.

#### Which name a status gets

One classifier, shared by the static half and the printer, decides what a
failing line speaks. The static half runs it on the Makefile's text. The
printer runs it on the expanded line the wrapper passes, with the interpreter's
path put back as `$(PY)`.

| The failing line | It speaks | Route keys a target may use for it |
|---|---|---|
| runs a keel script, under the rule above | `ExitCode` member names: 1 is `FAILURE`, 14 is `CONFIG` | member names |
| opens with the `WRITE_GUARD` sentinel `: keel-write-guard;` | the outcome `guard` | none: the route is fixed (see the `[write]` defence below) |
| anything else: a wrapped tool, a shell test, a `$(MAKE)` line | a number only | `status:<n>` |

A wrapped tool's numbers are its own: pytest's 2 means interrupted, not
`USAGE`. So a tool line is routed by `status:<n>` rows only. A shell refusal is
routed the same way. The 7 targets whose recipes hold a shell `exit 2` (`new`,
`audit-project`, `canary`, `run-web`, `test-fe-unit`, `test-fe-e2e`,
`fe-browsers`, read from the Makefile) can be routed by `status:2` because the
recipe shell sees that 2. The first draft claimed that routing under the
`$(call)` macro, where it was false (see the corrections log).

If one target ends with the same number from two different lines, and the
lines speak differently, the key tells them apart: `FAILURE` for a keel
script's 1 and `status:1` for a shell line's 1.

#### No route

A status the table does not route and the member defaults do not cover (any
`status:` failure without a row, any number that is not a member value from a
keel-script line) prints that it has no route and where to add one. It never
borrows the `FAILURE` default: an unknown outcome stays distinct from a known
one.

#### The footer never changes the status

If the printer cannot run (no interpreter, an unreadable manifest, a policy
error), the wrapper still exits with the status it kept, and the printer's own
failure is one stderr line saying no footer could be printed and why. Fail
closed on the status; the footer is advice.

#### Footer grammar

One line per step, on stderr so `make help | grep` still greps only the menu:

```text
next: make check-docs [local] — the structure passes; the doc gate adds freshness
next: make advise [local] — what this gate does not fail on
next (exit 1, FAILURE): make restamp-docs [tree] — a stale `updated:` is what --strict adds over check
next (exit 1, FAILURE, default): make check [local] — read the last stderr line, fix what it names, and run it again
next (exit 2, status:2): make fe-install [tree,read] — the recipe refused because the frontend packages are absent
next (exit 5, no route): `make test` has no route for exit 5 — add one to config/project.json make_targets.next.routes
```

The destination's effect label is printed from the Makefile, so a reader sees
`[tree]` or `[cost]` before typing the step. The label has one source, the
`## ` help line; the table never repeats it.

### report()'s next step and the table: one source each

Two different things are called "next step" today, and the design gives each
one owner:

| Question | Owner | Example |
|---|---|---|
| What in the input do I change? (the **repair**) | `report(...)`'s `next_step`, at the call site that knows the input | "set `evidence.dir` in config/project.json" |
| Which command do I run after that? (the **route**) | the table, printed by the footer | `make check-docs` |
| What does this code mean in general? | `ExitCode.meaning` and `.action`, and the generated table in `docs/guides/limits-and-troubleshooting.md` | `CONFIG`: "set or correct each key …" |

`report()` keeps its contract: three non-blank parts, one stderr line. It does
not read the table (`scripts/exit_codes.py` reads no config, by its header).

The overlap is the 11 literal `next_step` strings that name a backticked
`make` step. A static check reads the call sites by AST, as
`tests/integration/test_exit_gate.py` already does. It reads the 78 plain
constants and the constant text of the 8 `%` templates. It parses each step
as `make [VAR=value …] <target>`, so `` `make PY=python3.11 test` `` names
`test`. Each named target must be one the table routes to, for that code, from
a target whose recipe runs that script. A mismatch fails. A computed
`next_step` (20 measured) is out of its reach and is listed as a limit.

The three hard-coded `next:` lines go as follows:

- **`scripts/check_structure.py` `main`** becomes the `ok` row of `check`,
  and the line is deleted from the script.
- **`scripts/doc_review.py`** prints its line only on a dry run that found
  candidates. The route keeps that condition in its `why`:
  `doc-review`'s `ok` lists `doc-review-apply` "when the dry run above listed
  candidates". The line is deleted from the script. The other option keeps the
  machine's choice: `scripts/doc_review.py` would end with a distinct code when
  it has candidates, and the route would key on it. That changes the script's
  exit contract for a hint, so it is not proposed.
- **`scripts/hooks/on_stop_doc_review.py`** is a Stop hook, not a make
  target, so the table has no row for it and its line stays. The named-steps
  check still reads it, so the two targets it names must exist.

### The walk test: which edges run, which are checked on paper

An **edge** is (source target, outcome, step). The walk has a static half that
judges every edge and a running half that drives the ones it can afford.

**The static half** (a check in `scripts/check_structure.py`, beside `check_W`,
because it owns the label grammar, `make_target_rules` and `make_targets_policy`):

- every annotated target has an `ok` row; every row's target, step and outcome
  key is in its vocabulary; every `why` is non-blank;
- the success edges form no cycle;
- every annotated target is reachable from an entry, where reachability follows
  routes, prerequisites and the goals of a recipe's `$(MAKE)` line (the same
  closure `_scripts_reachable_from` and `check_W` already compute), or is an
  orphan with a reason; stale orphans and entries are errors;
- the Makefile sets `SHELL` and `.SHELLFLAGS` to the recipe shell, and every
  annotated recipe ends with `next_ok`;
- the recipe rules above: no `-` prefix, no status-changing construct on a
  keel-script line, no recipe line passed through `$(call)`, and the
  `WRITE_GUARD` sentinel present;
- an override names an outcome the source can end with, where that is
  decidable. For a keel-script line, that is the `ExitCode` members named in
  its script's own source, read by AST. That is an undercount: a code an
  imported module returns through the caller is missed, so this direction
  warns and never errors. For a shell line, it is the literal `exit <n>`
  values on the target's lines.

**The running half** (tests, by edge kind):

| Edge | Runs? | How |
|---|---|---|
| `ok` of an exactly-`[local]` target the sweep runs | yes, at no extra run | `tests/integration/test_make_target_effects.py` already runs 29 such targets; it also asserts the footer lines equal the table's `ok` steps |
| `ok` of a `[local]` target in `effect_proof_skip` | no | the 12 skips keep their named test; their `ok` edge is static only |
| a failure override from a `[local]` target | yes, once | a test marked `@pytest.mark.next_edge("<target>", "<outcome>")` plants the fault in a hermetic clone, runs the target, asserts the status the footer reports and the route; a coverage gate fails an override no test names, the shape of `tests/integration/test_e2e_coverage.py` |
| a default failure route | once per member, not per target | a unit test of the printer drives each member and the no-route case; the default is one mechanism, so walking it 51 times proves nothing more |
| the recipe shell itself | yes | a test drives a scratch makefile with a comma line, an `exit 13` line, a `-`-free ignored line, a parse-time `$(shell)` and a sub-make, and asserts the status and the footer for each |
| a repair loop ending in a `[tree]` target (`check-docs` → `restamp-docs` → `check-docs`) | on paper by default | the step's existence and label are checked; running the writer in the throwaway clone and then the source green again is the stronger proof, and is open decision 1 |
| any edge from or to `[read]` (network), `[cost]` (spend) or `[write]` (shared state) | on paper | the static half, plus `make -n <target>` showing the recipe is wired; an opt-in variable may run `[read]` edges for a person with network |
| the refusal edge of `eval-live` `[read,cost]` | yes, outside the gate runner | see the `[cost]` defence below |
| the `WRITE_GUARD` refusal of a `[write]` target | yes | `tests/integration/test_write_guard.py` already drives the refusal under `RALPH=1`; the build adds an assertion that the footer prints the `guard` route |

"On paper" therefore means: the edge's source and step exist, the step's
label is printed, the outcome is in the source's vocabulary, the success graph
stays acyclic, reachability holds, and the recipe is wired to print it. It does
not mean the step was run.

### Orphans and entries

The sketch used to measure reachability holds inferred routes, one or more per
target, 48 edges in all. It was written in scratch for this pass and is not
committed as code; its edges are listed in
[the appendix](#appendix-the-reachability-sketch-inferred) so the counts can
be recomputed.

- **From `help` along routes alone:** 10 of 51 reached (computed from the
  sketch).
- **Counting prerequisites and `verify`'s goals:** 37 reached and 14 orphans
  (computed from the sketch): `audit-project`, `canary`, `check-generic`,
  `demo`, `e2e`, `eval-live`, `integration`, `long-scripts`, `run`, `run-api`,
  `run-web`, `site-static`, `smoke`, `unit`.

The counts are computed, but from routes that are guesses, so they are
inferred, not measured. The design counts prerequisites and `verify`'s goals
as reachable, because make runs them, so a reader of `make check-all` has
reached `check-cdmon`. It declares a few entries beyond `help` (`new` in the
template; `run` and `demo` are candidates) and expects about a dozen orphan
reasons. A target that is only a narrower run of another (`unit` of `test`) is
an orphan with that reason, not a reason to invent a route to it. The build
records the counts again from the real table.

### What it costs to run

- **Per recipe line:** one extra `/bin/sh` start for the recipe shell, about
  2 ms (measured: 100 runs in 0.21 s).
- **Per target run, by a person:** one printer start, on success or on
  failure. The printer imports `scripts/config_loader.py` and
  `scripts/check_structure.py`, parses `config/project.json`, and reads the
  effect labels from the Makefile. Measured on 2026-10-22: the whole
  label-reading process took 0.03 to 0.05 s in this pass (importing
  `scripts/check_structure.py` 0.024 to 0.033 s, `target_effects` 0.003 s);
  an independent review measured `target_effects` runs at 0.04 s under 3.11 and 0.08 s
  under 3.6. `make check` itself took 4.07 s and `make help` 0.08 s in the same
  session, so the footer adds about 1 to 2% to the first and roughly doubles
  the second.
- **The static half:** a pass over the Makefile and one config block, of the
  size `check_W` already does; inferred under a second inside `make check`.
- **The running half:** the success edges ride the existing sweep, so their
  cost is the string comparison. The failure overrides each cost one planted
  run in a clone: the sketch has about 15, almost all in the `check` family
  (seconds each), so inferred one to two minutes of added integration time.
  Not measured; the build measures it.
- **Spend:** none. No `[cost]` edge runs in the walk, and the one `[cost]`
  refusal edge it runs refuses before any call.

### How a generated project gets it

- The Makefile ships verbatim (it has no `.jinja` twin), so the recipe shell,
  `next_ok` and the wiring arrive in every project, and
  `scripts/recipe_shell.sh` ships with `scripts/`.
- `config/project.json.jinja` carries the `make_targets.next` block. A
  keel-only target whose recipe is a stub downstream (`audit-project`,
  `canary`) is routed for its stub: `status:2` to `command:template-checkout`,
  the line naming where to run it.
- A frontend or showcase answer that prunes files leaves the target in place
  and turns it into a stated skip with exit 0, so its `ok` row still holds.
- **A project with targets of its own goes red on update** until it adds an
  `ok` row (or an orphan reason) for each. That is the fail-closed choice; the
  `CHANGELOG.md` entry names the one-row fix, and `make audit-project`
  predicts the finding before the update. Seeding `ok: stop` rows by migration
  was rejected: it would mark a project's targets routed when nobody routed
  them.
- A project's own `.mk` file runs through the same recipe shell, so its `-`
  lines and its keel-script lines meet the same recipe rules.
- The generated-project test (`tests/integration/test_copier_generation.py`)
  gains a case that the static half is green under each frontend answer.

### What it does NOT do

- It does not run the next step. A footer is advice, printed; nothing follows
  it automatically.
- It is not a permission. A footer may name a `[tree]` or `[cost]` target; the
  label is printed so the reader sees it, and `scripts/run_make_target.py` and
  `WRITE_GUARD` remain what refuses one unattended. An agent that follows a
  footer is held by the same gate runner as before.
- It does not replace `report()`. The repair stays at the call site that knows
  the input; the footer adds the route.
- It does not route by output. One outcome can have causes with different
  fixes (`doc-review` exits 0 whether or not it queued findings); the table
  lists the steps with a `why` that says when each applies, and a script that
  needs a machine-chosen route must split its outcome into distinct codes.
- It does not model prerequisites, order goals, or parallelise anything; make
  still does that.
- It does not cover a script run outside make: the route is keyed by make
  target, so `python scripts/check_structure.py` prints only its `report()`
  line. A hook such as `scripts/hooks/on_stop_doc_review.py` keeps its own line.
- It does not print a footer for `WRITE_GUARD`'s `-i` refusal: that branch is
  a `$(error)`, which stops make while it expands the recipe, before any shell
  runs. Its own message already says to run without the flag.
- It prints no machine-readable footer (JSON) and has no off switch for
  people in the first build: neither has a consumer yet. `NEXT_SUCCESS=off`
  exists for `scripts/gate_evidence.py` alone.
- It does not prove a repair works, except where the walk runs the repair
  loop; elsewhere it proves the step exists and is wired.

## Defence: the hard questions per effect class

The default route for any failure the table does not override is "rerun this
target after the repair the line above names", with that member's `action`.
Each class below answers what follows success, what follows each code, and what
proves it. Targets and codes are measured from the Makefile and each recipe's
own scripts (AST over the script file; an import's codes are not counted).
Which routes to write is inferred.

### `[local]` (41 targets; 41 − 12 skipped by name = 29 in the sweep)

- **On success:** the `ok` steps. A check routes to the next wider check
  (`check` → `check-docs` → `check-all` → `verify`), a narrow test run to its
  wide one, `verify` to `command:commit`, an advisory to `stop`.
- **`FAILURE` (1):** default rerun, overridden where a twin writer exists:
  `check-docs` → `restamp-docs`, `check-exit-codes` → `exit-codes`,
  `check-aad` → `agent-surface-schema`, `check-corpus` → `site-data`.
  `fmt-check` runs ruff, a tool line, so its 1 is `status:1` → `fmt`.
- **`USAGE` (2):** default rerun for a keel script's refusal of its own
  arguments.
- **`status:2` from a shell line:** the frontend targets' refusals
  (`run-web`, `test-fe-unit`, `test-fe-e2e`, `fe-browsers`) → `fe-install`;
  `new`'s refusal → default rerun with its line's own reason.
- **`verify`'s 2.** Today `scripts/gate_evidence.py` ends 2 in two different
  cases. One is its own refusal (a bad `--gate` or goal list, a `USAGE` it
  chose). The other is a goal that failed, whose make status 2 it passes
  through. Both arrive as `USAGE` to the classifier, because the line runs a
  keel script. A single route cannot serve both without routing by output, so
  `verify` gets no `USAGE` override and the default prints: "rerun after the
  repair the line above names". That is right for the refusal and only roughly
  right for a failed goal, whose own failure footer printed above it. Open
  decision 4 removes the ambiguity: `scripts/gate_evidence.py` would end
  `FAILURE` for a failed goal, keeping the goal's own status in the evidence
  record. Then `verify`'s `FAILURE` routes to `stop` ("that goal's footer
  names the step") and its `USAGE` and `CONFIG` keep the default rerun.
- **`CONFIG` (14):** default rerun after the `[not set]`/`accepted:` lines;
  emitted by `advise`, `check-exit-codes`, `eval`, `secret-scan`, `verify`.
- **`BACKEND_ABSENT` (11):** `secret-scan` → `secrets-install` (the existing
  report line names it); `eval` → default.
- **`NOTHING_JUDGED` (13):** `long-scripts` and `secret-scan` emit it; route
  `stop` with the reason "a pass over zero items is red; give it something to
  judge", because no target supplies the missing input.
- **`RED_RECORD` (10), `INTERRUPTED` (130):** `verify` only; default rerun.
- **A tool's own status** (pytest 1–5, ruff 1, mypy 1, npm 1): explicit
  `status:<n>` rows on the 18 tool-only targets, or the no-route line.
- **What proves it:** the sweep asserts every swept `ok` footer; a marked test
  per override; the printer's unit test per member; the static half for the 12
  skipped targets.

### `[read]` (`canary`, `fe-browsers`, `secrets-install`; plus `fe-install` and `eval-live` in mixed classes)

- **On success:** `fe-install` → `fe-browsers` → `test-fe`;
  `secrets-install` → `secret-scan`; `canary` → `command:` the release step
  (`docs/adr/keel/K-0023-canary-gates-a-release-not-a-commit.md`).
- **On failure:** the network fault is the common cause and a rerun is the
  route. `canary`'s script emits `CONFIG`, `FAILURE`, `NOTHING_JUDGED` and
  `USAGE`; its `NOTHING_JUDGED` routes to `stop` (no answer set to render).
  Its shell refusal outside the template checkout is `status:2` →
  `command:template-checkout`.
- **What proves it:** on paper. `config/project.json`
  `make_targets.gate_effects` lets the gate runner run `[read]`, but the walk
  does not, because each run reaches the network and takes minutes (inferred).
  An opt-in variable runs them for a person with network.

### `[cost]` (`doc-review-apply` `[tree,cost]`, `eval-live` `[read,cost]`)

- **On success:** `doc-review-apply` → `check-docs` (its edits are gated on
  it already; the route says so); `eval-live` → `stop`, a report to read.
- **On failure:** `eval-live`'s refusal before any call (`USAGE` when the
  cases exceed `evals.live.max_calls`, by `scripts/run_evals.py`'s header;
  `CONFIG` when the `evals` block cannot be used) routes to the config key; its
  `BACKEND_ABSENT` routes to the model registry's setup. The source of
  `scripts/doc_review.py` names only `SUCCESS` (measured), so its failure
  codes come from what it imports; they are an undercount the static half
  warns about.
- **What proves it:** the refusal edge runs, because it spends nothing; every
  other edge is on paper. No edge is ever walked by spending.
- **How the refusal test runs.** It cannot go through
  `scripts/run_make_target.py`: `make_targets.gate_effects` is `[local, read]`,
  so the gate runner refuses a `[read,cost]` target before it starts. The test
  runs `make eval-live` itself, in a hermetic clone, through a child
  environment from `scripts/child_env.py`. The clone's `config/project.json`
  sets `evals.live.max_calls` below the clone's case count. No credential
  variable is set, so a refusal that failed to fire would end in
  `BACKEND_ABSENT`, not in a call (inferred from the adapter's header; the
  build confirms the order). The test asserts the status, the footer's route
  and that no request was made.

### `[tree]` (`fmt`, `restamp-docs`, `exit-codes`, `agent-surface-schema`; plus `doc-review-apply`, `fe-install`)

- **On success:** each writer routes to its check twin (`fmt` → `fmt-check`,
  `restamp-docs` → `check-docs`, `exit-codes` → `check-exit-codes`,
  `agent-surface-schema` → `check-aad`). A writer reached from its twin's
  failure closes the repair loop.
- **On failure:** default rerun; `restamp-docs` and `exit-codes` also emit
  `USAGE` and `CONFIG`.
- **What proves it:** on paper by default. The repair loop (twin red, writer,
  twin green) is the strongest evidence the design can give and costs one
  writer run in a throwaway clone, never the checkout; whether the walk runs it
  is open decision 1.

### `[write]` (none in keel; a project's own)

- **On success:** a `[write]` target's `ok` may not route to another `[write]`
  target: a footer never chains one shared-state change into a second (the
  static half holds it).
- **On the guard's refusal.** `WRITE_GUARD` is its own recipe line, so it is
  not part of any other line. It has two branches, and they end differently:
  - The `-i` branch is a `$(error)`. Make stops while it expands the recipe,
    before any shell runs, so no footer can print; the message names the fix
    (run it without the flag).
  - The shell branch, under `CI` or `RALPH`, is `if …; then echo … >&2;
    exit 1; fi`. As a shell line its 1 would read `status:1`, the same number
    as a real failure of the write. The build opens this branch with a no-op
    sentinel, `: keel-write-guard;`, and the classifier maps a failing line
    that opens with it to the outcome `guard`. `guard` has one fixed route for
    every `[write]` target: "run it attended, outside CI and the gate runner".
    A project cannot override it. A dedicated exit status for the refusal is
    left to separate exit-code work, not this design.
- **On a real failure:** default rerun for a keel-script line, `status:<n>`
  rows or the no-route line for a shell or tool line.
- **What proves it:** `tests/integration/test_write_guard.py` already drives
  the shell branch under `RALPH=1`; the build adds an assertion that the footer
  prints the `guard` route. The static half checks that the macro still opens
  with the sentinel. Every other edge is on paper. A test never runs a
  `[write]` target past its guard.

## Lenses (for the maintainer's decision)

| Lens | Finding |
|---|---|
| Alternatives | The cheapest one: a static check that every backticked `make` step in a `report()` literal, a recipe echo or a `next:` line names an annotated target. It catches the measured defect class (11 + 8 + 3 named steps, none checked) in one step with no footer and no table. It does not give success footers or reachability. |
| Testability | Strong for the static half, the recipe shell and the swept success edges; per-override tests are the bulk of the build; computed `next_step` strings stay unchecked. |
| Usability | A reader gets one to three lines after every target, with the effect label of each step. The risk is noise: a footer nobody reads trains people to skip the `report()` line above it. |
| Cost | About 2 ms per recipe line and 0.04 to 0.08 s per target run (measured); roughly 51 `ok` rows and 15 overrides to write once (inferred); one row per new target forever. |
| Growth | Each new target costs one row; the check names the missing row. A project's own targets pay the same. |
| Anti-patterns | Routing by parsing output (refused); a default that hides an unknown status (refused); seeding rows by migration (refused); passing a command as a macro argument (refused, measured broken). |
| Assumptions vs evidence | Measured: target and label counts, call-site counts, recipe-line counts, make's status collapse, the recipe shell's behaviour and cost, the printer's cost. Inferred: the routes themselves and the reachability counts computed from them, the walk's minutes, the tool status meanings, the eval-live refusal order. |
| Risk and reversibility | Reversible: the table, the printer and the recipe shell come out with no data lost. Two risks reach further: every recipe line in keel and in each project now runs through one shell script, and keel has no shell lint yet; and a project with its own targets goes red on update. |
| Operator / bus factor | One table to read; the printer is small; the recipe shell is about ten lines; the recipe rules are what a newcomer must learn, and the check names a line that breaks one. |
| Security boundary | None moves. The footer is advice; `scripts/run_make_target.py` and `WRITE_GUARD` stay the enforcement. The recipe shell runs the same line make would have run, with the same environment. A footer could name a costly step; it prints the label so the reader sees it. |
| Scope cuts | No JSON footer, no off switch for people, no output-based routing, no `[read]`/`[cost]`/`[write]` runs, no tool status registry in the first build. |
| Why now | The exit-code list (`scripts/exit_codes.py`) and the one config loader ([K-0022](../adr/keel/K-0022-one-config-loader.md)) are settled, so the route is the remaining unchecked half of every failure line. Not urgent: nothing is broken that the cheap alternative does not catch. |
| What transfers | "A message that names a next step is a claim; check that the step exists" applies to any CLI keel generates, and to jarvis's node outcomes. "A macro argument is not a safe place for a command" applies to any make-based project. |

## Build steps, by intent

Rows are named by intent; the parent assigns campaign and slice ids when it
queues them. Each row is one commit (or a short series) that leaves
`make verify` green.

| Build step | Delivers | Proof it can fail | Depends on |
|---|---|---|---|
| Named steps must exist | the cheap alternative: every backticked `make [VAR=value …] <target>` in a `report()` literal (plain or `%` template), a recipe echo and the three `next:` lines names an annotated target | a planted `` `make no-such` `` in a fixture call site goes red, and so does `` `make PY=x no-such` `` | — |
| Route table and static check | `next` in `make_targets_policy`; the static half (`ok` per target, vocabularies, acyclic success edges, reachability, orphan and entry staleness) | one mutation per rule: drop an `ok`, add a cycle, orphan a target, stale an orphan | — |
| Footer printer | `scripts/next_step.py`: success with its four conditions, each member's default, overrides, `status:` rows, `guard`, no-route, and the printer-failure line; status never changed | a unit test per member and per fault; a printer made to raise still leaves the status unchanged | route table |
| Recipe shell and wiring | `scripts/recipe_shell.sh`, `SHELL` and `.SHELLFLAGS`, `next_ok` on every annotated recipe, `advise`'s four `-` lines rewritten to ignore their status explicitly, the `WRITE_GUARD` sentinel, `NEXT_SUCCESS=off` in `scripts/gate_evidence.py` with its settings-reference row, the recipe-rule checks, two `next:` lines moved into rows, CHANGELOG | the scratch-makefile test (comma, `exit 13`, parse-time `$(shell)`, sub-make); a `-` line, a keel-script line with `exit 1`, and a missing `next_ok` each go red | footer printer |
| Walk over the edges | the sweep asserts `ok` footers; `@pytest.mark.next_edge` and its coverage gate; one marked test per override; the `report()`-names-a-route AST check; the `eval-live` and `WRITE_GUARD` refusal edges | a wrong route in the table fails the sweep; an unmarked override fails the gate | recipe shell and wiring |
| Generated projects | the `config/project.json.jinja` block, stub routes for keel-only targets, the copier-generation case, the upgrade note, the audit prediction | the generation case under each frontend answer | walk over the edges |
| Record the decision | an ADR in keel's number space, once the maintainer accepts this design | — | generated projects |

Deferred, each with its trigger: running `[tree]` repair loops in a clone
(open decision 1), a tool status registry (when a third tool target needs
`status:` rows), a JSON footer (when an agent consumes footers), a separate
config file (past roughly 150 rows), a dedicated exit status for the
`WRITE_GUARD` refusal (with separate exit-code work).

## Open decisions

1. **Run the `[tree]` repair loops in a throwaway clone, or keep them on
   paper?** Recommendation: run them. A writer in a clone touches no checkout,
   and the loop (twin red, writer, twin green) is the only proof that a route
   moves the work on. The queue row says only that a *costly* edge is checked
   on paper; `[tree]` is not costly.
2. **Error or warning for a generated project's own unrouted targets in the
   first release?** Recommendation: error, with the audit prediction and the
   CHANGELOG line, per fail closed. A warning would let a project adopt the
   footer for keel's targets and leave its own silent.
3. **Is the cheap alternative enough?** If the goal is "no message names a
   step that does not exist", the first build step alone delivers it and the
   rest can wait. If the goal is "every outcome routes and a test proves the
   graph", the full table is needed. The route table, printer and wiring do
   not depend on the first step; the first step is independent and cheap, and
   the recommendation is to build it first either way, because it catches the
   defect that exists today.
4. **Should `scripts/gate_evidence.py` end `FAILURE` for a failed goal?**
   Today it passes make's 2 through, which collides with its own `USAGE`
   refusals. Recommendation: yes. Map a failed goal to `FAILURE` (1) and keep
   the goal's own status in the evidence record, so `verify`'s outcomes have
   one meaning each. It changes a gate's exit contract, so it needs its own
   decision and test, and a caller that reads `verify`'s 2 today must be
   checked first. Until then `verify` keeps the default route for 2.
5. **A sentinel or a dedicated status for the `WRITE_GUARD` refusal?**
   Recommendation: the sentinel now, because it needs no new `ExitCode`
   member; revisit when the exit-code work decides whether a refusal-to-run
   deserves its own number.
6. **Recipe shell or no footer on failure?** The recipe shell is the only
   measured way to see a line's real status inside make. Its cost is every
   recipe line in keel and in each project running through one keel shell
   script before shell lint exists. If that is too wide a change, the fallback
   is success footers only (`next_ok`) plus the cheap alternative, and failure
   routes stay in `report()` prose. Recommendation: the recipe shell, after
   KEEL-SHELL-1 lands, so the script has a lint gate from its first commit.

## Appendix: the reachability sketch (inferred)

The 48 edges used for the counts under [Orphans and entries](#orphans-and-entries).
Each is a guess at a route, not a decision. The sketch lists one set of next
targets per source and does not split them by outcome, so success and repair
edges sit together. A target with no next targets (`→ —`) was routed to
`stop` in the sketch.

| Source | Next targets |
|---|---|
| `help` | `check`, `new` |
| `check-python` | `check` |
| `new`, `audit-project`, `canary` | — |
| `check` | `check-docs`, `advise`, `doc-review` |
| `check-all` | `verify` |
| `check-corpus` | `site-data` |
| `check-openapi`, `check-cdmon` | — |
| `check-aad` | `agent-surface-schema` |
| `check-exit-codes` | `exit-codes` |
| `check-docs` | `restamp-docs`, `check-all` |
| `restamp-docs` | `check-docs` |
| `doc-review` | `doc-review-apply` |
| `doc-review-apply` | `check-docs` |
| `advise`, `check-generic`, `long-scripts`, `verify` | — |
| `test`, `trace`, `eval` | `verify` (each) |
| `eval-live` | — |
| `unit`, `integration`, `e2e`, `smoke` | `test` (each) |
| `lint` | `typecheck` |
| `lint-py` | `lint` |
| `lint-fe` | `fe-install`, `lint` |
| `fmt` | `fmt-check` |
| `fmt-check` | `fmt`, `lint` |
| `typecheck` | `test` |
| `typecheck-py` | `typecheck` |
| `typecheck-fe` | `fe-install`, `typecheck` |
| `test-fe` | `verify` |
| `test-fe-unit` | `fe-install`, `test-fe` |
| `test-fe-e2e` | `fe-install`, `fe-browsers`, `test-fe` |
| `fe-install` | `fe-browsers` |
| `fe-browsers` | `test-fe` |
| `secrets-install` | `secret-scan` |
| `secret-scan` | `secrets-install`, `verify` |
| `run`, `run-web`, `demo`, `site-static` | — |
| `site-data` | `check-corpus` |
| `run-api` | `run-web` |
| `agent-surface-schema` | `check-aad` |
| `exit-codes` | `check-exit-codes` |

Reachability from `help`, following these edges, Makefile prerequisites and
the goals `verify` handed `scripts/gate_evidence.py` before KEEL-SHELL-1 added
`test-sh` to them, gives the 37 and the 14 above. The Makefile's `verify`
recipe owns that list. Following these edges alone gives 10: `help`,
`check`, `new`, `check-docs`, `advise`, `doc-review`, `restamp-docs`,
`check-all`, `verify`, `doc-review-apply`.

## Corrections log

- 2026-10-22: The first draft wrapped recipe lines in `$(call step,…)` and
  `$(call tool_step,…)` macros. A comma inside the command split it, and an
  `exit N` inside it skipped the wrapper, so the design now uses a recipe
  shell set as `SHELL`. That draft also said the 7 shell `exit 2` refusals
  were routed as `status:2`. Under the macros they were not seen at all; they
  are now, through the recipe shell. It said the `WRITE_GUARD` refusal reads as
  `FAILURE` by value; it is a shell line, so it would read `status:1`, and it
  now gets its own `guard` outcome. Its `verify` example routed `status:2`,
  which the vocabulary rule forbids for a keel-script line; `verify`'s 2 is now
  an open decision. Its counts are restated: 86 literal `next_step` strings are
  78 constants and 8 templates, 11 of them name a `make` step (not 10), and
  there are 3 hard-coded `next:` lines (not 2). Its reachability counts are
  now labelled inferred, with the sketch's edges in the appendix. Its claim
  that every later build step depends on the first was too strong.
- 2026-10-23: The reachability paragraph spelled out the goals `verify` ran
  when the counts were taken. KEEL-SHELL-1 then added `test-sh` to the recipe,
  so the list went stale. The list is gone; the paragraph now says the counts
  predate `test-sh`, and they are not re-measured here.
