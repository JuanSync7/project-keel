---
title: CMP-23 — a generated project learns what the template fixed, and its test loop is quick without standing in for the gate
kind: design
layer: n/a
status: draft
owner: TBD
tags: [plan, template, downstream, freshness, taxonomy, effects, credentials, audit, convergence]
summary: The convergence record, slices and decisions for CMP-23.
id: docs-internals-campaigns-cmp-23
created: 2026-10-06
updated: 2026-11-16
visibility: internal
canonical: true
---

## CMP-23 — a generated project learns what the template fixed, and its test loop is quick without standing in for the gate

KEEL-DRIFT-1, KEEL-TESTLOOP-1, KEEL-SLOWTEST-1 and KEEL-CICACHE-1 come from project-jarvis, a keel-generated project, on 2026-11-07.
The headline is template drift: keel added the pytest retention keys (`tmp_path_retention_policy`, `tmp_path_retention_count`) to `pyproject.toml` and its `.jinja` twin, and the project, whose `.copier-answers.yml` `_commit` is hundreds of commits behind, never took them; it measured 26 leftover pytest runs, 1.8 GB, in RAM-backed scratch.
The cap is four slices, one pass each and three review fix rounds each under CONVENTIONS §17.
Stop at CMP-23.S4 green or the cap.
A narrowed or changed-only run never counts as the gate: KEEL-TESTSEL-1 (row 86) makes a full gate refuse narrowing, and every target this campaign adds is labelled as outside `make verify`.
Will not do in CMP-23: CI path filters, because a documentation-only change still feeds checks that read documentation, and a filter is safe only when it is derived from what each check reads and is itself tested; and pytest-testmon as a default, because it is a new install the maintainer has not approved and it skips tests from a coverage map.

| Slice | Gap | Status |
|-------|-----|--------|
| CMP-23.S1 | `make audit-project DEST=` reports the template commit DEST records, how many template commits it is behind, and which template test and build settings it lacks, starting with the two pytest retention keys; a structure check fails when either key leaves `pyproject.toml` or its `.jinja` twin. | done |
| CMP-23.S2 | A changed-tests target reruns failures first (`--lf`/`--ff`) with the pytest cache on and its `cache_dir` inside the checkout and ignored by git, so the cache goes when the checkout goes and no cleanup step exists to forget; a configured path is relative to the checkout root, and the structure check refuses an absolute path or one outside the checkout; the target refuses by name when the cache plugin is off instead of running the whole suite, and is labelled never the gate. | done |
| CMP-23.S3 | `make test` reports the slowest tests with `--durations` sized from config, and a `slow` marker lets `make unit` skip a test that the full gate still runs. | implemented — on main, delivered by 9c04a481; the done-condition is not re-audited |
| CMP-23.S4 | CI caches pip downloads keyed on the dependency files, in the keel workflow and the template workflow. | implemented — on main, delivered by 32f015ac; the done-condition is not re-audited |

