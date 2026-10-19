"""
title: Fixture — a listed store is reached only through a per-test copy
kind: tests
layer: n/a
summary: Not collected here (the name is not test_*). tests/integration/test_isolation_gate.py copies it into a scratch project whose config/project.json `tests.isolation.stores` lists OUTSIDE/live.db. The store_copy fixture hands a test its own copy, which it may change; opening the live store directly fails, after a copy and after a copy that failed too, and asking for a store the list does not name fails naming the key.
"""

import sqlite3
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

OUTSIDE = Path(__file__).resolve().parents[3] / "outside"


def test_store_copy_gives_the_test_its_own_copy(store_copy):
    copy = store_copy(str(OUTSIDE / "live.db"))
    con = sqlite3.connect(str(copy))
    try:
        assert con.execute("select x from t").fetchall() == [("live",)]
        con.execute("insert into t values ('changed by the test')")
        con.commit()
    finally:
        con.close()


def test_reading_the_live_store_is_refused():
    with open(str(OUTSIDE / "live.db"), "rb") as fh:
        fh.read()


def test_reading_the_live_store_after_a_copy_is_refused(store_copy):
    store_copy(str(OUTSIDE / "live.db"))
    with open(str(OUTSIDE / "live.db"), "rb") as fh:
        fh.read()


def test_reading_the_live_store_after_a_failed_copy_is_refused(store_copy, tmp_path):
    # A directory where the copy goes makes the copy fail inside its read
    # allowance, which must end with it.
    (tmp_path / "stores" / "live.db" / "live.db").mkdir(parents=True)
    with pytest.raises(IsADirectoryError):
        store_copy(str(OUTSIDE / "live.db"))
    with open(str(OUTSIDE / "live.db"), "rb") as fh:
        fh.read()


def test_an_unlisted_store_is_named(store_copy):
    store_copy(str(OUTSIDE / "unlisted.db"))
