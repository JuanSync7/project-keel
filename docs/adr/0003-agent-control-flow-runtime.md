---
title: "ADR-0003: Agent control flow as a neutral Runtime, with LangGraph as one adapter"
kind: adr
layer: n/a
status: accepted
owner: TBD
tags: [adr, agent, runtime, control-flow, langgraph, determinism]
summary: Agents declare control flow as a neutral Plan run by a Runtime; the default engine is stdlib, LangGraph is one optional adapter.
id: docs-adr-0003-agent-control-flow-runtime
created: 2026-06-22
updated: 2026-06-22
visibility: internal
canonical: true
---

# ADR-0003: Agent control flow as a neutral Runtime, with LangGraph as one adapter

**Status:** accepted

## Context

The agents (`agents/triage`, `agents/index_enforcer`, `agents/wiki_navigator`)
get their determinism today from four hand-rolled properties: `execute=False`
dry-run defaults; all deterministic logic living in pure-stdlib `scripts/`
doers invoked as CLIs (never imported); exactly one confined model node per
agent; and frozen-dataclass outputs with provenance. That works at this scale,
but the gating was encoded as ad-hoc inline conjunctions
(`if execute and not s_errors`, `if execute and fix_gaps and ... and not s_errors`)
that get tangled as routing grows, there was no per-step trace, and a crash
mid-loop loses work (relevant in our EDR/SIGKILL environment).

The question raised: should agents adopt **LangGraph** to ground them in
deterministic, flowchart-style steps? LangGraph is a capable, mature graph
engine (StateGraph, conditional edges, checkpointers, `interrupt()`, Send
fan-out, Studio). But it requires Python 3.10+ and pulls a heavy transitive
tree (langchain-core, langgraph-checkpoint, orjson, httpx, …). Our
`pyproject.toml` is `dependencies = []`, and our pre-commit gate runs
`python3 scripts/check_structure.py` as `language: system` under the host's old
(3.6.8) stdlib-only interpreter.

Two premises were offered and are **not** load-bearing:

- *"It's open-source, so there's no coupling problem."* Open-source settles
  licensing, not architecture. The coupling this template bans (root `AGENT.md`,
  §9) lives at the import/API boundary — `from langgraph.graph import StateGraph`
  in `agents/_brain.py` would wed the brain layer to one vendor's control-flow
  design. cdmon is open-source and still enters behind a thin adapter.
- *"It's the only SDK that follows a flowchart."* Burr, pydantic-graph, and
  Haystack are also graph engines; LlamaIndex Workflows and CrewAI Flows are
  flowchart-shaped without a graph; Temporal/Prefect give durable execution.
  That several interchangeable engines exist is itself the argument for naming
  the neutral concept and keeping the engine swappable.

## Decision

Model **agent control flow as a neutral concept first**, exactly as `models/`
models providers and `src/backend/agent_surface/` models agent discovery.

1. A top-level package **`runtimes/`** defines a neutral `Plan` (a flowchart of
   typed `Step`s + `Edge`s; `Step.effect` reuses the §10 `tool_effect`
   vocabulary `read-only` | `writes` | `model-call`) and a `Runtime` ABC
   (`run(plan, state, *, execute=False) -> RunResult`) in `contracts.py`,
   re-exported through `__init__.py`/`__all__` (§3).
2. `runtimes/registry.py` provides `get_runtime(name=None)` / `list_runtimes()`
   / `DEFAULT_RUNTIME = "inprocess"` — the shape of `models/registry.py`.
3. The **default** runtime, `runtimes/_inprocess.py`, is a ~40-line
   zero-dependency stdlib walker. It enforces the dry-run invariant **once**: a
   `writes`/`model-call` step is a no-op (its `run` is never called) unless
   `execute=True`. This is what CI, pre-commit, and the app always get.
4. **LangGraph is ONE adapter** in `runtimes/langgraph_adapter.py`;
   `import langgraph` appears there and nowhere else. It is a **lazy** registry
   entry, imported only when `get_runtime("langgraph")` is called, and an
   **optional extra** (`pip install -e '.[langgraph]'`), never in `dependencies`.
   It compiles a `Plan` into a `StateGraph` (the whole evolving state rides one
   merge-reduced channel) and applies the identical effect-guard — it changes
   **execution, never semantics**.
5. Agents import `from runtimes import get_runtime, Plan, Step, Edge` and never
   see a vendor. The single model node stays `Step(MODEL_CALL)` reached only via
   `models.get_model()`; `enforce()`/`answer()` keep returning their frozen
   dataclasses behind `__init__.py` (§13).
6. `config/project.json` gains a `runtimes` block (`default` + `available`),
   validated by `check_structure.py` (`check_H`, §16).

`index_enforcer` is refactored as the worked example (its two inline
conjunctions become the named edge predicates `_clean` and `_wants_fill`);
`wiki_navigator` becomes a `retrieve -> synthesize` plan; `triage` stays linear
(no runtime). LangGraph is **opt-in per agent** (`runtime="langgraph"`), adopted
only when an agent hits a real trigger.

## Consequences

- **Positive.** Rule-compliant by construction: vendor-neutrality, thin-adapter
  (§9), the §3 boundary, and §13 agent shape all hold. `dependencies = []` and
  the 3.6.8 pre-commit path are untouched (the default engine is stdlib;
  LangGraph is lazily imported only on explicit selection). Determinism gets
  *stronger*: the dry-run effect-guard moves from three hand-maintained brains
  into one runtime, becomes engine-independent, and is pinned by a conformance
  test asserting `inprocess` and `langgraph` yield identical state **and** trace
  on fixed plans (including that gated bodies are never invoked in a dry run).
  Control flow is now inspectable `Plan` data. The seam for LangGraph's heavier
  wins (checkpointer/interrupt/Send) is ready without editing agents or the
  contract.
- **Negative / cost.** Real new surface area (a package, the `Plan` IR,
  README/AGENT/CLAUDE labels, a `tests/unit/runtimes/` mirror, a manifest block)
  for pipelines that today trigger none of LangGraph's wins — deliberate
  future-proofing. The neutral `Plan` is a lowest-common-denominator IR:
  LangGraph's richest features (typed reducers, native `interrupt()`, Send)
  require growing the contract before they can be exposed. The effect-guard is
  implemented in two engines (mitigated by the conformance test).
- **Neutral.** Generated artifacts stay gitignored. If `inprocess` proves
  sufficient forever, the LangGraph adapter is simply never imported and no cost
  is paid.

See CONVENTIONS §16, `docs/guides/agent-runtimes.md`, and `runtimes/README.md`.
