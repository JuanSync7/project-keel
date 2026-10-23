"""
title: resource_limits — a bounded child process, and a server's memory cap and stop
kind: script
layer: n/a
summary: `run_bounded` starts a program through the child-process allowlist (scripts/child_env.py build_child_env, called inside the spawn so check_X sees it) in a process group of its own, feeds it the caller's stdin text, and returns a subprocess.CompletedProcess with its status and its output decoded as UTF-8. The call waits on the child's own exit, then gives its pipes one shared drain window of _DRAIN_S (2) seconds, so it returns within its limit plus that window: a process the child started that still holds a pipe then has the group sent SIGKILL (a setsid process is outside it and is left), what it writes after the window is not read, every pipe is closed and every thread it started has ended, and the child's own status and output are returned. A child still running when the caller's time limit passes has its whole group sent SIGKILL and is refused as ChildTimedOut; a child that writes more than the caller's byte cap to either stream has its group ended the same way and is refused as ChildOutputTooLarge. Both are RuntimeError subclasses whose message names the program by its file name only (never its arguments, which may carry a prompt), the limit, and the config key the caller says sets it. A limit below or equal to zero, or past threading.TIMEOUT_MAX (where a thread wait overflows), is a ValueError before anything starts; an exception while the child runs (KeyboardInterrupt included) ends its group before it propagates; a program that does not exist is the FileNotFoundError the spawn raises. Off POSIX there is no process group, so only the child itself is ended, and a pipe a stray process holds is left open with its thread until the process ends. run_bounded reads no configuration of its own. For a server entry point, serve_limits reads config/project.json `transports.serve` (memory_cap_mb, shutdown_grace_seconds) through scripts/config_loader.py; cap_memory sets RLIMIT_AS to that many megabytes and returns a line naming what it set and what it does not cover (a file in a memory-backed directory, the processes the server starts, resident memory), or that it set nothing (null, or no setrlimit on this platform); shutdown_owner owns SIGTERM and SIGINT while a server runs: the first writes `<name>: stopping on <signal>` to stderr and calls the server's stop, or raises ShutdownRequested, a BaseException, where the server waits idle, and a second one sends SIGKILL to the process group of every run_bounded child still running (each is in a group of its own, which a signal to the server does not reach), then ends the process by that signal's default action, so its exit status names the signal (128 plus its number in a shell). A child started in the instant between its spawn and its registration, or a process a child moved out of its group with setsid, is not reached. It writes no file.
"""

# NB: stdlib only, no `from __future__ import annotations`, no f-strings, no walrus,
# no `list[str]` or `X | None` annotations: this module sits in the bottom import
# layer (config/project.json import_layers.order), which
# tests/integration/test_gate_scope.py holds to the oldest interpreter a hook runs.

import contextlib
import os
import select
import signal
import subprocess
import sys
import threading
import time
from typing import IO, Any, Callable, Dict, Iterator, List, Optional, Sequence, Tuple

from scripts import config_loader
from scripts.child_env import build_child_env

try:
    import resource

    _HAS_RLIMIT = True
except ImportError:  # not POSIX: cap_memory says the cap is not set
    _HAS_RLIMIT = False

__all__ = [
    "ChildOutputTooLarge",
    "ChildTimedOut",
    "ShutdownOwner",
    "ShutdownRequested",
    "cap_memory",
    "run_bounded",
    "serve_limits",
    "shutdown_owner",
]

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MEMORY_CAP = ("transports", "serve", "memory_cap_mb")
_GRACE = ("transports", "serve", "shutdown_grace_seconds")
_OWNED_SIGNALS = (signal.SIGTERM, signal.SIGINT)

# The process group of each run_bounded child still running, keyed by the
# child's pid, which is its group's id: a second stop signal ends them all,
# since a signal to the server never reaches a group of its own. A dict and no
# lock: the handler runs on the main thread between bytecodes, possibly while
# that thread holds any lock, and a dict's item set, pop and list() each run
# whole under the GIL.
_RUNNING_GROUPS: Dict[int, None] = {}

# One read's size: large enough that a child writing megabytes costs few
# wake-ups, small enough that the cap is overshot by at most this much in memory.
_CHUNK = 65536

# How long the pipes get, all together, once the leader has ended: a child's
# own output is in the pipe by then and is read in far less, so a longer wait
# means a process it started still holds a pipe, and that process is not the
# caller's to wait for. A call so returns within its limit plus this window.
_DRAIN_S = 2.0

# How often a reader or the writer looks up from a pipe for its stop flag, so
# the call can end a thread whose pipe a stray process holds and close the pipe.
_POLL_S = 0.05

# select works on a pipe only on POSIX; elsewhere a pipe thread reads or writes
# blocking, cannot be stopped, and its pipe is left open for the process's end.
_SELECTABLE = os.name == "posix"


class ChildTimedOut(RuntimeError):
    """The child outlived its time limit."""


class ChildOutputTooLarge(RuntimeError):
    """The child wrote more than its byte cap to stdout or stderr."""


def _end_group(proc: "subprocess.Popen[bytes]") -> None:
    # SIGKILL, not SIGTERM: the limit has already passed, and a child that traps
    # SIGTERM would keep the caller waiting past it.
    if os.name == "posix":
        # Gone already: PermissionError is how some kernels answer for a group
        # whose only member is a zombie leader.
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, signal.SIGKILL)
    if proc.poll() is None:
        proc.kill()


def _end_running_groups() -> None:
    if os.name != "posix":
        return  # no process groups: the children end with their own exit
    for pgid in list(_RUNNING_GROUPS):
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(pgid, signal.SIGKILL)


def _ready(fd: int, for_write: bool) -> bool:
    if not _SELECTABLE:
        return True
    if for_write:
        return bool(select.select([], [fd], [], _POLL_S)[1])
    return bool(select.select([fd], [], [], _POLL_S)[0])


class _Reader(threading.Thread):
    """Reads one pipe to its end, or until stopped, keeping at most cap + one
    chunk in memory."""

    def __init__(self, stream: IO[bytes], cap: int, on_over: Callable[[], None]):
        threading.Thread.__init__(self, daemon=True)
        self.stream = stream
        self.cap = cap
        self.on_over = on_over
        self.stop = threading.Event()
        self.chunks: List[bytes] = []
        self.size = 0
        self.over = False

    def run(self) -> None:
        fd = self.stream.fileno()
        while not self.stop.is_set():
            if not _ready(fd, for_write=False):
                continue
            chunk = os.read(fd, _CHUNK)
            if not chunk:
                return
            if self.over:
                continue  # drain to the end so the killed child is not blocked
            self.size += len(chunk)
            if self.size > self.cap:
                self.over = True
                self.on_over()
                continue
            self.chunks.append(chunk)

    def text(self) -> str:
        return b"".join(self.chunks).decode("utf-8", "replace")


class _Writer(threading.Thread):
    """Feeds the child its input, then closes its stdin; stopped, it gives up
    on the rest."""

    def __init__(self, stream: IO[bytes], data: bytes):
        threading.Thread.__init__(self, daemon=True)
        self.stream = stream
        self.data = data
        self.stop = threading.Event()
        self.error: Optional[OSError] = None

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


def _await_exit(proc: "subprocess.Popen[bytes]", deadline: float) -> bool:
    """True once *proc* has exited, False when *deadline* passes first."""
    try:
        proc.wait(max(0.0, deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        return False
    return True


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
    refusal. The call waits on the child's own exit, then gives its pipes one
    _DRAIN_S window together; a process the child left holding a pipe past
    that has the group ended, and what it wrote after the window is not read.
    ChildTimedOut, ChildOutputTooLarge, ValueError for a limit not above 0 or
    past threading.TIMEOUT_MAX, and whatever the spawn raises
    (FileNotFoundError, ChildEnvError) propagate."""
    _positive("timeout", timeout)
    _positive("max_output_bytes", max_output_bytes)
    if isinstance(max_output_bytes, float):
        raise ValueError("run_bounded max_output_bytes must be a whole number")
    program = os.path.basename(argv[0]) if argv else "?"
    deadline = time.monotonic() + timeout
    proc = subprocess.Popen(
        list(argv),
        cwd=cwd,
        stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=build_child_env(credentials_for=credentials_for, root=root),
        start_new_session=True,
    )
    _RUNNING_GROUPS[proc.pid] = None
    # Both are pipes: PIPE was asked for each, so neither is None.
    assert proc.stdout is not None and proc.stderr is not None
    readers = [
        _Reader(proc.stdout, max_output_bytes, lambda: _end_group(proc)),
        _Reader(proc.stderr, max_output_bytes, lambda: _end_group(proc)),
    ]
    writer = None
    if stdin_text is not None and proc.stdin is not None:
        writer = _Writer(proc.stdin, stdin_text.encode("utf-8"))
    threads: List[Any] = readers + ([writer] if writer is not None else [])
    timed_out = False
    try:
        for thread in threads:
            thread.start()
        if not _await_exit(proc, deadline):
            timed_out = True
            _end_group(proc)
            proc.wait()
        drain_by = time.monotonic() + _DRAIN_S
        for thread in threads:
            thread.join(max(0.0, drain_by - time.monotonic()))
        if any(thread.is_alive() for thread in threads):
            # A process the child started holds a pipe: end the group, which
            # reaches it unless it called setsid.
            _end_group(proc)
    except BaseException:
        _end_group(proc)
        raise
    finally:
        for thread in threads:
            thread.stop.set()
        for thread in threads:
            if thread.ident is not None:
                thread.join(_POLL_S * 4 if _SELECTABLE else 0.0)
            # A thread still in a blocking call (off POSIX) keeps its pipe:
            # closing it under the call could hand the number to another
            # file. The daemon thread ends with the process.
            if not thread.is_alive():
                thread.stream.close()
        _RUNNING_GROUPS.pop(proc.pid, None)
    for name, reader in (("stdout", readers[0]), ("stderr", readers[1])):
        if reader.over:
            raise ChildOutputTooLarge(
                "%s wrote more than %d bytes to %s, so its process group was ended%s"
                % (program, max_output_bytes, name, _set_by(output_source))
            )
    if timed_out:
        raise ChildTimedOut(
            "%s did not finish within %s seconds, so its process group was ended%s"
            % (program, timeout, _set_by(timeout_source))
        )
    if writer is not None and writer.error is not None:
        raise writer.error
    return subprocess.CompletedProcess(
        list(argv), proc.returncode, readers[0].text(), readers[1].text()
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
        # The first signal is a request; a second one ends the process at once.
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
        _end_running_groups()
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
    SIGKILL to the process group of every run_bounded child still running,
    then ends the process by that signal's default action. The handlers before
    it are put back on the way out. Only the main thread may install a
    handler; elsewhere signal.signal's ValueError propagates."""
    owner = ShutdownOwner(name, stop)
    previous: Dict[int, Any] = {}
    try:
        for owned in _OWNED_SIGNALS:
            previous[owned] = signal.signal(owned, owner._handle)
        yield owner
    finally:
        for signum, handler in previous.items():
            # None: a handler installed outside Python, which cannot be put
            # back from here; the default action is the closest to it.
            signal.signal(signum, signal.SIG_DFL if handler is None else handler)
