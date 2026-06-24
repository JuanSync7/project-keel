"""
title: Unit — runtime conformance (inprocess == langgraph)
kind: tests
layer: backend
summary: Pins the LangGraph adapter as execution-only — identical state, trace, status, fan-out order, durability, and human-in-the-loop across engines.
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
    Edge,
    MemoryCheckpointer,
    Plan,
    Step,
    get_runtime,
    interrupt,
)

pytestmark = pytest.mark.unit

# The LangGraph engine is an optional extra (pip install -e '.[langgraph]').
# Without it, the inprocess tests still run; this whole module skips.
pytest.importorskip("langgraph")

ENGINES = ("inprocess", "langgraph")


# --- branching + dry-run guard ------------------------------------------------

def _branching(calls):
    def gate(s):
        calls.append("gate")
        return {"errors": s.get("inject_errors", 0)}

    def build(s):
        calls.append("build")
        return {"built": True}

    def report(s):
        calls.append("report")
        return {"gaps": ["a", "b"] if not s.get("errors") else []}

    def fill(s):
        calls.append("fill")
        return {"filled": len(s.get("gaps", []))}

    return Plan("conf", "gate",
                (Step("gate", READ_ONLY, gate), Step("build", WRITES, build),
                 Step("report", READ_ONLY, report), Step("fill", MODEL_CALL, fill)),
                (Edge("gate", "build", when=lambda s: not s["errors"]),
                 Edge("gate", "report"), Edge("build", "report"),
                 Edge("report", "fill", when=lambda s: s.get("fix_gaps") and s.get("gaps")),
                 Edge("report", END), Edge("fill", END)))


_SCENARIOS = [
    ("dry_fix", {"fix_gaps": True}, False),
    ("exec_fix", {"fix_gaps": True}, True),
    ("exec_dirty", {"inject_errors": 3, "fix_gaps": True}, True),
    ("exec_nofix", {}, True),
    ("dry_nofix", {}, False),
]


def _run(engine, init, execute):
    calls = []
    res = get_runtime(engine).run(_branching(calls), dict(init), execute=execute)
    trace = [(t.step, t.ran, t.skipped_reason) for t in res.trace]
    return res.state, trace, res.status, calls


@pytest.mark.parametrize("label,init,execute", _SCENARIOS, ids=[s[0] for s in _SCENARIOS])
def test_branching_equivalence(label, init, execute):
    a = _run("inprocess", init, execute)
    b = _run("langgraph", init, execute)
    assert a == b   # state, trace, status, and which bodies ran — all identical


def test_dry_run_guard_holds_on_both_engines():
    for engine in ENGINES:
        _, _, _, calls = _run(engine, {"fix_gaps": True}, False)
        assert "build" not in calls and "fill" not in calls, engine


# --- fan-out (map): same ordered result on both engines -----------------------

def _fan_plan():
    return Plan("f", "src",
                (Step("src", READ_ONLY, lambda s: {}),
                 Step("sq", WRITES, lambda s: {"sq": s["item"] ** 2},
                      fan_out=lambda s: s["nums"])),
                (Edge("src", "sq"), Edge("sq", END)))


def test_fan_out_equivalence_ordered():
    nums = [3, 1, 4, 1, 5, 9, 2, 6]
    a = get_runtime("inprocess").run(_fan_plan(), {"nums": nums}, execute=True)
    b = get_runtime("langgraph").run(_fan_plan(), {"nums": nums}, execute=True)
    # LangGraph Send runs items concurrently; results must still match item order
    assert a.state["sq"] == b.state["sq"] == [{"sq": n ** 2} for n in nums]
    assert [t.step for t in a.trace] == [t.step for t in b.trace] == ["src", "sq"]


# --- streaming: same events on both engines -----------------------------------

def test_streaming_equivalence():
    out = {}
    for engine in ENGINES:
        seen = []
        get_runtime(engine).run(_branching([]), {"fix_gaps": True}, execute=True,
                                on_event=lambda e: seen.append((e["step"], e["ran"])))
        out[engine] = seen
    assert out["inprocess"] == out["langgraph"]


# --- durability: full run completes + clears on both --------------------------

def test_durable_run_equivalence():
    def mk(k, v):
        return lambda s: {k: v}
    plan = Plan("d", "s1",
                (Step("s1", WRITES, mk("a", 1)), Step("s2", WRITES, mk("b", 2)),
                 Step("s3", WRITES, mk("c", 3))),
                (Edge("s1", "s2"), Edge("s2", "s3"), Edge("s3", END)))
    for engine in ENGINES:
        cp = MemoryCheckpointer()
        res = get_runtime(engine).run(plan, {}, execute=True, checkpointer=cp, run_key="k")
        assert res.state == {"a": 1, "b": 2, "c": 3} and res.status == COMPLETED
        assert cp.load("k") is None


# --- human-in-the-loop: same pause payload, same resumed state ----------------

def _approval_plan():
    def ask(s):
        return {"approved": interrupt(s, {"q": "approve?", "gaps": s.get("gaps", [])})}
    return Plan("h", "prep",
                (Step("prep", READ_ONLY, lambda s: {"gaps": ["g1", "g2"]}),
                 Step("ask", MODEL_CALL, ask),
                 Step("act", WRITES, lambda s: {"acted": s["approved"]})),
                (Edge("prep", "ask"), Edge("ask", "act"), Edge("act", END)))


def test_human_in_the_loop_equivalence():
    paused, resumed = {}, {}
    for engine in ENGINES:
        cp = MemoryCheckpointer()
        p = get_runtime(engine).run(_approval_plan(), {}, execute=True,
                                    checkpointer=cp, run_key="h")
        r = get_runtime(engine).run(_approval_plan(), {}, execute=True,
                                    checkpointer=cp, run_key="h", resume="OK")
        paused[engine] = (p.status, p.interrupt)
        resumed[engine] = (r.status, r.state)
    assert paused["inprocess"] == paused["langgraph"] == (PAUSED, {"q": "approve?", "gaps": ["g1", "g2"]})
    assert resumed["inprocess"] == resumed["langgraph"]
    assert resumed["inprocess"][1]["approved"] == "OK"
