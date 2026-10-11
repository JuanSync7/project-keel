"""
title: Live-server harness — the REST app as a real process on a loopback socket, and an MCP server over its real stdio
summary: Starts the REST transport under uvicorn as its own process group on a loopback port the OS picks, waits on a readiness probe within config/project.json `e2e.server.ready_timeout_s`, drives it over HTTP with the stdlib and no proxy, and kills the whole group in a `finally` - after a startup that never became ready and after a scenario that raised too - and, while the server lives, on a SIGTERM or SIGHUP to the runner before re-raising it, since neither unwinds to that `finally`. It walks the routes the app serves in a child (`rest_routes`), as the installed FastAPI flattens them, for the end-to-end gate. Also runs one JSON-RPC exchange with an MCP server over its stdio within `e2e.list_timeout_s`. Every value comes from the `e2e` block, read by key and refused by its dotted name when missing or mistyped; the port alone comes from the OS. Every child starts through scripts/child_env.py build_child_env. It writes nothing into the tree: the server's log goes to an anonymous temporary file.
"""

import ipaddress
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager, suppress

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.child_env import build_child_env  # noqa: E402

__all__ = [
    "LiveServerError",
    "free_port",
    "live_server",
    "load_e2e_config",
    "load_mcp_config",
    "load_server_config",
    "loopback_opener",
    "mcp_exchange",
    "rest_dir",
]

_MANIFEST = os.path.join("config", "project.json")
_BLOCK = "e2e"
_SERVER = "server"
_REST = "rest"
# The server keys and the type each must hold. A bool is an int to isinstance,
# so numbers are checked with _is_number, which refuses it.
_SERVER_STRINGS = ("app", "host", "probe_path")
_SERVER_NUMBERS = (
    "probe_interval_s",
    "ready_timeout_s",
    "request_timeout_s",
    "stop_timeout_s",
)
# How many lines of the server's log an error carries: enough for a traceback's
# cause, short enough to read in a pytest report.
_LOG_TAIL_LINES = 40
_OK = 200
_JSON = "application/json"


class LiveServerError(Exception):
    """The server could not be configured, started or made ready."""


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def load_e2e_config(root):
    """config/project.json's `e2e` block, refused by name when absent."""
    path = os.path.join(root, _MANIFEST)
    try:
        with open(path, encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError) as exc:
        raise LiveServerError("%s cannot be read: %s" % (path, exc)) from exc
    block = manifest.get(_BLOCK) if isinstance(manifest, dict) else None
    if not isinstance(block, dict):
        raise LiveServerError("%s has no `%s` object" % (_MANIFEST, _BLOCK))
    return block, manifest


def load_server_config(root):
    """`e2e.server` with every key checked; an error names the dotted key."""
    block, _manifest = load_e2e_config(root)
    server = block.get(_SERVER)
    where = "%s.%s" % (_BLOCK, _SERVER)
    if not isinstance(server, dict):
        raise LiveServerError("%s: `%s` must be an object" % (_MANIFEST, where))
    for key in _SERVER_STRINGS:
        if not isinstance(server.get(key), str) or not server[key]:
            raise LiveServerError(
                "%s: `%s.%s` must be a non-empty string" % (_MANIFEST, where, key)
            )
    for key in _SERVER_NUMBERS:
        if not _is_number(server.get(key)) or server[key] <= 0:
            raise LiveServerError(
                "%s: `%s.%s` must be a positive number" % (_MANIFEST, where, key)
            )
    try:
        loopback = ipaddress.ip_address(server["host"]).is_loopback
    except ValueError:
        loopback = False
    if not loopback:
        raise LiveServerError(
            "%s: `%s.host` is %r, not a loopback IP address -- a scenario server "
            "must not listen beyond this host" % (_MANIFEST, where, server["host"])
        )
    if not server["probe_path"].startswith("/"):
        raise LiveServerError(
            "%s: `%s.probe_path` must start with /" % (_MANIFEST, where)
        )
    return dict(server)


def load_mcp_config(root):
    """(`e2e.list_timeout_s`, `e2e.mcp_env`) checked; an error names the key."""
    block, _manifest = load_e2e_config(root)
    timeout = block.get("list_timeout_s")
    if not _is_number(timeout) or timeout <= 0:
        raise LiveServerError(
            "%s: `%s.list_timeout_s` must be a positive number" % (_MANIFEST, _BLOCK)
        )
    env = block.get("mcp_env")
    if not isinstance(env, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in env.items()
    ):
        raise LiveServerError(
            "%s: `%s.mcp_env` must map names to strings" % (_MANIFEST, _BLOCK)
        )
    return timeout, dict(env)


def rest_dir(root):
    """The REST transport's directory, from `transports.available.rest`."""
    _block, manifest = load_e2e_config(root)
    available = (manifest.get("transports") or {}).get("available") or {}
    path = available.get(_REST)
    if not isinstance(path, str) or not path:
        raise LiveServerError(
            "%s: `transports.available.%s` names no directory" % (_MANIFEST, _REST)
        )
    return os.path.join(root, path)


def loopback_opener():
    """A urllib opener with no proxy, so a proxy variable in the environment
    cannot reroute a loopback request."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _family(host):
    return socket.AF_INET6 if ":" in host else socket.AF_INET


def _url_host(host):
    return "[%s]" % host if ":" in host else host


def free_port(host):
    """A port the OS reports free on *host* now. Another process can take it
    before the server binds; the server then exits and the harness reports
    its log rather than hanging."""
    with socket.socket(_family(host), socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


def _log_tail(log):
    log.flush()
    log.seek(0)
    lines = log.read().decode("utf-8", "replace").splitlines()
    return "\n".join(lines[-_LOG_TAIL_LINES:])


def _signal_group(pgid, sig):
    """Signal a process group that may already be gone: teardown is the one
    place a vanished process is expected rather than an error."""
    with suppress(ProcessLookupError):
        os.killpg(pgid, sig)


def _stop_group(proc, stop_timeout_s):
    """SIGTERM the process group, SIGKILL it after *stop_timeout_s*, reap the
    leader, then SIGKILL whatever of the group is left (a grandchild)."""
    pgid = proc.pid  # start_new_session: the leader's pid is the group id
    _signal_group(pgid, signal.SIGTERM)
    try:
        proc.wait(timeout=stop_timeout_s)
    except subprocess.TimeoutExpired:
        _signal_group(pgid, signal.SIGKILL)
        proc.wait()
    _signal_group(pgid, signal.SIGKILL)


# Signals whose default action ends the runner without unwinding its stack, so
# the harness's `finally` never runs and the server, in its own session, is
# orphaned: a CI cancel, `timeout` and a batch scheduler's time limit send
# SIGTERM, a closed terminal SIGHUP. SIGINT already unwinds (KeyboardInterrupt);
# SIGKILL cannot be caught at all.
_UNWINDLESS = tuple(
    getattr(signal, name) for name in ("SIGTERM", "SIGHUP") if hasattr(signal, name)
)


@contextmanager
def _stopped_on_termination(proc, stop_timeout_s):
    """While inside, a signal in _UNWINDLESS stops *proc*'s group first, then
    is re-raised under the handler it replaced, so the runner still ends the
    way it would have. Python lets only the main thread install a handler;
    elsewhere this guard adds nothing and the `finally` is the only teardown."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    previous = {}

    def stop_then_reraise(signum, _frame):
        _stop_group(proc, stop_timeout_s)
        signal.signal(signum, previous[signum])
        os.kill(os.getpid(), signum)

    for sig in _UNWINDLESS:
        old = signal.signal(sig, stop_then_reraise)
        # None: a handler installed outside Python, which cannot be put back
        # from here; the default action is the closest to it.
        previous[sig] = signal.SIG_DFL if old is None else old
    try:
        yield
    finally:
        for sig, old in previous.items():
            signal.signal(sig, old)


class _Handle:
    """What a scenario holds: the base URL, the pid and a request method."""

    def __init__(self, base_url, pid, port, request_timeout_s):
        self.base_url = base_url
        self.pid = pid
        self.port = port
        self._timeout = request_timeout_s
        self._opener = loopback_opener()

    def request(self, method, path, body=None):
        """(status, headers, body bytes); an HTTP error status is returned,
        not raised. A dict or list *body* is sent as JSON."""
        data, headers = None, {}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = _JSON
        req = urllib.request.Request(
            self.base_url + path, data=data, headers=headers, method=method
        )
        try:
            with self._opener.open(req, timeout=self._timeout) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as exc:
            with exc:
                return exc.code, dict(exc.headers), exc.read()

    def json(self, method, path, body=None):
        """(status, decoded JSON body)."""
        status, _headers, raw = self.request(method, path, body)
        return status, json.loads(raw.decode("utf-8"))


def _wait_ready(proc, log, probe_url, config, ready_timeout_s):
    opener = loopback_opener()
    deadline = time.monotonic() + ready_timeout_s
    while True:
        code = proc.poll()
        if code is not None:
            raise LiveServerError(
                "the server exited with code %s before %s answered; its log:\n%s"
                % (code, probe_url, _log_tail(log))
            )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise LiveServerError(
                "the server did not answer 200 at %s within %ss "
                "(config/project.json `e2e.server.ready_timeout_s`); its log:\n%s"
                % (probe_url, ready_timeout_s, _log_tail(log))
            )
        try:
            with opener.open(probe_url, timeout=remaining) as resp:
                if resp.status == _OK:
                    return
        except urllib.error.HTTPError as exc:
            exc.close()  # answering, not ready: keep polling until the deadline
        except (urllib.error.URLError, OSError):
            pass  # not listening yet
        time.sleep(min(config["probe_interval_s"], max(remaining, 0)))


@contextmanager
def live_server(
    root, rest_dir_path, probe_path=None, ready_timeout_s=None, app=None, on_start=None
):
    """Serve the REST app from *rest_dir_path* as a real process and yield a
    handle once its probe answers 200. The overrides exist for the harness's
    own RED proofs; a scenario takes every value from `e2e.server`.
    *on_start*, when given, receives {"pid", "port"} as soon as the process
    exists, so a caller can check the process is gone after a failed start."""
    config = load_server_config(root)
    probe_path = config["probe_path"] if probe_path is None else probe_path
    ready_timeout_s = (
        config["ready_timeout_s"] if ready_timeout_s is None else ready_timeout_s
    )
    app = config["app"] if app is None else app
    host = config["host"]
    port = free_port(host)
    base_url = "http://%s:%d" % (_url_host(host), port)
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        app,
        "--app-dir",
        str(rest_dir_path),
        "--host",
        host,
        "--port",
        str(port),
    ]
    with tempfile.TemporaryFile() as log:
        proc = subprocess.Popen(
            cmd,
            cwd=str(root),
            env=build_child_env(root=str(root)),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            with _stopped_on_termination(proc, config["stop_timeout_s"]):
                if on_start is not None:
                    on_start({"pid": proc.pid, "port": port})
                _wait_ready(proc, log, base_url + probe_path, config, ready_timeout_s)
                yield _Handle(base_url, proc.pid, port, config["request_timeout_s"])
        finally:
            _stop_group(proc, config["stop_timeout_s"])


def _load_app(rest_dir_path, app):
    """The object *app* (`module:attribute`) names, imported with
    *rest_dir_path* first on sys.path, as uvicorn's `--app-dir` does."""
    import importlib

    module_name, _, attribute = app.partition(":")
    if not module_name or not attribute:
        raise LiveServerError("app %r is not `module:attribute`" % app)
    sys.path.insert(0, str(rest_dir_path))
    target = importlib.import_module(module_name)
    for part in attribute.split("."):
        target = getattr(target, part)
    return target


def _where(endpoint):
    """`file:line` of *endpoint*'s source, or None for an object without code."""
    code = getattr(endpoint, "__code__", None)
    if code is None:
        return None
    return "%s:%d" % (os.path.relpath(code.co_filename), code.co_firstlineno)


def _walk_routes(rest_dir_path, app):
    """{"docs": [...], "routes": [...]}: every route the app serves, as the
    installed FastAPI flattens its included routers, with the effective
    `include_in_schema` of each. Runs in the child `rest_routes` starts."""
    from fastapi import routing

    served = _load_app(rest_dir_path, app)
    # FastAPI that resolves included routers lazily keeps them as one entry in
    # app.routes and exposes iter_route_contexts to flatten them; an older one
    # copies each route into app.routes, which is flat already.
    flatten = getattr(routing, "iter_route_contexts", None)
    leaves = list(flatten(served.routes)) if flatten else list(served.routes)
    routes = []
    for leaf in leaves:
        original = getattr(leaf, "original_route", leaf)
        kind = type(original)
        in_schema = getattr(leaf, "include_in_schema", None)
        routes.append(
            {
                "type": "%s.%s" % (kind.__module__, kind.__qualname__),
                "api": isinstance(original, routing.APIRoute),
                "path": getattr(leaf, "path", None),
                "in_schema": in_schema if isinstance(in_schema, bool) else None,
                "where": _where(getattr(leaf, "endpoint", None)),
            }
        )
    # The routes the framework adds to serve the API's own documentation,
    # read from the app's settings so a project that renames or drops one is
    # judged by what it serves.
    docs = [
        getattr(served, name, None)
        for name in (
            "openapi_url",
            "docs_url",
            "redoc_url",
            "swagger_ui_oauth2_redirect_url",
        )
    ]
    return {"docs": sorted(d for d in docs if isinstance(d, str)), "routes": routes}


def rest_routes(root, rest_dir_path, timeout_s, app=None):
    """The `_walk_routes` record of the REST app, built in a child process so
    importing the app touches neither this process's modules nor its sys.path.
    *app* defaults to `e2e.server.app`, the object the scenario server loads."""
    app = load_server_config(root)["app"] if app is None else app
    try:
        proc = subprocess.run(
            [sys.executable, os.path.abspath(__file__), str(rest_dir_path), app],
            cwd=str(root),
            env=build_child_env(root=str(root)),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        raise LiveServerError(
            "walking the routes of %s did not finish within %ss (config/project.json "
            "`e2e.list_timeout_s`)" % (app, timeout_s)
        ) from None
    if proc.returncode != 0:
        raise LiveServerError(
            "walking the routes of %s exited with code %d: %s"
            % (app, proc.returncode, proc.stderr.strip())
        )
    try:
        return json.loads(proc.stdout)
    except ValueError:
        raise LiveServerError(
            "walking the routes of %s printed no JSON: %r" % (app, proc.stdout[:200])
        ) from None


def mcp_exchange(root, path, messages, timeout_s, extra_env=None):
    """Send *messages* to the MCP server script at *path* over its stdio, close
    its stdin, and return the decoded reply lines. A reply that is not JSON,
    a non-zero exit, or no exit within *timeout_s* (the group is killed) is a
    LiveServerError naming `e2e.list_timeout_s` for the timeout."""
    payload = "".join(json.dumps(m) + "\n" for m in messages)
    proc = subprocess.Popen(
        [sys.executable, str(path)],
        cwd=str(root),
        env=build_child_env(root=str(root), extra=extra_env),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        try:
            out, err = proc.communicate(payload, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            raise LiveServerError(
                "%s did not answer and exit within %ss (config/project.json "
                "`e2e.list_timeout_s`); it was killed" % (path, timeout_s)
            ) from None
    finally:
        _signal_group(proc.pid, signal.SIGKILL)
        proc.wait()
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            if stream is not None and not stream.closed:
                stream.close()
    if proc.returncode != 0:
        raise LiveServerError(
            "%s exited with code %s; stderr:\n%s" % (path, proc.returncode, err)
        )
    replies = []
    for number, line in enumerate(out.splitlines(), 1):
        if not line.strip():
            continue
        try:
            replies.append(json.loads(line))
        except ValueError:
            raise LiveServerError(
                "%s wrote a line that is not JSON-RPC (stdout line %d): %r"
                % (path, number, line[:200])
            ) from None
    return replies


if __name__ == "__main__":
    # The child `rest_routes` starts: argv is the REST directory and the app.
    sys.stdout.write(json.dumps(_walk_routes(sys.argv[1], sys.argv[2])) + "\n")
