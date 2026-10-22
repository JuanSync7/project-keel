"""
title: E2E — a server stops cleanly on SIGTERM
kind: tests
layer: backend
summary: Each server entry point is started as a real process on loopback or its own stdio, sent SIGTERM while it serves, and must exit 0 with its shutdown owner's `<name>: stopping on SIGTERM` line and its memory-cap line on stderr - the REST transport through api/rest_fastapi/serve.py on a port the OS picks, and the MCP action server after one JSON-RPC exchange with its stdin still open. The gRPC owner has no scenario here, since grpcio is not a dependency; tests/unit/api/test_grpc_server.py drives it against a fake server.
"""

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
from contextlib import suppress
from pathlib import Path

import pytest

import live_server
import optional_deps

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from scripts.child_env import build_child_env  # noqa: E402

pytestmark = pytest.mark.e2e


def _end_group(proc):
    """Teardown for a server the scenario failed to stop: a vanished group is
    the expected case."""
    with suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGKILL)
    proc.wait()


def _wait_for_probe(proc, url, config, log):
    opener = live_server.loopback_opener()
    deadline = time.monotonic() + config["ready_timeout_s"]
    while time.monotonic() < deadline:
        assert proc.poll() is None, "the server exited early:\n%s" % _read(log)
        try:
            with opener.open(url, timeout=config["request_timeout_s"]) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, OSError):
            pass  # not listening yet
        time.sleep(config["probe_interval_s"])
    pytest.fail(
        "%s did not answer within %ss:\n%s"
        % (url, config["ready_timeout_s"], _read(log))
    )


def _read(log):
    log.flush()
    log.seek(0)
    return log.read().decode("utf-8", "replace")


def test_the_rest_server_exits_zero_on_sigterm():
    optional_deps.importorskip("uvicorn", extra="transport")
    optional_deps.importorskip("fastapi", extra="transport")
    config = live_server.load_server_config(str(_ROOT))
    host = config["host"]
    port = live_server.free_port(host)
    serve = Path(live_server.rest_dir(str(_ROOT))) / "serve.py"
    with tempfile.TemporaryFile() as log:
        proc = subprocess.Popen(
            [sys.executable, str(serve), "--host", host, "--port", str(port)],
            cwd=str(_ROOT),
            env=build_child_env(root=str(_ROOT)),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            _wait_for_probe(
                proc, "http://%s:%d%s" % (host, port, config["probe_path"]), config, log
            )
            proc.send_signal(signal.SIGTERM)
            code = proc.wait(timeout=config["stop_timeout_s"])
        finally:
            _end_group(proc)
        output = _read(log)
    assert code == 0, output
    assert "REST server: stopping on SIGTERM" in output
    assert "memory cap: 4096 MB of address space" in output


def test_the_mcp_server_exits_zero_on_sigterm_with_its_stdin_open():
    timeout, extra = live_server.load_mcp_config(str(_ROOT))
    _e2e, manifest = live_server.load_e2e_config(str(_ROOT))
    server = _ROOT / manifest["transports"]["available"]["mcp"] / "action_server.py"
    proc = subprocess.Popen(
        [sys.executable, str(server)],
        cwd=str(_ROOT),
        env=build_child_env(root=str(_ROOT), extra=extra),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        proc.stdin.write(
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}) + "\n"
        )
        proc.stdin.flush()
        # One answered request: the server is up and waiting for the next line.
        reply = json.loads(proc.stdout.readline())
        proc.send_signal(signal.SIGTERM)
        code = proc.wait(timeout=timeout)
        err = proc.stderr.read()
    finally:
        _end_group(proc)
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            stream.close()
    assert reply["id"] == 1
    assert code == 0, err
    assert "MCP server keel-actions: stopping on SIGTERM" in err, err
    assert "memory cap: 4096 MB of address space" in err
