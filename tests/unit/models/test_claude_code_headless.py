"""
title: Unit — Claude Code headless backend (absent vs broken)
kind: tests
layer: backend
summary: Mirrors models/claude_code_headless.py. The adapter shells out to `claude -p`; a binary that is not on PATH is ModelUnavailable (absent — a caller may skip), a run that exits non-zero is RuntimeError (broken — a caller must not), and a clean run returns the stripped stdout. No subprocess is ever started here.
"""

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

    def run(cmd, capture_output, text):
        calls.append(cmd)
        if raise_:
            raise raise_
        return subprocess.CompletedProcess(
            cmd, returncode, stdout=stdout, stderr=stderr
        )

    run.calls = calls
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


def test_unavailable_is_a_runtime_error_so_old_callers_still_catch_it():
    assert issubclass(ModelUnavailable, RuntimeError)
