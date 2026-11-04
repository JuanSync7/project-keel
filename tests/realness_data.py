"""
title: Realness data — the libraries and fixtures that replace a dependency
summary: The tables tests/realness.py reads, from pyverdex's static realness classifier, kept apart from the logic (CONVENTIONS §18). `RANKS` orders the tiers, lowest first. `LIBRARIES` maps an import path to the tier a test that uses it is put in; a use is matched by the longest dotted prefix, so `unittest.mock.patch` is `mock` and `unittest.TestCase` is nothing. `NAMES` holds the class names that put a test in a tier with no classifying import (`httpx.ASGITransport`). `PLUGIN_FIXTURES` maps a fixture a pytest plugin provides, which no `conftest.py` defines, to its tier, or to None for a control signal that never demotes (`tmp_path`, `caplog`, `freezer`). A library or fixture absent from every table contributes nothing. It reads nothing and writes nothing.
"""

from typing import Dict, Optional

__all__ = ["LIBRARIES", "NAMES", "PLUGIN_FIXTURES", "RANKS"]

# Lowest first: a test's tier is the lowest among its signals.
RANKS: Dict[str, int] = {"mock": 0, "fake": 1, "in_process": 2, "real": 3}

LIBRARIES: Dict[str, str] = {
    "aioresponses": "mock",
    "django.test": "in_process",
    "docker": "real",
    "fakeredis": "fake",
    "fastapi.testclient": "in_process",
    "flask.testing": "in_process",
    "httpretty": "mock",
    "mock": "mock",
    "mongomock": "fake",
    "moto": "fake",
    "pyfakefs": "fake",
    "pytest_mock": "mock",
    "requests_mock": "mock",
    "respx": "mock",
    "responses": "mock",
    "starlette.testclient": "in_process",
    "testcontainers": "real",
    "unittest.mock": "mock",
    "vcr": "mock",
}

NAMES: Dict[str, str] = {
    "ASGITransport": "in_process",
    "TestClient": "in_process",
}

# None is listed, not left out, so a reader sees the control signals were
# judged neutral rather than forgotten.
PLUGIN_FIXTURES: Dict[str, Optional[str]] = {
    "caplog": None,
    "capfd": None,
    "capfdbinary": None,
    "capsys": None,
    "freezer": None,
    "httpx_mock": "mock",
    "mocker": "mock",
    "monkeypatch": "mock",
    "recwarn": None,
    "request": None,
    "requests_mock": "mock",
    "responses": "mock",
    "time_machine": None,
    "tmp_path": None,
    "tmp_path_factory": None,
    "tmpdir": None,
}
