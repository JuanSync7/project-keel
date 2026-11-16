---
title: CMP-24 — a shipped document that reports a change fails the prose gate
kind: design
layer: n/a
status: draft
owner: TBD
tags: [plan, template, downstream, freshness, taxonomy, effects, credentials, audit, convergence]
summary: The convergence record, slices and decisions for CMP-24.
id: docs-internals-campaigns-cmp-24
created: 2026-10-06
updated: 2026-11-16
visibility: internal
canonical: true
---

## CMP-24 — a shipped document that reports a change fails the prose gate

KEEL-VOCAB-1 is queue row 47.
`tests/integration/test_doc_drift.py` refuses `doc_drift.forbidden_phrases` in shipped prose, but those phrases name only one host or one person.
`change_comments.phrases` holds code comments only, and `make doc-review` reports a change opener in prose as an advisory that never fails.
The campaign adds a reviewed set of compound report phrases to `forbidden_phrases` and reads the block through `scripts/config_loader.py`.
It does not promote the advisory openers, because a past participle or "now" at an opener is as often a present claim as a report.
The cap is two slices, one pass each and three review fix rounds each under CONVENTIONS §17.
Stop at CMP-24.S2 green or the cap.
Will not do in CMP-24: duplicate a phrase literal in Python, change the fence grammar, or repair config decoders that the drift test does not read.

| Slice | Gap | Status |
|-------|-----|--------|
| CMP-24.S1 | `tests/integration/test_doc_drift.py` refuses a reviewed set of compound report phrases that `doc_drift.forbidden_phrases` declares in both manifest twins, and reads the block through `scripts/config_loader.py` `KEYS`. | implemented — delivered by 2e054f51 and 6f731e04; review LAND in round 2, and its findings are row 179 |
| CMP-24.S2 | A generated project's own prose gate gives the same verdict on a planted report phrase (`tests/integration/test_copier_generation.py`), and CONVENTIONS §15 states the two collections' scopes. | implemented — delivered by 175930b6 and b5682b87; review LAND in round 1, and its wording finding is fixed in b5682b87 |

