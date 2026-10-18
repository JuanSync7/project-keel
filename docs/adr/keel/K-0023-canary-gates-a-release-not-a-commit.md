---
title: "ADR-K-0023: the release canary gates a release, not a commit"
kind: adr
layer: n/a
status: proposed
owner: TBD
tags: [adr, release, canary, copier, update, gate]
summary: "No gate ran a generated project's own make verify, fresh or after copier update, so a frontend app without a lockfile kept CI red for five days. scripts/canary.py (make canary) renders each config/project.json canary.answer_sets set fresh and as an update from the previous release tag and runs that project's make verify. It costs one whole project verify per set and path, so it runs before a release push, weekly and on demand, and never inside make verify; a red canary blocks the push in CONTRIBUTING.md's Release steps and nothing else."
id: docs-adr-0023-canary-gates-a-release-not-a-commit
created: 2026-10-17
updated: 2026-10-18
visibility: internal
canonical: true
---

# ADR-K-0023: the release canary gates a release, not a commit

**Status:** proposed. It edits no other ADR. It adds a step to the release
order of [ADR-K-0016](K-0016-release-order-tag-before-verify.md), which is
accepted and so is not edited: CONTRIBUTING.md's Release section carries the
step, and this ADR is its record.

## Context

`make verify` tests each part of a generated project on its own: its
structure gate, its pytest suite, the evals, the trace, the exit gate and the
launcher. No test ran a generated project's whole `make verify`, with its
lint, type check, frontend suites and doc checks, and no test ran it after a
`copier update` from the previous release. The `react-vite` app shipped
without a `package-lock.json` (open item 17 of
`docs/design/downstream-feedback.md`), CI's npm resolved a tree of its own
under another Node major, and CI stayed red for five days before anyone traced
it.

A project's whole `make verify` is slow. Measured on the farm on 2026-10-17
with keel's two answer sets, one job per set and `canary.workers` 1, each
rendered project took 404 to 494 seconds, and the four projects (two sets, two
paths) about 31 minutes. keel's own CI run took 49 minutes on the same day
(run 39053838083).

## Decision

1. **The canary is a doer over copier, outside the gate.** `scripts/canary.py`,
   behind `make canary`, renders each config/project.json `canary.answer_sets`
   set from a snapshot of the checkout as it stands, fresh and as a
   `copier update` from the previous release tag, and runs `make fe-install`,
   `make fe-browsers` (each exits 0 with no frontend app) and the project's
   own `make verify`. It prints one line per set and path, keeps a failed project
   and deletes a passed one. `make verify` never runs it:
   `tests/integration/test_canary_wiring.py` fails a `verify` recipe that
   names it.
2. **It runs at three points.** CONTRIBUTING.md's Release steps run it after
   the release's `make verify` and before the push;
   `.github/workflows/canary.yml` runs it weekly and on a manual dispatch; and
   a maintainer may run it by hand. On this site the release step sends it to
   the farm through `scripts/launch.py`, sized by config/project.json
   `launcher.long_scripts."make canary"`.
3. **A red canary blocks the release push and nothing else.** At the Release
   step a red set means `git tag -d`, fix and start the step again, as a red
   `make verify` does. A red weekly run fails its workflow and uploads each
   kept project and its log; it blocks no commit and no pull request.
4. **The previous release is derived, never written down.** It is the newest
   dated `## [X.Y.Z]` heading of `CHANGELOG.md` whose tag exists and is a
   strict ancestor of `HEAD`, so a run on the release commit, which already
   carries its tag, updates from the release before it. With no such tag the
   canary exits 2 before it renders anything.
5. **It is keel's own.** copier.yml `_exclude` keeps the doer, its shared
   snapshot module, its tests and its workflow out of a generated project,
   whose `make canary` prints the template checkout's command and exits 2.

## Consequences

- A commit can break a generated project's own gate and stay green in
  `make verify` until the next weekly run or the next release. That window is
  the price of decision 3.
- Each release costs about 31 minutes of farm time more, and the weekly run
  as much on a GitHub runner.
- The release step needs the farm, or a host where four project verifies may
  run. config/project.json `launcher.farm.adapter` ships as `none`, so until a
  maintainer configures an adapter, `scripts/launch.py -- make canary` runs it
  on the calling host, niced and limited.
- An answer set covers only the answers it names. The `astro` stack is in no
  set, so no canary renders it; `tests/integration/test_frontend_lockfile_gate.py`
  holds its lockfile to its manifest without installing it.

## Alternatives considered

- **Run the canary in CI on every push and pull request.** Rejected for cost:
  about 31 minutes of four project verifies on top of CI's own 49, on every
  push. A pull request that breaks a generated project is then caught at the
  weekly run or the release instead.
- **Run it inside `make verify`.** Rejected: keel's `make verify` already
  takes about 105 minutes on the farm, the canary would add about 31 to every
  gate run, and its `fe-install` and `fe-browsers` steps reach the npm
  registry and the browser download, so a network fault would turn the gate
  red with no fault in keel.
- **Do not run it.** Rejected: the lockfile miss of open item 17 is the class
  of defect only a whole generated project shows, and it reached CI.
- **A fresh render only, no update path.** Rejected: a project in use meets
  keel through `copier update`, and a conflict or a migration fault shows only
  on that path.

## Scope cuts

Not built: an evidence record of a canary run beside the gate's
([ADR-K-0017](K-0017-gate-evidence-record.md)), a third answer set for the
`astro` stack, which would add about half again to the run, and a farm
adapter.
