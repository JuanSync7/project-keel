---
title: agents/doc_reviewer — agent rules
kind: rules
layer: backend
status: template
owner: TBD
summary: Local agent rules inside agents/doc_reviewer/.
id: agents-doc-reviewer-agent
created: 2026-09-02
updated: 2026-11-07
visibility: internal
canonical: true
---

# Agent rules — `agents/doc_reviewer/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- Policy/prompt only. Invoke `scripts/` doers as **tools** via their CLI (per `agents/tools/` specs in `tools.md`); never `import` script logic. `review` is the only public symbol; keep prompt/policy in `_brain.py` private behind `__init__.py`.
- Get the model from `models/` (`get_model`); never name a provider. A missing model is `ModelUnavailable`, and the doers that call this agent turn it into a stated skip (exit 0).
- Default to dry-run (`execute=False`): `review`, `retrieve` and `baseline` run so the report is real; `propose` (model) and `apply` (writes) are skipped. Editing needs `execute=True`.
- Control flow is a neutral `Plan` (steps + edges; see `runtimes/`) executed by a `Runtime`; the dry-run effect-guard lives in the runtime, not in inline `if`s.
- **The gate is the definition of done.** A chunk is `applied` only when `apply_refactor` keeps `make check-docs` green; a red gate triggers journalled restoration and the chunk is `skipped`. A failed restore is `RollbackError` naming every unrestored file; inspect the tree before another refactor, since startup replays interrupted targets from the durable journal.
- **An edit cannot reach the judge.** `apply_refactor` refuses, before any write, an edit outside the chunk's own file (the run binds it with `--allow`) or to a path config/project.json `agents` protects, and a spec that names a gate: the gate is the run's `--gate` flag, never the reply's. So a finding in CONVENTIONS.md, an AGENT.md, an ADR or a tool card is declined, not fixed; a `README.md` under a protected directory stays editable (`agents.editable_names`), and `docs/guides/coding-practices.md` owns this policy.
- Edit the finding, never the document: the stamp, the path, the cell. Never an accepted ADR's decision text (`docs/guides/doc-style.md §8`), never a `.jinja` twin's templated line.
- The loop is **durable**: one chunk per step, cursor-checkpointed under `wiki/.runtime`, so a crash resumes without re-proposing accepted chunks.

The apply doer recovers before applying the next spec and logs recovered paths.
A `journal_conflict: true` report stops the loop for evidence inspection.
