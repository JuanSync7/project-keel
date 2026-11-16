---
title: CMP-10 — a refused config file stops every reader, and a wrong claim in a doc is caught
kind: design
layer: n/a
status: draft
owner: TBD
tags: [plan, template, downstream, freshness, taxonomy, effects, credentials, audit, convergence]
summary: The convergence record, slices and decisions for CMP-10.
id: docs-internals-campaigns-cmp-10
created: 2026-10-06
updated: 2026-11-16
visibility: internal
canonical: true
---

## CMP-10 — a refused config file stops every reader, and a wrong claim in a doc is caught

The maintainer approved the queue order of KEEL-JSONDUP-1 (position 39) and
KEEL-DOC-2 (position 21) on 2026-10-22. The branch `keel-doc2` built both on
2026-10-24 from a `main` that has since moved 390 commits, including ADR K-0022
(`scripts/config_loader.py` is the one config loader) and the swallowed-error
gate, and a dry merge conflicts in 41 files. CMP-10 therefore rebuilds the two
rows on `main`, test-first, with `keel-doc2` as a reference only. The cap is
four passes, one slice each in the order S1 to S4, and a slice's review gets at
most three fix rounds; the stop point is CMP-10.S4 green or the cap, whichever
comes first. A slice that does not fit its pass is reported as
done-versus-remaining and queued.

The opening pass probed `main` at `25de8e2` on a copy, one run of each entry
point per fault. A key written twice in `config/project.json` passes
`scripts/check_structure.py` with exit 0 and `scripts/run_app.py` with exit 0.
A conflict hunk ends `scripts/exit_code_table.py`, `scripts/run_evals.py` and
five other readers with exit 14, where the copier jobs end it with exit 2.
`scripts/run_app.py` ends a hunk, bad UTF-8 or an empty file with a traceback,
and so does `scripts/jobs/declare_no_app.py` on bad UTF-8.
`scripts/jobs/export_showcase_static.py` skips, with exit 0, a manifest it
cannot read. No document check reads a cited check letter, and
`scripts/jobs/review_docs.py` has no advisory for a change phrase at a thought
opener. The session budget and the showcase-test pruning that `keel-doc2` also
holds are already on `main`, so CMP-10 does not rebuild them. The counts are one
probe, not a gate's measurement.

| Slice | Gap | Status |
|-------|-----|--------|
| CMP-10.S1 | `scripts/check_structure.py` reads both JSON configs through `config_loader.read`, which alone decides absence. A duplicate key, conflict hunk, bad bytes, wrong top level, directory at the path or I/O failure gives one finding per loader line naming the file, reported once per run; dependent checks apply no absent-file defaults. `scripts/run_app.py` ends a refused or missing manifest with exactly one stderr line naming config/project.json, no traceback and empty stdout: exit 2 for a hunk, 14 for any other refusal. The ten remaining `config_reads.allowed` entries agree with the gate ceiling and settings reference. The refusal integration matrix and loader, root, check_B and run_app unit cases cover these boundaries; the scripts and gate test ship through copier | implemented — second fix round |
| CMP-10.S2 | The same refused manifest ends every other script the same way, one rule: a conflict hunk is exit 2 (the user resolves it, as in the copier jobs) and any other refusal, bad UTF-8, an empty file, `null` or a key written twice, is `CONFIG` (exit 14), never a traceback or a skip. One `is_conflict` helper in `scripts/config_loader.py` decides it, and `exit_code_table`, `run_evals` (`evals/_config.py`), `declare_no_app`, `export_showcase_static`, `long_scripts`, `trace_requirements` and `launch` use it; a launcher `render()` refusal names the edit that clears it, and `LauncherConfigError` has no default remedy; a `gate_evidence` schema file that is not UTF-8 is `CONFIG`. It starts from `tests/integration/test_conflict_entry_points.py::test_every_entry_point_that_reads_the_manifest_ends_a_conflict_hunk_at_2`, which discovers each script under `scripts/`, `scripts/jobs/`, `scripts/hooks/` and `evals/` that reads the manifest, runs it on a copy with a hunk and fails on a count of zero, and from `tests/unit/scripts/test_exit_code_table.py::test_a_conflict_hunk_exits_2`. It ships through copier, since every script it edits is a template file | implemented — on main, delivered by 2cfe2eff, 0c6d4ee7, 0fc72e7f, 38cde3e3, d1144a3b, 7ac88396; the done-condition is not re-audited |
| CMP-10.S3 | A wrong claim in a shipped document passes every gate: a `check_<LETTER>` or a prose "check X" that `check_structure.CHECKS` lacks, and a `check_<name>` no Python file defines, are not read. A user gets `make verify` red naming the document and the cited check, and the guide's one sentence on which marks count as a citation is held by a test that goes red when a mark's effect is inverted. It starts from `tests/integration/test_doc_drift.py::test_a_document_citing_a_check_that_does_not_exist_fails` and `::test_the_check_name_sentence_fails_when_a_mark_effect_is_inverted`, and ships through copier where `tests/integration/test_doc_drift.py` is a template file; the opening step of S3 reads `copier.yml` to say whether it is | implemented — on main, delivered by 09a59e95, 4eae0c0f, 5b63ab1f, d856824f, fe42fa39, ecbac165, ff8244eb; the done-condition is not re-audited |
| CMP-10.S4 | A change phrase at the opening of a thought (a paragraph, list item, heading, table cell or sentence that starts with a `change_comments.phrases` entry) reaches no reader. A user running `make doc-review` gets one advisory `OPENER` line per hit, in `.md.jinja` twins too, and no mode fails on it, because a past participle at an opener is as often a present claim as a report. It starts from `tests/unit/scripts/test_review_docs.py::test_a_change_phrase_at_a_sentence_opener_is_an_advisory_line` and `::test_an_opener_advisory_fails_no_mode`; the guides' own hits on `main` are fixed by hand in the same slice; it ships through copier, since `scripts/jobs/review_docs.py` is a template file | implemented — on main, delivered by 2001278c, e1e31c9d, 562c5c5f, 3b94e696; the done-condition is not re-audited |

CMP-10.S1 owns `scripts/check_structure.py` (`_read_json_config` and its
consumers), `scripts/run_app.py`, `scripts/config_loader.py` (the `is_conflict`
helper, which S2 reuses) and the two `config_reads.allowed` rows for
`scripts/check_structure.py` and `scripts/run_app.py` in `config/project.json`.
It borrows from `keel-doc2` the commits `9d0d0b9` and `2dfeb74` for the gate's
read and `5bbc6ab` for `run_app`, and rewrites each against `main`'s loader,
which already refuses a duplicate key, NaN and bytes that are not UTF-8.
`scripts/check_structure.py` runs under the oldest host interpreter, so the
import must work there and a failed import must fail the gate, not skip it.

Fix round 2 corrects the stale allowlist counts, the filesystem prechecks that
read a refused config as absent, and the two runner tests whose single-line
claim accepted extra output. Planted stale counts, presence checks, swallowed
read errors and runner output each turn their regression cases red.

CMP-10.S2 owns `scripts/exit_code_table.py`, `evals/_config.py`,
`scripts/run_evals.py`, `scripts/jobs/declare_no_app.py`,
`scripts/jobs/export_showcase_static.py`, `scripts/launch.py`,
`scripts/long_scripts.py`, `scripts/trace_requirements.py`,
`scripts/gate_evidence.py`, `scripts/cdmon_sync.py` and the new discovery test.
It borrows `52b07d0`, `20d3a37`, `4a7c0f3`, `95783a3`, `ce795cb`, `d610da4`,
`bd667f7` and `04277ea` from `keel-doc2`. It shares `scripts/config_loader.py`
with S1, so it runs after S1. It shares `CHANGELOG.md`, `docs/reference/settings.md`
and `docs/guides/limits-and-troubleshooting.md` (the exit-code table) with S1;
KEEL-FRAG-1 (position 4) is still open, so the two do not run in parallel.

CMP-10.S3 owns `tests/integration/test_doc_drift.py`, `docs/guides/doc-style.md`
(the check-name sentence) and the `doc_drift` block of `config/project.json`
and its row in `scripts/config_loader.py`. It borrows `5aaf7a5`, `cb31508`,
`7b18150`, `a4442de` and `16f5dbf` from `keel-doc2`; the sentence is written
again against `main`'s guide, because the guide is not the one the lane edited.
It shares `docs/guides/doc-style.md` and `config/project.json` with S4, so S4
runs after S3.

CMP-10.S4 owns `scripts/jobs/review_docs.py`, `tests/unit/scripts/test_review_docs.py`
and the guides' own hits. It borrows `0c31e63`, `aca6f06`, `4ab411e`, `a02ccf4`,
`ed3a0f1`, `6e441aa`, `f27ee6f`, `e4916ef` and `118f2ef` from `keel-doc2`. It
shares `scripts/jobs/review_docs.py` with no other slice, and `CHANGELOG.md` with
S3. Row 47, KEEL-VOCAB-1 (a reject list over prose), overlaps S4's phrase list
and stays queued: S4 reads the existing `change_comments.phrases` and adds no key.

