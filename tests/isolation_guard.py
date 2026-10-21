"""
title: isolation guard — a test reaches the network, the disk and the stores only as its tier allows
summary: Judges each reach a test makes against config/project.json `tests.isolation`, read through scripts/config_loader.py. A tier has a rule on three axes — network (none, loopback, any), writes (temp, any) and stores (temp, any) — and the closest tier marker on a test picks the rule; a test with none that names a configured tier gets the strictest value on every axis. `install` adds one Python audit hook per process, active only while `begin` has named a test and phase; it raises IsolationError, which is not an OSError, at the reach itself, and `end` returns every violation of the phase, so tests/conftest.py fails a test whose code caught the error. `classify` is the judgement: a file created, changed or removed outside the temp roots (an open for writing, rename, remove, rmdir, mkdir, truncate, rmtree, a link's destination, a change of mode, owner, flags, times or an extended attribute, judged at the link and at what it points to unless the caller is shutil's own copy saying it stays on the link, and an AF_UNIX socket bound to a path; a bytecode file in a `__pycache__` and the null device aside), a socket connect, sendto or sendmsg that leaves the tier's network, a sqlite database opened outside the roots (a `file:` name judged both as a URI and as a file of that name in the working directory, because the event does not say which sqlite reads), and an open in any mode of a listed store. A root that holds the checkout leaves the checkout outside it: of the roots and the checkout, the deepest that holds a path decides. An exemption is config only, per axis and node id, with a reason; `unused_exemptions` names one whose test ran and reached nothing on its axis. `copy_store` copies a listed store with its -wal, -shm and -journal siblings into a test's own directory. `scratch_root` reads the test scratch root, config/project.json `tests.scratch_root` or KEEL_TEST_SCRATCH over it, with `~` expanded, and refuses one that is relative, has a `..` part, or sits under the system temporary directory (`system_tempdir`, computed with TMPDIR, TEMP and TMP removed) or inside the checkout, naming the key; `choose_scratch` picks the session's root: KEEL_TEST_SCRATCH when set; else `tests.memory_scratch_root` with `-<uid>` appended, held to the same refusals with its parent resolved and its last part not (a link another user plants at the configured name is never followed) and a trailing separator dropped, when its parent exists and is not writable by others without the sticky bit, its file system has `tests.memory_scratch_min_free_mb` megabytes free, and the directory is this user's with mode 0700 (made so, whatever the umask, when absent); else `tests.scratch_root`, with a note saying why memory was passed over. `point_temp_at` makes the root and points tempfile, TMPDIR, KEEL_TEST_SCRATCH (so a nested session inherits the root) and GIT_CEILING_DIRECTORIES at it, and a second call changes nothing. Not caught, because no audit event carries it: a write by a child process, a C extension's own file or socket calls, a FIFO or device node (os.mkfifo and os.mknod raise no event), and the directory an os.open with a relative path and a dir_fd lands in (the open event has no dir_fd, so the path is judged against the working directory). A name lookup is not judged, by choice: library code looks names up without reaching anywhere, and the connect that follows is judged.
effect: writes
rerun: fixed-point
rerun_proof: test:tests/unit/test_isolation_guard.py
"""

import contextlib
import ipaddress
import os
import shutil
import socket
import stat
import sys
import tempfile
import threading
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

_SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import config_loader  # noqa: E402

ConfigError = config_loader.ConfigError

# Each axis's values, strictest first: the strictest rule is derived from here.
VALUES = {
    "network": ("none", "loopback", "any"),
    "writes": ("temp", "any"),
    "stores": ("temp", "any"),
}
AXES = ("network", "writes", "stores")
_KEY = "tests.isolation"
# The keys that let a test reach past the strictest rule: a tier's `any` and a
# named exemption. The limits guide's waiver table names each, held there by
# tests/integration/test_doc_drift.py.
WAIVERS = (_KEY + ".tiers", _KEY + ".exempt")
_UNMARKED = "(none)"
# A store's sqlite siblings: a copy without its write-ahead log loses commits.
_SIBLINGS = ("", "-wal", "-shm", "-journal")
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
_PYCACHE = "__pycache__"
_BYTECODE = ".pyc"
# The events by which the interpreter, or pytest's assertion rewriter, writes
# a bytecode file: a temporary twin opened, renamed over the file, or removed
# when the write fails.
_BYTECODE_EVENTS = frozenset(("open", "os.rename", "os.remove"))
# A metadata change, mapped to the position of its dir_fd argument (None:
# the call takes none). None of these events says whether the call follows a
# link, so each is judged at the link and at what it points to, unless its
# caller is one of _LINK_AWARE_CALLERS and says it stays on the link.
_METADATA_EVENTS = {
    "os.chflags": None,
    "os.chmod": 2,
    "os.chown": 3,
    "os.removexattr": None,
    "os.setxattr": None,
    "os.utime": 3,
}
# The stdlib callers that hold, in a local, whether their metadata call
# follows a link, with that local's name (CPython 3.10 and 3.11):
# shutil.copytree(symlinks=True) copies a link's own times and extended
# attributes through these two, and a test that copies a tree holding a link
# that points outside must not be refused for it. An absent name or local
# leaves both ends judged.
_LINK_AWARE_CALLERS = (
    (shutil.copystat, "follow"),
    (getattr(shutil, "_copyxattr", None), "follow_symlinks"),
)
# The socket events that send to an address; a bind is judged as a write.
_SEND_EVENTS = frozenset(("socket.connect", "socket.sendmsg", "socket.sendto"))
_ENTRY_EVENTS = frozenset(
    (
        "os.remove",
        "os.rmdir",
        "os.mkdir",
        "os.rename",
        "os.symlink",
        "os.link",
        "shutil.rmtree",
    )
)
_JUDGED = (
    _ENTRY_EVENTS
    | _SEND_EVENTS
    | frozenset(_METADATA_EVENTS)
    | frozenset(("open", "os.truncate", "socket.bind", "sqlite3.connect"))
)


class IsolationError(Exception):
    """A test reached outside its tier. Not an OSError, so the `except OSError`
    a test wraps round a connect or an open does not swallow it."""


class StoreError(Exception):
    """A store copy was asked for a store the config does not list, or one
    that is not there."""


@dataclass(frozen=True)
class TierRule:
    """One tier's rule: its name and its value on each axis."""

    tier: str
    network: str
    writes: str
    stores: str


STRICTEST = TierRule(_UNMARKED, *(VALUES[axis][0] for axis in AXES))


@dataclass(frozen=True)
class Policy:
    """`tiers`: tier -> TierRule; `exempt`: axis -> {node id: reason};
    `stores`: the listed stores' real paths; `roots`: the real paths a test
    may write under before pytest's basetemp is added; `fenced`: the real
    paths that stay outside a root that holds them, the checkout's."""

    tiers: Dict[str, TierRule]
    exempt: Dict[str, Dict[str, str]]
    stores: Tuple[str, ...]
    roots: Tuple[str, ...]
    fenced: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Violation:
    """One reach outside a rule: the audit event, the resolved target, the
    axis and the rule's value on it, and the test, phase and tier it was in."""

    event: str
    target: str
    axis: str
    value: str
    nodeid: str = ""
    phase: str = ""
    tier: str = ""

    def message(self) -> str:
        return (
            "%s [%s] reached outside its tier '%s': %s %s (%s=%s). Use tmp_path or "
            "the store_copy fixture; or exempt it with a reason in "
            'config/project.json %s.exempt.%s."%s"'
            % (
                self.nodeid,
                self.phase,
                self.tier,
                self.event,
                self.target,
                self.axis,
                self.value,
                _KEY,
                self.axis,
                self.nodeid,
            )
        )


# --- the policy --------------------------------------------------------------


def _wrong(name: str, shown: str, accepted: str) -> config_loader.WrongValue:
    """The loader's refusal of *name*, whose value reads *shown*."""
    return config_loader.WrongValue(
        config_loader.CONFIG_FILE,
        [
            "%s: %s is %s; accepted: %s"
            % (config_loader.CONFIG_FILE, name, shown, accepted)
        ],
    )


def _tiers(raw: Dict[str, object]) -> Dict[str, TierRule]:
    out = {}
    for tier in sorted(raw):
        name = "%s.tiers.%s" % (_KEY, tier)
        rule = raw[tier]
        if not isinstance(rule, dict):
            raise _wrong(name, repr(rule), "an object holding %s" % ", ".join(AXES))
        unknown = sorted(set(rule) - set(AXES))
        if unknown:
            raise _wrong(
                name + "." + unknown[0],
                repr(rule[unknown[0]]),
                "no key: the axes are %s" % ", ".join(AXES),
            )
        for axis in AXES:
            accepted = "one of %s" % ", ".join(VALUES[axis])
            if axis not in rule:
                raise _wrong(name + "." + axis, "absent", accepted)
            if rule[axis] not in VALUES[axis]:
                raise _wrong(name + "." + axis, repr(rule[axis]), accepted)
        out[tier] = TierRule(tier, rule["network"], rule["writes"], rule["stores"])
    return out


def _exempt(raw: Dict[str, object]) -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {axis: {} for axis in AXES}
    for axis in sorted(raw):
        name = "%s.exempt.%s" % (_KEY, axis)
        table = raw[axis]
        if axis not in AXES:
            raise _wrong(name, repr(table), "no key: the axes are %s" % ", ".join(AXES))
        if not isinstance(table, dict):
            raise _wrong(
                name, repr(table), "an object mapping a test's node id to a reason"
            )
        for nodeid in sorted(table):
            reason = table[nodeid]
            if not isinstance(reason, str) or not reason.strip():
                raise _wrong(
                    '%s."%s"' % (name, nodeid),
                    repr(reason),
                    "a reason the test may reach outside its tier, not blank",
                )
            out[axis][nodeid] = reason
    return out


def _stores(root: str, raw: Sequence[str]) -> Tuple[str, ...]:
    out = []
    for i, store in enumerate(raw):
        if not store.strip():
            raise _wrong("%s.stores[%d]" % (_KEY, i), repr(store), "a path, not blank")
        out.append(os.path.realpath(os.path.join(root, store)))
    return tuple(out)


def load_policy(root: str) -> Policy:
    """The policy *root*'s config/project.json declares. Raises
    config_loader.ConfigError, naming the key, for a value it cannot use."""
    keys = config_loader.rows(
        ("tests", "isolation", "exempt"),
        ("tests", "isolation", "stores"),
        ("tests", "isolation", "tiers"),
    )
    values = config_loader.resolve(
        config_loader.read(root), keys, config_loader.CONFIG_FILE
    )
    return Policy(
        tiers=_tiers(values[("tests", "isolation", "tiers")]),
        exempt=_exempt(values[("tests", "isolation", "exempt")]),
        stores=_stores(root, values[("tests", "isolation", "stores")]),
        roots=(os.path.realpath(tempfile.gettempdir()),),
        # A scratch root may hold the checkout (KEEL_TEST_SCRATCH=$HOME, or a
        # nested session's inherited root); the checkout stays outside it.
        fenced=(os.path.realpath(root),),
    )


# --- the scratch root --------------------------------------------------------

SCRATCH_KEY = ("tests", "scratch_root")
# The variables tempfile reads before it falls back to the platform's own
# directory, in the order it reads them.
_TEMP_VARS = ("TMPDIR", "TEMP", "TMP")
_CEILINGS = "GIT_CEILING_DIRECTORIES"


def system_tempdir() -> str:
    """The real path of the directory tempfile picks when no TMPDIR, TEMP or
    TMP moves it. Called once, from tests/conftest.py at import, before any
    test phase is judged: tempfile's own choice writes a probe file there."""
    saved = {name: os.environ.pop(name) for name in _TEMP_VARS if name in os.environ}
    before = tempfile.tempdir
    tempfile.tempdir = None
    try:
        return os.path.realpath(tempfile.gettempdir())
    finally:
        tempfile.tempdir = before
        os.environ.update(saved)


def _refused(name: str, value: str, why: str) -> config_loader.WrongValue:
    return config_loader.WrongValue(
        config_loader.CONFIG_FILE,
        [
            "%s is %r: %s; accepted: an absolute path (`~` allowed) outside the "
            "system temporary directory and the checkout" % (name, value, why)
        ],
    )


def scratch_root(
    root: str, environ: Optional[Dict[str, str]] = None, systemp: Optional[str] = None
) -> str:
    """The real path test scratch lives under: *root*'s config/project.json
    `tests.scratch_root`, or the variable its row names when *environ*
    (os.environ when None) sets it, with `~` expanded. *systemp* is the system
    temporary directory (system_tempdir() when None). Raises ConfigError
    naming the key, and the variable when it set the value, for a path that is
    relative, has a `..` part, or lies under *systemp* or inside *root*.
    Creates nothing."""
    environ = os.environ if environ is None else environ
    (key,) = config_loader.rows(SCRATCH_KEY)
    dotted = ".".join(SCRATCH_KEY)
    from_env = key.env is not None and config_loader.env(key.env, environ) is not None
    name = (
        "%s, which sets %s" % (key.env, dotted)
        if from_env
        else ("config/project.json %s" % dotted)
    )
    try:
        raw = config_loader.resolve(
            config_loader.read(root), (key,), config_loader.CONFIG_FILE, environ
        )[SCRATCH_KEY]
    except config_loader.WrongValue as exc:
        if not from_env:
            raise
        # The loader names the variable alone; the key is what a reader of
        # the settings reference looks up.
        raise config_loader.WrongValue(
            exc.path,
            ["%s (%s sets %s)" % (line, key.env, dotted) for line in exc.lines],
        ) from exc
    systemp = system_tempdir() if systemp is None else systemp
    return _safe_root(name, raw, root, systemp)


def _safe_root(name: str, raw: str, root: str, systemp: str) -> str:
    """The real path of *raw* with `~` expanded; raises ConfigError naming
    *name* when it is relative or lies under *systemp* or inside *root*."""
    expanded = os.path.expanduser(raw)
    if not os.path.isabs(expanded):
        raise _refused(name, raw, "it is relative, so it would land in the checkout")
    return _placed(name, raw, os.path.realpath(expanded), root, systemp)


def _placed(name: str, raw: str, real: str, root: str, systemp: str) -> str:
    """*real*, the resolved place *raw* names; raises ConfigError naming
    *name* when it lies under *systemp* or inside *root*."""
    # The system temporary directory is shared with every other program, and
    # a failed session's kept directories pile up there unseen; a memory root
    # is a directory of the project's own, with a free-space floor.
    if _under(real, (systemp,)):
        raise _refused(
            name, raw, "it is under the system temporary directory %s" % systemp
        )
    checkout = os.path.realpath(root)
    # The tree walkers (checks, corpus build, gate tests) do not read
    # .gitignore, so a kept failure's directory would be judged as source.
    if _under(real, (checkout,)):
        raise _refused(name, raw, "it is inside the checkout %s" % checkout)
    return real


MEMORY_KEY = ("tests", "memory_scratch_root")
FLOOR_KEY = ("tests", "memory_scratch_min_free_mb")
_MB = 1024 * 1024


@dataclass(frozen=True)
class Scratch:
    """The root test scratch lives under; the medium it came from, `variable`
    (KEEL_TEST_SCRATCH), `memory` (tests.memory_scratch_root) or `disk`
    (tests.scratch_root); and, for `disk`, why the memory root was passed
    over."""

    path: str
    medium: str
    note: str


def choose_scratch(
    root: str, environ: Optional[Dict[str, str]] = None, systemp: Optional[str] = None
) -> Scratch:
    """The scratch root a session uses. The variable tests.scratch_root's row
    names wins when *environ* sets it. Otherwise the memory root,
    tests.memory_scratch_root with `-<uid>` appended, when its parent exists
    and is not writable by others without the sticky bit, its file system has
    tests.memory_scratch_min_free_mb free, and the directory is this user's
    with mode 0700 (made so when absent). Otherwise tests.scratch_root, which is resolved and
    judged on every path so a refused disk root is never hidden by memory.
    Raises ConfigError for a refused root or floor; a memory root this host
    cannot hold is not an error, and the note says why it was passed over."""
    environ = os.environ if environ is None else environ
    systemp = system_tempdir() if systemp is None else systemp
    disk = scratch_root(root, environ, systemp)
    (key,) = config_loader.rows(SCRATCH_KEY)
    if key.env is not None and config_loader.env(key.env, environ) is not None:
        return Scratch(disk, "variable", "")
    config = config_loader.read(root)
    rows = config_loader.rows(MEMORY_KEY)
    raw = config_loader.resolve(config, rows, config_loader.CONFIG_FILE, environ)[
        MEMORY_KEY
    ]
    name = "config/project.json %s" % ".".join(MEMORY_KEY)
    if raw is None:
        return Scratch(disk, "disk", "%s is null or absent" % name)
    floor = config_loader.resolve(
        config, config_loader.rows(FLOOR_KEY), config_loader.CONFIG_FILE, environ
    )[FLOOR_KEY]
    expanded = os.path.expanduser(raw)
    if not os.path.isabs(expanded):
        raise _refused(name, raw, "it is relative, so it would land in the checkout")
    # A trailing separator dropped, so `/dev/shm/x/` names `/dev/shm/x`.
    expanded = os.path.normpath(expanded)
    # The parent resolved, the last part not: the session uses only the
    # `-<uid>` name, so a link another user plants at the configured name is
    # never followed and cannot make the root refused for everyone.
    parent = os.path.realpath(os.path.dirname(expanded))
    base = _placed(
        name, raw, os.path.join(parent, os.path.basename(expanded)), root, systemp
    )
    if not os.path.isdir(parent):
        return Scratch(disk, "disk", "%s does not exist on this host" % parent)
    mode = os.stat(parent).st_mode
    # Where others may write without the sticky bit, they may rename the
    # checked directory away and put their own in its place.
    if mode & 0o022 and not mode & stat.S_ISVTX:
        return Scratch(
            disk,
            "disk",
            "%s is writable by other users without the sticky bit" % parent,
        )
    getuid = getattr(os, "getuid", None)
    if getuid is None:
        return Scratch(disk, "disk", "this platform has no user id to fence %s" % name)
    usage = os.statvfs(parent)
    free = usage.f_bavail * usage.f_frsize // _MB
    if free < floor:
        return Scratch(
            disk,
            "disk",
            "%s has %d MB free, under config/project.json %s %d"
            % (parent, free, ".".join(FLOOR_KEY), floor),
        )
    uid = getuid()
    mine = "%s-%d" % (base, uid)
    try:
        os.mkdir(mine, 0o700)
        # The umask can narrow the mode mkdir gives; the directory is new
        # and this user's, so it is set whole.
        os.chmod(mine, 0o700)
    except FileExistsError:
        pass
    except OSError as exc:
        return Scratch(disk, "disk", "%s could not be made: %s" % (mine, exc))
    held = os.lstat(mine)
    # Shared memory is writable by every user: a directory another user made,
    # or one they may enter, could be read or swapped under the session; one
    # the owner cannot write would fail the first test that makes a file.
    if (
        not stat.S_ISDIR(held.st_mode)
        or held.st_uid != uid
        or stat.S_IMODE(held.st_mode) != 0o700
    ):
        return Scratch(
            disk,
            "disk",
            "%s is not a directory this user owns with mode 0700" % mine,
        )
    return Scratch(mine, "memory", "")


def point_temp_at(path: str, environ: Dict[str, str]) -> None:
    """Create *path* and make it the temporary directory of this process and
    every child *environ* is handed to: tempfile's, TMPDIR's, and so pytest's
    basetemp. The scratch root's variable is set to *path* too, so a nested
    session inherits this root instead of reading its own project's config.
    *path* joins GIT_CEILING_DIRECTORIES, after any ceiling already there, so
    git started in scratch never finds a repository above it. A second call
    over the same *path* changes nothing."""
    os.makedirs(path, exist_ok=True)
    tempfile.tempdir = path
    environ["TMPDIR"] = path
    (key,) = config_loader.rows(SCRATCH_KEY)
    if key.env is not None:
        environ[key.env] = path
    # Kept verbatim: an empty entry there tells git to stop resolving the
    # symlinks of the entries after it.
    ceilings = environ.get(_CEILINGS, "")
    if path not in ceilings.split(os.pathsep):
        environ[_CEILINGS] = ceilings + os.pathsep + path if ceilings else path


def rule_for(policy: Policy, marker_names: Iterable[str]) -> TierRule:
    """The rule of the first marker, closest first, that names a configured
    tier; the strictest rule when none does."""
    for name in marker_names:
        if name in policy.tiers:
            return policy.tiers[name]
    return STRICTEST


# --- the judgement -----------------------------------------------------------


def _under(path: str, roots: Iterable[str]) -> bool:
    for root in roots:
        if path == root or path.startswith(root.rstrip(os.sep) + os.sep):
            return True
    return False


def _depth(path: str, roots: Iterable[str]) -> int:
    """The length of the deepest of *roots* that holds *path*; -1 for none."""
    return max((len(root) for root in roots if _under(path, (root,))), default=-1)


def _in_scratch(path: str, roots: Sequence[str], fenced: Sequence[str]) -> bool:
    """Whether *path* is under a root and not under a fenced path deeper than
    that root. A fenced path the same as a root wins."""
    return _depth(path, roots) > _depth(path, fenced)


def _is_store(path: str, stores: Iterable[str]) -> bool:
    return any(
        path == store + suffix or path.startswith(store + os.sep)
        for store in stores
        for suffix in _SIBLINGS
    )


def _text(path: object) -> Optional[str]:
    """*path* as text, or None for a file descriptor."""
    if isinstance(path, int):
        return None
    return os.fsdecode(os.fspath(path))


def _base(path: str, dir_fd: object, fd_dir: str) -> Optional[str]:
    """The absolute form of *path*, read against *dir_fd* when it is set; None
    when the descriptor cannot be read back."""
    if isinstance(dir_fd, int) and dir_fd >= 0 and not os.path.isabs(path):
        try:
            directory = os.readlink(os.path.join(fd_dir, str(dir_fd)))
        except OSError:
            return None
        return os.path.join(directory, path)
    try:
        return os.path.abspath(path)
    except OSError:
        # The working directory is gone: the path cannot be placed, so it is
        # judged as outside every root rather than allowed.
        return os.path.join("<unreadable cwd>", path)


def _followed(
    path: str, dir_fd: object = None, fd_dir: str = "/proc/self/fd"
) -> Optional[str]:
    """Where a write through *path* lands: every link followed."""
    base = _base(path, dir_fd, fd_dir)
    return None if base is None else os.path.realpath(base)


def _entry(
    path: str, dir_fd: object = None, fd_dir: str = "/proc/self/fd"
) -> Optional[str]:
    """The directory entry *path* names: its parent's links followed, never
    its own, so removing a link is judged where the link is."""
    base = _base(path, dir_fd, fd_dir)
    if base is None:
        return None
    base = os.path.normpath(base)
    return os.path.join(os.path.realpath(os.path.dirname(base)), os.path.basename(base))


def _bytecode_name(name: str) -> bool:
    """A bytecode file's name, or its temporary twin's: the name, a dot and
    the writer's decimal id."""
    if name.endswith(_BYTECODE):
        return True
    head, dot, tail = name.rpartition(".")
    return bool(dot) and head.endswith(_BYTECODE) and tail.isdigit()


def _cache_write(event: str, target: str) -> bool:
    if event == "os.mkdir":
        return os.path.basename(target) == _PYCACHE
    return (
        event in _BYTECODE_EVENTS
        and os.path.basename(os.path.dirname(target)) == _PYCACHE
        and _bytecode_name(os.path.basename(target))
    )


def _writes(event: str, args: tuple, fd_dir: str, follows: bool = True) -> List[str]:
    """The resolved targets a tree-changing event writes; a metadata change
    whose caller stays on a link (*follows* False) writes the link alone."""
    if event == "open":
        path, mode, flags = args[0], args[1], args[2]
        writing = (
            any(c in mode for c in "wax+")
            if isinstance(mode, str)
            else bool(flags & _WRITE_FLAGS)
        )
        text = _text(path)
        if not writing or text is None:
            return []
        return [t for t in (_followed(text),) if t is not None]
    if event == "os.truncate":
        text = _text(args[0])
        return [] if text is None else [t for t in (_followed(text),) if t is not None]
    if event in _METADATA_EVENTS:
        text = _text(args[0])
        if text is None:
            return []
        at = _METADATA_EVENTS[event]
        dir_fd = args[at] if at is not None and len(args) > at else None
        ends = [_entry(text, dir_fd, fd_dir)]
        if follows:
            ends.append(_followed(text, dir_fd, fd_dir))
        return sorted({t for t in ends if t is not None})
    if event == "socket.bind":
        sock, address = args[0], args[1]
        if getattr(sock, "family", None) != getattr(socket, "AF_UNIX", None):
            return []
        text = _text(address) if isinstance(address, (str, bytes)) else None
        # An abstract name (a leading NUL) or an empty one makes no file.
        if text is None or not text or text.startswith("\0"):
            return []
        return [t for t in (_entry(text),) if t is not None]
    if event == "os.rename":
        pairs = [(args[0], args[2]), (args[1], args[3])]
    elif event == "os.symlink":
        pairs = [(args[1], args[2])]
    elif event == "os.link":
        pairs = [(args[1], args[3])]
    else:
        pairs = [(args[0], args[-1] if len(args) > 1 else None)]
    out = []
    for path, dir_fd in pairs:
        text = _text(path)
        if text is None:
            continue
        target = _entry(text, dir_fd, fd_dir)
        if target is not None:
            out.append(target)
    return out


def _loopback_host(host: object) -> bool:
    if not isinstance(host, str):
        return False
    if host == "localhost":
        return True
    try:
        address = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return False
    mapped = getattr(address, "ipv4_mapped", None)
    return bool(address.is_loopback or (mapped is not None and mapped.is_loopback))


def _network(
    event: str,
    args: tuple,
    rule: TierRule,
    roots: Sequence[str],
    fenced: Sequence[str] = (),
) -> Optional[str]:
    """The target a socket event reaches outside *rule*, else None."""
    sock, address = args[0], args[1]
    if event == "socket.sendmsg" and address is None:
        # A connected socket, whose connect was judged, or one end of a
        # socketpair, whose peer is this process.
        return None
    family = getattr(sock, "family", None)
    if family == getattr(socket, "AF_UNIX", None):
        text = _text(address) if isinstance(address, (str, bytes)) else None
        if text is None or text.startswith("\0") or not text:
            return repr(address)
        target = _followed(text)
        return (
            None
            if target is not None and _in_scratch(target, roots, fenced)
            else (target or text)
        )
    if rule.network == "loopback" and family in (socket.AF_INET, socket.AF_INET6):
        host = address[0] if isinstance(address, tuple) and address else None
        if _loopback_host(host):
            return None
    return repr(address)


def _databases(name: object) -> List[str]:
    """The files a sqlite connect may open; none for an in-memory database.
    A `file:` name is a URI only under uri=True, which the event does not
    carry, so it is judged both as the URI's file and as the literal name
    sqlite opens in the working directory without it."""
    text = _text(name)
    if text is None or text in ("", ":memory:"):
        return []
    found = []
    if text.startswith("file:"):
        parts = urllib.parse.urlsplit(text)
        query = urllib.parse.parse_qs(parts.query)
        path = urllib.parse.unquote(parts.path)
        if "memory" not in query.get("mode", []) and path not in ("", ":memory:"):
            found.append(_followed(path))
    found.append(_followed(text))
    return [t for t in found if t is not None]


def classify(
    event: str,
    args: tuple,
    rule: TierRule,
    roots: Sequence[str],
    stores: Sequence[str] = (),
    readable: Sequence[str] = (),
    fd_dir: str = "/proc/self/fd",
    fenced: Sequence[str] = (),
    follows: bool = True,
) -> Optional[Violation]:
    """The first reach *event* with *args* makes outside *rule*, or None.
    *roots*, *stores* and *fenced* are real paths; a path under a fenced one
    is outside a root that holds it; a store in *readable* may be opened for
    reading; *follows* False says a metadata change stays on a link."""
    if event not in _JUDGED:
        return None
    if event in _SEND_EVENTS:
        if rule.network == "any":
            return None
        target = _network(event, args, rule, roots, fenced)
        return (
            None
            if target is None
            else Violation(event, target, "network", rule.network)
        )
    if event == "sqlite3.connect":
        if rule.stores == "any":
            return None
        for target in _databases(args[0]):
            if _is_store(target, stores) or not _in_scratch(target, roots, fenced):
                return Violation(event, target, "stores", rule.stores)
        return None
    if event == "open" and rule.stores != "any":
        text = _text(args[0])
        target = None if text is None else _followed(text)
        if target is not None and _is_store(target, stores):
            reading = not _writes(event, args, fd_dir)
            if not (reading and _is_store(target, readable)):
                return Violation(event, target, "stores", rule.stores)
    if rule.writes == "any":
        return None
    for target in _writes(event, args, fd_dir, follows):
        if (
            target == os.devnull
            or _cache_write(event, target)
            or _in_scratch(target, roots, fenced)
        ):
            continue
        return Violation(event, target, "writes", rule.writes)
    return None


# --- the hook ----------------------------------------------------------------

_LOCAL = threading.local()
_STATE: Dict[str, object] = {
    "policy": None,
    "roots": (),
    "nodeid": None,
    "phase": None,
    "rule": None,
    "violations": [],
    "seen": set(),
    "used": set(),
    "readable": (),
}


def _caller_follows(frame: Optional[FrameType]) -> bool:
    """False only when *frame* is a caller in _LINK_AWARE_CALLERS whose local
    says its metadata call stays on the link."""
    code = None if frame is None else frame.f_code
    for func, local in _LINK_AWARE_CALLERS:
        if frame is not None and code is getattr(func, "__code__", None):
            return frame.f_locals.get(local) is not False
    return True


def _hook(event: str, args: tuple) -> None:
    if (
        event not in _JUDGED
        or _STATE["nodeid"] is None
        or getattr(_LOCAL, "busy", False)
    ):
        return
    _LOCAL.busy = True
    try:
        policy = _STATE["policy"]
        found = classify(
            event,
            args,
            _STATE["rule"],
            _STATE["roots"],
            policy.stores,
            _STATE["readable"],
            fenced=policy.fenced,
            # The audit hook runs inside the C call, so the frame above it is
            # the Python code that made the call.
            follows=event not in _METADATA_EVENTS or _caller_follows(sys._getframe(1)),
        )
        if found is None:
            return
        nodeid = _STATE["nodeid"]
        if nodeid in policy.exempt[found.axis]:
            _STATE["used"].add((found.axis, nodeid))
            return
        found = Violation(
            found.event,
            found.target,
            found.axis,
            found.value,
            nodeid,
            _STATE["phase"],
            _STATE["rule"].tier,
        )
        _STATE["violations"].append(found)
        raise IsolationError(found.message())
    finally:
        _LOCAL.busy = False


def install(policy: Policy) -> bool:
    """Add the audit hook for *policy*; True on the first call of the process.
    A later call changes nothing and returns False: an audit hook cannot be
    removed, so a second would judge every event twice."""
    if _STATE["policy"] is not None:
        return False
    _STATE["policy"] = policy
    _STATE["roots"] = tuple(policy.roots)
    sys.addaudithook(_hook)
    return True


def add_root(path: str) -> None:
    """Let a test write under *path* as well, such as pytest's basetemp."""
    real = os.path.realpath(str(path))
    if real not in _STATE["roots"]:
        _STATE["roots"] = tuple(_STATE["roots"]) + (real,)


def begin(nodeid: str, phase: str, rule: TierRule) -> None:
    """Judge every reach from here under *rule*, as *nodeid*'s *phase*."""
    _STATE["violations"] = []
    _STATE["rule"] = rule
    _STATE["phase"] = phase
    _STATE["nodeid"] = nodeid
    if phase == "call":
        _STATE["seen"].add(nodeid)


def end() -> List[Violation]:
    """Stop judging; the violations since `begin`."""
    _STATE["nodeid"] = None
    found = list(_STATE["violations"])
    _STATE["violations"] = []
    return found


def unused_line(axis: str, nodeid: str) -> str:
    """The line that names *nodeid*'s exemption on *axis* as unused."""
    return (
        '%s.exempt.%s."%s": the test ran and reached nothing on %s; remove the '
        "exemption from config/project.json" % (_KEY, axis, nodeid, axis)
    )


def unused_exemptions() -> List[str]:
    """One line per exemption whose test ran and reached nothing on its axis."""
    policy = _STATE["policy"]
    if policy is None:
        return []
    return [
        unused_line(axis, nodeid)
        for axis in AXES
        for nodeid in sorted(policy.exempt[axis])
        if nodeid in _STATE["seen"] and (axis, nodeid) not in _STATE["used"]
    ]


@contextlib.contextmanager
def allow_reading(paths: Iterable[str]) -> Iterator[None]:
    """Let *paths*, listed stores, be opened for reading inside the block."""
    before = _STATE["readable"]
    _STATE["readable"] = tuple(paths)
    try:
        yield
    finally:
        _STATE["readable"] = before


def copy_store(policy: Policy, root: str, name: str, dest_dir: str) -> Path:
    """Copy the listed store *name* (relative to *root* or absolute) with its
    siblings into *dest_dir*; the copy's path. A second call over the same
    store leaves *dest_dir* as the first did. Raises StoreError for a store
    the policy does not list or one that is not a file."""
    real = os.path.realpath(os.path.join(root, name))
    if real not in policy.stores:
        raise StoreError(
            "%s is not a store config/project.json %s.stores lists; add it "
            "there to copy it, or open a file of the test's own under tmp_path"
            % (real, _KEY)
        )
    if not os.path.isfile(real):
        raise StoreError(
            "%s is listed in config/project.json %s.stores but is not a file; "
            "create the store, or drop it from the list" % (real, _KEY)
        )
    os.makedirs(dest_dir, exist_ok=True)
    base = os.path.basename(real)
    sources = [real + suffix for suffix in _SIBLINGS]
    with allow_reading(sources):
        for suffix in _SIBLINGS:
            source = real + suffix
            dest = os.path.join(dest_dir, base + suffix)
            if os.path.isfile(source):
                shutil.copy2(source, dest)
            elif os.path.lexists(dest):
                # A sibling the store no longer has must not survive from an
                # earlier copy, or sqlite would replay a stale log.
                os.remove(dest)
    return Path(dest_dir) / base
