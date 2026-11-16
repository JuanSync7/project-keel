---
title: CMP-22 — writers confine mutations to their authorized tree
kind: design
layer: n/a
status: draft
owner: TBD
tags: [plan, template, downstream, freshness, taxonomy, effects, credentials, audit, convergence]
summary: The convergence record, slices and decisions for CMP-22.
id: docs-internals-campaigns-cmp-22
created: 2026-10-06
updated: 2026-11-16
visibility: internal
canonical: true
---

## CMP-22 — writers confine mutations to their authorized tree

KEEL-PATH-CONTAIN-1 protects Copier engineers through resolved-path checks before a writer mutates the tree.
The cap is three slices, one pass each and three review fix rounds each under CONVENTIONS §17.
Stop at CMP-22.S3 green or the cap.
The campaign was planned under a working label and took the next free label when it landed, because check_Z refuses a gap in declared campaign numbers.
CMP-22.S2 also writes to the path the guard returns rather than the spelling it was given, and states or tests how an absolute export directory treats an internal link.

| Slice | Gap | Status |
|-------|-----|--------|
| CMP-22.S1 | The shared guard, and the scanner installer, scanner record and static export writers. | done |
| CMP-22.S2 | The remaining writers. | implemented — on main, delivered by 7fd0cb9a, 536c4ad6, d47db86e, 741fe030, b516a281; the done-condition is not re-audited |
| CMP-22.S3 | Verify-time refusal of an escaping frontend root. | implemented — on main, delivered by 5481c7e5; the done-condition is not re-audited |

