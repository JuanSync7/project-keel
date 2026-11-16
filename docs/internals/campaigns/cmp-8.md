---
title: CMP-8 — a rule a tool can decide is held by a check
kind: design
layer: n/a
status: draft
owner: TBD
tags: [plan, template, downstream, freshness, taxonomy, effects, credentials, audit, convergence]
summary: The convergence record, slices and decisions for CMP-8.
id: docs-internals-campaigns-cmp-8
created: 2026-11-03
updated: 2026-11-16
visibility: internal
canonical: true
---

## CMP-8 — a rule a tool can decide is held by a check

The maintainer approved this campaign on 2026-11-03. It is KEEL-LINT-1 (queue
position 11) with KEEL-ERR-1 (position 15), and its slices are rows 2a, 2b, 3
and 4 of the table in "KEEL-LINT-1, the lint checks" below. Row 5, a stale
excuse, stays queued: ruff 0.15.18 reports 725 `RUF100` findings on `main` at
`4ccd795`, where the opening pass measured 45, so it needs scoping again. By
the maintainer's choice on 2026-11-03, CMP-8 runs before CMP-7 resumes and
before KEEL-TESTQ-1. The cap is five passes, the opening pass included, and the
stop point is CMP-8.S4 green or the cap, whichever comes first.

CMP-8 is done at its cap of five passes, the opening pass and one per slice: the full `make verify` was green on `b853dd1` (6895
passed, 6 skipped), and one fresh reviewer found no STOP and six NOTEs, which
queue position 74, KEEL-LINT-2, holds with row 5.

It is built in one lane from current `main`. The branch `keel-lint`, built on
2026-10-23 and 539 commits behind `main`, is read as a reference only: each
check is written test-first again against today's tree. One fresh reviewer
tries to break the lane before the merge, and the merge waits for a green full
`make verify` on the merged tree. The counts below are ruff 0.15.18 and a text
search on `main` at `4ccd795`, not a gate's measurement.

| Slice | Gap | Status |
|-------|-----|--------|
| CMP-8.S1 | R-CODE-7, a dropped error: the swallowed-error gate judges a narrow handler that only drops the error, `contextlib.suppress` and `ignore_errors=True` (16 such calls on `main`) through the expiring tier, with no ruff `S110` or `S112` (ruling 11); each code the gate owns is excused only with its code and a reason; KEEL-ERR-1, `agents/doc_reviewer/_brain.py` reading unparseable JSON as zero findings, is fixed | done |
| CMP-8.S2 | R-CODE-7, a narrow handler that returns or assigns a fixed value, `None` included, in place of the error; a function whose documented result for "absent" is `None` carries the excuse | done |
| CMP-8.S3 | R-CODE-18, a boolean by position: ruff `FBT001`, `FBT002` and `FBT003` (176 findings on `main`); the keyword-only conversion lands as its own mechanical commit | done |
| CMP-8.S4 | R-CODE-24, a cache maximum: ruff `TID251` bans `functools.cache` and `lru_cache`, and a bounded-cache helper reads its maximum from a `KEYS` row (3 caches on `main`); R-CODE-17's `ERA001` (1 finding on `main`) | done |

