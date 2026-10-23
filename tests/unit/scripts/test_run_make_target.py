"""
title: Unit — run_make_target (the read-only gate runner)
kind: tests
layer: n/a
summary: run_target runs a make target only when its effect label, closed over its prerequisites, falls inside config/project.json `make_targets.gate_effects`; it refuses an unknown, unlabelled or wider target, an extra argument that is not a NAME=VALUE variable, a variable outside `make_targets.gate_vars` (make's control variables, the guard and the unattended variables among them), a value that is not one path-like word, a tree without git and a project without the policy, all without calling the runner. It passes the gate-runner variable last, so the Makefile's WRITE_GUARD refuses whatever the caller supplied, and fails a green run that changed the tree, naming the paths. A `make_targets.gate_vars` value found in the runner's own environment is forwarded on make's command line under the same one-word rule, an explicit one wins, and a bad one is refused before make runs. make and git get the allowlisted environment from scripts/child_env.py, never the runner's own. An allowlist that cannot be built, or that would copy a gate variable carrying a credential, is a refusal before anything runs and before any message could quote the value; a gate value, explicit or forwarded, that carries a credential is refused by name even when opted in, and no refusal quotes a value; and a ChildEnvError during the run or a tree that cannot be re-read afterwards is red, never a traceback. The runner and the snapshot are injected for those cases, so no make or git process runs in them. The default runner's own cases put a fake `make` (a short Python script) first on PATH that starts a grandchild, and prove that a timeout, a KeyboardInterrupt and a SIGTERM to the runner end the whole group, that an ignored SIGTERM is followed by SIGKILL after the grace, that a SIGTERM handler gets that grace, and that a process left behind after make exits is ended, named by pid and command, and turns a green make red while a failing make keeps its own status; each polls with a bound and kills only the pids it started. Further cases prove that the stop and the leak count reach every process in make's session, a process that left make's group for one of its own (GNU `timeout`) included; that output a process outside the session still holds makes the run red, naming it, without signalling it; that no signal goes to an id once make is reaped (an os.killpg recorder, in a child interpreter where a SIGTERM is sent at the moment under test) and that make stays unreaped while its leftovers are signalled; that a Ctrl-C or SIGTERM landing inside Popen still ends make; that a background job ending just after make is not a leak; that under an ignored SIGCHLD a stop just after make exits signals only held ids, a green make keeps its status, a leftover is ended, and the caller's SIGCHLD is put back, while off the main thread the run is refused before make starts; that a make another waiter reaped is red at once, a stop after that reap sends nothing, and its leftovers are named as not ended (settled first), or said to be unlisted and possibly still running without /proc; that output held by holders the runner cannot list is still an unlisted escape; that a SIGTERM after a timed-out make is reaped sends nothing; and that a runner killed with SIGKILL leaves none of make's tree running, through the watcher scripts/resource_limits.py starts beside make. The time limit and grace come from config/project.json `make_targets` through scripts/config_loader.py, the loader's default when the key is absent, a bad value or one past its row's upper bound is CONFIG or a refusal naming the key, `--timeout` overrides the configured limit within the same bound, and the configured grace outlasts `e2e.server.stop_timeout_s`.
"""

import base64
import contextlib
import io
import json
import os
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
    "effect_proof_kept_dirs": {"XDG_CONFIG_HOME": ".config"},
    "write_shape_exempt": {},
    "empty_test_selections": {},
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


@pytest.fixture(autouse=True)
def _no_gate_vars_in_env(monkeypatch):
    """`make PY=... test` exports PY to this suite, and the runner forwards a gate
    variable it finds in its environment; the exact-argv assertions below are
    about what the caller passed, so the inherited value is removed."""
    for name in _POLICY["gate_vars"]:
        monkeypatch.delenv(name, raising=False)


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


def test_a_git_that_ran_and_failed_is_refused_naming_its_status_before_make(proj):
    """A failed git is not "no git": the refusal says git could not list the
    tree and carries git's own status and stderr, and make never starts."""

    def failed(root):
        raise rmt.GitFailedError(128, "fatal: bad object HEAD")

    runner = _fake(0)
    res = rmt.run_target("check", cwd=str(proj), runner=runner, snapshot=failed)
    assert res["ok"] is False and res["returncode"] is None, res
    assert res["refused"].startswith("cannot prove a read-only run: git could not")
    assert "without git" not in res["refused"], res
    assert "git exited 128" in res["refused"], res
    assert "bad object HEAD" in res["refused"], res
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


def test_the_manifest_is_read_through_the_config_loader(proj):
    """scripts/config_loader.py `read` is the one parse, so a key written twice
    is a refusal naming it, never whichever value came last."""
    text = json.dumps({"make_targets": _POLICY})
    (proj / "config" / "project.json").write_text(
        text[:-1] + ', "make_targets": {}}', encoding="utf-8"
    )
    runner = _fake(0)
    res = rmt.run_target("check", cwd=str(proj), runner=runner, snapshot=_never)
    assert res["refused"] and "`make_targets` appears twice" in res["refused"], res
    assert "make_targets policy is unknown" in res["refused"], res
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


# --- the environment the runner hands on ---------------------------------------------


def test_a_gate_variable_in_the_parent_environment_is_forwarded_on_the_command_line(
    proj, monkeypatch
):
    """An agent calls the runner without `--make-arg PY`; the PY its own make
    started it with reaches it only through the environment, which the child's
    allowlist would otherwise leave to make's `python3` default."""
    monkeypatch.setenv("PY", "/opt/py/bin/python3")
    runner = _fake(0)
    rmt.run_target("check", cwd=str(proj), runner=runner, snapshot=_snaps({}, {}))
    assert runner.calls[0][0] == ["make", "check", "PY=/opt/py/bin/python3", "RALPH=1"]


def test_an_explicit_gate_variable_wins_over_the_environment(proj, monkeypatch):
    monkeypatch.setenv("PY", "/b")
    runner = _fake(0)
    rmt.run_target(
        "check", cwd=str(proj), extra=["PY=/a"], runner=runner, snapshot=_snaps({}, {})
    )
    assert runner.calls[0][0] == ["make", "check", "PY=/a", "RALPH=1"]


def test_a_gate_variable_in_the_environment_that_is_not_one_word_is_refused(
    proj, monkeypatch
):
    monkeypatch.setenv("PY", "python3 ; make deploy-apply RALPH=")
    runner = _fake(0)
    res = rmt.run_target("check", cwd=str(proj), runner=runner, snapshot=_never)
    assert res["refused"] and "PY" in res["refused"], res
    assert "environment" in res["refused"] and res["returncode"] is None, res
    assert runner.calls == []


@pytest.mark.parametrize(
    "value",
    ["http://alice:s3cr3t-pw@x y", "http://alice:s3cr3t-pw@x"],
    ids=["not-one-word", "one-word"],
)
def test_a_credentialed_gate_variable_is_refused_before_any_message_could_echo_it(
    proj, monkeypatch, value
):
    """PY is a gate variable, so the allowlist copies it. A value carrying a
    password is refused by name before the one-word rule could quote it back or
    the forwarding could put it on make's command line."""
    monkeypatch.setenv("PY", value)
    runner = _fake(0)
    res = rmt.run_target("check", cwd=str(proj), runner=runner, snapshot=_never)
    assert res["ok"] is False and res["refused"], res
    assert "PY" in res["refused"], res
    assert "child_env.credentialed_values" in res["refused"], res
    assert "s3cr3t-pw" not in json.dumps(res), "the refusal carries the value"
    assert runner.calls == []


_CREDENTIALED_GATE_VALUES = [
    "http://alice:s3cr3t-pw@x y",
    "http://alice:s3cr3t-pw@x",
    "alice:s3cr3t-pw@x:1",
]


@pytest.mark.parametrize("value", _CREDENTIALED_GATE_VALUES)
def test_an_explicit_gate_variable_carrying_a_credential_is_refused_by_name(
    proj, value
):
    """An explicit --make-arg value is the caller's, but make's command line
    reaches every recipe through MAKEFLAGS and any `ps`; it is judged by the rule
    child_env applies, refused by name, and never quoted back."""
    runner = _fake(0)
    res = rmt.run_target(
        "check", cwd=str(proj), extra=["PY=" + value], runner=runner, snapshot=_never
    )
    assert res["refused"] and "`PY`" in res["refused"], res
    assert "s3cr3t-pw" not in json.dumps(res), "the refusal carries the value"
    assert runner.calls == []


def test_an_opted_in_gate_variable_still_never_reaches_makes_command_line(
    proj, monkeypatch
):
    """child_env.credentialed_values lets a child's environment carry a
    credential; it does not put one on make's command line. The allowlist is
    stubbed as if PY were opted in, so only the forwarding rule is under test."""
    monkeypatch.setattr(rmt.child_env, "build_child_env", lambda **kw: {})
    monkeypatch.setenv("PY", "http://alice:s3cr3t-pw@x")
    runner = _fake(0)
    res = rmt.run_target("check", cwd=str(proj), runner=runner, snapshot=_never)
    assert res["refused"] and "PY" in res["refused"], res
    assert "s3cr3t-pw" not in json.dumps(res), "the refusal carries the value"
    assert runner.calls == []


def _segment(raw):
    """One base64url JWT segment, unpadded, as a token issuer writes it."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


# A synthetic JWT, assembled at import: header, claims, a fake signature.
_JWT = ".".join(
    [_segment(b'{"alg":"HS256"}'), _segment(b'{"sub":"1234"}'), "Sf1Kx" * 4]
)

# Assembled from parts so no scanner reads this file as holding a credential.
_SHAPED_GATE_VALUES = {
    "opaque-token": "tok_" + "aB3" * 12,
    "json-web-token": _JWT,
}


@pytest.mark.parametrize("label", sorted(_SHAPED_GATE_VALUES))
@pytest.mark.parametrize("source", ["explicit", "environment"])
def test_a_gate_value_matching_a_credential_pattern_is_refused_naming_only_the_variable(
    proj, monkeypatch, source, label
):
    """A one-word value is let through by the gate grammar, so a token shaped
    like keel's credential_value_patterns would ride make's command line; it is
    refused naming PY and the label, and no 12-character run of it survives."""
    value = _SHAPED_GATE_VALUES[label]
    extra = []
    if source == "explicit":
        extra = ["PY=" + value]
    else:
        monkeypatch.setenv("PY", value)
    runner = _fake(0)
    res = rmt.run_target(
        "check", cwd=str(proj), extra=extra, runner=runner, snapshot=_never
    )
    assert res["refused"] and "PY" in res["refused"], res
    assert label in res["refused"], res
    text = json.dumps(res)
    assert not [
        value[i : i + 12] for i in range(len(value) - 11) if value[i : i + 12] in text
    ]
    assert runner.calls == []


@pytest.mark.parametrize("source", ["explicit", "environment"])
def test_a_value_that_is_not_one_word_is_refused_without_being_quoted(
    proj, monkeypatch, source
):
    """A credential in a form no rule recognises (a bare token after a space)
    still never reaches the refusal: the one-word rule names the variable only."""
    value = "python3 tok-UNQUOTED"
    extra = []
    if source == "explicit":
        extra = ["PY=" + value]
    else:
        monkeypatch.setenv("PY", value)
    runner = _fake(0)
    res = rmt.run_target(
        "check", cwd=str(proj), extra=extra, runner=runner, snapshot=_never
    )
    assert res["refused"] and "PY" in res["refused"], res
    assert "UNQUOTED" not in json.dumps(res), res
    assert runner.calls == []


def test_make_and_git_run_with_the_allowlisted_environment(proj, monkeypatch):
    monkeypatch.setenv("KEEL_PLANTED_SECRET", "s")
    monkeypatch.setenv("GITHUB_TOKEN", "g")
    seen = []

    class _Done:
        returncode = 0
        stdout = b""
        stderr = b""

    class _Started(_Done):
        pid = -1  # never signalled: os.killpg is replaced below
        stdin = None
        stderr = None

        def __init__(self, cmd, **kw):
            seen.append(kw)
            # A real pipe whose writer is already closed: make printed nothing.
            read_end, write_end = os.pipe()
            os.close(write_end)
            self.stdout = os.fdopen(read_end, "rb")

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

    def record(cmd, **kw):
        seen.append(kw)
        return _Done()

    def no_group(pgid, sig):
        raise ProcessLookupError

    monkeypatch.setattr(rmt.subprocess, "run", record)
    # The stand-in make has exited 0 by poll: the runner reads it that way.
    monkeypatch.delattr(rmt.os, "waitid", raising=False)
    monkeypatch.setattr(rmt.subprocess, "Popen", _Started)
    monkeypatch.setattr(rmt.os, "killpg", no_group)
    rmt._default_runner(["make", "x"], str(proj), 5, grace=1)
    rmt._git(str(proj), "status")
    # make, the watcher scripts/resource_limits.py starts beside it, then git.
    assert len(seen) == 3
    assert seen[0].get("start_new_session") is True, seen[0]
    for kw in seen:
        assert "env" in kw, kw
        assert (
            "KEEL_PLANTED_SECRET" not in kw["env"] and "GITHUB_TOKEN" not in kw["env"]
        )
        assert kw["env"].get("PATH") == os.environ["PATH"]


def _broken_allowlist(**_kw):
    raise rmt.child_env.ChildEnvError("config/project.json: child_env.names: bad")


def test_a_broken_child_env_allowlist_is_a_refusal_before_anything_runs(
    proj, monkeypatch
):
    monkeypatch.setattr(rmt.child_env, "build_child_env", _broken_allowlist)
    runner = _fake(0)
    res = rmt.run_target("check", cwd=str(proj), runner=runner, snapshot=_never)
    assert res["ok"] is False and res["returncode"] is None, res
    assert res["refused"] and "child_env.names" in res["refused"], res
    assert runner.calls == []


def test_a_child_env_error_during_the_run_is_red_and_still_checks_the_tree(proj):
    def breaks(cmd, cwd, timeout):
        raise rmt.child_env.ChildEnvError("child_env.names: bad")

    snap = _snaps({}, {})
    res = rmt.run_target("check", cwd=str(proj), runner=breaks, snapshot=snap)
    assert res["ok"] is False and res["returncode"] is None, res
    assert "did not complete" in res["output"] and "child_env" in res["output"]
    assert snap.left == []


@pytest.mark.parametrize(
    "exc",
    [
        rmt.child_env.ChildEnvError("child_env.names: bad"),
        rmt.NoGitError("not a git work tree"),
        rmt.GitFailedError(128, "fatal: bad object HEAD"),
    ],
    ids=["child-env-error", "no-git", "git-failed"],
)
def test_a_tree_that_cannot_be_reread_after_the_run_is_red(proj, exc):
    """A green run whose after-snapshot fails has an unproven read-only claim."""
    seq = [{}]

    def snapshot(root):
        if seq:
            return seq.pop(0)
        raise exc

    res = rmt.run_target("check", cwd=str(proj), runner=_fake(0), snapshot=snapshot)
    assert res["ok"] is False and res["returncode"] == 0, res
    assert "cannot re-read the tree" in res["output"], res


# --- the gate's time limit and the process tree make starts ------------------
#
# These cases run a real process tree: a fake `make` (a Python script) that
# starts a grandchild, as `make test` starts pytest. The grandchild writes
# `ready` once its signal disposition is set, and the fake make writes `pids`
# (its own pid and the grandchild's) once the grandchild is ready, so a case
# never signals a process that has not finished starting.

import signal  # noqa: E402
import subprocess  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402

# A grandchild that sleeps until it is ended, one that ignores SIGTERM, and one
# that records SIGTERM and exits, as a server with a shutdown handler does.
_SLEEPS = (
    "import pathlib, time\npathlib.Path('ready').write_text('1')\ntime.sleep(600)\n"
)
_IGNORES_TERM = (
    "import pathlib, signal, time\n"
    "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
    "pathlib.Path('ready').write_text('1')\ntime.sleep(600)\n"
)
_TRAPS_TERM = (
    "import pathlib, signal, sys, time\n"
    "def stop(*_):\n    pathlib.Path('termed').write_text('1')\n    sys.exit(0)\n"
    "signal.signal(signal.SIGTERM, stop)\n"
    "pathlib.Path('ready').write_text('1')\ntime.sleep(600)\n"
)
# Seconds a case waits for a process to start or to be gone: generous, because
# a cold interpreter on a network home can take seconds to start, and bounded,
# so a survivor fails the case instead of hanging the suite.
_SETTLE = 30.0


def _write_fake_make(where, grandchild, detach=False, exit_after=False, status=0):
    """A `make` that starts *grandchild* and then sleeps (or exits *status*
    when *exit_after*). *detach* points the grandchild's output away from make's,
    as a daemon does, so make's output closes while the grandchild lives."""
    where.mkdir(exist_ok=True)
    make = where / "make"
    out = "subprocess.DEVNULL" if detach else "None"
    make.write_text(
        "#!%s\n"
        "import os, pathlib, subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', %r], stdout=%s, stderr=%s)\n"
        "deadline = time.monotonic() + %r\n"
        "while not pathlib.Path('ready').exists() and time.monotonic() < deadline:\n"
        "    time.sleep(0.05)\n"
        "pathlib.Path('pids').write_text('%%d %%d' %% (os.getpid(), child.pid))\n"
        "print('make started its child', flush=True)\n"
        "%s\n"
        % (
            sys.executable,
            grandchild,
            out,
            out,
            _SETTLE,
            "sys.exit(%d)" % status if exit_after else "time.sleep(600)",
        ),
        encoding="utf-8",
    )
    make.chmod(0o755)
    return make


def _alive(pid):
    """True while *pid* runs. A zombie counts as gone: it runs nothing, and
    who reaps it (init, or a subreaper) is not the runner's to decide."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:
        with open("/proc/%d/stat" % pid, encoding="utf-8") as fh:
            return fh.read().rsplit(")", 1)[1].split()[0] != "Z"
    except FileNotFoundError:
        # Reaped after signal 0 found it: a verify at load average 9 hit this.
        return False
    except OSError:
        return True


def _gone_within(pids, seconds=_SETTLE):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not any(_alive(p) for p in pids):
            return True
        time.sleep(0.05)
    return False


def _pids(cwd):
    path = cwd / "pids"
    assert path.exists(), "the fake make never wrote its pids: it did not start"
    return [int(p) for p in path.read_text(encoding="utf-8").split()]


@pytest.fixture
def tree(proj, monkeypatch):
    """The project, with a fake make first on PATH; the allowlisted environment
    copies PATH, so make is found there exactly as the real one is."""
    bin_dir = proj / "bin"
    monkeypatch.setenv("PATH", "%s%s%s" % (bin_dir, os.pathsep, os.environ["PATH"]))
    return proj


def _cleanup(pids):
    """A case that failed leaves its tree running; end only the pids it started."""
    for pid in pids:
        if _alive(pid):
            # It can still exit before the kill lands; that is the goal reached.
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)


def _reaped_after_the_probe(monkeypatch):
    """Signal 0 finds the pid, then it is reaped before /proc is read and
    before any kill lands: the window a loaded host widens."""
    real_kill = os.kill
    gone = {"after_probe": False}

    def kill(pid, sig):
        if gone["after_probe"]:
            raise ProcessLookupError(pid)
        if sig == 0:
            gone["after_probe"] = True
            return None
        return real_kill(pid, sig)

    def no_proc(*_args, **_kwargs):
        raise FileNotFoundError("/proc/<pid>/stat")

    monkeypatch.setattr(os, "kill", kill)
    monkeypatch.setattr("builtins.open", no_proc)


def test_a_pid_reaped_between_the_probe_and_proc_counts_as_gone(monkeypatch):
    _reaped_after_the_probe(monkeypatch)
    assert _alive(999_999_999) is False


def test_cleanup_spares_a_pid_that_exits_before_its_kill(monkeypatch):
    """/proc shows it running, then it exits before SIGKILL lands."""

    def kill(pid, sig):
        if sig == signal.SIGKILL:
            raise ProcessLookupError(pid)

    monkeypatch.setattr(os, "kill", kill)
    monkeypatch.setattr("builtins.open", lambda *_a, **_k: io.StringIO("1 (py) S 0"))
    _cleanup([999_999_999])


def test_a_timeout_ends_every_process_make_started_and_says_so(tree):
    _write_fake_make(tree / "bin", _SLEEPS)
    res = rmt.run_target(
        "check", cwd=str(tree), timeout=5, grace=5, snapshot=_snaps({}, {})
    )
    pids = _pids(tree)
    try:
        assert _gone_within(pids), "a process make started outlived the timeout"
    finally:
        _cleanup(pids)
    assert res["ok"] is False and res["returncode"] is None, res
    assert res["timed_out"] is True, res
    assert "did not complete within 5 s" in res["output"], res["output"]
    assert "make started its child" in res["output"], res["output"]


def test_a_process_that_ignores_sigterm_is_killed_after_the_grace(tree):
    _write_fake_make(tree / "bin", _IGNORES_TERM)
    started = time.monotonic()
    res = rmt.run_target(
        "check", cwd=str(tree), timeout=5, grace=1, snapshot=_snaps({}, {})
    )
    pids = _pids(tree)
    try:
        assert _gone_within(pids), "SIGTERM was ignored and nothing escalated"
    finally:
        _cleanup(pids)
    assert res["timed_out"] is True, res
    assert time.monotonic() - started < _SETTLE


def test_a_process_that_handles_sigterm_gets_the_grace_to_stop(tree):
    _write_fake_make(tree / "bin", _TRAPS_TERM)
    rmt.run_target("check", cwd=str(tree), timeout=5, grace=20, snapshot=_snaps({}, {}))
    pids = _pids(tree)
    try:
        assert _gone_within(pids)
    finally:
        _cleanup(pids)
    assert (tree / "termed").exists(), "the group was killed without a SIGTERM first"


def test_an_interrupt_ends_the_tree_and_propagates(tree):
    make = _write_fake_make(tree / "bin", _SLEEPS)

    # Raised only while the runner runs, so a late signal cannot interrupt the
    # case's own cleanup.
    in_run = [False]

    def interrupt(*_):
        if in_run[0]:
            raise KeyboardInterrupt

    # The watcher signals only while armed, under the lock the case takes to
    # disarm it: SIGUSR1's default action ends the process, so a signal sent
    # after the handler is restored would end the whole pytest session.
    armed, lock = [True], threading.Lock()

    def when_started():
        deadline = time.monotonic() + _SETTLE
        while not (tree / "pids").exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        with lock:
            if armed[0]:
                signal.pthread_kill(threading.main_thread().ident, signal.SIGUSR1)

    previous = signal.signal(signal.SIGUSR1, interrupt)
    watcher = threading.Thread(target=when_started, daemon=True)
    try:
        watcher.start()
        with pytest.raises(KeyboardInterrupt):
            in_run[0] = True
            try:
                rmt._default_runner([str(make)], str(tree), 600, grace=5)
            finally:
                in_run[0] = False
    finally:
        with lock:
            armed[0] = False
        watcher.join(_SETTLE)
        signal.signal(signal.SIGUSR1, previous)
    pids = _pids(tree)
    try:
        assert _gone_within(pids), "an interrupt left make's tree running"
    finally:
        _cleanup(pids)


def test_a_sigterm_to_the_runner_ends_the_tree_and_then_the_runner(tree):
    make = _write_fake_make(tree / "bin", _SLEEPS)
    code = (
        "import sys; sys.path.insert(0, %r); import run_make_target as r; "
        "r._default_runner([%r], %r, 600, grace=5)"
        % (str(_ROOT / "scripts"), str(make), str(tree))
    )
    runner = subprocess.Popen(  # noqa: S603 — argv list, never a shell string
        [sys.executable, "-c", code],
        cwd=str(tree),
        env=rmt.child_env.build_child_env(),
    )
    pids = []
    try:
        deadline = time.monotonic() + _SETTLE
        while not (tree / "pids").exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        pids = _pids(tree)
        runner.send_signal(signal.SIGTERM)
        assert runner.wait(timeout=_SETTLE) == -signal.SIGTERM
        assert _gone_within(pids), "a SIGTERM to the runner orphaned make's tree"
    finally:
        _cleanup(pids)
        if runner.poll() is None:
            runner.kill()
            runner.wait()


def test_a_sigkilled_runner_leaves_none_of_make_s_tree_running(tree):
    """SIGKILL runs no handler: the watcher scripts/resource_limits.py starts
    beside make sees the runner's pipe close and ends make's session."""
    make = _write_fake_make(tree / "bin", _SLEEPS)
    code = (
        "import sys; sys.path.insert(0, %r); import run_make_target as r; "
        "r._default_runner([%r], %r, 600, grace=5)"
        % (str(_ROOT / "scripts"), str(make), str(tree))
    )
    runner = subprocess.Popen(  # noqa: S603 — argv list, never a shell string
        [sys.executable, "-c", code],
        cwd=str(tree),
        env=rmt.child_env.build_child_env(),
    )
    pids = []
    try:
        deadline = time.monotonic() + _SETTLE
        while not (tree / "pids").exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        pids = _pids(tree)
        runner.kill()
        assert runner.wait(timeout=_SETTLE) == -signal.SIGKILL
        assert _gone_within(pids), "a SIGKILL to the runner orphaned make's tree"
    finally:
        _cleanup(pids)
        if runner.poll() is None:
            runner.kill()
            runner.wait()


def test_a_process_left_running_after_make_exits_is_ended_and_turns_the_gate_red(
    tree,
):
    """Fail closed: a green make that leaves a process behind leaked it, and a
    gate that passed it would hand the next pass a tree something still writes."""
    _write_fake_make(tree / "bin", _SLEEPS, detach=True, exit_after=True)
    res = rmt.run_target(
        "check", cwd=str(tree), timeout=60, grace=5, snapshot=_snaps({}, {})
    )
    pids = _pids(tree)
    try:
        assert _gone_within(pids), "a process make left behind is still running"
    finally:
        _cleanup(pids)
    assert res["returncode"] == 0 and res["timed_out"] is False, res
    assert res["ok"] is False, res
    leaked = res["leaked"]
    assert len(leaked) == 1 and leaked[0].startswith("%d " % pids[1]), leaked
    assert "-c" in leaked[0], leaked
    assert "leaked" in res["output"] and str(pids[1]) in res["output"], res["output"]


def test_a_failing_make_that_leaks_keeps_its_own_status(tree):
    _write_fake_make(tree / "bin", _SLEEPS, detach=True, exit_after=True, status=3)
    res = rmt.run_target(
        "check", cwd=str(tree), timeout=60, grace=5, snapshot=_snaps({}, {})
    )
    pids = _pids(tree)
    try:
        assert _gone_within(pids), "a process make left behind is still running"
    finally:
        _cleanup(pids)
    assert res["returncode"] == 3 and res["ok"] is False, res
    assert len(res["leaked"]) == 1, res


def test_a_run_that_leaks_nothing_names_no_leak(proj):
    res = rmt.run_target(
        "check",
        cwd=str(proj),
        runner=lambda cmd, cwd, timeout: (0, "ok\n"),
        timeout=5,
        grace=1,
        snapshot=_snaps({}, {}),
    )
    assert res["ok"] is True and res["leaked"] == [], res


def _with_limits(proj, **limits):
    policy = dict(_POLICY, **limits)
    (proj / "config" / "project.json").write_text(
        json.dumps({"make_targets": policy}), encoding="utf-8"
    )


def test_the_time_limit_and_grace_come_from_config(proj, monkeypatch):
    _with_limits(proj, gate_timeout_seconds=7, gate_stop_grace_seconds=3)
    seen = []
    monkeypatch.setattr(
        rmt,
        "_default_runner",
        lambda cmd, cwd, timeout, grace: seen.append((timeout, grace)) or (0, ""),
    )
    rmt.run_target("check", cwd=str(proj), snapshot=_snaps({}, {}))
    assert seen == [(7, 3)]


def test_an_absent_limit_takes_the_loader_default_and_says_so(
    proj, monkeypatch, capsys
):
    seen = []
    # The default line is written once per (where, key) per process; an earlier
    # test may have spent it, so this one starts from an empty announced set.
    monkeypatch.setattr(rmt.config_loader, "_ANNOUNCED", set())
    monkeypatch.setattr(
        rmt,
        "_default_runner",
        lambda cmd, cwd, timeout, grace: seen.append((timeout, grace)) or (0, ""),
    )
    rmt.run_target("check", cwd=str(proj), snapshot=_snaps({}, {}))
    rows = {k.path[-1]: k.default for k in rmt.config_loader.rows(*rmt.LIMIT_KEYS)}
    assert seen == [(rows["gate_timeout_seconds"], rows["gate_stop_grace_seconds"])]
    err = capsys.readouterr().err
    assert "[using default] make_targets.gate_timeout_seconds" in err, err


@pytest.mark.parametrize(
    "key, value",
    [
        ("gate_timeout_seconds", 0),
        ("gate_stop_grace_seconds", "10"),
        ("gate_timeout_seconds", True),
        ("gate_timeout_seconds", 604801),
        ("gate_stop_grace_seconds", 3601),
        ("gate_timeout_seconds", 10**400),
        ("gate_stop_grace_seconds", 10**400),
    ],
    ids=["zero", "string", "bool", "past-week", "past-hour", "huge", "huge-grace"],
)
def test_a_bad_limit_is_a_config_fault_before_make_runs(
    proj, monkeypatch, capsys, key, value
):
    _with_limits(proj, **{key: value})
    monkeypatch.setattr(rmt, "tree_snapshot", _never)
    assert rmt.main(["check", "--dir", str(proj)]) == rmt.ExitCode.CONFIG
    assert "make_targets.%s" % key in capsys.readouterr().err
    res = rmt.run_target("check", cwd=str(proj), runner=_fake(0), snapshot=_never)
    assert res["refused"] and "make_targets.%s" % key in res["refused"], res


def test_the_timeout_flag_overrides_the_configured_limit(proj, monkeypatch):
    _with_limits(proj, gate_timeout_seconds=7, gate_stop_grace_seconds=3)
    seen = []
    monkeypatch.setattr(
        rmt,
        "_default_runner",
        lambda cmd, cwd, timeout, grace: seen.append((timeout, grace)) or (0, ""),
    )
    monkeypatch.setattr(rmt, "tree_snapshot", lambda root: {})
    assert rmt.main(["check", "--dir", str(proj), "--timeout", "11"]) == 0
    assert rmt.main(["check", "--dir", str(proj)]) == 0
    assert seen == [(11, 3), (7, 3)]


@pytest.mark.parametrize(
    "value", ["0", "-5", "604801", "1" + "0" * 400], ids=["0", "-5", "604801", "huge"]
)
def test_a_timeout_flag_outside_its_bound_is_refused(proj, capsys, value):
    assert (
        rmt.main(["check", "--dir", str(proj), "--timeout", value])
        == rmt.ExitCode.USAGE
    )
    assert "--timeout" in capsys.readouterr().err


def test_the_cli_reports_a_timeout_through_the_exit_helper(proj, monkeypatch, capsys):
    def hangs(cmd, cwd, timeout, grace):
        raise subprocess.TimeoutExpired(cmd, timeout, output="half done\n")

    monkeypatch.setattr(rmt, "_default_runner", hangs)
    monkeypatch.setattr(rmt, "tree_snapshot", lambda root: {})
    code = rmt.main(["check", "--dir", str(proj), "--timeout", "9"])
    captured = capsys.readouterr()
    assert code == rmt.ExitCode.FAILURE
    assert "half done" in captured.out
    last = captured.err.strip().splitlines()[-1]
    assert "timed out" in last and "9 s" in last, last
    assert "make_targets.gate_timeout_seconds" in last, last


def _leaks(status):
    def runner(cmd, cwd, timeout, grace):
        raise rmt.LeftRunning(status, "made it\n", [(4242, "python -c sleep")])

    return runner


def test_the_cli_fails_a_green_target_that_leaked_a_process(proj, monkeypatch, capsys):
    monkeypatch.setattr(rmt, "_default_runner", _leaks(0))
    monkeypatch.setattr(rmt, "tree_snapshot", lambda root: {})
    code = rmt.main(["check", "--dir", str(proj)])
    captured = capsys.readouterr()
    assert code == rmt.ExitCode.FAILURE
    assert "made it" in captured.out
    last = captured.err.strip().splitlines()[-1]
    assert "leaked" in last and "4242 python -c sleep" in last, last
    assert "stop every process it starts" in last, last


def test_the_cli_keeps_makes_own_failure_when_a_red_target_leaked(
    proj, monkeypatch, capsys
):
    monkeypatch.setattr(rmt, "_default_runner", _leaks(2))
    monkeypatch.setattr(rmt, "tree_snapshot", lambda root: {})
    assert rmt.main(["check", "--dir", str(proj)]) == rmt.ExitCode.FAILURE
    last = capsys.readouterr().err.strip().splitlines()[-1]
    assert "the gate is red" in last and "rc=2" in last, last


def test_the_cli_reports_an_interrupt_through_the_exit_helper(
    proj, monkeypatch, capsys
):
    def interrupted(cmd, cwd, timeout, grace):
        raise KeyboardInterrupt

    monkeypatch.setattr(rmt, "_default_runner", interrupted)
    monkeypatch.setattr(rmt, "tree_snapshot", lambda root: {})
    assert rmt.main(["check", "--dir", str(proj)]) == rmt.ExitCode.INTERRUPTED
    assert "interrupted" in capsys.readouterr().err


# --- review findings: what counts as alive, signals, the pipe, cleanup --------


def _write_script(where, name, body):
    """An executable Python script *name* in *where* that runs *body*."""
    where.mkdir(exist_ok=True)
    path = where / name
    path.write_text("#!%s\n%s" % (sys.executable, body), encoding="utf-8")
    path.chmod(0o755)
    return path


def _in_child(tree, body):
    """Run *body* in a fresh interpreter that has imported run_make_target as
    `r`, and return what it printed: a case that changes process-wide state
    (a subreaper) keeps it out of the pytest process."""
    code = "import sys; sys.path.insert(0, %r); import run_make_target as r\n%s" % (
        str(_ROOT / "scripts"),
        body,
    )
    done = subprocess.run(  # noqa: S603 — argv list, never a shell string
        [sys.executable, "-c", code],
        cwd=str(tree),
        env=rmt.child_env.build_child_env(),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert done.returncode == 0, done.stderr
    return done.stdout.strip().splitlines()[-1]


def test_a_member_that_exited_but_was_not_yet_reaped_is_not_a_leak(tree):
    """A zombie runs nothing. Under a subreaper that has not collected it, a
    background job that already ended stays a zombie in make's group; the run
    must still be green and must not spend the grace waiting for it."""
    make = _write_script(
        tree / "bin",
        "make",
        "import subprocess, sys, time\n"
        # The middle process exits at once, so its child is reparented to the
        # subreaper (the runner's process), exits, and is never reaped.
        "subprocess.run([sys.executable, '-c', 'import subprocess, sys; "
        'subprocess.Popen([sys.executable, "-c", "pass"])\'])\n'
        "time.sleep(3)\n",
    )
    out = _in_child(
        tree,
        "import ctypes, json, time\n"
        "ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0)\n"
        "t = time.monotonic()\n"
        "try:\n"
        "    rc, _ = r._default_runner([%r], '.', 60, grace=20)\n"
        "    print(json.dumps({'rc': rc, 'leaked': None, 's': time.monotonic() - t}))\n"
        "except r.LeftRunning as e:\n"
        "    print(json.dumps({'rc': e.returncode, 'leaked': e.leftovers, "
        "'s': time.monotonic() - t}))\n" % str(make),
    )
    got = json.loads(out)
    assert got["rc"] == 0 and got["leaked"] is None, got
    assert got["s"] < 15, got


def test_a_signal_the_caller_ignored_stays_ignored(tree):
    """nohup: a runner started with SIGHUP ignored must not end make on one."""
    make = _write_script(
        tree / "bin",
        "make",
        "import pathlib, time\npathlib.Path('pids').write_text('1')\ntime.sleep(2)\n",
    )
    out = _in_child(
        tree,
        "import os, pathlib, signal, threading, time\n"
        "signal.signal(signal.SIGHUP, signal.SIG_IGN)\n"
        "def hup():\n"
        "    while not pathlib.Path('pids').exists():\n"
        "        time.sleep(0.05)\n"
        "    os.kill(os.getpid(), signal.SIGHUP)\n"
        "threading.Thread(target=hup, daemon=True).start()\n"
        "print(r._default_runner([%r], '.', 60, grace=5)[0])\n" % str(make),
    )
    assert out == "0", out


def test_a_background_child_holding_the_output_does_not_hold_the_run(tree):
    """make's exit, not the end of its output, ends the run: a child that keeps
    the pipe open is a leak, reported as soon as make exits, with make's 0."""
    _write_fake_make(tree / "bin", _SLEEPS, exit_after=True)
    started = time.monotonic()
    res = rmt.run_target(
        "check", cwd=str(tree), timeout=40, grace=2, snapshot=_snaps({}, {})
    )
    pids = _pids(tree)
    try:
        assert _gone_within(pids), "the child holding the pipe outlived the run"
    finally:
        _cleanup(pids)
    assert time.monotonic() - started < 20, "the run waited for the pipe to close"
    assert res["timed_out"] is False and res["returncode"] == 0, res
    assert len(res["leaked"]) == 1 and res["ok"] is False, res
    assert "make started its child" in res["output"], res["output"]


def test_a_sigterm_during_the_leak_cleanup_still_kills_the_leftover(tree):
    """The leftover ignores SIGTERM, so the cleanup waits out its grace; a
    SIGTERM to the runner then must still end it before the runner goes."""
    make = _write_fake_make(tree / "bin", _IGNORES_TERM, detach=True, exit_after=True)
    runner = subprocess.Popen(  # noqa: S603 — argv list, never a shell string
        [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0, %r); import run_make_target as r; "
            "r._default_runner([%r], %r, 600, grace=60)"
            % (str(_ROOT / "scripts"), str(make), str(tree)),
        ],
        cwd=str(tree),
        env=rmt.child_env.build_child_env(),
    )
    pids = []
    try:
        deadline = time.monotonic() + _SETTLE
        while not (tree / "pids").exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        pids = _pids(tree)
        assert _gone_within(pids[:1]), "the fake make did not exit"
        time.sleep(1)  # into the cleanup's grace
        runner.send_signal(signal.SIGTERM)
        assert runner.wait(timeout=_SETTLE) == -signal.SIGTERM
        assert _gone_within(pids[1:]), "a SIGTERM during cleanup orphaned the leftover"
    finally:
        _cleanup(pids)
        if runner.poll() is None:
            runner.kill()
            runner.wait()


def test_a_second_interrupt_during_the_grace_still_kills_the_group(tree):
    make = _write_fake_make(tree / "bin", _IGNORES_TERM)
    in_run = [False]

    def interrupt(*_):
        if in_run[0]:
            raise KeyboardInterrupt

    armed, lock = [True], threading.Lock()

    def twice():
        deadline = time.monotonic() + _SETTLE
        while not (tree / "pids").exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        for _ in range(2):
            with lock:
                if armed[0]:
                    signal.pthread_kill(threading.main_thread().ident, signal.SIGUSR1)
            time.sleep(1)

    previous = signal.signal(signal.SIGUSR1, interrupt)
    watcher = threading.Thread(target=twice, daemon=True)
    try:
        watcher.start()
        with pytest.raises(KeyboardInterrupt):
            in_run[0] = True
            try:
                rmt._default_runner([str(make)], str(tree), 600, grace=60)
            finally:
                in_run[0] = False
    finally:
        with lock:
            armed[0] = False
        watcher.join(_SETTLE)
        signal.signal(signal.SIGUSR1, previous)
    pids = _pids(tree)
    try:
        assert _gone_within(pids), "a second interrupt skipped the SIGKILL"
    finally:
        _cleanup(pids)


def test_the_runner_puts_back_the_signal_handlers_it_replaced(tree):
    make = _write_script(tree / "bin", "make", "pass\n")

    def mine(*_):
        return None

    before = {s: signal.getsignal(s) for s in rmt.resource_limits._UNWINDLESS}
    for sig in rmt.resource_limits._UNWINDLESS:
        signal.signal(sig, mine)
    try:
        assert rmt._default_runner([str(make)], str(tree), 30, grace=1)[0] == 0
        assert all(signal.getsignal(s) is mine for s in rmt.resource_limits._UNWINDLESS)
    finally:
        for sig, old in before.items():
            signal.signal(sig, old)


# --- re-review findings: the session, held output, held ids, bounds ----------

# A grandchild that leaves make's process group for one of its own, as GNU
# `timeout` does, and stays in make's session.
_OWN_GROUP = "import os\nos.setpgid(0, 0)\n" + _SLEEPS
# One that leaves make's session too (`setsid`), keeping make's output open.
_OWN_SESSION = "import os\nos.setsid()\n" + _SLEEPS


def test_a_timeout_ends_a_process_that_left_makes_group_but_not_its_session(tree):
    _write_fake_make(tree / "bin", _OWN_GROUP)
    res = rmt.run_target(
        "check", cwd=str(tree), timeout=3, grace=2, snapshot=_snaps({}, {})
    )
    pids = _pids(tree)
    try:
        assert _gone_within(pids), "a process in make's session outlived the timeout"
    finally:
        _cleanup(pids)
    assert res["timed_out"] is True and res["ok"] is False, res


def test_a_process_left_in_makes_session_outside_its_group_is_a_leak(tree):
    _write_fake_make(tree / "bin", _OWN_GROUP, detach=True, exit_after=True)
    res = rmt.run_target(
        "check", cwd=str(tree), timeout=60, grace=2, snapshot=_snaps({}, {})
    )
    pids = _pids(tree)
    try:
        assert _gone_within(pids), "a process make left in its session still runs"
    finally:
        _cleanup(pids)
    assert res["returncode"] == 0 and res["ok"] is False, res
    assert [p.split()[0] for p in res["leaked"]] == [str(pids[1])], res


def test_a_process_outside_makes_session_holding_its_output_turns_the_run_red(tree):
    """Fail closed on positive evidence: output still open once make's session
    has ended is held by a process that escaped it, which the runner does not
    signal; the run is red and names it, so a person can end it."""
    _write_fake_make(tree / "bin", _OWN_SESSION, exit_after=True)
    res = rmt.run_target(
        "check", cwd=str(tree), timeout=60, grace=1, snapshot=_snaps({}, {})
    )
    pids = _pids(tree)
    try:
        assert _alive(pids[1]), "the runner signalled a process outside make's session"
    finally:
        _cleanup(pids)
    assert res["returncode"] == 0 and res["leaked"] == [], res
    assert res["ok"] is False, res
    assert [p.split()[0] for p in res["escaped"]] == [str(pids[1])], res
    assert "-c" in res["escaped"][0], res
    assert str(pids[1]) in res["output"] and "kill" in res["output"], res["output"]


def test_the_cli_fails_a_run_whose_output_a_process_outside_the_session_holds(
    proj, monkeypatch, capsys
):
    def held(cmd, cwd, timeout, grace):
        raise rmt.OutputHeld(0, "made it\n", [(4243, "python -c sleep")])

    monkeypatch.setattr(rmt, "_default_runner", held)
    monkeypatch.setattr(rmt, "tree_snapshot", lambda root: {})
    code = rmt.main(["check", "--dir", str(proj)])
    captured = capsys.readouterr()
    assert code == rmt.ExitCode.FAILURE
    assert "made it" in captured.out and "-> FAIL" in captured.out, captured.out
    last = captured.err.strip().splitlines()[-1]
    assert "4243 python -c sleep" in last and "kill 4243" in last, last


def test_a_run_that_leaks_nothing_names_no_escape(proj):
    res = rmt.run_target(
        "check",
        cwd=str(proj),
        runner=_fake(0),
        timeout=5,
        grace=1,
        snapshot=_snaps({}, {}),
    )
    assert res["ok"] is True and res["escaped"] == [], res


# Records each os.killpg as (group id, signal, whether /proc still has the
# process whose id it is). make's pid is its group id, so a missing entry is a
# signal to an id make no longer held, which a new process could have taken.
_RECORD_KILLPG = (
    "import json, os, signal\n"
    "sent = []\n"
    "real_killpg = os.killpg\n"
    "def killpg(pgid, sig):\n"
    "    sent.append((pgid, int(sig), os.path.exists('/proc/%d' % pgid)))\n"
    "    return real_killpg(pgid, sig)\n"
    "os.killpg = killpg\n"
    "terms = []\n"
    "signal.signal(signal.SIGTERM, lambda *_: terms.append(1))\n"
)


@pytest.mark.parametrize("when", ["finish", "wait"])
def test_a_sigterm_after_make_exits_signals_no_id_make_gave_up(tree, when):
    """The stop handler runs whenever SIGTERM lands. Once make is reaped its
    pid, the group id, is free to pass to a new process, so a SIGTERM while
    the output is read after make exited ("finish"), or just after make is
    reaped ("wait"), must signal nothing that is not still held."""
    make = _write_script(tree / "bin", "make", "print('made it')\n")
    out = _in_child(
        tree,
        _RECORD_KILLPG + "when = %r\n"
        "real_finish = r.resource_limits.PipeReader.finish\n"
        "def finish(self, wait):\n"
        "    if when == 'finish' and wait > 0:\n"
        "        os.kill(os.getpid(), signal.SIGTERM)\n"
        "    return real_finish(self, wait)\n"
        "r.resource_limits.PipeReader.finish = finish\n"
        "real_wait = r.subprocess.Popen.wait\n"
        "def wait(self, *a, **k):\n"
        "    got = real_wait(self, *a, **k)\n"
        "    if when == 'wait' and not terms and not sent:\n"
        "        os.kill(os.getpid(), signal.SIGTERM)\n"
        "    return got\n"
        "r.subprocess.Popen.wait = wait\n"
        "rc, _ = r._default_runner([%r], '.', 30, grace=1)\n"
        "print(json.dumps({'rc': rc, 'sent': sent, 'terms': len(terms)}))\n"
        % (when, str(make)),
    )
    got = json.loads(out)
    assert got["rc"] == 0 and got["terms"] == 1, got
    assert all(held for _g, _s, held in got["sent"]), got
    if when == "finish":
        # make was still held then, so the stop reached its group.
        assert got["sent"], got


def test_without_waitid_a_leftover_is_named_but_not_signalled(tree, monkeypatch):
    """Where Python has no os.waitid, make is reaped as soon as it exits, so
    nothing holds its group id: the runner sends no signal after that, and the
    leftover is red and named as still running, not claimed ended."""
    _write_fake_make(tree / "bin", _SLEEPS, detach=True, exit_after=True)
    monkeypatch.delattr(os, "waitid")
    sent = []
    real_killpg = os.killpg

    def killpg(pgid, sig):
        sent.append((pgid, sig, os.path.exists("/proc/%d" % pgid)))
        return real_killpg(pgid, sig)

    monkeypatch.setattr(os, "killpg", killpg)
    res = rmt.run_target(
        "check", cwd=str(tree), timeout=60, grace=1, snapshot=_snaps({}, {})
    )
    pids = _pids(tree)
    try:
        assert _alive(pids[1]), "the leftover was signalled after make was reaped"
    finally:
        _cleanup(pids)
    assert all(held for _g, _s, held in sent), sent
    assert res["ok"] is False and len(res["leaked"]) == 1, res
    assert "still running" in res["output"] and "were ended" not in res["output"]
    assert "kill %d" % pids[1] in res["output"], res["output"]


# make sleeps; the runner's Popen is wrapped to send a signal to the runner
# right after make has started and before Popen has returned, the moment the
# runner has a child but no record of it.
_SIGNAL_INSIDE_POPEN = (
    "import json, os, pathlib, signal, time\n"
    "real_popen = r.subprocess.Popen\n"
    "def popen(*a, **k):\n"
    "    proc = real_popen(*a, **k)\n"
    # The first spawn is make; the watcher that follows it is left alone.
    "    if not pathlib.Path('makepid').exists():\n"
    "        pathlib.Path('makepid').write_text(str(proc.pid))\n"
    "        os.kill(os.getpid(), SIG)\n"
    "    return proc\n"
    "r.subprocess.Popen = popen\n"
    "def gone(pid):\n"
    "    deadline = time.monotonic() + 10\n"
    "    while time.monotonic() < deadline:\n"
    "        try:\n"
    "            os.kill(pid, 0)\n"
    "        except ProcessLookupError:\n"
    "            return True\n"
    "        try:\n"
    "            os.waitpid(pid, os.WNOHANG)\n"
    "        except ChildProcessError:\n"
    "            pass\n"
    "        time.sleep(0.05)\n"
    "    os.kill(pid, signal.SIGKILL)\n"
    "    return False\n"
)


def test_a_ctrl_c_while_make_starts_still_ends_make(tree):
    make = _write_script(tree / "bin", "make", "import time\ntime.sleep(487)\n")
    out = _in_child(
        tree,
        "import signal\nSIG = signal.SIGINT\n" + _SIGNAL_INSIDE_POPEN + "try:\n"
        "    r._default_runner([%r], '.', 30, grace=2)\n"
        "    what = 'returned'\n"
        "except KeyboardInterrupt:\n"
        "    what = 'interrupted'\n"
        "pid = int(pathlib.Path('makepid').read_text())\n"
        "print(json.dumps({'what': what, 'gone': gone(pid)}))\n" % str(make),
    )
    assert json.loads(out) == {"what": "interrupted", "gone": True}, out


def test_a_sigterm_while_make_starts_still_ends_make(tree):
    make = _write_script(tree / "bin", "make", "import time\ntime.sleep(488)\n")
    out = _in_child(
        tree,
        "import signal\nSIG = signal.SIGTERM\n" + _SIGNAL_INSIDE_POPEN + "terms = []\n"
        "signal.signal(signal.SIGTERM, lambda *_: terms.append(1))\n"
        "try:\n"
        "    what = r._default_runner([%r], '.', 8, grace=2)[0]\n"
        "except r.subprocess.TimeoutExpired:\n"
        "    what = 'timed out'\n"
        "pid = int(pathlib.Path('makepid').read_text())\n"
        "print(json.dumps({'what': what, 'terms': len(terms), 'gone': gone(pid)}))\n"
        % str(make),
    )
    assert json.loads(out) == {"what": -15, "terms": 1, "gone": True}, out


@pytest.mark.parametrize(
    "limits", [{"timeout": 10**400}, {"grace": 3601}], ids=["huge-timeout", "grace"]
)
def test_a_given_limit_past_its_bound_is_refused_before_make_runs(proj, limits):
    """run_target's own timeout and grace meet the bound the KEYS rows give,
    so a caller cannot pass a value the stop loop would overflow on."""
    with pytest.raises(ValueError, match="from 1 to"):
        rmt.run_target("check", cwd=str(proj), runner=_never, snapshot=_never, **limits)


def test_the_gate_grace_outlasts_the_e2e_servers_stop_wait():
    """On SIGTERM a test's handler stops the e2e server, which runs in a session
    of its own outside make's, with SIGTERM and then SIGKILL after
    e2e.server.stop_timeout_s. The runner sends pytest SIGKILL after its own
    grace; were that not longer, pytest could die before its SIGKILL and leave
    the server running, unseen by the runner."""
    import live_server

    _timeout, grace = rmt.gate_limits(
        rmt.config_loader.read(str(_ROOT), "config/project.json")
    )
    stop = live_server.load_server_config(str(_ROOT))["stop_timeout_s"]
    assert grace > stop, (grace, stop)


def test_make_stays_unreaped_while_its_leftovers_are_signalled(tree, monkeypatch):
    """os.waitid's WNOWAIT keeps make a zombie while the runner ends what it
    left, so every signal goes to an id make still holds: /proc still has
    make's entry at each one. Reaping make on its exit would free the id
    first, and a new process could take it."""
    _write_fake_make(tree / "bin", _SLEEPS, detach=True, exit_after=True)
    sent = []
    real_killpg = os.killpg

    def killpg(pgid, sig):
        sent.append((pgid, sig, os.path.exists("/proc/%d" % pgid)))
        return real_killpg(pgid, sig)

    monkeypatch.setattr(os, "killpg", killpg)
    res = rmt.run_target(
        "check", cwd=str(tree), timeout=60, grace=1, snapshot=_snaps({}, {})
    )
    pids = _pids(tree)
    try:
        assert _gone_within(pids), "the leftover outlived the run"
    finally:
        _cleanup(pids)
    assert len(res["leaked"]) == 1, res
    assert sent, "the leftover was never signalled"
    assert all(held for _g, _s, held in sent), sent


def test_a_child_exiting_just_after_make_is_not_a_leak(tree):
    """A background job that ends a moment after make (here 0.2 s, inside
    _SETTLE_SECONDS) is not left behind: the runner re-reads the session for
    the settle before it counts one, so this green make stays green."""
    _write_script(
        tree / "bin",
        "make",
        "import pathlib, subprocess, sys\n"
        "subprocess.Popen([sys.executable, '-c', 'import pathlib, time\\n"
        'while not pathlib.Path("go").exists():\\n'
        "    time.sleep(0.01)\\n"
        "time.sleep(0.2)\\n'])\n"
        "pathlib.Path('go').write_text('1')\n",
    )
    res = rmt.run_target(
        "check", cwd=str(tree), timeout=60, grace=1, snapshot=_snaps({}, {})
    )
    assert res["ok"] is True and res["leaked"] == [], res


# The probe pieces for a make that is gone: _RECORD_KILLPG records every
# os.killpg (with whether /proc still has that id), `made` gets make's pid as
# Popen returns, and state(pid) reads one process's state letter, None once it
# is gone.
_MAKE_PID = (
    "import os, time\n"
    "real_sleep = time.sleep\n"
    "made = []\n"
    "real_popen = r.subprocess.Popen\n"
    "def popen(*a, **k):\n"
    "    proc = real_popen(*a, **k)\n"
    "    made.append(proc.pid)\n"
    "    return proc\n"
    "r.subprocess.Popen = popen\n"
    "def state(pid):\n"
    "    try:\n"
    "        with open('/proc/%d/stat' % pid) as fh:\n"
    "            return fh.read().rsplit(')', 1)[1].split()[0]\n"
    "    except OSError:\n"
    "        return None\n"
    "def exited(pid):\n"
    "    deadline = time.monotonic() + 10\n"
    "    while state(pid) not in (None, 'Z') and time.monotonic() < deadline:\n"
    "        real_sleep(0.01)\n"
)
# A fake make that holds its exit until the case says `go`, bounded so a case
# that never says it fails on its own assertion instead of hanging.
_MAKE_WAITS_FOR_GO = (
    "import pathlib, time\n"
    "deadline = time.monotonic() + 30\n"
    "while not pathlib.Path('go').exists() and time.monotonic() < deadline:\n"
    "    time.sleep(0.01)\n"
)
# A waiter in the runner's own process, standing in for a library that reaps
# its children: the runner's first poll sleep waits for make to exit and reaps
# it with os.waitpid, so the runner's Popen never learns make's status.
_FOREIGN_WAITER = (
    "def sleep(seconds):\n"
    "    if made and not reaped:\n"
    "        exited(made[0])\n"
    "        os.waitpid(made[0], 0)\n"
    "        reaped.append(1)\n"
    "    real_sleep(seconds)\n"
    "reaped = []\n"
    "r.time.sleep = sleep\n"
)


@pytest.mark.parametrize("stop", ["sigterm", "interrupt"])
def test_a_stop_just_after_make_exits_under_an_ignored_sigchld_signals_no_freed_id(
    tree, stop
):
    """SIGCHLD set to ignore makes the kernel reap a child as it exits, so a
    stop in the moment between make's exit and the runner's next poll used to
    signal make's freed id. The runner sets SIGCHLD to its default for the run,
    so make stays a zombie holding its id, and puts the caller's back after.
    make waits for `go`, which the runner's first poll sleep writes: a make that
    exited before that poll left no sleep to stop in, so the case passed or
    failed by load (seen red in a full verify at load average 9)."""
    make = _write_script(tree / "bin", "make", _MAKE_WAITS_FOR_GO + "print('hi')\n")
    out = _in_child(
        tree,
        _RECORD_KILLPG + _MAKE_PID + "signal.signal(signal.SIGCHLD, signal.SIG_IGN)\n"
        "STOP = %r\n"
        "def sleep(seconds):\n"
        "    if made and not stopped:\n"
        "        open('go', 'w').close()\n"
        "        exited(made[0])\n"
        "        stopped.append(state(made[0]))\n"
        "        if STOP == 'sigterm':\n"
        "            os.kill(os.getpid(), signal.SIGTERM)\n"
        "        else:\n"
        "            raise KeyboardInterrupt\n"
        "    real_sleep(seconds)\n"
        "stopped = []\n"
        "r.time.sleep = sleep\n"
        "try:\n"
        "    what = r._default_runner([%r], '.', 20, grace=1)[0]\n"
        "except BaseException as e:\n"
        "    what = type(e).__name__\n"
        "print(json.dumps({'what': what, 'sent': sent, 'stopped': stopped, "
        "'ignored': signal.getsignal(signal.SIGCHLD) is signal.SIG_IGN}))\n"
        % (stop, str(make)),
    )
    got = json.loads(out)
    assert got["what"] == (0 if stop == "sigterm" else "KeyboardInterrupt"), got
    assert got["stopped"] == ["Z"], "make did not stay a zombie: %s" % got
    assert all(held for _g, _s, held in got["sent"]), got
    assert got["ignored"] is True, "the caller's SIGCHLD was not put back: %s" % got


def test_under_an_ignored_sigchld_a_green_make_keeps_its_status(tree):
    """The runner reads make's status even when the caller ignores SIGCHLD,
    because make runs with SIGCHLD at its default: no timeout, no unknown."""
    make = _write_script(tree / "bin", "make", "print('hi')\n")
    out = _in_child(
        tree,
        "import json, signal, time\n"
        "signal.signal(signal.SIGCHLD, signal.SIG_IGN)\n"
        "t = time.monotonic()\n"
        "rc, output = r._default_runner([%r], '.', 20, grace=1)\n"
        "print(json.dumps({'rc': rc, 'output': output, 's': time.monotonic() - t, "
        "'ignored': signal.getsignal(signal.SIGCHLD) is signal.SIG_IGN}))\n"
        % str(make),
    )
    got = json.loads(out)
    assert got["rc"] == 0 and got["output"] == "hi\n", got
    assert got["s"] < 10 and got["ignored"] is True, got


def test_under_an_ignored_sigchld_a_leftover_is_ended_through_makes_held_id(tree):
    make = _write_fake_make(tree / "bin", _SLEEPS, detach=True, exit_after=True)
    out = _in_child(
        tree,
        _RECORD_KILLPG + "signal.signal(signal.SIGCHLD, signal.SIG_IGN)\n"
        "try:\n"
        "    r._default_runner([%r], '.', 60, grace=2)\n"
        "    got = {'what': 'returned'}\n"
        "except r.LeftRunning as e:\n"
        "    got = {'what': 'left', 'left': e.leftovers, 'ended': e.ended}\n"
        "got['sent'] = sent\n"
        "print(json.dumps(got))\n" % str(make),
    )
    pids = _pids(tree)
    try:
        assert _gone_within(pids), "the leftover outlived the run"
    finally:
        _cleanup(pids)
    got = json.loads(out)
    assert got["what"] == "left" and got["ended"] is True, got
    assert [p for p, _c in got["left"]] == [pids[1]], got
    assert got["sent"] and all(held for _g, _s, held in got["sent"]), got


def test_off_the_main_thread_an_ignored_sigchld_is_refused_before_make_runs(tree):
    """Python lets only the main thread change a signal's handler, so a run
    started on another thread under an ignored SIGCHLD would race the kernel's
    reap: it is refused, and make never starts."""
    _write_script(
        tree / "bin", "make", "import pathlib\npathlib.Path('ran').write_text('1')\n"
    )
    out = _in_child(
        tree,
        "import json, signal, threading\n"
        "signal.signal(signal.SIGCHLD, signal.SIG_IGN)\n"
        "got = {}\n"
        "def run():\n"
        "    res = r.run_target('check', cwd='.', timeout=20, grace=1, "
        "snapshot=lambda root: {})\n"
        "    got['refused'] = res['refused']\n"
        "    try:\n"
        "        r._default_runner(['make'], '.', 20, grace=1)\n"
        "        got['direct'] = 'ran'\n"
        "    except r.ChildSignalIgnored as e:\n"
        "        got['direct'] = str(e)\n"
        "t = threading.Thread(target=run)\n"
        "t.start()\n"
        "t.join()\n"
        "print(json.dumps(got))\n",
    )
    got = json.loads(out)
    assert got["refused"] and "SIGCHLD" in got["refused"], got
    assert "SIGCHLD" in got["direct"] and "main thread" in got["direct"], got
    assert not (tree / "ran").exists(), "make ran off the main thread"


def test_a_make_another_waiter_reaped_is_red_and_its_leftovers_are_not_signalled(
    tree,
):
    """Another waiter in the runner's process can still reap make, and then
    make's id is free and its session id is anchored by nothing the runner
    holds. The run is red with make's status unknown, the leftovers are named
    from a listing of the session, and nothing is signalled, not even signal 0."""
    make = _write_fake_make(tree / "bin", _SLEEPS, detach=True, exit_after=True)
    out = _in_child(
        tree,
        _RECORD_KILLPG + _MAKE_PID + _FOREIGN_WAITER + "try:\n"
        "    r._default_runner([%r], '.', 60, grace=2)\n"
        "    got = {'what': 'returned'}\n"
        "except r.MakeReaped as e:\n"
        "    got = {'what': 'reaped', 'left': e.leftovers, 'listed': e.listed}\n"
        "got['sent'] = sent\n"
        "print(json.dumps(got))\n" % str(make),
    )
    pids = _pids(tree)
    try:
        assert _alive(pids[1]), "the runner signalled a leftover of a reaped make"
    finally:
        _cleanup(pids)
    got = json.loads(out)
    assert got["what"] == "reaped" and got["listed"] is True, got
    assert [p for p, _c in got["left"]] == [pids[1]], got
    assert got["sent"] == [], got


@pytest.mark.parametrize("stop", ["sigterm", "interrupt"])
def test_a_stop_after_another_waiter_reaps_make_signals_nothing(tree, stop):
    """The window the root fix leaves: another waiter reaps make, and a stop
    lands before the runner's next poll has seen it. The stop asks held
    again, finds make gone, and sends nothing to make's freed id or to the
    session it anchored; the leftover is not the runner's to end."""
    make = _write_fake_make(tree / "bin", _SLEEPS, detach=True, exit_after=True)
    out = _in_child(
        tree,
        _RECORD_KILLPG + _MAKE_PID + "STOP = %r\n"
        "def sleep(seconds):\n"
        "    if made and not reaped:\n"
        "        exited(made[0])\n"
        "        os.waitpid(made[0], 0)\n"
        "        reaped.append(1)\n"
        "        if STOP == 'sigterm':\n"
        "            os.kill(os.getpid(), signal.SIGTERM)\n"
        "        else:\n"
        "            raise KeyboardInterrupt\n"
        "    real_sleep(seconds)\n"
        "reaped = []\n"
        "r.time.sleep = sleep\n"
        "try:\n"
        "    r._default_runner([%r], '.', 60, grace=2)\n"
        "    what = 'returned'\n"
        "except BaseException as e:\n"
        "    what = type(e).__name__\n"
        "print(json.dumps({'what': what, 'sent': sent, 'terms': len(terms)}))\n"
        % (stop, str(make)),
    )
    pids = _pids(tree)
    try:
        assert _alive(pids[1]), "a stop after the reap signalled the leftover"
    finally:
        _cleanup(pids)
    got = json.loads(out)
    want = "MakeReaped" if stop == "sigterm" else "KeyboardInterrupt"
    assert got["what"] == want, got
    assert got["terms"] == (1 if stop == "sigterm" else 0), got
    assert got["sent"] == [], got


def test_a_child_exiting_just_after_a_reaped_make_is_not_a_leftover(tree):
    """The settle applies when make was reaped elsewhere too: a background
    job ending a moment after make is not named as left running."""
    _write_script(
        tree / "bin",
        "make",
        "import pathlib, subprocess, sys\n"
        "subprocess.Popen([sys.executable, '-c', 'import pathlib, time\\n"
        'while not pathlib.Path("go").exists():\\n'
        "    time.sleep(0.01)\\n"
        "time.sleep(0.3)\\n'])\n"
        "pathlib.Path('go').write_text('1')\n",
    )
    out = _in_child(
        tree,
        _MAKE_PID + _FOREIGN_WAITER + "import json\n"
        "try:\n"
        "    r._default_runner(['make'], '.', 60, grace=2)\n"
        "    got = {'what': 'returned'}\n"
        "except r.MakeReaped as e:\n"
        "    got = {'what': 'reaped', 'left': e.leftovers}\n"
        "print(json.dumps(got))\n",
    )
    assert json.loads(out) == {"what": "reaped", "left": []}, out


def test_without_proc_a_reaped_makes_session_is_said_to_be_unlisted(tree):
    """With no /proc and make reaped elsewhere, nothing in make's session can
    be listed or signalled: the runner sends nothing, and run_target says what
    make left could not be listed and may still run."""
    _write_fake_make(tree / "bin", _SLEEPS, detach=True, exit_after=True)
    out = _in_child(
        tree,
        _RECORD_KILLPG
        + _MAKE_PID
        + _FOREIGN_WAITER
        + "r.resource_limits.session_members = lambda sid: None\n"
        "res = r.run_target('check', cwd='.', timeout=60, grace=2, "
        "snapshot=lambda root: {})\n"
        "print(json.dumps({'res': res, 'sent': sent}))\n",
    )
    pids = _pids(tree)
    try:
        assert _alive(pids[1]), "a leftover was signalled with no /proc to list it"
    finally:
        _cleanup(pids)
    got = json.loads(out)
    res = got["res"]
    assert got["sent"] == [], got
    assert res["reaped"] is True and res["ok"] is False and res["leaked"] == [], res
    assert "could not be listed" in res["output"], res["output"]
    assert "may still run" in res["output"], res["output"]


def test_a_make_reaped_elsewhere_fails_the_gate_naming_the_cause(
    proj, monkeypatch, capsys
):
    def reaped(cmd, cwd, timeout, grace):
        raise rmt.MakeReaped("made it\n", [], True)

    monkeypatch.setattr(rmt, "_default_runner", reaped)
    monkeypatch.setattr(rmt, "tree_snapshot", lambda root: {})
    code = rmt.main(["check", "--dir", str(proj)])
    captured = capsys.readouterr()
    assert code == rmt.ExitCode.FAILURE
    assert "made it" in captured.out and "-> FAIL (rc=None)" in captured.out
    last = captured.err.strip().splitlines()[-1]
    assert "another waiter" in last and "status" in last, last


def test_a_leftover_of_a_reaped_make_is_named_as_not_ended(proj):
    def reaped(cmd, cwd, timeout):
        raise rmt.MakeReaped("made it\n", [(4244, "python -c sleep")], True)

    res = rmt.run_target(
        "check",
        cwd=str(proj),
        runner=reaped,
        timeout=5,
        grace=1,
        snapshot=_snaps({}, {}),
    )
    assert res["ok"] is False and res["returncode"] is None, res
    assert res["leaked"] == ["4244 python -c sleep"], res
    assert "not ended" in res["output"] and "4244" in res["output"], res["output"]
    assert "were ended" not in res["output"], res["output"]


@pytest.mark.parametrize("unreadable", ["proc", "descriptors"])
def test_output_held_by_holders_the_runner_cannot_list_still_turns_the_run_red(
    tree, monkeypatch, unreadable
):
    """Fail closed when the holders cannot be named: a host with no /proc
    ("proc"), or descriptors another user owns ("descriptors"), still leave
    the output open, so the run is red with an unlisted escape."""
    _write_fake_make(tree / "bin", _OWN_SESSION, exit_after=True)
    real_listdir = os.listdir

    def listdir(path="."):
        path = str(path)
        if unreadable == "descriptors" and path.endswith("/fd"):
            raise PermissionError(13, "Permission denied", path)
        return real_listdir(path)

    def no_proc(inode):
        return None

    if unreadable == "proc":
        monkeypatch.setattr(rmt.resource_limits, "pipe_holders", no_proc)
    else:
        monkeypatch.setattr(rmt.os, "listdir", listdir)
    res = rmt.run_target(
        "check", cwd=str(tree), timeout=60, grace=1, snapshot=_snaps({}, {})
    )
    monkeypatch.undo()
    pids = _pids(tree)
    try:
        assert _alive(pids[1]), "the runner signalled a process outside make's session"
    finally:
        _cleanup(pids)
    assert res["returncode"] == 0 and res["leaked"] == [], res
    assert res["ok"] is False and res["escaped"] == ["(unlisted)"], res
    assert "ps -eo pid,sid,args" in res["output"], res["output"]


def test_a_sigterm_after_a_timed_out_make_is_reaped_signals_no_freed_id(tree):
    """A timeout ends make's session and marks it ending, so a SIGTERM that
    lands next goes straight to SIGKILL; once release has reaped make, that
    SIGKILL must not go to make's pid, which is free again."""
    make = _write_script(tree / "bin", "make", "import time\ntime.sleep(489)\n")
    out = _in_child(
        tree,
        _RECORD_KILLPG + "real_wait = r.subprocess.Popen.wait\n"
        "def wait(self, *a, **k):\n"
        "    got = real_wait(self, *a, **k)\n"
        "    if not terms:\n"
        "        os.kill(os.getpid(), signal.SIGTERM)\n"
        "    return got\n"
        "r.subprocess.Popen.wait = wait\n"
        "try:\n"
        "    r._default_runner([%r], '.', 2, grace=1)\n"
        "    what = 'returned'\n"
        "except r.subprocess.TimeoutExpired:\n"
        "    what = 'timed out'\n"
        "print(json.dumps({'what': what, 'sent': sent, 'terms': len(terms)}))\n"
        % str(make),
    )
    got = json.loads(out)
    assert got["what"] == "timed out" and got["terms"] == 1, got
    assert got["sent"] and all(held for _g, _s, held in got["sent"]), got
