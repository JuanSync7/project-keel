---
title: Unit tests
kind: tests
layer: n/a
status: template
owner: TBD
summary: Mirrors src/ 1:1.
id: tests-unit-readme
created: 2026-06-17
updated: 2026-10-09
visibility: internal
canonical: true
---

# Unit tests

Mirror `src/` exactly: `src/<pkg>/<mod>.py` → `tests/unit/<pkg>/test_<mod>.py`. A subpackage counts as one module tested through its `__init__.py`, so `src/backend/example_feature/` (whose code is in a private `_impl.py`) → `tests/unit/backend/test_example_feature.py`. Test via the public API.
