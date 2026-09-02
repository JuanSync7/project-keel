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
updated: 2026-09-02
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
mentions never are). What neither can decide — is this `Not for` cell *true*, does
this stale stamp deserve today's date, is this backticked name a path or a noun —
this agent judges, one chunk at a time, with the guide's own rules retrieved from
the corpus as its context. Every edit lands through `apply_refactor`, gated on
`make check-docs` (the structure gate plus strict freshness), and is **rolled
back** unless the tree stays green.

It is thin: policy + prompt only. The doers are `scripts/` tools (per the specs in
`agents/tools/`, declared in `tools.md`); control flow is a neutral `Plan` on a
`Runtime`; the model comes from `models/`. The single public symbol is
`review(...)`, returning a `DocReviewReport`. It **defaults to dry-run**:
`review()` gathers the findings, retrieves the rules, gates the read-only baseline
and reports the candidate chunks plus the prompt it *would* send, calling no model
and writing nothing; `review(execute=True)` proposes and applies the gated edits
in a durable per-chunk loop that resumes after a crash. An unavailable model is a
stated skip in its callers (`ModelUnavailable`, `models/`).

Its thin CLI is `scripts/doc_review.py` (`make doc-review`); its event trigger is
`scripts/hooks/on_stop_doc_review.py`, fired by `.claude/settings.json`; its
vendor-specific skill is `.claude/skills/doc-review/`. The nightly schedule
(`.github/workflows/scheduled.yml`, `ops/scheduled/crontab.example`) runs the
deterministic doer, not this agent: a schedule has no one to read a judgment.
