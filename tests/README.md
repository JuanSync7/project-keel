---
title: Tests
kind: tests
layer: n/a
status: template
owner: TBD
public_api: none
tags: []
summary: Unit tests mirror src/; integration/e2e/smoke go by scenario.
id: tests-readme
created: 2026-06-17
updated: 2026-10-08
visibility: internal
canonical: true
---

# Tests

Unit tests mirror src/; integration/e2e/smoke go by scenario.

| Subdir | Mirrors `src/`? | Organize by |
|--------|-----------------|-------------|
| `unit/` | **Yes, 1:1** | source module |
| `integration/` | No | scenario (2+ real components) |
| `e2e/` | No | user journey |
| `smoke/` | No | liveness check |

`fixtures/` holds shared data; `conftest.py` holds shared pytest
fixtures. Markers (`unit`/`integration`/`e2e`/`smoke`) are declared
in `pyproject.toml` — select with `pytest -m`.

## A run in which zero tests ran fails

pytest itself exits 5 only when it collects nothing; a run whose every selected
test skipped exits 0 having executed no assertion. `conftest.py` counts the
tests that ran (passed, failed, or xfail) and, when the session ends,
`selection_guard.py` turns a run of zero into exit 5 with a message naming the
selection. That covers every `make` tier and a direct `pytest` call alike, so a
single file run alone whose tests all skip now exits 5 too.

The one exemption is a bare `-m <marker>` selection declared in
config/project.json `make_targets.empty_test_selections` with a reason: that
run exits 0 and prints the reason. A compound `-m` expression, the whole
suite, and a run narrowed by `-k` or an explicit path are never exempt, and the
message names that selection as given (`-m smoke -k name tests/x.py`), never as
the whole suite. Once a test of a declared marker runs, the declaration is
stale and the run exits 1 until it is removed. `--collect-only`,
`--setup-plan` and `--setup-only` (which execute no test by design), a run
that already failed, and an xdist worker are left alone.
