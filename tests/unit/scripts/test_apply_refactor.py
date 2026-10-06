"""
title: Unit — apply_refactor (edit application and its default gate)
kind: tests
layer: n/a
summary: apply_one applies a search/replace only when the target text occurs EXACTLY once, so a refactor edit is unambiguous — zero or multiple matches raise before anything is written. The default gate is scripts/run_make_target.py, so a refused gate (a target labelled wider than a gate may run) and a gate that changed the tree are both red and roll the edit back, and so is a gate that raises any exception.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import apply_refactor as ar  # noqa: E402

pytestmark = pytest.mark.unit


def test_apply_one_replaces_a_unique_match():
    assert ar.apply_one("a = 1\nb = 2\n", "b = 2", "b = 3") == "a = 1\nb = 3\n"


def test_apply_one_raises_when_not_present():
    with pytest.raises(ar.RefactorError):
        ar.apply_one("x = 1\n", "nope", "y")


def test_apply_one_raises_on_ambiguous_match():
    with pytest.raises(ar.RefactorError):
        ar.apply_one("pass\npass\n", "pass", "return")


def test_apply_one_preserves_the_rest_of_the_text():
    src = "class C:\n    pass\n"
    out = ar.apply_one(src, "    pass", "    __slots__ = ()")
    assert out == "class C:\n    __slots__ = ()\n"


# --- the default gate is the read-only gate runner ------------------------------


def _spec(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("keep = 1\n", encoding="utf-8")
    return f, {"edits": [{"file": "m.py", "find": "keep = 1", "replace": "keep = 2"}]}


def _fake_run_target(result):
    calls = []

    def run_target(
        target, cwd=None, timeout=1800, extra=None, runner=None, snapshot=None
    ):
        calls.append((target, cwd, timeout))
        return dict(result, target=target)

    run_target.calls = calls
    return run_target


def test_the_default_gate_goes_through_run_make_target(tmp_path, monkeypatch):
    f, spec = _spec(tmp_path)
    fake = _fake_run_target(
        {
            "ok": True,
            "returncode": 0,
            "output": "green\n",
            "changed": [],
            "refused": None,
        }
    )
    monkeypatch.setattr(ar.run_make_target, "run_target", fake)
    res = ar.apply_and_gate(spec, str(tmp_path), gate="check", timeout=7)
    assert fake.calls == [("check", str(tmp_path), 7)]
    assert res["applied"] is True and f.read_text(encoding="utf-8") == "keep = 2\n"


def test_a_refused_gate_is_red_and_rolls_back(tmp_path, monkeypatch):
    f, spec = _spec(tmp_path)
    fake = _fake_run_target(
        {
            "ok": False,
            "returncode": None,
            "output": "run_make_target: refused: `make fmt` is labelled [tree]",
            "changed": [],
            "refused": "`make fmt` is labelled [tree]",
        }
    )
    monkeypatch.setattr(ar.run_make_target, "run_target", fake)
    res = ar.apply_and_gate(spec, str(tmp_path), gate="fmt")
    assert res["rolled_back"] is True and res["applied"] is False
    assert "[tree]" in res["gate_output"]
    assert f.read_text(encoding="utf-8") == "keep = 1\n"


def test_a_gate_that_dirtied_the_tree_is_red_and_names_the_paths(tmp_path, monkeypatch):
    f, spec = _spec(tmp_path)
    fake = _fake_run_target(
        {
            "ok": False,
            "returncode": 0,
            "output": "ok\n",
            "changed": ["wiki/x.json"],
            "refused": None,
        }
    )
    monkeypatch.setattr(ar.run_make_target, "run_target", fake)
    res = ar.apply_and_gate(spec, str(tmp_path), gate="check")
    assert res["rolled_back"] is True and "wiki/x.json" in res["gate_output"]
    assert f.read_text(encoding="utf-8") == "keep = 1\n"


def _raise(exc):
    def gate_runner(gate, cwd, timeout):
        raise exc

    return gate_runner


@pytest.mark.parametrize(
    "exc",
    [
        ar.run_make_target.child_env.ChildEnvError("child_env.names: bad"),
        KeyError("result"),
        RuntimeError("gate crashed"),
    ],
    ids=["child-env-error", "key-error", "runtime-error"],
)
def test_a_gate_that_raises_anything_is_red_and_rolls_back(tmp_path, exc):
    """The rollback contract is "a non-returning gate never leaves an ungated
    write behind", so it cannot depend on which exception type the gate raised."""
    f, spec = _spec(tmp_path)
    res = ar.apply_and_gate(spec, str(tmp_path), gate="check", gate_runner=_raise(exc))
    assert res["rolled_back"] is True and res["applied"] is False
    assert type(exc).__name__ in res["gate_output"]
    assert f.read_text(encoding="utf-8") == "keep = 1\n"
