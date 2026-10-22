---
title: "ADR-K-0027: a generated project's own code warns until a hard date, from a record that only shrinks"
kind: adr
layer: n/a
status: proposed
owner: TBD
tags: [adr, gate, copier, upgrade, policy]
summary: "A keel gate test that adopts the expiring tier hands its finding lines to scripts/expiring_tier.py under a check id scripts/expiring_tier_data.py CHECKS registers. In the template repository, which holds copier.yml, every finding is red. In a generated project a finding whose identity (its line with the line number dropped) the baseline config/project.json expiring_tier.baseline names still records warns until expiring_tier.expires and is red from that day; an unrecorded finding and an entry no finding matches are red at once. make gate-baseline (scripts/record_gate_baseline.py, [tree,write]) writes the baseline from what the gate tests see, and may add entries only when .copier-answers.yml _commit differs from the commit the file records. expiring_tier.expires may be no later than CEILING, a keel-owned data file copier rewrites on every update. A hand edit is not prevented; review holds it."
id: docs-adr-0027-a-project-s-own-code-warns-until-a-hard-date
created: 2026-10-22
updated: 2026-10-22
visibility: internal
canonical: true
---

# ADR-K-0027: a generated project's own code warns until a hard date, from a record that only shrinks

**Status:** proposed. It edits no other ADR. It reads its block through the
one loader of [ADR-K-0022](K-0022-one-config-loader.md), reads the day through
the one run date of [ADR-K-0019](K-0019-one-date-per-gate-run.md), and labels
its make target under [ADR-K-0011](K-0011-make-target-effect-labels.md).

## Context

A keel gate test judges every file under its roots. In a generated project two
things went wrong with that.

- `tests/integration/test_exit_gate.py` failed a project's own code from the
  first `make test` after `copier update`, with no warning period.
- The two finding tests of `tests/integration/test_config_reads_gate.py`
  skipped in a generated project and only named what they saw, so a project's
  own direct read was never judged.

The maintainer ruled (docs/design/downstream-feedback.md, B1 and rulings 9 and
10) that a project's own code warns before it fails, until a hard date, and
that keel's own code stays red.

## Decision

- **Where the gate runs tells keel's code from a project's.** When
  `copier.yml` exists at the root, the gate is in the template repository and
  every finding is red. Anywhere else is a generated project. A fresh project
  is green under every answer set (`tests/integration/test_copier_generation.py`),
  so a finding there is in code the project wrote or edited.
- **A finding has an identity.** A finding line is
  `<file>:<line>: <rule> — <fix>`, and its identity is the line with the line
  number dropped. Identities are counted as a multiset. A line outside that
  grammar names no file and is always red.
- **A per-check baseline records the project's findings.** config/project.json
  `expiring_tier.baseline` names it; keel ships `config/gate-baseline.json`.
  A recorded finding warns as an `ExpiringTierWarning`. A finding with no entry
  left for it is red at once and names `make gate-baseline`. An entry no
  finding matches is red, so the file only shrinks. With no baseline every
  finding is red, so `copier update` stays red until the target runs once.
- **One writer, which grows the file only across an update.**
  `make gate-baseline` runs `scripts/record_gate_baseline.py`. It runs each
  registered gate test under pytest with tests/conftest.py's
  `--expiring-tier-record` option, so the record is exactly what the gate saw.
  It may add entries only when `.copier-answers.yml` `_commit` differs from the
  `commit` the file records; at the same commit it refuses each new entry and
  writes nothing. Its output is canonical JSON, so a second run writes the same
  bytes.
- **A hard date with a keel-owned ceiling.** config/project.json
  `expiring_tier.expires` is the day recorded findings turn red. It may be no
  later than `CEILING` in `scripts/expiring_tier_data.py`, 2027-01-31, a
  CONVENTIONS §18 data registry that copier rewrites on every update. An
  earlier date is the project's choice. The day is `scripts/run_date.py`
  `today`, so one gate run judges by one date.
- **The target is `[tree,write]`.** It rewrites a tracked file, which is
  `[tree]`, and its recipe opens with `$(WRITE_GUARD)`, which check_W allows
  only in a `[write]` recipe. The guard stops CI, a Ralph loop and the gate
  runner from recording a baseline unattended.

## Consequences

- A project runs `make gate-baseline` once after each `copier update` and
  commits the file. The guide `docs/guides/generate-and-upgrade.md` says so.
- A project's new finding is red at once, and its existing findings are red
  from the date.
- A keel file the project edited warns like the project's own code; the
  maintainer accepted that.
- Adopting the tier in another gate test is one `CHECKS` row and one
  `expiring_tier.apply` call, which `tests/integration/test_expiring_tier_wiring.py`
  holds together.

## Alternatives considered

- **A manifest of keel's files, or a fetch of the template.** Either would tell
  keel's files from a project's directly. The B1 ruling rejected both: copier
  ships no such manifest, and a gate must not reach the network.
- **A date with no record.** Every finding would warn until the date, and so
  would code the project writes after the update. The ruling keeps a new
  finding red at once.
- **The ceiling in config/project.json.** A project owns that file, so a later
  date would be one edit. The ceiling sits in a keel file instead, where an
  edit shows on the next update.

## Scope cuts

- Only the config-reads gate's two finding tests and the exit gate's helper
  and shared-module tests adopt the tier. The swallowed-error, change-comment,
  import-layer and committed-secret gates still fail a project's own code at
  once.
- ruff, mypy and check_structure findings are not under the tier: they are not
  gate tests and do not print the finding grammar.
- Nothing inside a repository stops a determined edit of the baseline or of
  `scripts/expiring_tier_data.py`. Review holds both.
