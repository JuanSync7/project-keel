"""
title: Unit — the gRPC transport's server entry
kind: tests
layer: backend
summary: api/grpc/server.py `serve` listens on config/project.json `transports.grpc.port` with `transports.grpc.workers` threads unless the caller names others, refuses a port or worker count outside its bound through scripts/config_loader.py before a server exists, and its entry `main` turns any refused setting, a serve limit included, into exit CONFIG through the exit helper with the key on stderr before anything listens, and is driven here against fake `grpc` and generated-stub modules, so neither grpcio nor a socket is needed.
"""

import importlib.util
import json
import os
import signal
import sys
import types
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts"))

from exit_codes import ExitCode  # noqa: E402
from scripts import config_loader  # noqa: E402

pytestmark = pytest.mark.unit

_SERVER = _ROOT / "api" / "grpc" / "server.py"


class _FakeServer:
    """What grpc.server returns, recording what the transport asked of it."""

    def __init__(self, executor):
        self.workers = executor._max_workers
        self.ports = []
        self.events = []
        self.signal_while_waiting = False

    def add_insecure_port(self, address):
        self.ports.append(address)
        return 1

    def start(self):
        self.events.append("start")

    def wait_for_termination(self, timeout=None):
        self.events.append("wait")
        if self.signal_while_waiting:
            # A real server blocks here until stop; the signal stands in for
            # the operator's SIGTERM arriving while it serves.
            os.kill(os.getpid(), signal.SIGTERM)
        return True

    def stop(self, grace):
        self.events.append(("stop", grace))


@pytest.fixture
def grpc_server(monkeypatch):
    """api/grpc/server.py loaded against fake grpc modules; `.made` lists the
    fake servers it built."""
    made = []

    def server(executor):
        made.append(_FakeServer(executor))
        return made[-1]

    fake_grpc = types.ModuleType("grpc")
    fake_grpc.server = server
    stubs = types.ModuleType("thing_pb2_grpc")
    stubs.ThingServiceServicer = object
    stubs.add_ThingServiceServicer_to_server = lambda servicer, srv: None
    monkeypatch.setitem(sys.modules, "grpc", fake_grpc)
    monkeypatch.setitem(sys.modules, "thing_pb2", types.ModuleType("thing_pb2"))
    monkeypatch.setitem(sys.modules, "thing_pb2_grpc", stubs)
    spec = importlib.util.spec_from_file_location("keel_grpc_server", _SERVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.made = made
    module.caps = []
    # The real cap would bound the test process itself.
    monkeypatch.setattr(module.resource_limits, "cap_memory", _record(module.caps))
    return module


def _record(caps):
    def cap_memory(megabytes):
        caps.append(megabytes)
        return "memory cap: recorded"

    return cap_memory


def _project(tmp_path, grpc_block):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.json").write_text(
        json.dumps({"transports": {"grpc": grpc_block}}), encoding="utf-8"
    )
    return str(tmp_path)


def test_serve_listens_on_the_configured_port_with_the_configured_workers(
    grpc_server, tmp_path
):
    grpc_server.serve(root=_project(tmp_path, {"port": 50123, "workers": 3}))
    (server,) = grpc_server.made
    assert server.ports == ["[::]:50123"]
    assert server.workers == 3
    assert server.events[:2] == ["start", "wait"]


def test_a_port_and_worker_count_the_caller_names_win(grpc_server, tmp_path):
    root = _project(tmp_path, {"port": 50123, "workers": 3})
    grpc_server.serve(port=50999, workers=2, root=root)
    (server,) = grpc_server.made
    assert (server.ports, server.workers) == (["[::]:50999"], 2)


@pytest.mark.parametrize(
    "block, key",
    [
        ({"port": 0}, "transports.grpc.port"),
        ({"port": 65536}, "transports.grpc.port"),
        ({"port": "50051"}, "transports.grpc.port"),
        ({"workers": 0}, "transports.grpc.workers"),
        ({"workers": True}, "transports.grpc.workers"),
    ],
)
def test_a_port_or_worker_count_out_of_bound_is_refused_before_a_server(
    grpc_server, tmp_path, block, key
):
    with pytest.raises(config_loader.WrongValue, match=key.replace(".", r"\.")):
        grpc_server.serve(root=_project(tmp_path, block))
    assert grpc_server.made == []


def test_serve_caps_memory_at_the_configured_size_before_it_listens(
    grpc_server, tmp_path
):
    root = _project(tmp_path, {"port": 50123})
    (tmp_path / "config" / "project.json").write_text(
        json.dumps({"transports": {"serve": {"memory_cap_mb": 512}}}),
        encoding="utf-8",
    )
    grpc_server.serve(root=root)
    assert grpc_server.caps == [512]


def test_sigterm_while_serving_stops_the_server_with_the_configured_grace(
    grpc_server, tmp_path, monkeypatch, capsys
):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.json").write_text(
        json.dumps({"transports": {"serve": {"shutdown_grace_seconds": 3}}}),
        encoding="utf-8",
    )
    before = signal.getsignal(signal.SIGTERM)
    real_server = grpc_server.grpc.server

    def server(executor):
        made = real_server(executor)
        made.signal_while_waiting = True
        return made

    monkeypatch.setattr(grpc_server.grpc, "server", server)
    grpc_server.serve(root=str(tmp_path))
    (made,) = grpc_server.made
    assert made.events == ["start", "wait", ("stop", 3)]
    assert "gRPC server: stopping on SIGTERM" in capsys.readouterr().err
    assert signal.getsignal(signal.SIGTERM) is before


@pytest.mark.parametrize(
    "block, key",
    [
        ({"serve": {"memory_cap_mb": 0}}, "transports.serve.memory_cap_mb"),
        ({"grpc": {"port": 0}}, "transports.grpc.port"),
    ],
)
def test_main_fails_a_refused_setting_as_config_before_a_server(
    grpc_server, tmp_path, capsys, block, key
):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.json").write_text(
        json.dumps({"transports": block}), encoding="utf-8"
    )
    assert grpc_server.main(root=str(tmp_path)) is ExitCode.CONFIG
    assert grpc_server.made == [] and grpc_server.caps == []
    assert key in capsys.readouterr().err


def test_main_is_success_once_the_server_has_stopped(grpc_server, tmp_path):
    assert grpc_server.main(root=_project(tmp_path, {"port": 50123})) is (
        ExitCode.SUCCESS
    )
    assert grpc_server.made[0].events[:2] == ["start", "wait"]
