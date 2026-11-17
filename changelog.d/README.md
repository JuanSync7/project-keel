---
title: Unreleased changelog entries
kind: doc
form: reference
layer: n/a
status: template
owner: TBD
summary: Keel-only bullet sources for Unreleased, with enforced independent names and explicit release rotation; dated history stays in the assembled changelog.
id: changelog-d-readme
created: 2026-11-17
updated: 2026-11-17
visibility: internal
canonical: true
---

# Unreleased changelog entries

Each file holds one complete bullet, its indented continuation lines and its
intentional blank separators, including the final newline. Entries have no
frontmatter. Write links relative to the assembled `CHANGELOG.md`, where
check_Q reads them. These sources never ship into a generated project.

`config/project.json` `changelog_fragments.categories` orders the `added`,
`changed`, `fixed` and `security` folders. Its `unsectioned` value names
`general`, for bullets above the first category. Governance files named
`README.md`, `AGENT.md` or `CLAUDE.md` are never entries.

Name an entry `<order>-<identity>.part`: a positive six-digit order, a hyphen,
and 32 lowercase hexadecimal UUID digits, followed by the suffix configured
in `reference_fragments.suffix`. Take one more than the largest order in the
category and generate a fresh UUID, for example with
`python3 -c 'import uuid; print(uuid.uuid4().hex)'`. Keep that name for edits.
Parallel lanes may choose the same order; their independently generated UUIDs
keep their filenames distinct. Sorting the merged names keeps every existing
entry's relative order. Do not renumber entries on merge.

`scripts/assemble_fragments.py` refuses a name outside this grammar, a name
longer than 255 UTF-8 bytes, names differing only in letter case, and files
that do not hold one bullet. It names the refused file before writing outputs.
`make assemble-fragments` writes references and Unreleased; `make check-fragments`
compares them without writing. It preserves the changelog preamble and every
dated section byte for byte. Edit entries here; read history in `CHANGELOG.md`.

For release, follow `CONTRIBUTING.md`: the assembler's `--release` and `--date`
flags rotate entries into a dated section and delete the consumed sources.
It does not tag. Commit the output and deletions together, tag locally, verify,
then push on green. Publication is atomic per file; interruption during source
deletion requires recovery before another assembly. Generated projects edit
their own changelogs by hand and disable fragment assembly in their manifest.
