---
name: doc-review
description: Review the documentation against docs/guides/doc-style.md — stale `updated:` stamps, backticked paths that resolve to nothing, and every roster's `Not for` cell — and, when asked, apply one gated edit per finding. Use when the user asks to check, review, freshen, or tidy the docs, to make the READMEs say what ships, or to find documentation drift. Dry-run by default; every applied edit is gated on `make check-docs` and rolled back if red.
---

# Doc review

This skill is a **thin, vendor-specific trigger** over a vendor-agnostic doer. It
holds no logic — it only says "run the doc-review doer" and how to read the
result. The reasoning lives in `agents/doc_reviewer/` (model from `models/`), the
deterministic facts in `scripts/jobs/review_docs.py`, the gate in `make check-docs`.
See `docs/guides/doc-style.md`.

## When to use
The user wants the documentation *reviewed* — kept current, unambiguous, with every
roster cell true — not the gate run (that is `make check`, on every commit) and not
prose written from scratch.

## How to run

1. **Dry-run first** (default — gathers the findings, retrieves the rules, gates the
   read-only baseline, calls no model, writes nothing):
   ```
   make doc-review
   ```
   or, for the full report: `.venv/bin/python scripts/doc_review.py --json`. Read
   `stale`, `unresolved`, `rosters`, and `candidates` (the chunks the model would be
   asked about, in order). `preview` is the exact prompt the first chunk would get.

2. **Execute** once the dry-run looks right (one bounded edit per chunk, applied
   through the gated `apply_refactor`, which **rolls back** any edit that turns
   `make check-docs` red):
   ```
   .venv/bin/python scripts/doc_review.py --execute --json
   ```

3. **Report** `applied` (files whose edit passed the gate) vs `skipped` (chunks
   the model declined, or whose edit was rolled back). A chunk is *done* only if
   the gate stayed green — never on self-assessment.

## Rules
- Default to dry-run; only pass `--execute` after the preview is reviewed.
- Never bypass the doer with a raw edit — the gate is the definition of done
  (root `AGENT.md`; CONVENTIONS §17).
- Pick the model with `--model <name>` from the `models/` registry; never name a
  provider here. If no model is available the doer says so and exits 0.
- What the gate already fails on (a dead link, a roster that names a missing
  member) is not this skill's job: fix it, then review.
