"""
title: Fixture — one test per further seam the guard judges, outside the temp roots and inside them
kind: tests
layer: n/a
summary: Not collected here (the name is not test_*). tests/integration/test_isolation_gate.py copies it into a scratch project as a unit test file, where the isolation guard must fail each `test_outside_*` case (a mode change, a time change, a time change through a link, a sendmsg to a routable address, an AF_UNIX bind, a file in a `__pycache__` that is not bytecode, a `file:` database name opened in the checkout) and pass each `test_inside_*` case, a tree copied with an outbound link among them. OUTSIDE is a directory beside the scratch project, outside every temp root the inner run has.
"""

import os
import shutil
import socket
import sqlite3
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

# The scratch project is <case dir>/proj; OUTSIDE sits beside it.
PROJECT = Path(__file__).resolve().parents[2]
OUTSIDE = PROJECT.parent / "outside"


def test_outside_chmod():
    os.chmod(str(OUTSIDE / "kept.txt"), 0o600)


def test_outside_touch():
    # An existing file: Path.touch changes its times through os.utime alone.
    (OUTSIDE / "kept.txt").touch()


def test_outside_touch_through_a_link(tmp_path):
    # os.utime follows the link, so the time that changes is OUTSIDE's.
    (tmp_path / "link").symlink_to(OUTSIDE / "kept.txt")
    os.utime(str(tmp_path / "link"))


def test_outside_sendmsg():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # 192.0.2.0/24 is TEST-NET-1: never routed, so no packet leaves.
        sock.sendmsg([b"x"], [], 0, ("192.0.2.1", 9))
    finally:
        sock.close()


def test_outside_unix_bind(monkeypatch):
    # A relative name: an AF_UNIX path is capped near 108 bytes.
    monkeypatch.chdir(str(OUTSIDE))
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.bind("s")
    finally:
        sock.close()


def test_outside_pycache_note():
    (OUTSIDE / "__pycache__" / "notes.json").write_text("{}", encoding="utf-8")


def test_outside_sqlite_file_name(monkeypatch):
    # Without uri=True sqlite opens this name as a file in the checkout.
    monkeypatch.chdir(str(PROJECT))
    sqlite3.connect("file:x?mode=memory").close()


def test_inside_chmod(tmp_path):
    (tmp_path / "f").write_text("x", encoding="utf-8")
    os.chmod(str(tmp_path / "f"), 0o600)
    (tmp_path / "f").touch()


def test_inside_copytree_keeps_an_outbound_link(tmp_path):
    # shutil copies the link's own times and attributes, never its target's.
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "link").symlink_to(OUTSIDE / "kept.txt")
    shutil.copytree(str(tmp_path / "src"), str(tmp_path / "dst"), symlinks=True)
    assert os.readlink(str(tmp_path / "dst" / "link")) == str(OUTSIDE / "kept.txt")


def test_inside_sendmsg_on_a_socketpair():
    left, right = socket.socketpair()
    try:
        left.sendmsg([b"x"])
        assert right.recv(1) == b"x"
    finally:
        left.close()
        right.close()


def test_inside_sqlite_file_name(tmp_path, monkeypatch):
    monkeypatch.chdir(str(tmp_path))
    sqlite3.connect("file:x?mode=memory").close()
