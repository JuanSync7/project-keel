---
title: Scratch
kind: doc
layer: n/a
status: draft
owner: TBD
public_api: none
tags: [scratch, handoff]
summary: Short-lived working notes for in-flight work — handoff state, worklists. Not a source of truth and not shipped to generated projects.
id: tmp-readme
created: 2026-08-06
updated: 2026-08-06
visibility: internal
canonical: false
---

# `tmp/`

Short-lived working notes for **in-flight** work: what a branch has landed, what
is left, and what a fresh session needs in order to continue on another machine.

**Nothing here is authoritative.** The sources of truth are `docs/` (plan, ADRs,
guides) and the gate itself. If a file here disagrees with `docs/`, `docs/` wins
and the file here is stale — fix it or delete it.

Delete the whole directory when the branch it describes merges. It exists because
a handoff note that lives in the repo travels with the work; one that lives in a
chat log does not.

`copier.yml` excludes this directory, so it never reaches a generated project.

## Contents

- `HANDOFF.md` — resume state for the template-hardening branch
  (`feat/keel-hardening-pass-1`).
