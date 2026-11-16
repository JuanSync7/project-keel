---
title: CMP-21 — interrupted refactors recover the whole change set
kind: design
layer: n/a
status: draft
owner: TBD
tags: [plan, template, downstream, freshness, taxonomy, effects, credentials, audit, convergence]
summary: The convergence record, slices and decisions for CMP-21.
id: docs-internals-campaigns-cmp-21
created: 2026-10-06
updated: 2026-11-16
visibility: internal
canonical: true
---

## CMP-21 — interrupted refactors recover the whole change set

KEEL-ROLLBACK-2 follows ruling 3b in the rulings recorded after CMP-5.S3: a refactor's change set becomes a journalled transaction.
The cap is two slices, one pass each and three review fix rounds each under CONVENTIONS §17.
Stop at CMP-21.S2 green or the cap.
The campaign was planned under a working label and took the next free label when it landed, because check_Z refuses a gap in declared campaign numbers.

| Slice | Gap | Status |
|-------|-----|--------|
| CMP-21.S1 | Durable application, replay and caller recovery. | done |
| CMP-21.S2 | Explicit recovery, human discard and process-kill proof. | implemented — on main, delivered by 986b660b, 0ccfa2df; the done-condition is not re-audited |

