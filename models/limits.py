"""
title: Model call limits
layer: backend
public_api: no
summary: The configured bounds on one model call, read through scripts/config_loader.py from config/project.json of the checkout (or a root a caller names). `timeout_seconds(adapter)` is the adapter's entry in `models.timeout_seconds`; an adapter that calls out and has no entry is a ValueError naming the key and the entry to add, so a call is never left unbounded by an omission. `max_reply_bytes()` is `models.max_reply_bytes`, the most one reply, an HTTP body or a model child's output stream, may hold. A value out of its bound is config_loader.WrongValue.
"""

from __future__ import annotations

import os

from scripts import config_loader

__all__ = ["max_reply_bytes", "timeout_seconds"]

_TIMEOUTS = ("models", "timeout_seconds")
_REPLY_CAP = ("models", "max_reply_bytes")
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _resolved(path: tuple, root: str | None) -> object:
    loaded = config_loader.read(_REPO if root is None else root)
    values = config_loader.resolve(
        loaded, config_loader.rows(path), config_loader.CONFIG_FILE
    )
    return values[path]


def timeout_seconds(adapter: str, root: str | None = None) -> float:
    """The seconds one call of *adapter* may take, from *root*'s config (this
    checkout when None)."""
    table = _resolved(_TIMEOUTS, root)
    assert isinstance(table, dict)  # the KEYS row's type is object
    if adapter not in table:
        raise ValueError(
            "config/project.json models.timeout_seconds has no entry for %r, so "
            'its calls would have no time limit; add "%s": <seconds>'
            % (adapter, adapter)
        )
    return float(table[adapter])


def max_reply_bytes(root: str | None = None) -> int:
    """The bytes one model reply may hold, from *root*'s config (this checkout
    when None)."""
    cap = _resolved(_REPLY_CAP, root)
    assert isinstance(cap, int)  # the KEYS row's type is int
    return cap
