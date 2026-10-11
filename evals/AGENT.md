---
title: evals — agent rules
kind: rules
layer: n/a
status: template
owner: TBD
summary: Local agent rules inside evals/.
id: evals-agent
created: 2026-06-17
updated: 2026-10-11
visibility: internal
canonical: true
---

# Agent rules — `evals/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- Evals score quality on a dataset; they are not pass/fail unit tests — keep them out of `tests/`.
- Version datasets in git: the dataset is the history. A run report is per run, written under config/project.json `evals.report_dir` (git-ignored) and replaced whole, never accumulated.
- A live run never writes the tracked dataset; it writes candidates, and a person promotes one by hand (`README_run.md`).
- Add a scorer only in `_scorers.py` plus its branch in the `scorer.oneOf` of `config/evals/eval-case.schema.json`; add a doer only in `_doers.py` plus the schema's `input.doer` enum. `tests/integration/test_evals_schema.py` holds each pair equal.
- Harness code stays here; `scripts/run_evals.py` is a thin CLI over it and holds no judging logic.
- Compute a case's hashes with `evals.prompt_sha256` and `evals.sha256_text`, never by hand.
