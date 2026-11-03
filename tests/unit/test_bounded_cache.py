"""
title: Unit — a cache holds at most the configured number of entries
kind: tests
layer: n/a
summary: tests/bounded_cache.py over a project config written to a temporary root. `max_entries` reads config/project.json `tests.cache_max_entries`, takes the default when the key is absent, and refuses 0, a negative and a non-integer value naming the key; `bounded` caches a call by its arguments and, past the maximum, drops the least recently used entry, so that call runs again.
"""

import json

import config_loader
import pytest

import bounded_cache

pytestmark = pytest.mark.unit

_KEY = "tests.cache_max_entries"


def _root(tmp_path, tests_block):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.json").write_text(
        json.dumps({"tests": tests_block}), encoding="utf-8"
    )
    return str(tmp_path)


def test_the_maximum_is_the_configured_value(tmp_path):
    assert bounded_cache.max_entries(_root(tmp_path, {"cache_max_entries": 7})) == 7


def test_an_absent_maximum_takes_the_default_and_says_so(tmp_path, capsys):
    assert bounded_cache.max_entries(_root(tmp_path, {})) == bounded_cache.DEFAULT
    assert "[using default] %s" % _KEY in capsys.readouterr().err


@pytest.mark.parametrize("value", [0, -1, 2.5, "8", None])
def test_a_maximum_the_loader_refuses_names_the_key(tmp_path, value):
    with pytest.raises(config_loader.ConfigError, match=_KEY):
        bounded_cache.max_entries(_root(tmp_path, {"cache_max_entries": value}))


def test_a_call_is_cached_by_its_arguments(tmp_path):
    calls = []

    @bounded_cache.bounded(_root(tmp_path, {"cache_max_entries": 4}))
    def square(n):
        calls.append(n)
        return n * n

    assert [square(3), square(3), square(4)] == [9, 9, 16]
    assert calls == [3, 4]


def test_past_the_maximum_the_least_recently_used_entry_runs_again(tmp_path):
    calls = []

    @bounded_cache.bounded(_root(tmp_path, {"cache_max_entries": 2}))
    def same(n):
        calls.append(n)
        return n

    for n in (1, 2, 1, 3, 2, 1):
        same(n)
    # 3 drops 2, the least recently used; then 2 drops 1, and 1 runs again.
    assert calls == [1, 2, 3, 2, 1]
    assert same.cache_info().maxsize == 2
