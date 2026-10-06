"""
title: Unit — Claude Code headless backend (absent vs broken)
kind: tests
layer: backend
summary: Mirrors models/claude_code_headless.py. The adapter shells out to `claude -p` with the allowlisted environment plus the credential names config/project.json `models.credential_env` declares for it, so a planted cloud credential never reaches the CLI; a binary that is not on PATH is ModelUnavailable (absent — a caller may skip), a run that exits non-zero is RuntimeError (broken — a caller must not), and a clean run returns the stripped stdout. A broken allowlist is a ChildEnvError, never ModelUnavailable. No subprocess is ever started here.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from models import ModelUnavailable, get_model  # noqa: E402
from models import claude_code_headless as mod  # noqa: E402

pytestmark = pytest.mark.unit


def _fake_run(returncode=0, stdout="", stderr="", raise_=None):
    calls = []
    envs = []

    def run(cmd, capture_output, text, env):
        calls.append(cmd)
        envs.append(env)
        if raise_:
            raise raise_
        return subprocess.CompletedProcess(
            cmd, returncode, stdout=stdout, stderr=stderr
        )

    run.calls = calls
    run.envs = envs
    return run


def test_a_missing_binary_is_unavailable_not_a_traceback(monkeypatch):
    monkeypatch.setattr(
        mod.subprocess, "run", _fake_run(raise_=FileNotFoundError("claude"))
    )
    with pytest.raises(ModelUnavailable) as caught:
        get_model("claude-code-headless").run("hi")
    assert "not on PATH" in str(caught.value) and "fake" in str(caught.value)


def test_a_failing_run_is_a_runtime_error_and_not_unavailable(monkeypatch):
    """Present but broken must stay loud: a caller that skips on ModelUnavailable
    must NOT skip this."""
    monkeypatch.setattr(mod.subprocess, "run", _fake_run(returncode=2, stderr="boom"))
    with pytest.raises(RuntimeError) as caught:
        get_model("claude-code-headless").run("hi")
    assert type(caught.value) is RuntimeError and "boom" in str(caught.value)


def test_a_clean_run_returns_the_stripped_answer_and_the_command_is_headless(
    monkeypatch,
):
    run = _fake_run(stdout="  answer \n")
    monkeypatch.setattr(mod.subprocess, "run", run)
    assert (
        get_model("claude-code-headless", model="m1", binary="claude-x").run("q")
        == "answer"
    )
    assert run.calls == [["claude-x", "-p", "q", "--model", "m1"]]


def test_the_cli_child_gets_the_allowlist_plus_this_adapters_credentials(
    monkeypatch,
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "s")
    monkeypatch.setenv("KEEL_PLANTED_SECRET", "p")
    run = _fake_run(stdout="ok")
    monkeypatch.setattr(mod.subprocess, "run", run)
    assert get_model("claude-code-headless").run("q") == "ok"
    (env,) = run.envs
    assert env["ANTHROPIC_API_KEY"] == "k" and env["PATH"] == os.environ["PATH"]
    assert "AWS_SECRET_ACCESS_KEY" not in env and "KEEL_PLANTED_SECRET" not in env


def test_a_broken_allowlist_is_loud_and_not_unavailable(monkeypatch):
    """A caller that skips on ModelUnavailable must not skip a broken config."""

    class Broken(Exception):
        pass

    def broken(**_kw):
        raise Broken("config/project.json has no child_env block")

    monkeypatch.setattr(mod, "build_child_env", broken)
    monkeypatch.setattr(mod.subprocess, "run", _fake_run(stdout="ok"))
    with pytest.raises(Broken):
        get_model("claude-code-headless").run("q")


def test_unavailable_is_a_runtime_error_so_old_callers_still_catch_it():
    assert issubclass(ModelUnavailable, RuntimeError)
