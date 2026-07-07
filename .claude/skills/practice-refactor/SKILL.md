---
name: practice-refactor
description: Refactor existing code toward ONE named coding practice from config/practices.json, gating every edit on `make verify`. Use when the user asks to apply/adopt/roll out a coding practice across the codebase, clean up code toward a keel practice, or "make the code follow <practice>". Walks the corpus knowledge graph one bounded neighbourhood at a time and cannot mark a chunk done unless the gate stays green.
---

# Practice refactor

This skill is a **thin, vendor-specific trigger** over a vendor-agnostic doer. It
holds no logic — it only says "run the practice-refactor doer" and how to read the
result. The reasoning lives in `agents/practice_refactor/` (model from `models/`),
the gate in the `scripts/` doers. See `docs/guides/coding-practices.md`.

## When to use
The user wants an *existing* codebase brought toward one **named** practice from
`config/practices.json` (e.g. `precise-container-types`, `exception-chaining`,
`typed-everywhere`) — not to enforce practices on new code (that is the gate:
`make verify`).

## How to run

1. **Pick the practice id.** List them with:
   `python3 -c "import json; [print(p['id']) for p in json.load(open('config/practices.json'))['practices']]"`

2. **Dry-run first** (default — walks the graph, gates the read-only baseline,
   proposes and writes nothing):
   ```
   python3 scripts/refactor_practice.py <practice-id> --json
   ```
   Read the report: `candidates` (the chunks it would touch), `baseline_green`
   (is the tree safe to refactor), and `preview`. If `candidates` is empty, the
   corpus may be stale — rebuild it with `make site-data`.

3. **Execute** once the dry-run looks right (proposes one bounded edit per chunk
   and applies it through the gated `apply_refactor`, which **rolls back** any edit
   that turns `make verify` red):
   ```
   python3 scripts/refactor_practice.py <practice-id> --execute --json
   ```

4. **Report** `refactored` (chunks whose edit passed the gate) vs `skipped`
   (chunks with no accepted edit). A chunk is *done* only if the gate stayed
   green — never on self-assessment.

## Rules
- One practice per run; keep edits bounded (the doer proposes the smallest edit
  and gates each one).
- Default to dry-run; only pass `--execute` after the preview is reviewed.
- Never bypass the doer with a raw edit — the gate is the definition of done
  (root `AGENT.md`; CONVENTIONS §17).
- Pick the model with `--model <name>` from the `models/` registry; never name a
  provider here (the doer stays vendor-agnostic).
