---
title: CMP-17 — an unreadable tool report fails the agent run
kind: design
layer: n/a
status: draft
owner: TBD
tags: [plan, template, downstream, freshness, taxonomy, effects, credentials, audit, convergence]
summary: The convergence record, slices and decisions for CMP-17.
id: docs-internals-campaigns-cmp-17
created: 2026-10-06
updated: 2026-11-16
visibility: internal
canonical: true
---

## CMP-17 — an unreadable tool report fails the agent run

KEEL-ERR-2: three agents read a tool report that does not parse as an empty one. The cap is one pass per slice and three review fix rounds each; stop at CMP-17.S3 green or the cap. Slices start from the preceding commit. Engineers using the Copier template and `make verify` get ToolReportUnreadable before an unreadable report selects a verdict.

| Slice | Gap | Status |
|-------|-----|--------|
| CMP-17.S1 | Review and style-rule reports share one refusal; first red: `tests/integration/test_doc_reviewer.py::test_tool_report_error_export_is_shared`. | implemented |
| CMP-17.S2 | Index and practice verdicts require readable reports; first red: `tests/integration/test_index_enforcer_durability.py::test_unreadable_owner_report_fails`. | implemented — delivered by 81d0be9d and 16cc10fb; review LAND |
| CMP-17.S3 | Wiki retrieval refuses unreadable reports before synthesis; first red: `tests/unit/agents/test_wiki_navigator_step.py::test_unreadable_retrieval_fails_before_model`. | implemented — delivered by 30b04ef4; the decode was already shared on the base, so the slice adds the refusal tests and docs; review LAND |

`scripts/tool_reports.py` exports `read_report(tool, rc, out, err, root, *, container)` and `ToolReportUnreadable` in `__all__`. Blank, non-JSON, too-deep and wrong-shape output raises ToolReportUnreadable; catch ValueError and RecursionError. Owner reports and queries require `container=list` with object members; review, baseline and apply require dicts. Preserve KEEL-ERR-1's RuntimeError and `parts=(what, on, next_step)` from `ab2c04a`, naming tool, status, root and stderr. `tool` is the repo-relative path run.

`scripts/tool_reports.py` imports nothing of the project: it raises and never ends the process. It registers under `tool_reports` and `scripts.tool_reports`, following `scripts/config_loader.py:2364-2365` and `_bind_to_package:2387,2390`. The mirror asserts one error in both import orders. All four agents' `_brain.py` modules use `from scripts import tool_reports`; `scripts/refactor_practice.py` uses bare `import tool_reports` after module lines 23-26. Doc-reviewer re-exports the error to its CLI and hook. CMP-17 adds no config key.

CMP-17.S1 owns `scripts/tool_reports.py`, `tests/unit/scripts/test_tool_reports.py`, `agents/doc_reviewer/_brain.py`, `agents/doc_reviewer/__init__.py`, `tests/integration/test_doc_reviewer.py`, `agents/doc_reviewer/README.md`, `scripts/doc_review.py`, `scripts/hooks/on_stop_doc_review.py`, `scripts/AGENT.md`, `config/project.json`, `config/project.json.jinja`, `CONVENTIONS.md`, `scripts/README.md`, `scripts/README.md.jinja`, `docs/reference/features.md`, `docs/reference/settings.md`, `CHANGELOG.md` and `docs/internals/downstream-feedback.md`.

Extract the reader, delete doc-reviewer's `_report` and preserve its re-export together. S1's first red is `test_tool_report_error_export_is_shared`, which imports `scripts.tool_reports` inside its body, so the module still collects on the base; `test_nested_review_report_is_unreadable` follows it. Keep index's `_report(state)`. Accountability stays in S2 because S1 exceeds about 15 files.

S1 extends both manifests' `import_layers.order[0]` and `_comment`, the §3 layer bullet's bottom-layer list (CONVENTIONS.md:369-370) and settings' layer default. `test_import_layers_gate.py` checks layering; `test_gate_scope.py` checks the oldest hook interpreter. Add beside scripts/AGENT.md's bottom-layer modules: "`tool_reports.py` is never run: it is the one reader of a tool report an agent runs. A second `json.loads` of a tool's stdout in `agents/` is a defect. It imports nothing of the project and stays stdlib-only and safe on the oldest hook interpreter, because it sits in the bottom import layer."

S1 reads style rules through `read_report(..., container=list)`: deep reports, non-lists and lists with non-object members raise ToolReportUnreadable. Nonzero status and execute `[]` keep RulesRefused. Correct the non-JSON-means-RulesRefused claims in the brain's summary and `_retrieve` docstring, both entrypoint summaries and `agents/doc_reviewer/README.md`. No other converted reader contains that claim.

S1 works test-first:

- Nested reviews raise base RecursionError (`_report:106-107` catches only ValueError), then ToolReportUnreadable before retrieval. Build the shallowest rejected nesting iteratively without changing the process's recursion limit.
- Non-JSON, blank and whitespace style-rule reports raise base RulesRefused (`_retrieve:371-373`); deep output raises RecursionError there. `{"a":1}`, `"x"` and `[1]` raise AttributeError (`_retrieve:389`). All become ToolReportUnreadable before baseline; also reject `{}` before `_retrieve:380`.
- Keep wrong-container refusals, including `[1]` (`_report:112`). The mirror covers diagnostics and valid reports.
- Assert `scripts/jobs/review_docs.py` in the message and next step (`_review:310`); base `_report:116` suggests nonexistent `scripts/review_docs.py`.
- Keep nonzero-query and execute-`[]` RulesRefused (`_retrieve:364,381`), dry `[]` (`_retrieve:380,389`), red-baseline stopping (`_wants_edits:470`) and skipped apply (`_apply:452`), including nonzero negative gate and apply reports. Nonzero review still raises ToolReportUnreadable (`_review:314`).
- Non-JSON rules change CLI USAGE (`scripts/doc_review.py` `main:127`) and executing-hook USAGE (`main:136`) to FAILURE (`main:129-132`, `main:139-143`). The dry hook keeps stderr and SUCCESS (`main:148`, `_said:36-37`). The README states these exits.

Acceptance runs these cases and `make verify`, including `check_S` and `test_reference_drift.py` for rosters and the shared-script row.

CMP-17.S2 owns `agents/index_enforcer/_brain.py`, `tests/unit/agents/test_index_enforcer_step.py`, `tests/integration/test_index_enforcer_durability.py`, `agents/practice_refactor/_brain.py`, `tests/unit/agents/test_practice_refactor_step.py`, `tests/integration/test_practice_refactor.py`, `scripts/refactor_practice.py`, `scripts/accountability_report.py`, `tests/unit/scripts/test_corpus_owner.py`, `agents/index_enforcer/README.md`, `agents/practice_refactor/README.md`, `agents/tools/accountability_report.tool.md`, `scripts/README.md`, `scripts/README.md.jinja`, `docs/reference/features.md`, `CHANGELOG.md` and `docs/internals/downstream-feedback.md`.

S2 converts index `_report` and practice `_walk`, `_baseline` and `_apply`, correcting their docs. Index rejects nonzero owner status first. Accountability's absent-corpus `--json` emits stdout `[]` and a stderr notice; text keeps its notice and SUCCESS. Extend existing suites; only the reader gets a mirror. The CLI reports the shared error as FAILURE with its parts; WalkRefused keeps USAGE. S2 completes only row 64's first KEEL-VIS-10 leftover.

S2 works test-first:

- Index reads non-JSON as no gaps (`_report:156-157`), whitespace and `{}` as no gaps (`_report:154`), and nonzero `[]` as no gaps because `_report:149` discards status. `[1]` raises TypeError (`_report:154`). A report nested past the parser's limit raises RecursionError (`_report:154`, whose handler at 156 catches only ValueError). All become ToolReportUnreadable.
- Index `_gate` discards `scripts/check_structure.py`'s status and counts only `ERROR ` lines (`_gate:120-126`), so a crashed gate with no `ERROR ` line reads as a clean tree (`_clean:205`) and an execute run builds and fills. A nonzero status with no `ERROR ` line becomes ToolReportUnreadable; the control keeps a status-1 run with `ERROR ` lines read as not clean.
- Accountability's absent-corpus JSON mode prints a stdout notice (`main:118`); require `[]`, stderr notice and SUCCESS.
- Practice reads non-JSON as no hits (`_walk:268-269`), blank or whitespace as no hits (`_walk:267`), and `{}` as no hits (`_served:190`). `[1]` raises AttributeError through `_served:190` at `config_loader.is_served:2245`. Each becomes ToolReportUnreadable before baseline.
- Non-JSON or whitespace baselines become false (`_baseline:295-298`) and applies become skipped (`_apply:358-364`). `[1]` raises AttributeError (`_baseline:298`, `_apply:361`). Deep reports raise RecursionError at each decode. All become ToolReportUnreadable.
- The practice CLI lets the shared error escape (`main:133`); require FAILURE with its parts.

Public tests check error parts in both modes with approved budgets. Recordings forbid fill or commit after owner failure, baseline after walk failure, edits after baseline failure, and another chunk after broken apply. Controls keep index lists mapped to ids (`_report:154`), practice `[]` empty (`_walk:275`), false `ok` stopped (`_wants_refactor:387`), and false or true `applied` skipped or recorded (`_apply:364,362`), despite nonzero gate or apply status. Nonzero queries keep WalkRefused (`_walk:259-260`).

`tests/integration/test_agent_runtime_equivalence.py:26-32` keeps both engines equal with or without a corpus. Give `scripts/accountability_report.py` a nonexistent absolute `--corpus` path (`main:115-117`). Its real output feeds a corpus-free scratch index dry run; keep `owner_gaps == ()` without writes (base `_load_corpus:69-70`, `_report:156-157`). Acceptance runs these cases and `make verify`.

CMP-17.S3 owns `agents/wiki_navigator/_brain.py`, `tests/unit/agents/test_wiki_navigator_step.py`, `tests/integration/test_mcp_servers.py`, `agents/wiki_navigator/README.md`, `docs/reference/features.md`, `CHANGELOG.md` and `docs/internals/downstream-feedback.md`.

Public `answer` tests in both modes require ToolReportUnreadable before backend construction. Base non-JSON becomes no hits (`_retrieve:118-119`); whitespace and `{}` reach empty synthesis (`_retrieve:117`, `_visible:73`, `_plan:174`). `[1]` raises AttributeError through `_visible:73` at `config_loader.is_served:2245`; deep output raises RecursionError (`_retrieve:117`). With approved budgets, MCP reports the error, tool and root with `isError=true` and no model call (`mcp/protocol.py` `ToolServer.call_tool:92`, `_error_result:106`). Controls keep empty `[]`, served citations (`_retrieve:121`) and nonzero-query RuntimeError (`_retrieve:115`). S3 updates its docs, runs these cases and `make verify`.

The whole-tree `noqa: DROP001` search finds five KEEL-ERR-2 excuses: index `_report:156`, practice `_walk:268`, `_baseline:296`, `_apply:359`, and wiki `_retrieve:118`. S2 removes four; S3 removes the fifth and repeats the search. Gate-evidence's file-report excuse stays: `junit_counts:196` returns None, failed by `overall:320,331`. Other excuses read files, configuration, probes, replies or fixtures; their fallbacks stay.

Will not do in CMP-17: validate individual fields or their truth. A list whose nodes state no level reads as no hits; KEEL-VIS-9 owns the shape check before the model sees it. Index build and link statuses and the root mismatch stay with KEEL-VIS-3; a retrieval of `[]` that still reaches the model stays with KEEL-VIS-9. Wiki's nonzero retrieval keeps its plain RuntimeError (`_retrieve:115`), which every caller already reports: the MCP server catches it (`mcp/protocol.py:92`) and `answer` documents it; naming it is left to KEEL-VIS-9. `scripts/scan_secrets.py` `_findings:224-225` and `scripts/audit_dependencies.py` `_report_of:915-916` do not read an agent's tool report. Both remain KEEL-CFGCRASH-2 sites: ValueError is refused (`_verdict:245`, `_report_of:920`), but deep output raises RecursionError.

keel-cmp12 and keel-cmp13 each stack on keel-cmp10. keel-cmp12's `56456e2` changes `scripts/check_structure.py`, `scripts/jobs/review_docs.py`, `CONVENTIONS.md`, `CHANGELOG.md` and `docs/internals/downstream-feedback.md`, and keel-cmp13's slices change `scripts/config_loader.py` `KEYS` and `config/project.json` `test_quality`. keel-cmp10 changes `agents/doc_reviewer/_brain.py`, `tests/integration/test_doc_reviewer.py`, `scripts/refactor_practice.py`, both manifests, `CONVENTIONS.md`, `docs/reference/features.md` and `docs/reference/settings.md`, all of which a CMP-17 slice also changes. So CMP-17.S1 starts from main after all three land and rebases on them. Every line cited here is at `0796377`, the keel-cmp13 tip that carries keel-cmp10's code. The required diff confirms each overlap; S1 re-checks every cited line at its start, because keel-cmp10's fix commit, `56456e2` and keel-cmp13's `KEYS` rows land first. The coordinator assigns queue positions. If keel-cmp11 lands first, changelog and feature rows become entry files and this section moves to `docs/design/campaigns/`. S3 completes row 73 after green; `tests/integration/test_work_trailers.py` checks trailers.

