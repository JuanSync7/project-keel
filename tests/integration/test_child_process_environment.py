"""
title: Integration — a child process sees only the allowlisted environment
kind: tests
layer: n/a
summary: Driven through real make, git and a fake model CLI. A target the gate runner starts prints an environment holding none of the credentials planted in the parent, yet holding PATH and the gate-runner variable. The interpreter choice (`PY`, a `make_targets.gate_vars` name) and the write guard (`RALPH`, a `make_targets.unattended_vars` name) both survive a hop through a Python process that builds its child's environment with scripts/child_env.py. The claude-code-headless adapter hands its CLI the credential names config/project.json `models.credential_env` declares for it and no other planted credential. A proxy URL carrying a password refuses the gate run by name, and the password appears nowhere in its result.
"""

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT))

import run_make_target as rmt  # noqa: E402
from models import get_model  # noqa: E402

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("make") is None, reason="make not installed"),
    pytest.mark.skipif(shutil.which("git") is None, reason="git not installed"),
]

_PLANTED = {
    "AWS_SECRET_ACCESS_KEY": "s",
    "GITHUB_TOKEN": "g",
    "KEEL_PLANTED_SECRET": "p",
}
# make hands its command-line variables to a child through these. A suite run
# under the gate runner carries them, and they would mask whether the allowlist,
# not make's own inheritance, carried a variable across the hop.
_MAKE_INHERITANCE = ("MAKEFLAGS", "MFLAGS", "MAKELEVEL", "MAKEOVERRIDES")
# A plain `=`, not keel's `?=`: the environment cannot override it, only make's
# command line can, so this probe shows the runner forwarded PY onto argv.
_PROBE = (
    "PY = python3-from-the-makefile\n"
    "probe: ## [local] Print the environment and the interpreter choice\n"
    "\t@env | sort\n"
    "\t@echo PY=$(PY)\n"
)
_DEMO = (
    "include Makefile\n"
    "\n"
    "demo-apply: ## [write] Change shared state (a demo)\n"
    "\t$(WRITE_GUARD)\n"
    "\t@echo applied > applied.txt\n"
)


def _probe_repo(tmp_path, makefile=_PROBE):
    (tmp_path / "config").mkdir()
    shutil.copy(str(_ROOT / "config" / "project.json"), str(tmp_path / "config"))
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    for argv in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "fixture"]):
        r = subprocess.run(["git"] + argv, cwd=str(tmp_path), capture_output=True)
        assert r.returncode == 0, r.stderr
    return tmp_path


def _names(output):
    return {ln.split("=", 1)[0] for ln in output.splitlines() if "=" in ln}


def test_a_gate_run_child_sees_no_planted_secret(tmp_path, monkeypatch):
    for key, value in _PLANTED.items():
        monkeypatch.setenv(key, value)
    repo = _probe_repo(tmp_path)
    res = rmt.run_target("probe", cwd=str(repo))
    assert res["ok"] is True, res
    out = str(res["output"])
    assert not set(_PLANTED) & _names(out), out
    assert "PATH" in _names(out) and "\nRALPH=1\n" in "\n" + out, out


def test_a_credentialed_proxy_never_reaches_a_gate_run_child(tmp_path, monkeypatch):
    """Through real make and git: a proxy URL carrying a password is an
    allowlisted name with a credential in its value. The run is refused by
    name, the password appears nowhere in the result, and the same probe
    without the variable runs (the control). The opt-in is not exercised: the
    runner builds the environment from keel's own config, not the probe's."""
    repo = _probe_repo(tmp_path)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    assert rmt.run_target("probe", cwd=str(repo))["ok"] is True
    monkeypatch.setenv("HTTPS_PROXY", "http://alice:s3cr3t-pw@127.0.0.1:9")
    res = rmt.run_target("probe", cwd=str(repo))
    assert res["ok"] is False and res["refused"], res
    assert "HTTPS_PROXY" in res["refused"], res
    assert "s3cr3t-pw" not in json.dumps(res), "the result carries the password"


def test_the_interpreter_choice_survives_a_python_hop(tmp_path, monkeypatch):
    """An agent starts the runner the way agents/*/_brain.py `_run` does: a Python
    child with the allowlisted environment and no `--make-arg`. PY is still what
    the parent chose, not the Makefile's default."""
    import child_env  # here, not at the top: the other cases need no helper import

    monkeypatch.setenv("PY", sys.executable)
    for key in _MAKE_INHERITANCE:
        monkeypatch.delenv(key, raising=False)
    repo = _probe_repo(tmp_path)
    r = subprocess.run(
        [sys.executable, "-B", str(_ROOT / "scripts" / "run_make_target.py")]
        + ["probe", "--dir", str(repo)],
        cwd=str(_ROOT),
        env=child_env.build_child_env(),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "\nPY=%s\n" % sys.executable in r.stdout, r.stdout
    assert "python3-from-the-makefile" not in r.stdout, r.stdout


def test_the_write_guard_survives_a_python_hop(tmp_path):
    """RALPH reaches the hop's environment the way a gate run puts it there; the
    nested make is started by Python with the allowlisted environment, and the
    guard still refuses."""
    shutil.copy(str(_ROOT / "Makefile"), str(tmp_path / "Makefile"))
    (tmp_path / "demo.mk").write_text(_DEMO, encoding="utf-8")
    parent = {k: v for k, v in os.environ.items() if k not in _MAKE_INHERITANCE}
    parent["RALPH"] = "1"
    hop = (
        "import subprocess, sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "import child_env\n"
        "sys.exit(subprocess.run(['make', '-s', '-f', 'demo.mk', 'demo-apply'],"
        " env=child_env.build_child_env()).returncode)\n"
    )
    r = subprocess.run(
        [sys.executable, "-B", "-c", hop, str(_ROOT / "scripts")],
        cwd=str(tmp_path),
        env=parent,
        capture_output=True,
        text=True,
    )
    # make exits 2 when a recipe fails; the guard's refusal is that failure.
    assert r.returncode == 2, r.stdout + r.stderr
    assert "refusing 'demo-apply'" in r.stderr, r.stderr
    assert not (tmp_path / "applied.txt").exists()


def test_the_model_adapter_child_gets_only_its_declared_credentials(
    tmp_path, monkeypatch
):
    fake = tmp_path / "fake-cli"
    fake.write_text("#!/bin/sh\nenv\n", encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    for key, value in _PLANTED.items():
        monkeypatch.setenv(key, value)
    out = get_model("claude-code-headless", binary=str(fake)).run("q")
    assert "ANTHROPIC_API_KEY=k" in out.splitlines(), out
    assert not set(_PLANTED) & _names(out), out


# A recipe whose git answers for whichever repository its environment selects.
_WHERE = "where: ## [local] Print the repository git sees\n\t@git rev-parse --absolute-git-dir\n"


def _git_repo(top):
    top.mkdir()
    (top / "a").write_text("a\n", encoding="utf-8")
    for argv in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "decoy"]):
        r = subprocess.run(["git"] + argv, cwd=str(top), capture_output=True)
        assert r.returncode == 0, r.stderr


def test_a_gate_run_in_another_repository_ignores_the_hooks_repository(tmp_path):
    """A pre-commit hook exports GIT_DIR/GIT_INDEX_FILE for the repository being
    committed. A gate the hook starts in another checkout must see that
    checkout: the recipe's git answers for probe/, and the hook repository's
    index is neither read into nor rewritten."""
    (tmp_path / "probe").mkdir()
    probe = _probe_repo(tmp_path / "probe", makefile=_WHERE)
    decoy = tmp_path / "decoy"
    _git_repo(decoy)
    index = decoy / ".git" / "index"
    before = index.read_bytes(), index.stat().st_mtime_ns
    parent = {k: v for k, v in os.environ.items() if k not in _MAKE_INHERITANCE}
    parent.update(GIT_DIR=str(decoy / ".git"), GIT_INDEX_FILE=str(index))
    r = subprocess.run(
        [sys.executable, "-B", str(_ROOT / "scripts" / "run_make_target.py")]
        + ["where", "--dir", str(probe)],
        cwd=str(_ROOT),
        env=parent,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    printed = [ln for ln in r.stdout.splitlines() if ln.endswith("/.git")]
    assert [Path(p).resolve() for p in printed] == [(probe / ".git").resolve()], (
        r.stdout
    )
    assert (index.read_bytes(), index.stat().st_mtime_ns) == before


def test_the_test_suite_drops_the_parent_repository_at_import(tmp_path, monkeypatch):
    """tests/hermetic_git.py and copier run git with the suite's own environment,
    not through build_child_env. A pytest started from a hook must not hand them
    the committing repository: conftest strips the names at import (before
    plumbum snapshots os.environ), and git_env() never carries them."""
    import child_env

    import hermetic_git

    tests = _ROOT / "tests"
    hook = {
        "GIT_DIR": "/decoy/.git",
        "GIT_INDEX_FILE": "/decoy/.git/index",
        "GIT_PREFIX": "sub/",
    }
    pythonpath = os.pathsep.join(str(p) for p in (tests, _ROOT / "scripts", _ROOT))
    r = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            "import conftest, os, json; print(json.dumps(dict(os.environ)))",
        ],
        cwd=str(tests),
        env=child_env.build_child_env(extra=dict(hook, PYTHONPATH=pythonpath)),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    seen = json.loads(r.stdout)
    assert not set(hook) & set(seen), sorted(set(hook) & set(seen))
    assert "GIT_CONFIG_GLOBAL" in seen, sorted(seen)  # the hermetic update still ran

    for key, value in hook.items():
        monkeypatch.setenv(key, value)
    env = hermetic_git.git_env(tmp_path)
    assert not set(hook) & set(env), sorted(set(hook) & set(env))
    assert set(hermetic_git.repo_context_names(_ROOT)) >= set(hook)
