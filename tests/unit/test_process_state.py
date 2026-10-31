"""
title: Unit — process_state says whether a pid a test started still runs
kind: tests
layer: n/a
summary: tests/process_state.py alive. This process is alive; a pid signal 0 cannot find is not; a zombie and a dying task are not; a pid reaped after signal 0 found it is not, whether /proc is gone at the open or the read raises; and a /proc that cannot be read for another reason counts as running.
"""

import io
import os

import pytest

import process_state

pytestmark = pytest.mark.unit

_PID = 999_999_999


def test_this_process_is_alive():
    assert process_state.alive(os.getpid()) is True


def test_a_pid_signal_0_cannot_find_is_gone():
    assert process_state.alive(_PID) is False


def _found_by_signal_0(monkeypatch, opener):
    monkeypatch.setattr(os, "kill", lambda pid, sig: None)
    monkeypatch.setattr("builtins.open", opener)


@pytest.mark.parametrize(
    ("state", "running"),
    [("S", True), ("R", True), ("D", True), ("Z", False), ("X", False)],
)
def test_the_proc_state_decides(monkeypatch, state, running):
    stat = "%d (a (name) with) %s 1 1 1\n" % (_PID, state)
    _found_by_signal_0(monkeypatch, lambda *a, **k: io.StringIO(stat))
    assert process_state.alive(_PID) is running


class _ReapedWhileRead:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        raise ProcessLookupError(3, "No such process")


@pytest.mark.parametrize(
    "opener",
    [
        pytest.param(
            lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("stat")),
            id="reaped-before-the-open",
        ),
        pytest.param(lambda *a, **k: _ReapedWhileRead(), id="reaped-while-read"),
    ],
)
def test_a_pid_reaped_after_signal_0_found_it_is_gone(monkeypatch, opener):
    _found_by_signal_0(monkeypatch, opener)
    assert process_state.alive(_PID) is False


def test_a_proc_that_cannot_be_read_counts_as_running(monkeypatch):
    def denied(*_args, **_kwargs):
        raise PermissionError("stat")

    _found_by_signal_0(monkeypatch, denied)
    assert process_state.alive(_PID) is True
