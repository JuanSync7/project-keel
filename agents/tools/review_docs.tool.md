---
title: Review docs
kind: tool
layer: cross-cutting
status: stable
owner: platform-team
public_api: scripts/jobs/review_docs.py
tags: [tool, documentation, freshness, rosters, review]
summary: Read-only documentation review — stale `updated:` stamps, backticked paths that resolve to nothing, and every roster row, as JSON.
id: tool-review-docs
created: 2026-09-02
updated: 2026-09-02
visibility: internal
canonical: true
tool_command: python3 scripts/jobs/review_docs.py --json
tool_effect: read-only
---

# Review docs

## Command
`python3 scripts/jobs/review_docs.py [--json] [--strict] [--today YYYY-MM-DD] [--root PATH]`

## Purpose
The deterministic half of the documentation review: the facts a rule can state
about the docs. Freshness — every governed document's `updated:` is no earlier
than its last commit, and a document modified in the working tree carries
today's date (CONVENTIONS §1). The advisory that stays advisory — a backticked
repository path that resolves to nothing. And every roster row (`## What ships
here`: path, member, line, the `Not for` cell), so the `doc_reviewer` can judge
each cell against `docs/guides/doc-style.md §2`.

## When to use
- Before proposing any documentation edit, to know what is actually stale,
  dangling or unjudged — the model reasons over these facts, never over a guess.
- NOT to gate the tree from an agent (the gate is `run_make_target check-docs`,
  which runs this doer with `--strict` alongside `check_structure`), and NOT to
  judge a roster cell — it reports the cell; the judgment is the agent's.

## Args
| Flag | Required | Default | Meaning |
|------|----------|---------|---------|
| `--json` | no | off | emit `{checked, findings, unresolved_mentions, rosters}` |
| `--strict` | no | off | exit 1 on a stale stamp (gate mode; mentions stay advisory) |
| `--today` | no | today | the date a modified file must carry (tests pin it) |
| `--root` | no | this checkout | repository root |

## Output
Text: one `STALE`/`MENTION` line per finding and a summary line. `--json`: the
object above. No git repository → a stated skip on stdout, exit 0.

## Side effects
READ-ONLY. Reads the tree and asks git for dates; writes nothing; no model call.

## Used by
- agents/doc_reviewer
