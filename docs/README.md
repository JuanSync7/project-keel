---
title: Docs
kind: doc
layer: n/a
status: template
owner: TBD
public_api: none
tags: []
summary: Documentation organized by purpose and audience, not by source file.
id: docs-readme
created: 2026-06-17
updated: 2026-10-09
visibility: internal
canonical: true
---

# Docs

Documentation organized by purpose and audience, not by source file.

Where to start:

- [The guide index](guides/README.md) lists every guide, who it is for and
  what it is not for.
- [Your project's ADRs](adr/README.md) are numbered from `0001`;
  [the template's own ADRs](adr/keel/README.md) are cited as `ADR-K-NNNN`.
- [CONVENTIONS.md](../CONVENTIONS.md) is the source of truth for labels and the
  directory taxonomy.

| Subdir | Audience | Content |
|--------|----------|---------|
| `architecture/` | builders | system shape, components, data flow |
| `specs/` | builders/QA | requirements + acceptance criteria |
| `design/` | builders | per-feature design, task breakdown, contracts |
| `guides/` | adopters and contributors (each guide's row says which) | user guides, engineering guides, how-tos |
| `reference/` | everyone | per-module reference (the only part that thinly mirrors `src/`) |
| `adr/` | builders | Architecture Decision Records (numbered, immutable) |

Before writing anything here, read **[doc-style](guides/doc-style.md)** — how
prose is written in this repository, and the twin of
[python-style](guides/python-style.md) for code. `make check-docs` gates the
mechanical half; `make doc-review` reports the rest.
