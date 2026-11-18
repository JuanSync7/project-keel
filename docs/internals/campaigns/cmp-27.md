---
title: CMP-27 — the test suite keeps its workers busy
kind: design
layer: n/a
status: draft
owner: TBD
tags: [plan, template, downstream, freshness, taxonomy, effects, credentials, audit, convergence]
summary: The convergence record, slices and decisions for CMP-27.
id: docs-internals-campaigns-cmp-27
created: 2026-11-18
updated: 2026-11-18
visibility: internal
canonical: true
---

## CMP-27 — the test suite keeps its workers busy

KEEL-VERIFYTIME-1 is queue row 91: a full `make verify` takes about three hours, and every landing pays for it twice, once in `make test-ship` and once in the full verify.
Lever L1 landed in 6ac0bdf7; this campaign takes the row's last lever first, the measurement of why four workers give little more than one, because that measurement found the largest cost.
The cap is two slices, one pass each and three review fix rounds each under CONVENTIONS §17.
Stop at CMP-27.S2 green or the cap.
Will not do in CMP-27: change `tests.workers`, drop or merge a nested-suite variant (L2), share test_copier_audit's old-tag renders (L4), reorder or regroup test modules, or add a build system.

| Slice | Gap | Status |
|-------|-----|--------|
| CMP-27.S1 | `make test` runs the suite on `tests.workers` workers under pytest-xdist's default `load` scheduling, which hands each worker a run of consecutive tests and never takes queued tests back, so one worker runs every heavy copier module while the other three sit idle; the recipe schedules with `--dist worksteal`, and the tests and docs that state the recipe say so. | implemented — the `make test` recipe passes `--dist worksteal`, the Makefile judge and both manifests' `tests.full_gate_options` accept only that value, the pytest-xdist floor is 3.2 in both pyproject files, and the recipe test fails without the flag; the Sonnet review approved with notes, and its two doc findings are fixed; done — landing verify at 3caf9d76: `make verify` 3398 s against 11103 s, junit `<testsuite time>` 3306 s against 10992 s and the model's 66 min, summed test time 11444 s against 13752 s over 12933 cases, workers 87% busy against 31%. The summed drop is all in the ship set (175.9 to 137.5 min; the rest stays at 53.3 and 53.2 min), mostly the four nested-suite cases (about 20 to about 9.6 min each); inferred cause: a generated project's shipped `make test` now steals work too. The baseline ran beside another project's full verify; this run had the heavy slot alone, with a 1-minute load median of 12.1. The same chain's `make test-ship`, still one process, took 7888 s against 10614 s |
| CMP-27.S2 | `make test-ship` runs the ship set in one process although the ship set is the heaviest part of the suite; the recipe runs it on `tests.workers` workers with `--dist worksteal`, as `make test` does after S1, and `tests.workers` set to 0 still runs it in one process. | planned |

### Baseline

The "before" record is chain64's run at ccc299db on 2026-11-18, niced, beside another project's full verify on the same host.
It is kept outside the repository, in the run's plan inputs, as `verifytime-baseline-ccc299db/` (junit report, gate record, collection order and the replay scripts).

| Measure | Before |
|---|---|
| `make verify` wall time | 11103 s |
| pytest wall time (`<testsuite time>`) | 10992 s |
| Summed test time | 13752 s (229.2 min) over 12927 cases |
| Worker utilisation, summed time over wall time times four workers | 31% |
| `make test-ship` wall time, one process | 10614 s; its 392 cases sum to 175.9 min |

The four slowest cases take about 20 minutes each and sit next to each other in collection order: the declined-showcase prune case and the three `test_a_generated_project_passes_its_own_suite` variants.

### Why the workers sit idle

pytest-xdist 3.8.0's `load` scheduler sends each worker an opening run of consecutive tests, a quarter of its share, and refills a worker in consecutive runs; it holds back a refill while a worker runs a long test, and it never moves a queued test to an idle worker.
The copier modules are consecutive in collection order, so one worker's run holds all of them.
Replaying the baseline durations in collection order through that rule gives a wall time of 182.8 min, with the workers finishing at 182.8, 21.3, 12.5 and 12.5 min; the measured pytest wall time is 183.2 min.
The `worksteal` scheduler, in the same xdist release, lets a worker with fewer than two queued tests take half of the longest queue, leaving that worker two.
The same replay under `worksteal` gives about 66 min for `make test` and about 66 min for the ship set on four workers.
These two figures are a model, not a measurement: the replay uses the baseline durations, which were taken with one worker running the heavy modules, so it ignores CPU and disk contention when several nested suites run at once, and the extra module-scoped renders a module costs on each worker that runs part of it.
A unit subset of 746 tests passes on four workers under `worksteal`, with the controller's per-worker exemption hand-over intact.

### Done-condition

CMP-27.S1 is done when its landing verify is green and its junit `<testsuite time>` is recorded against 10992 s, with summed test time recorded against 13752 s.
CMP-27.S2 is done when its landing `make test-ship` is green and its wall time is recorded against 10614 s.
Neither slice states a target time: the record says what the change bought, and a slower result is reported, not tuned to the model.

### Decisions

- The scheduler changes and the worker count does not. `tests.workers` stays at 4 because the baseline shows idle workers, not too few of them, and more workers would run more nested suites at once on a shared disk.
- `worksteal` and not `loadfile` or `loadscope`: those keep a module on one worker, and test_copier_generation alone sums to 124 min, so they would keep the long tail.
- The shipped `Makefile` is the same file keel runs, so a generated project gets the same scheduling. Three template-side facts move with it: `pyproject.toml` and `pyproject.toml.jinja` allow `pytest-xdist>=3.0`, and `worksteal` first shipped in pytest-xdist 3.2, so the floor rises to 3.2; the full gate refuses any option `tests.full_gate_options` does not list (tests/selection_guard.py), so both manifests list `--dist` with the one value `worksteal`; and the `tests` block's `_comment` in both manifests states the recipe.
- The slice's class search covers every test and doc that states the `make test` recipe, including tests/integration/test_copier_test_recipe.py, tests/integration/test_isolation_gate.py, tests/integration/test_isolation_docs.py, `docs/guides/dev-loops.md` and the `make test` and `tests.workers` reference entries.
- `tests.workers` set to 0 with `--dist worksteal` runs the session in one process: pytest-xdist 3.8.0 ignores the scheduling mode when it starts no workers (98 tests passed under `-n 0 --dist worksteal` on 2026-11-18).
- `make test-ship` gets workers in its own slice. Before this campaign only `make test` asked for workers, and the Makefile states that rule without a reason; the recorder that refuses `-n` (tests/conftest.py) guards a separate option that `make test-ship` does not pass.
- L2 and L4 are not built here. After S1 the wall time is expected to be bound by the four ~20-minute cases, and L2 saves time only by dropping the full nested suite on two variants, which is a coverage cut. Whether that trade is worth taking goes to the owner with S1's measurement; row 91 keeps L2 and L4 open until then.
- Each slice's landing verify is its "after" record, so no separate profiling run is planned. A heavy run waits for a handshake with the session that shares the disk.
