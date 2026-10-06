"""
title: Unit — run_make_target (the read-only gate runner)
kind: tests
layer: n/a
summary: run_target runs a make target only when its effect label, closed over its prerequisites, falls inside config/project.json `make_targets.gate_effects`; it refuses an unknown, unlabelled or wider target, an extra argument that is not a NAME=VALUE variable, a variable outside `make_targets.gate_vars` (make's control variables, the guard and the unattended variables among them), a value that is not one path-like word, a tree without git and a project without the policy, all without calling the runner. It passes the gate-runner variable last, so the Makefile's WRITE_GUARD refuses whatever the caller supplied, and fails a green run that changed the tree, naming the paths. The runner and the snapshot are injected, so no make or git process runs here.
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import run_make_target as rmt  # noqa: E402

pytestmark = pytest.mark.unit

_POLICY = {
    "unattended_vars": ["CI", "RALPH"],
    "gate_runner_var": "RALPH",
    "gate_effects": ["local", "read"],
    "write_shapes": [],
    "area_dir": None,
    "effect_proof_skip": {},
    "gate_vars": ["PY"],
}
_MAKEFILE = (
    "check: ## [local] Validate\n\tc\n"
    "cloud: ## [read] Read a service\n\tr\n"
    "fmt: ## [tree] Format\n\tf\n"
    "verify: check fmt ## [tree] Both\n"
    "sneaky: fmt ## [local] Claims local\n"
    "plain:\n\tp\n"
)


@pytest.fixture
def proj(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.json").write_text(
        json.dumps({"make_targets": _POLICY}), encoding="utf-8"
    )
    (tmp_path / "Makefile").write_text(_MAKEFILE, encoding="utf-8")
    return tmp_path


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


def _snaps(*states):
    """A snapshot seam returning each state in turn (before, after)."""
    seq = list(states)

    def snapshot(root):
        return seq.pop(0)

    snapshot.left = seq
    return snapshot


def _never(root):
    raise AssertionError("a refusal must not snapshot the tree")


def test_a_read_only_target_runs_with_the_loop_variable_last(proj):
    runner = _fake(0, "all green\n")
    res = rmt.run_target(
        "check",
        cwd=str(proj),
        extra=["PY=.venv/bin/python"],
        runner=runner,
        snapshot=_snaps({}, {}),
    )
    assert res["ok"] is True and res["returncode"] == 0
    assert res["effects"] == ["local"] and res["changed"] == []
    assert res["refused"] is None and res["output"] == "all green\n"
    cmd, cwd, _ = runner.calls[0]
    assert cmd == ["make", "check", "PY=.venv/bin/python", "RALPH=1"]
    assert cwd == str(proj)


def test_the_gate_runner_variable_comes_from_config(proj):
    policy = dict(_POLICY, unattended_vars=["CI", "LOOP"], gate_runner_var="LOOP")
    (proj / "config" / "project.json").write_text(
        json.dumps({"make_targets": policy}), encoding="utf-8"
    )
    runner = _fake(0)
    rmt.run_target("check", cwd=str(proj), runner=runner, snapshot=_snaps({}, {}))
    assert runner.calls[0][0] == ["make", "check", "LOOP=1"]


def test_a_read_target_runs_when_the_policy_allows_read(proj):
    runner = _fake(0)
    res = rmt.run_target("cloud", cwd=str(proj), runner=runner, snapshot=_snaps({}, {}))
    assert res["ok"] is True and res["effects"] == ["read"]


def test_a_failing_target_is_red(proj):
    res = rmt.run_target(
        "check", cwd=str(proj), runner=_fake(1, "1 failed"), snapshot=_snaps({}, {})
    )
    assert res["ok"] is False and res["returncode"] == 1 and res["refused"] is None


def test_a_green_run_that_changed_the_tree_is_red_and_names_the_paths(proj):
    before = {"a.py": "sha:1", "gone.txt": "sha:2"}
    after = {"a.py": "sha:9", "new.txt": "sha:3"}
    res = rmt.run_target(
        "check", cwd=str(proj), runner=_fake(0), snapshot=_snaps(before, after)
    )
    assert res["ok"] is False and res["returncode"] == 0
    assert res["changed"] == ["a.py", "gone.txt", "new.txt"]
    assert "a.py" in res["output"] and "changed the tree" in res["output"]


@pytest.mark.parametrize(
    "target, expect",
    [
        ("fmt", "[tree]"),
        ("verify", "[tree]"),
        ("sneaky", "tree"),
        ("plain", "no effect label"),
        ("nonesuch", "no rule"),
    ],
    ids=["tree", "composite", "lying-composite", "unlabelled", "unknown"],
)
def test_a_target_outside_the_gate_effects_is_refused_unrun(proj, target, expect):
    runner = _fake(0)
    res = rmt.run_target(target, cwd=str(proj), runner=runner, snapshot=_never)
    assert res["ok"] is False and res["returncode"] is None
    assert expect in res["refused"], res["refused"]
    assert runner.calls == []


@pytest.mark.parametrize(
    "arg", ["-f", "--file=other.mk", "-C", "check", "1BAD=x", "-e"]
)
def test_an_extra_argument_that_is_not_a_variable_is_refused(proj, arg):
    runner = _fake(0)
    res = rmt.run_target(
        "check", cwd=str(proj), extra=[arg], runner=runner, snapshot=_never
    )
    assert res["refused"] and "NAME=VALUE" in res["refused"], res
    assert runner.calls == []


@pytest.mark.parametrize(
    "arg",
    [
        "RALPH=",  # unsets the gate-runner variable
        "CI=",  # an unattended variable
        "WRITE_GUARD=",  # empties the guard itself
        "MAKEFILES=/tmp/x.mk",  # loads a makefile whose labels nobody read
        "MAKEFLAGS=-f evil.mk",  # flags by another name
        "MFLAGS=-i",
        "SHELL=/tmp/evil.sh",
        "FOO=1",  # any name the policy does not list
    ],
)
def test_a_variable_outside_gate_vars_is_refused(proj, arg):
    runner = _fake(0)
    res = rmt.run_target(
        "check", cwd=str(proj), extra=[arg], runner=runner, snapshot=_never
    )
    assert res["refused"] and "gate_vars" in res["refused"], res
    assert arg.split("=")[0] in res["refused"], res
    assert runner.calls == []


@pytest.mark.parametrize(
    "value",
    [
        "make deploy-apply RALPH= CI= ; true",  # measured: ran a [write] target
        "x;true",
        "$(shell touch y)",
        "${X}",
        "a b",
        "a|b",
        "a&&b",
        "`id`",
        "'q'",
        "a#b",
        "x\ny",
    ],
)
def test_a_gate_variable_whose_value_is_not_one_plain_word_is_refused(proj, value):
    """A recipe expands the value into a shell line, so a value with spaces, make
    or shell syntax could run a target whose label nobody read."""
    runner = _fake(0)
    res = rmt.run_target(
        "check", cwd=str(proj), extra=["PY=" + value], runner=runner, snapshot=_never
    )
    assert res["refused"] and "PY" in res["refused"], res
    assert runner.calls == []


@pytest.mark.parametrize(
    "value", ["", ".venv/bin/python", "/opt/py-3.12/bin/python3.12", "C:/x+y@z,w~1"]
)
def test_a_gate_variable_with_a_path_like_value_runs(proj, value):
    runner = _fake(0)
    res = rmt.run_target(
        "check",
        cwd=str(proj),
        extra=["PY=" + value],
        runner=runner,
        snapshot=_snaps({}, {}),
    )
    assert res["refused"] is None and res["ok"] is True, res
    assert runner.calls[0][0] == ["make", "check", "PY=" + value, "RALPH=1"]


def test_without_git_the_run_is_refused(proj):
    def no_git(root):
        raise rmt.NoGitError("not a git work tree")

    runner = _fake(0)
    res = rmt.run_target("check", cwd=str(proj), runner=runner, snapshot=no_git)
    assert res["refused"].startswith("cannot prove a read-only run without git")
    assert runner.calls == []


@pytest.mark.parametrize(
    "manifest",
    [{"name": "x"}, {"make_targets": dict(_POLICY, gate_effects=["read"])}, None],
    ids=["missing", "invalid", "no-manifest"],
)
def test_without_a_valid_policy_the_run_is_refused(proj, manifest):
    path = proj / "config" / "project.json"
    if manifest is None:
        path.unlink()
    else:
        path.write_text(json.dumps(manifest), encoding="utf-8")
    runner = _fake(0)
    res = rmt.run_target("check", cwd=str(proj), runner=runner, snapshot=_never)
    assert res["refused"] and "make_targets" in res["refused"], res
    assert runner.calls == []


def test_a_timeout_is_red_and_still_checks_the_tree(proj):
    import subprocess

    def hangs(cmd, cwd, timeout):
        raise subprocess.TimeoutExpired(cmd, timeout)

    snap = _snaps({}, {"half.txt": "sha:1"})
    res = rmt.run_target("check", cwd=str(proj), runner=hangs, snapshot=snap)
    assert res["ok"] is False and res["returncode"] is None
    assert res["changed"] == ["half.txt"] and "did not complete" in res["output"]
    assert snap.left == []


def test_run_target_rejects_an_unsafe_target_name():
    with pytest.raises(ValueError):
        rmt.run_target("a; rm -rf /", runner=_fake(0))


def test_main_exits_2_on_an_unsafe_name():
    assert rmt.main(["bad;target"]) == 2


def test_main_exits_2_and_still_emits_json_on_a_refusal(proj, capsys):
    assert rmt.main(["fmt", "--json", "--dir", str(proj)]) == 2
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and "[tree]" in out["refused"]
