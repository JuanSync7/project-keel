---
title: Contributing
kind: doc
layer: n/a
status: template
owner: TBD
summary: How to add code/tests/docs without breaking the structure.
id: contributing
created: 2026-06-17
updated: 2026-10-09
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
2. New package → add `__init__.py` with `__all__` (check_C). New top-level
   directory → make it a CONVENTIONS §2 row or declare it in
   `config/project.json` `structure.extra_toplevel`, and add a `README.md` and
   a `CLAUDE.md` (check_B); a new directory directly under `agents/` (an
   agent, §13, or the shared `agents/tools/`, §10) needs the same two files. Private modules are `_underscore`d.
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

When a gate refuses you, `docs/guides/limits-and-troubleshooting.md` lists every
waiver, every exit code the gate's scripts return and the common fixes; when you
generate, adopt or update a project, `docs/guides/generate-and-upgrade.md` lists
each step `copier update` runs and how to recover from it.

## Release

A release follows [ADR-K-0016](docs/adr/keel/K-0016-release-order-tag-before-verify.md)
(proposed), which replaces the order in decision 4 of
[ADR-K-0009](docs/adr/keel/K-0009-release-identity-and-the-tag-ordering-rule.md).
`tests/integration/test_release_identity.py` fails `make verify` while a dated
version heading in `CHANGELOG.md` has no matching tag, so the tag comes first:

1. Rotate `[Unreleased]` in `CHANGELOG.md` into a dated `## [<version>]`
   heading, update every line that tells a reader which version to check out,
   and commit. ADR-K-0016 lists those lines for the keel template itself.
2. Tag that commit locally: `git tag -a v<version> -m "v<version>"`.
3. Run `make verify`.
4. On green, push both together: `git push --atomic origin main v<version>`.
5. On red, `git tag -d v<version>`, fix, commit, and go back to step 2.
