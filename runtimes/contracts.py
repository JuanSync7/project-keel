"""
title: Agent runtime contract
layer: backend
public_api: yes
summary: The neutral Plan/Step/Edge flowchart IR, the Runtime ABC, and the durability/HIL/fan-out capabilities every engine implements.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

__all__ = [
    "READ_ONLY", "WRITES", "MODEL_CALL", "EFFECTS", "END",
    "COMPLETED", "PAUSED",
    "Step", "Edge", "Plan", "TraceEntry", "RunResult", "Runtime",
    "Checkpointer", "Pause", "interrupt",
]

# Effect vocabulary -- identical to the `tool_effect` set in CONVENTIONS section
# 10, so a Step's effect IS its tool's declared effect. The runtime treats
# WRITES and MODEL_CALL as side-effecting: such a step is a no-op (never called)
# unless the run is authorized with execute=True. READ_ONLY steps always run.
# These same effectful steps are the natural durability commit points (a crash
# after them would lose real work); see Checkpointer.
READ_ONLY = "read-only"
WRITES = "writes"
MODEL_CALL = "model-call"
EFFECTS = (READ_ONLY, WRITES, MODEL_CALL)

# Neutral terminal sentinel: an edge to END ends the run. Mirrors LangGraph's
# END marker without importing it, so the IR names no vendor.
END = "__end__"

# RunResult.status values.
COMPLETED = "completed"
PAUSED = "paused"


@dataclass(frozen=True)
class Step:
    """One node in a plan: a named unit of work with a declared side-effect.

    ``run(state)`` returns a dict merged into the run state (or ``None`` for no
    change). ``effect`` is one of EFFECTS; a ``writes``/``model-call`` step is
    skipped -- its ``run`` is never invoked -- unless the run is authorized
    (``execute=True``).

    ``fan_out`` makes this a **map** step: when set, ``fan_out(state)`` returns a
    list of items and ``run`` is invoked once per item with ``state["item"]`` (and
    ``state["index"]``) bound; the per-item results are collected, in item order,
    under ``state[name]``. The default engine runs them sequentially; the
    LangGraph engine fans them out concurrently -- same ordered result either way.
    """

    name: str
    effect: str
    run: Callable[[dict], Optional[dict]]
    fan_out: Optional[Callable[[dict], list]] = None


@dataclass(frozen=True)
class Edge:
    """A directed transition ``src -> dst``, taken when ``when(state)`` is true.

    ``when=None`` is an unconditional edge. A runtime evaluates a node's
    outgoing edges in declaration order and follows the first whose ``when`` is
    ``None`` or returns true; ``dst == END`` ends the run. Branch predicates are
    pure functions of state -- this is what keeps control flow deterministic.
    An edge whose ``dst`` is an earlier node forms a cycle (e.g. iterative RAG).
    """

    src: str
    dst: str
    when: Optional[Callable[[dict], bool]] = None


@dataclass(frozen=True)
class Plan:
    """An agent's control flow as inspectable data: a flowchart of Steps.

    ``entry`` names the first step; ``steps`` are the nodes; ``edges`` are the
    transitions. The same Plan runs identically on any Runtime -- the engine
    changes how it executes, never what it means.
    """

    name: str
    entry: str
    steps: Tuple[Step, ...]
    edges: Tuple[Edge, ...]

    def step(self, name: str) -> Step:
        """Return the Step with this name, or raise KeyError if absent."""
        for s in self.steps:
            if s.name == name:
                return s
        raise KeyError(name)

    def next_from(self, current: str, state: dict) -> str:
        """Return the dst of the first matching outgoing edge from ``current``.

        Edges are tried in declaration order; the first whose ``when`` is None or
        returns true wins, else END. This is the single definition of edge
        semantics both engines share, so routing can't drift between them.
        """
        for edge in self.edges:
            if edge.src == current and (edge.when is None or edge.when(state)):
                return edge.dst
        return END

    def to_mermaid(self) -> str:
        """Render the plan as a Mermaid ``flowchart`` (it is already a graph).

        Nodes show their effect; a fan-out step is marked; conditional edges are
        dashed. Useful for docs/review and as the neutral analogue of LangGraph
        Studio -- no engine or vendor needed to visualise the flow.
        """
        shape = {READ_ONLY: ('["', '"]'), WRITES: ('[/"', '"/]'),
                 MODEL_CALL: ('{{"', '"}}')}
        lines = ["flowchart TD"]
        for s in self.steps:
            lo, hi = shape.get(s.effect, ('["', '"]'))
            tag = " &laquo;map&raquo;" if s.fan_out else ""
            lines.append("    %s%s%s (%s)%s%s" % (s.name, lo, s.name, s.effect, tag, hi))
        lines.append('    %s(("END"))' % "_END")
        for e in self.edges:
            dst = "_END" if e.dst == END else e.dst
            arrow = "-.->" if e.when is not None else "-->"
            lines.append("    %s %s %s" % (e.src, arrow, dst))
        return "\n".join(lines)


@dataclass(frozen=True)
class TraceEntry:
    """One executed (or skipped) node, in execution order -- the run's audit trail."""

    step: str
    effect: str
    ran: bool             # False => skipped (gated step in a dry run)
    skipped_reason: str   # "" when ran; else "dry-run"


@dataclass(frozen=True)
class RunResult:
    """The final run state, the ordered trace, and the run's terminal status.

    ``status`` is ``completed`` or ``paused``; when paused, ``interrupt`` carries
    the payload a step surfaced for a human, and the run can be resumed via
    ``Runtime.run(..., checkpointer=..., run_key=..., resume=<value>)``.
    """

    state: dict
    trace: Tuple[TraceEntry, ...]
    status: str = COMPLETED
    interrupt: object = None


class Runtime(ABC):
    """Executes a Plan. Engines (in-process, LangGraph, ...) are adapters of this.

    Callers depend on THIS, never on a concrete engine. An adapter changes HOW a
    plan executes (eager walk, compiled graph, durable checkpoints, fan-out) but
    never WHAT it means: the dry-run effect-guard, edge semantics, durability,
    human-in-the-loop, and fan-out ordering are identical across runtimes, pinned
    by ``tests/unit/runtimes/test_runtime_equivalence.py``.
    """

    name: str

    @abstractmethod
    def run(self, plan: Plan, state: Optional[dict] = None, *,
            execute: bool = False, checkpointer: "Optional[Checkpointer]" = None,
            run_key: str = "run", resume: object = ..., on_event=None) -> RunResult:
        """Execute ``plan`` from its entry node (or resume) and return a RunResult.

        ``execute`` authorises side-effecting (``writes``/``model-call``) steps.
        ``checkpointer`` (with ``run_key``) makes the run **durable**: state is
        snapshotted at step boundaries so it can resume after a crash or a pause.
        ``resume`` (anything other than the default sentinel) resumes a suspended
        run, injecting the value into the paused step's ``interrupt`` call.
        ``on_event`` is called once per step for **streaming** progress.
        """
        raise NotImplementedError


class Checkpointer(ABC):
    """Persists a run snapshot so a plan can resume after a crash or a pause.

    A snapshot is a plain dict (``cursor`` + ``state`` + ``trace``); the default
    engine writes one at each step boundary. Durability is keyed by ``run_key``,
    so concurrent runs don't collide. Implementations: an in-memory store for
    tests, a JSON file for cross-process recovery (see ``runtimes._checkpoint``).
    """

    @abstractmethod
    def save(self, key: str, snapshot: dict) -> None:
        """Persist ``snapshot`` under ``key`` (overwriting any prior one)."""
        raise NotImplementedError

    @abstractmethod
    def load(self, key: str) -> Optional[dict]:
        """Return the snapshot saved under ``key``, or ``None`` if there is none."""
        raise NotImplementedError

    @abstractmethod
    def clear(self, key: str) -> None:
        """Drop the snapshot under ``key`` (called when a run completes)."""
        raise NotImplementedError


class Pause(Exception):
    """Raised by ``interrupt`` to suspend a run pending human input.

    Engines catch this, checkpoint, and return a ``paused`` RunResult carrying
    the payload. Callers never raise it directly -- they call ``interrupt``.
    """

    def __init__(self, payload=None):
        super().__init__("paused")
        self.payload = payload


def interrupt(state: dict, payload=None):
    """Request human input from within a step (human-in-the-loop).

    On the first encounter the run **suspends**: the caller receives a ``paused``
    RunResult whose ``interrupt`` is ``payload``. When the run is resumed with a
    value, this call **returns that value** so the step proceeds. The engine
    injects the actual mechanism under ``state["_interrupt"]`` so this stays
    vendor-neutral; calling it outside a run raises RuntimeError.
    """
    impl = state.get("_interrupt")
    if impl is None:
        raise RuntimeError("interrupt() called outside a runtime run")
    return impl(payload)
