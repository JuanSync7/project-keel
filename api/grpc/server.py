"""
title: gRPC API
layer: backend
public_api: no
summary: Thin gRPC transport over the backend domain. `serve` listens on config/project.json `transports.grpc.port` with `transports.grpc.workers` threads, read through scripts/config_loader.py, unless the caller names others; a configured value out of its bound is config_loader.WrongValue before any server exists.
"""

from __future__ import annotations

import sys
from concurrent import futures
from pathlib import Path

import grpc

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "src"))
# The repository root, so the config loader imports as `scripts.config_loader`.
sys.path.insert(1, str(_REPO))
# Generated from proto/thing.proto via `make gen`.
import thing_pb2  # noqa: E402
import thing_pb2_grpc  # noqa: E402
from scripts import config_loader  # noqa: E402

from backend import do_thing  # noqa: E402

_PORT = ("transports", "grpc", "port")
_WORKERS = ("transports", "grpc", "workers")


class ThingService(thing_pb2_grpc.ThingServiceServicer):
    def CreateThing(self, request, context):
        thing = do_thing(request.name, request.value)  # delegate to domain
        return thing_pb2.Thing(name=thing.name, value=thing.value)


def configured(root: str | None = None) -> dict:
    """{path: value} of the transport's keys in *root*'s config (this checkout
    when None); config_loader.WrongValue for a value out of its bound."""
    loaded = config_loader.read(str(_REPO) if root is None else root)
    return config_loader.resolve(
        loaded, config_loader.rows(_PORT, _WORKERS), config_loader.CONFIG_FILE
    )


def serve(
    port: int | None = None, workers: int | None = None, root: str | None = None
) -> None:
    """Serve ThingService until the server terminates; *port* and *workers*
    default to the configured values."""
    values = configured(root)
    port = values[_PORT] if port is None else port
    workers = values[_WORKERS] if workers is None else workers
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=workers))
    thing_pb2_grpc.add_ThingServiceServicer_to_server(ThingService(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    print(f"gRPC serving on :{port}")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
