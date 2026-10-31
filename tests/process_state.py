"""
title: Process state — whether a pid a test started still runs
summary: alive(pid) is the one answer a test gives to "is this process still running" after it stopped one. A pid signal 0 cannot find is gone; a zombie (Z) or a dying task (X) is gone, since it runs nothing and who reaps it (init, or a subreaper) is not the test's to decide; a pid reaped after signal 0 found it, before /proc/<pid>/stat is opened or while it is read, is gone; any other failure to read /proc counts as running, so a test that cannot tell fails rather than passes. tests/unit/test_process_state.py holds each case.
"""

import os

# The /proc/<pid>/stat states of a task that runs nothing more.
_GONE_STATES = ("Z", "X")


def alive(pid):
    """True while *pid* runs: it exists, and /proc does not show it a zombie
    or dying."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:
        with open("/proc/%d/stat" % pid, encoding="utf-8") as fh:
            stat = fh.read()
    except (FileNotFoundError, ProcessLookupError):
        # Reaped after signal 0 found it: before the open (a verify at load
        # average 9 hit this) or between the open and the read.
        return False
    except OSError:
        return True
    # The command name in parentheses may hold spaces or `)`; the state is
    # the first field after the last `)`.
    return stat.rsplit(")", 1)[1].split()[0] not in _GONE_STATES
