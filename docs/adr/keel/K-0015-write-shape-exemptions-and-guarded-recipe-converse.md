---
title: "ADR-K-0015: A write-shaped target is exempted by a named reason, and a guarded recipe is a write"
kind: adr
layer: n/a
status: accepted
owner: TBD
tags: [adr, make, effect-labels, check-w]
summary: "config/project.json `make_targets.write_shape_exempt` maps a target whose name ends in a `write_shapes` suffix but that is not a write to the reason it keeps its label; check_W then neither demands [write] of it nor demands `$(WRITE_GUARD)`, and an entry that names no defined, shaped, labelled, non-[write] target is a stale ERROR. Conversely, a labelled recipe that calls `$(WRITE_GUARD)` anywhere in any line, a `$$`-escaped reference excepted, must be labelled [write]. Neither rule changes which labels exist or what the gate runner admits."
id: docs-adr-0015-write-shape-exemptions-and-guarded-recipe-converse
created: 2026-10-08
updated: 2026-10-09
visibility: internal
canonical: true
---

# ADR-K-0015: Write-shape exemptions and the guarded-recipe converse

**Status:** accepted 2026-10-09 by the maintainer.

## Context

`docs/adr/keel/K-0011-make-target-effect-labels.md` (decision 3) holds a
target whose name ends in a `make_targets.write_shapes` suffix to the write
guard and to a `[write]` label. bedrock-platform names its shared-state
targets `-apply`, `-drill` and `-destroy`, and adopting that policy met two
gaps in check_W:

- **A write-shaped name that is not a write.** bedrock's `doc-review-apply`
  applies a paid model review to the working tree. It changes files, not
  shared state, so `[write]` would be a wrong label: `make help EFFECT=write`
  would list it beside the targets that change cloud resources. Under
  K-0011 its only ways out were a rename, which breaks every operator's
  muscle memory and every doc that names it, or a wrong label.
- **A guard under a narrower label.** check_W demanded the guard of a
  `[write]` or shaped target, but never asked the converse. A `[read]` target
  whose recipe calls `$(WRITE_GUARD)` passed: the gate runner admits it,
  because `read` is in `gate_effects`, and the guard then kills it under the
  gate runner's `gate_runner_var=1`. The label claims what the recipe refuses.

## Decision

1. **An exemption is a named target and a reason.** `config/project.json`
   `make_targets.write_shape_exempt` is an object of target name to a
   non-empty reason; a value that is not an object, or a reason that is blank
   or not a string, is a policy ERROR naming the key or the target. The key
   is required, like every other `make_targets` key; keel ships `{}`.
2. **An exempt target keeps its label.** check_W treats a valid exemption as
   if the name carried no write shape: it neither demands `[write]` nor the
   guard. The exemption is per target, never per shape, so a second `-apply`
   target is still held to K-0011.
3. **A stale exemption is an ERROR.** An entry is stale, and check_W says
   which way, sorted by name, when it names a target that no makefile
   defines, that no `write_shapes` suffix matches, that carries no effect
   label, or that is already `[write]`. A stale entry is never applied.
4. **A guarded recipe is a write.** A labelled target that is not `[write]`,
   whose name carries no unexempted write shape, and whose recipe calls
   `$(WRITE_GUARD)` (or `${WRITE_GUARD}`) anywhere in any line is an ERROR:
   label it `[write]` or drop the guard. make expands the reference wherever
   it sits, so `$(WRITE_GUARD) && cmd` and a guard with trailing blanks still
   refuse a gate run; only a `$$`-escaped `$$(WRITE_GUARD)`, which make hands
   the shell as text, is not a call. An exempt target that calls the guard falls
   under this rule, because the exemption says it is not a write and the
   guard says it is. A shaped target that is not exempt is already reported
   by K-0011's shape rule, so this rule stays silent there rather than report
   one defect twice. An unannotated target has no label to contradict.

## Consequences

1. **bedrock-platform keeps `doc-review-apply` as `[cost]`**, with one line in
   its manifest saying why, and its guarded targets stay as they are: every
   one is already `[write]`.
2. **The reason is reviewed, not checked.** check_W proves an exemption names
   a real, shaped, labelled, non-`[write]` target; whether the reason is true
   is a review question, as with `effect_proof_skip`.
3. **A project's manifest gains a key.** `copier update` carries
   `"write_shape_exempt": {}` into `config/project.json`; a project that edited
   the lines around it merges it there like any other manifest change.

## Alternatives considered

- **Rename the target.** Rejected. A name is an interface operators and docs
  already use, and the name was right: it applies a review.
- **A label escape hatch (a `[tree!]` or `[nowrite]` word).** Rejected. It
  widens the closed vocabulary that K-0011 fixed, and puts the reason in the
  help line, where `make help` would print it to every reader.
- **A warning instead of an error for the converse.** Rejected. A guarded
  `[read]` target fails every gate run that reaches it; a warning would let
  that ship and surface as a red gate in someone else's loop.
