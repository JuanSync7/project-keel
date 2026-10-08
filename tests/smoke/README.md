---
title: Smoke tests
kind: tests
layer: n/a
status: template
owner: TBD
summary: Fast post-deploy liveness checks.
id: tests-smoke-readme
created: 2026-06-17
updated: 2026-10-08
visibility: internal
canonical: true
---

# Smoke tests

Fast post-deploy liveness checks. Do **not** mirror source files — one file per scenario.

`make smoke` selects `-m smoke`, so every file here sets
`pytestmark = pytest.mark.smoke`. The one keel ships,
`test_app_runs.py`, runs `make run` with the allowlisted environment and
requires exit 0: it proves the composition root config/project.json
`layers.app` declares starts in a clean shell.

A smoke run in which zero tests ran fails, skips included
(`tests/selection_guard.py`). A project with no composition root
(`layers.app` null) has that test skip, so it declares `smoke` in
config/project.json `make_targets.empty_test_selections` with its reason, as
`src/app/README.md` says. Adding a smoke test that runs makes that declaration
stale, and the run fails until it is removed.
