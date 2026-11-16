---
title: CMP-12 — a fence inside a list or a quote is read as a renderer reads it
kind: design
layer: n/a
status: draft
owner: TBD
tags: [plan, template, downstream, freshness, taxonomy, effects, credentials, audit, convergence]
summary: The convergence record, slices and decisions for CMP-12.
id: docs-internals-campaigns-cmp-12
created: 2026-10-06
updated: 2026-11-16
visibility: internal
canonical: true
---

## CMP-12 — a fence inside a list or a quote is read as a renderer reads it

KEEL-FENCE-CONTAINERS-1 came out of the CMP-10.S3 round-3 review and the review
after its cap. Every document check reads prose through one fence grammar,
`scripts/check_structure.py` `_fence_scan`, and `scripts/jobs/review_docs.py`
`unfenced_lines` is a copy of it that `tests/unit/scripts/test_review_docs.py`
pins equal. The grammar is a line scanner with no container model, so it
disagrees with a CommonMark renderer in three shapes. The opening pass probed
`keel-cmp10` at `1d8b041` in memory, one call per shape, and both copies gave
the same answer each time:

- a fence opened in a list item stays open after the item ends, so prose after
  the list is blanked and the fence is reported open at its line;
- HTML comments are blanked before fences are found, so a `<!--` inside a fence
  hides every line up to the next `-->`, and a fence it swallows the closer of
  stays open to the end of the document;
- a fence inside a blockquote (`> ` prefix), and a fence indented four or more
  spaces inside a list item, are not seen at all, so their code is read as
  prose and a link or a citation written in it is checked.

`tests/unit/scripts/test_check_structure_fences.py` pins the two container
shapes of the last item as stated gaps, and holds no comment case, and `docs/guides/doc-style.md` states the gap in one sentence. No shipped
document hits any of the three today, so the defect is latent: a user's next
document with a fenced example inside a list or a quote gets a false finding or
a missed one. The cap is one pass and one slice, with at most three review fix
rounds; the stop point is CMP-12.S1 green or the cap.

| Slice | Gap | Status |
|-------|-----|--------|
| CMP-12.S1 | The fence grammar keeps a stack of the containers a line sits in, as CommonMark's block phase does. A blockquote marker is up to three spaces, `>` and one optional space. A list item's content column is the marker's own column inside its container, plus the marker's width, plus its padding. The padding is one to four spaces. Five or more spaces after the marker count as a padding of one. An item whose first line is empty has a padding of one. A line stays in each open container whose prefix it carries. An unprefixed line continues an open paragraph only when it is paragraph text. A line that would start a fence, a heading, a thematic break, a list item, a quote or an HTML block ends the containers whose prefix it lacks, and is read again outside them. These are cmark-gfm's paragraph-interruption rules: an ordered marker that starts above 1, and a list marker with nothing after it, continue a paragraph when its containers are continued; a line lacking its container prefix starts a new list instead, a known difference from micromark's lazy-text reading. A fenced block is never continued lazily. A fence opens with up to three spaces past its container's content column. A fence closes on a closer of the same character, at least as long, with up to three spaces of its own past that column, whatever the opener's indent. A fence also closes when its container ends. An HTML block of CommonMark types 1 to 5 starts at a line whose text past its containers begins with its start marker after up to three spaces. Those starts are a `<script>`, `<pre>`, `<style>` or `<textarea>` tag, `<!--`, `<?`, `<!` and an ASCII letter, and `<![CDATA[`. Each runs to the line that holds its end marker, or to its container's end. A fence line inside such a block is HTML, not a fence. An inline comment that closes inside its line is still blanked, so a heading's anchor is read without it. A `<!--` that opens mid-paragraph and does not close within that paragraph is text, and hides no line after it. Both copies change together. The pin holds them equal. `_fence_scan` still returns the opener's 1-based line for a fence left open. A user's prose after a list or a quote is checked, and code inside one is not | implemented — on main, delivered by 83dcb1f9, 33e7438a; the done-condition is not re-audited |

CMP-12.S1 owns `_fence_scan`, its docstring and the module `summary:` sentence on
fences in `scripts/check_structure.py`, `unfenced_lines` and its comment in
`scripts/jobs/review_docs.py`, `tests/unit/scripts/test_check_structure_fences.py`
(its two stated-gap cases turn into renderer-true cases), the container cases
in `tests/integration/test_doc_drift.py`
`test_check_citations_follow_shared_fence_boundaries` (the quoted fence and the
list fence indented four spaces now hide their citation), the shared texts in
the pin `test_the_fence_grammar_is_check_structures`, the gap sentence in
`docs/guides/doc-style.md`, the test module's `summary:` and one `CHANGELOG.md`
row. It works test-first. Each regression case below fails on the lane's base
for the shape it names, as the plan's probes on `9a9703f` showed:

- a list item's fence that the item's end closes, and the prose after it;
- an item whose marker is indented three spaces, holding a fence indented six;
- a `1000.` line after an item, which starts a new list item whose content
  column is 6 under cmark-gfm's rules; a fence indented five spaces is lazy
  paragraph text and stays shown (`ordered-item-full-column`), while a fence
  indented six spaces is code inside the new item (`wide-ordered-after-item`);
- a quoted fence whose opener is indented three spaces and whose closer is not;
- an item with five spaces after its marker, an item whose first line is
  empty, and an item with a lazy line, each holding a fence indented five
  spaces;
- a quote inside a list item, and a list item inside a quote;
- an unprefixed line after a quoted fence, which ends the fence;
- a `<!--` inside a fence;
- a `<pre>` block, a `<?` block, a `<!DOCTYPE` block and a `<![CDATA[` block,
  each holding a fence line.

Four preservation cases already pass on the base and must still pass: a
comment block holding a fence line, a `<!--` in mid-paragraph that never
closes, an inline comment in a heading, which stays blanked from its
anchor, and a `<!` before a non-ASCII letter, which remains text and leaves
a following fence a fence. A lowercase declaration such as `<!doctype html`
starts an HTML block under CommonMark 0.31 and hides fence lines until its
closing `>`.

Its acceptance includes the tree's own output before and after, taken by
read-only probes, not by `make trace`, which writes a matrix. The probes are
the `check_structure.run_checks` findings, the `traceability.trace_tree` result
and counts, and the `review_docs.change_openers` list over the tree. Each is
the same after the slice, or the slice names each change and why.
`scripts/traceability.py` and `scripts/jobs/build_corpus.py` call the grammar
and get the fix without an edit; their tests run in the slice's gate.

Will not do in CMP-12: move the grammar into one shared module. The copy exists
because `scripts/jobs/conflict_guard.py` refuses a job over every file its
imports read, and importing `scripts/check_structure.py` would stop
`restamp_docs` and `declare_no_app` over a conflicted Makefile; a module that
reads no file would remove that reason, but the pin already fails a drift
between the copies on its shared texts, so the move buys no correctness there.
A full CommonMark parser is also out. The grammar models containers, fences
and HTML blocks of types 1 to 7. Types 1 to 5 end at a marker of their own;
types 6 and 7 end before a blank line. It does not model inline syntax beyond
an inline comment, or tables. KEEL-FENCE-HTML-1 closes the blank-line HTML gap:
a `<div>` or `<details>` line, or a whole-tag block, hides its fence-looking
lines until a blank line or container end. Type 6 may interrupt a paragraph;
type 7 may not. The doc-style guide states that contract.

CMP-12 builds on `keel-cmp11`, whose plan declares CMP-11, because the
campaign naming check refuses a CMP-12 with no CMP-11 before it. `keel-cmp11`
sits on `keel-cmp10`, which owns both copies of the grammar. CMP-12 lands after
CMP-10 and CMP-11's plan commits, and is rebased each time one of them moves.
It shares `CHANGELOG.md` and `docs/guides/doc-style.md` with CMP-10 and CMP-11,
whose rows the coordinator merges.

