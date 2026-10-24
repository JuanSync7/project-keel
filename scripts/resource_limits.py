"""
title: resource_limits — a bounded child process, and a server's memory cap and stop
kind: script
layer: n/a
summary: The one supervisor for a child process, which scripts/run_make_target.py and `run_bounded` both run on. `start_child` starts a program through the child-process allowlist (scripts/child_env.py build_child_env, called inside the spawn so check_X sees it) in a session of its own, and on POSIX starts a watcher beside it: a stdlib one-liner holding a pipe only this process writes to, so when this process dies without unwinding (SIGKILL included) the pipe reaches end of file and the watcher sends SIGKILL to every process group in the child's session. `supervised` holds one run: a SIGCHLD the caller ignores is set to its default for the run and put back afterwards (ChildSignalIgnored off the main thread, where Python cannot change it, before anything starts); a SIGTERM or SIGHUP the caller neither ignores nor gives to a ShutdownOwner ends the child's session and then this process as it would have ended; a stop signal that lands while the child is being started is deferred until its pid is known, then acts. `ChildSession` holds the child as a zombie (os.waitid WNOWAIT) until its session is ended, so no signal goes to an id that could pass to another process, lists the session's members through /proc (`session_members`), and ends them SIGTERM-then-SIGKILL after its grace; a child another waiter reaped is ChildReaped. `PipeReader` reads a pipe in a thread up to an optional byte cap, and names the processes still holding it open (`pipe_holders`). `run_bounded` feeds a program the caller's stdin text and returns a subprocess.CompletedProcess with its status and its output decoded as UTF-8. It waits on the child's own exit; what the child left running in its session after a short settle is sent SIGKILL and named in a log warning by pid and program name, never by its arguments; its pipes then get one shared drain window of _DRAIN_S (2) seconds, a module constant rather than a config key, since it bounds only how long output a stray process still writes is waited for, so the call returns within its limit plus that window. A process outside the session that still holds a pipe after the window is named in a log warning the same way and is not signalled; what it writes after the window is not read, every pipe is closed, every thread the call started has ended, and the child's own status and output are returned. A child still running when the caller's time limit passes has its session sent SIGKILL and is refused as ChildTimedOut; a child that writes more than the caller's byte cap to either stream has its session ended the same way and is refused as ChildOutputTooLarge. Both are RuntimeError subclasses whose message names the program by its file name only (never its arguments, which may carry a prompt), the limit, and the config key the caller says sets it. A limit below or equal to zero, a time limit past threading.TIMEOUT_MAX (where a thread wait overflows), and a byte cap that is no whole number or past sys.maxsize (the longest bytes object) are a ValueError before anything starts; an exception while the child runs (KeyboardInterrupt included) ends its session before it propagates; a program that does not exist is the FileNotFoundError the spawn raises. Off POSIX there is no session, process group or watcher, so only the child itself is ended, and a pipe a stray process holds is left open with its thread until the process ends. run_bounded reads no configuration of its own. For an agent's tool child and the MCP action server's doer, tool_limits reads config/project.json `agents.tool_timeout_seconds` and `agents.tool_max_output_bytes` through scripts/config_loader.py, and refuses as config_loader.WrongValue a time limit below `make_targets.gate_timeout_seconds` plus twice `make_targets.gate_stop_grace_seconds` plus `agents.tool_gate_margin_seconds`, since a tool child can be the gate runner, whose timed-out run waits its grace once for make's session and once more for make's output, and a SIGKILL to it first would cut make's SIGTERM grace short, lose its structured result and leave an applied edit not rolled back, and refuses a margin that puts that sum past `agents.tool_timeout_seconds`'s own ceiling, threading.TIMEOUT_MAX, naming the margin and the most it can be; run_tool is run_bounded under those two limits, with this checkout's allowlisted environment and no credential, its refusals naming the key. For a server entry point, serve_limits reads config/project.json `transports.serve` (memory_cap_mb, shutdown_grace_seconds) through scripts/config_loader.py; cap_memory sets RLIMIT_AS to that many megabytes and returns a line naming what it set and what it does not cover (a file in a memory-backed directory, the processes the server starts, resident memory), or that it set nothing (null, or no setrlimit on this platform); shutdown_owner owns SIGTERM and SIGINT while a server runs: the first writes `<name>: stopping on <signal>` to stderr and calls the server's stop, or raises ShutdownRequested, a BaseException, where the server waits idle; once the server returns after a stop signal, every supervised child still running has its session sent SIGKILL, so a request thread waiting on one cannot hold the exit for that child's whole limit; and a second signal sends that SIGKILL at once, then ends the process by that signal's default action, so its exit status names the signal (128 plus its number in a shell). A child that dies in the instant between its own spawn and its watcher's, a process a child moved to a session of its own with setsid, and a process that inherited the watcher's pipe through a fork with no exec are not reached. It writes no file.
"""

# NB: stdlib only, no `from __future__ import annotations`, no f-strings, no walrus,
# no `list[str]` or `X | None` annotations: this module sits in the bottom import
# layer (config/project.json import_layers.order), which
# tests/integration/test_gate_scope.py holds to the oldest interpreter a hook runs.

import contextlib
import logging
import os
import select
import signal
import subprocess
import sys
import threading
import time
from typing import (
    IO,
    Any,
    Callable,
    Dict,
    Iterator,
    List,
    NoReturn,
    Optional,
    Sequence,
    Tuple,
)

from scripts import config_loader
from scripts.child_env import build_child_env

try:
    import resource

    _HAS_RLIMIT = True
except ImportError:  # not POSIX: cap_memory says the cap is not set
    _HAS_RLIMIT = False

__all__ = [
    "ChildOutputTooLarge",
    "ChildReaped",
    "ChildSession",
    "ChildSignalIgnored",
    "ChildTimedOut",
    "PipeReader",
    "ShutdownOwner",
    "ShutdownRequested",
    "cap_memory",
    "pipe_holders",
    "run_bounded",
    "run_tool",
    "serve_limits",
    "session_members",
    "shutdown_owner",
    "start_child",
    "supervised",
    "tool_limits",
]

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MEMORY_CAP = ("transports", "serve", "memory_cap_mb")
_GRACE = ("transports", "serve", "shutdown_grace_seconds")
_OWNED_SIGNALS = (signal.SIGTERM, signal.SIGINT)
_LOG = logging.getLogger(__name__)
_TOOL_TIMEOUT = ("agents", "tool_timeout_seconds")
_TOOL_OUTPUT = ("agents", "tool_max_output_bytes")
_GATE_TIMEOUT = ("make_targets", "gate_timeout_seconds")
_GATE_GRACE = ("make_targets", "gate_stop_grace_seconds")
_GATE_MARGIN = ("agents", "tool_gate_margin_seconds")

# Every child session still running, keyed by the child's pid, which is its
# session's and its first group's id: a server's stop ends them all, since a
# signal to the server never reaches a session of its own. A dict and no
# lock: a signal handler runs on the main thread between bytecodes, possibly
# while that thread holds any lock, and a dict's item set, pop and list()
# each run whole under the GIL.
_RUNNING = {}  # type: Dict[int, ChildSession]

# One read's size: large enough that a child writing megabytes costs few
# wake-ups, small enough that a cap is overshot by at most this much in memory.
_CHUNK = 65536

# How long run_bounded's pipes get, all together, once the session has
# emptied: a child's own output is in the pipe by then and is read in far
# less, so a longer wait means a process outside the session holds a pipe,
# and that process is not the caller's to wait for. A call so returns within
# its limit plus this window and the settle. A constant, not a config key: it
# bounds a read of output already written, which no project has a reason to
# tune, and a caller with a policy of its own (the make runner's stop grace)
# passes its own wait to PipeReader.finish.
_DRAIN_S = 2.0

# How often a wait looks again: for a pipe thread, at its stop flag, so the
# call can end a thread whose pipe a stray process holds and close the pipe;
# for an exit wait, at the child's status. It sets how soon a change is seen,
# never how long anything gets.
_POLL_S = 0.05

# How long members still in a child's session after it exits are re-read
# before they count as left behind: `(cmd &)` whose cmd is finishing as the
# child exits would otherwise be a leftover by a race. It bounds the wait on
# a clean run, and a real leftover is reported after it.
_SETTLE_S = 0.5

# select works on a pipe only on POSIX; elsewhere a pipe thread reads or writes
# blocking, cannot be stopped, and its pipe is left open for the process's end.
_SELECTABLE = os.name == "posix"

# Signals whose default action ends this process without unwinding its stack.
# The child runs in a session of its own, so the signal no longer reaches it
# with this process: a CI cancel, `timeout` and a batch scheduler's limit send
# SIGTERM, a closed terminal SIGHUP. SIGINT already unwinds (KeyboardInterrupt);
# SIGKILL cannot be caught, and the watcher below covers it.
_UNWINDLESS = tuple(
    getattr(signal, name) for name in ("SIGTERM", "SIGHUP") if hasattr(signal, name)
)

# The watcher: a second process per child session that blocks reading a pipe
# only this process holds the write end of. The runner ends it before a
# normal end, so end of file means the runner died without unwinding (SIGKILL,
# os._exit), and the watcher then sends SIGKILL to the child's group and to
# every other group listed in its session. 3.6-safe and stdlib-only, as it
# runs under this interpreter with -I -S.
_WATCHER = r"""
import os, signal, sys
sid = int(sys.argv[1])
try:
    told = os.read(0, 1)
except OSError:
    told = b""
if told:
    sys.exit(0)
groups = set([sid])
try:
    names = os.listdir("/proc")
except OSError:
    names = []
for name in names:
    if not name.isdigit():
        continue
    try:
        with open("/proc/%s/stat" % name) as fh:
            fields = fh.read().rsplit(")", 1)[1].split()
        if int(fields[3]) == sid:
            groups.add(int(fields[2]))
    except (OSError, IndexError, ValueError):
        continue
for group in sorted(groups):
    try:
        os.killpg(group, signal.SIGKILL)
    except OSError:
        pass
"""


class ChildTimedOut(RuntimeError):
    """The child outlived its time limit."""


class ChildOutputTooLarge(RuntimeError):
    """The child wrote more than its byte cap to stdout or stderr."""


class ChildReaped(RuntimeError):
    """The child has exited, but something other than its runner reaped it,
    so its status is lost and its pid is free."""


class ChildSignalIgnored(RuntimeError):
    """The caller has SIGCHLD set to ignore and the runner is not on the main
    thread, so it cannot put SIGCHLD back to its default for the run."""


# --- a child's session ---------------------------------------------------------


def session_members(sid: int) -> Optional[List[Tuple[int, int, str]]]:
    """(pid, process group, command) of each process in session *sid* that
    still runs, read from /proc (Linux), or None on a host with no /proc. The
    child leads its session and its group, so *sid* is its pid; a group never
    spans sessions, so this holds every member of the child's group and every
    process that moved to a group of its own and stayed in the session (GNU
    `timeout` does, unless given --foreground). A zombie runs nothing, so it is
    not a member: its parent reaps it in its own time, and the runner never
    waits for that. A process that ends while it is read is skipped."""
    try:
        names = os.listdir("/proc")
    except OSError:
        return None
    members = []
    for name in sorted(names, key=lambda n: (len(n), n)):
        if not name.isdigit():
            continue
        try:
            with open("/proc/%s/stat" % name) as fh:
                # The command name in parentheses may hold spaces or `)`, so
                # the fields are counted after the last `)`: state, ppid,
                # pgrp, session (stat fields 3 to 6).
                fields = fh.read().rsplit(")", 1)[1].split()
            if int(fields[3]) != sid or fields[0] == "Z":
                continue
            pgrp = int(fields[2])
            command = _command(int(name))
        except (OSError, IndexError, ValueError):
            continue
        members.append((int(name), pgrp, command))
    return members


def _command(pid: int) -> str:
    """*pid*'s argv joined by spaces, `?` when it has none. Raises OSError
    once the process has gone."""
    with open("/proc/%d/cmdline" % pid, "rb") as fh:
        argv = fh.read().split(b"\0")
    return " ".join(a.decode("utf-8", "replace") for a in argv if a) or "?"


def pipe_holders(inode: int) -> Optional[List[Tuple[int, str]]]:
    """(pid, command) of each process other than this one with a descriptor
    open on the pipe whose inode is *inode*, read from /proc, or None on a
    host with no /proc. A process whose descriptors cannot be read (another
    user's) is not listed."""
    try:
        names = os.listdir("/proc")
    except OSError:
        return None
    target = "pipe:[%d]" % inode
    me = os.getpid()
    holders = []
    for name in sorted(names, key=lambda n: (len(n), n)):
        if not name.isdigit() or int(name) == me:
            continue
        try:
            links = [
                os.readlink("/proc/%s/fd/%s" % (name, fd))
                for fd in os.listdir("/proc/%s/fd" % name)
            ]
            if target in links:
                holders.append((int(name), _command(int(name))))
        except OSError:
            continue
    return holders


def _signal_group(pgid: int, sig: int) -> None:
    """Send *sig* to group *pgid*; a group that has emptied meanwhile is the
    outcome the caller wanted, so it is not an error. PermissionError is how
    some kernels answer for a group whose only member is a zombie leader."""
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(pgid, sig)


def _program(command: str) -> str:
    # The file name only: the arguments may carry a prompt or a credential.
    return os.path.basename(command.split(" ", 1)[0]) or "?"


class ChildSession:
    """One child's session: the child leads it and its first process group
    (start_child starts it with start_new_session), so its pid is both ids.
    The members are every process in that session, whatever group each is
    in, and nothing outside it is signalled. *grace* is how long end gives
    the members between SIGTERM and SIGKILL; 0 sends SIGKILL at once. Empty
    until start_child has started the child."""

    def __init__(self, grace: float) -> None:
        self.grace = grace
        self.proc = None  # type: Optional[subprocess.Popen[bytes]]
        self.watcher = None  # type: Optional[subprocess.Popen[bytes]]
        self.ending = False
        # Set while the child is being started: a stop signal then is kept in
        # deferred and replayed once proc is set (see _deferred_while_starting).
        self.starting = False
        self.deferred = []  # type: List[int]
        # Set once the child is found reaped by another waiter: its pid, the
        # session and group id, is then free.
        self.lost = False

    def exit_status(self) -> Optional[int]:
        """The child's status once it has exited (negative: the signal that
        ended it), else None. Where os.waitid exists the child is left
        unreaped (WNOWAIT): its zombie keeps holding its pid, which is the
        group id, so no new process can take that id while the runner still
        signals the group. Elsewhere it is reaped here, and held then stops
        every later signal. Raises ChildReaped when the child is no longer
        this process's to wait on: SIGCHLD set to ignore makes the kernel
        reap it as it exits, and another waiter in this process can reap it
        first."""
        assert self.proc is not None
        if not hasattr(os, "waitid"):
            return self.proc.poll()
        try:
            info = os.waitid(
                os.P_PID, self.proc.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT
            )
        except ChildProcessError:
            self.lost = True
            raise ChildReaped(
                "%s exited, but another waiter in this process reaped it, so its "
                "status is lost" % os.path.basename(self._argv()[0])
            ) from None
        if info is None or info.si_pid == 0:
            return None
        return info.si_status if info.si_code == os.CLD_EXITED else -info.si_status

    def _argv(self) -> List[str]:
        assert self.proc is not None
        args = self.proc.args
        if isinstance(args, (list, tuple)):
            return [str(a) for a in args]
        return [str(args)]

    def wait_exit(self, deadline: float) -> Optional[int]:
        """exit_status, polled until the child exits or the monotonic
        *deadline* passes (None then); ChildReaped as exit_status raises it."""
        status = self.exit_status()
        while status is None and time.monotonic() < deadline:
            time.sleep(_POLL_S)
            status = self.exit_status()
        return status

    def held(self) -> bool:
        """True while the child is unreaped. Its pid is the session and group
        id, and a pid that a process (a zombie included) still holds cannot
        be handed to a new one, so a signal to that id reaches only the
        child's own. Asked again before every signal: where os.waitid exists,
        a child that another waiter in this process has reaped is found here
        and marked lost, so the window left is the one between this check and
        the signal."""
        if self.proc is None or self.proc.returncode is not None:
            return False
        if hasattr(os, "waitid"):
            try:
                os.waitid(os.P_PID, self.proc.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
            except ChildProcessError:
                self.lost = True
                return False
        return True

    def _listed(self) -> Optional[List[Tuple[int, int, str]]]:
        assert self.proc is not None
        return session_members(self.proc.pid)

    def members(self) -> Tuple[bool, List[Tuple[int, str]]]:
        """(alive, the members it could list). Without /proc, alive comes from
        signal 0 to the child's group, which a zombie also answers, the list
        is empty, and a process that left the group is not seen."""
        assert self.proc is not None
        listed = self._listed()
        if listed is not None:
            return bool(listed), [(pid, command) for pid, _g, command in listed]
        if self.lost:
            # The child's pid is free, so signal 0 to it says nothing.
            return False, []
        self.proc.poll()
        if not hasattr(os, "killpg"):
            return self.proc.returncode is None, []
        try:
            os.killpg(self.proc.pid, 0)
        except ProcessLookupError:
            return False, []
        except PermissionError:
            return True, []
        return True, []

    def settled(self) -> Tuple[bool, List[Tuple[int, str]]]:
        """members(), re-read for up to _SETTLE_S while any remain, so a
        background job that is exiting as the child exits is not a leftover."""
        deadline = time.monotonic() + _SETTLE_S
        alive, listed = self.members()
        while alive and time.monotonic() < deadline:
            time.sleep(_POLL_S)
            alive, listed = self.members()
        return alive, listed

    def signal(self, sig: int) -> None:
        """*sig* to the child's group, then to each other group a session
        member was listed in. A group id stays taken while any member holds
        it, so a listed group cannot pass to an unrelated process unless all
        of it exits and the id is handed out again before the signal is sent.
        Nothing is sent once the child has been reaped, by its runner or
        another waiter (held is false): its id, the one the session listing
        is keyed on, is then free to pass to a process the runner did not
        start, so no listing by it can be trusted. Off POSIX there are no
        groups, and *sig* goes to the child alone."""
        if self.proc is None or not self.held():
            return
        if not hasattr(os, "killpg"):
            self.proc.send_signal(sig)
            return
        groups = {g for _p, g, _c in self._listed() or ()}
        _signal_group(self.proc.pid, sig)
        groups.discard(self.proc.pid)
        for pgid in sorted(groups):
            _signal_group(pgid, sig)

    def kill(self) -> None:
        """SIGKILL to every group in the session (see signal)."""
        if hasattr(signal, "SIGKILL"):
            self.signal(signal.SIGKILL)
        elif self.proc is not None and self.held():
            self.proc.kill()

    def end(self) -> None:
        """SIGTERM, up to the grace for the session to empty, then SIGKILL; a
        no-op once the child has been reaped (see held). The SIGKILL is in a
        finally, so a second interrupt that cuts the grace short still reaches
        every member. The child is left unreaped: release reaps it."""
        if not self.held():
            return
        self.ending = True
        try:
            if self.grace > 0:
                self.signal(signal.SIGTERM)
                deadline = time.monotonic() + self.grace
                while self.members()[0] and time.monotonic() < deadline:
                    time.sleep(_POLL_S)
        finally:
            if self.members()[0]:
                self.kill()

    def release(self) -> None:
        """Reap the child, after which no signal goes to its ids. Called last,
        once the session has been ended or found empty, so it does not block."""
        if self.proc is not None:
            self.proc.wait()


def _ready(fd: int, for_write: bool) -> bool:
    if not _SELECTABLE:
        return True
    if for_write:
        return bool(select.select([], [fd], [], _POLL_S)[1])
    return bool(select.select([fd], [], [], _POLL_S)[0])


class PipeReader:
    """Reads *stream* on a thread until end of file or until stopped, so the
    runner waits on the child's exit and not on its output: a background
    process that holds the pipe open no longer holds the run. With a *cap*,
    at most cap + one chunk is kept, and the first chunk past it sets over
    and calls *on_over* once; the pipe is still read to its end so the child
    is never blocked on it."""

    def __init__(
        self,
        stream: IO[bytes],
        cap: Optional[int] = None,
        on_over: Optional[Callable[[], None]] = None,
    ) -> None:
        self.stream = stream
        self._fd = stream.fileno()
        self._inode = os.fstat(self._fd).st_ino
        self._cap = cap
        self._on_over = on_over
        self._chunks = []  # type: List[bytes]
        self._size = 0
        self.over = False
        self._stop = threading.Event()
        self._eof = threading.Event()
        self._done = None  # type: Optional[bytes]
        # None while the pipe closed; else who still held it open.
        self.holders = None  # type: Optional[List[Tuple[int, str]]]
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    @property
    def eof(self) -> bool:
        """True once the last writer has closed the pipe."""
        return self._eof.is_set()

    def _keep(self, chunk: bytes) -> None:
        if self.over:
            return  # drained to the end so the ended child is not blocked
        self._size += len(chunk)
        if self._cap is not None and self._size > self._cap:
            self.over = True
            if self._on_over is not None:
                self._on_over()
            return
        self._chunks.append(chunk)

    def _run(self) -> None:
        while not self._stop.is_set():
            if not _ready(self._fd, for_write=False):
                continue
            chunk = os.read(self._fd, _CHUNK)
            if not chunk:
                self._eof.set()
                return
            self._keep(chunk)

    def _drain(self) -> None:
        """What the pipe holds now, read without waiting; end of file is set
        when the last writer has closed it since the thread stopped."""
        while _SELECTABLE and not self._eof.is_set():
            if not select.select([self._fd], [], [], 0)[0]:
                return
            chunk = os.read(self._fd, _CHUNK)
            if not chunk:
                self._eof.set()
                return
            self._keep(chunk)

    def finish(self, wait: float) -> bytes:
        """The bytes kept, after up to *wait* seconds for end of file; a
        second call returns the first one's. A pipe still open then is held
        by a process outside the child's session: holders lists each one
        (empty when /proc cannot list them). The pipe is closed once its
        thread has ended; off POSIX a thread still in a blocking read keeps
        it, since closing it under the call could hand the number to another
        file, and the daemon thread ends with the process."""
        if self._done is not None:
            return self._done
        self._eof.wait(max(0.0, wait))
        self._stop.set()
        self._thread.join(_POLL_S * 4 if _SELECTABLE else 0.0)
        if not self._thread.is_alive():
            self._drain()
        if not self._eof.is_set():
            self.holders = pipe_holders(self._inode) or []
        if not self._thread.is_alive():
            self.stream.close()
        self._done = b"".join(self._chunks)
        return self._done


def _owner_handler(handler: Any) -> bool:
    # A stop signal a ShutdownOwner holds stays the owner's: it decides when
    # the server's children end (see ShutdownOwner).
    return isinstance(getattr(handler, "__self__", None), ShutdownOwner)


@contextlib.contextmanager
def _ended_on_termination(session: ChildSession) -> Iterator[None]:
    """While inside, a signal in _UNWINDLESS ends *session* first (SIGKILL at
    once when it is already being ended) and is then raised again under the
    handler it replaced, so this process still ends the way it would have. A
    signal the caller ignores (nohup), and one a ShutdownOwner holds, is left
    as it is. Python lets only the main thread install a handler; elsewhere
    this adds nothing and the caller's except is the only teardown."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    previous = {}  # type: Dict[int, Any]

    def end_then_reraise(signum: int, _frame: object) -> None:
        if session.starting and session.proc is None:
            # The child may already run with no record of it yet: kept and
            # replayed once Popen returns, when there is a session to end.
            session.deferred.append(signum)
            return
        if session.ending:
            session.kill()
        else:
            session.end()
        signal.signal(signum, previous[signum])
        os.kill(os.getpid(), signum)

    for sig in _UNWINDLESS:
        current = signal.getsignal(sig)
        if current is signal.SIG_IGN or _owner_handler(current):
            continue
        old = signal.signal(sig, end_then_reraise)
        # None: a handler installed outside Python, which cannot be put back
        # from here; the default action is the closest to it.
        previous[sig] = signal.SIG_DFL if old is None else old
    try:
        yield
    finally:
        for sig, old in previous.items():
            signal.signal(sig, old)


@contextlib.contextmanager
def _deferred_while_starting(session: ChildSession) -> Iterator[None]:
    """While inside, a stop signal is kept in *session*'s deferred list
    instead of acting, and on leaving each is sent again to this process, now
    that session.proc names the child. SIGINT gets a recording handler for the
    window (unless the caller ignores it); SIGTERM and SIGHUP are recorded by
    _ended_on_termination's handler, which checks session.starting. Blocking
    the signals instead (pthread_sigmask) is not an option: the blocked mask
    passes through fork and exec, so the child would start with them blocked.
    Off the main thread there is no handler to swap, and the window stays
    open."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    old_int = signal.getsignal(signal.SIGINT)
    if old_int is not signal.SIG_IGN:
        signal.signal(signal.SIGINT, lambda signum, _f: session.deferred.append(signum))
    session.starting = True
    try:
        yield
    finally:
        session.starting = False
        if old_int is not signal.SIG_IGN:
            signal.signal(signal.SIGINT, signal.SIG_DFL if old_int is None else old_int)
        pending, session.deferred = session.deferred, []
        for signum in dict.fromkeys(pending):
            os.kill(os.getpid(), signum)


@contextlib.contextmanager
def _sigchld_default() -> Iterator[None]:
    """While inside, a SIGCHLD the caller set to ignore is at its default, and
    the caller's setting is put back on leaving. Ignored, the kernel reaps
    the child the moment it exits, so its pid is free while a stop could
    still signal it; at the default it stays a zombie the runner holds (and
    the child starts with the default too, where an ignored SIGCHLD would pass
    through exec). Raises ChildSignalIgnored off the main thread, where Python
    cannot change a handler, before anything has run."""
    sigchld = getattr(signal, "SIGCHLD", None)
    if sigchld is None or signal.getsignal(sigchld) is not signal.SIG_IGN:
        yield
        return
    if threading.current_thread() is not threading.main_thread():
        raise ChildSignalIgnored(
            "SIGCHLD is set to ignore and the runner is not on the main thread, "
            "so it cannot set SIGCHLD to its default for the run, and the "
            "child's exit would free its id while a stop could still signal it; "
            "run it on the main thread, or with SIGCHLD at its default"
        )
    signal.signal(sigchld, signal.SIG_DFL)
    try:
        yield
    finally:
        signal.signal(sigchld, signal.SIG_IGN)


def _watch(pid: int) -> "subprocess.Popen[bytes]":
    """The watcher for session *pid* (see _WATCHER), its stdin the pipe only
    this process writes to. In a session of its own, so a signal to the
    caller's group (a terminal's Ctrl-C) does not end it first."""
    return subprocess.Popen(  # noqa: S603 — argv list, never a shell string
        [sys.executable, "-I", "-S", "-c", _WATCHER, str(pid)],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        env=build_child_env(),
        start_new_session=True,
    )


def start_child(
    session: ChildSession,
    argv: Sequence[str],
    cwd: Optional[str],
    stdin: Any,
    stderr: Any,
    credentials_for: Optional[str] = None,
    root: Optional[str] = None,
) -> "subprocess.Popen[bytes]":
    """Start *argv* as *session*'s child, inside supervised(session): with the
    allowlisted environment (plus *credentials_for*'s credential names, read
    from *root*'s config), stdout a pipe, *stdin* and *stderr* as Popen takes
    them, in a session of its own. A stop signal while it starts is deferred
    until session.proc is set. On POSIX a watcher process follows it, which
    ends the session if this process dies without unwinding. The session is
    registered for a server's stop until supervised(session) ends. Whatever
    the spawn raises (FileNotFoundError, ChildEnvError) propagates; a watcher
    that cannot start is the OSError its spawn raises, with the child ended
    by the caller's teardown."""
    with _deferred_while_starting(session):
        session.proc = subprocess.Popen(  # noqa: S603 — argv list, never a shell string
            list(argv),
            cwd=cwd,
            stdin=stdin,
            stdout=subprocess.PIPE,
            stderr=stderr,
            env=build_child_env(credentials_for=credentials_for, root=root),
            # Its own session and group, so an end reaches what the child
            # started and not just the child.
            start_new_session=True,
        )
        _RUNNING[session.proc.pid] = session
        if os.name == "posix":
            session.watcher = _watch(session.proc.pid)
    return session.proc


def _close_watcher(session: ChildSession) -> None:
    # Ended before its pipe closes, so it never reads a normal end as this
    # process dying.
    watcher = session.watcher
    if watcher is None:
        return
    session.watcher = None
    if watcher.poll() is None:
        watcher.kill()
    watcher.wait()
    if watcher.stdin is not None:
        watcher.stdin.close()


@contextlib.contextmanager
def supervised(session: ChildSession) -> Iterator[ChildSession]:
    """Hold *session* for one run: inside, a SIGCHLD the caller ignores is at
    its default (ChildSignalIgnored off the main thread, before anything
    runs), and a SIGTERM or SIGHUP ends the session and then this process as
    it would have (see _ended_on_termination). On leaving, the watcher is
    ended, the session leaves the server's registry and the child is reaped
    (release) and its pipes closed, in that order; the caller ends the
    session before it leaves, since release waits on the child."""
    with _sigchld_default(), _ended_on_termination(session):
        try:
            yield session
        finally:
            _close_watcher(session)
            proc = session.proc
            if proc is not None:
                _RUNNING.pop(proc.pid, None)
            # Last: until here a stop signal can still reach the child's ids.
            session.release()
            if proc is not None:
                for stream in (proc.stdin, proc.stdout, proc.stderr):
                    if stream is not None:
                        stream.close()


def _end_running_sessions() -> None:
    for session in list(_RUNNING.values()):
        session.kill()


# --- a bounded child: run_bounded ----------------------------------------------


class _Writer(threading.Thread):
    """Feeds the child its input, then closes its stdin; stopped, it gives up
    on the rest."""

    def __init__(self, stream: IO[bytes], data: bytes):
        threading.Thread.__init__(self, daemon=True)
        self.stream = stream
        self.data = data
        self.stop = threading.Event()
        self.error = None  # type: Optional[OSError]

    def run(self) -> None:
        fd = self.stream.fileno()
        view = memoryview(self.data)
        try:
            if _SELECTABLE:
                # Non-blocking, so a write never outlasts a stop: a full pipe
                # takes what fits and the rest waits for the next select.
                os.set_blocking(fd, False)
            while view and not self.stop.is_set():
                if not _ready(fd, for_write=True):
                    continue
                try:
                    view = view[os.write(fd, view) :]
                except BlockingIOError:
                    continue
            if not view:
                self.stream.close()
        except BrokenPipeError:
            # The child exited without reading all of it; its status says why.
            pass
        except OSError as exc:  # carried to the caller's thread, not lost
            self.error = exc


def _set_by(source: Optional[str]) -> str:
    return "; the limit is %s" % source if source else ""


def _positive(name: str, value: object) -> None:
    # The upper bound: past threading.TIMEOUT_MAX a thread wait raises
    # OverflowError mid-call. `not 0 < value <= max` also refuses NaN.
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 0 < value <= threading.TIMEOUT_MAX
    ):
        raise ValueError(
            "run_bounded %s must be a number above 0 and at most %s, got %r"
            % (name, threading.TIMEOUT_MAX, value)
        )


def _byte_cap(value: object) -> None:
    # A cap is a length, so sys.maxsize, the longest bytes object, bounds it;
    # threading.TIMEOUT_MAX bounds seconds and has no say over bytes.
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 < value <= sys.maxsize
    ):
        raise ValueError(
            "run_bounded max_output_bytes must be a whole number above 0 and at "
            "most sys.maxsize (%d), got %r" % (sys.maxsize, value)
        )


def _named(found: Sequence[Tuple[int, str]]) -> str:
    return ", ".join("%d (%s)" % (pid, _program(command)) for pid, command in found)


def run_bounded(
    argv: Sequence[str],
    timeout: float,
    max_output_bytes: int,
    cwd: Optional[str] = None,
    stdin_text: Optional[str] = None,
    credentials_for: Optional[str] = None,
    root: Optional[str] = None,
    timeout_source: Optional[str] = None,
    output_source: Optional[str] = None,
) -> "subprocess.CompletedProcess[str]":
    """Run *argv* with the allowlisted environment (plus *credentials_for*'s
    credential names, read from *root*'s config) for at most *timeout* seconds,
    keeping at most *max_output_bytes* of each stream; *timeout_source* and
    *output_source* name where the caller configures each limit, for the
    refusal. The child runs supervised (see supervised): the call waits on its
    exit, sends SIGKILL to what it left in its session after a short settle,
    then gives its pipes one _DRAIN_S window together; a process outside the
    session still holding a pipe after that is named in a log warning, never
    signalled, and what it writes after the window is not read. ChildTimedOut,
    ChildOutputTooLarge, ChildReaped, ChildSignalIgnored, ValueError for a
    limit not above 0, a time limit past threading.TIMEOUT_MAX or a byte cap
    that is no whole number or past sys.maxsize, and whatever the spawn
    raises (FileNotFoundError, ChildEnvError) propagate."""
    _positive("timeout", timeout)
    _byte_cap(max_output_bytes)
    program = os.path.basename(argv[0]) if argv else "?"
    deadline = time.monotonic() + timeout
    # Grace 0: the limit has already passed when an end is called for, and a
    # child that traps SIGTERM would keep the caller waiting past it.
    session = ChildSession(0)
    readers = []  # type: List[PipeReader]
    writer = None  # type: Optional[_Writer]
    timed_out = False
    with supervised(session):
        try:
            proc = start_child(
                session,
                argv,
                cwd,
                subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
                subprocess.PIPE,
                credentials_for=credentials_for,
                root=root,
            )
            # Both are pipes: PIPE was asked for each, so neither is None.
            assert proc.stdout is not None and proc.stderr is not None
            readers = [
                PipeReader(proc.stdout, max_output_bytes, session.kill),
                PipeReader(proc.stderr, max_output_bytes, session.kill),
            ]
            if stdin_text is not None and proc.stdin is not None:
                writer = _Writer(proc.stdin, stdin_text.encode("utf-8"))
                writer.start()
            if session.wait_exit(deadline) is None:
                timed_out = True
                session.kill()
                session.wait_exit(float("inf"))
            alive, leftovers = session.settled()
            if alive:
                session.kill()
                _LOG.warning(
                    "%s left %s running in its session; each was sent SIGKILL",
                    program,
                    _named(leftovers) or "processes /proc could not list",
                )
            drain_by = time.monotonic() + _DRAIN_S
            if writer is not None:
                writer.join(max(0.0, drain_by - time.monotonic()))
            for reader in readers:
                reader.finish(drain_by - time.monotonic())
            for name, reader in (("stdout", readers[0]), ("stderr", readers[1])):
                if reader.holders is not None:
                    _LOG.warning(
                        "%s's %s is still held open by %s outside its session, "
                        "which was not signalled; what it writes is not read",
                        program,
                        name,
                        _named(reader.holders) or "a process /proc could not list",
                    )
        except BaseException:
            session.kill()
            raise
        finally:
            if writer is not None:
                writer.stop.set()
                writer.join(_POLL_S * 4 if _SELECTABLE else 0.0)
            for reader in readers:
                reader.finish(0)
    for name, reader in (("stdout", readers[0]), ("stderr", readers[1])):
        if reader.over:
            raise ChildOutputTooLarge(
                "%s wrote more than %d bytes to %s, so its session was ended%s"
                % (program, max_output_bytes, name, _set_by(output_source))
            )
    if timed_out:
        raise ChildTimedOut(
            "%s did not finish within %s seconds, so its session was ended%s"
            % (program, timeout, _set_by(timeout_source))
        )
    if writer is not None and writer.error is not None:
        raise writer.error
    assert session.proc is not None
    return subprocess.CompletedProcess(
        list(argv),
        session.proc.returncode,
        readers[0].finish(0).decode("utf-8", "replace"),
        readers[1].finish(0).decode("utf-8", "replace"),
    )


# --- an agent's tool child --------------------------------------------------------


def _dotted(path: Tuple[str, ...]) -> str:
    return ".".join(path)


def tool_limits(root: Optional[str] = None) -> Tuple[int, int]:
    """(tool_timeout_seconds, tool_max_output_bytes) from *root*'s
    config/project.json `agents` block (this checkout when None);
    config_loader.WrongValue for a value out of its bound, and for a time
    limit below make_targets.gate_timeout_seconds plus twice
    make_targets.gate_stop_grace_seconds plus agents.tool_gate_margin_seconds,
    and for a margin that puts that sum past the time limit's own ceiling."""
    loaded = config_loader.read(_REPO if root is None else root)
    values = config_loader.resolve(
        loaded,
        config_loader.rows(
            _TOOL_TIMEOUT, _TOOL_OUTPUT, _GATE_TIMEOUT, _GATE_GRACE, _GATE_MARGIN
        ),
        config_loader.CONFIG_FILE,
    )
    timeout = values[_TOOL_TIMEOUT]
    cap = values[_TOOL_OUTPUT]
    # A timed-out gate run spends the grace twice: ChildSession.end waits it
    # for make's session, then the runner waits it again for make's output.
    gate = values[_GATE_TIMEOUT] + 2 * values[_GATE_GRACE]
    least = gate + values[_GATE_MARGIN]
    assert isinstance(timeout, int) and isinstance(cap, int)  # the KEYS rows' type
    # The time limit's row stops at threading.TIMEOUT_MAX, so a margin that puts
    # the bound past it leaves no tool limit to accept: the fault is the margin's.
    most_margin = int(threading.TIMEOUT_MAX) - gate
    if values[_GATE_MARGIN] > most_margin:
        _refuse(
            "%s: %s is %d; accepted: at most %d, so that %s plus twice %s plus "
            "it stays within %s's ceiling, threading.TIMEOUT_MAX"
            % (
                config_loader.CONFIG_FILE,
                _dotted(_GATE_MARGIN),
                values[_GATE_MARGIN],
                most_margin,
                _dotted(_GATE_TIMEOUT),
                _dotted(_GATE_GRACE),
                _dotted(_TOOL_TIMEOUT),
            )
        )
    if timeout < least:
        # A tool child may be scripts/run_make_target.py. A SIGKILL to it
        # before its timeout path ends has the watcher send make's session
        # SIGKILL at once, so make's SIGTERM grace is cut short, the runner's
        # structured result is lost, and an applied edit is not rolled back;
        # the order is refused, not trusted.
        _refuse(
            "%s: %s is %d; accepted: at least %d, %s plus twice %s plus %s, so "
            "a tool that runs a gate is not ended before the gate runner "
            "returns its result"
            % (
                config_loader.CONFIG_FILE,
                _dotted(_TOOL_TIMEOUT),
                timeout,
                least,
                _dotted(_GATE_TIMEOUT),
                _dotted(_GATE_GRACE),
                _dotted(_GATE_MARGIN),
            )
        )
    return timeout, cap


def _refuse(line: str) -> NoReturn:
    # The loader's contract for a ConfigError: its lines are on stderr.
    sys.stderr.write(line + "\n")
    raise config_loader.WrongValue(config_loader.CONFIG_FILE, [line])


def run_tool(
    argv: Sequence[str],
    cwd: Optional[str] = None,
    stdin_text: Optional[str] = None,
    root: Optional[str] = None,
) -> "subprocess.CompletedProcess[str]":
    """run_bounded under *root*'s tool_limits (this checkout when None), with
    this checkout's allowlisted environment and no credential: what every
    agent tool child
    and the MCP action server's doer is started through. ChildTimedOut and
    ChildOutputTooLarge name the key that sets the limit passed; a config
    fault is the loader's ConfigError, raised before anything starts."""
    timeout, cap = tool_limits(root)
    return run_bounded(
        argv,
        timeout,
        cap,
        cwd=cwd,
        stdin_text=stdin_text,
        timeout_source="%s %s" % (config_loader.CONFIG_FILE, _dotted(_TOOL_TIMEOUT)),
        output_source="%s %s" % (config_loader.CONFIG_FILE, _dotted(_TOOL_OUTPUT)),
    )


# --- a server's limits and its end ---------------------------------------------


def serve_limits(root: Optional[str] = None) -> Tuple[Optional[int], float]:
    """(memory_cap_mb, shutdown_grace_seconds) from *root*'s config/project.json
    `transports.serve` (this checkout when None); config_loader.WrongValue for a
    value out of its bound. memory_cap_mb None: no cap."""
    loaded = config_loader.read(_REPO if root is None else root)
    values = config_loader.resolve(
        loaded, config_loader.rows(_MEMORY_CAP, _GRACE), config_loader.CONFIG_FILE
    )
    cap = values[_MEMORY_CAP]
    grace = values[_GRACE]
    assert cap is None or isinstance(cap, int)  # the KEYS row's type
    assert isinstance(grace, (int, float))
    return cap, grace


def cap_memory(megabytes: Optional[int]) -> str:
    """Cap this process's address space at *megabytes* (RLIMIT_AS) and return
    the line that says what was set; None sets nothing. ValueError for a cap
    that is not a whole number of megabytes above 0."""
    if megabytes is None:
        return (
            "memory cap: off (config/project.json transports.serve.memory_cap_mb "
            "is null)"
        )
    if isinstance(megabytes, bool) or not isinstance(megabytes, int) or megabytes < 1:
        raise ValueError(
            "cap_memory takes a whole number of megabytes above 0, got %r" % megabytes
        )
    if not _HAS_RLIMIT:
        return (
            "memory cap: not set, this platform has no setrlimit; the process "
            "runs with no cap"
        )
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    wanted = megabytes << 20
    clamped = ""
    if hard != resource.RLIM_INFINITY and wanted > hard:
        # An unprivileged process may lower its limit, never raise it past hard.
        wanted = hard
        clamped = ", lowered to the hard limit"
    try:
        resource.setrlimit(resource.RLIMIT_AS, (wanted, hard))
    except (ValueError, OSError) as exc:
        # Some kernels (macOS) refuse RLIMIT_AS; the server still runs, and the
        # line it writes says it is uncapped and why.
        return (
            "memory cap: not set, setrlimit refused it (%s); the process runs with no cap"
            % exc
        )
    return (
        "memory cap: %d MB of address space (RLIMIT_AS%s); an allocation past it "
        "is a MemoryError. It does not cover a file in a memory-backed directory "
        "such as /dev/shm, the total of the processes this one starts (each gets "
        "its own copy of the cap), or resident memory, which address space "
        "overstates" % (wanted >> 20, clamped)
    )


class ShutdownRequested(BaseException):
    """A stop signal reached an idle server. A BaseException, as
    KeyboardInterrupt is, so a request handler's `except Exception` cannot
    swallow the stop."""


class ShutdownOwner:
    """The one owner of a server's stop signals, from shutdown_owner."""

    def __init__(self, name: str, stop: Optional[Callable[[int], Any]]):
        self.name = name
        self.signum: Optional[int] = None
        self._stop = stop
        self._idle = False

    @contextlib.contextmanager
    def idle(self) -> Iterator[None]:
        """Mark a wait a stop may interrupt, such as reading the next request;
        ShutdownRequested at once when a stop was already asked for."""
        if self.signum is not None:
            raise ShutdownRequested(self.signum)
        self._idle = True
        try:
            yield
        finally:
            self._idle = False

    def _handle(self, signum: int, _frame: object) -> None:
        self.signum = signum
        # The first signal is a request; a second one goes to _again, which
        # ends the supervised children's sessions and then the process by it.
        for owned in _OWNED_SIGNALS:
            signal.signal(owned, self._again)
        sys.stderr.write(
            "%s: stopping on %s\n" % (self.name, signal.Signals(signum).name)
        )
        sys.stderr.flush()
        if self._stop is not None:
            self._stop(signum)
        elif self._idle:
            raise ShutdownRequested(signum)

    def _again(self, signum: int, _frame: object) -> None:
        _end_running_sessions()
        # Ended by the signal itself, as with no handler at all, so the
        # status says which signal it was (128 + its number in a shell).
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)


@contextlib.contextmanager
def shutdown_owner(
    name: str, stop: Optional[Callable[[int], Any]] = None
) -> Iterator[ShutdownOwner]:
    """Own SIGTERM and SIGINT while inside: the first one writes `<name>:
    stopping on <signal>` to stderr, then calls *stop* with the signal number,
    or, with no *stop*, raises ShutdownRequested where the owner is idle and
    else leaves `owner.signum` set for the server to see. A second one sends
    SIGKILL to the session of every supervised child still running, then ends
    the process by that signal's default action. Leaving after a stop signal
    sends the same SIGKILL before the handlers before it are put back. Only the main thread may install a
    handler; elsewhere signal.signal's ValueError propagates."""
    owner = ShutdownOwner(name, stop)
    previous: Dict[int, Any] = {}
    try:
        for owned in _OWNED_SIGNALS:
            previous[owned] = signal.signal(owned, owner._handle)
        yield owner
    finally:
        if owner.signum is not None:
            # The server has stopped by now, its grace spent: a request
            # thread still waiting on a bounded child would hold the
            # process's exit for that child's whole limit.
            _end_running_sessions()
        for signum, handler in previous.items():
            # None: a handler installed outside Python, which cannot be put
            # back from here; the default action is the closest to it.
            signal.signal(signum, signal.SIG_DFL if handler is None else handler)
