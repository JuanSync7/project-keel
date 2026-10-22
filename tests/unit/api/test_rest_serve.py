"""
title: Unit — the REST transport's serve entry
kind: tests
layer: backend
summary: api/rest_fastapi/serve.py hands uvicorn the app, the host and port it was given and config/project.json `transports.serve.shutdown_grace_seconds`, caps memory at `transports.serve.memory_cap_mb` first, serves inside a shutdown owner, and returns CONFIG for a limit out of its bound before anything serves. uvicorn and the memory cap are fakes here, so no socket opens and the test process keeps its own limits; tests/e2e/test_server_shutdown.py starts the real server.
"""

import importlib.util
import signal
import sys
import types
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts"))

from exit_codes import ExitCode  # noqa: E402
from scripts import config_loader, resource_limits  # noqa: E402

pytestmark = pytest.mark.unit

_SERVE = _ROOT / "api" / "rest_fastapi" / "serve.py"


@pytest.fixture
def serve(monkeypatch):
    """serve.py loaded with a fake uvicorn; `.runs` holds each uvicorn.run's
    keyword arguments and the SIGTERM handler in force during it, `.caps` each
    cap asked for."""
    runs, caps = [], []
    fake = types.ModuleType("uvicorn")

    def run(app, **kwargs):
        runs.append(dict(kwargs, app=app, handler=signal.getsignal(signal.SIGTERM)))

    fake.run = run
    monkeypatch.setitem(sys.modules, "uvicorn", fake)
    monkeypatch.setattr(
        resource_limits, "cap_memory", lambda mb: caps.append(mb) or "memory cap: seen"
    )
    spec = importlib.util.spec_from_file_location("keel_rest_serve", _SERVE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.runs, module.caps = runs, caps
    return module


def test_uvicorn_gets_the_app_the_address_and_the_configured_grace(serve):
    cap, grace = resource_limits.serve_limits()
    before = signal.getsignal(signal.SIGTERM)
    assert serve.main(["--port", "8123"]) is ExitCode.SUCCESS
    (run,) = serve.runs
    assert run["app"] == "app:app"
    assert (run["host"], run["port"], run["reload"]) == ("127.0.0.1", 8123, False)
    assert run["timeout_graceful_shutdown"] == grace
    assert run["app_dir"] == str(_SERVE.parent)
    assert serve.caps == [cap]
    assert run["handler"] not in (before, signal.SIG_DFL), "no owner while serving"
    assert signal.getsignal(signal.SIGTERM) is before


def test_a_limit_out_of_bound_is_config_before_anything_serves(
    serve, monkeypatch, capsys
):
    def wrong(root=None):
        raise config_loader.WrongValue(
            "config/project.json", ["transports.serve.memory_cap_mb must be >= 1"]
        )

    monkeypatch.setattr(resource_limits, "serve_limits", wrong)
    assert serve.main(["--port", "8123"]) is ExitCode.CONFIG
    assert serve.runs == [] and serve.caps == []
    assert "transports.serve.memory_cap_mb" in capsys.readouterr().err
