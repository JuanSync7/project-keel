#!/usr/bin/env python3
"""
title: Project interpreter — run a script with the current or main checkout's venv
summary: Selects this tree's .venv/bin/python, then the main checkout's through git's common directory. Missing venvs, bare or unusual fallback layouts and a config/project.json an update left conflicted refuse with USAGE, and any other refused manifest with CONFIG; exec preserves arguments, stdin and the script's status under the child environment allowlist. Stdlib-only and Python 3.6-safe.
effect: read-only
"""

# The hook runs before any venv exists, on the host python3 (possibly 3.6.8).
# ruff: noqa: FA100

import os
import subprocess
import sys
from typing import List, Optional

# Running by path puts scripts/ on sys.path; mypy's configured path is src/ only.
import config_loader  # type: ignore[import-not-found]
from child_env import ChildEnvError, build_child_env  # type: ignore[import-not-found]
from exit_codes import ExitCode, finish, report  # type: ignore[import-not-found]

__all__ = ["main"]

_USAGE = "usage: python3 scripts/project_python.py SCRIPT [ARG ...]"
_BUILD = "build .venv in the current work tree or main checkout, then run again"


def _git(*args: str) -> str:
    """Read repository metadata from Git in the session's current directory."""
    return subprocess.check_output(
        ["git"] + list(args),
        env=build_child_env(),
        stderr=subprocess.PIPE,
        universal_newlines=True,
    ).strip()


def _executable(path: str) -> bool:
    """Return whether a path is an executable regular file."""
    return os.path.isfile(path) and os.access(path, os.X_OK)


def main(argv: Optional[List[str]] = None) -> ExitCode:
    """Replace this process with the selected interpreter, or report a refusal."""
    args = sys.argv[1:] if argv is None else list(argv)
    if not args:
        return report(
            ExitCode.USAGE,
            "project_python: no script (USAGE)",
            "command line",
            _USAGE,
        )
    if args == ["--help"]:
        print(_USAGE)
        return ExitCode.SUCCESS

    try:
        try:
            tree = _git("rev-parse", "--show-toplevel")
        except (OSError, subprocess.CalledProcessError):
            return report(
                ExitCode.USAGE,
                "project_python: no work tree (USAGE)",
                os.getcwd(),
                "run from a non-bare project work tree",
            )
        local_python = os.path.join(tree, ".venv", "bin", "python")
        interpreter = local_python
        if not _executable(local_python):
            common = os.path.realpath(_git("rev-parse", "--git-common-dir"))
            # Only the conventional non-bare .git layout identifies a checkout.
            # Bare or unusual common directories have no safe parent to guess.
            if os.path.basename(common) != ".git":
                return report(
                    ExitCode.USAGE,
                    "project_python: unusual git common directory (USAGE)",
                    common,
                    "build .venv in the current work tree; the main checkout "
                    "cannot be inferred safely",
                )
            bare = _git("--git-dir=" + common, "rev-parse", "--is-bare-repository")
            if bare != "false":
                return report(
                    ExitCode.USAGE,
                    "project_python: bare common directory (USAGE)",
                    common,
                    "build .venv in the current work tree; a bare repository "
                    "has no main checkout",
                )
            interpreter = os.path.join(
                os.path.dirname(common), ".venv", "bin", "python"
            )
            if not _executable(interpreter):
                return report(
                    ExitCode.USAGE,
                    "project_python: no project venv (USAGE)",
                    "%s and %s" % (local_python, interpreter),
                    _BUILD,
                )
        # exec retains stdin and the program's own status without a wrapper hop.
        os.execve(interpreter, [interpreter] + args, env=build_child_env())
    except ChildEnvError as exc:
        return report(
            ExitCode.USAGE
            if config_loader.is_conflict(exc.__cause__ or exc)
            else ExitCode.CONFIG,
            "project_python: child environment refused",
            str(exc),
            "repair config/project.json, resolving any hunk, then run again",
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        return report(
            ExitCode.USAGE,
            "project_python: cannot locate or start the project interpreter (USAGE)",
            str(exc),
            _BUILD,
        )
    # The exit gate requires an explicit ending; a successful exec never returns.
    return ExitCode.SUCCESS  # type: ignore[unreachable]


if __name__ == "__main__":
    finish(main())
