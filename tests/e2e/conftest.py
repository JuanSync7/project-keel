"""
title: E2E fixtures — the REST server on a loopback socket, and an MCP server over its stdio
summary: `rest_server` starts the REST transport once per session as a real uvicorn process through tests/live_server.py (host, readiness probe and timeouts from config/project.json `e2e.server`, the port from the OS) and stops it, whatever the scenarios did; it skips, naming the `transport` extra, without uvicorn or FastAPI. `mcp_session` hands a scenario a function that runs one JSON-RPC exchange with an MCP server script over its real stdio, with `e2e.mcp_env` added to its environment and bounded by `e2e.list_timeout_s`.
"""

import os

import pytest

import live_server
import optional_deps

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="session")
def rest_server(real_corpus):
    """The handle of a live REST server: `.base_url`, `.request()`, `.json()`.
    It depends on `real_corpus` because the showcase routes read the corpus."""
    optional_deps.importorskip("uvicorn", extra="transport")
    optional_deps.importorskip("fastapi", extra="transport")
    with live_server.live_server(_ROOT, live_server.rest_dir(_ROOT)) as server:
        yield server


@pytest.fixture
def mcp_session():
    """A function `(server script path, messages) -> replies` that speaks
    newline-delimited JSON-RPC to the server over its stdio, then closes it."""
    timeout, extra = live_server.load_mcp_config(_ROOT)

    def exchange(path, messages):
        return live_server.mcp_exchange(_ROOT, path, messages, timeout, extra)

    return exchange
