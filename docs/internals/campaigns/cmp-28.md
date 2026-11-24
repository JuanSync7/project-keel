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
updated: 2026-11-24
visibility: internal
canonical: true
---

## CMP-28 — the pushed main's CI goes green again

The `ci` workflow run on 7fd1d61c ended with 12 failed and 12912 passed, while the local landing verify of the same commit was green.
The last green `ci` run was on 7ecb5f83.
The 12 failures have four causes, one queue row each (rows 205 to 208). Each is a test that depends on something the local gate host does not vary. Two of the tests ship: the shell-sample case (row 206) and the SIGKILL case (row 207) also failed in the nested suites of generated projects, so a project generated before these fixes carries both until it runs `copier update`. Row 207 also names a window in shipped code: `scripts/resource_limits.py` `start_child` starts the child before its watcher, and CMP-28.S3 makes the test wait past that window and leaves the window open.
The cap is four slices, one pass each and three review fix rounds each under CONVENTIONS §17.
Stop at a green `ci` run on the pushed main, or at the cap.
Will not do in CMP-28: change `scripts/jobs/restamp_docs.py` or `scripts/resource_limits.py`, pin a linter version in CI, diagnose the weekly `canary` workflow, or add a linter to the local gate host.

| Slice | Gap | Status |
|-------|-----|--------|
| CMP-28.S1 | The update fixtures date their commits by the clock while the stamper runs on a pinned day, so three `copier update` cases fail on the calendar alone (queue row 205); `tests/doc_stamps.py` `pinned_day` dates both by one epoch, the three fixtures and `tests/integration/test_copier_project_checks.py` `cycle` use it, and a case holds the cycle's commits to the pinned days. | implemented — at 7fd1d61c on 2026-11-22, four days past the newest stamp, the date-pinned copier cases went from 3 failed and 65 passed to 69 passed; the new case failed on the old fixtures with the commits dated 2026-11-22 against a pinned 2026-11-19. Done — landing verify green at 17f0d93b |
| CMP-28.S2 | The shell-style sample is linted in a tree without the helper it sources (queue row 206); the sample's tree carries `scripts/exit_codes.sh`. | implemented — with ShellCheck 0.10.0 on `PATH` the lint case failed with SC1091 before and passed after; the local gate skips it. Done — landing verify green at 17f0d93b, where the case skipped for want of a linter |
| CMP-28.S3 | The SIGKILL case can kill the runner before its watcher has started (queue row 207); the case waits for the watcher. | implemented — with the watcher's start held back one second in a private PID namespace, the child outlived the old sequence and was ended under the new one; the cause in CI stays inferred, and a green `ci` run shows only that the case passes there. Done — landing verify green at 17f0d93b |
| CMP-28.S4 | The planted-red collection cases need a user namespace the `ubuntu-24.04` runner refuses (queue row 208); the owner chose the skip: `tests/integration/test_copier_generator_contract.py` `_require_private_namespace` probes the namespace before a planted red case runs, skips the case where the host has no `unshare` or `unshare` reports that the host refuses the namespace, naming the refusal, and fails the case on any other probe failure. | implemented — with an `unshare` first on `PATH` that refuses as the runner does, the case failed as in `ci` before and skips after, and the planted module is never collected; a stand-in that fails another way (a missing `setsid`, an unknown option, another exit status, an interpreter that is not there) fails the case; on the gate host the module's 75 cases pass with none skipped |

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
- S4 skips and does not lift the runner's restriction: the owner chose it on 2026-11-24, because lifting it changes the pipeline every generated project ships for a test those projects do not carry. The cost is that the four planted-red cases do not run in `ci` while the runner refuses the namespace. The probe's result decides, not a CI flag, so the cases run wherever the probe succeeds.
- S4 never runs a planted red case without the namespace: nothing in the test can tell a disposable runner from a shared host.
- S4 skips in two cases only: no `unshare` on `PATH`, and a refusal it recognises, which is `unshare` ending with status 1 and an access, permission, namespace-limit or invalid-argument error as its last line. Any other probe failure fails the case, because a skip would hide a broken tool on a host that could run the cases.
- S4's evidence for the refusal is partial. The runner's error text was read from the failing `ci` run; its exit status was not recorded there, and status 1 is inferred from util-linux 2.32.1 on the gate host, where a refused `unshare -m` ends with status 1. The namespace-limit and invalid-argument errors are read from unshare(2) and user_namespaces(7). If the runner's status differs, the four cases fail in `ci` with the probe's command, status and text, and do not skip.
- S4's refusal is a stand-in `unshare` that exits non-zero without running anything, so the proof plants no fault on the host.
