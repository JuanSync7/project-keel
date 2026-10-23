"""
title: Unit — resource_limits (a bounded child)
kind: tests
layer: n/a
summary: scripts/resource_limits.py `run_bounded` starts a child through the child-process allowlist in its own process group and returns its status and output; a child that runs past its time limit, and one whose output passes its byte cap, has its whole group ended and is refused as ChildTimedOut or ChildOutputTooLarge, naming the program, the limit and the key the caller says sets that limit, and a grandchild holding stdout or an unread stdin open after its parent exits holds the call for one drain window only, after which the parent's status and output are returned, not a timeout; a setsid grandchild, which no group kill reaches, leaves no reader or writer thread and no pipe open behind the call, and the call returns within its limit plus the drain window, timed out or not. An exception while the child runs ends its group. A limit past threading.TIMEOUT_MAX or NaN is refused before a child starts. `shutdown_owner` makes one named owner of SIGTERM and SIGINT for a server: the first signal writes a line naming the owner and the signal and calls the owner's stop, or raises ShutdownRequested (no Exception, so a request's own handler cannot eat it) only where the server says it is idle, and a second signal ends the process the default way; the handlers before it are put back. `cap_memory` sets RLIMIT_AS, proven in a child: an allocation past the cap is a MemoryError, one below it is not, and null says the cap is off. `serve_limits` reads config/project.json `transports.serve.memory_cap_mb` and `transports.serve.shutdown_grace_seconds`, refusing a value out of its bound by its key. Every child is a short Python one-liner under this interpreter; nothing reaches a network.
"""

import contextlib
import json
import os
import signal
import sys
import threading
import time
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from scripts import config_loader, resource_limits  # noqa: E402

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


def _kill(pidfile):
    # Cleanup for a test whose grandchild is outside run_bounded's reach.
    if pidfile.exists():
        with contextlib.suppress(ProcessLookupError):
            os.kill(int(pidfile.read_text()), signal.SIGKILL)


def _holder(pidfile, holds, new_session=False):
    """A child that starts a grandchild holding the pipes *holds* names
    (stdin, stdout) open without reading or writing them, prints `done`, and
    exits 0 at once."""
    redirect = {
        "stdin": "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL",
        "stdout": "stdin=subprocess.DEVNULL",
    }[holds]
    return (
        "import subprocess, sys;"
        "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'],"
        " %s, start_new_session=%r);"
        "open(%r, 'w').write(str(p.pid)); print('done')"
        % (redirect, new_session, str(pidfile))
    )


def _open_fds():
    return len(os.listdir("/proc/self/fd"))


def test_a_child_that_exits_while_a_grandchild_holds_the_pipe_returns_its_status(
    tmp_path,
):
    # The leader's exit ends the call: the grandchild gets one short drain
    # window, then its group is ended; the leader's status and output stand.
    pidfile = tmp_path / "grandchild.pid"
    started = time.monotonic()
    done = resource_limits.run_bounded(
        [_PY, "-c", _holder(pidfile, "stdout")], timeout=20, max_output_bytes=64
    )
    elapsed = time.monotonic() - started
    assert (done.returncode, done.stdout) == (0, "done\n")
    assert elapsed < 20 - 5, "the call waited on the grandchild, not the child"
    assert _gone_within(int(pidfile.read_text()), 5)


@pytest.mark.skipif(not os.path.isdir("/proc/self/fd"), reason="counts /proc fds")
@pytest.mark.parametrize("new_session", [False, True])
def test_a_grandchild_holding_stdin_unread_does_not_hold_the_call(
    tmp_path, new_session
):
    # A megabyte cannot fit the pipe, so the writer blocks until the drain
    # window stops it; a setsid grandchild is never ended, so only the stop
    # releases the writer's thread and pipe.
    pidfile = tmp_path / "grandchild.pid"
    threads, fds = threading.active_count(), _open_fds()
    started = time.monotonic()
    try:
        done = resource_limits.run_bounded(
            [_PY, "-c", _holder(pidfile, "stdin", new_session)],
            timeout=20,
            max_output_bytes=64,
            stdin_text="x" * 1000000,
        )
        elapsed = time.monotonic() - started
        assert (threading.active_count(), _open_fds()) == (threads, fds)
    finally:
        _kill(pidfile)
    assert done.returncode == 0
    assert elapsed < 20 - 5, "the stdin writer was waited on with no limit"


@pytest.mark.skipif(not os.path.isdir("/proc/self/fd"), reason="counts /proc fds")
@pytest.mark.parametrize("leader_sleeps", [0, 60])
def test_a_setsid_process_holding_the_pipe_leaks_no_thread_or_file(
    tmp_path, leader_sleeps
):
    # setsid takes the grandchild out of the group, so nothing ends it; the
    # call still returns within its limit plus one drain window, and releases
    # every reader thread and pipe it opened.
    pidfile = tmp_path / "grandchild.pid"
    script = _holder(pidfile, "stdout", new_session=True)
    script += "; import time; time.sleep(%d)" % leader_sleeps
    threads, fds = threading.active_count(), _open_fds()
    started = time.monotonic()
    try:
        if leader_sleeps:
            with pytest.raises(resource_limits.ChildTimedOut):
                resource_limits.run_bounded(
                    [_PY, "-c", script], timeout=2, max_output_bytes=64
                )
        else:
            done = resource_limits.run_bounded(
                [_PY, "-c", script], timeout=2, max_output_bytes=64
            )
            assert done.returncode == 0
        elapsed = time.monotonic() - started
        assert (threading.active_count(), _open_fds()) == (threads, fds)
    finally:
        _kill(pidfile)
    assert elapsed < 2 + resource_limits._DRAIN_S + 1.5


def test_an_exception_while_the_child_runs_ends_its_group(tmp_path, monkeypatch):
    # A KeyboardInterrupt in the wait stands in for any exception there: the
    # caller loses the child, so nothing else would end its group.
    pidfile = tmp_path / "grandchild.pid"
    script = (
        "import subprocess, sys, time;"
        "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']);"
        "open(%r, 'w').write(str(p.pid)); time.sleep(60)" % str(pidfile)
    )

    def interrupted(proc, deadline):
        while not pidfile.exists() or not pidfile.read_text():
            time.sleep(0.02)
        raise KeyboardInterrupt

    monkeypatch.setattr(resource_limits, "_await_exit", interrupted)
    try:
        with pytest.raises(KeyboardInterrupt):
            resource_limits.run_bounded([_PY, "-c", script], 30, 64)
        assert _gone_within(int(pidfile.read_text()), 5)
    finally:
        _kill(pidfile)


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


def test_a_limit_out_of_its_bound_is_refused_before_a_child_starts():
    # Past threading.TIMEOUT_MAX a thread wait raises OverflowError mid-call.
    for kwargs in (
        {"timeout": 0, "max_output_bytes": 64},
        {"timeout": 5, "max_output_bytes": 0},
        {"timeout": threading.TIMEOUT_MAX * 2, "max_output_bytes": 64},
        {"timeout": float("nan"), "max_output_bytes": 64},
    ):
        with pytest.raises(ValueError):
            resource_limits.run_bounded(["/nonexistent/keel-no-such-program"], **kwargs)


# --- the end of a server: shutdown_owner ---------------------------------------


def test_the_first_signal_calls_the_owner_s_stop_once_and_names_it(capsys):
    stopped = []
    with resource_limits.shutdown_owner("test server", stop=stopped.append) as owner:
        os.kill(os.getpid(), signal.SIGTERM)
        assert stopped == [signal.SIGTERM] and owner.signum == signal.SIGTERM
        # A second signal now ends the process the default way.
        assert signal.getsignal(signal.SIGTERM) is signal.SIG_DFL
        assert signal.getsignal(signal.SIGINT) is signal.SIG_DFL
    assert "test server: stopping on SIGTERM" in capsys.readouterr().err


def test_the_handlers_before_the_owner_are_put_back():
    before = signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT)
    with resource_limits.shutdown_owner("test server"):
        assert signal.getsignal(signal.SIGTERM) not in before
    assert (signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT)) == before


def test_a_signal_while_idle_raises_shutdown_requested():
    with resource_limits.shutdown_owner("test server") as owner:
        with pytest.raises(resource_limits.ShutdownRequested), owner.idle():
            os.kill(os.getpid(), signal.SIGINT)
            time.sleep(5)
        assert owner.signum == signal.SIGINT


def test_a_signal_while_busy_is_held_until_the_owner_is_next_idle():
    with resource_limits.shutdown_owner("test server") as owner:
        os.kill(os.getpid(), signal.SIGTERM)  # busy: noted, nothing raised
        assert owner.signum == signal.SIGTERM
        with pytest.raises(resource_limits.ShutdownRequested), owner.idle():
            raise AssertionError("idle() must refuse once a stop was asked for")


def test_shutdown_requested_is_not_caught_by_a_generic_handler():
    # A server's `except Exception` around one request must not eat the stop.
    assert not issubclass(resource_limits.ShutdownRequested, Exception)


# --- the memory cap: cap_memory, in a child so this process keeps its limit ----

_CAP_CHILD = (
    "import sys; sys.path.insert(0, %r)\n"
    "from scripts import resource_limits\n"
    "print(resource_limits.cap_memory(%s))\n"
    "try:\n"
    "    block = bytearray(%d << 20)\n"
    "    print('allocated')\n"
    "except MemoryError:\n"
    "    print('refused')\n"
)


def _capped(cap_mb, alloc_mb):
    done = resource_limits.run_bounded(
        [_PY, "-c", _CAP_CHILD % (str(_ROOT), cap_mb, alloc_mb)],
        timeout=60,
        max_output_bytes=4096,
    )
    assert done.returncode == 0, done.stderr
    return done.stdout.splitlines()


@pytest.mark.skipif(not hasattr(os, "fork"), reason="RLIMIT_AS is a POSIX limit")
def test_an_allocation_past_the_cap_is_refused_and_one_below_it_is_not():
    status, verdict = _capped(1024, 2048)
    assert status.startswith("memory cap: 1024 MB of address space")
    assert verdict == "refused"
    assert _capped(1024, 64)[1] == "allocated"


def test_no_cap_is_said_and_allocates_freely():
    status, verdict = _capped(None, 64)
    assert status.startswith("memory cap: off") and verdict == "allocated"


def test_a_cap_below_one_megabyte_is_refused():
    for bad in (0, -1, True, 1.5):
        with pytest.raises(ValueError):
            resource_limits.cap_memory(bad)


# --- what a server reads: serve_limits ------------------------------------------


def _project(tmp_path, serve_block):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.json").write_text(
        json.dumps({"transports": {"serve": serve_block}}), encoding="utf-8"
    )
    return str(tmp_path)


def test_serve_limits_are_read_from_the_transports_block(tmp_path):
    root = _project(tmp_path, {"memory_cap_mb": 512, "shutdown_grace_seconds": 2.5})
    assert resource_limits.serve_limits(root) == (512, 2.5)
    root2 = tmp_path / "off"
    root2.mkdir()
    assert (
        resource_limits.serve_limits(_project(root2, {"memory_cap_mb": None}))[0]
        is None
    )


@pytest.mark.parametrize(
    "block, key",
    [
        ({"memory_cap_mb": 0}, r"transports\.serve\.memory_cap_mb"),
        ({"memory_cap_mb": "1G"}, r"transports\.serve\.memory_cap_mb"),
        ({"shutdown_grace_seconds": -1}, r"transports\.serve\.shutdown_grace_seconds"),
    ],
)
def test_a_serve_limit_out_of_its_bound_is_refused(tmp_path, block, key):
    with pytest.raises(config_loader.WrongValue, match=key):
        resource_limits.serve_limits(_project(tmp_path, block))


def test_the_shipped_serve_limits():
    assert resource_limits.serve_limits() == (4096, 10)
