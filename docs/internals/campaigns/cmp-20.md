---
title: CMP-20 — blank-line HTML blocks cannot manufacture fences
kind: design
layer: n/a
status: draft
owner: TBD
tags: [plan, template, downstream, freshness, taxonomy, effects, credentials, audit, convergence]
summary: The convergence record, slices and decisions for CMP-20.
id: docs-internals-campaigns-cmp-20
created: 2026-10-06
updated: 2026-11-16
visibility: internal
canonical: true
---

## CMP-20 — blank-line HTML blocks cannot manufacture fences

KEEL-FENCE-HTML-1 serves engineers who start from the Copier template and keep it healthy with `make verify`: the fence scanners in `scripts/check_structure.py` and `scripts/jobs/review_docs.py` recognise CommonMark HTML block boundaries.
The cap is one slice, one pass and three review fix rounds under CONVENTIONS §17.
Stop at CMP-20.S1 green or the cap.
The campaign was planned under a working label and took the next free label when it landed, because check_Z refuses a gap in declared campaign numbers.

| Slice | Gap | Status |
|-------|-----|--------|
| CMP-20.S1 | Pin type-6 and type-7 HTML block starts, paragraph interruption and blank-line endings in both scanners. | done |

