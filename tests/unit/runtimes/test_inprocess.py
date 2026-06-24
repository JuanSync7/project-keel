"""
title: Unit — runtimes (default in-process engine + capabilities)
kind: tests
layer: backend
summary: Reference semantics — edge routing, dry-run guard, streaming, fan-out, durability, human-in-the-loop. No deps, no disk.
"""
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from runtimes import (  # noqa: E402
    COMPLETED,
    END,
    MODEL_CALL,
    PAUSED,
    READ_ONLY,
    WRITES,
    DEFAULT_RUNTIME,
    Edge,
    MemoryCheckpointer,
    Plan,
    Step,
    get_runtime,
    interrupt,
    list_runtimes,
)

pytestmark = pytest.mark.unit


def _rt():
    return get_runtime("inprocess")


def _branching_plan(calls):
    """gate -> build(writes) -> report -> fill(model) ; gate -> report when dirty."""
    def gate(s):
        calls.append("gate")
        return {"errors": s.get("inject_errors", 0)}

    def build(s):
        calls.append("build")
        return {"built": True}

    def report(s):
        calls.append("report")
        return {"gaps": ["x"] if not s.get("errors") else []}

    def fill(s):
        calls.append("fill")
        return {"filled": len(s.get("gaps", []))}

    return Plan(
        name="t", entry="gate",
        steps=(Step("gate", READ_ONLY, gate), Step("build", WRITES, build),
               Step("report", READ_ONLY, report), Step("fill", MODEL_CALL, fill)),
        edges=(Edge("gate", "build", when=lambda s: not s["errors"]),
               Edge("gate", "report"),
               Edge("build", "report"),
               Edge("report", "fill", when=lambda s: s.get("fix_gaps") and s.get("gaps")),
               Edge("report", END),
               Edge("fill", END)))


# --- registry + routing + dry-run guard ---------------------------------------

def test_registry_default_and_listing():
    assert DEFAULT_RUNTIME == "inprocess"
    assert list_runtimes() == ["inprocess", "langgraph"]   # registered != installed
    assert get_runtime().name == "inprocess"
    assert get_runtime("inprocess").name == "inprocess"


def test_unknown_runtime_raises_keyerror():
    with pytest.raises(KeyError):
        get_runtime("does-not-exist")


def test_dry_run_skips_gated_steps_and_never_calls_them():
    calls = []
    res = _rt().run(_branching_plan(calls), {"fix_gaps": True}, execute=False)
    assert "build" not in calls and "fill" not in calls
    assert calls == ["gate", "report"]
    assert res.state.get("built") is None and res.state.get("filled") is None
    assert res.status == COMPLETED
    skipped = {t.step: t.skipped_reason for t in res.trace if not t.ran}
    assert skipped == {"build": "dry-run", "fill": "dry-run"}


def test_execute_runs_full_clean_path():
    calls = []
    res = _rt().run(_branching_plan(calls), {"fix_gaps": True}, execute=True)
    assert calls == ["gate", "build", "report", "fill"]
    assert res.state["built"] is True and res.state["filled"] == 1
    assert all(t.ran for t in res.trace)


def test_conditional_edge_takes_dirty_branch():
    calls = []
    res = _rt().run(_branching_plan(calls),
                    {"inject_errors": 2, "fix_gaps": True}, execute=True)
    assert calls == ["gate", "report"]
    assert res.state["errors"] == 2 and res.state["gaps"] == []


def test_step_lookup_missing_raises():
    with pytest.raises(KeyError):
        _branching_plan([]).step("nope")


# --- visualization ------------------------------------------------------------

def test_to_mermaid_renders_the_graph():
    mer = _branching_plan([]).to_mermaid()
    assert mer.splitlines()[0] == "flowchart TD"
    assert "gate (read-only)" in mer and "fill (model-call)" in mer
    assert "_END" in mer            # terminal node
    assert "-.->" in mer            # at least one conditional (dashed) edge


# --- streaming ----------------------------------------------------------------

def test_on_event_streams_every_step_in_order():
    seen = []
    calls = []
    _rt().run(_branching_plan(calls), {"fix_gaps": True}, execute=True,
              on_event=lambda e: seen.append((e["step"], e["ran"])))
    assert seen == [("gate", True), ("build", True), ("report", True), ("fill", True)]


def test_on_event_reports_skipped_in_dry_run():
    seen = []
    _rt().run(_branching_plan([]), {"fix_gaps": True}, execute=False,
              on_event=lambda e: seen.append((e["step"], e["ran"], e["skipped_reason"])))
    assert ("build", False, "dry-run") in seen and ("fill", False, "dry-run") in seen


# --- fan-out (map step) -------------------------------------------------------

def _square_plan():
    def body(s):
        return {"sq": s["item"] ** 2}
    return Plan("f", "src",
                (Step("src", READ_ONLY, lambda s: {}),
                 Step("sq", WRITES, body, fan_out=lambda s: s["nums"])),
                (Edge("src", "sq"), Edge("sq", END)))


def test_fan_out_maps_in_item_order():
    res = _rt().run(_square_plan(), {"nums": [1, 2, 3, 4]}, execute=True)
    assert res.state["sq"] == [{"sq": 1}, {"sq": 4}, {"sq": 9}, {"sq": 16}]
    # a fan-out is ONE logical step in the trace
    assert [t.step for t in res.trace] == ["src", "sq"]


def test_fan_out_skipped_in_dry_run():
    res = _rt().run(_square_plan(), {"nums": [1, 2, 3]}, execute=False)
    assert "sq" not in res.state                      # body never ran
    assert any(t.step == "sq" and not t.ran for t in res.trace)


# --- durability (checkpoint + resume) -----------------------------------------

def _linear_plan(spy=None):
    def mk(key, val):
        def fn(s):
            if spy is not None:
                spy.append(key)
            return {key: val}
        return fn
    return Plan("d", "s1",
                (Step("s1", WRITES, mk("a", 1)),
                 Step("s2", WRITES, mk("b", 2)),
                 Step("s3", WRITES, mk("c", 3))),
                (Edge("s1", "s2"), Edge("s2", "s3"), Edge("s3", END)))


def test_checkpointer_writes_each_step_then_clears_on_completion():
    cp = MemoryCheckpointer()
    res = _rt().run(_linear_plan(), {}, execute=True, checkpointer=cp, run_key="k")
    assert res.state == {"a": 1, "b": 2, "c": 3} and res.status == COMPLETED
    assert cp.load("k") is None      # cleared once the run completed


def test_resume_after_a_crash_continues_from_the_checkpoint():
    spy = []
    plan = _linear_plan(spy)
    # make s2 fail exactly once
    boom = {"n": 0}
    original = plan.step("s2").run

    def flaky(s):
        boom["n"] += 1
        if boom["n"] == 1:
            raise RuntimeError("crash")
        return original(s)

    plan = Plan(plan.name, plan.entry,
                (plan.step("s1"), Step("s2", WRITES, flaky), plan.step("s3")),
                plan.edges)
    cp = MemoryCheckpointer()
    with pytest.raises(RuntimeError):
        _rt().run(plan, {}, execute=True, checkpointer=cp, run_key="k")
    snap = cp.load("k")
    assert snap is not None and snap["cursor"] == "s2"   # crashed before s2 committed
    res = _rt().run(plan, {}, execute=True, checkpointer=cp, run_key="k", resume=None)
    assert res.state == {"a": 1, "b": 2, "c": 3} and res.status == COMPLETED
    assert spy.count("a") == 1       # s1 (writes "a") NOT re-run on resume


def test_resume_without_checkpointer_is_an_error():
    with pytest.raises(RuntimeError):
        _rt().run(_linear_plan(), {}, execute=True, resume="x")


# --- human-in-the-loop (pause / resume) ---------------------------------------

def _approval_plan():
    def ask(s):
        decision = interrupt(s, {"question": "approve?", "gaps": s.get("gaps", [])})
        return {"approved": decision}
    return Plan("h", "prep",
                (Step("prep", READ_ONLY, lambda s: {"gaps": ["g1", "g2"]}),
                 Step("ask", MODEL_CALL, ask),
                 Step("act", WRITES, lambda s: {"acted": s["approved"]})),
                (Edge("prep", "ask"), Edge("ask", "act"), Edge("act", END)))


def test_interrupt_pauses_then_resumes_with_value():
    cp = MemoryCheckpointer()
    paused = _rt().run(_approval_plan(), {}, execute=True, checkpointer=cp, run_key="h")
    assert paused.status == PAUSED
    assert paused.interrupt == {"question": "approve?", "gaps": ["g1", "g2"]}
    assert "approved" not in paused.state           # the paused step did not commit
    resumed = _rt().run(_approval_plan(), {}, execute=True, checkpointer=cp,
                        run_key="h", resume="YES")
    assert resumed.status == COMPLETED
    assert resumed.state["approved"] == "YES" and resumed.state["acted"] == "YES"


def test_interrupt_outside_a_run_is_an_error():
    with pytest.raises(RuntimeError):
        interrupt({}, {"q": "x"})
