"""
title: Render cache — one copier render per answer set per session, and a private copy for each test
summary: `RenderCache` renders a project once for each distinct answer set and day, through the renderer its caller passes (copier in the suite), under a root of the session's scratch, and `copy_into` hands each test a copy of that render at the path the test names, with symlinks kept as links and every file's mode as the renderer left it. The shared render is made read-only once it is made, so a test that writes into it instead of into its own copy fails with PermissionError at the write; that is the guard against two tests sharing a writable folder. A renderer that raises leaves nothing cached and the next request renders again; one that writes nothing raises RenderError naming the answers; a copy over an existing path raises FileExistsError. `close` makes the renders writable again and removes them. Nothing persists past the session: a render cache that survived a run would pass a test against a template that has since changed.
"""

import datetime
import hashlib
import json
import os
import shutil
import stat
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping

Renderer = Callable[[Path, Dict[str, Any]], None]

# Every write bit: the render is frozen for its owner and for anyone else.
_WRITE_BITS = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH


class RenderError(Exception):
    """A render the cache refuses to hand out: the renderer wrote nothing."""


def answer_key(answers: Mapping[str, Any], day: datetime.date) -> str:
    """The canonical text of an answer set on *day*: two dicts that hold the
    same answers in another order give the same key. The day is part of it
    because the render stamps each document's `updated:` with the day it is
    made (copier.yml `_tasks`), so a render made yesterday is not the project
    the same answers give today."""
    return json.dumps(
        {"answers": answers, "day": day.isoformat()},
        sort_keys=True,
        separators=(",", ":"),
    )


def _frozen_modes(root: Path) -> Dict[str, int]:
    """Every path under *root*, symlinks aside, relative -> its mode, with the
    write bits then cleared on each. A symlink is skipped because Linux has no
    mode of its own for a link: a chmod through it would freeze its target."""
    modes = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in sorted(filenames + dirnames):
            path = Path(dirpath) / name
            if path.is_symlink():
                continue
            rel = str(path.relative_to(root))
            modes[rel] = stat.S_IMODE(path.lstat().st_mode)
            path.chmod(modes[rel] & ~_WRITE_BITS)
    modes["."] = stat.S_IMODE(root.lstat().st_mode)
    root.chmod(modes["."] & ~_WRITE_BITS)
    return modes


def _thaw(root: Path) -> None:
    """Gives every directory under *root* its owner's write bit back, so the
    tree can be removed."""
    if not root.is_dir() or root.is_symlink():
        return
    root.chmod(stat.S_IMODE(root.lstat().st_mode) | stat.S_IWUSR)
    for dirpath, dirnames, _filenames in os.walk(root):
        for name in dirnames:
            path = Path(dirpath) / name
            if not path.is_symlink():
                path.chmod(stat.S_IMODE(path.lstat().st_mode) | stat.S_IWUSR)


class RenderCache:
    """One render per answer set and day under *root*, made by *renderer*
    (called as `renderer(dest, answers)`), each handed out only as a copy."""

    def __init__(self, root: Path, renderer: Renderer) -> None:
        self._root = Path(root)
        self._renderer = renderer
        self._made: Dict[str, Path] = {}
        self._modes: Dict[str, Dict[str, int]] = {}

    def renders(self) -> List[Path]:
        """The shared renders made so far, sorted; read-only."""
        return sorted(self._made.values())

    def _render(self, answers: Mapping[str, Any], day: datetime.date) -> str:
        key = answer_key(answers, day)
        if key in self._made:
            return key
        dest = self._root / hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        self._root.mkdir(parents=True, exist_ok=True)
        try:
            self._renderer(dest, dict(answers))
        except BaseException:
            # A refused answer set is the test's subject, not a cache entry:
            # the next request asks the renderer again.
            shutil.rmtree(str(dest), ignore_errors=True)
            raise
        if not dest.is_dir() or not any(dest.iterdir()):
            shutil.rmtree(str(dest), ignore_errors=True)
            raise RenderError(
                "the renderer wrote nothing for answers %r on %s"
                % (dict(answers), day.isoformat())
            )
        self._modes[key] = _frozen_modes(dest)
        self._made[key] = dest
        return key

    def copy_into(
        self, dest: Path, answers: Mapping[str, Any], day: datetime.date
    ) -> Path:
        """Copy the render of *answers* on *day* to *dest*, rendering it first
        if this session has not, and return *dest*. The copy carries the
        render's bytes, its symlinks as links and each path's mode as the
        renderer left it, so it is writable wherever the render was before it
        was frozen. Raises FileExistsError when *dest* exists."""
        dest = Path(dest)
        if os.path.lexists(str(dest)):
            raise FileExistsError("refusing to copy a render over %s" % dest)
        key = self._render(answers, day)
        shutil.copytree(str(self._made[key]), str(dest), symlinks=True)
        # copytree copied the frozen modes; the copy gets the renderer's.
        for rel, mode in sorted(self._modes[key].items()):
            (dest / rel).chmod(mode)
        return dest

    def close(self) -> None:
        """Remove every render; a second call does nothing."""
        if os.path.lexists(str(self._root)):
            _thaw(self._root)
            shutil.rmtree(str(self._root))
        self._made.clear()
        self._modes.clear()
