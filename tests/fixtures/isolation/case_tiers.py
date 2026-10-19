"""
title: Fixture — the closest tier marker decides what a test may reach
kind: tests
layer: n/a
summary: Not collected here (the name is not test_*). tests/integration/test_isolation_gate.py copies it into a scratch project as a unit test file. The module is marked unit; a loopback connect passes in the function marked integration and fails in the one left to the module's marker, and a reach under xfail fails rather than counting as the expected failure.
"""

import socket
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

OUTSIDE = Path(__file__).resolve().parents[3] / "outside"


def _loopback_round_trip():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        client.connect(server.getsockname())
    finally:
        client.close()
        server.close()


@pytest.mark.integration
def test_loopback_marked_integration():
    _loopback_round_trip()


def test_loopback_under_unit():
    _loopback_round_trip()


@pytest.mark.xfail(reason="an expected failure must not hide a reach")
def test_violation_under_xfail():
    (OUTSIDE / "xfail.txt").write_text("reached", encoding="utf-8")
    raise AssertionError("the expected failure")
