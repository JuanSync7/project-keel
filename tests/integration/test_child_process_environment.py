"""
title: Integration — a child process sees only the allowlisted environment
kind: tests
layer: n/a
summary: Driven through real make, git and a fake model CLI. A target the gate runner starts prints an environment holding none of the credentials planted in the parent, yet holding PATH and the gate-runner variable. The interpreter choice (`PY`, a `make_targets.gate_vars` name) and the write guard (`RALPH`, a `make_targets.unattended_vars` name) both survive a hop through a Python process that builds its child's environment with scripts/child_env.py. The claude-code-headless adapter hands its CLI the credential names config/project.json `models.credential_env` declares for it and no other planted credential.
"""

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


def _probe_repo(tmp_path):
    (tmp_path / "config").mkdir()
    shutil.copy(str(_ROOT / "config" / "project.json"), str(tmp_path / "config"))
    (tmp_path / "Makefile").write_text(_PROBE, encoding="utf-8")
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
