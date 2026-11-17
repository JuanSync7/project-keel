---
title: Reference
kind: doc
form: index
layer: n/a
status: template
owner: TBD
summary: Per-module reference, the settings reference and the feature catalogue. The only docs that may thinly mirror src/.
id: docs-reference-readme
created: 2026-06-17
updated: 2026-11-17
visibility: internal
canonical: true
---

# Reference

Per-module reference. The only docs that may thinly mirror src/.

## What ships here

| Member | What it lists | Not for |
|--------|---------------|---------|
| `settings.d/` | Independently authored settings rows and fixed table text; `make assemble-fragments` writes `settings.md`. | Reading settings: use `settings.md`. |
| `features.d/` | Independently authored feature rows and fixed table text; `make assemble-fragments` writes `features.md`. | Reading features: use `features.md`. |
| `settings.md` | Every setting keel reads: each key of `config/project.json` and `config/practices.json`, each copier question, make variable, environment variable and command-line flag, with its default; `tests/integration/test_reference_drift.py` holds the rows equal to the code. | How to choose a setting for a task: the guides in `docs/guides/README.md` say that. |
| `features.md` | Every feature keel ships: what it does and why, how to run it, the settings it reads, its limits, its guide and which projects receive it; `tests/integration/test_reference_drift.py` holds the rows of the shapes the tree declares equal to the tree. | A setting's default or effect: `settings.md` lists those. |

## Authoring entries

Keel's `config/project.json` `reference_fragments` names both roots and their `.part`
suffix. Each root holds `head.part`, one numbered subfolder per table, and
`tail.part` for fixed trailing text. A table's `head.part` holds its heading,
prose and two header lines. Every other file holds exactly one complete row,
including its final newline, with the header's number of cells. Its key is
the first code span in the first cell, or the whole cell when there is none.
Keys are unique within a table; the assembler refuses duplicates and malformed
entries before writing any output.

An entry's file name is its key percent-encoded with nothing left safe
(`/` becomes `%2F`, a space `%20`), plus the `.part` suffix. Tables already
sorted by key use that name alone. Other tables keep their historical order
by putting a six-digit prefix and `-` before it. A new entry in one of those
tables takes the next prefix; parallel entries may share a prefix because
their distinct keys keep filenames apart. The assembler refuses, before
writing any output, a name that does not encode its key and a table that
mixes the two forms.
Do not rename existing entries to insert a row. Run `make assemble-fragments`,
then `make restamp-docs` and `make check-fragments`. Readers use the assembled
Markdown files. Fragments carry no frontmatter and their links are relative to
the assembled file; the document gates judge the assembled Markdown.

An assembled-file merge conflict is resolved by taking either side and running
`make assemble-fragments` over the union of entry files. The assembler retains
the output's `updated:` line, so restamping and reassembly reach the same fixed
point after an addition or deletion. The fragment folders are keel-only and
excluded from generation. A generated project lists no fragment sets and edits
`settings.md` and `features.md` by hand; the check still refuses stray fragment
folders.
