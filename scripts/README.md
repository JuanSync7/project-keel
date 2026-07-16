---
title: Scripts
kind: script
layer: n/a
status: template
owner: TBD
public_api: none
tags: []
summary: Dev and CI automation, one-shots, and the deterministic checks.
id: scripts-readme
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Scripts

Dev and CI automation, one-shots, and the deterministic checks.

Executable helpers, not importable library code. Anything reused by the app
belongs in `src/`, not here. Project generation is `copier`-based (the repo root
is the template; see [ADR 0004](../docs/adr/0004-project-templating-copier.md)).

## Deterministic checks (the template linter)

These scripts keep the template structurally honest — labeling, package
boundaries, the doc/code corpus, and the published contracts:

- `check_structure.py` — conventions validator (checks A–M); `make check`.
- `jobs/check_corpus.py` — `wiki/corpus.json` integrity + build reproducibility.
- `agent_surface/generate_aad_schema.py --check` / `cdmon_sync.py --check` — contract drift.

Run them all with `make check-all` (or `make verify` for checks + lint +
types + tests). Each one's purpose, when to run it, and how to wire it as a
pre-commit / CI / scheduled hook is catalogued in
**[`docs/guides/deterministic-checks.md`](../docs/guides/deterministic-checks.md)**.
