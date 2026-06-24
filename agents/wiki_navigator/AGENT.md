---
title: agents/wiki_navigator — agent rules
kind: rules
layer: backend
status: template
owner: TBD
summary: Local agent rules inside agents/wiki_navigator/.
id: agents-wiki-navigator-agent
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# Agent rules — `agents/wiki_navigator/`

These rules are **local and authoritative** for this directory. They inherit from the root `AGENT.md` and `CONVENTIONS.md`; where they conflict, the more specific (this) file wins.

## Rules

- Policy/prompt only. Retrieve via the `query_corpus` tool (its CLI, per `agents/tools/`); never `import` script logic. `answer` is the only public symbol; keep policy in `_brain.py`.
- Get the model from `models/` (`get_model`); never name a provider.
- Default to dry-run (`execute=False`): retrieval + citations run, but no model call.
- Control flow is a neutral `Plan` (`retrieve` -> `synthesize`; see `runtimes/`) executed by a `Runtime`; only the `synthesize` (`model-call`) step is gated by `execute`. `answer(runtime=...)` selects the engine; default is the stdlib `inprocess` engine, never a vendor.
- Answer only from retrieved nodes; cite every claim by `node_id`; surface provenance (authored vs generated) and accountability (`owner_source`); never reveal `confidential`/`restricted` nodes.
