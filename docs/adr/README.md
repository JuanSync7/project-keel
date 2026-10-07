---
title: Architecture decision records
kind: doc
layer: n/a
status: template
owner: TBD
public_api: none
tags: [adr, decisions]
summary: Where a decision is recorded. This directory is the project's own ADR space, NNNN-<slug>.md numbered from 0001; the ADRs the template ships live in keel/ as K-NNNN-<slug>.md.
id: docs-adr-readme
created: 2026-10-07
updated: 2026-10-07
visibility: internal
canonical: true
---

# Architecture decision records

An ADR records one architecturally significant decision: its context, the
decision, its consequences and the alternatives it rejected. ADRs are
immutable once accepted; a later decision supersedes an earlier one instead
of editing it (`docs/CLAUDE.md`).

## Two number spaces

ADRs are numbered in two spaces, so a template's decisions and a project's
never compete for a number (CONVENTIONS §19):

- **The project's space is this directory.** A project's own ADR is
  `NNNN-<slug>.md` here, numbered from 0001 whatever the template has
  written, and is cited as `ADR-NNNN`.
- **The template's space is [keel/](keel/README.md).** An ADR the template
  ships is `K-NNNN-<slug>.md` there and is cited as `ADR-K-NNNN`. The template
  updates those files and lists each one in `config/project.json`
  `adr.template_adrs`; a project does not write there or add to that list.

`config/project.json` `adr` names both directories, the `K-` prefix and the
four digits. check_Y in `scripts/check_structure.py` holds every ADR to its
space: an ADR here named with the `K-` prefix, an unprefixed ADR in `keel/`, a
file in `keel/` that `adr.template_adrs` does not list, an ADR (`kind: adr`)
anywhere but directly in one of the two directories, a number used twice
within one space and a title that does not name its own file are each an
error. The same number once in each space is not.

## A template ADR the project edited

When the template moves or retires an ADR, `copier update` deletes the
project's copy of the old path. The first `copier.yml` migration,
`scripts/jobs/keep_edited_retired.py`, puts the copy back when the project
edited it (any byte but the frontmatter `updated:` value) and names it on
stderr with its successor. The kept copy shares its `id:` with the template's
new file, so check_A reports a duplicate id until the project resolves it in
one of two ways:

1. **Carry the edit into the template's file.** Make the same change to the
   `K-NNNN` file in `keel/`, then delete the old copy.
2. **Make it a project decision.** Give the copy the next free project number,
   a new `id:` and a title that begins `ADR-NNNN:` for that number, then
   delete the old copy.

A later `copier.yml` migration that deletes a named path still wins over the
guard. Run `make audit-project` against the template before an update: its
`retired` group names each file the update would delete that the project
edited.
