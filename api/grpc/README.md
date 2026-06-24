---
title: API — gRPC
kind: api
layer: backend
status: template
owner: TBD
public_api: api/grpc/proto/thing.proto
tags: []
summary: Thin gRPC transport (HTTP/2 + protobuf) over the backend domain.
id: api-grpc-readme
created: 2026-06-17
updated: 2026-06-17
visibility: internal
canonical: true
---

# API — gRPC

Thin gRPC transport (HTTP/2 + protobuf) over the backend domain.

gRPC service over HTTP/2 with protobuf. The `.proto` is the contract;
Python stubs are generated, not committed.

```bash
pip install -r requirements.txt
make gen          # generate thing_pb2*.py from proto/thing.proto
python server.py  # serves on :50051
```

- `proto/thing.proto` — service + messages (mirror `src/shared/`).
- `server.py` — servicer; `CreateThing` calls `backend.do_thing` (thin).
