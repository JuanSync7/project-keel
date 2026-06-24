"""
title: LangGraph runtime adapter
layer: backend
public_api: no
summary: One engine adapter -- compiles a neutral Plan into a LangGraph StateGraph (durability, HIL, fan-out via Send, streaming).
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Annotated, TypedDict

from .contracts import (
    COMPLETED,
    END,
    MODEL_CALL,
    PAUSED,
    WRITES,
    Pause,
    RunResult,
    Runtime,
    TraceEntry,
)

__all__ = ["LangGraphRuntime"]

_GATED = (WRITES, MODEL_CALL)
_UNSET = object()
_INTERNAL = ("_interrupt", "_execute", "_trace")


def _merge(old, new):
    """Reducer: accumulate the evolving plan state as one last-value-merged dict."""
    merged = dict(old or {})
    merged.update(new or {})
    return merged


def _concat(old, new):
    """Reducer: gather fan-out worker results (each concurrent worker appends)."""
    return list(old or []) + list(new or [])


# The evolving plan state rides one merge-reduced `bag` channel; `collect` is a
# concat-reduced channel where fan-out workers (LangGraph Send) drop their
# per-item results to be reassembled in order. Defined at module scope so
# get_type_hints resolves it despite `from __future__ import annotations`.
class _PlanState(TypedDict):
    bag: Annotated[dict, _merge]
    collect: Annotated[list, _concat]


class _PauseSignal(Exception):
    """Internal: abort a LangGraph invoke when a step pauses (details in holder)."""


def _public(bag):
    return {k: v for k, v in bag.items() if k not in _INTERNAL}


def _emit(on_event, name, effect, ran, reason):
    if on_event is not None:
        on_event({"step": name, "effect": effect, "ran": ran, "skipped_reason": reason})


class LangGraphRuntime(Runtime):
    """Execute a Plan on LangGraph -- the vendor name is confined to THIS file.

    Compiles each Step into a ``StateGraph`` node and each Edge into an
    ``add_edge`` / ``add_conditional_edges`` transition, applying the IDENTICAL
    dry-run guard, durability, human-in-the-loop, and edge order as the
    in-process reference, so it changes execution and never semantics. Fan-out
    steps dispatch concurrently via LangGraph's ``Send`` and are reassembled in
    item order; resume re-enters the graph at the checkpoint cursor.

    LangGraph is an optional dependency (``pip install -e '.[langgraph]'``)
    imported lazily here, so the default install and the pre-commit path pull
    nothing. Equivalence with the default engine is pinned by
    ``tests/unit/runtimes/test_runtime_equivalence.py``.
    """

    name = "langgraph"

    def run(self, plan, state=None, *, execute=False, checkpointer=None,
            run_key="run", resume=_UNSET, on_event=None):
        """Compile ``plan`` to a StateGraph, invoke (or resume) it, return a RunResult."""
        from langgraph.graph import StateGraph

        resume_box = {"has": resume is not _UNSET, "value": resume}
        if resume is not _UNSET:
            if checkpointer is None:
                raise RuntimeError("resume requires a checkpointer")
            snap = checkpointer.load(run_key)
            if snap is None:
                raise RuntimeError("no checkpoint to resume for run_key %r" % run_key)
            bag0 = dict(snap["state"])
            bag0["_trace"] = [list(r) for r in snap["trace"]]
            entry = snap["cursor"]
        else:
            bag0 = dict(state or {})
            bag0["_trace"] = []
            entry = plan.entry
        bag0["_execute"] = execute

        holder = {}
        builder = StateGraph(_PlanState)
        for step in plan.steps:
            if step.fan_out is None:
                builder.add_node(step.name, self._node(
                    plan, step, checkpointer, run_key, on_event, resume_box, holder))
            else:
                self._add_fan_out(builder, plan, step, checkpointer, run_key, on_event)
        builder.set_entry_point(entry)
        _wire(builder, plan)
        graph = builder.compile()

        try:
            final = graph.invoke({"bag": bag0, "collect": []})
        except Exception:
            if not holder.get("paused"):
                raise
            if checkpointer is not None:
                checkpointer.save(run_key, {"cursor": holder["cursor"],
                                            "state": holder["state"],
                                            "trace": holder["trace"]})
            return RunResult(state=holder["state"],
                             trace=tuple(TraceEntry(*r) for r in holder["trace"]),
                             status=PAUSED, interrupt=holder["payload"])

        bag = final["bag"]
        if checkpointer is not None:
            checkpointer.clear(run_key)
        return RunResult(state=_public(bag),
                         trace=tuple(TraceEntry(*r) for r in bag.get("_trace", [])),
                         status=COMPLETED)

    def _node(self, plan, step, checkpointer, run_key, on_event, resume_box, holder):
        """Wrap a normal Step as a LangGraph node (dry-run guard, HIL, checkpoint)."""
        def _interrupt(payload):
            if resume_box["has"]:
                resume_box["has"] = False
                return resume_box["value"]
            raise Pause(payload)

        def node(state):
            bag = state["bag"]
            execute = bag.get("_execute", False)
            trace = list(bag.get("_trace", []))
            if step.effect in _GATED and not execute:
                _emit(on_event, step.name, step.effect, False, "dry-run")
                return {"bag": {"_trace": trace + [[step.name, step.effect, False, "dry-run"]]}}
            local = dict(bag)
            local["_interrupt"] = _interrupt
            try:
                update = step.run(local) or {}
            except Pause as p:
                holder.update(paused=True, payload=p.payload, cursor=step.name,
                              state=_public(bag), trace=trace)
                raise _PauseSignal()
            new = dict(update)
            new["_trace"] = trace + [[step.name, step.effect, True, ""]]
            _emit(on_event, step.name, step.effect, True, "")
            _checkpoint_after(checkpointer, run_key, plan, step.name, bag, update, new["_trace"])
            return {"bag": new}
        return node

    @staticmethod
    def _add_fan_out(builder, plan, step, checkpointer, run_key, on_event):
        """Compile a fan-out Step into dispatch -> worker (Send) -> gather nodes."""
        from langgraph.types import Send

        worker_name = step.name + "__worker"
        gather_name = step.name + "__gather"

        def dispatch(state):
            return {}   # routing happens on the conditional edge below

        def route(state):
            bag = state["bag"]
            if step.effect in _GATED and not bag.get("_execute", False):
                return gather_name   # skipped: gather emits the skipped trace
            items = list(step.fan_out(bag))
            if not items:
                return gather_name
            sends = []
            for index, item in enumerate(items):
                payload = dict(bag)
                payload["item"] = item
                payload["index"] = index
                sends.append(Send(worker_name, {"bag": payload}))
            return sends

        def worker(state):
            bag = state["bag"]
            result = step.run(bag) or {}
            return {"collect": [[step.name, bag["index"], result]]}

        def gather(state):
            bag = state["bag"]
            execute = bag.get("_execute", False)
            trace = list(bag.get("_trace", []))
            if step.effect in _GATED and not execute:
                _emit(on_event, step.name, step.effect, False, "dry-run")
                return {"bag": {"_trace": trace + [[step.name, step.effect, False, "dry-run"]]}}
            mine = [(idx, res) for (nm, idx, res) in state.get("collect", [])
                    if nm == step.name]
            mine.sort(key=lambda pair: pair[0])
            update = {step.name: [res for _, res in mine]}
            new = dict(update)
            new["_trace"] = trace + [[step.name, step.effect, True, ""]]
            _emit(on_event, step.name, step.effect, True, "")
            _checkpoint_after(checkpointer, run_key, plan, step.name, bag, update, new["_trace"])
            return {"bag": new}

        builder.add_node(step.name, dispatch)
        builder.add_node(worker_name, worker)
        builder.add_node(gather_name, gather)
        builder.add_conditional_edges(
            step.name, route, {gather_name: gather_name, worker_name: worker_name})
        builder.add_edge(worker_name, gather_name)
        # gather_name -> the step's normal successors is wired by _wire (it
        # re-homes the plan edges whose src == step.name onto the gather node).


def _checkpoint_after(checkpointer, run_key, plan, name, bag, update, new_trace):
    """Durability commit point: snapshot after a step (cursor = the next node)."""
    if checkpointer is None:
        return
    post = dict(bag)
    post.update(update or {})
    nxt = plan.next_from(name, post)
    if nxt != END:
        checkpointer.save(run_key, {"cursor": nxt, "state": _public(post),
                                    "trace": new_trace})


def _wire(builder, plan):
    """Translate plan edges into LangGraph (conditional) edges, by source.

    A fan-out step's outgoing edges are re-homed onto its ``::gather`` node, so
    routing after the fan-out sees the collected results.
    """
    from langgraph.graph import END as LG_END

    fan_names = set(s.name for s in plan.steps if s.fan_out is not None)
    by_src = OrderedDict()
    for edge in plan.edges:
        src = edge.src + "__gather" if edge.src in fan_names else edge.src
        by_src.setdefault(src, []).append(edge)
    for src, edges in by_src.items():
        if len(edges) == 1 and edges[0].when is None:
            dst = edges[0].dst
            builder.add_edge(src, LG_END if dst == END else dst)
        else:
            builder.add_conditional_edges(src, _router(edges), _dest_map(edges, LG_END))


def _router(edges):
    """Return a path function mirroring 'first matching outgoing edge' order."""
    def route(state):
        bag = state["bag"]
        for edge in edges:
            if edge.when is None or edge.when(bag):
                return edge.dst
        return END
    return route


def _dest_map(edges, lg_end):
    """Map each possible router result (incl. END) to its LangGraph target."""
    dest = {}
    for edge in edges:
        dest[edge.dst] = lg_end if edge.dst == END else edge.dst
    dest[END] = lg_end   # fallback when no edge matched
    return dest
