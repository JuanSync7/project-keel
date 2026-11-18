---
title: CMP-25 — an interrupted release and the template-only allowance fail loudly
kind: design
layer: n/a
status: draft
owner: TBD
tags: [plan, template, downstream, freshness, taxonomy, effects, credentials, audit, convergence]
summary: The convergence record, slices and decisions for CMP-25.
id: docs-internals-campaigns-cmp-25
created: 2026-11-18
updated: 2026-11-18
visibility: internal
canonical: true
---

## CMP-25 — an interrupted release and the template-only allowance fail loudly

KEEL-FRAG-2 is queue row 201 and KEEL-COPY-1 is queue row 203; both were queued when CMP-11.S3 landed.
KEEL-FRAG-3, row 202, is closed as not worth doing, so CMP-25 does not build it.
The cap is two slices, one pass each and three review fix rounds each under CONVENTIONS §17.
Stop at CMP-25.S2 green or the cap.
Will not do in CMP-25: change how an entry ends or how entries are joined, add a file that records a release in progress, or ship the changelog entry folders into generated projects.

| Slice | Gap | Status |
|-------|-----|--------|
| CMP-25.S1 | `scripts/assemble_fragments.py` refuses, naming each file and the version, an entry whose text already sits line-anchored in the newest dated section of `CHANGELOG.md`, on assembly, `--check` and `--release`, and writes nothing; `tests/integration/test_changelog_fragments.py` restores entries a completed release consumed in a toy repository and shows the refusal. | planned |
| CMP-25.S2 | A keel-side test holds the template-only allowance of `tests/integration/test_script_copy.py` `_assert_exemptions` to the test modules `copier.yml` `_exclude` prunes, in both directions, with a planted fault for each. | planned |

CMP-25.S1 owns the interrupted release.
`--release` publishes `CHANGELOG.md` and then deletes the entries it consumed, so a process stopped between the two leaves entries that the next assembly would render under `## [Unreleased]` as well as under the dated section.
The slice refuses that state instead of repairing it.
A repair that deletes files must know exactly which files the release consumed.
A side file of consumed names would know that only in the checkout that crashed: once the half-released state is committed, another checkout has no record.
The refusal is derived from tracked files, so it holds in every checkout, and it never deletes.
The remedy the refusal names is to delete the listed entries by hand, because their text is already published.
On 2026-11-18 no entry in `changelog.d/` or in `tests/fixtures/changelog-migration/changelog.d/` sits in the newest dated section, so the rule refuses nothing in the tree today.

CMP-25.S2 owns the allowance.
`_assert_exemptions` reads the allowance only where `copier.yml` is absent, that is in a generated project, so the allowance cannot be derived there at run time.
The slice holds the hand-kept list to `copier.yml` `_exclude` from keel instead: every excluded test module that has an exemption is allowed, and every allowed module is excluded.
It reuses the reader of `_exclude` that the shipping tests already use.

### Decisions

- KEEL-FRAG-3 is closed, not built. 105 of the 127 entries in `changelog.d/` end without a blank line, in the live folder and in the frozen migration fixture alike, because the hand-written history used tight bullets. Refusing such an entry would reject that history, and supplying a separator would change the assembled bytes that the migration test compares with the original. An entry that ends tight before a `###` heading passes `scripts/check_structure.py` and the tests that read `CHANGELOG.md` (probe on 7e4493cf).
- KEEL-FRAG-2 is narrowed from "the next run converges" to "the next run refuses, naming the files", for the reason under CMP-25.S1.
