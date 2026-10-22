"""
title: Serve the REST API
kind: script
layer: backend
summary: The REST transport's entry, run by `make run-api`. It caps its address space at config/project.json `transports.serve.memory_cap_mb` (scripts/resource_limits.py cap_memory) and serves the app under uvicorn, which drains the connections in flight for `transports.serve.shutdown_grace_seconds` on the first SIGTERM or SIGINT; scripts/resource_limits.py shutdown_owner, installed around it, takes the signal uvicorn raises again once it has stopped, so a stop exits 0 with `REST server: stopping on <signal>` on stderr rather than dying by the signal. Under --reload uvicorn's reload supervisor owns the signals instead and the owner line is not written.
"""

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
# The repository root, so the shared limits import as `scripts.resource_limits`,
# and the scripts directory, so the exit helper imports as `exit_codes`, as
# export_openapi.py imports it.
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "scripts"))

from exit_codes import ExitCode, finish, report  # noqa: E402
from scripts import config_loader, resource_limits  # noqa: E402

_LIMITS = "config/project.json transports.serve"


def main(argv=None):
    """Serve app:app from this directory on --host/--port until a stop signal."""
    parser = argparse.ArgumentParser(description="Serve the REST API under uvicorn.")
    parser.add_argument("--host", default="127.0.0.1", help="the address to bind")
    parser.add_argument("--port", type=int, required=True, help="the TCP port")
    parser.add_argument(
        "--reload", action="store_true", help="restart on a source change (development)"
    )
    args = parser.parse_args(argv)
    try:
        memory_cap, grace = resource_limits.serve_limits()
    except config_loader.ConfigError as exc:
        return report(
            ExitCode.CONFIG,
            "the REST server's limits are refused",
            "; ".join(exc.lines),
            "set %s inside its bound" % _LIMITS,
        )
    try:
        import uvicorn
    except ImportError:
        return report(
            ExitCode.BACKEND_ABSENT,
            "uvicorn is not installed",
            sys.executable,
            "install the REST transport's requirements (api/rest_fastapi/requirements.txt)",
        )
    sys.stderr.write(resource_limits.cap_memory(memory_cap) + "\n")
    with resource_limits.shutdown_owner("REST server"):
        uvicorn.run(
            "app:app",
            app_dir=_HERE,
            host=args.host,
            port=args.port,
            reload=args.reload,
            timeout_graceful_shutdown=grace,
        )
    return ExitCode.SUCCESS


if __name__ == "__main__":
    finish(main())
