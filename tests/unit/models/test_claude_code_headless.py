"""
title: Unit — Claude Code headless backend (absent vs broken, and bounded)
kind: tests
layer: backend
summary: Mirrors models/claude_code_headless.py. The adapter runs `claude -p` through scripts/resource_limits.py run_bounded with the allowlisted environment plus the credential names config/project.json `models.credential_env` declares for it, so a planted cloud credential never reaches the CLI; a binary that is not on PATH is ModelUnavailable (absent — a caller may skip), a run that exits non-zero is RuntimeError (broken — a caller must not), and a clean run returns the stripped stdout. The CLI's time limit is config/project.json `models.timeout_seconds.claude-code-headless` and its output cap `models.max_reply_bytes`: a CLI past either has its process group ended and is a RuntimeError naming the key, never ModelUnavailable. A broken allowlist is a ChildEnvError, never ModelUnavailable. The CLI is a stand-in Python script written into the test's own directory; no real CLI is started.
"""

import json
import os
import stat
import sys
import time
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from models import ModelUnavailable, get_model  # noqa: E402
from models import claude_code_headless as mod  # noqa: E402
from scripts import child_env, resource_limits  # noqa: E402

pytestmark = pytest.mark.unit


def _cli(tmp_path, body):
    """A stand-in for the CLI: an executable Python script running *body*, with
    its argv in `args`."""
    path = tmp_path / "claude-stand-in"
    path.write_text(
        "#!%s\nimport json, os, sys, time\nargs = sys.argv[1:]\n%s\n"
        % (sys.executable, body),
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


def _limits(monkeypatch, seconds=30.0, cap=1 << 20):
    monkeypatch.setattr(mod, "timeout_seconds", lambda adapter, root=None: seconds)
    monkeypatch.setattr(mod, "max_reply_bytes", lambda root=None: cap)


def test_a_missing_binary_is_unavailable_not_a_traceback(monkeypatch, tmp_path):
    _limits(monkeypatch)
    with pytest.raises(ModelUnavailable) as caught:
        get_model("claude-code-headless", binary=str(tmp_path / "absent")).run("hi")
    assert "not on PATH" in str(caught.value) and "fake" in str(caught.value)


def test_a_failing_run_is_a_runtime_error_and_not_unavailable(monkeypatch, tmp_path):
    """Present but broken must stay loud: a caller that skips on ModelUnavailable
    must NOT skip this."""
    _limits(monkeypatch)
    cli = _cli(tmp_path, "sys.stderr.write('boom'); sys.exit(2)")
    with pytest.raises(RuntimeError) as caught:
        get_model("claude-code-headless", binary=cli).run("hi")
    assert type(caught.value) is RuntimeError and "boom" in str(caught.value)


def test_a_clean_run_returns_the_stripped_answer_and_the_command_is_headless(
    monkeypatch, tmp_path
):
    _limits(monkeypatch)
    cli = _cli(tmp_path, "print('  ' + json.dumps(args) + ' ')")
    answer = get_model("claude-code-headless", model="m1", binary=cli).run("q")
    assert json.loads(answer) == ["-p", "q", "--model", "m1"]


def test_the_cli_child_gets_the_allowlist_plus_this_adapters_credentials(
    monkeypatch, tmp_path
):
    _limits(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "s")
    monkeypatch.setenv("KEEL_PLANTED_SECRET", "p")
    cli = _cli(tmp_path, "print(json.dumps(dict(os.environ)))")
    env = json.loads(get_model("claude-code-headless", binary=cli).run("q"))
    assert env["ANTHROPIC_API_KEY"] == "k" and env["PATH"] == os.environ["PATH"]
    assert "AWS_SECRET_ACCESS_KEY" not in env and "KEEL_PLANTED_SECRET" not in env


def test_a_cli_past_its_time_limit_is_ended_and_broken_not_absent(
    monkeypatch, tmp_path
):
    _limits(monkeypatch, seconds=1.0)
    cli = _cli(tmp_path, "time.sleep(60)")
    started = time.monotonic()
    with pytest.raises(resource_limits.ChildTimedOut) as caught:
        get_model("claude-code-headless", binary=cli).run("q")
    assert time.monotonic() - started < 15
    assert not isinstance(caught.value, ModelUnavailable)
    assert "models.timeout_seconds.claude-code-headless" in str(caught.value)


def test_a_cli_reply_past_the_cap_is_ended_and_refused(monkeypatch, tmp_path):
    _limits(monkeypatch, cap=100)
    cli = _cli(
        tmp_path, "sys.stdout.write('x' * 5000); sys.stdout.flush(); time.sleep(60)"
    )
    with pytest.raises(resource_limits.ChildOutputTooLarge) as caught:
        get_model("claude-code-headless", binary=cli).run("q")
    assert not isinstance(caught.value, ModelUnavailable)
    assert "models.max_reply_bytes" in str(caught.value)


def test_the_limits_default_to_this_adapter_s_configured_values(monkeypatch):
    asked = []

    def fake(argv, timeout, max_output_bytes, **kw):
        asked.append((timeout, max_output_bytes, kw["credentials_for"]))
        return resource_limits.subprocess.CompletedProcess(argv, 0, "ok", "")

    monkeypatch.setattr(
        mod,
        "timeout_seconds",
        lambda adapter, root=None: {"claude-code-headless": 12.0}[adapter],
    )
    monkeypatch.setattr(mod, "max_reply_bytes", lambda root=None: 34)
    monkeypatch.setattr(mod, "run_bounded", fake)
    assert get_model("claude-code-headless").run("q") == "ok"
    assert asked == [(12.0, 34, "claude-code-headless")]


def test_a_broken_allowlist_is_loud_and_not_unavailable(monkeypatch, tmp_path):
    """A caller that skips on ModelUnavailable must not skip a broken config."""
    _limits(monkeypatch)

    def broken(**_kw):
        raise child_env.ChildEnvError("config/project.json has no child_env block")

    monkeypatch.setattr(resource_limits, "build_child_env", broken)
    cli = _cli(tmp_path, "print('ok')")
    with pytest.raises(child_env.ChildEnvError):
        get_model("claude-code-headless", binary=cli).run("q")


def test_unavailable_is_a_runtime_error_so_old_callers_still_catch_it():
    assert issubclass(ModelUnavailable, RuntimeError)
