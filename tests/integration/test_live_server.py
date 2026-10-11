"""
title: Integration — the live-server harness starts a real process, waits on a probe and leaves nothing behind
kind: tests
layer: n/a
summary: tests/live_server.py starts the REST app under uvicorn as its own process on a loopback port the OS picks, waits on a readiness probe bounded by config/project.json `e2e.server.ready_timeout_s`, and kills its whole process group on the way out. Each test here is a RED proof of one promise - a server that answers over the socket and leaves no process, one that never becomes ready times out and is killed, one that exits early fails fast with its log, a scenario that raises still kills the server, a runner ended by SIGTERM or SIGHUP still kills the server, and a proxy in the environment cannot reroute a loopback request. Skips, naming the `transport` extra, without uvicorn or FastAPI.
"""

import contextlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from scripts.child_env import build_child_env

import live_server
import optional_deps

optional_deps.importorskip("uvicorn", extra="transport")
optional_deps.importorskip("fastapi", extra="transport")

pytestmark = pytest.mark.integration

_ROOT = Path(__file__).resolve().parents[2]
# An address nothing listens on: TEST-NET-1 (RFC 5737) is never routed.
_UNROUTABLE_PROXY = "http://192.0.2.1:9"


def _rest_dir():
    return live_server.rest_dir(str(_ROOT))


def _assert_gone(pid, host, port):
    """The process group is gone and the port refuses a connection."""
    with pytest.raises(ProcessLookupError):
        os.killpg(pid, 0)
    with pytest.raises(ConnectionRefusedError):
        socket.create_connection((host, port), timeout=1).close()


def _enter_and_fail(raising=None, seen=None, **overrides):
    """Enter the harness and fail inside it: with *raising*, as a scenario
    whose assertion raised; without, because entry should not have yielded."""
    with live_server.live_server(str(_ROOT), _rest_dir(), **overrides) as server:
        if raising is None:
            pytest.fail("a server that never became ready must not be yielded")
        seen["pid"], seen["port"] = server.pid, server.port
        raise raising


def test_the_server_answers_over_the_socket_and_leaves_no_process():
    config = live_server.load_server_config(str(_ROOT))
    before = signal.getsignal(signal.SIGTERM)
    with live_server.live_server(str(_ROOT), _rest_dir()) as server:
        status, _headers, body = server.request("GET", config["probe_path"])
        assert status == 200, body
        pid, port = server.pid, server.port
        os.killpg(pid, 0)  # alive while inside: raises if it is not
        assert signal.getsignal(signal.SIGTERM) is not before  # the guard is on
    _assert_gone(pid, config["host"], port)
    assert signal.getsignal(signal.SIGTERM) is before  # and put back


def test_a_server_that_never_becomes_ready_times_out_and_is_killed():
    config = live_server.load_server_config(str(_ROOT))
    timeout = 2
    seen = {}
    started = time.monotonic()
    with pytest.raises(live_server.LiveServerError) as caught:
        _enter_and_fail(
            probe_path="/__never_ready__",
            ready_timeout_s=timeout,
            on_start=seen.update,
        )
    elapsed = time.monotonic() - started
    message = str(caught.value)
    assert "e2e.server.ready_timeout_s" in message, message
    assert "/__never_ready__" in message, message
    assert elapsed < timeout + config["stop_timeout_s"] + 5, elapsed
    _assert_gone(seen["pid"], config["host"], seen["port"])


def test_a_server_that_exits_early_fails_fast_with_its_log():
    config = live_server.load_server_config(str(_ROOT))
    seen = {}
    started = time.monotonic()
    with pytest.raises(live_server.LiveServerError) as caught:
        _enter_and_fail(app="no_such_module:app", on_start=seen.update)
    elapsed = time.monotonic() - started
    message = str(caught.value)
    assert "exited with code" in message, message
    assert "no_such_module" in message, message  # the log tail carries the cause
    assert elapsed < config["ready_timeout_s"], elapsed
    _assert_gone(seen["pid"], config["host"], seen["port"])


def test_a_failing_scenario_still_kills_the_server():
    config = live_server.load_server_config(str(_ROOT))
    seen = {}
    with pytest.raises(RuntimeError, match="the scenario failed"):
        _enter_and_fail(raising=RuntimeError("the scenario failed"), seen=seen)
    _assert_gone(seen["pid"], config["host"], seen["port"])


_RUNNER = """
import sys, time
sys.path.insert(0, {tests!r})
import live_server
root = {root!r}
with live_server.live_server(root, live_server.rest_dir(root)) as server:
    with open({out!r} + ".tmp", "w") as fh:
        fh.write("%d %d" % (server.pid, server.port))
    import os
    os.replace({out!r} + ".tmp", {out!r})
    time.sleep(600)
"""


def _wait_for(path, proc, deadline_s):
    deadline = time.monotonic() + deadline_s
    while not path.is_file():
        assert proc.poll() is None, "the runner exited with %s" % proc.returncode
        assert time.monotonic() < deadline, "the runner never reported a server"
        time.sleep(0.1)
    pid, port = path.read_text(encoding="utf-8").split()
    return int(pid), int(port)


@pytest.mark.parametrize(
    "name", [n for n in ("SIGTERM", "SIGHUP") if hasattr(signal, n)]
)
def test_a_runner_ended_by_a_signal_leaves_no_server(tmp_path, name):
    # A CI cancel, `timeout` or a batch scheduler's time limit sends SIGTERM to
    # the runner, and a closed terminal SIGHUP; neither unwinds to the harness's
    # `finally` by default, and the server is in its own session.
    sig = getattr(signal, name)
    config = live_server.load_server_config(str(_ROOT))
    out = tmp_path / "server"
    script = tmp_path / "runner.py"
    script.write_text(
        _RUNNER.format(tests=str(_ROOT / "tests"), root=str(_ROOT), out=str(out)),
        encoding="utf-8",
    )
    runner = subprocess.Popen(
        [sys.executable, str(script)],
        cwd=str(_ROOT),
        env=build_child_env(root=str(_ROOT)),
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    pid = None
    try:
        pid, port = _wait_for(out, runner, config["ready_timeout_s"] + 10)
        os.kill(runner.pid, sig)
        assert runner.wait(timeout=config["stop_timeout_s"] + 10) == -sig
        _assert_gone(pid, config["host"], port)
    finally:
        # A RED run must not leave the orphan it reports.
        for group in (runner.pid, pid):
            if group is not None:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(group, signal.SIGKILL)
        runner.wait()


def test_loopback_requests_ignore_proxy_environment(monkeypatch):
    for name in ("HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.setenv(name, _UNROUTABLE_PROXY)
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
    config = live_server.load_server_config(str(_ROOT))
    with live_server.live_server(str(_ROOT), _rest_dir()) as server:
        status, _headers, _body = server.request("GET", config["probe_path"])
    assert status == 200


def test_a_missing_or_mistyped_server_key_is_named(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    manifest = (_ROOT / "config" / "project.json").read_text(encoding="utf-8")
    data = json.loads(manifest)
    data["e2e"]["server"]["ready_timeout_s"] = "30"
    (config_dir / "project.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(live_server.LiveServerError, match="e2e.server.ready_timeout_s"):
        live_server.load_server_config(str(tmp_path))
    data["e2e"]["server"]["host"] = "10.0.0.1"
    data["e2e"]["server"]["ready_timeout_s"] = 30
    (config_dir / "project.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(live_server.LiveServerError, match="e2e.server.host"):
        live_server.load_server_config(str(tmp_path))
