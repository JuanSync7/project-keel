#!/usr/bin/env python3
"""
title: Run make target (the read-only gate runner)
kind: script
layer: n/a
summary: Deterministic doer — run a make target as a gate and report a structured pass/fail, but only a target whose effect label, closed over what it runs, falls inside config/project.json `make_targets.gate_effects`. It refuses an unknown, unlabelled or wider target, an extra argument that is not a NAME=VALUE variable named in `make_targets.gate_vars` with a one-word path-like value, a tree without git, and an allowlist scripts/child_env.py cannot build or that would copy a value carrying a credential, all before make runs; it forwards a `make_targets.gate_vars` variable found in its own environment onto make's command line under the same one-word rule (an explicit one wins), and refuses any gate value, explicit or forwarded, that carries a credential by scripts/child_env.py's carries_credential under the project's child_env policy (user information, or a `child_env.credential_value_patterns` match, named by its label), even one `child_env.credentialed_values` opts in, because make's command line reaches every recipe; every refusal names the variable and never quotes a value; because make and git get the allowlisted environment from scripts/child_env.py, never this one; it sets the gate-runner variable last so WRITE_GUARD refuses a [write] target; and it snapshots what git lists before and after (each path's porcelain status and content, by scripts/git_tree.py), failing a green run that changed it and naming the paths, and one whose tree cannot be re-read afterwards. It reads config/project.json through scripts/config_loader.py `read`, so a manifest it cannot use, a key written twice in one object included, is a refusal carrying the loader's line. It starts make in a session of its own and gives it `--timeout` seconds, else config/project.json `make_targets.gate_timeout_seconds` (scripts/config_loader.py KEYS gives its type and default; a value that is not a whole number >= 1 is ExitCode.CONFIG, or a refusal from run_target). On that timeout, on KeyboardInterrupt (ExitCode.INTERRUPTED) and on a SIGTERM or SIGHUP to itself it ends make's whole session, every process group in it included (GNU `timeout` moves itself to a group of its own and stays in the session): SIGTERM, then SIGKILL once `make_targets.gate_stop_grace_seconds` pass with any member alive (a second interrupt during that wait still sends the SIGKILL; a signal the caller ignored stays ignored); it signals no process outside that session, and holds make unreaped (os.waitid WNOWAIT, where Python has it) so the group id cannot be reused meanwhile. It waits on make's exit, not on its output, so a background job holding the output open does not hold the run. A timeout is red with `timed_out` true in the result and ExitCode.FAILURE from the command line; a process still in the session (a zombie excepted) after make exits and a short settle is ended the same way, listed by pid and command in `leaked`, and fails closed: a make that exited 0 is red (ExitCode.FAILURE, naming each leftover), and a make that failed keeps its own status. A runner killed with SIGKILL cannot do this, so make's session outlives it. The refactor loop (agents/practice_refactor, scripts/apply_refactor.py) and tests/integration/test_make_target_effects.py gate through it. Vendor-neutral, stdlib; it writes nothing itself.
"""

from __future__ import annotations

import argparse
import functools
import json
import os
import re
import select
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_structure  # noqa: E402 — the one owner of the label grammar and policy
import child_env  # noqa: E402 — the environment make and git inherit
import config_loader  # noqa: E402 — the one reader of config/project.json
from exit_codes import ExitCode, finish, report  # noqa: E402

# One definition of what git lists, shared with scripts/gate_evidence.py. `_git`
# is re-exported, not used here: tests/unit/scripts/test_run_make_target.py proves
# through it that git, like make, runs with the allowlisted environment.
from git_tree import (  # noqa: E402
    GitFailedError,
    NoGitError,
    _git,  # noqa: F401
    tree_snapshot,
)

# A make target is a plain token — reject anything that could be a shell
# injection (the target reaches `make` as an argv element, never a shell string,
# but validating keeps callers honest and the intent auditable).
_TARGET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
# The only extra argument a gate run accepts: a make variable. A flag could point
# make at another makefile (`-f`, `-C`) or add a goal whose label nobody read.
_VARIABLE_ARG = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")
# ...and only one config/project.json `make_targets.gate_vars` names, with a value
# that is one path-like word. A recipe expands the value into a shell line, so a
# space, `;`, `$` or a quote would let a [local] target run a [write] one with the
# guard unset (measured: `PY=make deploy-apply RALPH= ; true` did). A leading
# `-`/`+`/`@` would become a make recipe prefix. The value still names a program
# the recipe runs; choosing it is the caller's, and the tree snapshot is the
# backstop for what that program does.
_GATE_VALUE = re.compile(r"^(?:[A-Za-z0-9_./~][A-Za-z0-9_./+,:@%~-]*)?$")
_MANIFEST = os.path.join("config", "project.json")
# The gate's time limit and the grace a stopped run gets between SIGTERM and
# SIGKILL; scripts/config_loader.py `KEYS` gives each its type, bound and default.
LIMIT_KEYS = (
    ("make_targets", "gate_timeout_seconds"),
    ("make_targets", "gate_stop_grace_seconds"),
)
# How often the stop loop asks whether make's session is empty. It only
# sets how soon after the last member exits the runner notices, never how long
# a member gets: the grace bounds that.
_POLL_SECONDS = 0.05
# How long members still in make's session after it exits are re-read before
# they count as left behind: `(cmd &)` whose cmd is finishing as make exits
# would otherwise be a leak by a race. It bounds the wait on a green run, and
# a real leftover is reported after it.
_SETTLE_SECONDS = 0.5
# Signals whose default action ends this process without unwinding its stack.
# make runs in its own session, so the signal no longer reaches make's group
# with this process: a CI cancel, `timeout` and a batch scheduler's limit send
# SIGTERM, a closed terminal SIGHUP. SIGINT already unwinds (KeyboardInterrupt);
# SIGKILL cannot be caught, and is the one way this runner still orphans make.
_UNWINDLESS = tuple(
    getattr(signal, name) for name in ("SIGTERM", "SIGHUP") if hasattr(signal, name)
)

# (returncode, combined_output) — the shape a runner returns.
Runner = Callable[[Sequence[str], "str | None", int], "tuple[int, str]"]
# root -> {repo-relative path: digest} — what git lists, and each entry's content.
Snapshot = Callable[[str], "dict[str, str]"]


def is_safe_target(name: str) -> bool:
    """True when `name` is a plain make-target token (no shell metacharacters).

    SAFE means well-formed, NOT read-only: `fmt` is a plain token and rewrites
    the tree. Read-only-ness is the effect label's claim (check_W), which
    run_target checks and then tests by snapshotting the tree.
    """
    return bool(_TARGET_RE.match(name or ""))


def _session_members(sid: int) -> list[tuple[int, int, str]] | None:
    """(pid, process group, command) of each process in session *sid* that
    still runs, read from /proc (Linux), or None on a host with no /proc. make
    leads its session and its group, so *sid* is make's pid; a group never
    spans sessions, so this holds every member of make's group and every
    process that moved to a group of its own and stayed in the session (GNU
    `timeout` does, unless given --foreground). A zombie runs nothing, so it is
    not a member: its parent (make's, a subreaper's) reaps it in its own time,
    and the runner never waits for that. A process that ends while it is read
    is skipped."""
    try:
        names = os.listdir("/proc")
    except OSError:
        return None
    members = []
    for name in sorted(names, key=lambda n: (len(n), n)):
        if not name.isdigit():
            continue
        try:
            with open("/proc/%s/stat" % name, encoding="utf-8") as fh:
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


def _signal_group(pgid: int, sig: int) -> None:
    """Send *sig* to group *pgid*; a group that has emptied meanwhile is the
    outcome the caller wanted, so it is not an error."""
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        return


def _exit_status(proc: subprocess.Popen[bytes]) -> int | None:
    """make's status once it has exited (negative: the signal that ended it),
    else None. Where os.waitid exists make is left unreaped (WNOWAIT): its
    zombie keeps holding its pid, which is the group id, so no new process can
    take that id while the runner still signals the group. Elsewhere make is
    reaped here, and that guarantee is lost."""
    if not hasattr(os, "waitid"):
        return proc.poll()
    try:
        info = os.waitid(os.P_PID, proc.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    except ChildProcessError:
        return proc.returncode
    if info is None or info.si_pid == 0:
        return None
    return info.si_status if info.si_code == os.CLD_EXITED else -info.si_status


class LeftRunning(Exception):
    """make exited with *returncode* and *output*, but the processes in
    *leftovers* ((pid, command) pairs; empty when they could not be listed)
    were still running in its session; they have been ended by the time this is
    raised."""

    def __init__(
        self, returncode: int, output: str, leftovers: Sequence[tuple[int, str]]
    ) -> None:
        super().__init__(returncode, output, leftovers)
        self.returncode = returncode
        self.output = output
        self.leftovers = list(leftovers)


class _Group:
    """make's session: *proc* leads it and its first process group (it
    started with start_new_session), so its pid is both ids. The members are
    every process in that session, whatever group each is in, and nothing
    outside it is signalled. Empty until the runner has started make."""

    def __init__(self, grace: int) -> None:
        self.grace = grace
        self.proc: subprocess.Popen[bytes] | None = None
        self.ending = False

    def _listed(self) -> list[tuple[int, int, str]] | None:
        assert self.proc is not None
        return _session_members(self.proc.pid)

    def members(self) -> tuple[bool, list[tuple[int, str]]]:
        """(alive, the members it could list). Without /proc, alive comes from
        signal 0 to make's group, which a zombie also answers, the list is
        empty, and a process that left the group is not seen."""
        assert self.proc is not None
        listed = self._listed()
        if listed is not None:
            return bool(listed), [(pid, command) for pid, _g, command in listed]
        self.proc.poll()
        try:
            os.killpg(self.proc.pid, 0)
        except ProcessLookupError:
            return False, []
        except PermissionError:
            return True, []
        return True, []

    def settled(self) -> tuple[bool, list[tuple[int, str]]]:
        """members(), re-read for up to _SETTLE_SECONDS while any remain, so a
        background job that is exiting as make exits is not a leftover."""
        deadline = time.monotonic() + _SETTLE_SECONDS
        alive, listed = self.members()
        while alive and time.monotonic() < deadline:
            time.sleep(_POLL_SECONDS)
            alive, listed = self.members()
        return alive, listed

    def signal(self, sig: int) -> None:
        """*sig* to make's group, then to each other group a session member
        was listed in. A group id stays taken while any member holds it, so
        a listed group cannot pass to an unrelated process unless all of it
        exits and the id is handed out again before the signal is sent."""
        if self.proc is None:
            return
        _signal_group(self.proc.pid, sig)
        for pgid in sorted({g for _p, g, _c in self._listed() or ()} - {self.proc.pid}):
            _signal_group(pgid, sig)

    def kill(self) -> None:
        self.signal(signal.SIGKILL)

    def end(self) -> None:
        """SIGTERM, up to the grace for the session to empty, then SIGKILL,
        and make reaped. The SIGKILL is in a finally, so a second interrupt
        that cuts the grace short still reaches every member."""
        if self.proc is None:
            return
        self.ending = True
        try:
            self.signal(signal.SIGTERM)
            deadline = time.monotonic() + self.grace
            while self.members()[0] and time.monotonic() < deadline:
                time.sleep(_POLL_SECONDS)
        finally:
            if self.members()[0]:
                self.kill()
            self.proc.wait()


class _Reader:
    """Reads *stream* on a thread until end of file or until stopped, so the
    runner waits on make's exit and not on its output: a background child that
    holds the pipe open no longer holds the run."""

    def __init__(self, stream: Any) -> None:
        self._fd = stream.fileno()
        self._chunks: list[bytes] = []
        self._stop = threading.Event()
        self._eof = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            ready, _, _ = select.select([self._fd], [], [], _POLL_SECONDS)
            if not ready:
                continue
            chunk = os.read(self._fd, 65536)
            if not chunk:
                self._eof.set()
                return
            self._chunks.append(chunk)

    def finish(self, wait: float) -> str:
        """The output read, after up to *wait* seconds for end of file. A pipe
        still open then is held by a process outside make's group, which is
        not this runner's to end; the output says so."""
        self._eof.wait(wait)
        self._stop.set()
        self._thread.join()
        text = b"".join(self._chunks).decode("utf-8", "replace")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if not self._eof.is_set():
            text += (
                "run_make_target: output after this point was not read: a process "
                "outside make's group holds make's output open\n"
            )
        return text


@contextmanager
def _group_ended_on_termination(group: _Group) -> Iterator[None]:
    """While inside, a signal in _UNWINDLESS ends *group* first (SIGKILL at
    once when it is already being ended) and is then raised again under the
    handler it replaced, so this process still ends the way it would have. A
    signal the caller ignores (nohup) is left ignored. Python lets only the
    main thread install a handler; elsewhere this adds nothing and the
    caller's except is the only teardown."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    previous: dict[int, Any] = {}

    def end_then_reraise(signum: int, _frame: object) -> None:
        if group.ending:
            group.kill()
        else:
            group.end()
        signal.signal(signum, previous[signum])
        os.kill(os.getpid(), signum)

    for sig in _UNWINDLESS:
        if signal.getsignal(sig) is signal.SIG_IGN:
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


def _default_runner(
    cmd: Sequence[str], cwd: str | None, timeout: int, grace: int
) -> tuple[int, str]:
    """(returncode, combined output) of *cmd*, run in its own session so that
    every process it starts can be ended with it. The run ends when make
    exits, whatever still holds its output. Past *timeout* seconds, or on any
    exception while it runs (KeyboardInterrupt included), the whole session is
    ended (see _Group.end) and subprocess.TimeoutExpired, carrying the output
    read so far, or the exception, is raised. A session member still running
    after make exits is ended too, and LeftRunning names it."""
    group = _Group(grace)
    # Handlers first, so a SIGTERM that lands while make starts still ends it.
    with _group_ended_on_termination(group):
        proc = subprocess.Popen(  # noqa: S603 — argv list, never a shell string
            list(cmd),
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=child_env.build_child_env(),
            # Its own session and group, so a timeout reaches what make
            # started (pytest, copier, a server) and not just make: killing
            # make alone left those running and writing in the tree.
            start_new_session=True,
        )
        group.proc = proc
        reader = _Reader(proc.stdout)
        try:
            deadline = time.monotonic() + timeout
            status = _exit_status(proc)
            while status is None and time.monotonic() < deadline:
                time.sleep(_POLL_SECONDS)
                status = _exit_status(proc)
            if status is None:
                group.end()
                raise subprocess.TimeoutExpired(
                    list(cmd), timeout, output=reader.finish(grace)
                )
            alive, leftovers = group.settled()
            if alive:
                # Listed before they are ended, so the report can name them.
                group.end()
                raise LeftRunning(status, reader.finish(grace), leftovers)
            proc.wait()
            return status, reader.finish(grace)
        except (subprocess.TimeoutExpired, LeftRunning):
            raise
        except BaseException:
            # Any exception leaves make's session with no owner: end it, then
            # let the exception carry on to the caller.
            group.end()
            raise
        finally:
            reader.finish(0)
            if proc.stdout is not None:
                proc.stdout.close()


def gate_limits(
    manifest: Mapping[str, Any], timeout: int | None = None, grace: int | None = None
) -> tuple[int, int]:
    """(timeout, grace) in seconds: each given value, else its LIMIT_KEYS row
    resolved from *manifest* (config/project.json, parsed) by
    scripts/config_loader.py, which announces a default it uses. Raises
    config_loader.ConfigError (WrongValue for a value out of its row's bound)
    and ValueError for a given value below 1."""
    for name, given in (("timeout", timeout), ("grace", grace)):
        if given is not None and (type(given) is not int or given < 1):
            raise ValueError(
                "the gate %s must be 1 or more seconds, not %r" % (name, given)
            )
    if timeout is not None and grace is not None:
        return timeout, grace
    values = config_loader.resolve(
        manifest, config_loader.rows(*LIMIT_KEYS), config_loader.CONFIG_FILE
    )
    return (
        values[LIMIT_KEYS[0]] if timeout is None else timeout,
        values[LIMIT_KEYS[1]] if grace is None else grace,
    )


def _refusal(target: str, why: str, effects: Sequence[str] = ()) -> dict[str, object]:
    return {
        "target": target,
        "ok": False,
        "returncode": None,
        "output": "run_make_target: refused `make %s`: %s\n" % (target, why),
        "effects": list(effects),
        "changed": [],
        "refused": why,
        "timed_out": False,
        "leaked": [],
    }


def _policy(
    root: str,
) -> tuple[dict[str, Any], dict[str, object] | None, str | None]:
    """(manifest, policy, None), or ({}, None, why) when the policy is unknown."""
    path = os.path.join(root, _MANIFEST)
    if not os.path.isfile(path):
        return (
            {},
            None,
            "%s is absent, so the make_targets policy is unknown" % _MANIFEST,
        )
    try:
        manifest = config_loader.read(root, _MANIFEST)
    except config_loader.ConfigError as exc:
        return (
            {},
            None,
            "%s, so the make_targets policy is unknown" % "; ".join(exc.lines),
        )
    policy, errs = check_structure.make_targets_policy(manifest)
    if errs:
        return {}, None, "%s: %s" % (_MANIFEST, "; ".join(errs))
    return manifest, policy, None


def run_target(
    target: str,
    cwd: str | None = None,
    timeout: int | None = None,
    extra: Sequence[str] | None = None,
    runner: Runner | None = None,
    snapshot: Snapshot | None = None,
    grace: int | None = None,
) -> dict[str, object]:
    """Run ``make <target>`` as a read-only gate and return a structured result.

    The result holds target, ok, returncode, output, effects (the target's
    closed-over label), changed (sorted paths whose git-listed state differs
    after the run), refused (None, or why the run never started) and timed_out
    (True when make ran past ``timeout``) and leaked ("<pid> <command>" of each
    process left in make's session after it exited, ended; any makes ok False). A
    refusal never calls the runner.
    ``timeout`` and ``grace`` are seconds; each left None is read through
    gate_limits, and a limit config/project.json gets wrong is a refusal.
    Past the timeout, or on an interrupt, every process make started is ended
    (SIGTERM, then SIGKILL after ``grace``); an interrupt is then re-raised. ``extra`` are NAME=VALUE make variables, each named
    in ``make_targets.gate_vars`` with a one-word path-like value; a gate
    variable set in this process's environment and not in ``extra`` is
    forwarded the same way (make itself gets the allowlisted environment from
    scripts/child_env.py, never this one). The gate-runner variable is appended
    last, so a caller cannot unset it.
    ``runner`` and ``snapshot`` are injected for testing.
    Raises ValueError on a target name that is not a plain token.
    """
    if not is_safe_target(target):
        raise ValueError("unsafe make target: %r" % target)
    root = os.path.abspath(cwd or os.getcwd())
    extra = list(extra or [])
    for arg in extra:
        if not _VARIABLE_ARG.match(arg):
            return _refusal(
                target,
                "`%s` is not a NAME=VALUE make variable -- a gate run passes only "
                "variables, never a flag (`-f`/`-C` would run a makefile whose "
                "labels were never read) or another goal" % arg,
            )
    manifest, policy, why = _policy(root)
    if policy is None:
        return _refusal(target, str(why))
    try:
        timeout, grace = gate_limits(manifest, timeout, grace)
    except config_loader.ConfigError as exc:
        return _refusal(
            target, "%s, so the gate's time limit is unknown" % "; ".join(exc.lines)
        )
    # Built once here so a malformed allowlist is a refusal before the tree is
    # touched; make and git rebuild it from the same file a moment later. It
    # runs before the gate variables are forwarded because a gate variable is
    # allowlisted: one whose value carries a credential must be refused by name
    # before the one-word rule below could quote the value back, or forwarding
    # could put it on make's command line. The policy is read once, beside it,
    # so a gate value is judged by the same credential_value_patterns and
    # login_name_schemes the allowlist applies.
    try:
        child_env.build_child_env()
        env_policy = child_env.load_policy()
    except child_env.ChildEnvError as exc:
        return _refusal(
            target,
            "cannot start make or git without an allowlisted environment -- %s" % exc,
        )
    allowed = list(policy["gate_vars"])  # type: ignore[call-overload]
    # A gate variable the caller's make set reaches this process only through the
    # environment; make's own child gets the allowlist, so it is forwarded here,
    # on the command line, under the same one-word rule. An explicit one wins.
    given = {arg.split("=", 1)[0] for arg in extra}
    for name in sorted(allowed):
        if name in given or name not in os.environ:
            continue
        if not _GATE_VALUE.match(os.environ[name]):
            # The value is never quoted: a credential in a form no rule
            # recognises would otherwise reach the caller's log.
            return _refusal(
                target,
                "the environment variable %s is not one path-like word (value not "
                "shown) -- forwarded to make it would be expanded into a shell "
                "line, where spaces, `;`, `$` or quotes could run a target whose "
                "label nobody read" % name,
            )
        extra.append("%s=%s" % (name, os.environ[name]))
    for arg in extra:
        name, value = arg.split("=", 1)
        if name not in allowed:
            return _refusal(
                target,
                "`%s` is not one of make_targets.gate_vars [%s] -- a gate run sets "
                "no make control variable, guard or unattended variable, which could "
                "run what no label declares" % (name, ",".join(allowed)),
            )
        # Judged even when child_env.credentialed_values opts the variable in:
        # that lets a child's environment carry it, but make hands its command
        # line to every recipe through MAKEFLAGS, and `ps` shows it.
        label = child_env.carries_credential(name, value, env_policy)
        if label is not None:
            return _refusal(
                target,
                "`%s`'s value carries a credential (matched: %s; value not shown) "
                "-- a gate variable names a program or path, and make's command "
                "line reaches every recipe and any `ps`; pass the program without "
                "the credential" % (name, label),
            )
        if not _GATE_VALUE.match(value):
            return _refusal(
                target,
                "`%s`'s value is not one path-like word (value not shown) -- a "
                "recipe expands it into a shell line, where spaces, `;`, `$` or "
                "quotes could run a target whose label nobody read" % name,
            )
    effects = check_structure.target_effects(root)
    if target not in effects:
        return _refusal(
            target, "no rule named `%s` in this project's makefiles" % target
        )
    labels, why = effects[target]
    if labels is None:
        return _refusal(target, "cannot prove `make %s` read-only: %s" % (target, why))
    gate = list(policy["gate_effects"])  # type: ignore[call-overload]
    wider = [w for w in labels if w not in gate]
    if wider:
        return _refusal(
            target,
            "`make %s` is labelled [%s] (closed over what it runs), outside "
            "make_targets.gate_effects [%s] -- a gate run only runs what leaves the "
            "tree and shared state alone" % (target, ",".join(labels), ",".join(gate)),
            labels,
        )
    snap = snapshot or tree_snapshot
    try:
        before = snap(root)
    except NoGitError as exc:
        return _refusal(
            target,
            "cannot prove a read-only run without git -- %s is not a git work tree "
            "(%s)" % (root, exc),
            labels,
        )
    except GitFailedError as exc:
        return _refusal(
            target,
            "cannot prove a read-only run: git could not list the tree at %s (%s)"
            % (root, exc),
            labels,
        )
    cmd = ["make", target, *extra, "%s=1" % policy["gate_runner_var"]]
    # Looked up at call time, so a test that replaces _default_runner is used.
    run = runner or functools.partial(_default_runner, grace=grace)
    timed_out = False
    leaked: list[str] = []
    try:
        code, output = run(cmd, root, timeout)
    except LeftRunning as exc:
        code = exc.returncode
        leaked = ["%d %s" % pair for pair in exc.leftovers]
        output = (
            "%srun_make_target: `make %s` leaked %s: %s still running in its "
            "session after make exited, so they were ended (SIGTERM, then "
            "SIGKILL after %d s); a gate target must stop every process it starts\n"
            % (
                exc.output,
                target,
                "a process" if len(leaked) == 1 else "processes",
                "; ".join(leaked) or "(the members could not be listed)",
                grace,
            )
        )
        if not leaked:
            leaked = ["(unlisted)"]
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        partial = exc.output if isinstance(exc.output, str) else ""
        code, output = (
            None,
            "%srun_make_target: `make %s` did not complete within %d s, so every "
            "process in its session was ended (SIGTERM, then SIGKILL after %d s)\n"
            % (partial, target, timeout, grace),
        )
    except (OSError, child_env.ChildEnvError) as exc:
        code, output = (
            None,
            "run_make_target: `make %s` did not complete: %s\n"
            % (
                target,
                exc,
            ),
        )
    try:
        after = snap(root)
    except (NoGitError, GitFailedError, child_env.ChildEnvError) as exc:
        # The run may have broken git or the allowlist itself; either way its
        # read-only claim is unproven, so the verdict is red, never a crash.
        return {
            "target": target,
            "ok": False,
            "returncode": code,
            "output": "%s\nrun_make_target: cannot re-read the tree after `make %s`, "
            "so the run is not proven read-only: %s\n" % (output, target, exc),
            "effects": list(labels),
            "changed": [],
            "refused": None,
            "timed_out": timed_out,
            "leaked": leaked,
        }
    changed = sorted(
        p for p in set(before) | set(after) if before.get(p) != after.get(p)
    )
    if changed:
        output = (
            "%s\nrun_make_target: `make %s` changed the tree (what git lists): %s\n"
            % (
                output,
                target,
                ", ".join(changed),
            )
        )
    return {
        "target": target,
        "ok": code == 0 and not changed and not leaked,
        "returncode": code,
        "output": output,
        "effects": list(labels),
        "changed": changed,
        "refused": None,
        "timed_out": timed_out,
        "leaked": leaked,
    }


def main(argv: Sequence[str] | None = None) -> int:
    """CLI: exit 0 green, 1 red, timed out or the tree changed, 2 refused (never
    run), 14 a time limit config/project.json gets wrong, 130 interrupted."""
    ap = argparse.ArgumentParser(
        description="Run a read-only make target as a gate and report pass/fail."
    )
    ap.add_argument("target", help="make target (e.g. verify, check, lint, test)")
    ap.add_argument("--json", action="store_true", help="emit the result as JSON")
    ap.add_argument("--dir", default=None, help="run in this directory (default: cwd)")
    ap.add_argument(
        "--timeout",
        type=int,
        help="seconds before every process make started is ended (default: "
        "config/project.json make_targets.gate_timeout_seconds)",
    )
    ap.add_argument(
        "--make-arg",
        action="append",
        default=[],
        dest="make_args",
        metavar="NAME=VALUE",
        help="extra make variable, repeatable (e.g. PY=.venv/bin/python)",
    )
    args = ap.parse_args(argv)

    if not is_safe_target(args.target):
        return report(
            ExitCode.USAGE,
            "run_make_target: not a make target token",
            repr(args.target),
            "name one target `make help` lists",
        )
    if args.timeout is not None and args.timeout < 1:
        return report(
            ExitCode.USAGE,
            "run_make_target: --timeout must be 1 or more seconds",
            "--timeout %d" % args.timeout,
            "pass a whole number of seconds, or leave it out to use "
            "config/project.json make_targets.gate_timeout_seconds",
        )
    root = os.path.abspath(args.dir or os.getcwd())
    timeout: int | None = args.timeout
    grace: int | None = None
    try:
        timeout, grace = gate_limits(config_loader.read(root, _MANIFEST), timeout)
    except (config_loader.WrongValue, config_loader.NotSet):
        # resolve has written one stderr line per key at fault.
        return report(
            ExitCode.CONFIG,
            "run_make_target: the gate's time limit cannot be used",
            "config/project.json make_targets",
            "correct each key the lines above name, then run it again",
        )
    except (config_loader.ConfigAbsent, config_loader.ConfigUnreadable):
        # Left to run_target, whose refusal names the manifest and why the
        # make_targets policy is unknown, before anything runs.
        pass
    try:
        result = run_target(
            args.target,
            cwd=root,
            timeout=timeout,
            extra=args.make_args,
            grace=grace,
        )
    except KeyboardInterrupt:
        return report(
            ExitCode.INTERRUPTED,
            "run_make_target: interrupted",
            "`make %s`, whose processes were ended" % args.target,
            "run the gate again; a partial run is not a verdict",
        )
    if args.json:
        json.dump(result, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(str(result["output"]))
        verdict = (
            "REFUSED" if result["refused"] else ("PASS" if result["ok"] else "FAIL")
        )
        sys.stdout.write(
            "\nrun_make_target: `make %s` [%s] -> %s (rc=%s)\n"
            % (
                result["target"],
                ",".join(result["effects"]),  # type: ignore[arg-type]
                verdict,
                result["returncode"],
            )
        )
    if result["refused"]:
        return report(
            ExitCode.USAGE,
            "run_make_target: refused, and make was never run",
            "`make %s`: %s" % (result["target"], result["refused"]),
            "run a target config/project.json `make_targets.gate_effects` allows",
        )
    if result["ok"]:
        return ExitCode.SUCCESS
    if result["timed_out"]:
        return report(
            ExitCode.FAILURE,
            "run_make_target: the gate timed out, and every process in make's "
            "session was ended",
            "`make %s` after %d s (--timeout, else config/project.json "
            "make_targets.gate_timeout_seconds)" % (result["target"], timeout or 0),
            "if the output above was still progressing, raise --timeout or "
            "make_targets.gate_timeout_seconds; otherwise find the step that hung "
            "in the output above",
        )
    if result["leaked"] and result["returncode"] == 0 and not result["changed"]:
        return report(
            ExitCode.FAILURE,
            "run_make_target: the gate is red because the target leaked a process",
            "`make %s` exited 0 and left %s running"
            % (result["target"], "; ".join(result["leaked"])),  # type: ignore[arg-type]
            "make the target stop every process it starts before it exits; "
            "these were ended",
        )
    return report(
        ExitCode.FAILURE,
        "run_make_target: the gate is red",
        "`make %s` (rc=%s%s)"
        % (
            result["target"],
            result["returncode"],
            ", and it changed the tree" if result["changed"] else "",
        ),
        "read the output above, fix what it names and run it again",
    )


if __name__ == "__main__":
    finish(main())
