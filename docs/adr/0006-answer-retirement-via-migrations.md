---
title: "ADR-0006: Retire declined answers with `_migrations`, accepting the `--trust` requirement, amending ADR-0004"
kind: adr
layer: n/a
status: accepted
owner: TBD
tags: [adr, template, copier, migrations, update, trust]
summary: "`_exclude` prunes at generation but can never delete on update, so re-answering a question left the declined tree on disk and reddened the project's own gate; keel mirrors every answer-driven prune with a `_migrations` entry and accepts that `copier update` now requires `--trust`."
id: docs-adr-0006-answer-retirement-via-migrations
created: 2026-08-05
updated: 2026-08-05
visibility: internal
canonical: true
---

# ADR-0006: Retire declined answers with `_migrations`

**Status:** accepted — amends the update consequences of
[ADR-0004](0004-project-templating-copier.md), which stands otherwise.

## Context

ADR-0004 made keel's repo root a copier template and chose `copier update` as the
upgrade channel. Answer-driven pruning was implemented with `_exclude`: a project
that answers `frontend_stack: astro` never receives `src/frontend/react-vite`.

That is correct at **generation** and structurally incapable of being correct at
**update**. On update copier renders the old template copy with the **union** of the
old and new excludes, deliberately — the code comment reads *"so they won't be
included in the diff as deleted paths to prevent deletion"*
(`copier/_main.py:1391-1394`). An excluded path is therefore never *retired*, only
never *created*.

The consequence is not cosmetic. A project generated with `react-vite` that later
re-answers `astro` keeps the react-vite tree while `.copier-answers.yml` says it uses
astro. Measured on a real restack: **13 errors** from the project's own
`check_structure` — dangling `CLAUDE.md -> AGENT.md` symlinks plus a stack
`config/project.json` does not declare. The project's gate goes red through no act of
its own, as a direct result of running the update we advertise.

The same shape covers any project generated *before* a prune existed: it keeps the
files forever, and `copier update` is precisely what hands it the newer `ci.yml` that
runs them.

## Decision

**Every answer-driven `_exclude` entry gets a mirroring `_migrations` entry.** The two
are a contract: `_exclude` covers a project that never had the path, `_migrations`
covers one that did. The pairing is asserted for the whole class by
`tests/integration/test_copier_generation.py`, so a prune added later without its
retirement fails keel's own gate rather than surfacing as a mystery downstream.

Migrations are conditioned on `_stage == 'after'` — they must see the *new* answers —
and re-read the answer rather than diffing old against new, so a project that never
had the path simply runs a no-op `rm`.

## Consequences

- **`copier update` now requires `--trust`.** Migrations run arbitrary commands, so
  copier classes the template as unsafe (`_check_unsafe`) and *refuses* rather than
  silently skipping. This is a real cost and it is accepted: deletion cannot be
  expressed declaratively in copier, and an update that cannot delete is the defect
  above. Every documented update command carries the flag, pinned by a test rather
  than by prose.
- **Generation is unaffected.** `_check_unsafe` only counts migrations when
  `mode == "update"`, so `copier copy` and `make new` still need no trust flag.
- **Changing an answer deletes a directory a project may have edited.**
  `src/frontend/<stack>` is a real app tree. That is the honest meaning of switching
  stacks, and it is bounded by copier's own preconditions: update requires git and
  refuses a dirty subproject, so the deletion is always recoverable with
  `git checkout -- <path>`. The rule this sets is that `_migrations` must never name a
  path a project could have authored **from scratch**, where no such history exists.
- **Retirement is tested live, not asserted structurally.** A restack fixture
  generates with one stack, commits, updates to the other, and requires the declined
  tree to be gone *and* the project's own gate to pass.

## Alternatives considered

- **Leave it to release notes.** Rejected: it makes every future prune a manual
  migration note, and the failure is silent until someone else's CI goes red.
- **Delete from a copier task instead.** Tasks run on `copy`, not `update`, so they
  cannot retire anything for an existing project — and they would make *generation*
  require trust, which migrations do not.
- **Never prune by answer; ship everything and document deletion.** This is what
  `scaffold.py` did and what ADR-0004 rejected.
