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
updated: 2026-11-12
visibility: internal
canonical: true
---

# API — gRPC

Thin gRPC transport (HTTP/2 + protobuf) over the backend domain.

gRPC service over HTTP/2 with protobuf. The `.proto` is the contract;
Python stubs are generated, not committed.

```bash
pip install -r requirements.txt   # or, in a checkout: pip install -e ".[grpc]"
make gen          # generate thing_pb2*.py from proto/thing.proto
python server.py  # serves on :50051
```

- `proto/thing.proto` — service + messages (mirror `src/shared/`).
- `server.py` — servicer; `CreateThing` calls `backend.do_thing` (thin).

The `grpc` extra in `pyproject.toml` holds the same packages as
`requirements.txt`. A project that serves gRPC names it in
`config/project.json` `transports.extras`, so `make check-venv` fails a venv
without them and `tests/optional_deps.py` turns a skipped gRPC test into a
failure. `tests/unit/scripts/test_check_venv.py` holds the extra and
`requirements.txt` equal.
