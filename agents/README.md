---
title: Agents
kind: agent
layer: backend
status: template
owner: TBD
public_api: none
tags: []
summary: Autonomous / LLM agents (the 'brains') — reasoning, policy, prompts.
id: agents-readme
created: 2026-06-17
updated: 2026-09-02
visibility: internal
canonical: true
---

# Agents

Autonomous / LLM agents (the 'brains') — reasoning, policy, prompts.

Each agent is the decision-making core: prompts, policy, tool-use
logic. An agent needs a *model* to run on — it gets one from
`models/` (`get_model(name).run(prompt)`), so it never hardcodes a
provider. Keep transport (how the agent is *reached*) out of here —
that's `mcp/` and `api/`. Agents call into `src/` for real work and
into `evals/` for scoring. Default any state-changing action to a
dry run unless explicitly authorized.

## What ships here

| Member | Purpose | Not for | Entry point |
|--------|---------|---------|-------------|
| `doc_reviewer/` | Reviews the documentation against `docs/guides/doc-style.md`: `review_docs` supplies the deterministic facts (stale stamps, unresolved mentions, every roster row), `query_corpus` the guide's rules, `run_make_target` a green `check-docs` baseline; then, per chunk, the model proposes one bounded edit that `apply_refactor` applies gated on `make check-docs` and rolls back if red. Public symbol `review()` returning a frozen `DocReviewReport`; dry-run by default (no model call, nothing written). | Enforcing the documentation rules — that is the gate (`check_structure.py` P–T) and `tests/integration/test_doc_freshness.py`; the deterministic facts themselves — `scripts/jobs/review_docs.py`, which needs no agent; building or querying the corpus for a user — `index_enforcer/` and `wiki_navigator/`; code — `practice_refactor/`. | `scripts/doc_review.py` (`make doc-review`, `make doc-review-apply`); the stop hook `scripts/hooks/on_stop_doc_review.py` fired by `.claude/settings.json`; the `.claude/skills/doc-review/` skill. |
| `index_enforcer/` | Curates the corpus: gates the tree with `structure_check` (errors stop the run), rebuilds `wiki/corpus.json` with `build_corpus` then `link_corpus`, lists owner gaps with `accountability_report`, and fills only summaries that have no authored one via `models/` (needs `execute=True` and `fix_gaps=True`; a durable one-gap-per-step loop that resumes from `wiki/.runtime`). Public symbol `enforce()` returning a frozen `EnforceReport`; dry-run by default. | Answering questions over the corpus, which is `wiki_navigator/` (it only builds and annotates nodes, never reads them for a user); changing source code, which is `practice_refactor/`; and the README title list that `mcp/action_server.py`'s `rebuild_index` tool writes through `scripts/jobs/rebuild_index.py` (a markdown `Doc index`, no corpus, no model). A plain gate-free rebuild is `make site-data`, not this agent. | In-process only: `from agents.index_enforcer import enforce`. No thin `scripts/` CLI ships yet; it is driven by `tests/integration/test_index_enforcer_durability.py` and `test_agent_runtime_equivalence.py`. |
| `practice_refactor/` | Brings existing code toward ONE named practice from `config/practices.json`: `query_corpus` walks the KG neighbourhood for that practice, `run_make_target` proves a green baseline, then per chunk the model proposes one bounded edit that `apply_refactor` applies gated on `make verify` and rolls back if red. Public symbol `refactor()` returning a frozen `RefactorReport` (`candidates`, `refactored`, `skipped`, `preview`); dry-run by default (walks and gates, writes nothing). | Enforcing practices on new code, which is the gate itself (`make verify`: `check_structure.py` checks J to M, ruff, mypy) plus the advisory `scripts/check_practices.py`; rebuilding the corpus it walks, which is `index_enforcer/` or `make site-data`; and answering questions, which is `wiki_navigator/`. `scripts/refactor_practice.py` is this agent's thin CLI, not a second implementation of it. | `scripts/refactor_practice.py <practice-id> [--execute] [--json]`, itself triggered by the vendor-specific `.claude/skills/practice-refactor/` skill. |
| `tools/` | Eight shared `*.tool.md` adapter cards (`kind: tool`) that tell any agent how to invoke a `scripts/` doer: the exact `tool_command`, its `tool_effect` (`read-only`, `writes` or `model-call`), args, output, side effects and `## Used by`. Cards: `accountability_report`, `apply_refactor`, `build_corpus`, `link_corpus`, `query_corpus`, `review_docs`, `run_make_target`, `structure_check`. | Tool logic, which stays in the wrapped `scripts/` doer named by `public_api` (check G verifies `tool_command` invokes it); granting an agent a tool, which is a row in that agent's own `tools.md` manifest (`doc_reviewer/`, `index_enforcer/`, `practice_refactor/`, `wiki_navigator/`; check G keeps manifest and `## Used by` in sync); and reasoning prose, which is that agent's `prompt.md`. | Not executable. An agent's `_brain.py` shells out with `sys.executable` plus the card's argv; `check_structure.py` checks F and G validate the cards. |
| `triage/` | The minimal example brain: renders one fixed prompt (what happened, likely cause, next action) over an event payload such as a failure, diff or log, and only with `execute=True` runs it on `models.get_model(model)`. Public symbol `triage()` returning a plain `str` (in dry-run, the prompt it would have sent). No tools, no `Plan`, no corpus. | Anything that reads the corpus: a question over the wiki is `wiki_navigator/`, a corpus rebuild is `index_enforcer/`, a code change is `practice_refactor/`. Nor is it the pattern to copy for a new agent: it has no `prompt.md` or `tools.md` (CONVENTIONS §13 requires both) and returns a bare `str`; copy `wiki_navigator/` instead. | `scripts/hooks/on_stop_triage.py [PAYLOAD or -] [--execute] [--model NAME]`, the thin event-hook doer. No trigger is wired to it in this template (`.claude/settings.json`, pre-commit and CI do not reference it). |
| `wiki_navigator/` | Answers a question from the corpus: `query_corpus` retrieves a tree-plus-links neighbourhood (always runs, so `citations` is populated even in dry-run; a failed retrieval raises rather than handing the model an empty context), `confidential` and `restricted` nodes are dropped, and with `execute=True` the model synthesizes an answer citing each `node_id`. Public symbol `answer()` returning a frozen `Answer` (`text`, `Citation`s carrying `summary_source` and `owner` and `owner_source`); dry-run by default. | Building, linking or gap-filling the corpus it reads, which is `index_enforcer/`; editing code, which is `practice_refactor/`; and summarising an arbitrary payload with no retrieval, which is `triage/`. It answers only from retrieved nodes and says so when they do not contain the answer. | `mcp/qa_server.py` tool `wiki_answer` on the read-only `keel-wiki-qa` server, which calls `answer(question, execute=True)`. No `scripts/` CLI. |
