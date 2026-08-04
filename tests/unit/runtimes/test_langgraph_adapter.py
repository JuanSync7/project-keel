"""
title: Unit — LangGraph adapter pause signal
kind: tests
layer: backend
summary: Pins the gate-tier `exception-chaining` practice where the adapter converts a caller's Pause into its private abort signal — the cause must survive.
"""
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from runtimes import READ_ONLY, Pause, Step, get_runtime, interrupt  # noqa: E402

pytestmark = pytest.mark.unit

# No `importorskip("langgraph")` on purpose: the adapter imports LangGraph
# lazily inside `run()`, and the node wrapper exercised here is pure Python.
# This test must therefore hold on a default install too.

_PAYLOAD = {"q": "approve?", "gaps": ["g1"]}


def _fire_pause_node():
    """Drive the adapter's node wrapper through a human-in-the-loop pause.

    Returns ``(raised, holder)``. The pause -> internal-signal conversion is the
    one `raise` inside an `except` clause in this adapter, and it is unreachable
    from `Runtime.run` (the signal is always swallowed into a PAUSED RunResult),
    so the wrapper is driven directly — via the *public* runtime object.
    """
    holder = {}
    step = Step(name="ask", effect=READ_ONLY,
                run=lambda state: interrupt(state, _PAYLOAD))
    node = get_runtime("langgraph")._node(
        None, step, None, "run", None, {"has": False, "value": None}, holder)
    with pytest.raises(Exception) as excinfo:  # noqa: PT011 - signal type is private
        node({"bag": {"_execute": True}})
    return excinfo.value, holder


def test_the_pause_signal_keeps_the_pause_as_its_explicit_cause():
    """`raise ... from p`: the Pause that triggered the abort stays attached.

    Without it the signal escaping (holder never set — the bug path this
    diagnostic exists for) reaches the operator stripped of the step that
    paused, which is exactly what the `exception-chaining` practice forbids.
    """
    raised, _ = _fire_pause_node()
    assert isinstance(raised.__cause__, Pause), (
        "the adapter's pause signal dropped its cause: __cause__=%r "
        "(exception-chaining is a gate-tier practice; use `raise ... from p`)"
        % (raised.__cause__,))
    assert raised.__cause__.payload == _PAYLOAD


def test_the_pause_signal_still_hands_the_pause_to_the_caller():
    """Non-regression: chaining must not disturb the PAUSED hand-off."""
    _, holder = _fire_pause_node()
    assert holder["paused"] is True
    assert holder["payload"] == _PAYLOAD
    assert holder["cursor"] == "ask"
