#!/usr/bin/env python3
"""
title: child_exec — re-run a shell script under the child environment allowlist
kind: script
layer: n/a
effect: read-only
summary: The shell side of scripts/child_env.py. A shell script's first command is `REEXEC_LINE`, which hands the script and its arguments to this module unless `MARKER` already holds the script's own pid; this module then replaces itself with the script, under the environment `build_child_env` builds (the same allowlist and credential refusals a Python spawn gets) plus `MARKER` set to its own pid, which exec keeps. So the script's body runs once, under the allowlist, and every command it starts inherits that environment; a marker a parent exported matches no new pid, so it never skips the re-run, and a nested script re-runs itself too. No program is USAGE; an allowlist that cannot be built is CONFIG naming the program, never a run under the parent's environment; a program that cannot be started (not executable, or absent) is USAGE naming it. It runs under the host `python3` the line names, so it is stdlib-only and 3.6-safe. scripts/check_structure.py check_X holds every shell script to the line. Defence-in-depth, not a sandbox (docs/adr/keel/K-0012-child-process-environment-allowlist.md).
"""

# NB: stdlib only, no f-strings, no annotations: REEXEC_LINE runs it with the
# host's bare `python3`, which may be 3.6 (as child_env.py's own note says).

import os
import sys

import child_env
from exit_codes import ExitCode, finish, report

__all__ = ["MARKER", "REEXEC_LINE", "main"]

# The variable that tells a re-run script it is already under the allowlist.
MARKER = "KEEL_CHILD_ENV"
# The one line check_X requires as a shell script's first command. The path may
# be any spelling that ends in /child_exec.py, as the exit gate allows for
# exit_codes.sh.
REEXEC_LINE = (
    '[ "${%s-}" = "$$" ] || exec python3 "$(dirname "$0")/child_exec.py" "$0" "$@"'
    % MARKER
)


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
        env = child_env.build_child_env(extra={MARKER: str(os.getpid())})
    except child_env.ChildEnvError as exc:
        return report(
            ExitCode.CONFIG,
            "child_exec: the allowlisted environment cannot be built (%s)" % exc,
            program,
            "correct config/project.json child_env as the message says, then run "
            "the script again",
        )
    try:
        os.execvpe(program, args, env)
    except OSError as exc:
        return report(
            ExitCode.USAGE,
            "child_exec: the script cannot be started (%s)" % exc.strerror,
            program,
            "make it executable (chmod +x) and run it by its path",
        )
    return ExitCode.SUCCESS  # unreachable: a successful exec never returns


if __name__ == "__main__":
    finish(main())
