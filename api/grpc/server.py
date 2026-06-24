"""
title: gRPC API
layer: backend
public_api: no
summary: Thin gRPC transport over the backend domain.
"""
from __future__ import annotations

import sys
from concurrent import futures
from pathlib import Path

import grpc

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from backend import do_thing  # noqa: E402

# Generated from proto/thing.proto via `make gen`.
import thing_pb2  # noqa: E402
import thing_pb2_grpc  # noqa: E402


class ThingService(thing_pb2_grpc.ThingServiceServicer):
    def CreateThing(self, request, context):
        thing = do_thing(request.name, request.value)  # delegate to domain
        return thing_pb2.Thing(name=thing.name, value=thing.value)


def serve(port: int = 50051) -> None:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    thing_pb2_grpc.add_ThingServiceServicer_to_server(ThingService(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    print(f"gRPC serving on :{port}")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
