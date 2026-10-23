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
updated: 2026-10-23
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
every node under it.

## When to use
- When the `index_enforcer` reports owner gaps, to enumerate exactly which
  docs/sections/symbols need an owner assigned.
- In CI/review to keep accountability from rotting.
- NOT to gate the tree (that is `structure_check`, which errors; this always
  exits 0) and NOT to build the corpus it reads (that is `build_corpus`).

## Args
| Flag | Required | Default | Meaning |
|------|----------|---------|---------|
| `--corpus` | no | `wiki/corpus.json` | corpus to read |
| `--json` | no | off | emit JSON instead of text |

## Output
A count plus one line per unowned node (`kind  node_id  (path)`); then a count
of the nodes on the default owner, from how many `TBD`s, with one line per
`TBD` location; then a count of the nodes with a real owner. With `--json`, a
list of the unowned nodes only (`node_id`, `kind`, `path`), the owner gaps
`index_enforcer` reads. No corpus present → prints a notice and exits 0.

## Side effects
READ-ONLY. Reads the corpus; writes nothing; no model call.

## Used by
- agents/index_enforcer
