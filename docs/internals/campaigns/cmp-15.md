---
title: CMP-15 — config conversion failures end in a named refusal or one finding
kind: design
layer: n/a
status: draft
owner: TBD
tags: [plan, template, downstream, freshness, taxonomy, effects, credentials, audit, convergence]
summary: The convergence record, slices and decisions for CMP-15.
id: docs-internals-campaigns-cmp-15
created: 2026-10-06
updated: 2026-11-16
visibility: internal
canonical: true
---

## CMP-15 — config conversion failures end in a named refusal or one finding

KEEL-CFGCRASH-1 came out of KEEL-VIS-2's round-1 and round-2 reviews and KEEL-LEAK-1's first review.
keel serves engineers who start from the Copier template and keep it healthy with `make verify`; a malformed or hostile value in config/project.json or config/practices.json must end a check as a named CONFIG refusal or one finding, never as a traceback, a hang or a huge allocation.
Each slice has one pass and at most three review fix rounds.
Stop at four green `make verify` slices or a cap.

| Slice | Gap | Status |
|-------|-----|--------|
| CMP-15.S1 | The loader refuses recursion. Rendering preserves redaction and deduplicates by identity. | implemented |
| CMP-15.S2 | Section faults exit CONFIG for practices and FAILURE for source headers. A loader-refused config/practices.json exits CONFIG, or USAGE for a conflict hunk. | implemented — delivered by 2a36e455; review LAND, its two NEXT findings are row 176 |
| CMP-15.S3 | Floor faults exit CONFIG. ADR widths are bounded before allocation. Policy faults yield one key-naming FAILURE finding. | implemented — delivered by bc56aafc; review LAND, its two NEXT findings are row 177 |
| CMP-15.S4 | Child-env pattern faults and launcher load faults exit CONFIG. | implemented |

Unit tests below live in `tests/unit/scripts/`.
CMP-15.S1 owns `scripts/config_loader.py` and its `summary:`, `test_config_loader.py`, `test_config_get.py`, `tests/integration/test_config_loader_read.py`, `tests/integration/test_conflict_entry_points.py`, loader limits in `docs/guides/limits-and-troubleshooting.md`, and this plan and its queue row in `docs/internals/downstream-feedback.md`.
`read` catches decoder RecursionError as ConfigUnreadable naming the file.
`resolve` catches RecursionError only copying config, raising WrongValue naming source and key.
A default's copy stays unguarded because the default is code.
When canonical JSON or `repr` raises RecursionError, `shown` and `quoted` return `<hidden: nested too deep to show>`, held in `_HIDDEN_DEPTH`.
`quoted` wraps that text in single quotes for a string.
A value holding an `@` still returns `_HIDDEN_AT`, because iterative `_holds_at` runs first.
`_refused_members` uses canonical text or, on rendering failure, `id` for first-seen and repeated members, never deep equality or fallback text.
`read` and `resolve` build their refusal lines from the file name and key, never from the RecursionError's text.

Decoder, rendering and configured-copy regressions raise on the base.
Fixtures find the shallowest nesting `json.dumps` refuses in-process.
Member and copy cases call `resolve` on iteratively built values.
Rendering tests assert both fallbacks, string quoting and `@` precedence.
Identity tests cover repeated and distinct deep members.
CLI cases skip with a reason if no nesting decodes but fails resolution.
Controls retain shallow copies, deduplication, redaction, defaults and refusals.
A deep default still raises at its copy.
`scripts/config_get.py` `main` acceptance for each file asserts CONFIG naming it, no traceback or stdout.
The practices case uses a test-only `KEYS` row with `file=config/practices.json`.
`is_conflict` keeps USAGE.

CMP-15.S2 owns the section, reachability, check_V and provenance code below in `scripts/check_structure.py`, `test_check_t.py`, `test_check_u.py`, `test_check_v.py`, `tests/integration/test_check_structure_manifest_refusal.py` and its `summary:`, and exits and checks T, U and V in `docs/guides/deterministic-checks.md`.
`_ASCII_NUMBER` holds `[0-9]{1,4}` for full matching by the section and floor readers.
Its comment explains that four digits bound integer conversion and `int` accepts underscores and non-ASCII digits.
A `§` is a section number only when it matches that grammar.
`_mechanism_reason` reports any other section text as a section fault.
`_mechanism_findings` records file, practice index and `enforced_by` index as provenance.
A practice naming a missing check, file, target or numeric section stays a FAILURE finding.
`main` chooses CONFIG for a practices section fault or loader-refused practices file, preserving USAGE for a conflict.
`_read_json_config` records the refused file and conflict provenance.
`run_checks` resets provenance per call without changing finding tuples.
`_mechanism_reason` and `_policy_reachability_findings` give non-strings grammar findings before text conversion.
`_policy_reachability_findings` skips a practice whose `enforced_by` is not a list, as `_mechanism_findings` does.
On the base, `str` converts four raw practices members: `_mechanism_reason`'s `ref`, and `_policy_reachability_findings`' `ref` prefix, `ref` path and practice `id`.

Regressions append `@` to all eight practice section positions; the base raises at `int(section)`.
A practice whose `enforced_by` is `doc:<an existing ADR> §x` reaches the same `int(section)`.
A section sign followed by `0_3` or by `٣` resolves cleanly as section 3 on the base; S2 makes each one finding.
Python and shell `rerun_proof: doc:<existing doc> §x` each raise on the base and become one check_V FAILURE finding.
Deep refs raise at the base's first `str`; deep `id` raises at collection.
Regressions isolate all four sites.
`"enforced_by": 1` raises TypeError on the base; S2 leaves check_T's one list finding.
A practices file with a key written twice exits FAILURE on the base and CONFIG with S2.
A practices file holding a conflict hunk exits FAILURE on the base and USAGE with S2.
Controls retain valid sections, absent practices and malformed-proof or convention FAILURE.
Acceptance calls structural `main` for both files: named input, specified exit, no traceback.
`@` cases assert no payload reaches either stream.
Repeated `run_checks` proves provenance reset.

CMP-15.S3 owns the floor, ADR and work-policy code below in `scripts/check_structure.py`, `test_check_structure_parse.py`, `test_check_y.py`, `test_check_z.py`, the `layers.backend.python`, `adr.number_digits` and `work_naming.backlog_id` rows in `docs/reference/settings.md`, and the floor and checks Y and Z in `docs/guides/deterministic-checks.md`.
`_declared_python_floor` converts major and minor only when each fully matches `_ASCII_NUMBER`.
A part passing `str.isdigit` but failing that grammar is a CONFIG floor fault.
check_Y reads the file-name limit of the nearest existing ancestor of each ADR directory.
Where the platform reports none, it uses 255 bytes, a named module constant whose comment gives the reason: the common NAME_MAX.
An unknown limit never refuses a width.
`adr_policy` stays pure: check_Y measures and passes the limits.
S3 updates `test_check_y.py` `_tree_inventory_holds`.
The width bound subtracts encoded prefix and minimum suffix bytes.
`adr_policy` bounds `adr.number_digits` before `_adr_grammars` or shape allocation.
The bound adds no config key.
ADR and work-policy refusals, including OverflowError, RecursionError and oversized widths, stay one key-naming FAILURE finding without CONFIG provenance.
Config-pattern guards catch `re.error`, RecursionError and OverflowError without pattern or exception text.

Superscript and overlong floor digits raise at the base's `int`.
`>=٣.١١` gives (3, 11) on the base and a floor fault with S3.
Overlong-digit tests skip when the runtime has no integer-string conversion limit or has it disabled.
An ADR test raises a `re.compile` sentinel before the base allocates for `number_digits: 2000000000`.
With S3, `adr_policy` returns one width finding, and the sentinel never fires.
Unrepresentable widths raise on the base.
Recursive `work_naming.backlog_id` and `x{4294967296}` escape the base's guard; each becomes one FAILURE finding.
Controls retain valid inputs, syntax-pattern FAILURE and missing-file findings.
`number_digits: 4` stays clean with absent `template_dir` and empty `template_adrs`.
Limit tests cover absent directories, unavailable, unknown or differing limits, prefix bytes and boundaries.
Structural `main` acceptance asserts floor CONFIG and one FAILURE finding per policy fault without traceback or huge allocation.

CMP-15.S4 owns `scripts/child_env.py` `_value_patterns`, `scripts/launch.py` `load_launcher_config`, `test_child_env.py`, `test_launch.py`, `test_child_exec.py`, `tests/integration/test_launcher.py`, and the `child_env.credential_value_patterns` and `launcher.spare.max_load_per_cpu` rows in `docs/reference/settings.md`.
`_value_patterns` catches those three exceptions and names key and label without the pattern.
`load_launcher_config` checks numeric range before `math.isfinite`.
Recursive child-env patterns, `x{4294967296}` and oversized launcher integers raise on the base.
Controls retain syntax refusals, valid patterns, ordinary loads, boolean refusals, non-finite floats and range refusals.
Launcher and `scripts/child_exec.py` `main` acceptance asserts CONFIG without traceback or pattern text.
Child-exec tests assert no body runs.
S4 starts from S1 independently of S2 and S3.

Each slice owns one `CHANGELOG.md` row naming KEEL-CFGCRASH-1.
Each owns `docs/reference/features.md` rows: S1 `scripts/config_loader.py`; S2 `scripts/check_structure.py`, check_T, check_U and check_V; S3 check_Y, check_Z and check_D (floor deferral); S4 `scripts/child_env.py`, `scripts/child_exec.py` and `scripts/launch.py`.
This plan adds row 75, KEEL-CFGCRASH-2, to `Queued after Campaign 6`: the direct decoders and configured-text readers CMP-15 does not reach.

Will not do in CMP-15: judge application schemas beyond JSON and type checks.
`_mechanism_reason` cannot judge enforcement.
KEEL-CFGCRASH-2 owns those boundaries and regex execution time.
Corpus decoders in `scripts/query_corpus.py`, `scripts/jobs/link_corpus.py`, `scripts/jobs/check_corpus.py`, `scripts/jobs/export_showcase_static.py`, `scripts/accountability_report.py`, `agents/index_enforcer/_brain.py` and `agents/doc_reviewer/_brain.py` read generated views.
`runtimes/_checkpoint.py` decodes runtime state.
Tool-report decoders in `scripts/scan_secrets.py`, `scripts/audit_dependencies.py`, `agents/doc_reviewer/_brain.py` and `agents/practice_refactor/_brain.py` read tool output.
`evals/_dataset.py` decodes test cases.
`evals/_config.py` and `scripts/trace_requirements.py` decode schemas.
`scripts/audit_project.py`, `scripts/jobs/finish_update.py` and `scripts/jobs/keep_edited_retired.py` decode Copier history in YAML.

Base verdicts are read from `0796377f10b6`.
CMP-15's plan sits on CMP-14's declaration because check_Z refuses campaign gaps.
CMP-15.S1 starts from main after keel-cmp10 and CMP-13's build land.
keel-cmp10 owns loader, check_structure and review_docs, including its pre-landing fix.
CMP-13 owns loader KEYS and test-quality edits.
S2 starts from S1's commit after keel-cmp12's fence code lands.
S3 starts from S2's commit and uses its provenance for floor faults.
After CMP-11 lands, slices restate plan, reference and changelog ownership as fragments.
Each slice rechecks EVIDENCE on its base before TDD.
Green `make verify` and a `Slice:` trailer gate each delivering commit.

