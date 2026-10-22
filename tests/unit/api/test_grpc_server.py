"""
title: Unit — the gRPC transport's server entry
kind: tests
layer: backend
summary: api/grpc/server.py `serve` listens on config/project.json `transports.grpc.port` with `transports.grpc.workers` threads unless the caller names others, refuses a port or worker count outside its bound through scripts/config_loader.py before a server exists, and is driven here against fake `grpc` and generated-stub modules, so neither grpcio nor a socket is needed.
"""

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from scripts import config_loader  # noqa: E402

pytestmark = pytest.mark.unit

_SERVER = _ROOT / "api" / "grpc" / "server.py"


class _FakeServer:
    """What grpc.server returns, recording what the transport asked of it."""

    def __init__(self, executor):
        self.workers = executor._max_workers
        self.ports = []
        self.events = []

    def add_insecure_port(self, address):
        self.ports.append(address)
        return 1

    def start(self):
        self.events.append("start")

    def wait_for_termination(self, timeout=None):
        self.events.append("wait")
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
    return module


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
