---
title: Practice refactor
kind: agent
layer: backend
status: template
owner: TBD
public_api: agents/practice_refactor/__init__.py
tags: [agent, refactor, practices, corpus, gate]
summary: Walks the corpus KG and refactors each chunk toward a named practice, gating every edit on make verify.
id: agents-practice-refactor-readme
created: 2026-07-07
updated: 2026-07-07
visibility: internal
canonical: true
---

# Practice refactor

Walks the corpus KG and refactors each chunk toward a named practice, gating
every edit on `make verify`.

The **applying** companion to the coding-practices catalogue: where the gate
(`check_structure.py` / ruff / mypy) *enforces* the practices on new code, this
agent brings *existing* code toward one **named** practice from
`config/practices.json`, one bounded corpus neighbourhood at a time. It walks the
graph with the read-only `query_corpus` tool, gates a green baseline with
`run_make_target`, then for each chunk proposes one bounded edit and applies it
through `apply_refactor` — which gates on `make verify` and **rolls back** unless
the tree stays green. So the agent **cannot mark a chunk done unless it satisfies
the very rule the gate encodes**.

It is thin: policy + prompt only. The real work lives in `scripts/` doers,
invoked as **tools** (per the specs in `agents/tools/`, declared in `tools.md`);
control flow is a neutral `Plan` on a `Runtime`; the model comes from `models/`.
The single public symbol is `refactor(...)`, returning a `RefactorReport`. It
**defaults to dry-run**: `refactor("<practice>")` walks the graph, gates the
read-only baseline, and reports the candidate chunks + the prompt it *would*
send, writing nothing; `refactor("<practice>", execute=True)` proposes and applies
the gated edits, with a durable per-chunk loop that resumes after a crash.

Its vendor-specific trigger is the `.claude/skills/practice-refactor/` skill; its
thin CLI entrypoint is `scripts/refactor_practice.py`. See
[coding-practices](../../docs/guides/coding-practices.md) for the catalogue.
