"""
title: Checkpointer implementations
layer: backend
public_api: no
summary: In-memory and JSON-file Checkpointer backends for durable/ resumable runs.
"""
from __future__ import annotations

import copy
import json
import os
from typing import Optional

from .contracts import Checkpointer

__all__ = ["MemoryCheckpointer", "FileCheckpointer"]


class MemoryCheckpointer(Checkpointer):
    """Process-local checkpointer: keeps snapshots in a dict (deep-copied).

    Good for tests and single-process pauses. Holds arbitrary Python state (no
    JSON constraint), but does not survive process exit -- use FileCheckpointer
    for crash recovery across processes.
    """

    def __init__(self):
        self._store = {}

    def save(self, key, snapshot):
        """Store a deep copy of ``snapshot`` so later state mutation can't bleed in."""
        self._store[key] = copy.deepcopy(snapshot)

    def load(self, key):
        """Return a deep copy of the snapshot under ``key`` (or None)."""
        snap = self._store.get(key)
        return copy.deepcopy(snap) if snap is not None else None

    def clear(self, key):
        """Drop the snapshot under ``key`` if present."""
        self._store.pop(key, None)


class FileCheckpointer(Checkpointer):
    """JSON-file checkpointer for cross-process crash recovery.

    Each ``key`` is a ``<key>.json`` file under a directory. State must be
    JSON-serialisable (the price of surviving a process exit). Writes are atomic
    (temp file + rename) so a crash mid-write can't corrupt the snapshot.
    """

    def __init__(self, directory: str):
        self.directory = directory
        os.makedirs(directory, exist_ok=True)

    def _path(self, key):
        safe = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in key)
        return os.path.join(self.directory, safe + ".json")

    def save(self, key, snapshot):
        """Atomically write ``snapshot`` as JSON (temp file + os.replace)."""
        path = self._path(key)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(snapshot, fh, sort_keys=True)
        os.replace(tmp, path)

    def load(self, key) -> Optional[dict]:
        """Return the JSON snapshot under ``key``, or None if absent."""
        path = self._path(key)
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    def clear(self, key):
        """Remove the snapshot file under ``key`` if present."""
        path = self._path(key)
        if os.path.exists(path):
            os.remove(path)
