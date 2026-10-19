"""
title: Fixture — one test per kind of reach, outside the temp roots and inside them
kind: tests
layer: n/a
summary: Not collected here (the name is not test_*). tests/integration/test_isolation_gate.py copies it into a scratch project as a unit test file, where the isolation guard must fail each `test_outside_*` case and the swallowed one, and pass each `test_inside_*` case. OUTSIDE is a directory beside the scratch project, outside every temp root the inner run has.
"""

import socket
import sqlite3
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

# The scratch project is <case dir>/proj; OUTSIDE sits beside it.
OUTSIDE = Path(__file__).resolve().parents[3] / "outside"


def test_outside_socket():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.01)
    try:
        # 192.0.2.0/24 is TEST-NET-1: never routed, so no packet leaves.
        sock.connect(("192.0.2.1", 9))
    except OSError:
        pass
    finally:
        sock.close()


def test_outside_write():
    (OUTSIDE / "written.txt").write_text("reached", encoding="utf-8")


def test_outside_sqlite():
    sqlite3.connect(str(OUTSIDE / "outside.db")).close()


def test_swallowed_write():
    try:  # noqa: SIM105 -- a try block is the shape a test that swallows an error has
        (OUTSIDE / "swallowed.txt").write_text("reached", encoding="utf-8")
    except Exception:  # noqa: BLE001 -- the case proves a swallowed refusal still fails the test
        pass


def test_inside_socket(tmp_path, monkeypatch):
    # A relative name: an AF_UNIX path is capped near 108 bytes, and tmp_path
    # can be longer than that.
    monkeypatch.chdir(tmp_path)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind("s")
        server.listen(1)
        client.connect("s")
    finally:
        client.close()
        server.close()


def test_inside_write(tmp_path):
    (tmp_path / "written.txt").write_text("inside", encoding="utf-8")
    assert (tmp_path / "written.txt").read_text(encoding="utf-8") == "inside"


def test_inside_sqlite(tmp_path):
    con = sqlite3.connect(str(tmp_path / "inside.db"))
    try:
        con.execute("create table t (x)")
    finally:
        con.close()
