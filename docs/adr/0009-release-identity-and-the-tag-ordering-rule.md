---
title: "ADR-0009: Release identity — a tag names a commit no descendant is ahead of"
kind: adr
layer: n/a
status: accepted
owner: TBD
tags: [adr, release, versioning, copier, upgrade, tags, changelog]
summary: "keel's first release is the current main tip, not the 2026-08-04 commit its CHANGELOG named in anticipation. A version heading may only exist for a tag that exists, and a tag may only name a commit that no already-generated descendant is ahead of — because copier resolves an untagged template to a `.postN.devM` version that compares GREATER than the tag, and refuses to update downwards. Tagging the older commit would have broken `copier update` for every project generated from main."
id: docs-adr-0009-release-identity-and-the-tag-ordering-rule
created: 2026-09-02
updated: 2026-09-02
visibility: internal
canonical: true
---

# ADR-0009: Release identity, and the tag-ordering rule

**Status:** accepted. Completes pass 1 of
[the hardening plan](../design/keel-hardening-plan.md), whose version-identity
half has been outstanding since `d0a25c4`. Governs every future release.

## Context

Version identity is the whole reason [ADR-0004](0004-project-templating-copier.md)
chose copier: a descendant should be able to state which keel it came from and
upgrade to a *named* known-good ref instead of a bare SHA. Pass 1 landed the
mechanics — the tracked `.copier-answers.yml`, `_min_copier_version`, and a
`## [0.1.0] — 2026-08-04` CHANGELOG section — and then **the tag was never cut**.

That left three defects, all measured on this tree:

1. **A version heading existed for a release that did not.** `git tag --list` was
   empty while `CHANGELOG.md` documented `[0.1.0]`. Nothing gated it, because no
   check reads keel's own changelog.
2. **Five shipped references assumed the tag resolved** — `CHANGELOG.md:8` and
   `:217`, `copier.yml:18`, `.github/workflows/ci.yml:9`, and `README.md:73` plus
   its twin (which pass no `--vcs-ref` at all, so copier resolves
   `self.ref or get_latest_tag`). Each one either errored or misled.
3. **The obvious repair was the harmful one.** Honouring the recorded date and
   tagging `v0.1.0` at `d0a25c4` looks like fidelity to the record. It is not:

   | Step | Measured |
   |---|---|
   | A project generated from `main` today records | `_commit: <main tip>` |
   | With `v0.1.0` at an ancestor, `git describe` renders that | `0.1.0.postN.devM` |
   | PEP 440 comparison | `0.1.0.postN.devM` **>** `0.1.0` |
   | copier on an update that would go backwards | refuses (`copier/_main.py`) |

   So the project's own documented `copier update --trust` would hard-error on
   day one, through no act of its author — the exact class of defect this
   hardening branch exists to remove.

A related fact, verified because it was previously believed backwards: copier
does **not** need a tag to run migrations. `Template.version` falls back to
dunamai, which synthesises `0.0.0.postN.devM+<sha>` from `git describe --always`
with zero tags. Answer retirement (ADR-0006) has been live all along. What the
absence of a tag actually cost was *nameable* identity, not machinery.

## Decision

**1. `0.1.0` is the current `main` tip, dated the day it is cut.** Not
2026-08-04. Nothing was ever released, so there has only ever been one release
and this is it; the August date recorded an intention, and a changelog that dates
an intention as a release is simply wrong. The `[Unreleased]` section and the
former `[0.1.0]` section are folded into one dated version, because every line in
both shipped for the first time in the same release.

**2. A tag MUST name a commit that no already-generated descendant is ahead of.**
In practice: cut at the tip, never at an ancestor. This is the durable rule, and
it is not a copier quirk — it follows from PEP 440 ordering plus copier's refusal
to update downwards. A tag placed behind live descendants is worse than no tag,
because it converts a working upgrade channel into a hard error.

**3. A version heading in `CHANGELOG.md` MUST correspond to a real tag**, and
this is gated (`tests/integration/test_release_identity.py`) rather than left to
discipline — the defect above survived precisely because nothing read the
changelog. `[Unreleased]` is exempt by definition, and a repository with no tags
at all is a real state (a fresh clone, a generated project), reported as such and
passed, per the absent-vs-broken split of [ADR-0007](0007-optional-showcase-and-project-owned-identity.md).

**4. The release procedure is: rotate, verify, tag, push — in that order.**
Rotate `[Unreleased]` into a dated heading and open a fresh empty one; run the
gate; tag the resulting commit; push the commit *and* the tag. Pushing matters:
every documented command resolves against `origin`, so a local-only tag fixes
none of the five references.

## What is deliberately NOT decided here

- **A version number scheme beyond this release.** `0.1.0` is a first named
  version, not a semver promise about a template's rendered output. When the
  first breaking change to a *generated* project's contract lands, that decision
  gets its own ADR.
- **Automating the tag.** Cutting a release stays a deliberate human act. The
  gate proves the changelog and the tags agree; it does not create either.
- **Backfilling history.** `Template foundations (pre-0.1.0)` keeps its place as
  an undated record of what predates the first release.

## Alternatives considered

- **Tag `v0.1.0` at `d0a25c4`, honouring the recorded date.** Rejected on the
  measurement in Context: it breaks `copier update` for every descendant
  generated from `main`. Fidelity to a date is not worth a broken upgrade
  channel, and the date recorded an intention that was never carried out.
- **Tag the old commit `v0.0.1` and the tip `v0.1.0`.** Rejected as invented
  history: `d0a25c4` was never released and no descendant was ever generated from
  it as a named version, so a tag there names nothing anyone can have.
- **Leave the tree untagged and delete the `[0.1.0]` heading.** Rejected: it
  resolves the contradiction by giving up the capability ADR-0004 was chosen for,
  and leaves `--vcs-ref` unusable in five documented commands.
- **A `check_*` letter for changelog/tag parity.** Rejected: `check_structure.py`
  is stdlib-only and must stay 3.6-safe, and this rule needs `git`. It also has
  no business blocking a pre-commit hook. It lands as an integration test, where
  the git dependency and the absent-repo path are both honest.

## Consequences

- `copier copy --vcs-ref v0.1.0 gh:JuanSync7/project-keel` works, and a bare
  `copier copy` resolves the newest tag — so all five references become true at
  once, on push.
- ADR-0008's grace-tier rule ("ship a new check WARN for one release, promote in
  the next") acquires a real boundary to count from. That free pass is now spent.
- A future release cannot silently claim a version again: the heading and the tag
  are gated against each other.
- Migrations gain real version boundaries. They already ran against synthesised
  dev versions; from here they run against named ones, which is what makes a
  `version:`-scoped migration meaningful should one ever be needed.
