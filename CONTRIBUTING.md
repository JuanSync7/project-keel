---
title: Contributing
kind: doc
layer: n/a
status: template
owner: TBD
summary: How to add code/tests/docs without breaking the structure.
id: contributing
created: 2026-06-17
updated: 2026-06-24
visibility: internal
canonical: true
---
# Contributing

Work in the repo's development loops (test-first, bounded convergence,
end-to-end coverage) **and solve the general case, not the specimen in front of
you**; the playbooks are `docs/guides/dev-loops.md` and
`docs/guides/generic-solution.md`, and the rules are CONVENTIONS §17–§18. The
steps below are that discipline applied to one change:

1. Read `CONVENTIONS.md`.
2. New package → add `__init__.py` with `__all__`, a `README.md`, and a
   `CLAUDE.md`. Private modules are `_underscore`d.
3. New public symbol → re-export it from the package `__init__.py`.
4. New `src/` module → write the mirrored `tests/unit/...` test **first**
   (red), then the code (green), then refactor with the suite green.
5. New behavior across components → add a `tests/integration` or
   `tests/e2e` scenario and (if user-facing) a `test-docs/` plan entry.
6. Making a failing eval/golden/case pass → fix the **general rule or the
   generator**, not the instance: don't hardcode the expected output, branch on
   the specimen, or paste a golden datum into `src/`. Run `make advise` for an
   advisory pass that flags answer keys (distinctive literals that are both a
   test's expected value and hardcoded in `src/`); it never fails the build —
   the gate stays `make verify`. Genuine data belongs in a `*_data.py` registry;
   an intentional literal is annotated `# generic-ok: <reason>`. (CONVENTIONS §18.)
7. Run `make verify` (the full gate) — or at least `make lint test` — before
   pushing; treat green as the definition of done, not your own assessment.
