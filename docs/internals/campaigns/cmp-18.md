---
title: CMP-18 — one excluded cabinet and a reachable index for shipped documents
kind: design
layer: n/a
status: draft
owner: TBD
tags: [plan, template, downstream, freshness, taxonomy, effects, credentials, audit, convergence]
summary: The convergence record, slices and decisions for CMP-18.
id: docs-internals-campaigns-cmp-18
created: 2026-10-06
updated: 2026-11-16
visibility: internal
canonical: true
---

## CMP-18 — one excluded cabinet and a reachable index for shipped documents

KEEL-CABINET-1 gives Copier adopters a shipped tree that names no path in an unconditionally excluded cabinet, enforced by the document-drift gate.
The cap is three slices, one pass each and three review fix rounds each under CONVENTIONS §17.
Stop at CMP-18.S3 green or the cap.
The gate lands at today's paths before the cabinet move.

| Slice | Gap | Status |
|-------|-----|--------|
| CMP-18.S1 | Extend the existing gate to shipped source text and repair its findings. | implemented — on main, delivered by 56365723; the done-condition is not re-audited |
| CMP-18.S2 | Move keel-only records, add one cabinet exclusion and assert real render absence. | implemented — on main, delivered by f425eaa7; the done-condition is not re-audited |
| CMP-18.S3 | Give every shipped document a reachable index. | implemented — on main, delivered by eb8e0c30, e77d1549; the done-condition is not re-audited |

CMP-18.S1 owns `tests/integration/test_doc_drift.py`, its temporary-tree regressions, the shipped files its extended scan flags, the gate-contract sentences in `CONVENTIONS.md`, `docs/guides/doc-style.md`, `docs/guides/deterministic-checks.md` and `docs/guides/limits-and-troubleshooting.md`, the feature row and the changelog row.
The scan reuses the shipping test's Copier matcher over unconditional exclusions from `copier.yml`.
Conditional exclusions are outside this gate's class.
It reads every shipped text source, including Jinja source without rendering answers, and counts and skips files containing a NUL byte.
A module-level `pytest.mark.skipif` using the copier-absent `_TEMPLATE_ONLY` guard exempts the whole test module.
No history prefix or table waives a mention.
Zero shipped files, zero unconditional exclusions or zero directory exclusions fail the gate.
ADR repairs change one cross-reference clause and restamp the record.

S1 regressions plant existing and nonexistent descendants of a directory exclusion and require two findings.
Mentions in Python, JSON, a Makefile, Jinja source, an ADR, a table row and a fenced block each require findings.
Removing the template-only module guard must expose its mention.
S1 controls retain guarded-module and excluded-source mentions and accept paths outside the exclusion boundary.
Each regression uses a temporary tree with a small copier configuration.
S1 reports the real-tree finding count before repairs and zero after repairs.

CMP-18.S2 owns the four design-record moves, the tracked run-directory move, `copier.yml`, the generation and shipping tests, the upgrade-guide inventory, the feature row and the changelog row.
The records move under `docs/internals/`, which one `_exclude` entry omits.
The coordinator moves the untracked run file.
Real renders must omit arbitrary cabinet descendants and retain a public prefix sibling and the design README.
The S1 gate derives the excluded set again after the move.
No declared private-path list, config key, Jinja extension or bridge implements the cabinet.

CMP-18.S3 owns `docs/README.md` and its twin, the cabinet README, the index-reachability tests, the index-contract documentation and twin registration, the feature row and the changelog row.
Its graph starts at the root README and follows index links to every shipped document.
An orphan, a disconnected cycle and an edge replaced by prose, a fence or a leaf-only mention must fail with positive document, index and edge counts.
Controls retain linked guides, ADRs and specifications, deduplicate twins and account for conditional absence.

Will not do in CMP-18: move or revise K-0004, K-0005, K-0016, CONTRIBUTING.md's release section, deterministic-checks.md's template-only audit, features.md or settings.md beyond S1's required repairs and gate-contract sentences.
The maintainer decides each of those documents.
Extra moves and ADR retirement remain outside this campaign.

