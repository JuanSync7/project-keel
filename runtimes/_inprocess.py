"""
title: In-process runtime
layer: backend
public_api: no
summary: The default zero-dependency Plan executor; reference semantics for the dry-run guard, durability, HIL, fan-out, and streaming. A run that takes more steps than its cap is a RuntimeError naming the plan and the cap; the cap is the constructor's `max_steps`, or config/project.json `runtimes.max_steps` read through scripts/config_loader.py when none is given, and a cap that is not an integer >= 1 is refused, a configured one as config_loader.WrongValue naming the key.
"""

from __future__ import annotations

import os

from scripts import config_loader

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

__all__ = ["InProcessRuntime"]

_GATED = (WRITES, MODEL_CALL)
_MAX_STEPS = ("runtimes", "max_steps")
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UNSET = object()
_INTERNAL = ("_interrupt",)  # engine-injected keys never returned to the caller


def configured_max_steps(root=None):
    """config/project.json `runtimes.max_steps` of *root* (this checkout when
    None), through scripts/config_loader.py: its default when unset, and
    config_loader.WrongValue when it is not an integer >= 1."""
    loaded = config_loader.read(_REPO if root is None else root)
    values = config_loader.resolve(
        loaded, config_loader.rows(_MAX_STEPS), config_loader.CONFIG_FILE
    )
    return values[_MAX_STEPS]


def _public(state):
    """Return state without engine-internal keys (e.g. the interrupt hook)."""
    return {k: v for k, v in state.items() if k not in _INTERNAL}


def _rows(trace):
    return [[t.step, t.effect, t.ran, t.skipped_reason] for t in trace]


def _objs(rows):
    return [TraceEntry(*r) for r in rows]


def _run_step(step, state):
    """Run a Step. A fan-out step runs its body per item (in order) and collects
    the per-item results, in item order, under ``state[step.name]``."""
    if step.fan_out is None:
        return step.run(state)
    results = []
    for index, item in enumerate(step.fan_out(state)):
        sub = dict(state)
        sub["item"] = item
        sub["index"] = index
        results.append(step.run(sub))
    return {step.name: results}


class InProcessRuntime(Runtime):
    """Walk a Plan's edges in pure Python -- no dependencies, runs anywhere.

    This is the DEFAULT runtime and the *reference semantics* every other engine
    must match: a ``writes``/``model-call`` step is skipped unless
    ``execute=True``; the first matching outgoing edge is followed until END;
    a ``checkpointer`` snapshots state at each step boundary (durable resume);
    ``interrupt`` suspends for human input; ``fan_out`` maps a step over items;
    ``on_event`` streams per-step progress. Pure stdlib -- runs under CI,
    pre-commit, and the app with no install.
    """

    name = "inprocess"

    def __init__(self, max_steps=None, root=None):
        """*max_steps* caps the steps of one run; None reads
        `runtimes.max_steps` from *root*'s config (this checkout when None)."""
        if max_steps is None:
            max_steps = configured_max_steps(root)
        # bool is an int to isinstance, and `True` steps is a typo, not a cap.
        elif isinstance(max_steps, bool) or not isinstance(max_steps, int):
            raise ValueError("max_steps must be an integer >= 1, not %r" % max_steps)
        if max_steps < 1:
            raise ValueError("max_steps must be an integer >= 1, not %r" % max_steps)
        self.max_steps = max_steps

    def run(
        self,
        plan,
        state=None,
        *,
        execute=False,
        checkpointer=None,
        run_key="run",
        resume=_UNSET,
        on_event=None,
    ):
        """Execute (or resume) the plan; return final state, trace, and status."""
        resume_box = {"has": resume is not _UNSET, "value": resume}
        if resume is not _UNSET:
            if checkpointer is None:
                raise RuntimeError("resume requires a checkpointer")
            snap = checkpointer.load(run_key)
            if snap is None:
                raise RuntimeError("no checkpoint to resume for run_key %r" % run_key)
            st = dict(snap["state"])
            trace = _objs(snap["trace"])
            current = snap["cursor"]
        else:
            st = dict(state or {})
            trace = []
            current = plan.entry

        def _interrupt(payload):
            if resume_box["has"]:
                resume_box["has"] = False
                return resume_box["value"]
            raise Pause(payload)

        st["_interrupt"] = _interrupt

        steps = 0
        while current and current != END:
            step = plan.step(current)
            if step.effect in _GATED and not execute:
                trace.append(TraceEntry(step.name, step.effect, False, "dry-run"))
                self._emit(on_event, step.name, step.effect, False, "dry-run")
            else:
                try:
                    update = _run_step(step, st)
                except Pause as p:
                    if checkpointer is not None:
                        checkpointer.save(
                            run_key,
                            {
                                "cursor": current,
                                "state": _public(st),
                                "trace": _rows(trace),
                            },
                        )
                    return RunResult(
                        state=_public(st),
                        trace=tuple(trace),
                        status=PAUSED,
                        interrupt=p.payload,
                    )
                if update:
                    st.update(update)
                trace.append(TraceEntry(step.name, step.effect, True, ""))
                self._emit(on_event, step.name, step.effect, True, "")
            current = plan.next_from(current, st)
            # Durability commit point: snapshot after every step. The effect
            # taxonomy means we only strictly need this after writes/model-call
            # steps; snapshotting after read-only steps too is a harmless, simpler
            # over-approximation (a resume just skips re-running cheap steps).
            if checkpointer is not None and current != END:
                checkpointer.save(
                    run_key,
                    {"cursor": current, "state": _public(st), "trace": _rows(trace)},
                )
            steps += 1
            if steps > self.max_steps:
                raise RuntimeError(
                    "plan %r exceeded %d steps (cyclic plan with no exit?); "
                    "raise config/project.json `runtimes.max_steps` if the plan "
                    "is meant to run longer" % (plan.name, self.max_steps)
                )
        if checkpointer is not None:
            checkpointer.clear(run_key)
        return RunResult(state=_public(st), trace=tuple(trace), status=COMPLETED)

    @staticmethod
    def _emit(on_event, name, effect, ran, reason):
        if on_event is not None:
            on_event(
                {"step": name, "effect": effect, "ran": ran, "skipped_reason": reason}
            )
