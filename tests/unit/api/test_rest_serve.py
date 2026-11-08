"""
title: Unit — the REST transport's serve entry
kind: tests
layer: backend
summary: api/rest_fastapi/serve.py hands uvicorn the app, the host and port it was given and config/project.json `transports.serve.shutdown_grace_seconds`, caps memory at `transports.serve.memory_cap_mb` first, serves inside a shutdown owner, and returns CONFIG for a limit out of its bound before anything serves. uvicorn and the memory cap are fakes here, so no socket opens and the test process keeps its own limits; tests/e2e/test_server_shutdown.py starts the real server.
"""

import importlib.util
import json
import runpy
import shutil
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

from backend.shared import IdentityUnreadable  # noqa: E402

pytestmark = pytest.mark.unit

_SERVE = _ROOT / "api" / "rest_fastapi" / "serve.py"


def _load_serve(path):
    spec = importlib.util.spec_from_file_location("keel_rest_serve", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    module = _load_serve(_SERVE)
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


@pytest.mark.parametrize("reload", [False, True])
@pytest.mark.parametrize("manifest", ["[]", json.dumps({"name": 123}), "[" * 2000])
def test_unreadable_identity_is_config_before_server_or_reload_starts(
    serve, tmp_path, monkeypatch, capsys, reload, manifest
):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/project.json").write_text(manifest, encoding="utf-8")
    monkeypatch.setattr(serve, "_ROOT", str(tmp_path))
    argv = ["--port", "8123"] + (["--reload"] if reload else [])
    assert serve.main(argv) is ExitCode.CONFIG
    assert serve.runs == [] and serve.caps == []
    output = capsys.readouterr()
    assert output.out == ""
    assert len(output.err.splitlines()) == 1
    assert "config/project.json" in output.err and "repair" in output.err
    assert "Traceback" not in output.err


@pytest.mark.parametrize("reload", [False, True])
def test_symlinked_entry_preflights_the_identity_the_app_reads(
    serve, tmp_path, monkeypatch, capsys, reload
):
    _run_symlinked_entry(serve, tmp_path, monkeypatch, capsys, reload)


def _run_symlinked_entry(serve, tmp_path, monkeypatch, capsys, reload):
    real_root = tmp_path / "real"
    real_api = real_root / "api" / "rest_fastapi"
    real_api.mkdir(parents=True)
    for name in ("serve.py", "app.py", "schemas.py"):
        shutil.copyfile(_SERVE.parent / name, real_api / name)
    (real_root / "config").mkdir()
    (real_root / "config/project.json").write_text("[]", encoding="utf-8")

    entry_root = tmp_path / "entry"
    (entry_root / "api").mkdir(parents=True)
    (entry_root / "config").mkdir()
    (entry_root / "config/project.json").write_text(
        json.dumps({"name": "decoy"}), encoding="utf-8"
    )
    linked_api = entry_root / "api" / "rest_fastapi"
    linked_api.symlink_to(real_api, target_is_directory=True)
    monkeypatch.setattr(sys, "path", sys.path.copy())
    # Import the scratch copy, then restore any worker's cached schemas module.
    monkeypatch.setitem(sys.modules, "schemas", sys.modules.get("schemas"))
    monkeypatch.delitem(sys.modules, "schemas")

    # Import the actual app through the link: its reader rejects the real root.
    with pytest.raises(IdentityUnreadable, match="must be an object"):
        runpy.run_path(str(linked_api / "app.py"))
    linked_serve = _load_serve(linked_api / "serve.py")
    argv = ["--port", "8123"] + (["--reload"] if reload else [])
    assert linked_serve.main(argv) is ExitCode.CONFIG
    assert serve.runs == [] and serve.caps == []
    output = capsys.readouterr()
    assert output.out == ""
    assert len(output.err.splitlines()) == 1
    assert "identity is refused" in output.err and "repair" in output.err
    assert "Traceback" not in output.err


@pytest.mark.parametrize("reload", [False, True])
@pytest.mark.parametrize("cached", [False, True], ids=["absent", "cached"])
def test_symlinked_entry_restores_modules(
    serve, tmp_path, monkeypatch, capsys, reload, cached
):
    monkeypatch.delitem(sys.modules, "schemas", raising=False)
    if cached:
        spec = importlib.util.spec_from_file_location(
            "schemas", _SERVE.parent / "schemas.py"
        )
        schemas = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(schemas)
        monkeypatch.setitem(sys.modules, "schemas", schemas)
    before = sys.modules.get("schemas")

    with monkeypatch.context() as case_patch:
        _run_symlinked_entry(serve, tmp_path, case_patch, capsys, reload)

    assert sys.modules.get("schemas") is before, "schemas"
