---
title: Runtimes
kind: package
layer: backend
status: template
owner: TBD
public_api: none
tags: [runtime, orchestration, control-flow, agents]
summary: Execute an agent's control flow as a neutral Plan — engines (in-process, LangGraph) are adapters behind one contract.
id: runtimes-readme
created: 2026-06-22
updated: 2026-06-22
visibility: internal
canonical: true
---

# Runtimes

The neutral home for **agent control flow**. An agent's policy is a
**`Plan`** — a small flowchart of typed `Step`s and `Edge`s — and a
**`Runtime`** executes it. This is the same neutral-concept-plus-adapter
shape as [`models/`](../models/README.md): a `ModelBackend` is *what an
agent runs on*; a `Runtime` is *how an agent's steps are run*.

| Path | Role |
|------|------|
| `__init__.py` | public API — `Plan`/`Step`/`Edge` + `get_runtime(name=None)` |
| `contracts.py` | the `Plan` IR (Step/Edge/RunResult) and the `Runtime` ABC |
| `registry.py` | name -> engine + the default (`inprocess`) |
| `_inprocess.py` | the default **zero-dependency** engine (reference semantics) |
| `langgraph_adapter.py` | one engine adapter — compiles a Plan to a LangGraph `StateGraph` |

## Why a Plan, not inline `if`s

A `Plan` makes an agent's flowchart **inspectable data** instead of nested
conditionals, and moves the **dry-run effect-guard into one place**: a
`Step` whose `effect` is `writes` or `model-call` is *skipped* (its `run`
is never called) unless the run is authorized with `execute=True`. The
`effect` vocabulary is exactly the `tool_effect` set from CONVENTIONS §10,
so a step's danger level is declared the same way its tool's is.

```python
from runtimes import Plan, Step, Edge, END, READ_ONLY, WRITES, get_runtime

plan = Plan(
    name="example", entry="gate",
    steps=(Step("gate", READ_ONLY, _gate), Step("build", WRITES, _build)),
    edges=(Edge("gate", "build", when=lambda s: not s["errors"]),
           Edge("gate", END), Edge("build", END)),
)
result = get_runtime().run(plan, {}, execute=False)   # default engine; dry-run
```

## Capabilities (same result on every engine)

These are neutral `Plan`/`Runtime` capabilities; the default engine implements
each in pure stdlib, and the LangGraph adapter maps them to native mechanisms
where it adds value (concurrency). All are pinned equivalent by the conformance
test.

| Capability | How to use it | Default engine | LangGraph engine |
|------------|---------------|----------------|------------------|
| **Visualize** | `plan.to_mermaid()` | renders the graph | same (it's a graph) |
| **Stream** | `run(..., on_event=cb)` — `cb` gets `{step, effect, ran, skipped_reason}` per step | per-step callback | per-node callback |
| **Durable / resume** | `run(..., checkpointer=cp, run_key=k)`; resume with `run(..., resume=value)` | snapshot at each step, re-enter at cursor | rebuild graph at `entry=cursor` |
| **Human-in-the-loop** | a step calls `interrupt(state, payload)`; the run returns `RunResult(status=PAUSED, interrupt=payload)`; resume with `run(..., resume=human_value)` | raise → pause; inject on resume | same hook, caught around `invoke` |
| **Fan-out (map)** | `Step(..., fan_out=lambda s: items)`; the body runs per item with `state["item"]`, results collected under `state[name]` in item order | sequential | LangGraph **`Send`** (concurrent) |

**Durability boundary.** A snapshot is written after *every* step. The `effect`
taxonomy means only `writes`/`model-call` steps strictly need it (those are the
commit points where a crash loses work); snapshotting after `read-only` steps
too is a harmless over-approximation that simply lets a resume skip re-running
cheap steps. Use `MemoryCheckpointer` for in-process pauses/tests and
`FileCheckpointer` for crash recovery across processes (state must be JSON-able).

## Engines are interchangeable (the vendor stays in one file)

`get_runtime(name)` mirrors `models.get_model(name)`. The default
`inprocess` engine is pure stdlib and is the **reference semantics**. A
graph engine such as **LangGraph** is *one adapter*, registered **lazily**
so the default install and the pre-commit path import nothing extra — it
is an optional dependency:

```bash
pip install -e '.[langgraph]'     # only if/when you select runtime="langgraph"
```

A different engine (Burr, pydantic-graph, a durable executor) is a new
sibling adapter over the same `Runtime` contract — never an edit to the
contract or to `agents/`. Adopt a heavier engine **per agent** only when a
real trigger arrives (durable resume across a crash, mid-flow human
approval, or a genuine cycle/fan-out), not for uniformity.

See [`docs/adr/0003-agent-control-flow-runtime.md`](../docs/adr/0003-agent-control-flow-runtime.md)
for the decision and [`docs/guides/agent-runtimes.md`](../docs/guides/agent-runtimes.md)
for the how-to.
