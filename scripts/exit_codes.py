"""
title: exit_codes — the closed list of exit codes and the one place a process ends
kind: script
layer: n/a
summary: ExitCode is the closed list of statuses a keel process exits with, each member carrying its value, what it means and what to do about it; scripts/exit_code_table.py writes the list into the limits guide. report writes the one stderr line a failure ends on, `<what failed>: <on which input>; <what to do next>`, refuses a blank part, and returns the member so `main` can return it. passthrough marks a wrapped tool's own status, so a code outside the list is visible as one. finish is the entry line `finish(main())` and the only call to sys.exit in the tree: it exits with a member or a passed-through status and refuses anything else. fail is finish over report, for code that is not `main`. Import it by its bare name with scripts/ on sys.path, never as `scripts.exit_codes`: two import names would be two ExitCode classes. Stdlib-only and 3.6-safe, because the pre-commit hooks and copier's own interpreter run scripts that import it. It is not a logger (a progress or per-finding line is the caller's own write) and it reads no config. tests/integration/test_exit_gate.py fails an exit written anywhere else.
effect: read-only
"""

# NB: stdlib only, no `from __future__ import annotations`, no f-strings, no
# walrus, no dataclass: `python3` on a hook host may be 3.6
# (tests/integration/test_gate_scope.py `_old_python_safe`).

import enum
import sys

__all__ = [
    "BlankMessagePart",
    "ExitCode",
    "PassedThrough",
    "fail",
    "finish",
    "passthrough",
    "report",
]

# One line per failure, so a caller that reads stderr can split it back.
_LINE = "%s: %s; %s\n"
# The shell's spelling of "killed by signal N".
_SIGNAL_BASE = 128


@enum.unique
class ExitCode(enum.IntEnum):
    """Every status a keel process chooses for itself. A member is its int
    value and carries `meaning` and `action`, the two cells of its row in the
    generated exit-code table."""

    def __new__(cls, value, meaning, action):
        member = int.__new__(cls, value)
        member._value_ = value
        member.meaning = meaning
        member.action = action
        return member

    SUCCESS = (
        0,
        "it ran and found nothing wrong, or it skipped and said why",
        "nothing",
    )
    FAILURE = (
        1,
        "it ran and the answer is no: a check found something, or the work "
        "did not succeed",
        "read the last stderr line, fix what it names, and run it again",
    )
    USAGE = (
        2,
        "it refused before judging: wrong usage, bad config, or an input it "
        "could not read",
        "correct the call or the input the last stderr line names, and run it again",
    )
    # 10, 11 and 12 are numbers no tool in a gate's path already uses: the shell
    # owns 0 and 1, argparse and make 2, pytest 1 to 5, sysexits.h 64 to 78,
    # timeout and the shell 124 to 127, a signal 128 and up, and 255 is an
    # out-of-range status. A caller can then act on the number alone.
    RED_RECORD = (
        10,
        "every step it ran passed, and the record it wrote of the run says fail",
        "read `reasons` in the record the last stderr line names, fix what they "
        "name, and run it again",
    )
    BACKEND_ABSENT = (
        11,
        "the backend it was told to use did not answer, so nothing was judged",
        "start or configure the backend the last stderr line names, and run it again",
    )
    NO_CAPACITY = (
        12,
        "nothing ran: the farm did not start the job within the wait bound and "
        "this host had no spare compute",
        "run it again later, or raise config/project.json launcher.farm.wait_seconds",
    )
    INTERRUPTED = (
        130,
        "it was interrupted before it finished",
        "run it again; what it had written so far is not a result",
    )


class BlankMessagePart(ValueError):
    """A failure message is missing one of its three parts."""


class PassedThrough(int):
    """A wrapped tool's own exit status, which need not be an ExitCode value."""

    __slots__ = ()


def _require_parts(what, on, next_step):
    for name, part in (("what", what), ("on", on), ("next_step", next_step)):
        if not isinstance(part, str) or not part.strip():
            raise BlankMessagePart(
                "the `%s` part of a failure message is %r: say what failed, on "
                "which input, and what to do next" % (name, part)
            )


def report(code, what, on, next_step, stream=None):
    """Write `<what>: <on>; <next_step>` as one line to *stream* (stderr when
    None) and return *code*, for `main` to return. *code* is a member other
    than SUCCESS: a success has nothing to report."""
    if not isinstance(code, ExitCode):
        raise TypeError("report takes an ExitCode member, not %r" % (code,))
    if code is ExitCode.SUCCESS:
        raise ValueError("report is for a failure; return ExitCode.SUCCESS itself")
    _require_parts(what, on, next_step)
    (sys.stderr if stream is None else stream).write(_LINE % (what, on, next_step))
    return code


def passthrough(returncode):
    """The exit status of a tool this process wrapped, marked as not chosen
    here. A child killed by signal N reports -N; the shell's spelling is 128+N,
    and a negative status would wrap to a value that hides the signal."""
    if type(returncode) is not int:
        raise TypeError(
            "passthrough takes a child's int exit status, not %r" % (returncode,)
        )
    if returncode < 0:
        return PassedThrough(_SIGNAL_BASE - returncode)
    return PassedThrough(returncode)


def finish(result):
    """End the process with *result*, what `main` returned: an ExitCode member
    or a passthrough status. Anything else is a `main` that chose a code outside
    the list, and ends as USAGE with a line saying so."""
    if not isinstance(result, (ExitCode, PassedThrough)):
        result = report(
            ExitCode.USAGE,
            "this process tried to exit with a status outside the exit-code list",
            repr(result),
            "return an ExitCode member, or passthrough(<a wrapped tool's status>), "
            "from main (scripts/exit_codes.py)",
        )
    sys.exit(int(result))


def fail(code, what, on, next_step):
    """Write the failure line and end the process: report, then finish. For
    code that is not `main` and has no caller to return a member to."""
    finish(report(code, what, on, next_step))
