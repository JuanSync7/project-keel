---
title: Accountability report
kind: tool
layer: cross-cutting
status: stable
owner: platform-team
public_api: scripts/accountability_report.py
tags: [tool, accountability, owner, governance]
summary: Read-only list of corpus nodes with no resolved owner (accountability gaps).
id: tool-accountability-report
created: 2026-06-17
updated: 2026-10-26
visibility: internal
canonical: true
tool_command: python3 scripts/accountability_report.py --corpus wiki/corpus.json
tool_effect: read-only
---

# Accountability report

## Command
`python3 scripts/accountability_report.py [--corpus PATH] [--json]`
> Requires Python ≥3.10 (per `pyproject.toml`); an agent invokes it via its own interpreter (`sys.executable`), not a bare `python3`.

## Purpose
Lists every corpus node whose owner could not be resolved
(`owner_source: none`) — the human-accountability gaps. A node inherits its
owner from a section/symbol marker, then frontmatter, then its parent; only
nodes that resolve to nothing are listed. A node whose chain ends on the `TBD`
placeholder answers to `accountability.default_owner` when one is set
(`owner_source: default`): the report counts those on their own line, listed
by the `TBD` each answers to, because writing the real owner there repairs
every node under it. A node that names no owner source at all (missing,
null, or outside CONVENTIONS §12's set) is unknown, neither owned nor `none`,
and the report counts it on its own line. build_corpus writes that where a
`README.md` above the node cannot be read, so the repair is to repair that
`README.md`, or to state an owner on the node, then rebuild the corpus.

## When to use
- When the `index_enforcer` reports owner gaps, to enumerate exactly which
  docs/sections/symbols need an owner assigned.
- In CI/review to keep accountability from rotting.
- NOT to gate the tree (that is `structure_check`, which errors; this exits
  0 on any corpus it can count) and NOT to build the corpus it reads (that is `build_corpus`).

## Args
| Flag | Required | Default | Meaning |
|------|----------|---------|---------|
| `--corpus` | no | `wiki/corpus.json` | corpus to read |
| `--json` | no | off | emit JSON instead of text |

## Output
A count plus one line per unowned node (`kind  node_id  (path)`); then a count
of the nodes on the default owner, from how many `TBD`s, with one line per
`TBD` location; then a count plus one line per node that names no owner
source; then a count of the nodes with a real owner (`frontmatter`, `marker`
or `inherited`). With `--json`, a
list of the unowned nodes only (`node_id`, `kind`, `path`), the owner gaps
`index_enforcer` reads. A row that lacks a field the report shows is still
listed: the field reads `(missing)` in text and `null` in JSON, and a row that
is not an object counts as one with every field missing. No corpus present →
prints a notice and exits 0. A corpus that is not JSON, not an object, or has
no `nodes` list (missing, null or another type) → prints nothing on stdout,
one stderr line naming the file and what is wrong with it, and exits 2
(`USAGE`). A module that imports the report and passes such a corpus to
`unowned`, `unknown` or `defaulted` gets a ValueError saying what is wrong
with it, never an empty list.

## Side effects
READ-ONLY. Reads the corpus; writes nothing; no model call.

## Used by
- agents/index_enforcer
