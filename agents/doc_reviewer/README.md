---
title: Doc reviewer agent
kind: agent
layer: backend
status: template
owner: TBD
public_api: agents/doc_reviewer/__init__.py
tags: [agent, documentation, review, rosters, freshness]
summary: Reviews the documentation against docs/guides/doc-style.md — the deterministic findings first, then one judged edit per chunk, each gated on make check-docs and rolled back if red.
id: agents-doc-reviewer
created: 2026-09-02
updated: 2026-10-28
visibility: internal
canonical: true
---

# Doc reviewer

Reviews the documentation against `docs/guides/doc-style.md`: the deterministic
findings first, then one judged edit per chunk, each gated and rolled back if
red.

The **judgment half** of the documentation-quality system. The gate
(`check_structure.py` P–T) proves what a rule can prove — links resolve, rosters
match, tool specs carry their sections — and `scripts/jobs/review_docs.py`
reports what stays a report (stale stamps are gated separately; unresolved
mentions never are). A stale stamp is counted but never judged: a rule decides
it, so `make restamp-docs` clears it, and until then `make check-docs` is red and
the run stops at its baseline. What no rule can decide — is this `Not for` cell
*true*, is this backticked name a path or a noun — this agent judges, one chunk at a time, with the guide's own rules retrieved from
the corpus as its context. Every edit lands through `apply_refactor`, gated on
`make check-docs` (the structure gate plus strict freshness), and is **rolled
back** unless the tree stays green.

It is thin: policy + prompt only. The doers are `scripts/` tools (per the specs in
`agents/tools/`, declared in `tools.md`); control flow is a neutral `Plan` on a
`Runtime`; the model comes from `models/`. The entry point is
`review(...)`, returning a `DocReviewReport`. The second public symbol,
`propose(rules, chunk, backend=b)`, is the one model call per chunk: one bounded
edit spec, or `None` for a decline. The eval harness (`evals/_doers.py`) drives it on a recording backend, so a replayed case judges the real prompt and parser and calls no model. It **defaults to dry-run**:
`review()` gathers the findings, retrieves the rules, gates the read-only baseline
and reports the candidate chunks plus the prompt it *would* send, calling no model
and writing nothing; `review(execute=True)` proposes and applies the gated edits
in a durable per-chunk loop that resumes after a crash. An unavailable model is a
stated skip in its callers (`ModelUnavailable`, `models/`).

A finding is sent to a model only when `wiki/corpus.json` has a node for its
file and `config_loader.is_served` keeps every such node at the project's
`corpus.served_visibilities`, and `config_loader.is_served_now` keeps it at the
level the file states on disk now (`scripts/corpus_level.py` `stated_now`), so a
file reclassified after the corpus was built, or one whose level cannot be read
now, is not sent. Any other finding is **withheld**: the report keeps
it in `withheld` as (chunk id, why), its file's text is never read, and no prompt,
preview or apply carries it. The check fails closed: a corpus or config that
cannot be read withholds every finding, and a file with no corpus node is
withheld because its level is unknown. `propose` asks the corpus again, so a run
resumed after its file left the served levels declines that chunk with no model
call. `scripts/doc_review.py` prints one `withheld <id>: <why>` line per finding,
and the hook's line counts them. `tests/integration/test_doc_reviewer.py` holds
each case.

A style-rule retrieval that `scripts/query_corpus.py` refuses, or whose output
is not JSON, raises the third public symbol, `RulesRefused`, a `RuntimeError`
carrying the exit helper's three parts (what failed, on which input, what to do),
before the baseline gate and any model call. An execute run raises it as well
when the retrieval finds no node at all, which `[]` from a checkout with no
corpus, or from a corpus with no node for the rule query, means; so no model is
asked for edits with an empty rules section. A dry run calls no model, so it
goes on and its preview shows the empty section. `scripts/doc_review.py` ends a
run that raises it with exit 2 through `report`.

Its thin CLI is `scripts/doc_review.py` (`make doc-review`); its event trigger is
`scripts/hooks/on_stop_doc_review.py`, fired by `.claude/settings.json`; its
vendor-specific skill is `.claude/skills/doc-review/`. The nightly schedule
(`.github/workflows/scheduled.yml`, `ops/scheduled/crontab.example`) runs the
deterministic doer, not this agent: a schedule has no one to read a judgment.
