#!/usr/bin/env python3
"""
title: child_exec — re-run a shell script under the child environment allowlist
kind: script
layer: n/a
effect: read-only
summary: The shell side of scripts/child_env.py. A shell script's first command is `REEXEC_LINE`, which hands the script and its arguments to this module unless `MARKER` already holds the script's own pid; this module then replaces itself with the script, under the environment `build_child_env` builds (the same allowlist and credential refusals a Python spawn gets) plus `MARKER` set to its own pid, which exec keeps. It starts the file the shell ran, by its path and never by a PATH search (a name with no slash is the file in the current directory), under the interpreter its `#!` line names, read as Linux reads it (the interpreter and at most one argument), or /bin/sh when it has none, so the execute bit does not matter; a script handed to a different shell than its `#!` line names (`bash x.sh` of a `#!/bin/sh` file) re-runs under the one the line names. So the script's body runs once, under the allowlist, and every command it starts inherits that environment; a marker a parent exported matches no new pid, so it skips the re-run only when that parent exec'd in place, and a nested script re-runs itself too. No program is USAGE; an allowlist that cannot be built is CONFIG naming the program, never a run under the parent's environment; a file that cannot be read (absent, a directory) or whose interpreter cannot be started is USAGE naming it. It runs under the host `python3` the line names, so it is stdlib-only and 3.6-safe. scripts/check_structure.py check_X holds every shell script to the line. Defence-in-depth, not a sandbox (docs/adr/keel/K-0012-child-process-environment-allowlist.md).
"""

# NB: stdlib only, no f-strings, no annotations: REEXEC_LINE runs it with the
# host's bare `python3`, which may be 3.6 (as child_env.py's own note says).

import os
import sys

import child_env
import config_loader
from exit_codes import ExitCode, finish, report

__all__ = ["MARKER", "REEXEC_LINE", "main", "start_argv"]

# The variable that tells a re-run script it is already under the allowlist.
MARKER = "KEEL_CHILD_ENV"
# The one line check_X requires as a shell script's first command. The path may
# be any spelling that ends in /child_exec.py, as the exit gate allows for
# exit_codes.sh.
REEXEC_LINE = (
    '[ "${%s-}" = "$$" ] || exec python3 "$(dirname "$0")/child_exec.py" "$0" "$@"'
    % MARKER
)
# A file with no `#!` line is run by sh, as a shell's own exec fallback does.
_NO_SHEBANG = "/bin/sh"
# Linux reads at most this much of the `#!` line (BINPRM_BUF_SIZE, 5.1 and on).
_SHEBANG_BYTES = 256


def start_argv(path):
    """The argv that starts the file at `path` as the kernel would, without
    the execute bit: its `#!` interpreter, that line's one argument if any,
    then the path. Raises OSError when the file cannot be read."""
    if "/" not in path:
        # The shell ran a slashless $0 from the current directory; a PATH
        # search here could start a different file of the same name.
        path = "./" + path
    with open(path, "rb") as handle:
        first = handle.read(_SHEBANG_BYTES).split(b"\n", 1)[0]
    words = []
    if first.startswith(b"#!"):
        line = os.fsdecode(first[2:]).strip()
        if line:
            words = line.split(None, 1)
    return (words or [_NO_SHEBANG]) + [path]


def main(argv=None):
    """Replace this process with argv[0] under the allowlist; return only on a
    refusal."""
    args = sys.argv[1:] if argv is None else list(argv)
    if not args:
        return report(
            ExitCode.USAGE,
            "child_exec: no program to run",
            "the command line",
            "open the shell script with the line `%s`" % REEXEC_LINE,
        )
    program = args[0]
    try:
        start = start_argv(program)
    except OSError as exc:
        return report(
            ExitCode.USAGE,
            "child_exec: the script cannot be read (%s)" % exc.strerror,
            program,
            "run it by a path that names the file, with a `#!` line naming an "
            "interpreter that exists",
        )
    try:
        env = child_env.build_child_env(extra={MARKER: str(os.getpid())})
    except child_env.ChildEnvError as exc:
        return report(
            ExitCode.USAGE
            if config_loader.is_conflict(exc.__cause__ or exc)
            else ExitCode.CONFIG,
            "child_exec: the allowlisted environment cannot be built (%s)" % exc,
            program,
            "correct config/project.json child_env as the message says, then run "
            "the script again",
        )
    try:
        os.execve(start[0], start + args[1:], env)
    except OSError as exc:
        return report(
            ExitCode.USAGE,
            "child_exec: the interpreter %s cannot be started (%s)"
            % (start[0], exc.strerror),
            program,
            "name an interpreter that exists in the script's `#!` line",
        )
    return ExitCode.SUCCESS  # unreachable: a successful exec never returns


if __name__ == "__main__":
    finish(main())
