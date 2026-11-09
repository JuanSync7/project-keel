"""
title: Changed-tests cache — shared checkout confinement and git refusals
summary: Resolves tests.cache_dir through config_loader and refuses absolute, escaping, tracked or unignored paths. Shared by check_structure and changed_tests; stdlib-only and Python 3.6-safe for the evidence writer. Raises without ending a process and writes nothing.
"""

# The evidence writer reaches this module through check_structure even under
# an interpreter older than the project's floor; keep pytest in its caller.
import ntpath
import os

import config_loader
import git_tree

__all__ = ["cache_path"]

_CACHE_KEY = ("tests", "cache_dir")


def cache_path(root, manifest=None):
    """Return an absolute, confined, git-ignored tests.cache_dir or raise.

    A configured name is relative to the checkout, never the caller's cwd.
    Git must answer: an unavailable repository cannot prove a local write.
    """
    if manifest is None:
        manifest = config_loader.read(root)
    path = config_loader.resolve(
        manifest, config_loader.rows(_CACHE_KEY), config_loader.CONFIG_FILE
    )[_CACHE_KEY]
    if (
        ntpath.isabs(path)
        or ntpath.splitdrive(path)[0]
        or "\\" in path
        or any(part in ("", ".", "..") for part in path.split("/"))
    ):
        raise ValueError(
            "tests.cache_dir must be a relative checkout path without empty, . or .. parts"
        )
    resolved = git_tree.confined_path(root, path)
    # Test both names: an internal symlink must not conceal tracked data.
    real_relative = os.path.relpath(resolved, os.path.realpath(root)).replace(
        os.sep, "/"
    )
    names = {path, real_relative}
    if git_tree.tracked(root, names):
        raise ValueError(
            "tests.cache_dir is tracked by git; choose an ignored directory"
        )
    if not all(git_tree.is_ignored(root, name + "/") for name in names):
        raise ValueError(
            "tests.cache_dir must be git-ignored; add it to .gitignore and its copier twin"
        )
    if any(
        candidate.startswith(name + "/")
        for candidate in git_tree.candidate_files(root)
        for name in names
    ):
        raise ValueError(
            "tests.cache_dir contains files git tracks; choose an ignored directory"
        )
    return resolved
