---
title: "ADR-0011: Every make target declares its effect, and a gate runner runs only a read-only one"
kind: adr
layer: n/a
status: proposed
owner: TBD
tags: [adr, make, effect-labels, gate, ralph, idempotency, check-w]
summary: "Every `## `-annotated make target opens its help with one bracketed effect label of one or more words from a closed vocabulary (local, tree, read, cost, write), comma-separated in that order, `local` only alone. check_W in scripts/check_structure.py holds the labels, a composite's label must cover what its prerequisites and `$(MAKE)` calls reach, and a [write] target opens its recipe with `$(WRITE_GUARD)`. scripts/run_make_target.py, the gate runner agents use, runs only a target inside config/project.json `make_targets.gate_effects` and fails a green run that changed what git sees. Adapted from bedrock-platform's ADR-0010, with a `tree` label that bedrock folded into `local`."
id: docs-adr-0011-make-target-effect-labels
created: 2026-10-06
updated: 2026-10-06
visibility: internal
canonical: true
---

# ADR-0011: Make targets declare their effect

**Status:** proposed — the vocabulary and the gate-runner contract await the
maintainer's acceptance. It adapts a decision a downstream project already
made: bedrock-platform's `docs/adr/0010-areas-and-effect-labels.md` (the
bedrock-platform repository, accepted 2026-10-03).

## Context

An agent in a Ralph loop calls `scripts/run_make_target.py` as its gate, and
`scripts/apply_refactor.py` calls a gate after every edit. Before this ADR the
runner accepted any target name that was a plain token. Three defects
followed from that.

1. **A gate could rewrite the tree.** `make fmt` reformats files. Run as a
   gate, it is green, and the edit it rewrote is then committed as if a person
   had written it.
2. **A gate could change shared state.** Nothing stopped an unattended loop
   from running a target that applies infrastructure, if a project added one.
3. **A claim of "read-only" was untested.** `make site-static` was believed to
   write only ignored files. Run under the new runner in a generated project
   whose frontend is not astro, it wrote `src/frontend/<stack>/public/api/`,
   which `.gitignore` covered only for astro. The tree was dirty, and nothing
   had measured it.

A person reading `make help` had the same blind spot: no target said what it
touches.

bedrock-platform, a project generated from keel, solved the human half first.
Its ADR-0010 gives every target one label from `local`, `read`, `cost` and
`write`, refuses a `[write]` target under `CI` or `RALPH`, and groups targets
by area. Its `[local]` deliberately covers `fmt` and `site-data`, which rewrite
files in the tree. That is right for blast radius, and it is wrong for a gate:
the gate runner needs to know that a target leaves the tree alone.

## Decision

1. **A closed vocabulary.** `EFFECT_LABELS` in `scripts/check_structure.py` is
   `local`, `tree`, `read`, `cost`, `write`, in that order:

   | Label | Meaning |
   |---|---|
   | `local` | this machine only; writes nothing git would list |
   | `tree` | rewrites files in the working tree |
   | `read` | reads a remote service |
   | `cost` | spends money |
   | `write` | changes shared remote state; refused under CI and gate runs |

   `tree` is the one addition to bedrock's vocabulary. It splits bedrock's
   `[local]` into the part a gate may run and the part it may not.
2. **A label is a claim check_W holds.** Every `## `-annotated target opens its
   help with one bracketed label: words from the vocabulary, comma-separated,
   in canonical order, without duplicates. `local` stands alone. A second
   bracket is an error, and so is a target annotated on two rules with two
   different labels: make merges the rules into one target, and keeping the
   first label would hide a wider second one. A composite target's label must
   cover every word that
   its prerequisites and `$(MAKE)` calls reach, so `verify` cannot claim
   `[local]` over a `[tree]` prerequisite. A recursion check_W cannot resolve
   is a stated WARN, never a pass.
3. **A `[write]` target refuses to run unattended.** Its recipe opens with
   `$(WRITE_GUARD)`, defined in the root Makefile. The guard tests every name in
   config/project.json `make_targets.unattended_vars` (keel ships `CI` and
   `RALPH`) and exits 1 when any is set, in the environment or on the command
   line. check_W fails a guard that misses one of those names, tests a name the
   config omits, or does not `exit 1`; it reads the definition as make stores
   it, so a refusal hidden behind a make `#` comment does not count. A `-`
   prefix, on the guard's call in the recipe or at the head of its definition,
   is an error: make would ignore the guard's `exit 1` and run the recipe. A target whose name ends in a `make_targets.write_shapes` suffix
   needs the guard even if its label forgot `write`; keel ships no shapes, and
   bedrock's are `-apply`, `-drill` and `-destroy`.
4. **The gate runner runs only what a gate may run.**
   `scripts/run_make_target.py` closes the target's label over its
   prerequisites and refuses it, without running make, unless every word is in
   `make_targets.gate_effects` (keel ships `local` and `read`; check_W requires
   `local` and forbids `tree` and `write`). It refuses an extra argument that is
   not `NAME=VALUE`, so `-f` cannot point make at another makefile, and a
   variable that `make_targets.gate_vars` does not name (keel ships `PY`) or
   whose value is not one path-like word. make's own control variables
   (`MAKEFILES`, `MAKEFLAGS`, `SHELL` and the like), `WRITE_GUARD` and the
   unattended variables can never be gate variables, so a caller cannot load an
   unlabelled makefile, empty the guard, or smuggle a sub-make through a recipe
   that expands the value. It passes
   `make_targets.gate_runner_var=1` last, so `$(WRITE_GUARD)` refuses whatever
   the caller supplied. It snapshots what git sees before and after, each
   path's porcelain status and content, and a green run that changed either is
   red, naming the paths. Without git it refuses, because
   it cannot prove the run was read-only.
5. **The labels are tested by running them.**
   `tests/integration/test_make_target_effects.py` runs every target whose
   closed label is exactly `[local]` through the runner, in a hermetic clone of
   the working tree, and fails any that is red or changed the tree. A target
   that cannot run unattended is skipped only by name and reason in
   `make_targets.effect_proof_skip`. A skip that names no `[local]` target is
   stale and fails. A planted target that writes a file proves the sweep can go
   red.
6. **`make help` shows the label.** `scripts/make_help.py` renders each
   target's label, a legend, and an `EFFECT=` or `AREA=` filter. Areas follow
   bedrock's rule when a project sets `make_targets.area_dir`: one
   `<area>.mk` per area, included by the root Makefile, opening with one
   `##@ <area>` header, with public targets prefixed `<area>-`. Keel sets
   `area_dir` to null and has no areas.

## Consequences

- **A downstream project must label its own targets.** check_W fails an
  unlabelled `## ` target, so a `copier update` that brings check_W in turns a
  project's added targets red until each carries a label. The CHANGELOG
  upgrade note says so.
- **`apply_refactor.py` now refuses a wide gate.** Its default gate goes through
  the runner, so `--gate fmt` rolls the edit back as red instead of passing.
- **The site-static defect is fixed at its source.** `.gitignore` and its twin
  ignore `src/frontend/*/public/api/` and the two `llms` files for every
  stack, and `tests/integration/test_copier_generation.py` runs `site-static`
  through the runner in a generated react-vite and astro project.
- **`[local]` means less than bedrock's `[local]`.** A project that copies a
  label from bedrock must relabel `fmt`-like targets `[tree]`. The difference is
  deliberate; the gate needs it.
- **The unattended variable names live in two places.** The Makefile's
  `WRITE_GUARD` and `config/project.json` `make_targets.unattended_vars` both
  spell `CI` and `RALPH`. Deriving the guard from the config would make every
  `make` call run an interpreter to read JSON, so instead check_W holds the two
  equal in both directions: a configured name the guard misses is an error, and
  so is a name the guard's condition tests that the config omits. This departs
  from "define the names once"; the config stays the one source the Python
  consumers and the tests read.
- **A suite run through the gate runner must not inherit its variable.** make
  hands `RALPH=1` to every child through `MAKEFLAGS`, so a test that drives make
  attended drops `MAKEFLAGS`, `MFLAGS`, `MAKELEVEL` and `MAKEOVERRIDES` from the
  child's environment; `tests/integration/test_write_guard.py` proves it by
  running its attended cases through the runner.
- **Some `[local]` targets are not proven by running.** The sweep skips `test`,
  `verify`, `integration`, `run` and the servers by reason; their prerequisites
  are proven, and the skip list is tested for staleness.

## Alternatives considered

- **Adopt bedrock's four labels unchanged.** Rejected. The gate runner would
  have to run `fmt` to learn it rewrites the tree, which is the defect.
- **Keep the old runner and trust the target name.** Rejected. A name is not a
  claim anything checks, and `site-static` showed that a believed-safe target
  can dirty the tree.
- **Let the runner snapshot and roll back instead of refusing.** Rejected. A
  rollback cannot undo a `[write]` to shared state, so the refusal must come
  before make runs.
- **One label per target, as bedrock's ADR states.** Rejected for keel.
  `doc-review-apply` both rewrites the tree and spends money, and one word
  would hide one of the two.
