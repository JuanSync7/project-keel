---
title: Make next steps — one route table, a footer printed from it, and a walk that proves it
kind: design
layer: n/a
status: draft
owner: TBD
tags: [design, make, exit-codes, footer, graph, orphans, gate]
summary: The design pass for queue item KEEL-NEXT-1. Every annotated make target gets a route for each outcome it can end with, kept in one table in config/project.json `make_targets.next`; a footer printed from that table after the target ends names the next target or command; a static check holds the table to the Makefile and the exit-code list, a walk test drives each declared edge once from the entry targets, a costly, networked or shared-state edge is checked on paper, and a target no entry reaches is an orphan only with a reason. It names the incumbents and where each falls short, records what was measured and what is inferred, answers the hard questions per effect class, and lists the build steps by intent. Nothing here is built.
id: docs-design-make-next-steps
created: 2026-10-22
updated: 2026-10-22
visibility: internal
canonical: true
---

# Make next steps — one route table, a footer printed from it, and a walk that proves it

This is a design record, not a build. It answers queue item KEEL-NEXT-1 in
`docs/design/downstream-feedback.md`: a `make` target's next step is prose
today, a success prints no next step, and nothing checks that a named next step
exists or moves the work on. It is keel-only (copier.yml `_exclude` names it),
because it is about building keel's gate, not about using a generated project.
No code in `scripts/`, `src/`, the Makefile or `tests/` changes with it.

## The idea, and the question it reframes

The maintainer's idea, in short: each make target ends with a footer that says
what to do next given how it ended; the footers together form a graph of all
make targets; a test starts from the entry targets and proves each step leads
somewhere real; a target nothing leads to is an orphan only with a stated
reason; and so every target has a defined exit and a defined next step.

The old question was "can we build a DAG of the make targets from their
footers". The design below answers a reframed one: **can every outcome of
every target name a next step that exists, and can a test prove each named
step is reachable and runs?** The reframe matters for two measured reasons:

- **The graph is not acyclic.** The common failure route is a repair loop:
  `check-docs` fails, `restamp-docs` fixes the stamps, `check-docs` runs again.
  Only the success edges can be held acyclic (a success chain that loops would
  print "next" forever); failure edges are expected to close loops.
- **Orphans are not rare.** A first sketch of routes for keel's 51 targets
  (inferred, written for this pass and listed under
  [Orphans](#orphans-and-entries)) reaches 37 of them from `make help`, even
  after counting prerequisites and `verify`'s goals as reachable; 14 stay
  unreached. They are leaves a person starts by name (`run`, `demo`,
  `run-api`), narrower runs of a wider target (`unit`, `smoke`), template
  maintenance (`canary`, `audit-project`), and one paid run (`eval-live`).
  The reason column is not the exception path; it is a quarter of the table.

## What exists today (measured 2026-10-22, on this branch)

| What | Where | What it gives | Where it falls short |
|---|---|---|---|
| 51 `## `-annotated targets, each with an effect label | `Makefile`, `docs/adr/keel/K-0011-make-target-effect-labels.md`, `check_W` | what a target touches: 41 `[local]`, 4 `[tree]`, 3 `[read]`, 1 `[tree,cost]`, 1 `[read,cost]`, 1 `[tree,read]`, 0 `[write]` | says what a target is, not what follows it |
| `make help` | `scripts/make_help.py` | every target, grouped, with its label and a legend | a menu, not a route: nothing per outcome |
| `ExitCode` | `scripts/exit_codes.py` | 9 members (0, 1, 2, 10–14, 130), each with `meaning` and a generic `action` | `action` is the same for every target ("read the last stderr line … run it again") |
| `report(code, what, on, next_step)` | `scripts/exit_codes.py`; 106 calls and 1 `fail` in 28 files under `scripts/` (counted by AST: a `report`/`fail` call whose first argument is an attribute) | the one failure line, with an input-specific repair | 10 of the 86 literal `next_step` strings name a backticked `` `make X` ``; nothing checks that X exists or is the right route; 20 are computed and unread by any check |
| Two hard-coded `next:` lines | `scripts/check_structure.py` `main`, `scripts/doc_review.py` | a success hint | `check_structure` prints the same `next:` line whether it passed or failed; neither is checked against the Makefile |
| Recipe echo strings | `Makefile` | 8 lines that say "run 'make fe-install'" | prose in a shell line; unchecked |
| The [local] sweep | `tests/integration/test_make_target_effects.py` | runs every exactly-`[local]` target in a hermetic clone through `scripts/run_make_target.py`: 29 targets, 12 skipped by name and reason in `make_targets.effect_proof_skip` | asserts tree and HOME are untouched, not what the target printed next |
| Name-and-reason exemptions | `make_targets.effect_proof_skip`, `e2e.exempt`, `traceability.gaps` | the house shape for "this one is excused, and why", with staleness checks | none exists for routes or orphans |
| Coverage by marker | `@pytest.mark.endpoint` (`tests/integration/test_e2e_coverage.py`), `@pytest.mark.req` (`make trace`) | a test names what it is evidence for; a gate fails what no test names | no marker for a route |
| The evidence record | `scripts/gate_evidence.py` | `verify`'s goals, each goal's result and exit code | records the code make returned, not the script's |

One measured fact shapes the mechanism more than any other. **GNU make
collapses a recipe's exit status to 2.** A scratch makefile whose recipe runs
`exit 13` prints `make: *** [Makefile:2: a] Error 13` and exits 2, as goal and
as prerequisite (GNU Make 4.4.1, 2026-10-22). So `make check` failing with
`FAILURE` (1), `CONFIG` (14) or `BACKEND_ABSENT` (11) reaches its caller as 2,
and so does each failing goal `scripts/gate_evidence.py` runs. The comment in
`scripts/exit_codes.py` that 10–14 let "a caller act on the number alone"
holds for a script run directly, not for one run through make. A footer keyed
on the outcome must therefore be resolved **inside the recipe**, where the
script's own status is still visible.

### The incumbent tools, and where they stop

The maintainer's standing rule is to name the incumbent before pitching a
mechanism. Rows marked *documented* are from each tool's own documentation as
recalled, not run for this pass.

| Incumbent | What it does for "what next" | Where it stops |
|---|---|---|
| GNU make prerequisites and `.PHONY` | a *before* graph: what must run first | no *after* edge; outcome lost to status 2 (measured above) |
| `make help` / `make_help.py` | lists every target and its effect | no outcome, no route |
| just (`just --list`, recipe dependencies, `[confirm]`) *documented* | a nicer menu and a before graph; a confirm prompt on a recipe | no outcome-keyed next step; switching runners rewrites 347 Makefile lines and every doc that says `make` |
| Task (go-task: `deps`, `preconditions` with `msg`, `status`, `summary`) *documented* | a failure message for a failed precondition, the nearest thing to a failure footer | one message per precondition, nothing on success, nothing walks it |
| Nx / Bazel graphs *documented* | a build dependency graph, visualised | the same before graph at larger scale |
| git's `hint:` lines and `git status` "(use … to …)" | per-outcome next steps, the closest UX precedent | hard-coded strings; nothing proves the named command exists |

No incumbent keys a next step on how a target ended, and none proves the step
it names is reachable. Changing runner would cost the most and solve none of
it, so the design stays inside make and keel's existing gates.

## The design

### The route table: schema

One block, `make_targets.next` in `config/project.json`, read through
`scripts/config_loader.py` with a `KEYS` row for each key (type and default in
the row, never in the reader).

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
      "status:2": [{"to": "stop", "why": "a goal failed; its own footer above names the next step"}]
    }
  },
  "orphans": {
    "demo": "a showcase run a person starts by name; no gate's outcome leads to it"
  }
}
```

- **`routes.<target>`** has one key per outcome: `ok`, an `ExitCode` member
  name other than `SUCCESS`, or `status:<n>` for a status that is not a member
  value (a wrapped tool's own, such as pytest's 5). The vocabulary is closed;
  any other key is an error.
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
   3.6-safe; `scripts/config_loader.py` is stdlib and 3.6-safe already
   (its header), so the config route costs no new reader.

Rejected alternatives:

- **A separate `config/next_steps.json`.** It would keep `project.json`
  smaller (54,061 bytes measured), at the price of a second file the loader and
  `config/project.json.jinja` must each learn. Reopen it if the block passes
  roughly 150 rows; the sketch below has 48 edges.
- **Comments beside each target in the Makefile** (`#> ok: check-docs`), the
  way the effect label sits in the `## ` help. Co-location is its strength; it
  loses because a route is not one target's property (it joins two), the table
  must be read whole to compute reachability, and a second grammar inside
  Makefile comments is a regex-parsed format where JSON already has a reader.
- **A generated `next.mk` of make variables** so the footer is an `echo` with
  no Python. It needs its own writer and `--check` twin for a saving of about
  0.03 s per target (measured below).

### How a footer is printed, on success and on each code

The printer is one stdlib, 3.6-safe script, `scripts/next_step.py`
(the name is a proposal), called by two Makefile macros:

```make
# $(call step,<keel script command>) and $(call tool_step,<wrapped tool command>):
# run it; on a non-zero status print the route for ($@, that status) and exit with
# the same status. The status is read here because make itself reports only 2.
step      = $(1) || { rc=$$?; $(PY) scripts/next_step.py --target $@ --status $$rc --speaks exit-codes; exit $$rc; }
tool_step = $(1) || { rc=$$?; $(PY) scripts/next_step.py --target $@ --status $$rc --speaks tool; exit $$rc; }
# The last recipe line of an annotated target; make reaches it only when every line above passed.
next_ok   = @$(PY) scripts/next_step.py --target $@ --status 0 --goals '$(MAKECMDGOALS)'
```

- **Success.** `next_ok` is the last line of every annotated recipe, so it runs
  only when the target passed. It prints the `ok` steps only when the target is
  a goal on the command line (or the default goal), so `make check-all` prints
  one success footer, not six. A prerequisite-only target (`check-all`, `lint`,
  `typecheck`, `test-fe`, `check-generic`: 5 measured) gains this one line as
  its recipe.
- **A failure.** The failing line's wrapper prints the route for its status and
  exits with that status; make then stops and reports 2 as before. A failure
  footer prints whether or not the target was a goal: the target that failed
  is the one the reader must act on, prerequisite or not.
- **Which name a status gets.** Under `--speaks exit-codes`, a status that is a
  member value is that member (1 is `FAILURE`, 14 is `CONFIG`). Under
  `--speaks tool`, a status is only a number: pytest's 2 means interrupted, not
  `USAGE`, so a tool target is routed by `status:<n>` rows only. A shell
  refusal inside a recipe (`exit 2` in `new`, `audit-project`, `canary`,
  `run-web`, `test-fe-unit`, `test-fe-e2e`, `fe-browsers`: 7 targets, read from
  the Makefile) is routed as `status:2` of that target.
- **No route.** A status the table does not route and the member defaults do
  not cover (any `--speaks tool` failure without a row, any status that is not
  a member) prints that it has no route and where to add one. It never borrows
  the `FAILURE` default: an unknown outcome stays distinct from a known one.
- **The footer never changes the status.** If the printer cannot run (no
  interpreter, an unreadable manifest), the wrapper still exits with the
  captured status and the printer's own failure is one stderr line saying no
  footer could be printed and why. Fail closed on the status; the footer is
  advice.

The footer grammar is one line per step, on stderr so `make help | grep` still
greps only the menu:

```text
next: make check-docs [local] — the structure passes; the doc gate adds freshness
next: make advise [local] — what this gate does not fail on
next (exit 1, FAILURE): make restamp-docs [tree] — a stale `updated:` is what --strict adds over check
next (exit 1, FAILURE, default): make check [local] — read the last stderr line, fix what it names, and run it again
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
The overlap is the 10 literal `next_step` strings that name a backticked
`` `make X` `` (measured): each must name a target the table routes to from a
target whose recipe runs that script, for that code. A static check reads the
call sites by AST, as `tests/integration/test_exit_gate.py` already does,
and fails a mismatch. A computed `next_step` (20 measured) is out of its reach
and is listed as a limit. The two hard-coded `next:` lines in
`scripts/check_structure.py` and `scripts/doc_review.py` become `ok` rows and
are deleted from the scripts, so the route has one source.

### The walk test: which edges run, which are checked on paper

An **edge** is (source target, outcome, step). The walk has a static half that
judges every edge and a running half that drives the ones it can afford.

**The static half** (a check in `scripts/check_structure.py`, beside `check_W`,
because it owns the label grammar and `make_target_rules`):

- every annotated target has an `ok` row; every row's target, step and outcome
  key is in its vocabulary; every `why` is non-blank;
- the success edges form no cycle;
- every annotated target is reachable from an entry, where reachability follows
  routes, prerequisites and the goals of a recipe's `$(MAKE)` line (the same
  closure `_scripts_reachable_from` and `check_W` already compute), or is an
  orphan with a reason; stale orphans and entries are errors;
- every annotated recipe ends with `next_ok` and wraps each command line in
  `step` or `tool_step`, and a `step` line runs a keel script while a
  `tool_step` line does not;
- an override names an outcome the source can end with, where that is
  decidable: for a `--speaks exit-codes` line, the `ExitCode` members named in
  its script's own source, read by AST (an undercount: a code an imported
  module returns through the caller is missed, so this direction warns and
  never errors).

**The running half** (tests, by edge kind):

| Edge | Runs? | How |
|---|---|---|
| `ok` of an exactly-`[local]` target the sweep runs | yes, at no extra run | `tests/integration/test_make_target_effects.py` already runs 29 such targets; it also asserts the footer lines equal the table's `ok` steps |
| `ok` of a `[local]` target in `effect_proof_skip` | no | the 12 skips keep their named test; their `ok` edge is static only |
| a failure override from a `[local]` target | yes, once | a test marked `@pytest.mark.next_edge("<target>", "<outcome>")` plants the fault in a hermetic clone, runs the target, asserts the status the footer reports and the route; a coverage gate fails an override no test names, the shape of `tests/integration/test_e2e_coverage.py` |
| a default failure route | once per member, not per target | a unit test of the printer drives each member and the no-route case; the default is one mechanism, so walking it 51 times proves nothing more |
| a repair loop ending in a `[tree]` target (`check-docs` → `restamp-docs` → `check-docs`) | on paper by default | the step's existence and label are checked; running the writer in the throwaway clone and then the source green again is the stronger proof, and is an open decision below |
| any edge from or to `[read]` (network), `[cost]` (spend) or `[write]` (shared state) | on paper | the static half, plus `make -n <target>` showing the recipe is wired; an opt-in variable may run `[read]` edges for a person with network |
| the refusal edge of a `[cost]` target | yes | `eval-live` refuses before any call when its cases exceed `evals.live.max_calls`; that path spends nothing, so its route runs like a `[local]` one |
| the `WRITE_GUARD` refusal of a `[write]` target | yes | `tests/integration/test_write_guard.py` already drives it under `RALPH=1`; the build adds an assertion on the route it prints |

"On paper" therefore means: the edge's source and step exist, the step's
label is printed, the outcome is in the source's vocabulary, the success graph
stays acyclic, reachability holds, and the recipe is wired to print it. It does
not mean the step was run.

### Orphans and entries

The sketch used to measure reachability (inferred routes, one or more per
target, 48 edges; written in scratch for this pass, not committed):

- **From `help` along routes alone:** 10 of 51 reached.
- **Counting prerequisites and `verify`'s `$(MAKE)` goals:** 37 reached, 14
  orphans: `audit-project`, `canary`, `check-generic`, `demo`, `e2e`,
  `eval-live`, `integration`, `long-scripts`, `run`, `run-api`, `run-web`,
  `site-static`, `smoke`, `unit`.

So the design counts prerequisites and `$(MAKE)` goals as reachable (make runs
them, so a reader of `make check-all` has reached `check-cdmon`), declares a
few entries beyond `help` (`new` in the template; `run` and `demo` are
candidates), and expects about a dozen orphan reasons. A target that is only a
narrower run of another (`unit` of `test`) is an orphan with that reason, not
a reason to invent a route to it. These counts move with the real table; the
build records them again.

### What it costs to run

- **Per target run, by a person:** one extra interpreter start that imports
  `scripts/config_loader.py` and parses `config/project.json`: 0.03 s measured
  under both the host interpreter and the 3.11 venv (2026-10-22, `time`, one
  run each). `make check` itself took 4.07 s and `make help` 0.08 s in the same
  session, so the footer adds under 1% to the first and about a third to the
  second.
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

- The Makefile ships verbatim (it has no `.jinja` twin), so the macros and the
  wiring arrive in every project.
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
  line.
- It does not route a line whose errors the recipe ignores (`-` prefix, as in
  `advise`); that line cannot end the target.
- It prints no machine-readable footer (JSON) and has no off switch in the
  first build: neither has a consumer yet.
- It does not prove a repair works, except where the walk runs the repair
  loop; elsewhere it proves the step exists and is wired.

## Defence: the hard questions per effect class

The default route for any failure the table does not override is "rerun this
target after the repair the line above names", with that member's `action`.
Each class below answers what follows success, what follows each code, and what
proves it. Targets and codes are measured from the Makefile and each recipe's
own scripts (AST over the script file; an import's codes are not counted).

### `[local]` (41 targets; 41 − 12 skipped by name = 29 in the sweep)

- **On success:** the `ok` steps. A check routes to the next wider check
  (`check` → `check-docs` → `check-all` → `verify`), a narrow test run to its
  wide one, `verify` to `command:commit`, an advisory to `stop`.
- **`FAILURE` (1):** default rerun, overridden where a twin writer exists:
  `check-docs` → `restamp-docs`, `check-exit-codes` → `exit-codes`,
  `check-aad` → `agent-surface-schema`, `check-corpus` → `site-data`,
  `fmt-check` (ruff 1, `status:1`) → `fmt`.
- **`USAGE` (2) / `status:2`:** default rerun for a keel script; for the
  frontend targets' shell refusals, → `fe-install`; for `verify`, `stop`,
  because 2 there means a goal failed and printed its own footer.
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
  route; `canary` emits `CONFIG`, `FAILURE`, `NOTHING_JUDGED`, `USAGE`; its
  `NOTHING_JUDGED` routes to `stop` (no answer set to render).
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
  `BACKEND_ABSENT` routes to the model registry's setup. `doc_review.py`'s own
  source names only `SUCCESS` (measured), so its failure codes come from what
  it imports; they are an undercount the static half warns about.
- **What proves it:** the refusal edge runs, because it spends nothing; every
  other edge is on paper. No edge is ever walked by spending.

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
- **On failure:** the `WRITE_GUARD` refusal exits 1 under CI or the gate
  runner; it is a shell `exit 1`, so it reads as `FAILURE` by value, and its
  route says to run the target attended. A real failure of the write and the
  refusal share the number; the refusal's own line already names the cause.
- **What proves it:** the refusal edge runs in `tests/integration/test_write_guard.py`
  (the route assertion is the build's addition); every other edge is on paper. A `[write]` target is never run by a test.

## Lenses (for the maintainer's decision)

| Lens | Finding |
|---|---|
| Alternatives | The cheapest one: a static check that every backticked `` `make X` `` in a `report()` literal, a recipe echo or a `next:` line names an annotated target. It catches the measured defect class (10 + 8 + 2 named steps, none checked) in one step with no footer and no table. It does not give success footers or reachability. |
| Testability | Strong for the static half and the swept success edges; per-override tests are the bulk of the build; computed `next_step` strings stay unchecked. |
| Usability | A reader gets one to three lines after every target, with the effect label of each step. The risk is noise: a footer nobody reads trains people to skip the `report()` line above it. |
| Cost | About 0.03 s per target run (measured); roughly 51 `ok` rows and 15 overrides to write once (inferred); one row per new target forever. |
| Growth | Each new target costs one row; the check names the missing row. A project's own targets pay the same. |
| Anti-patterns | Routing by parsing output (refused); a default that hides an unknown status (refused); seeding rows by migration (refused). |
| Assumptions vs evidence | Measured: target and label counts, call-site counts, make's status collapse, footer cost, the sketch's reachability. Inferred: the routes themselves, the walk's minutes, the tool status meanings. |
| Risk and reversibility | Reversible: the table, the printer and the macros come out with no data lost. The one-way risk is the downstream red-on-update for projects with their own targets. |
| Operator / bus factor | One table to read; the printer is small; the macros are the part a newcomer must learn, and the check names a recipe that skips them. |
| Security boundary | None moves. The footer is advice; `scripts/run_make_target.py` and `WRITE_GUARD` stay the enforcement. A footer could name a costly step; it prints the label so the reader sees it. |
| Scope cuts | No JSON footer, no off switch, no output-based routing, no `[read]`/`[cost]`/`[write]` runs, no tool status registry in the first build. |
| Why now | The exit-code list (`scripts/exit_codes.py`) and the one config loader ([K-0022](../adr/keel/K-0022-one-config-loader.md)) are settled, so the route is the remaining unchecked half of every failure line. Not urgent: nothing is broken that the cheap alternative does not catch. |
| What transfers | "A message that names a next step is a claim; check that the step exists" applies to any CLI keel generates, and to jarvis's node outcomes. |

## Build steps, by intent

Rows are named by intent; the parent assigns campaign and slice ids when it
queues them. Each row is one commit (or a short series) that leaves
`make verify` green.

| Build step | Delivers | Proof it can fail | Depends on |
|---|---|---|---|
| Named steps must exist | the cheap alternative: every backticked `` `make X` `` in a `report()` literal, a recipe echo and a `next:` line names an annotated target | a planted `` `make no-such` `` in a fixture call site goes red | — |
| Route table and static check | the `make_targets.next` block, its `KEYS` rows and settings-reference rows; the static half (`ok` per target, vocabularies, acyclic success edges, reachability, orphan and entry staleness) | one mutation per rule: drop an `ok`, add a cycle, orphan a target, stale an orphan | named steps must exist |
| Footer printer | `scripts/next_step.py`: success, each member's default, overrides, no-route, and the printer-failure line; status never changed | a unit test per member and per fault; a printer made to raise still exits with the captured status | route table |
| Makefile wiring | `step`, `tool_step`, `next_ok` on every annotated recipe; the two hard-coded `next:` lines moved into rows; the wiring check; features-reference rows; CHANGELOG | an unwrapped recipe line and a missing `next_ok` each go red | footer printer |
| Walk over the edges | the sweep asserts `ok` footers; `@pytest.mark.next_edge` and its coverage gate; one marked test per override; the `report()`-names-a-route AST check; the refusal edges of `[cost]` and `[write]` | a wrong route in the table fails the sweep; an unmarked override fails the gate | Makefile wiring |
| Generated projects | the `config/project.json.jinja` block, stub routes for keel-only targets, the copier-generation case, the upgrade note, the audit prediction | the generation case under each frontend answer | walk over the edges |
| Record the decision | an ADR in keel's number space, once the maintainer accepts this design | — | generated projects |

Deferred, each with its trigger: running `[tree]` repair loops in a clone
(open decision 1), a tool status registry (when a third tool target needs
`status:` rows), a JSON footer (when an agent consumes footers), a separate
config file (past roughly 150 rows).

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
   graph", the full table is needed. The recommendation is to build the first
   step now either way, since every later step depends on it.

## Corrections log

None yet.
