---
title: "ADR-0010: Generation runs a stamping task, so `copier copy` needs `--trust`, amending ADR-0006 and ADR-0007"
kind: adr
layer: n/a
status: accepted
owner: TBD
tags: [adr, template, copier, tasks, trust, freshness, idempotency]
summary: "A project generated from keel and committed the same day failed its own doc-freshness test on arrival, because every `updated:` was a literal from keel's history. Generation now runs `scripts/jobs/restamp_docs.py` as a copier task and every update ends with the same writer as its last migration, so a document is stamped on the day it arrives. Tasks are unsafe to copier, so `copier copy` and `make new` now require `--trust`, which reverses ADR-0006's claim that generation is trust-free."
id: docs-adr-0010-generation-needs-trust-to-stamp-docs
created: 2026-10-06
updated: 2026-10-06
visibility: internal
canonical: true
---

# ADR-0010: Generation needs `--trust` to stamp documents

**Status:** accepted 2026-10-06 by the maintainer. It amends the "generation is unaffected" consequence of
[ADR-0006](0006-answer-retirement-via-migrations.md) and the "generation is
deliberately trust-free" reasoning in
[ADR-0007](0007-optional-showcase-and-project-owned-identity.md). Both ADRs stand
otherwise.

## Context

`updated:` means *touched in this repository*.
`tests/integration/test_doc_freshness.py` enforces that rule through
`scripts/jobs/review_docs.py`. Keel ships its documents with keel's own stamps.
A project that is generated and committed on the same day therefore holds
documents whose stamps are older than their first commit. The measurement:
generating from the working tree and committing once made 112 of 112 governed
documents stale. The project's gate was red on arrival, and the project had done
nothing to cause it.

The same defect recurs on every `copier update` that changes a document. The
three-way merge keeps the project's old stamp and lands a newer body, so the
commit that records the update makes the document stale.

The freshness rule is correct and stays as it is. The defect is that no doer
moves the stamp when a document arrives.

## Decision

1. **One writer.** `scripts/jobs/restamp_docs.py` sets a stale `updated:` to
   today. It reads the stamp through the same grammar as the judge
   (`review_docs.updated_span`), changes only the date bytes, and never moves a
   stamp backwards. It declares `rerun: fixed-point`, and
   `tests/integration/test_idempotence.py` proves the claim.
2. **At generation**, `copier.yml` runs it as a `_tasks` entry with no mode
   flag. The writer stamps only what git would commit: the untracked
   documents, the ones changed against `HEAD`, and the ones already stale
   against their last commit. With no git it stamps every document. That one
   rule is right in a bare directory and in a repository that already has
   history, where every arriving document is untracked. It is also right in
   every render `copier update` makes: the throwaway copies of the old and the
   new template and the real project are stamped alike, so their stamp lines
   agree and the update's patch applies.
3. **At update**, the last `_migrations` entry runs it after the merge. It
   restamps exactly the documents that differ from `HEAD`, plus any that are
   already stale against their last commit.
4. **By hand**, `make restamp-docs` runs it, and every stale finding from
   `review_docs` names that target as the remedy.
5. **Today** comes from `--today`, then `SOURCE_DATE_EPOCH` read in UTC, then
   the local clock. A pinned build therefore stamps the same day on every host.
   The judge resolves today through the same function
   (`review_docs.resolve_today`), so the writer and the judge never stand on
   different days. A stamp target is never earlier than the document's last
   commit date, because the judge reads that date from git and not from a
   clock.

## Consequences

- **`copier copy` and `make new` now require `--trust`.** Copier classes any
  template with `_tasks` as unsafe and refuses to copy without the flag; the
  refusal names "tasks". Every documented copier command carries the flag.
  `tests/integration/test_copier_generator_contract.py` pins this by scanning
  every fenced block in every tracked Markdown file, the expanded `make new`
  recipe, and the showcase's setup steps. The refusal itself is pinned by
  `tests/integration/test_copier_generation.py`.
- **The trust is bounded.** The task is one list-form command with no shell. It
  runs keel's own stdlib-only writer under copier's own interpreter
  (`_copier_python`), and that writer only edits `updated:` values under the
  destination.
- **Generation stays deterministic.** Two generations with the same answers and
  the same `SOURCE_DATE_EPOCH` are byte-identical. The writer does not leave
  bytecode in the project.
- **Both conflict modes are measured clean.** An update on a later day than
  the project's stamps moves the stamp line on both sides of the merge. Under
  copier's default `inline` mode `tests/integration/test_copier_update.py`
  measures no conflict markers, no unmerged paths and no `.rej` files. Under
  `--conflict rej` the same file measures no `.rej` file and no changed
  document after an update that changes one non-document file. An earlier
  design that skipped the real project (`--fresh-only`) left one `.rej` per
  governed document there, measured.
- **A pinned date can lag.** Under a `SOURCE_DATE_EPOCH` older than the real
  day, a modified document is stamped with the pinned day, and the judge
  accepts it because it reads the same pin. The commit-date floor keeps
  committed documents honest; an uncommitted edit carries the pinned day until
  it is committed.

## Alternatives considered

- **Weaken the rule so a template stamp counts as fresh.** Rejected. A stamp
  that does not mean "touched here" stops answering the one question
  `updated:` exists for.
- **Strip `updated:` from documents at generation.** Rejected. The project's own
  gate requires the key, so that trades a stale finding for a missing one.
- **Tell the task whether it runs on copy or update.** Rejected. Copier's
  `_copier_operation` would say so directly, but it arrived in copier 9.6.0 and
  keel's floor is 9.3.0. Deriving the mode from git (`--fresh-only`, a no-op in
  a tree with committed history) was tried and measured wrong twice: it left
  105 of 113 documents stale when generating into a repository with history,
  and one `.rej` per document under `--conflict rej`.
- **Run the writer only as a migration.** Rejected. Migrations do not run on
  `copy`, so the arrival defect is untouched.
- **Ask the generated project to run `make restamp-docs` before its first
  commit.** Rejected as the only fix. A step that every new project must
  remember is the step the first project forgot. The target is kept as the
  manual remedy.
