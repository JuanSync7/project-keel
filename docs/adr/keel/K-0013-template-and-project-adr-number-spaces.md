---
title: "ADR-K-0013: Template and project ADRs live in separate number spaces"
kind: adr
layer: n/a
status: accepted
owner: TBD
tags: [adr, copier, update, numbering, check-y]
summary: "The ADRs a template ships and the ADRs a project writes are numbered in two spaces. A project's own ADRs are docs/adr/NNNN-<slug>.md, numbered from 0001; the template's are docs/adr/keel/K-NNNN-<slug>.md, shown as ADR-K-NNNN. config/project.json `adr` names both spaces and check_Y holds every ADR file to its space. On update, scripts/jobs/keep_edited_retired.py puts back a retired template ADR the project edited. This is the first breaking change to the generated-project contract, so the next release is 0.2.0."
id: docs-adr-0013-template-and-project-adr-number-spaces
created: 2026-10-07
updated: 2026-10-07
visibility: internal
canonical: true
---

# ADR-K-0013: Template and project ADRs live in separate number spaces

**Status:** accepted 2026-10-07 by the maintainer.

## Context

Until this decision keel shipped its ADRs as `docs/adr/NNNN-<slug>.md`, the
same directory and the same numbers a generated project uses for its own
decisions. Both measured downstream projects collided:

- **bedrock-platform** holds keel's 0001-0009 and its own 0010 (areas and
  effect labels). Keel has since written its own 0010, 0011 and 0012, so its
  next update would land a second 0010 beside the project's.
- **project-jarvis** holds keel's 0001-0004 and its own 0005-0011. Keel's
  0005-0011 are seven different decisions under the same seven numbers.
- **project-jarvis edited keel's ADRs.** Its copies of 0001-0004 carry
  `owner: Juan.Kok` where keel ships `owner: TBD`.

Moving keel's ADRs out of the shared directory is a rename, and copier does
not carry a project's edit across a rename. On `copier update` copier 9.17's
`_remove_old_files` deletes every file the old render had and the new render
lacks, edited or not, before any migration runs (measured). copier runs the
`_migrations` of the template it updates to whenever it can give both commits
a PEP 440 version, and it versions a commit with no tag ancestry through
dunamai: project-jarvis records `_commit: 72fd224`, which no tag describes,
and copier versions it `0.0.0.post17.dev0+72fd224` (measured), so its update
runs them.

## Decision

1. **Two number spaces.** A project's own ADRs live in `docs/adr/` as
   `NNNN-<slug>.md` and are numbered from 0001. The ADRs the template ships
   live in `docs/adr/keel/` as `K-NNNN-<slug>.md`. Each space numbers on its
   own, so a project's ADR-0010 and the template's ADR-K-0010 are two
   decisions, and neither blocks the other.
2. **The display form names the space.** A template ADR's title and heading
   begin `ADR-K-NNNN:`; a project ADR's begin `ADR-NNNN:`. A citation uses the
   same form.
3. **The spaces are configuration, not code.** `config/project.json` `adr`
   names `project_dir`, `template_dir`, `template_prefix`,
   `number_digits` and `template_adrs`, the file names the template ships in
   `template_dir`. The template writes that list; a project's decision under a
   free `K-` number would meet the template's next ADR of that number on
   update, so a file the list does not name is an error. CONVENTIONS §19 is the rule.
4. **check_Y holds every ADR to its space.** `scripts/check_structure.py`
   check_Y errors on an ADR in the project space that carries the template
   prefix, an unprefixed ADR in the template space, a file name outside its
   space's grammar, a file in the template space that `adr.template_adrs`
   does not list (or a listed name with no file), a `kind: adr` document
   anywhere but directly in one of the two directories, a number taken twice within one space, a `kind` other than
   `adr`, and a title that does not name its own file. A missing or malformed
   `adr` block is an error once the tree holds a `kind: adr` document.
5. **Ids are kept.** A moved ADR keeps its frontmatter `id:`
   (`docs-adr-NNNN-...`), so every corpus reference to it still resolves.
6. **An edited template ADR survives the move.** `scripts/jobs/keep_edited_retired.py`
   is the first `after` migration in `copier.yml`. It lists the files the
   update deleted and compares each with the template's blob at the commit the
   project was generated from. A copy that differs in anything but its
   frontmatter `updated:` value is put back from HEAD and named on stderr with
   its successor (`kept <path>: the project edited it and the template
   retired it (now <successor>)`). The kept copy shares
   its `id:` with the new K- file, so check_A reports the duplicate until the
   project resolves it as `docs/adr/README.md` describes.
7. **The audit reports it before the update.** `scripts/audit_project.py`'s
   `retired` group names each file the predicted update deletes that the
   project edited, by the same `is_edited` rule. It is an owed error.

## Consequences

1. **Versioning.** ADR-K-0009 left the version scheme beyond 0.1.0 open until
   "the first breaking change to a *generated* project's contract". This is
   that change: every template ADR moves, and a project's own ADR named with
   the template prefix becomes a gate error. The next release is therefore the
   next minor before 1.0, `0.2.0`. The maintainer cuts the tag under ADR-K-0009's
   tag-ordering rule; this decision does not tag, and no `v0.2.0` tag exists
   when it is written.
2. **An `rm` migration still wins over the guard.** The guard runs before the
   `copier.yml` migrations that delete a named path, so a file one of them
   deletes stays deleted, edited or not. `make audit-project`'s `retired` group
   names each such file the project edited before the update runs: for
   project-jarvis it names `tests/integration/test_copier_generation.py`
   (measured).
3. **A file the template renders from a `.jinja` source is not judged.** The
   guard puts it back and names it; the audit warns. Comparing a rendered file
   with its source would need the old answers and a render.
4. **ADR-K-0001 is refined, not superseded.** It decided that decisions are
   numbered and immutable; this decides which number space each one is
   numbered in. It supersedes nothing.

## Alternatives considered

- **Move the project's ADRs instead.** Rejected. A project owns its own
  numbers and its links to them; keel cannot rename files it did not write,
  and every project would pay for a template's choice.
- **Offset the template's numbers (9000 and up).** Rejected. It postpones the
  collision instead of removing it, and a project that reaches the offset, or
  a second template, collides again. A prefix cannot be reached by counting.
- **`_exclude` the template ADRs from generated projects.** Rejected. A
  project's agents and gates cite them (ADR-K-0011 and ADR-K-0012 explain why
  `make` targets carry labels and why a child gets an allowlisted environment),
  and `_exclude` never retires a file a project already has.
- **Rely on copier's deletion of the old paths.** Rejected on the measurement
  in Context: copier deletes an edited copy as readily as an unedited one, so
  project-jarvis's `owner:` edits to 0001-0004 would be lost without a word.
