"""
title: Unit — run_make_target (the read-only gate runner)
kind: tests
layer: n/a
summary: run_target runs a make target only when its effect label, closed over its prerequisites, falls inside config/project.json `make_targets.gate_effects`; it refuses an unknown, unlabelled or wider target, an extra argument that is not a NAME=VALUE variable, a variable outside `make_targets.gate_vars` (make's control variables, the guard and the unattended variables among them), a value that is not one path-like word, a tree without git and a project without the policy, all without calling the runner. It passes the gate-runner variable last, so the Makefile's WRITE_GUARD refuses whatever the caller supplied, and fails a green run that changed the tree, naming the paths. A `make_targets.gate_vars` value found in the runner's own environment is forwarded on make's command line under the same one-word rule, an explicit one wins, and a bad one is refused before make runs. make and git get the allowlisted environment from scripts/child_env.py, never the runner's own. An allowlist that cannot be built, or that would copy a gate variable carrying a credential, is a refusal before anything runs and before any message could quote the value; a gate value, explicit or forwarded, that carries a credential is refused by name even when opted in, and no refusal quotes a value; and a ChildEnvError during the run or a tree that cannot be re-read afterwards is red, never a traceback. The runner and the snapshot are injected for those cases, so no make or git process runs in them. The default runner's own cases put a fake `make` (a short Python script) first on PATH that starts a grandchild, and prove that a timeout, a KeyboardInterrupt and a SIGTERM to the runner end the whole group, that an ignored SIGTERM is followed by SIGKILL after the grace, that a SIGTERM handler gets that grace, and that a process left behind after make exits is ended, named by pid and command, and turns a green make red while a failing make keeps its own status; each polls with a bound and kills only the pids it started. The time limit and grace come from config/project.json `make_targets` through scripts/config_loader.py, the loader's default when the key is absent, a bad value is CONFIG or a refusal naming the key, and `--timeout` overrides the configured limit.
"""

import base64
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

        def __init__(self, cmd, **kw):
            seen.append(kw)

        def communicate(self, timeout=None):
            return "", None

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
    monkeypatch.setattr(rmt.subprocess, "Popen", _Started)
    monkeypatch.setattr(rmt.os, "killpg", no_group)
    rmt._default_runner(["make", "x"], str(proj), 5, grace=1)
    rmt._git(str(proj), "status")
    assert len(seen) == 2
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
            os.kill(pid, signal.SIGKILL)


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
    ],
    ids=["zero", "string", "bool"],
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


@pytest.mark.parametrize("value", ["0", "-5"])
def test_a_timeout_flag_below_one_second_is_refused(proj, capsys, value):
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
