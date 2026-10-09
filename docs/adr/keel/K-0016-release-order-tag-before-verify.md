---
title: "ADR-K-0016: Tag locally before the release verify, push only on green"
kind: adr
layer: n/a
status: proposed
owner: TBD
tags: [adr, release, tags]
summary: "A release rotates the changelog, updates the pin sites and commits; then it creates an annotated tag locally, runs the full make verify, and only on green pushes main and the tag together with git push --atomic. On red it deletes the local tag, fixes, commits and tags again. This replaces decision 4 of ADR-K-0009, whose verify-then-tag order cannot pass: the release verify runs a test that fails while a dated version heading has no tag."
id: docs-adr-0016-release-order-tag-before-verify
created: 2026-10-09
updated: 2026-10-09
visibility: internal
canonical: true
---

# ADR-K-0016: Tag locally before the release verify, push only on green

**Status:** proposed 2026-10-09 — supersedes decision 4 of [ADR-K-0009](K-0009-release-identity-and-the-tag-ordering-rule.md) only; decisions 1–3 stand.

## Context

Decision 4 of ADR-K-0009 orders a release as rotate, verify, tag, push. Its
decision 3 gates every dated version heading in `CHANGELOG.md` on a matching
git tag, and `tests/integration/test_release_identity.py`
`test_every_released_version_heading_has_a_matching_tag` is that gate. Once
the rotation has dated the heading, the verify that decision 4 runs next
includes that test, and the test fails, because the tag is created only after
the verify. So the procedure as written cannot reach a green verify: a release
either skips the verify or tags first, against the order the ADR states.

## Decision

1. Rotate `[Unreleased]` into a dated heading and open a fresh empty one,
   update the pin sites (`README.md`, `README.md.jinja`, the `--vcs-ref`
   comment in `copier.yml` and the `CHANGELOG.md` preamble) to the new version,
   and commit.
2. Create an annotated tag on that commit, locally:
   `git tag -a v<version> -m "v<version>"`.
3. Run the full `make verify`.
4. On green, push the commit and the tag in one step:
   `git push --atomic origin main v<version>`.
5. On red, delete the local tag (`git tag -d v<version>`), fix the failure,
   commit, and restart from step 2.

## Consequences

- The release verify runs with the tag present, so
  `test_every_released_version_heading_has_a_matching_tag` judges the state
  the push publishes.
- The tag always names the commit that was verified, which is the tip of
  `main` at push time, so
  `test_the_newest_tag_is_not_behind_the_default_branch_tip` holds.
- `--atomic` pushes the branch and the tag together or not at all, so `origin`
  never carries a dated heading without its tag, nor a tag ahead of its
  branch.
- A red verify leaves only a local tag, which no generated project can have
  resolved, so deleting it and tagging again rewrites nothing anyone fetched.

## What is deliberately NOT decided here

- **Automating the tag.** A make target or a CI job that tags and pushes is
  not decided; the steps above stay manual until one is proposed.
- Decisions 1–3 of ADR-K-0009, which stand unchanged.

## Alternatives considered

- **Keep verify-then-tag, and skip the heading test during a release.** That
  turns decision 3's gate off at the one moment it judges a new heading.
- **Tag and push before the verify.** A red verify would then leave a
  published tag that a project may already have resolved; fixing it means
  moving a public tag, which ADR-K-0009 decision 2 exists to prevent.
