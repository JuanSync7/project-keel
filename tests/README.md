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
updated: 2026-06-17
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
