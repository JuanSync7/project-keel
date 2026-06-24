---
title: Contributing
kind: doc
layer: n/a
status: template
owner: TBD
summary: How to add code/tests/docs without breaking the structure.
id: contributing
created: 2026-06-17
updated: 2026-06-22
visibility: internal
canonical: true
---
# Contributing

Work in the repo's development loops (test-first, bounded convergence,
end-to-end coverage); the playbook is `docs/guides/dev-loops.md` and the rule
is CONVENTIONS §17. The steps below are that discipline applied to one change:

1. Read `CONVENTIONS.md`.
2. New package → add `__init__.py` with `__all__`, a `README.md`, and a
   `CLAUDE.md`. Private modules are `_underscore`d.
3. New public symbol → re-export it from the package `__init__.py`.
4. New `src/` module → write the mirrored `tests/unit/...` test **first**
   (red), then the code (green), then refactor with the suite green.
5. New behavior across components → add a `tests/integration` or
   `tests/e2e` scenario and (if user-facing) a `test-docs/` plan entry.
6. Run `make verify` (the full gate) — or at least `make lint test` — before
   pushing; treat green as the definition of done, not your own assessment.
