---
title: Structure check
kind: tool
layer: cross-cutting
status: stable
owner: platform-team
public_api: scripts/check_structure.py
tags: [tool, enforce, structure]
summary: Validate repo structure + frontmatter against CONVENTIONS.md; read-only.
id: tool-structure-check
created: 2026-06-17
updated: 2026-09-02
visibility: internal
canonical: true
tool_command: python3 scripts/check_structure.py
tool_effect: read-only
---

# Structure check

## Command
`python3 scripts/check_structure.py`

## Purpose
Enforces CONVENTIONS.md — checks A–T: frontmatter validity and unique corpus
ids, documented dirs, the package and private-import boundaries, authored
coverage and the module header contract, tool-spec governance and the
tool↔agent binding, project facts, agent-rules symlinks, the gate-tier practice
boundaries, ruleset/twin/help/catalogue parity, cross-references, rosters and practice mechanisms;
plus the accountability warnings. This is how the `index_enforcer` proves the
repo is convention-clean before it trusts the corpus.

## When to use
- Before building/refreshing the corpus (a dirty tree yields a dirty index).
- After any structural edit (new dir, package, moved file).
- NOT for content/meaning questions — it checks structure, not semantics.

## Args
| Flag | Required | Default | Meaning |
|------|----------|---------|---------|
| (none) | — | — | Scans the repo root; no flags. |

## Output
`WARN <msg>` / `ERROR <msg>` lines on stdout, then
`check_structure: N error(s), M warning(s)`. Exit 0 = clean, 1 = errors.
Warnings never change the exit code.

## Side effects
READ-ONLY. Reads files; writes nothing; safe to run any number of times.

## Used by
- agents/index_enforcer
