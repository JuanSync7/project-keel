---
title: "ADR-0004: Interactive project generation via copier (root-as-template), superseding scaffold.py"
kind: adr
layer: n/a
status: accepted
owner: TBD
tags: [adr, template, scaffold, copier, generator, jinja2]
summary: Keel's repo root is a copier template — one command runs a Q&A and writes a tailored project; copier coexists with scaffold.py until a parity harness proves no loss, then scaffold.py is retired.
id: docs-adr-0004-project-templating-copier
created: 2026-07-16
updated: 2026-07-16
visibility: internal
canonical: true
---

# ADR-0004: Interactive project generation via copier (root-as-template)

**Status:** accepted

## Context

Project Keel is a template, but its only generator was `scripts/scaffold.py`: a
10.3k-line hand-authored Python program that emits ~81 artifacts with **no variable
substitution** (everything hardcoded `project_keel`), ships **all** frontend stacks
and transports for the user to "delete the rest", and keeps 28 source files as
**byte-synced embeds** (`_NAME_SRC = r'''...'''`) guarded by `check_scaffold_sync`.
There was no interactive Q&A and no one-command "make a tailored new project."

We want: a **one-command, interactive** generator that asks what the project is and
writes only the relevant skeleton (chosen stack, filled-in `config/project.json`,
pruned dirs), plus the ability to pull future template improvements into an existing
project.

## Decision

Adopt **copier** (a Jinja2 project templater), with **keel's repo root as the
template** (`_subdirectory: "."`).

- **Root-as-template, not a duplicated `template/`.** copier copies keel's real files
  **verbatim** and only renders files carrying the `.jinja` suffix. So keel stays a
  valid, self-gating working repo, and the template can never drift from the source —
  it *is* the source. This dissolves the need for the 28 byte-synced embeds: copier
  ships the real `runtimes/*.py`, `scripts/check_*.py`, etc. directly.
- **Only what varies gets a `.jinja` twin.** `config/project.json.jinja` renders the
  `check_H` manifest from the answers; `.copier-answers.yml.jinja` records them for
  `copier update`. These files are **inert to keel's own gates** (`build_corpus`
  matches `*.md`/`*.py` exactly; `check_H` reads the real `project.json`; mypy/ruff
  scope by extension), so they live in the repo without breaking `make verify`.
- **Core Q&A → the manifest.** `project_name`, `frontend_stack`, `backend_python`,
  `transports`, `profiles` map 1:1 to `config/project.json` (CONVENTIONS §15). The
  un-chosen frontend stack is pruned via answer-driven `_exclude`. `_preserve_symlinks`
  keeps keel's `CLAUDE.md → AGENT.md` links (else `check_I` fails).
- **Optional dependency.** `template = ["copier>=9"]` — the default install, CI, and
  pre-commit stay dependency-free (same pattern as the `langgraph` runtime extra).

## Coexistence, then gated retirement

copier is added **alongside** `scaffold.py`. `scripts/scaffold_parity.py` (and
`tests/integration/test_copier_parity.py`) generate the skeleton both ways and prove
copier reproduces **every artifact** scaffold.py emits — a coverage **gap** is a real
loss and fails; content differences are expected (copier ships keel's *current* files,
scaffold reconstructs from possibly-stale literals). At adoption the harness reports
**0 losses** (scaffold 246 files ⊆ copier 324). Only with that gate green will
`scaffold.py` + the 28 embeds + `check_scaffold_sync` be **retired** (a later,
separately-approved change).

## Consequences

- One command generates a tailored project: `copier copy gh:JuanSync7/project-keel DEST`
  (or `make new DEST=...`); `copier update` pulls later template improvements.
- The byte-sync machinery becomes redundant once scaffold.py is retired — a large
  simplification (a 10.3k-line generator + its sync gate removed).
- A new dependency (copier) exists, but it is optional and only needed to *generate*
  or *update* a project, never to build or test one.
- Transport-dir pruning (beyond the frontend stack) is a follow-up: `mcp`/`rest`
  couple to the Python test suite, while `api/grpc` + `api/edge_nginx` are cleanly
  separable.

See `docs/guides/deterministic-checks.md` for the check suite and
`docs/guides/` for the how-to.

## Addendum (2026-07-16): retirement executed

The parity gate ran green (`scaffold=246 files ⊆ copier=324`, **0 losses**), so the
coexistence phase is complete: `scripts/scaffold.py`, its 28 byte-synced embeds,
`scripts/check_scaffold_sync.py`, and the `scaffold_parity.py` harness (which had
nothing left to compare against) were **removed**. copier is now the sole generator.
The parity evidence lives in this repo's history (the harness and its green run are
recoverable from git); the removal touched only generator/meta machinery — the
generated project surface is unchanged.
