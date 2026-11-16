---
title: CMP-19 — every structure check has an id and a failing twin
kind: design
layer: n/a
status: draft
owner: TBD
tags: [plan, template, downstream, freshness, taxonomy, effects, credentials, audit, convergence]
summary: The convergence record, slices and decisions for CMP-19.
id: docs-internals-campaigns-cmp-19
created: 2026-10-06
updated: 2026-11-16
visibility: internal
canonical: true
---

## CMP-19 — every structure check has an id and a failing twin

KEEL-CHECKID-1 closes row 44: a check can be registered without evidence that it
has ever rejected a planted fault.
The cap is three slices, one pass each and three review fix rounds each under
CONVENTIONS §17. Stop at CMP-19.S3 green or the cap.

| Slice | Capability | Proof | Status |
|-------|------------|-------|--------|
| CMP-19.S1 | Give every existing structure check one id, enforcement sentence and statically resolved fault-injection twin. | `tests/integration/test_check_twins_gate.py` rejects missing and stale rows, broken twins and zero rows. | implemented — on main, delivered by e3be9507; the done-condition is not re-audited |
| CMP-19.S2 | Prove each twin depends on its named check rejecting the fault. | `test_each_twin_fails_with_a_silent_check` requires each twin to fail when its check is made silent, with a positive twin count. | implemented — on main, delivered by 2e78dbe9; the done-condition is not re-audited |
| CMP-19.S3 | Link practice enforcement references to check ids. | `test_practice_check_ids_resolve` rejects an unknown check id; valid references preserve existing verdicts. | implemented — on main, delivered by 92ca0509; the done-condition is not re-audited |

CMP-19.S1 owns `scripts/checks_data.py`, its mirror unit test,
`tests/integration/test_check_twins_gate.py`, small fault-injection twins, the
CONVENTIONS check-contract sentence, the feature row and the changelog row.
The registry is declared data under CONVENTIONS §18, following
`scripts/audit_dependencies_data.py`; there is no prose copy of its membership.
The gate derives named check functions from source and resolves twin functions
by parsing their test modules without executing them.
A check helper outside the dispatch naming grammar is not a registered check.
The gate proves twin existence, not that a twin's assertion is meaningful.
Existing behavior tests and review establish the latter.

CMP-19.S2 owns the twin-dependence tests and any twin repairs they expose.
It derives its cases from the registry and runs each twin with that check
made silent, requiring the twin's assertion to fail.
S1 registers 26 checks: 19 twins already existed, seven short twins were
written, and zero ids are deferred. The S2 empty-twin backlog is empty;
an empty twin is always a finding. No blanket exemption permits one.

CMP-19.S3 owns the practice-reference migration, its loader and gate changes,
and their tests and documentation. It reuses the S1 registry rather than
introducing another list of checks.

Will not do in CMP-19: change check behavior, inventory project-owned checks or
other gate families, execute twins during static resolution, introduce a
mutation-testing service, or merge check ids into requirement and goal ids.
The requirement traceability prefix registry serves only those two families.

