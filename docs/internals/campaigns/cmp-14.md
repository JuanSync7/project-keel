---
title: CMP-14 — a gate sees every change it claims to judge
kind: design
layer: n/a
status: draft
owner: TBD
tags: [plan, template, downstream, freshness, taxonomy, effects, credentials, audit, convergence]
summary: The convergence record, slices and decisions for CMP-14.
id: docs-internals-campaigns-cmp-14
created: 2026-10-06
updated: 2026-11-16
visibility: internal
canonical: true
---

## CMP-14 — a gate sees every change it claims to judge

Read-only bug sweeps of `scripts/` and `tests/` on 2026-11-06 found five gates
that pass on an input they exist to catch; a refuter reproduced each one live,
except KEEL-REAPRACE-1, which a full `make verify` showed red at a load average
of about 45. Each slice fixes the class of its defect, not the case found. The
cap is one pass per slice, with at most three review fix rounds each; the stop
point is CMP-14.S6 green or the cap. The slices own no code file in common, so
they are built in parallel on keel-cmp10 and land together on one full
`make verify`.

| Slice | Gap | Status |
|-------|-----|--------|
| CMP-14.S1 | KEEL-SNAPSHOT-ID-1: `scripts/git_tree.py` `tree_snapshot` records only each listed path's porcelain code and working content, so a commit, a staged-only change, a mode change and a nested repository's moved HEAD all compare equal, and a gate step that made one of them passes as "no change". The snapshot records the HEAD commit and branch, each index entry, each path's working content and mode, and a nested repository's identity; one public helper names what differs between two snapshots with readable labels, and `scripts/gate_evidence.py` and `scripts/run_make_target.py` both read changes through it | implemented — on main, delivered by 41994174; the done-condition is not re-audited |
| CMP-14.S2 | KEEL-MARKATTACH-1: `scripts/pytest_markers.py` `attached_markers` credits a marker on a module or class that holds no collected test, an annotated `pytestmark` is unseen, and the e2e coverage scan credits a marker in a file `python_files` excludes or a directory `norecursedirs` skips. A marker counts only when it applies to a test pytest collects, `attached_markers` derives from `marked_tests`, and the scan walks `tests/` as pytest does | planned |
| CMP-14.S3 | KEEL-ANSWERS-1: a `project_name` holding a double quote renders broken JSON and TOML and leaves a half-generated project, and the `backend_python` validator judges the answer with its spaces removed while the raw answer ships. Every free-text question in `copier.yml` is refused at the question when the template cannot render it, and a validator judges exactly the text that ships | implemented — on main, delivered by 5566cb9c; the done-condition is not re-audited |
| CMP-14.S4 | KEEL-EXITDROP-1: an entry block that calls a module function, drops its result and then calls `finish(ExitCode.SUCCESS)` passes the exit gate, because `tests/integration/test_exit_gate.py` judges a dropped result only when no `finish` call is in the block. A result bound to a name that no `finish` argument reads is a finding in every entry block | implemented — on main, delivered by 601e7523; the done-condition is not re-audited |
| CMP-14.S5 | KEEL-REAPRACE-1: two cases of `tests/unit/scripts/test_run_make_target.py` that stand in a foreign waiter fail when the fake make exits before the runner's first poll, which a loaded host makes likely. Every case whose outcome needs make still running at the runner's first sleep holds make's exit on a condition that sleep sets, never on timing | implemented — on main, delivered by 7e139b89; the done-condition is not re-audited |
| CMP-14.S6 | KEEL-REAPRACE-2: the review of CMP-14.S5 showed two more cases of `tests/unit/scripts/test_run_make_target.py` that pass or fail by load: the background job that exits just after make starts its interpreter on no condition, so a slow start puts its exit outside the runner's settle time. A background job that a case needs running signals that it started, and make waits for that signal, bounded, before it exits | implemented — on main, delivered by ae30014d; the done-condition is not re-audited |

CMP-14.S1 owns `scripts/git_tree.py`, `scripts/gate_evidence.py`,
`scripts/run_make_target.py`, `tests/unit/scripts/test_git_tree.py`,
`tests/unit/scripts/test_gate_evidence.py`,
`tests/integration/test_gate_evidence_record.py`,
`tests/integration/test_refactor_doers.py`, the cases it appends at the end of
`tests/unit/scripts/test_run_make_target.py`, the `tree_digest` and
`tree_changed` rows of `docs/guides/deterministic-checks.md` and
`config/evidence/gate-record.schema.json`, its row of `scripts/README.md` and
`scripts/README.md.jinja`, and one `CHANGELOG.md` row. A `tree_digest` recorded
before S1 does not match one computed after it, and the schema version stays,
because the field's type and name do not change.

CMP-14.S2 owns `scripts/pytest_markers.py`,
`tests/unit/scripts/test_pytest_markers.py`,
`tests/integration/test_e2e_coverage.py` and one `CHANGELOG.md` row.

CMP-14.S3 owns `copier.yml`, `tests/integration/test_copier_answer_validation.py`,
`tests/integration/test_copier_toolchain_answer.py`, the `backend_python` row
of `docs/reference/settings.md` and one `CHANGELOG.md` row.

CMP-14.S4 owns `scripts/exit_code_table.py`,
`tests/unit/scripts/test_exit_code_table.py`,
`tests/integration/test_exit_gate.py` and one `CHANGELOG.md` row. The drop
finding keeps its wording, because a generated project's baseline keys on a
finding's text.

CMP-14.S5 owns every case of `tests/unit/scripts/test_run_make_target.py` that
acts in the runner's sleep, and one `CHANGELOG.md` row. CMP-14.S6 owns the
cases of that file whose background job exits just after make, and one
`CHANGELOG.md` row; it is built on S5's commit. S1 appends to the same file and
changes none of its existing lines.

Each slice works test-first: its brief names a regression case that fails on
keel-cmp10 at `33e7438` (S6: at S5's commit), and a fresh reviewer of the other model family than
its builder checks each case can fail. Will not do in CMP-14: the review NEXTs
queued as KEEL-ANSWERS-2, and the three questions held for the maintainer as
KEEL-TESTSEL-1, KEEL-ROLLBACK-1 and KEEL-PRIVATTR-1.

