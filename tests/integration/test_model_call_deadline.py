"""
title: Integration — one openai-compatible call ends at its time limit, however slowly the server answers
kind: tests
layer: n/a
summary: models/openai_compatible.py is pointed at a loopback socket server that answers one byte at a time, each byte well inside the call's time limit, so a limit applied to each socket wait alone would never fire. Whether the server drips the status line and headers or the body, the call is refused within the limit plus _SLACK_S, with a RuntimeError that is not ModelUnavailable, naming the endpoint, the limit and config/project.json `models.timeout_seconds`, and never the path. An https call whose TCP connect takes most of the limit, to a server that never answers the ClientHello, is refused within the limit plus _SLACK_S too, so the TLS handshake waits only the time the connect left; through a CONNECT proxy that takes most of the limit to open the tunnel, the handshake waits only the time the tunnel left (the opener is rebuilt with the proxy set, as it reads the proxy variables when it is built); and a TCP connect that starts _BEFORE_CONNECT_S into the call is given at most the limit less that time. A host name whose lookup never returns is refused at the limit as ModelUnavailable naming the host, and each address of a name with two is given only the time left. The server stops dripping after _DRIP_FOR_S, far past the limit plus the slack, so a call that waits on each byte fails the elapsed-time assertion instead of hanging the run.
@covers models/openai_compatible.py
"""

import socket
import sys
import threading
import time
import urllib.request
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


# The TLS case: a TCP connect that takes most of the limit, then a server that
# never answers the ClientHello. The connect's wait is fixed before it starts,
# so a handshake that reused it would get the whole limit again and run to
# about _TLS_LIMIT_S + _TLS_CONNECT_S (measured: 3.07 s at a 2.0 s limit).
_TLS_LIMIT_S = 2.0
_TLS_CONNECT_S = 1.8


@contextmanager
def _silent_server():
    """A loopback server that accepts one connection and never writes to it;
    yields its host:port and joins its thread on the way out."""
    stop = threading.Event()
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind((_HOST, 0))
    listener.listen(1)
    listener.settimeout(_DRIP_FOR_S)

    def serve():
        try:
            conn, _addr = listener.accept()
        except OSError:
            return  # no client came, or the listener was closed
        stop.wait(_DRIP_FOR_S)
        conn.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield "%s:%d" % (_HOST, listener.getsockname()[1])
    finally:
        stop.set()
        listener.close()
        thread.join(_DRIP_FOR_S)
        assert not thread.is_alive(), "the silent server outlived its test"


def _slow_connect(monkeypatch, delay, seen):
    """Make every TCP connect take *delay* seconds longer, and record the wait
    each one was given in *seen*."""
    connect = socket.create_connection

    def slow(address, timeout=None, *args, **kwargs):
        seen.append(timeout)
        time.sleep(delay)
        return connect(address, timeout, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", slow)


def test_a_tls_handshake_waits_only_the_time_the_connect_left(monkeypatch):
    from models import get_model
    from models import openai_compatible as mod

    with _silent_server() as entry:
        policy = mod.load_policy()._replace(allowed_hosts={_ADAPTER: (entry,)})
        monkeypatch.setattr(mod, "load_policy", lambda root=None: policy)
        monkeypatch.setenv("no_proxy", "*")
        monkeypatch.setenv("NO_PROXY", "*")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        backend = get_model(
            _ADAPTER, base_url="https://%s/v1" % entry, timeout=_TLS_LIMIT_S
        )
        _slow_connect(monkeypatch, _TLS_CONNECT_S, [])
        started = time.monotonic()
        with pytest.raises(RuntimeError):
            backend.run("ping")
        elapsed = time.monotonic() - started
    assert elapsed < _TLS_LIMIT_S + _SLACK_S, elapsed


# The time a request spends inside its deadline before it connects; the
# connect must be given what is left, not the whole limit again.
_BEFORE_CONNECT_S = 0.5


def test_the_tcp_connect_waits_only_the_time_left_before_it(monkeypatch):
    import http.client

    seen = []
    putrequest = http.client.HTTPConnection.putrequest

    def late_putrequest(self, *args, **kwargs):
        time.sleep(_BEFORE_CONNECT_S)
        return putrequest(self, *args, **kwargs)

    with _silent_server() as entry:
        backend = _backend(monkeypatch, "http://" + entry)
        _slow_connect(monkeypatch, 0, seen)
        monkeypatch.setattr(http.client.HTTPConnection, "putrequest", late_putrequest)
        with pytest.raises(RuntimeError):
            backend.run("ping")
    assert seen and all(0 < wait <= _LIMIT_S - _BEFORE_CONNECT_S for wait in seen), seen


@contextmanager
def _slow_tunnel_proxy(delay):
    """A loopback proxy that reads one CONNECT request, waits *delay* seconds,
    says the tunnel is open and then never writes again, so the TLS handshake
    through it never ends; yields its http:// URL."""
    stop = threading.Event()
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind((_HOST, 0))
    listener.listen(1)
    listener.settimeout(_DRIP_FOR_S)

    def serve():
        try:
            conn, _addr = listener.accept()
        except OSError:
            return  # no client came, or the listener was closed
        _read_request(conn)
        if not stop.wait(delay):
            conn.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
        stop.wait(_DRIP_FOR_S)
        conn.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield "http://%s:%d" % (_HOST, listener.getsockname()[1])
    finally:
        stop.set()
        listener.close()
        thread.join(_DRIP_FOR_S)
        assert not thread.is_alive(), "the proxy outlived its test"


def test_a_tls_handshake_through_a_proxy_waits_only_the_time_the_tunnel_left(
    monkeypatch,
):
    from models import get_model
    from models import openai_compatible as mod

    entry = "api.example.test:443"
    with _slow_tunnel_proxy(_TLS_CONNECT_S) as proxy:
        policy = mod.load_policy()._replace(allowed_hosts={_ADAPTER: (entry,)})
        monkeypatch.setattr(mod, "load_policy", lambda root=None: policy)
        for name in ("no_proxy", "NO_PROXY"):
            monkeypatch.delenv(name, raising=False)
        for name in ("https_proxy", "HTTPS_PROXY"):
            monkeypatch.setenv(name, proxy)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        # The opener reads the proxy variables when it is built, at import;
        # rebuilt here, it is the opener of a process started with them set.
        opener = urllib.request.build_opener(
            mod._NoRedirect, mod._DeadlineHTTPHandler, mod._DeadlineHTTPSHandler
        )
        monkeypatch.setattr(mod, "_OPENER", opener)
        backend = get_model(
            _ADAPTER, base_url="https://%s/v1" % entry, timeout=_TLS_LIMIT_S
        )
        started = time.monotonic()
        with pytest.raises(RuntimeError) as raised:
            backend.run("ping")
        elapsed = time.monotonic() - started
    assert "handshake" in str(raised.value), raised.value
    assert elapsed < _TLS_LIMIT_S + _SLACK_S, elapsed


# The name-resolution cases: a lookup that hangs (a resolver that never
# answers) and a name with several addresses, each refusing late. Both reach
# no network: getaddrinfo is replaced, and every address is the loopback one.
_NAMED = "api.example.test"


def _named_backend(monkeypatch):
    from models import get_model
    from models import openai_compatible as mod

    entry = _NAMED + ":443"
    policy = mod.load_policy()._replace(allowed_hosts={_ADAPTER: (entry,)})
    monkeypatch.setattr(mod, "load_policy", lambda root=None: policy)
    monkeypatch.setenv("no_proxy", "*")
    monkeypatch.setenv("NO_PROXY", "*")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return get_model(_ADAPTER, base_url="https://%s/v1" % entry, timeout=_LIMIT_S)


def test_a_name_that_never_resolves_is_refused_at_the_call_limit(monkeypatch):
    from models import ModelUnavailable

    resolve = socket.getaddrinfo
    release = threading.Event()

    def hangs(host, *args, **kwargs):
        if host == _NAMED:
            release.wait(_DRIP_FOR_S)
        return resolve(host, *args, **kwargs)

    backend = _named_backend(monkeypatch)
    monkeypatch.setattr(socket, "getaddrinfo", hangs)
    started = time.monotonic()
    try:
        with pytest.raises(ModelUnavailable) as info:
            backend.run("ping")
        elapsed = time.monotonic() - started
    finally:
        release.set()
    assert elapsed < _LIMIT_S + _SLACK_S, elapsed
    assert _NAMED in str(info.value), info.value


def test_each_address_of_a_name_waits_only_the_time_left(monkeypatch):
    """Two addresses, the first refusing only after most of the limit: the
    second connect gets what is left, not the whole limit again."""
    late = 0.6
    seen = []
    calls = []
    resolve = socket.getaddrinfo

    def two_addresses(host, port, *args, **kwargs):
        if host != _NAMED:
            return resolve(host, port, *args, **kwargs)
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))
            for ip in ("127.0.0.2", "127.0.0.3")
        ]

    def refuses_late(address, timeout=None, *args, **kwargs):
        seen.append(timeout)
        calls.append(address)
        time.sleep(late)
        raise ConnectionRefusedError(111, "refused")

    backend = _named_backend(monkeypatch)
    monkeypatch.setattr(socket, "getaddrinfo", two_addresses)
    monkeypatch.setattr(socket, "create_connection", refuses_late)
    started = time.monotonic()
    with pytest.raises(RuntimeError):
        backend.run("ping")
    elapsed = time.monotonic() - started
    assert calls == [("127.0.0.2", 443), ("127.0.0.3", 443)], (seen, calls)
    assert seen[1] <= _LIMIT_S - late, seen
    assert elapsed < _LIMIT_S + _SLACK_S, elapsed
