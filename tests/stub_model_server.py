"""
title: Stub model server — a canned chat-completions endpoint on a loopback socket
kind: tests
layer: n/a
summary: stub_chat_server(root, replies) serves the OpenAI-style chat-completions route from a stdlib ThreadingHTTPServer bound to config/project.json `e2e.server.host` on a port the OS assigns, so models/openai_compatible.py is driven over a real socket with no paid call. Each POST to /chat/completions (with or without a /v1 prefix) is recorded with its parsed JSON body and answered from the reply queue: a string is a 200 completion carrying that text, an int is that HTTP status, a Redirect(status, location) is that status with that `Location` header and no body, and an empty queue is a 500. Every request it receives, by any method and on any path, except its own readiness probe, is also recorded in the yielded `.seen` list as (method, path, whether an Authorization header was present), never with the header's value, so a test can show a credential did not arrive. It waits until GET /health answers 200 through tests/live_server.py's proxy-free opener within `e2e.server.ready_timeout_s`, and its `finally` shuts the server down and joins the thread within `e2e.server.stop_timeout_s`, raising LiveServerError if the thread outlives that, so no server is left behind. It writes nothing.
"""

import collections
import json
import socket
import threading
import time
import urllib.error
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from live_server import LiveServerError, load_server_config, loopback_opener

__all__ = ["Redirect", "stub_chat_server"]

_ROUTES = ("/chat/completions", "/v1/chat/completions")
_HEALTH = "/health"
_OK = 200
# The status an exhausted queue answers: a test that sends more requests than
# it scripted sees a case error, not a hang or a recycled reply.
_EXHAUSTED = 500
# A scripted reply that sends the client elsewhere: `status` is a 3xx code and
# `location` the URL its Location header names.
Redirect = collections.namedtuple("Redirect", "status location")
# One request as the server saw it; has_authorization is a bool so the
# credential itself is never held by the test.
Seen = collections.namedtuple("Seen", "method path has_authorization")


class _Served:
    """(base_url, requests) by iteration and index, so `as (base, requests)`
    still unpacks, with the `seen` list of every request as an attribute."""

    __slots__ = ("_pair", "seen")

    def __init__(self, base, requests, seen):
        self._pair = (base, requests)
        self.seen = seen

    def __iter__(self):
        return iter(self._pair)

    def __getitem__(self, index):
        return self._pair[index]

    def __len__(self):
        return len(self._pair)


def _handler(replies, requests, seen, lock):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            """Silence the per-request stderr line; the test reads `requests`."""

        def _record(self):
            with lock:
                seen.append(
                    Seen(
                        self.command,
                        self.path,
                        self.headers.get("Authorization") is not None,
                    )
                )

        def _redirect(self, reply):
            self.send_response(reply.status)
            self.send_header("Location", reply.location)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _send(self, status, body):
            data = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == _HEALTH:
                self._send(_OK, {"status": "ok"})
            else:
                self._record()
                self._send(404, {"error": "not found"})

        def do_POST(self):
            self._record()
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length)
            if self.path not in _ROUTES:
                self._send(404, {"error": "not found"})
                return
            with lock:
                requests.append(json.loads(raw.decode("utf-8")))
                reply = replies.pop(0) if replies else _EXHAUSTED
            if isinstance(reply, Redirect):
                self._redirect(reply)
            elif isinstance(reply, int):
                self._send(reply, {"error": "scripted status %d" % reply})
            else:
                self._send(_OK, {"choices": [{"message": {"content": reply}}]})

        def _other(self):
            self._record()
            self._send(405, {"error": "method not allowed"})

        # Any other method is still a request that arrived, so it is recorded.
        do_HEAD = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = _other

    return Handler


def _wait_ready(url, timeout_s, interval_s):
    opener = loopback_opener()
    deadline = time.monotonic() + timeout_s
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise LiveServerError(
                "the stub model server did not answer 200 at %s within %ss "
                "(config/project.json `e2e.server.ready_timeout_s`)" % (url, timeout_s)
            )
        try:
            with opener.open(url, timeout=remaining) as resp:
                if resp.status == _OK:
                    return
        except urllib.error.HTTPError as exc:
            exc.close()
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(min(interval_s, max(remaining, 0)))


@contextmanager
def stub_chat_server(root, replies):
    """Serve *replies* (str: a completion, int: an HTTP status, Redirect: a
    redirect) in order and yield (base_url, requests), where requests is the
    list of parsed request bodies, appended as they arrive; the yielded pair's
    `.seen` lists every request, any method, as a Seen."""
    config = load_server_config(str(root))
    host = config["host"]
    queue = list(replies)
    requests = []
    seen = []
    lock = threading.Lock()
    server_class = ThreadingHTTPServer
    if ":" in host:
        # An IPv6 loopback host binds only on an AF_INET6 socket.
        server_class = type("_V6Server", (ThreadingHTTPServer,), {})
        server_class.address_family = socket.AF_INET6
    server = server_class((host, 0), _handler(queue, requests, seen, lock))
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, name="stub-model-server")
    thread.start()
    try:
        port = server.server_address[1]
        url_host = "[%s]" % host if ":" in host else host
        base = "http://%s:%d" % (url_host, port)
        _wait_ready(
            base + _HEALTH, config["ready_timeout_s"], config["probe_interval_s"]
        )
        yield _Served(base, requests, seen)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(config["stop_timeout_s"])
        if thread.is_alive():
            raise LiveServerError(
                "the stub model server thread outlived its shutdown by %ss "
                "(config/project.json `e2e.server.stop_timeout_s`)"
                % config["stop_timeout_s"]
            )
