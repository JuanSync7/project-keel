"""
title: bounded cache — a cache holds at most the configured number of entries
summary: `bounded(root)` is the one way a test module caches a function: functools.lru_cache with its maximum read from config/project.json `tests.cache_max_entries` under *root*, through scripts/config_loader.py, so the maximum is neither absent nor typed into code (R-CODE-24). Past the maximum the least recently used entry is dropped and its call runs again. `max_entries(root)` is that read; an absent key takes `DEFAULT`, the KEYS row's default, and the loader's `[using default]` line says so, and a value below 1 or not an integer raises config_loader.ConfigError naming the key. pyproject.toml's ruff TID251 bans `functools.cache` and `functools.lru_cache` everywhere else. A cache lives as long as the process; it is never written to disk.
"""

import functools
import os
import sys
from typing import Any, Callable, TypeVar

_SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import config_loader  # noqa: E402

__all__ = ["DEFAULT", "KEY", "bounded", "max_entries"]

KEY = ("tests", "cache_max_entries")
DEFAULT = config_loader.rows(KEY)[0].default

_F = TypeVar("_F", bound=Callable[..., Any])


def max_entries(root: str) -> int:
    """config/project.json `tests.cache_max_entries` under *root*. Raises
    config_loader.ConfigError, naming the key, for a value the loader
    refuses."""
    values = config_loader.resolve(
        config_loader.read(root), config_loader.rows(KEY), config_loader.CONFIG_FILE
    )
    return int(values[KEY])


def bounded(root: str) -> Callable[[_F], _F]:
    """A decorator that caches a function by its arguments, holding at most
    `max_entries(root)` entries."""
    return functools.lru_cache(maxsize=max_entries(root))  # noqa: TID251 -- the maximum is read from config
