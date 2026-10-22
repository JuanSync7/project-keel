"""
title: Unit — resource_limits (a bounded child)
kind: tests
layer: n/a
summary: scripts/resource_limits.py `run_bounded` starts a child through the child-process allowlist in its own process group and returns its status and output; a child that runs past its time limit, and one whose output passes its byte cap, has its whole group ended and is refused as ChildTimedOut or ChildOutputTooLarge, naming the program, the limit and the key the caller says sets that limit, and a grandchild holding the pipe open after its parent exits does not hold the call past the limit. Every child is a short Python one-liner under this interpreter; nothing reaches a network.
"""

import os
import sys
import time
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from scripts import resource_limits  # noqa: E402

pytestmark = pytest.mark.unit

_PY = sys.executable


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _gone_within(pid, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.02)
    return False


def test_a_child_within_its_limits_returns_status_and_output():
    done = resource_limits.run_bounded(
        [_PY, "-c", "import sys; print('out'); sys.stderr.write('err'); sys.exit(3)"],
        timeout=30,
        max_output_bytes=1024,
    )
    assert (done.returncode, done.stdout, done.stderr) == (3, "out\n", "err")


def test_input_reaches_the_child_and_cwd_is_honoured(tmp_path):
    done = resource_limits.run_bounded(
        [_PY, "-c", "import os, sys; print(os.getcwd()); print(sys.stdin.read())"],
        timeout=30,
        max_output_bytes=1 << 20,
        cwd=str(tmp_path),
        stdin_text="spec",
    )
    assert done.stdout.split("\n")[:2] == [str(tmp_path), "spec"]


def test_the_child_gets_the_allowlisted_environment(monkeypatch):
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "planted")
    done = resource_limits.run_bounded(
        [_PY, "-c", "import os; print(os.environ.get('AWS_SECRET_ACCESS_KEY'))"],
        timeout=30,
        max_output_bytes=1024,
    )
    assert done.stdout.strip() == "None"


def test_a_child_past_its_time_limit_has_its_group_ended_and_is_refused(tmp_path):
    pidfile = tmp_path / "grandchild.pid"
    # The grandchild outlives a plain kill of its parent: only ending the
    # group reaches it.
    script = (
        "import subprocess, sys, time;"
        "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']);"
        "open(%r, 'w').write(str(p.pid)); time.sleep(60)" % str(pidfile)
    )
    started = time.monotonic()
    with pytest.raises(resource_limits.ChildTimedOut) as caught:
        resource_limits.run_bounded(
            [_PY, "-c", script],
            timeout=1,
            max_output_bytes=1024,
            timeout_source="config/project.json models.timeout_seconds",
        )
    assert time.monotonic() - started < 15
    message = str(caught.value)
    assert "1 seconds" in message and "models.timeout_seconds" in message
    assert _gone_within(int(pidfile.read_text()), 5)


def test_a_grandchild_holding_the_pipe_does_not_hold_the_call(tmp_path):
    pidfile = tmp_path / "grandchild.pid"
    script = (
        "import subprocess, sys;"
        "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']);"
        "open(%r, 'w').write(str(p.pid))" % str(pidfile)
    )
    started = time.monotonic()
    with pytest.raises(resource_limits.ChildTimedOut):
        resource_limits.run_bounded([_PY, "-c", script], timeout=2, max_output_bytes=64)
    assert time.monotonic() - started < 15
    assert _gone_within(int(pidfile.read_text()), 5)


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_output_past_its_cap_ends_the_child_and_is_refused(stream):
    script = (
        "import sys, time; sys.%s.write('x' * 5000); sys.%s.flush(); time.sleep(60)"
    )
    started = time.monotonic()
    with pytest.raises(resource_limits.ChildOutputTooLarge) as caught:
        resource_limits.run_bounded(
            [_PY, "-c", script % (stream, stream)],
            timeout=30,
            max_output_bytes=4096,
            output_source="config/project.json models.max_reply_bytes",
        )
    assert time.monotonic() - started < 15
    message = str(caught.value)
    assert "4096 bytes" in message and "models.max_reply_bytes" in message


def test_output_exactly_at_the_cap_is_kept():
    done = resource_limits.run_bounded(
        [_PY, "-c", "import sys; sys.stdout.write('x' * 4096)"],
        timeout=30,
        max_output_bytes=4096,
    )
    assert done.stdout == "x" * 4096


def test_a_program_that_does_not_exist_is_file_not_found():
    with pytest.raises(FileNotFoundError):
        resource_limits.run_bounded(
            ["/nonexistent/keel-no-such-program"], timeout=5, max_output_bytes=64
        )


def test_a_limit_below_one_is_refused_before_a_child_starts():
    for kwargs in (
        {"timeout": 0, "max_output_bytes": 64},
        {"timeout": 5, "max_output_bytes": 0},
    ):
        with pytest.raises(ValueError):
            resource_limits.run_bounded(["/nonexistent/keel-no-such-program"], **kwargs)
