"""
title: Integration — one openai-compatible call ends at its time limit, however slowly the server answers
kind: tests
layer: n/a
summary: models/openai_compatible.py is pointed at a loopback socket server that answers one byte at a time, each byte well inside the call's time limit, so a limit applied to each socket wait alone would never fire. Whether the server drips the status line and headers or the body, the call is refused within the limit plus _SLACK_S, with a RuntimeError that is not ModelUnavailable, naming the endpoint, the limit and config/project.json `models.timeout_seconds`, and never the path. The server stops dripping after _DRIP_FOR_S, far past the limit plus the slack, so a call that waits on each byte fails the elapsed-time assertion instead of hanging the run.
@covers models/openai_compatible.py
"""

import socket
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

pytestmark = pytest.mark.integration

_ADAPTER = "openai-compatible"
_HOST = "127.0.0.1"
_LIMIT_S = 1.0
# One byte every this many seconds: each socket wait ends well inside the limit.
_DRIP_EVERY_S = 0.2
# How long the server drips before it closes, so a call bounded only per socket
# wait ends here and fails the assertion, instead of waiting forever.
_DRIP_FOR_S = 6.0
# What the call may take past its limit: the wake-up of the read that sees the
# deadline, plus scheduling on a loaded shared host. The bug this guards ran to
# the end of the drip, many times this.
_SLACK_S = 1.0

_HEADERS = (
    b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 1000\r\n\r\n"
)


def _read_request(conn):
    """Read the whole request, body included: a socket closed with unread
    input sends a reset, and the client would see that instead of the end of
    the drip."""
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = conn.recv(4096)
        if not chunk:
            return
        data += chunk
    head, _, body = data.partition(b"\r\n\r\n")
    length = 0
    for line in head.split(b"\r\n")[1:]:
        name, _, value = line.partition(b":")
        if name.strip().lower() == b"content-length":
            length = int(value)
    while len(body) < length:
        chunk = conn.recv(4096)
        if not chunk:
            return
        body += chunk


def _drip(conn, prefix, byte, stop):
    """Send *prefix* at once, then *byte* every _DRIP_EVERY_S until the client
    goes, *stop* is set, or _DRIP_FOR_S passes."""
    try:
        _read_request(conn)
        conn.sendall(prefix)
        until = time.monotonic() + _DRIP_FOR_S
        while time.monotonic() < until and not stop.wait(_DRIP_EVERY_S):
            conn.sendall(byte)
    except OSError:
        pass  # the client closed its end: the call is over
    finally:
        conn.close()


@contextmanager
def _drip_server(prefix, byte):
    """A loopback server that answers one request with *prefix*, then one
    *byte* at a time; yields its base_url and joins its thread on the way out."""
    stop = threading.Event()
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind((_HOST, 0))
    listener.listen(1)
    listener.settimeout(_DRIP_FOR_S + _SLACK_S)

    def serve():
        try:
            conn, _addr = listener.accept()
        except OSError:
            return  # no client came, or the listener was closed
        _drip(conn, prefix, byte, stop)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield "http://%s:%d" % (_HOST, listener.getsockname()[1])
    finally:
        stop.set()
        listener.close()
        thread.join(_DRIP_FOR_S + _SLACK_S)
        assert not thread.is_alive(), "the drip server outlived its test"


def _backend(monkeypatch, base_url):
    from models import get_model
    from models import openai_compatible as mod

    entry = base_url.split("://", 1)[1]
    policy = mod.load_policy()._replace(allowed_hosts={_ADAPTER: (entry,)})
    monkeypatch.setattr(mod, "load_policy", lambda root=None: policy)
    # urllib honours proxy variables; the loopback server is direct.
    monkeypatch.setenv("no_proxy", "*")
    monkeypatch.setenv("NO_PROXY", "*")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return get_model(_ADAPTER, base_url=base_url + "/v1", timeout=_LIMIT_S)


@pytest.mark.parametrize(
    "prefix, byte",
    [
        # The status line arrives, then one header byte at a time.
        pytest.param(b"HTTP/1.1 200 OK\r\nX-Pad: ", b"x", id="headers"),
        # The headers arrive whole, then one body byte at a time.
        pytest.param(_HEADERS + b'{"pad": "', b"x", id="body"),
    ],
)
def test_a_server_that_drips_its_reply_is_refused_at_the_call_limit(
    monkeypatch, prefix, byte
):
    from models import ModelUnavailable

    with _drip_server(prefix, byte) as base_url:
        backend = _backend(monkeypatch, base_url)
        started = time.monotonic()
        with pytest.raises(RuntimeError) as info:
            backend.run("ping")
        elapsed = time.monotonic() - started
    assert elapsed < _LIMIT_S + _SLACK_S, elapsed
    assert not isinstance(info.value, ModelUnavailable), info.value
    message = str(info.value)
    assert base_url in message and "models.timeout_seconds" in message, message
    assert str(_LIMIT_S) in message and "/chat/completions" not in message, message
