"""
title: Unit — resource_limits (a bounded child)
kind: tests
layer: n/a
summary: scripts/resource_limits.py `run_bounded` starts a child through the child-process allowlist in a session of its own and returns its status and output; a child that runs past its time limit, and one whose output passes its byte cap, has its whole session ended and is refused as ChildTimedOut or ChildOutputTooLarge, naming the program, the limit and the key the caller says sets that limit, and a grandchild holding stdout or an unread stdin open after its parent exits holds the call for one drain window only, after which the parent's status and output are returned, not a timeout; a setsid grandchild, which leaves the session and so no session end reaches, leaves no reader or writer thread and no pipe open behind the call, and the call returns within its limit plus the drain window, timed out or not. An exception while the child runs ends its session. A process the child left in its session is ended and named in a log warning by pid and program, never by its arguments; a holder outside the session is named and not signalled. Each of these, proven in a child interpreter, ends the bounded child: a SIGTERM to a plain CLI with no handler (the child ends, then the CLI by SIGTERM), a SIGKILL to the runner (the watcher ends the child's session), and a server stopped by one signal returning from shutdown_owner while a request thread waits on a child (the watcher disabled in that probe, so only the owner's end is measured). An ignored SIGCHLD is set to its default for the run and put back, and off the main thread the run is refused as ChildSignalIgnored. A time limit past threading.TIMEOUT_MAX or NaN, and a byte cap that is no whole number or past sys.maxsize, are refused before a child starts; a byte cap past threading.TIMEOUT_MAX, a seconds constant, is accepted by run_bounded and by tool_limits. tool_limits refuses a margin one past the most that leaves the gate keys plus it within threading.TIMEOUT_MAX, naming the margin and that most, and accepts that most. `shutdown_owner` makes one named owner of SIGTERM and SIGINT for a server: the first signal writes a line naming the owner and the signal and calls the owner's stop, or raises ShutdownRequested (no Exception, so a request's own handler cannot eat it) only where the server says it is idle, and a second signal, proven in a child that runs `run_bounded` under the owner, ends the bounded child's session (its pid no longer runs) and then the owner's process by that signal, SIGTERM and SIGINT alike; the handlers before it are put back. `cap_memory` sets RLIMIT_AS, proven in a child: an allocation past the cap is a MemoryError, one below it is not, and null says the cap is off; a cap past a hard limit the child lowered first sets the hard limit and the line says it was lowered to it. `serve_limits` reads config/project.json `transports.serve.memory_cap_mb` and `transports.serve.shutdown_grace_seconds`, refusing a value out of its bound by its key. Every child is a short Python one-liner under this interpreter; nothing reaches a network.
"""

import contextlib
import json
import os
import signal
import subprocess
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


def test_a_child_past_its_time_limit_has_its_session_ended_and_is_refused(tmp_path):
    pidfile = tmp_path / "grandchild.pid"
    # The grandchild outlives a plain kill of its parent: only ending the
    # session reaches it.
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

    def interrupted(session, deadline):
        while not pidfile.exists() or not pidfile.read_text():
            time.sleep(0.02)
        raise KeyboardInterrupt

    monkeypatch.setattr(resource_limits.ChildSession, "wait_exit", interrupted)
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
        {"timeout": 5, "max_output_bytes": sys.maxsize + 1},
        {"timeout": 5, "max_output_bytes": 64.0},
    ):
        with pytest.raises(ValueError):
            resource_limits.run_bounded(["/nonexistent/keel-no-such-program"], **kwargs)


def test_a_byte_cap_past_the_seconds_ceiling_is_accepted():
    # A byte cap is a length, bounded by sys.maxsize, not by
    # threading.TIMEOUT_MAX, which bounds a number of seconds.
    done = resource_limits.run_bounded(
        [_PY, "-c", "print('ok')"],
        timeout=30,
        max_output_bytes=int(threading.TIMEOUT_MAX) + 1,
    )
    assert (done.returncode, done.stdout) == (0, "ok\n")


# --- the end of a server: shutdown_owner ---------------------------------------


def test_the_first_signal_calls_the_owner_s_stop_once_and_names_it(capsys):
    stopped = []
    with resource_limits.shutdown_owner("test server", stop=stopped.append) as owner:
        first = signal.getsignal(signal.SIGTERM)
        os.kill(os.getpid(), signal.SIGTERM)
        assert stopped == [signal.SIGTERM] and owner.signum == signal.SIGTERM
        # A second signal now ends the process, by the handler the next test
        # proves in a child; the first handler is not called twice.
        for owned in (signal.SIGTERM, signal.SIGINT):
            assert signal.getsignal(owned) not in (first, signal.SIG_DFL), owned
    assert "test server: stopping on SIGTERM" in capsys.readouterr().err


_SECOND_SIGNAL_PROBE = (
    "import sys; sys.path.insert(0, %r)\n"
    "from scripts import resource_limits\n"
    # No watcher, so only the second signal's handler can end the child.
    "resource_limits._watch = lambda pid: None\n"
    "with resource_limits.shutdown_owner('probe'):\n"
    "    resource_limits.run_bounded(\n"
    "        ['sh', '-c', 'echo $$ > %s; exec sleep 47'], timeout=30, "
    "max_output_bytes=1000\n"
    "    )\n"
)


def _running(pid):
    """Alive and not a zombie: a killed child waits as one until reaped."""
    try:
        with open("/proc/%d/stat" % pid) as stat:
            return stat.read().rsplit(")", 1)[1].split()[0] != "Z"
    except FileNotFoundError:
        return False


def _wait_for(predicate, seconds, what):
    deadline = time.monotonic() + seconds
    while not predicate():
        assert time.monotonic() < deadline, what
        time.sleep(0.02)


@pytest.mark.skipif(not os.path.isdir("/proc"), reason="reads a pid's state in /proc")
@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGINT])
def test_a_second_signal_ends_the_bounded_child_s_session_and_then_the_process(
    tmp_path, signum
):
    """A run_bounded child runs in a session of its own, which a signal to
    the server never reaches; the second stop ends that session before the
    server ends by the signal's default action (exit status 128 + signal in a
    shell), so no child outlives it."""
    from scripts.child_env import build_child_env

    pid_file = tmp_path / "child.pid"
    err_file = tmp_path / "probe.err"
    child = None
    with open(str(err_file), "w") as err:
        probe = subprocess.Popen(
            [_PY, "-c", _SECOND_SIGNAL_PROBE % (str(_ROOT), pid_file)],
            cwd=str(_ROOT),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=err,
            env=build_child_env(),
        )
    try:
        _wait_for(
            lambda: pid_file.read_text().endswith("\n") if pid_file.exists() else False,
            10,
            "the bounded child never started",
        )
        child = int(pid_file.read_text())
        os.kill(probe.pid, signum)
        _wait_for(
            lambda: "probe: stopping on" in err_file.read_text(),
            10,
            "the probe never saw the first signal",
        )
        assert probe.poll() is None, "the first signal is a request, not the end"
        # The owner holds the first signal: a bounded child keeps running
        # until a second one, or until the server's stop has run its course.
        assert _running(child), "the first signal ended the bounded child"
        os.kill(probe.pid, signum)
        assert probe.wait(10) == -signum, err_file.read_text()
        _wait_for(lambda: not _running(child), 5, "the bounded child outlived it")
    finally:
        if probe.poll() is None:
            probe.kill()
            probe.wait()
        if child is not None and _running(child):
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(child, signal.SIGKILL)


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


# --- the child's session outlives no runner ------------------------------------
#
# Each case runs a probe interpreter that calls run_bounded, so a signal or a
# kill reaches the probe and never this test process. The bounded child writes
# its pid and then execs a sleep, so its pid is the session's id.

_PROBE_HEAD = (
    "import json, os, signal, sys, threading, time\n"
    "sys.path.insert(0, %r)\n"
    "from scripts import resource_limits\n"
)
# Leaves the termination handler as the only teardown a probe has, so a case
# that proves the handler is not passed by the watcher instead.
_NO_WATCHER = "resource_limits._watch = lambda pid: None\n"


def _sleeper(pid_file):
    return "['sh', '-c', 'echo $$ > %s; exec sleep 47']" % pid_file


def _start_probe(tmp_path, body):
    from scripts.child_env import build_child_env

    # The probe keeps its own copy of the descriptor, so this one closes here.
    with open(str(tmp_path / "probe.err"), "w") as err:
        return subprocess.Popen(
            [_PY, "-c", _PROBE_HEAD % str(_ROOT) + body],
            cwd=str(tmp_path),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=err,
            env=build_child_env(),
        )


def _started_child(pid_file):
    _wait_for(
        lambda: pid_file.read_text().endswith("\n") if pid_file.exists() else False,
        10,
        "the bounded child never started",
    )
    return int(pid_file.read_text())


def _reap_probe(probe, child):
    if probe.poll() is None:
        probe.kill()
    probe.wait()
    probe.stdout.close()
    if child is not None and _running(child):
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(child, signal.SIGKILL)


@pytest.mark.skipif(not os.path.isdir("/proc"), reason="reads a pid's state in /proc")
def test_a_sigterm_to_a_plain_cli_ends_its_bounded_child_then_the_cli(tmp_path):
    """A command-line caller with no handler of its own: SIGTERM ends the
    bounded child's session first, then the caller by the signal, with no
    watcher to do it for the handler."""
    pid_file = tmp_path / "child.pid"
    probe = _start_probe(
        tmp_path,
        _NO_WATCHER
        + "resource_limits.run_bounded(%s, timeout=60, max_output_bytes=1000)\n"
        % _sleeper(pid_file),
    )
    child = None
    try:
        child = _started_child(pid_file)
        os.kill(probe.pid, signal.SIGTERM)
        assert probe.wait(10) == -signal.SIGTERM
        _wait_for(lambda: not _running(child), 5, "the bounded child outlived it")
    finally:
        _reap_probe(probe, child)


@pytest.mark.skipif(not os.path.isdir("/proc"), reason="reads a pid's state in /proc")
def test_a_sigkilled_runner_leaves_no_bounded_child_running(tmp_path):
    """SIGKILL gives the runner no handler and no unwinding; the watcher
    started beside the child sees its pipe close and ends the session."""
    pid_file = tmp_path / "child.pid"
    probe = _start_probe(
        tmp_path,
        "resource_limits.run_bounded(%s, timeout=60, max_output_bytes=1000)\n"
        % _sleeper(pid_file),
    )
    child = None
    try:
        child = _started_child(pid_file)
        os.kill(probe.pid, signal.SIGKILL)
        assert probe.wait(10) == -signal.SIGKILL
        _wait_for(lambda: not _running(child), 10, "the bounded child outlived it")
    finally:
        _reap_probe(probe, child)


@pytest.mark.skipif(not os.path.isdir("/proc"), reason="reads a pid's state in /proc")
def test_a_server_stopped_once_ends_the_bounded_children_still_running(tmp_path):
    """A request thread still in run_bounded when a server's stop has run
    its course would hold the process's exit for the child's whole limit;
    leaving the owner after a stop ends that child, so the thread returns."""
    pid_file = tmp_path / "child.pid"
    probe = _start_probe(
        tmp_path,
        "got = {}\n"
        "def request():\n"
        "    got['rc'] = resource_limits.run_bounded(%s, timeout=60, "
        "max_output_bytes=1000).returncode\n"
        "stopped = threading.Event()\n"
        "with resource_limits.shutdown_owner('probe', stop=lambda s: stopped.set()):\n"
        "    t = threading.Thread(target=request)\n"
        "    t.start()\n"
        "    while not os.path.exists(%r):\n"
        "        time.sleep(0.02)\n"
        "    time.sleep(0.2)\n"
        "    os.kill(os.getpid(), signal.SIGTERM)\n"
        "    stopped.wait(10)\n"
        "t.join(10)\n"
        "print(json.dumps({'returned': not t.is_alive(), 'rc': got.get('rc')}))\n"
        % (_sleeper(pid_file), str(pid_file)),
    )
    try:
        out, _ = probe.communicate(timeout=30)
        got = json.loads(out)
        assert got == {"returned": True, "rc": -signal.SIGKILL}, got
    finally:
        _reap_probe(probe, int(pid_file.read_text()) if pid_file.exists() else None)


def test_a_leftover_in_the_session_is_ended_and_named_without_its_arguments(
    tmp_path, caplog
):
    pidfile = tmp_path / "grandchild.pid"
    with caplog.at_level("WARNING", logger=resource_limits.__name__):
        done = resource_limits.run_bounded(
            [_PY, "-c", _holder(pidfile, "stdout")], timeout=20, max_output_bytes=64
        )
    grandchild = int(pidfile.read_text())
    assert done.returncode == 0
    assert _gone_within(grandchild, 5)
    (record,) = [r for r in caplog.records if "left" in r.getMessage()]
    message = record.getMessage()
    assert "%d (%s)" % (grandchild, os.path.basename(_PY)) in message, message
    assert "sleep" not in message, "a leftover's arguments reached the log"


@pytest.mark.skipif(not os.path.isdir("/proc"), reason="lists pipe holders in /proc")
def test_a_holder_outside_the_session_is_named_and_not_signalled(tmp_path, caplog):
    pidfile = tmp_path / "grandchild.pid"
    try:
        with caplog.at_level("WARNING", logger=resource_limits.__name__):
            done = resource_limits.run_bounded(
                [_PY, "-c", _holder(pidfile, "stdout", new_session=True)],
                timeout=20,
                max_output_bytes=64,
            )
        holder = int(pidfile.read_text())
        assert (done.returncode, done.stdout) == (0, "done\n")
        assert _alive(holder), "a process outside the session was signalled"
        messages = [r.getMessage() for r in caplog.records]
        assert any(
            "stdout is still held open by %d (" % holder in m for m in messages
        ), messages
    finally:
        _kill(pidfile)


def test_an_ignored_sigchld_is_set_to_its_default_for_the_run_or_refused(tmp_path):
    """Ignored, SIGCHLD would have the kernel reap the child as it exits and
    free its id while the run can still signal it: on the main thread it is
    at its default for the run and put back, off it the run is refused."""
    probe = _start_probe(
        tmp_path,
        "signal.signal(signal.SIGCHLD, signal.SIG_IGN)\n"
        "got = {}\n"
        "got['rc'] = resource_limits.run_bounded([sys.executable, '-c', "
        "'import sys; sys.exit(3)'], timeout=30, max_output_bytes=64).returncode\n"
        "got['kept'] = signal.getsignal(signal.SIGCHLD) is signal.SIG_IGN\n"
        "def off_main():\n"
        "    try:\n"
        "        resource_limits.run_bounded(['true'], 30, 64)\n"
        "        got['off'] = 'ran'\n"
        "    except resource_limits.ChildSignalIgnored as exc:\n"
        "        got['off'] = str(exc)\n"
        "t = threading.Thread(target=off_main)\n"
        "t.start()\n"
        "t.join()\n"
        "print(json.dumps(got))\n",
    )
    out, _ = probe.communicate(timeout=60)
    probe.stdout.close()
    got = json.loads(out)
    assert got["rc"] == 3 and got["kept"] is True, got
    assert "SIGCHLD" in got["off"] and "main thread" in got["off"], got


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


_HARD_CHILD = (
    "import resource, sys; sys.path.insert(0, %r)\n"
    "from scripts import resource_limits\n"
    "resource.setrlimit(resource.RLIMIT_AS, (%d << 20, %d << 20))\n"
    "print(resource_limits.cap_memory(%d))\n"
    "print(*resource.getrlimit(resource.RLIMIT_AS))\n"
)


@pytest.mark.skipif(not hasattr(os, "fork"), reason="RLIMIT_AS is a POSIX limit")
def test_a_cap_above_the_hard_limit_is_lowered_to_it_and_says_so():
    """An unprivileged process cannot raise its hard limit, so a configured cap
    past it sets the hard limit and the line names both the size and why."""
    hard_mb = 1536
    done = resource_limits.run_bounded(
        [_PY, "-c", _HARD_CHILD % (str(_ROOT), hard_mb, hard_mb, hard_mb * 2)],
        timeout=60,
        max_output_bytes=4096,
    )
    assert done.returncode == 0, done.stderr
    status, limits = done.stdout.splitlines()
    assert status.startswith(
        "memory cap: %d MB of address space (RLIMIT_AS, lowered to the hard limit)"
        % hard_mb
    ), status
    assert limits.split() == [str(hard_mb << 20)] * 2, limits


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


# --- what an agent's tool child is held to: tool_limits, run_tool ----------------


def _tools_project(tmp_path, agents_block, gate_block=None):
    gate = {"gate_timeout_seconds": 60, "gate_stop_grace_seconds": 5}
    gate.update(gate_block or {})
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.json").write_text(
        json.dumps({"agents": agents_block, "make_targets": gate}), encoding="utf-8"
    )
    return str(tmp_path)


def test_tool_limits_are_read_from_the_agents_block(tmp_path):
    # 60 + 2 * 5 + 3: the least time limit the gate runner's 60 s limit, its
    # 5 s grace spent twice and a 3 s margin accept.
    root = _tools_project(
        tmp_path,
        {
            "tool_timeout_seconds": 73,
            "tool_max_output_bytes": 4096,
            "tool_gate_margin_seconds": 3,
        },
    )
    assert resource_limits.tool_limits(root) == (73, 4096)


@pytest.mark.parametrize(
    "block, key",
    [
        ({"tool_timeout_seconds": 0}, r"agents\.tool_timeout_seconds"),
        ({"tool_timeout_seconds": 1.5}, r"agents\.tool_timeout_seconds"),
        ({"tool_timeout_seconds": "10m"}, r"agents\.tool_timeout_seconds"),
        (
            {"tool_timeout_seconds": int(threading.TIMEOUT_MAX) + 1},
            r"agents\.tool_timeout_seconds",
        ),
        ({"tool_gate_margin_seconds": 0}, r"agents\.tool_gate_margin_seconds"),
        ({"tool_gate_margin_seconds": 1.5}, r"agents\.tool_gate_margin_seconds"),
        ({"tool_max_output_bytes": 0}, r"agents\.tool_max_output_bytes"),
        (
            {"tool_max_output_bytes": sys.maxsize + 1},
            r"agents\.tool_max_output_bytes",
        ),
    ],
)
def test_a_tool_limit_out_of_its_bound_is_refused(tmp_path, block, key):
    agents = {
        "tool_timeout_seconds": 600,
        "tool_max_output_bytes": 4096,
        "tool_gate_margin_seconds": 3,
    }
    agents.update(block)
    with pytest.raises(config_loader.WrongValue, match=key):
        resource_limits.tool_limits(_tools_project(tmp_path, agents))


def test_a_byte_cap_is_bounded_by_the_largest_length_not_a_seconds_constant(tmp_path):
    # threading.TIMEOUT_MAX is a number of seconds; a byte cap past it is a
    # length Python can still hold, so only sys.maxsize bounds it.
    cap = int(threading.TIMEOUT_MAX) + 1
    root = _tools_project(
        tmp_path,
        {
            "tool_timeout_seconds": 600,
            "tool_max_output_bytes": cap,
            "tool_gate_margin_seconds": 3,
        },
    )
    assert resource_limits.tool_limits(root) == (600, cap)
    with pytest.raises(config_loader.WrongValue) as caught:
        config_loader.resolve(
            {"agents": {"tool_max_output_bytes": sys.maxsize + 1}},
            config_loader.rows(("agents", "tool_max_output_bytes")),
            config_loader.CONFIG_FILE,
        )
    assert "sys.maxsize" in "; ".join(caught.value.lines)


@pytest.mark.parametrize("seconds", [60, 65, 66, 72])
def test_a_tool_limit_that_does_not_outlast_the_gate_runner_is_refused(
    tmp_path, capsys, seconds
):
    # 60 + 2 * 5 + 3: on its timeout the gate runner waits its grace once for
    # make's session to end and once more for make's output, then snapshots
    # the tree, so 66 (the limit plus one grace plus one) is refused too.
    root = _tools_project(
        tmp_path,
        {
            "tool_timeout_seconds": seconds,
            "tool_max_output_bytes": 4096,
            "tool_gate_margin_seconds": 3,
        },
    )
    with pytest.raises(config_loader.WrongValue) as caught:
        resource_limits.tool_limits(root)
    line = "; ".join(caught.value.lines)
    for key in (
        "agents.tool_timeout_seconds",
        "make_targets.gate_timeout_seconds",
        "make_targets.gate_stop_grace_seconds",
        "agents.tool_gate_margin_seconds",
    ):
        assert key in line
    assert "at least 73" in line
    assert line in capsys.readouterr().err


def test_a_margin_no_tool_limit_can_cover_is_refused_naming_the_margin(
    tmp_path, capsys
):
    # 60 + 2 * 5 leaves threading.TIMEOUT_MAX - 70 for the margin: one more and
    # no agents.tool_timeout_seconds within its own ceiling meets the bound, so
    # the fault is the margin's, not the tool limit's.
    most = int(threading.TIMEOUT_MAX) - 70
    root = _tools_project(
        tmp_path,
        {
            "tool_timeout_seconds": int(threading.TIMEOUT_MAX),
            "tool_max_output_bytes": 4096,
            "tool_gate_margin_seconds": most + 1,
        },
    )
    with pytest.raises(config_loader.WrongValue) as caught:
        resource_limits.tool_limits(root)
    line = "; ".join(caught.value.lines)
    assert line.startswith(
        "%s: agents.tool_gate_margin_seconds is %d"
        % (config_loader.CONFIG_FILE, most + 1)
    )
    assert "at most %d" % most in line
    assert line in capsys.readouterr().err


def test_the_largest_margin_a_tool_limit_can_cover_is_accepted(tmp_path):
    most = int(threading.TIMEOUT_MAX) - 70
    root = _tools_project(
        tmp_path,
        {
            "tool_timeout_seconds": int(threading.TIMEOUT_MAX),
            "tool_max_output_bytes": 4096,
            "tool_gate_margin_seconds": most,
        },
    )
    assert resource_limits.tool_limits(root) == (int(threading.TIMEOUT_MAX), 4096)


def test_the_shipped_tool_limits_outlast_the_shipped_gate_runner():
    timeout, cap = resource_limits.tool_limits()
    assert (timeout, cap) == (15000, 67108864)
    gate = config_loader.read(str(_ROOT))["make_targets"]
    margin = config_loader.read(str(_ROOT))["agents"]["tool_gate_margin_seconds"]
    assert margin == 60
    least = gate["gate_timeout_seconds"] + 2 * gate["gate_stop_grace_seconds"] + margin
    # Slack over the bound, so raising a gate key a little does not refuse
    # every agent tool at once.
    assert timeout > least


def test_run_tool_holds_the_child_to_the_configured_limit_and_names_the_key(tmp_path):
    root = _tools_project(
        tmp_path,
        {
            "tool_timeout_seconds": 66,
            "tool_max_output_bytes": 4096,
            "tool_gate_margin_seconds": 3,
        },
        {"gate_timeout_seconds": 1, "gate_stop_grace_seconds": 1},
    )
    done = resource_limits.run_tool(
        [_PY, "-c", "import os, sys; print(os.getcwd()); print(sys.stdin.read())"],
        cwd=str(tmp_path),
        stdin_text="spec",
        root=root,
    )
    assert done.stdout.split("\n")[:2] == [str(tmp_path), "spec"]
    with pytest.raises(resource_limits.ChildOutputTooLarge) as caught:
        resource_limits.run_tool(
            [_PY, "-c", "import sys; sys.stdout.write('x' * 5000)"],
            cwd=str(tmp_path),
            root=root,
        )
    assert "4096 bytes" in str(caught.value)
    assert "agents.tool_max_output_bytes" in str(caught.value)


def test_run_tool_ends_a_child_past_the_configured_time(tmp_path, monkeypatch):
    # One second keeps the test short; tool_limits would refuse it against any
    # gate runner's limit, so it is handed in past the reader.
    monkeypatch.setattr(resource_limits, "tool_limits", lambda root=None: (1, 4096))
    started = time.monotonic()
    with pytest.raises(resource_limits.ChildTimedOut) as caught:
        resource_limits.run_tool(
            [_PY, "-c", "import time; time.sleep(30)"], cwd=str(tmp_path)
        )
    assert time.monotonic() - started < 15
    assert "agents.tool_timeout_seconds" in str(caught.value)
