---
title: Agent runtimes (Plan + Runtime; LangGraph as one engine)
kind: doc
layer: backend
status: template
owner: TBD
tags: [agents, runtime, control-flow, langgraph, determinism, guide]
summary: How to declare an agent's control flow as a neutral Plan, run it on the default engine, and opt into LangGraph as one adapter.
id: docs-guides-agent-runtimes
created: 2026-06-22
updated: 2026-06-22
visibility: internal
canonical: true
---

# Agent runtimes

An agent's *policy* is what it decides; its *control flow* is the order its
steps run in. This template keeps control flow a **neutral concept** — a
`Plan` executed by a `Runtime` — so the execution engine is one interchangeable
adapter, exactly like a model provider behind [`models/`](../../models/README.md)
(see CONVENTIONS §16 for the rule, ADR-0003 for the decision).

## The model

- **`Step`** — one node: a `name`, an `effect`, and a `run(state) -> dict|None`
  callable. The `effect` reuses the `tool_effect` vocabulary (CONVENTIONS §10):
  `read-only`, `writes`, or `model-call`.
- **`Edge`** — a transition `src -> dst`, optionally guarded by a pure
  `when(state) -> bool` predicate. From a node, the **first** matching outgoing
  edge is followed; an edge to `END` ends the run.
- **`Plan`** — `name`, `entry`, the `steps`, and the `edges`. The agent's
  flowchart as inspectable data.
- **`Runtime`** — executes a Plan: `run(plan, state, *, execute=False)`.

### The one rule that buys determinism

A `writes` or `model-call` step is **skipped — its `run` is never called** —
unless the run is authorized with `execute=True`. This dry-run effect-guard
lives in the runtime, in one place, instead of being copy-pasted as
`if execute:` across every agent. Read-only steps always run, so a report or a
retrieval populates its result even in a dry run.

## Declare a plan

```python
from runtimes import Plan, Step, Edge, END, READ_ONLY, WRITES, MODEL_CALL, get_runtime

def _gate(s):   return {"errors": _run_checker()}
def _build(s):  _rebuild_index(); return None
def _report(s): return {"gaps": _find_gaps()}
def _fill(s):   return {"filled": _fill_gaps(s["gaps"])}

PLAN = Plan(
    name="enforce", entry="gate",
    steps=(Step("gate",  READ_ONLY,  _gate),
           Step("build", WRITES,     _build),
           Step("report", READ_ONLY, _report),
           Step("fill",  MODEL_CALL, _fill)),
    edges=(Edge("gate", "build", when=lambda s: not s["errors"]),  # clean -> rebuild
           Edge("gate", "report"),                                 # dirty -> skip build
           Edge("build", "report"),
           Edge("report", "fill", when=lambda s: s.get("gaps")),
           Edge("report", END),
           Edge("fill", END)),
)

report = get_runtime().run(PLAN, {}, execute=False)   # default engine, dry-run
```

The branch predicates (`when=...`) are what used to be inline
`if execute and not errors` conjunctions — now they are named, pure functions
you can read as a transition table.

## Run it on a different engine

`get_runtime(name)` mirrors `models.get_model(name)`:

```python
get_runtime().run(PLAN, {}, execute=True)              # 'inprocess' (default, stdlib)
get_runtime("langgraph").run(PLAN, {}, execute=True)   # same plan, LangGraph engine
```

The default **`inprocess`** engine is pure stdlib and is the *reference
semantics*. LangGraph is **one adapter**, registered lazily and shipped as an
optional extra — install it only if you select it:

```bash
pip install -e '.[langgraph]'
```

Without it installed, `get_runtime("langgraph")` raises `ImportError`; the
default path imports nothing extra.

## Add another engine

Write an adapter implementing the `Runtime` ABC (`runtimes/contracts.py`),
register a lazy thunk in `runtimes/registry.py`, and add its dependency as a new
optional extra in `pyproject.toml`. Keep the vendor name inside that one file.
Your adapter must produce the **same final state and trace** as the `inprocess`
reference — that equivalence is enforced by
`tests/unit/runtimes/test_runtime_equivalence.py` (it `importorskip`s the
optional engine, so CI without the dep stays green).

## Capabilities (work on *every* engine)

The operational features people reach for LangGraph for are **neutral
capabilities** of the `Plan`/`Runtime` contract — the default engine implements
each in pure stdlib, and the conformance test pins both engines to the same
result. You opt into each by passing an argument or marking a step; you do not
switch engines to get them.

```python
from runtimes import get_runtime, interrupt, MemoryCheckpointer, PAUSED

# Streaming — a callback per step.
get_runtime().run(plan, {}, execute=True, on_event=lambda e: print(e["step"], e["ran"]))

# Durable / resumable — snapshot at each step boundary; resume continues from the cursor.
cp = MemoryCheckpointer()                 # or FileCheckpointer(dir) for cross-process
get_runtime().run(plan, {}, execute=True, checkpointer=cp, run_key="job")

# Human-in-the-loop — a step asks, the run pauses, you resume with the answer.
def review(s):
    decision = interrupt(s, {"question": "approve these gaps?", "gaps": s["gaps"]})
    return {"approved": decision}
paused = get_runtime().run(plan, {}, execute=True, checkpointer=cp, run_key="job")
assert paused.status == PAUSED            # paused.interrupt holds the question
get_runtime().run(plan, {}, execute=True, checkpointer=cp, run_key="job", resume="yes")

# Fan-out (map) — a step's body runs per item; results collected in item order.
Step("fill", MODEL_CALL, fill_one, fan_out=lambda s: s["gaps"])

# Visualize — render the flowchart (no engine needed).
print(plan.to_mermaid())
```

**Durability boundary (why "after every step").** The `effect` of a step tells
us exactly where a crash would lose work: `writes`/`model-call` steps are the
commit points. Snapshotting after `read-only` steps too is a deliberate, harmless
over-approximation — slightly *more* durability than strictly needed — so a
resume can also skip re-running cheap steps. Idempotent doers (the template's
rule: "safe to run twice") mean re-running the in-flight step on resume is safe.

## When the LangGraph engine specifically earns its keep

The capabilities above run on `inprocess`, so **default to it**. Switch a given
agent to `runtime="langgraph"` only when LangGraph's *execution* adds something
the stdlib walker can't:

| Trigger | What the LangGraph engine adds |
|---------|--------------------------------|
| A fan-out step with many slow items (e.g. N model calls) | `Send` runs them **concurrently** (the default engine is sequential) |
| You want LangGraph Studio / its native persistence backends | deeper adapter integration, kept inside `langgraph_adapter.py` |

A linear 1–2 step agent (e.g. `triage`) stays a Plan on the default engine, or
need not adopt one at all. Don't switch engines for uniformity.

## See also

- [`runtimes/README.md`](../../runtimes/README.md) — the package map.
- [`docs/adr/0003-agent-control-flow-runtime.md`](../adr/0003-agent-control-flow-runtime.md) — the decision.
- [`docs/guides/deterministic-checks.md`](deterministic-checks.md) — the suite that keeps the repo (and the conformance test) honest.
