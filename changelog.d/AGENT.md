---
title: Changelog entry agent rules
kind: rules
layer: n/a
status: template
owner: TBD
summary: Author one bullet per source file using the enforced order and UUID naming rule; assemble history without editing dated releases.
id: changelog-d-agent
created: 2026-11-17
updated: 2026-11-17
visibility: internal
canonical: true
---

# Changelog entry rules

Read `README.md` here for the enforced filename and bullet contract.
Add one file per bullet in its configured category. Keep existing entry names
stable, and use a fresh UUID for each addition. Read links from the assembled
changelog's location. Run `scripts/assemble_fragments.py`, then its `--check`
mode. Dated sections belong to release history; the assembler preserves them.
Release consumes entry files and follows the steps in `CONTRIBUTING.md`.
