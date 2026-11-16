---
title: CMP-16 — document checks read tables through one GFM grammar
kind: design
layer: n/a
status: draft
owner: TBD
tags: [plan, template, downstream, freshness, taxonomy, effects, credentials, audit, convergence]
summary: The convergence record, slices and decisions for CMP-16.
id: docs-internals-campaigns-cmp-16
created: 2026-10-06
updated: 2026-11-16
visibility: internal
canonical: true
---

## CMP-16 — document checks read tables through one GFM grammar

`562c5c5` (CMP-10.S4) already splits `scripts/jobs/review_docs.py` `table_cells` at unescaped pipes. CMP-16 moves that rule into `scripts/markdown_tables.py` for every reader.
keel serves engineers who start from the Copier template and keep it healthy with `make verify`; every document check reads a Markdown table through one GFM table grammar, so an escaped pipe, a borderless row or an indented table is read as a GFM renderer reads it, or a user gets a false or a missed finding.
The cap is three passes, one per slice, with three review fix rounds each. Stop at CMP-16.S3 green or the cap.

| Slice | Gap | Status |
|-------|-----|--------|
| CMP-16.S1 | `check_S`, `check_R` and `_anchors` read tables through `iter_tables`. `check_R` emits one finding naming every empty column in a row, whether written or padded. `check_R` judges that row no further. | planned |
| CMP-16.S2 | `thought_openers`, `roster_rows` and `parse_plan` use shared table rows and cell spans. | planned |
| CMP-16.S3 | Document gates and their mutation selectors use the shared grammar. Name comparisons decode escaped pipes in cell source. | planned |

`tests/unit/scripts/test_markdown_tables.py` pins the helper grammar. `table_cells` splits at pipes preceded by an even number of backslashes, even inside code spans. `table_cells` trims cells but preserves markup, escapes and non-border empties. Name comparisons first replace each escaped `\|` with `|`, as GFM does. Helper tests pin decoding separately from source cells.
`iter_tables` requires equal header and delimiter widths. Each delimiter cell matches `:?-+:?`. `iter_tables` reads no table whose delimiter row matches `_SETEXT_UNDERLINE`: under a paragraph line that row is a setext underline, as GFM reads it. `iter_tables` accepts optional borders and zero to three leading spaces. Its body ends at a blank line, heading, thematic break, list marker, quote, fence, indented code or HTML block. It pads short rows with empty cells. It discards cells beyond delimiter width. It returns row indexes and cell spans within fence and section scope.
A `.jinja` reader removes statement, expression and comment tags before reading tables. Tag removal reuses the newline-preserving pattern of `tests/integration/test_doc_drift.py:400` `_strip_jinja`. Helper tests pin normalized line numbers and spans.

CMP-16.S1 owns the helper and its tests. It owns `_pipe_table`, `_roster_table`, `_roster_findings`, `_catalogue_parity_findings` and `_anchors` in `scripts/check_structure.py`. It owns the three check test modules below.
S1 owns the helper roster rows in `scripts/README.md` and `scripts/README.md.jinja`. It owns grammar and required-cell prose in `docs/guides/doc-style.md` and `docs/guides/deterministic-checks.md`. It owns the plan, queue row, CMP-7.S1 escaped-pipe prose and defence row in `docs/internals/downstream-feedback.md`, at CMP-11's campaign location if moved. S1 corrects the split comment in `scripts/exit_code_table.py:100`. `tests/unit/scripts/test_exit_code_table.py` preserves `_CELL_BREAKERS`' refusal of pipes and line breaks in enum text.

Helper tests pin escaped headers, optional borders, all accepted indents, invalid delimiters, unequal header widths, body termination and body width normalization. Base `_pipe_table` uses `scripts/check_structure.py:3850–3861`. Its `Name` followed by `---` regression yields an h2 and no table.
`tests/unit/scripts/test_check_s.py` pins three roster cells for `routing \| sibling`. The base split at 3861 returns four. Its `_find` gives Purpose `a \| b` and Not for `—` one empty-Not-for error. The base check at 4183 passes the row. A borderless `Name | Purpose | Not for` header gets one "must be 'Member'" error. Base 3850 skips that header, so 4135–4139 report "no table follows it". `_roster_findings` takes iterator headers to avoid the IndexError at 4141–4150 after widening `_pipe_table`. It keeps its cases for a matching roster, an empty Not for cell and a duplicate member green.
`tests/unit/scripts/test_check_r.py` pins a first cell `A \| B` without shifting the Script cell. The base misreads Script at 3951. A written empty Interpreter yields one finding naming Interpreter. Base 3942 accepts it. A row with several empty columns gets one finding naming each column and no further judgment. Its `test_a_row_with_too_few_cells_is_an_error_not_a_skip` at 219–225 stays at one finding naming all padded columns.
`tests/unit/scripts/test_check_q.py` pins no anchor for a borderless table body followed by `---`. The base `_anchors` at 3629 invents one. It keeps `test_a_setext_heading_is_an_anchor` and `test_a_frontmatter_closer_is_not_a_setext_heading` green. Helper tests read list-item tables at `docs/adr/keel/K-0011-make-target-effect-labels.md:55` and `docs/internals/keel-hardening-plan.md:793`.

`check_E` gates helper exports in `__all__`. `tests/integration/test_import_layers_gate.py` gates bare imports against `config/project.json` `import_layers`. `tests/integration/test_gate_scope.py:797` `_local_imports` gates helper hook compatibility. `tests/integration/test_copier_job_conflict_refusal.py` pins that the file-free helper adds no read closure to `scripts/jobs/conflict_guard.py`. S1 runs its named unit and integration tests, `tests/integration/test_reference_drift.py`, `tests/integration/test_copier_generation.py` and `tests/integration/test_copier_shipping.py` before its `make verify` gate.

CMP-16.S2 starts from S1's commit. It owns `scripts/jobs/review_docs.py` table readers and `tests/unit/scripts/test_review_docs.py`. It owns `_cells`, `_slice_tables` and `parse_plan` in `scripts/check_structure.py`, plus `tests/unit/scripts/test_check_z.py`.
`tests/unit/scripts/test_review_docs.py` pins `review_docs.table_cells` to the shared callable. `thought_openers` splits raw cells before replacing inline code. The base order at `scripts/jobs/review_docs.py:468` hides pipe boundaries. `thought_openers` takes cells from `iter_tables` rows, so a borderless row's second cell opens its own thought, where the base reads the row as one prose line at 472. A `Removed | x` body-row regression pins separate cell thoughts. `roster_rows` takes iterator rows instead of the border predicate at 628.
Its Jinja-twin test feeds `scripts/jobs/README.md.jinja` through `shipped_markdown` and `thought_openers` and pins the cells of the `check_corpus.py` (43) and `link_corpus.py` (45) rows. The base reads each as one prose line at 472. The `review_docs.py` row (46) is the control. It tests tag-prefixed rows in `docs/guides/README.md.jinja`.
`tests/unit/scripts/test_check_z.py` pins `parse_plan` masking source spans of declaring first cells before masking prose. A borderless `CMP-1.S1 | mentions CMP-9.S9 | planned` row declares only CMP-1.S1. The base `_slice_tables` at `scripts/check_structure.py:7503` misses it. Selection alone leaves `parse_plan` at 7564 blanking Gap. `_line_scan_slices` keeps its independent regex, widened to ``^ {0,3}\|?\s*([^|`]*?)\s*\|``. `test_this_tree_is_z_clean_and_declares_what_a_line_scan_finds` compares the two readers. The module preserves escaped-pipe parity cases, fenced examples and campaign heading scope.
S2 reports every difference between the base and S2 in the tree's `run_checks` findings, `roster_rows` results and `thought_openers` results. S2 runs its owned unit tests, `tests/integration/test_gate_scope.py` and `tests/integration/test_copier_job_conflict_refusal.py` before its `make verify` gate.

CMP-16.S3 starts from S2's commit and rebases on landed CMP-11.S1.

| Owned file | Owned changes |
|---|---|
| `tests/integration/test_doc_drift.py` | It owns `shipped_docs`, `citable_docs`, `_without_tables`, `waiver_rows`, `_backticked`, `_blank_first_audience`, `_table_line_numbers` and waiver, exit, upgrade and task mutations. |
| `tests/integration/test_reference_drift.py` | It owns `_row_line` and cell-name decoding through `_first_span`. |
| `tests/integration/test_config_default_lines_docs.py` | It owns `_key_cell` and the settings-row filter. |
| `tests/integration/test_gate_evidence_record.py` | It owns `_documents`, `_text_units`, `_table_rows` and the script-roster selector at 577. |
| `tests/integration/test_canary_wiring.py` | It owns the canary-step regex at 406. |
| `tests/integration/test_copier_generation.py` | It owns the slice-row read at 501–503 after CMP-11.S1, settings deletion at 3392, feature deletion at 3406 and allowlist selection at 3624. |
| `tests/integration/test_copier_shipping.py` | It owns `_replace_row` at 322. |
| `tests/integration/test_tool_card_drift.py` | It owns `_a_card_with_a_default` at 152. |
| `tests/unit/scripts/test_corpus_owner.py` | It owns the script-roster selector at 607. |
| `tests/unit/backend/test_showcase.py` | It owns `_pillar_findings`' key regex at 215. |

S3 tests source-preserving cells and decoded names. `tests/integration/test_config_default_lines_docs.py:93–94` `_key_cell` reads source `` `config.a\|b` `` as `config.a|b`. `tests/integration/test_reference_drift.py:1458` selects that row through `_first_span` using key `config.a|b`. `tests/integration/test_doc_drift.py:835` `waiver_rows` reads source `` `waiver\|name` `` through `_backticked` as `waiver|name`. Each base reader truncates the escaped key.
`tests/integration/test_gate_evidence_record.py` pins escaped-pipe two-column rows that `_table_rows` splits or drops at 800–801. Its `_text_units` regression keeps borderless rows separate where 362 and 368 merge them. Every selector tests optional borders and zero to three spaces. Doc-drift mutations replace indexed borders at 1650, 1707 and 1793–1800 with iterator spans. Doc-drift tests cover `shipped_docs` twins. Evidence tests cover `_documents` and roster twins. Corpus-owner tests cover roster twins. Doc-drift keeps the clean and one-finding assertions at 1602, 1619, 1714 and 1717. Tool-card tests keep those assertions at 162 and 174. S3 runs every owned test module and the Copier update scenario in `tests/integration/test_update_without_app.py` before its `make verify` gate.

Each slice uses `rg` on `scripts/`, `tests/`, `agents/` and `src/` for splits, pipe regexes, border predicates and mutations. It excludes non-Markdown splits and fixture cell removal that tests malformed rows. `src/frontend/astro/src/lib/md.ts` retains its marked GFM renderer. `rg` found no Python table reader in `agents/` or `src/`. Each slice records KEEL-TABLE-PIPE-1 in the feature catalogue and changelog. `tests/integration/test_work_trailers.py` gates its `Slice:` trailer.

`make doc-review` retains judgment of Not for truth. `iter_tables` reads a table indented zero to three spaces in any container, and leaves unread a table inside a block quote or indented four or more spaces; CMP-12's container stack is where those join. No test compares `iter_tables` with cmark-gfm output, so parity with that renderer is unverified.

Each base verdict is read from the code at `0796377`; none was run. CMP-16.S1 starts after `keel-cmp10`, `keel-cmp12` and `keel-cmp13` land. CMP-10 and CMP-12.S1 own both Markdown scanners. CMP-12.S1 also owns doc-drift fence tests, review-docs tests and doc-style prose. CMP-13.S1 and CMP-13.S2 own deterministic-checks and feature rows. The coordinator merges shared entries. CMP-11 has a committed plan and unbuilt slices. CMP-11.S1 owns the slice-row read in `tests/integration/test_copier_generation.py`. CMP-11.S2 owns the feature rows in `docs/reference/features.md`. CMP-11.S3 owns `CHANGELOG.md`. CMP-16.S3 starts after CMP-11.S1 lands. CMP-16.S1 and S2 write their changelog entry and feature row the way the tree each starts from records one. They may land before or after CMP-11. Each rebase rechecks citations.
This plan adds row 76, KEEL-TABLE-PIPE-1, to `Queued after Campaign 6`.

