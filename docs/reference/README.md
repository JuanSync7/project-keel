---
title: Reference
kind: doc
layer: n/a
status: template
owner: TBD
summary: Per-module reference, the settings reference and the feature catalogue. The only docs that may thinly mirror src/.
id: docs-reference-readme
created: 2026-06-17
updated: 2026-10-10
visibility: internal
canonical: true
---

# Reference

Per-module reference. The only docs that may thinly mirror src/.

## What ships here

| Member | What it lists | Not for |
|--------|---------------|---------|
| `settings.md` | Every setting keel reads: each key of `config/project.json` and `config/practices.json`, each copier question, make variable, environment variable and command-line flag, with its default; `tests/integration/test_reference_drift.py` holds the rows equal to the code. | How to choose a setting for a task: the guides in `docs/guides/README.md` say that. |
| `features.md` | Every feature keel ships: what it does and why, how to run it, the settings it reads, its limits, its guide and which projects receive it; `tests/integration/test_reference_drift.py` holds the rows of the shapes the tree declares equal to the tree. | A setting's default or effect: `settings.md` lists those. |
