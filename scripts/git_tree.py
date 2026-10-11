"""
title: git_tree — what git lists, and a digest of it
kind: script
layer: n/a
summary: The one definition of "what git lists" in a work tree. tree_snapshot maps every path `git status` reports (modified, staged, deleted, untracked; never an ignored one) to its two-letter porcelain status joined to a digest of its content, and raises NoGitError when the directory is not inside a git work tree or git cannot run; snapshot_digest reduces a snapshot to one `sha256:` value over its canonical JSON. is_ignored answers whether git would list a path that may not exist yet, and head_commit names HEAD's sha or None when there is no commit. through_symlink names the project-relative paths that reach their file through a symlink, which needs no git and is what a writer asks before it writes or deletes at a path read from config. git runs with the allowlisted environment from scripts/child_env.py and with the developer's global excludes file switched off. Stdlib and 3.6-safe, so scripts/gate_evidence.py can import it under the old interpreter. It decides nothing about what runs or passes (scripts/run_make_target.py and scripts/gate_evidence.py do), and it writes nothing.
"""

# NB: stdlib only, no `from __future__ import annotations`, no f-strings, no walrus,
# no `list[str]` or `X | None` annotations. scripts/gate_evidence.py imports this
# module, and a `make verify` whose PY is older than requires-python must still run
# that writer so the record it leaves is red rather than an earlier green one
# (tests/integration/test_gate_scope.py `_old_python_safe`).
# subprocess.run and child_env.build_child_env are looked up on their modules at
# call time on purpose: tests/unit/scripts/test_run_make_target.py patches both
# through run_make_target's module attributes, which are these same modules.

import hashlib
import json
import os
import subprocess

import child_env

__all__ = [
    "NoGitError",
    "head_commit",
    "is_ignored",
    "snapshot_digest",
    "through_symlink",
    "tree_snapshot",
]


class NoGitError(Exception):
    """The directory is not inside a git work tree, so no before/after
    comparison of what git lists is possible and a read-only claim is unproven."""


def _run(root, argv):
    # The developer's global excludes file is ignored ON PURPOSE: a stray file a
    # personal ignore hides is still a change this machine's checkout would carry.
    try:
        return subprocess.run(  # noqa: S603 — argv list, never a shell string
            ["git", "-c", "core.excludesFile=" + os.devnull] + list(argv),
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=child_env.build_child_env(),
        )
    except OSError as exc:
        raise NoGitError("git is not runnable here (%s)" % exc) from exc


def _failed(proc):
    return NoGitError(
        proc.stderr.decode("utf-8", "replace").strip()
        or "git exited %d" % proc.returncode
    )


def _git(root, *argv):
    proc = _run(root, argv)
    if proc.returncode != 0:
        raise _failed(proc)
    return proc.stdout


def _digest(path):
    if os.path.islink(path):
        return "link:" + os.readlink(path)
    if os.path.isfile(path):
        sha = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 16), b""):
                sha.update(chunk)
        return "sha:" + sha.hexdigest()
    if os.path.isdir(path):
        return "dir"  # a nested repository git lists as one entry
    return "absent"


def tree_snapshot(root):
    """{repo-relative path: state} for every path `git status` lists under root
    (modified, staged, deleted, untracked — never ignored). The state is the
    two-letter porcelain status joined to the sha256 of the content, so a second
    edit to an already-dirty file and a change to the index alone both show.

    Raises NoGitError when root is not inside a git work tree."""
    top = _git(root, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    raw = _git(top, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    fields = raw.decode("utf-8", "surrogateescape").split("\0")
    codes = {}
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if len(entry) < 4:
            continue
        code, path = entry[:2], entry[3:]
        codes[path] = code
        # A rename/copy carries its source as the next field, in either column:
        # ` R` is a worktree rename (an intent-to-add file), `R ` a staged one.
        if "R" in code or "C" in code:
            codes[fields[i]] = code + "<"
            i += 1
    return {
        p: "%s|%s" % (codes[p], _digest(os.path.join(top, p))) for p in sorted(codes)
    }


def snapshot_digest(snap):
    """`sha256:<hex>` over the canonical JSON of a tree_snapshot result: one value
    that names the listed content, equal for equal snapshots and for a clean tree."""
    text = json.dumps(snap, sort_keys=True, separators=(",", ":"))
    return (
        "sha256:" + hashlib.sha256(text.encode("utf-8", "surrogateescape")).hexdigest()
    )


def is_ignored(root, rel):
    """True when git ignores the repo-relative path *rel* (which need not exist
    yet), False when it would list it. A tracked path is never ignored. Raises
    NoGitError when root is not inside a git work tree."""
    proc = _run(root, ("check-ignore", "-q", "--", rel))
    # check-ignore answers with its exit code: 0 ignored, 1 not; anything else
    # is git failing, which must not read as "not ignored".
    if proc.returncode in (0, 1):
        return proc.returncode == 0
    raise _failed(proc)


def head_commit(root):
    """The full sha HEAD names, or None when there is none: no commit yet, or
    no work tree git can read."""
    try:
        out = _git(root, "rev-parse", "--verify", "-q", "HEAD^{commit}")
    except NoGitError:
        return None
    return out.decode("ascii", "replace").strip() or None


def through_symlink(root, paths):
    """The project-relative POSIX *paths* that do not resolve to themselves
    under *root*: some component, or the path itself, is a symlink, wherever it
    points. A path that does not exist yet resolves to itself, and *root* itself
    may be reached through a link. Needs no git."""
    real_root = os.path.realpath(root)
    return [
        p
        for p in paths
        if os.path.realpath(os.path.join(root, p))
        != os.path.join(
            real_root, *[part for part in p.split("/") if part not in ("", ".")]
        )
    ]
