"""
title: Unit — run_make_target (refactor gate doer)
kind: tests
layer: n/a
summary: run_target shapes a structured pass/fail from an injected runner (no real subprocess), rejects unsafe target names, and forwards extra make args — so the refactor loop can gate a step deterministically.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import run_make_target as rmt  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "name", ["verify", "check", "typecheck-py", "site.data", "a1_b-c"]
)
def test_safe_targets_accepted(name):
    assert rmt.is_safe_target(name)


@pytest.mark.parametrize("name", ["", "a b", "a;rm -rf /", "$(x)", "a|b", "-x", ".x"])
def test_unsafe_targets_rejected(name):
    assert not rmt.is_safe_target(name)


def _fake(returncode, out="out"):
    calls = []

    def runner(cmd, cwd, timeout):
        calls.append((list(cmd), cwd, timeout))
        return returncode, out

    runner.calls = calls
    return runner


def test_run_target_shapes_a_passing_result():
    runner = _fake(0, "all green\n")
    res = rmt.run_target("verify", runner=runner)
    assert res == {
        "target": "verify",
        "ok": True,
        "returncode": 0,
        "output": "all green\n",
    }
    assert runner.calls[0][0] == ["make", "verify"]  # argv list, not a shell string


def test_run_target_shapes_a_failing_result():
    res = rmt.run_target("test", runner=_fake(1, "1 failed"))
    assert res["ok"] is False and res["returncode"] == 1


def test_run_target_forwards_dir_and_extra_make_args():
    runner = _fake(0)
    rmt.run_target(
        "verify", cwd="/somewhere", extra=["PY=.venv/bin/python"], runner=runner
    )
    cmd, cwd, _ = runner.calls[0]
    assert cmd == ["make", "verify", "PY=.venv/bin/python"]
    assert cwd == "/somewhere"


def test_run_target_rejects_an_unsafe_target():
    with pytest.raises(ValueError):
        rmt.run_target("a; rm -rf /", runner=_fake(0))


def test_main_returns_nonzero_when_the_gate_fails():
    # main() with an injected-free path: unsafe target short-circuits to exit 2.
    assert rmt.main(["bad;target"]) == 2
