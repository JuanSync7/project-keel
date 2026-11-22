---
title: CMP-28 — the pushed main's CI goes green again
kind: design
layer: n/a
status: draft
owner: TBD
tags: [plan, template, downstream, freshness, taxonomy, effects, credentials, audit, convergence]
summary: The convergence record, slices and decisions for CMP-28.
id: docs-internals-campaigns-cmp-28
created: 2026-11-22
updated: 2026-11-22
visibility: internal
canonical: true
---

## CMP-28 — the pushed main's CI goes green again

The `ci` workflow run on 7fd1d61c ended with 12 failed and 12912 passed, while the local landing verify of the same commit was green.
The last green `ci` run was on 7ecb5f83.
The 12 failures have four causes, one queue row each (rows 205 to 208), and none is a fault in what keel ships: each is a test that depends on something the local gate host does not vary.
The cap is four slices, one pass each and three review fix rounds each under CONVENTIONS §17.
Stop at a green `ci` run on the pushed main, or at the cap.
Will not do in CMP-28: change `scripts/jobs/restamp_docs.py` or `scripts/resource_limits.py`, pin a linter version in CI, diagnose the weekly `canary` workflow, or add a linter to the local gate host.

| Slice | Gap | Status |
|-------|-----|--------|
| CMP-28.S1 | The update fixtures date their commits by the clock while the stamper runs on a pinned day, so three `copier update` cases fail on the calendar alone (queue row 205); `tests/doc_stamps.py` `pinned_day` dates both by one epoch, the three fixtures and `tests/integration/test_copier_project_checks.py` `cycle` use it, and a case holds the cycle's commits to the pinned days. | implemented — at 7fd1d61c on 2026-11-22, four days past the newest stamp, the date-pinned copier cases went from 3 failed and 65 passed to 69 passed; the new case failed on the old fixtures with the commits dated 2026-11-22 against a pinned 2026-11-19 |
| CMP-28.S2 | The shell-style sample is linted in a tree without the helper it sources (queue row 206); the sample's tree carries `scripts/exit_codes.sh`. | implemented — with ShellCheck 0.10.0 on `PATH` the lint case failed with SC1091 before and passed after; the local gate skips it |
| CMP-28.S3 | The SIGKILL case can kill the runner before its watcher has started (queue row 207); the case waits for the watcher. | implemented — with the watcher's start held back one second in a private PID namespace, the child outlived the old sequence and was ended under the new one; the cause in CI stays inferred, and a green `ci` run shows only that the case passes there |
| CMP-28.S4 | The planted-red collection cases need a user namespace the `ubuntu-24.04` runner refuses (queue row 208); the fix waits for the owner's choice among the row's three options. | planned — waits for the owner |

### What failed, and why only in CI

| Failed cases | Cause | Why the local verify was green |
|---|---|---|
| 3 in `tests/integration/test_copier_update.py` | fixture commits dated by the clock, two days past the template's newest stamp (S1) | it ran within one day of the newest stamp |
| 1 in `tests/integration/test_shell_style_sample.py`, and the same case inside each of 4 nested suites | the sample's tree lacks the helper it sources (S2) | the host has no shell linter, so the case skips |
| `test_a_sigkilled_runner_leaves_no_bounded_child_running` inside 3 of the 4 nested suites | the runner can be killed before its watcher starts (S3) | the window is short on an idle host |
| 4 `test_runtime_collection_*` in `tests/integration/test_copier_generator_contract.py` | the runner refuses the user namespace (S4) | the host allows it |

The four nested-suite cases in `tests/integration/test_copier_generation.py` fail for the S2 and S3 causes together, and have no cause of their own.

### Done-condition

A slice is done when its landing verify is green.
The campaign is done when a `ci` run on the pushed main is green; a push needs the owner's yes, and only that run can show S3's case and S4's fix passing on the runner.

### Decisions

- S1 fixes the fixtures and not the stamper. The stamper raising a stamp to its document's commit date is the rule the freshness judge relies on; the fixtures broke their own premise by committing on a day they did not pin.
- S1's proof ran on a tree whose newest stamp was four days old. A tree that carries a stamp from the day of the run passes the three cases with or without the fix, so this document's own commit hides the fault for a day.
- S2 puts the helper in the sample's own tree and not in the shared `_sh_tree` builder, whose other callers judge trees without it.
- S2's red and green were measured with a ShellCheck 0.10.0 binary on `PATH` for that one run; the local gate still skips the case.
- S3 changes the test and not the supervisor. The test asserts what the watcher does, so it must not act before the watcher exists.
- S3's planted delay ran inside a private PID namespace, never on the host.
- S4 is not built until the owner chooses, because one option changes the pipeline every generated project ships.
