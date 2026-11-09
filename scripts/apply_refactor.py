#!/usr/bin/env python3
"""
title: Apply a gated refactor (refactor doer)
kind: script
layer: n/a
summary: Apply a bounded spec as a durable undo-journal transaction under an exclusive nonblocking lock. Recover interrupted targets before reading or planning the next spec; publish raw bytes and modes with fsync, replace and directory fsync; commit only after a green read-only gate. A red gate or apply error restores every original; failed restores retain the journal and raise RollbackError. A corrupt or conflicting journal refuses with journal_conflict. plan_edits enforces the configured agents edit policy, tracked targets, closed spec vocabulary and caller --allow binding before any target write. Gate writes outside planned targets are not restored. Dry-run creates nothing and reports pending recovery. --recover exits after replay or cleanup without reading a spec; human-only --discard-journal --yes abandons evidence without touching targets. Vendor-neutral, stdlib.
effect: writes
rerun: fixed-point
rerun_proof: test:tests/integration/test_idempotence.py
"""

from __future__ import annotations

import argparse
import base64
import binascii
import fcntl
import fnmatch
import hashlib
import json
import os
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from functools import partial
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, NamedTuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config_loader  # noqa: E402 — the one reader of config/project.json
import git_tree  # noqa: E402 — the one definition of what git tracks
import run_make_target  # noqa: E402 — the read-only gate runner; tests patch it here
from exit_codes import ExitCode, finish, report  # noqa: E402

# gate_runner(gate, cwd, timeout) -> (ok, combined_output); a timeout of None
# leaves the limit to config/project.json make_targets.gate_timeout_seconds.
GateRunner = Callable[[str, str, "int | None"], "tuple[bool, str]"]


class RefactorError(Exception):
    """A refactor could not be applied as specified (bad spec / non-unique match).

    Raised BEFORE any file is written, so a malformed spec never leaves a
    half-applied tree.
    """


class RollbackError(Exception):
    """A failed gate's per-file restore left the named files unrestored."""

    def __init__(self, failures: Sequence[tuple[str, OSError]]) -> None:
        self.failures = tuple(failures)
        super().__init__(
            "RollbackError: could not restore "
            + "; ".join("%s (%s)" % (path, exc) for path, exc in self.failures)
        )


# A spec is model-written, so its shape is a closed vocabulary: a key outside
# it is refused rather than ignored, because an ignored key is one the model
# may believe took effect. `gate` is refused by name: see _GATE_KEY.
_SPEC_KEYS = frozenset({"practice", "edits"})
_EDIT_KEYS = frozenset({"file", "find", "replace", "content"})
# The gate is the caller's --gate, never the spec's: a spec that chose its own
# gate would let the model choose its own judge, and `"gate": "none"` once
# applied with no gate at all.
_GATE_KEY = "gate"

_PATHS_KEY = ("agents", "protected_paths")
_NAMES_KEY = ("agents", "protected_names")
_EDITABLE_KEY = ("agents", "editable_names")
_JOURNAL_KEY = ("refactor", "journal_path")
_TEMP_PREFIX = ".refactor-tmp-"
_ACTIVE_JOURNAL: ContextVar[tuple[Path, dict[str, Any]] | None] = ContextVar(
    "refactor_journal", default=None
)

# One rule: (case-folded parts, or a case-folded name as a 1-tuple; the key as
# config/project.json spells it; its reason).
Rule = tuple[tuple[str, ...], str, str]


class EditPolicy(NamedTuple):
    """What an agent edit may not reach, read from config/project.json `agents`.

    Each field is a tuple of rules sorted by key, so the rule a refusal names
    does not depend on the order the file lists them in."""

    protected_paths: tuple[Rule, ...]
    protected_names: tuple[Rule, ...]
    editable_names: tuple[Rule, ...]


def _fold(parts: Sequence[str]) -> tuple[str, ...]:
    # Case-folded because make reads makefile as well as Makefile, and a
    # case-insensitive filesystem opens scripts/x.py as SCRIPTS/x.py: on a
    # case-sensitive one this over-protects a distinct name, the fail-closed side.
    return tuple(part.casefold() for part in parts)


def _rules(mapping: Mapping[str, str], *, split: bool) -> tuple[Rule, ...]:
    return tuple(
        (_fold(PurePosixPath(key).parts) if split else (key.casefold(),), key, reason)
        for key, reason in sorted(mapping.items())
    )


def _covers(rule_parts: tuple[str, ...], parts: tuple[str, ...]) -> bool:
    return parts[: len(rule_parts)] == rule_parts


def load_policy(root: str) -> EditPolicy:
    """The edit policy of the project at *root*, from its config/project.json
    `agents` block through scripts/config_loader.py.

    Raises config_loader.ConfigError when the file or block cannot be used, and
    WrongValue when `protected_paths` leaves config/project.json uncovered: a
    policy that does not protect itself could be edited away by the edit it
    is meant to refuse."""
    loaded = config_loader.read(root)
    values = config_loader.resolve(
        loaded,
        config_loader.rows(_EDITABLE_KEY, _NAMES_KEY, _PATHS_KEY),
        config_loader.CONFIG_FILE,
    )
    policy = EditPolicy(
        protected_paths=_rules(values[_PATHS_KEY], split=True),
        protected_names=_rules(values[_NAMES_KEY], split=False),
        editable_names=_rules(values[_EDITABLE_KEY], split=False),
    )
    own = _fold(PurePosixPath(config_loader.CONFIG_FILE.replace(os.sep, "/")).parts)
    if not any(_covers(parts, own) for parts, _key, _why in policy.protected_paths):
        where = config_loader.CONFIG_FILE
        raise config_loader.WrongValue(
            where,
            [
                "%s: agents.protected_paths covers no path holding %s; accepted: "
                "a map with an entry covering it (such as `config`), so an agent "
                "edit cannot remove the policy itself" % (where, where)
            ],
        )
    return policy


def _named(rules: tuple[Rule, ...], name: str) -> Rule | None:
    """The rule for file *name*: the one spelled exactly as *name* when there
    is one, else the first by key among those whose key, a name or a glob over
    one (`*.test.*`), matches it case-folded."""
    folded = name.casefold()
    # fnmatchcase on folded text, never fnmatch: fnmatch folds case only on a
    # case-insensitive OS, so one policy would protect differently per host.
    matches = [rule for rule in rules if fnmatch.fnmatchcase(folded, rule[0][0])]
    exact = [rule for rule in matches if rule[1] == name]
    candidates = exact or matches
    return candidates[0] if candidates else None


def protected_by(relparts: Sequence[str], policy: EditPolicy) -> tuple[str, str] | None:
    """(the rule key, its reason), as a refusal shows them, that protects the repo-relative path whose
    parts are *relparts*, or None when an agent may edit it.

    A protected name refuses, else an editable name allows, else a protected
    path refuses; the comparison is on case-folded parts only."""
    parts = tuple(relparts)
    if not parts:
        return None
    name = _named(policy.protected_names, parts[-1])
    if name is not None:
        return _rule("agents.protected_names", name[1], name[2])
    if _named(policy.editable_names, parts[-1]) is not None:
        return None
    folded = _fold(parts)
    for rule_parts, key, reason in policy.protected_paths:
        if _covers(rule_parts, folded):
            return _rule("agents.protected_paths", key, reason)
    return None


def _rule(block: str, key: str, reason: str) -> tuple[str, str]:
    """A matched rule as a refusal shows it: its configured key and reason go
    through scripts/config_loader.py `shown`, hidden when either holds an `@`."""
    return (
        "%s.%s" % (block, config_loader.shown(key, bare=True)),
        config_loader.shown(reason, bare=True),
    )


def apply_one(text: str, find: str, replace: str) -> str:
    """Apply a single search/replace to ``text``. ``find`` must occur EXACTLY once
    so a refactor edit is unambiguous; raises RefactorError on zero or many."""
    count = text.count(find)
    if count == 0:
        raise RefactorError("find text not present")
    if count > 1:
        raise RefactorError("find text is ambiguous (%d matches)" % count)
    return text.replace(find, replace, 1)


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _refuse_protected(
    index: int, shown: object, parts: Sequence[str], policy: EditPolicy
) -> None:
    rule = protected_by(parts, policy)
    if rule is not None:
        raise RefactorError(
            "edit %d: %s is protected by %s (%s); an agent edit may not reach "
            "the code that judges it" % (index, shown, rule[0], rule[1])
        )


def _refuse_spec_keys(spec: Mapping[str, object]) -> None:
    if _GATE_KEY in spec:
        raise RefactorError(
            "spec names a gate (%r); the gate is the caller's --gate, never the "
            "spec's" % (spec[_GATE_KEY],)
        )
    unknown = sorted(set(spec) - _SPEC_KEYS)
    if unknown:
        raise RefactorError(
            "spec has unknown key(s) %s; accepted: %s"
            % (", ".join(repr(k) for k in unknown), ", ".join(sorted(_SPEC_KEYS)))
        )


def _refuse_untracked(index: int, shown: str, real_root: str, resolved: str) -> None:
    """Refuse an edit to a file git does not track. The deny list names the
    judges a project ships; what git does not track is judge-shaped by default:
    git's own state (`.git/config` sets core.fsmonitor, which runs inside the
    gate's own `git status`), the toolchain the gate runs (.venv, node_modules)
    and any ignored file. An agent refactors tracked source and nothing else."""
    try:
        known = git_tree.tracked(real_root, [resolved])
    except (git_tree.NoGitError, git_tree.GitFailedError) as exc:
        raise RefactorError(
            "edit %d: %s: git cannot say whether it is tracked (%s); an agent "
            "edits only a file git tracks" % (index, shown, exc)
        ) from exc
    if not known:
        raise RefactorError(
            "edit %d: %s is not a file git tracks; an agent edits only tracked "
            "source, never git's own state, an ignored file or the toolchain "
            "the gate runs" % (index, shown)
        )


def _bound(root: str, allow: Sequence[str] | None) -> frozenset[str] | None:
    """The realpaths of the files *allow* binds the run to, or None for no
    binding (the deny floor alone)."""
    if allow is None:
        return None
    return frozenset(os.path.realpath(os.path.join(root, a)) for a in allow)


def plan_edits(
    spec: dict[str, object],
    root: str,
    allow: Sequence[str] | None = None,
    policy: EditPolicy | None = None,
) -> list[tuple[str, str, str]]:
    """Validate the spec against the tree WITHOUT writing. Returns
    ``[(path, original_text, new_text)]``. Multiple edits to one file compose in
    order. Raises RefactorError on any problem (so callers can dry-run safely),
    and config_loader.ConfigError when *policy* is None and the root's edit
    policy cannot be loaded.

    *allow*, when given, binds the run to those repo-relative files: an edit
    whose realpath is none of theirs is refused, and an empty list refuses
    every edit."""
    _refuse_spec_keys(spec)
    edits = spec.get("edits")
    if not isinstance(edits, list) or not edits:
        raise RefactorError("spec has no 'edits' list")
    if policy is None:
        policy = load_policy(root)
    bound = _bound(root, allow)
    real_root = os.path.realpath(root)
    # Keyed on the resolved path, so `src/m.py` and `./src/m.py` are one file
    # whose edits compose, not two planned from one original, the second
    # write dropping the first.
    originals: dict[str, str] = {}
    working: dict[str, str] = {}
    order: list[str] = []
    for i, e in enumerate(edits):
        if not isinstance(e, dict) or "file" not in e:
            raise RefactorError("edit %d missing 'file'" % i)
        unknown = sorted(set(e) - _EDIT_KEYS)
        if unknown:
            raise RefactorError(
                "edit %d: unknown key %s; accepted: %s"
                % (
                    i,
                    ", ".join(repr(k) for k in unknown),
                    ", ".join(sorted(_EDIT_KEYS)),
                )
            )
        rel = e["file"]
        if not isinstance(rel, str) or not rel:
            raise RefactorError("edit %d: 'file' must be a non-empty string" % i)
        # A spelling, not a location, is judged first: `src/../scripts/x.py`
        # and an absolute path inside the root reach the same files as a plain
        # relative path, so they buy an agent nothing but a way round a rule.
        written = PurePosixPath(rel)
        if os.path.isabs(rel) or ".." in written.parts or not written.parts:
            raise RefactorError(
                "edit %d: %s: a path with '..' or an absolute path is refused"
                % (i, rel)
            )
        # Never write outside the repo root — a spec path must not escape it.
        real_path = os.path.realpath(os.path.join(root, rel))
        if real_path != real_root and not real_path.startswith(real_root + os.sep):
            raise RefactorError("edit %d: path escapes root: %s" % (i, rel))
        resolved = os.path.relpath(real_path, real_root)
        path = os.path.join(root, resolved)
        # Judged as written and again after resolving links, and both must
        # pass: CLAUDE.md is a symlink to AGENT.md, so a link is how an
        # editable name reaches a protected file. Before the existence check,
        # so a new file under a protected directory names its rule.
        _refuse_protected(i, rel, written.parts, policy)
        _refuse_protected(i, rel, PurePosixPath(resolved).parts, policy)
        # The model writes edits[].file, so a caller that names the one chunk
        # it asked about (--allow) takes the choice of file away from it.
        if bound is not None and real_path not in bound:
            raise RefactorError(
                "edit %d: %s is not a file this run was bound to (%s)"
                % (
                    i,
                    rel,
                    " ".join("--allow %s" % a for a in allow or ())
                    or "no --allow file",
                )
            )
        if path not in working:
            if not os.path.isfile(path):
                raise RefactorError("edit %d: file does not exist: %s" % (i, rel))
            # A hard link shares one inode under two names, and realpath sees
            # neither name as the other, so an editable name linked to a
            # protected file would pass both judgements above.
            links = os.stat(path).st_nlink
            if links > 1:
                raise RefactorError(
                    "edit %d: %s has %d hard links; one may be a protected file"
                    % (i, rel, links)
                )
            _refuse_untracked(i, rel, real_root, resolved)
            raw = Path(path).read_bytes()
            _newline(raw)
            originals[path] = working[path] = (
                raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
            )
            order.append(path)
        if "content" in e:  # full-file replacement
            working[path] = str(e["content"])
        elif "find" in e and "replace" in e:
            working[path] = apply_one(working[path], str(e["find"]), str(e["replace"]))
        else:
            raise RefactorError("edit %d needs 'find'+'replace' or 'content'" % i)
    for path in order:
        _newline(working[path].replace("\r\n", "\n").encode("utf-8"))
    return [(p, originals[p], working[p]) for p in order]


def _read_only_gate(gate: str, cwd: str, timeout: int | None) -> tuple[bool, str]:
    """The default gate: scripts/run_make_target.py, as (ok, output).

    A refusal (a target labelled wider than a gate may run, no git, no policy)
    and a green run that changed the tree are both red, so the caller attempts
    per-file restoration; the changed paths are appended so the reader sees why."""
    active = _ACTIVE_JOURNAL.get()
    runner = (
        None
        if active is None
        else partial(_gate_process, path=active[0], journal=active[1])
    )
    res = run_make_target.run_target(gate, cwd, timeout, runner=runner)
    output = str(res["output"])
    changed_value = res.get("changed")
    changed = changed_value if isinstance(changed_value, list) else []
    if changed:
        output += "".join("\nchanged: %s" % path for path in changed)
    return bool(res["ok"]), output


def _gate_process(
    cmd: Sequence[str],
    cwd: str | None,
    timeout: int,
    *,
    path: Path,
    journal: dict[str, Any],
) -> tuple[int, str]:
    """Run the gate on ChildSession, durably recording its live process group."""
    _, grace = run_make_target.gate_limits(config_loader.read(cwd or "."), timeout)
    session = run_make_target.resource_limits.ChildSession(grace)
    reader: run_make_target.resource_limits.PipeReader | None = None
    with run_make_target.resource_limits.supervised(session):
        try:
            # A stop signal between fork and Popen's return would find no make
            # to end, so start_child defers it until session.proc is set,
            # inside this try, so that the KeyboardInterrupt a replayed Ctrl-C
            # raises reaches the except that ends make.
            # The pipe prevents exec until recovery can identify the gate.
            proc = run_make_target.resource_limits.start_child(
                session,
                [
                    "sh",
                    "-c",
                    'read -r release && exec "$@" < /dev/null',
                    "refactor-gate",
                    *cmd,
                ],
                cwd,
                run_make_target.subprocess.PIPE,
                run_make_target.subprocess.STDOUT,
            )
            journal["gate_pgid"] = proc.pid
            _save(path, journal)
            assert proc.stdin is not None  # start_child asks for a pipe
            proc.stdin.write(b"go\n")
            proc.stdin.close()
            assert proc.stdout is not None  # start_child asks for a pipe
            reader = run_make_target.resource_limits.PipeReader(proc.stdout)
            try:
                status = session.wait_exit(run_make_target.time.monotonic() + timeout)
            except run_make_target.resource_limits.ChildReaped:
                # Named, never signalled: make's freed id anchors nothing.
                _alive, leftovers = session.settled()
                listed = (
                    run_make_target.resource_limits.session_members(proc.pid)
                    is not None
                )
                output = run_make_target._make_text(reader, grace)
                raise run_make_target.MakeReaped(
                    output, leftovers, listed=listed, holders=reader.holders
                ) from None
            if status is None:
                session.end()
                output = run_make_target._make_text(reader, grace)
                raise run_make_target.TimedOut(cmd, timeout, output, reader.holders)
            alive, leftovers = session.settled()
            if alive:
                # Listed before they are ended, so the report can name them.
                ended = session.held()
                session.end()
                output = run_make_target._make_text(reader, grace)
                raise run_make_target.LeftRunning(
                    status, output, leftovers, reader.holders, ended=ended
                )
            output = run_make_target._make_text(reader, grace)
            if reader.holders is not None:
                raise run_make_target.OutputHeld(status, output, reader.holders)
            return status, output
        except (
            run_make_target.subprocess.TimeoutExpired,
            run_make_target.LeftRunning,
            run_make_target.OutputHeld,
            run_make_target.MakeReaped,
        ):
            raise
        except BaseException:
            # Any exception leaves make's session with no owner: end it, then
            # let the exception carry on to the caller.
            session.end()
            raise
        finally:
            if session.proc is not None and session.proc.stdin is not None:
                session.proc.stdin.close()
            if reader is not None:
                reader.finish(0)


class JournalConflict(RefactorError):
    """Recovery evidence cannot safely be replayed in this checkout."""


class LockBusy(RefactorError):
    """Another refactor holds the configured journal's lock."""


def _checkpoint(name: str) -> None:
    """An in-process crash injection seam for transaction boundaries."""


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _publish(path: Path, data: bytes, mode: int) -> None:
    """Durably replace *path* with bytes and mode using a sibling temporary."""
    fd, temp = tempfile.mkstemp(prefix=_TEMP_PREFIX, dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            os.fchmod(stream.fileno(), mode)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        _fsync_dir(path.parent)
    finally:
        if os.path.lexists(temp):
            os.unlink(temp)


def _hash(data: bytes | None) -> str | None:
    return None if data is None else hashlib.sha256(data).hexdigest()


def _newline(data: bytes) -> str:
    if b"\r\n" in data:
        rest = data.replace(b"\r\n", b"")
        if b"\n" in rest or b"\r" in rest:
            raise RefactorError("mixed newline conventions are refused")
        return "\r\n"
    if b"\r" in data:
        raise RefactorError("mixed or bare CR newline conventions are refused")
    return "\n"


def _journal_path(root: str) -> Path:
    values = config_loader.resolve(
        config_loader.read(root),
        config_loader.rows(_JOURNAL_KEY),
        config_loader.CONFIG_FILE,
    )
    rel = str(values[_JOURNAL_KEY])
    return Path(root) / rel


def _validate_journal_path(root: str, path: Path) -> None:
    try:
        for candidate in (path, Path(str(path) + ".lock")):
            if candidate.is_symlink() or any(
                p.is_symlink() for p in candidate.parents if p != Path(root)
            ):
                raise ValueError("journal and lock must not traverse symlinks")
            if candidate.exists() and not candidate.is_file():
                raise ValueError("journal and lock must be regular files")
            if git_tree.tracked(
                root, [str(candidate.relative_to(root))]
            ) or not git_tree.is_ignored(root, str(candidate.relative_to(root))):
                raise ValueError("journal and lock must be ignored and untracked")
        ancestor = path.parent
        while not ancestor.exists():
            ancestor = ancestor.parent
        if not ancestor.is_dir() or not os.access(ancestor, os.W_OK | os.X_OK):
            raise ValueError("journal directory is not usable")
    except (ValueError, OSError, git_tree.NoGitError, git_tree.GitFailedError) as exc:
        raise config_loader.WrongValue(
            config_loader.CONFIG_FILE,
            [
                "refactor.journal_path: %s; choose an ignored, untracked writable path"
                % exc
            ],
        ) from exc


@contextmanager
def _locked(path: Path, *, dry: bool = False) -> Iterator[None]:
    lock = Path(str(path) + ".lock")
    if dry and not lock.exists():
        yield
        return
    if not dry:
        missing: list[Path] = []
        parent = path.parent
        while not parent.exists():
            missing.append(parent)
            parent = parent.parent
        for parent in reversed(missing):
            parent.mkdir()
            _fsync_dir(parent.parent)
    with open(lock, "rb" if dry else "a+b") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise LockBusy(
                "%s is locked; retry after the other refactor exits" % lock
            ) from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def _save(path: Path, journal: dict[str, Any]) -> None:
    _publish(
        path,
        (json.dumps(journal, sort_keys=True, separators=(",", ":")) + "\n").encode(),
        0o600,
    )


def _remove(path: Path) -> None:
    path.unlink(missing_ok=True)
    _fsync_dir(path.parent)


def _clean(directory: Path) -> None:
    for path in directory.glob(_TEMP_PREFIX + "*"):
        if path.is_file() or path.is_symlink():
            path.unlink()
    _fsync_dir(directory)


def _group_alive(group: int) -> bool:
    try:
        os.killpg(group, 0)
    except ProcessLookupError:  # noqa: DROP001 -- a missing group is the liveness probe's negative verdict
        return False
    except PermissionError:  # noqa: DROP001 -- an inaccessible group is conservatively still alive
        return True
    return True


def _identity(root: str) -> dict[str, object]:
    git = os.stat(Path(root) / ".git")
    return {"root": root, "git_device": git.st_dev, "git_inode": git.st_ino}


def _journal_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate journal key")
        out[key] = value
    return out


def _validated(path: Path, root: str) -> dict[str, Any]:
    """Read and validate all replay evidence before touching any target."""
    try:
        journal = json.loads(path.read_bytes(), object_pairs_hook=_journal_object)
        if (
            not isinstance(journal, dict)
            or type(journal["schema"]) is not int
            or journal["schema"] != 1
            or journal["checkout"] != _identity(root)
        ):
            raise ValueError("wrong schema or checkout")
        if (
            journal["state"] not in ("prepared", "applied", "committed")
            or journal["temp_prefix"] != _TEMP_PREFIX
        ):
            raise ValueError("invalid state or temporary prefix")
        group = journal.get("gate_pgid")
        if group is not None and (
            type(group) is not int or group <= 0 or _group_alive(group)
        ):
            raise ValueError(
                "gate process group %s is alive or invalid; wait for it to exit" % group
            )
        targets = journal["targets"]
        if not isinstance(targets, list) or not targets:
            raise ValueError("no ordered targets")
        seen: set[str] = set()
        for entry in targets:
            rel = entry["path"]
            if (
                not isinstance(rel, str)
                or not rel
                or rel in seen
                or str(PurePosixPath(rel)) != rel
                or PurePosixPath(rel).is_absolute()
                or ".." in PurePosixPath(rel).parts
            ):
                raise ValueError("invalid or repeated target path")
            target = Path(root) / rel
            if (
                os.path.realpath(target) != str(target)
                or not target.parent.is_dir()
                or target.is_dir()
            ):
                raise ValueError("target is linked or has no directory")
            seen.add(rel)
            raw = (
                None
                if entry["prior"] is None
                else base64.b64decode(entry["prior"], validate=True)
            )
            if _hash(raw) != entry["prior_sha256"]:
                raise ValueError("prior hash mismatch")
            mode = entry["mode"]
            if type(mode) is not int or mode < 0 or mode > 0o7777:
                raise ValueError("invalid saved mode")
            intended = entry["intended_sha256"]
            if intended is not None and (
                not isinstance(intended, str)
                or len(intended) != 64
                or any(c not in "0123456789abcdef" for c in intended)
            ):
                raise ValueError("invalid intended hash")
            current = target.read_bytes() if target.exists() else None
            if _hash(current) not in (entry["prior_sha256"], intended):
                raise ValueError("conflicting bytes at %s" % rel)
        if journal["directories"] != sorted(
            {str(PurePosixPath(e["path"]).parent) for e in targets}
        ):
            raise ValueError("invalid temporary directories")
        return journal
    except (
        KeyError,
        TypeError,
        ValueError,
        OSError,
        binascii.Error,
        OverflowError,
        RecursionError,
    ) as exc:
        raise JournalConflict(
            "%s: %s; preserve the journal and reconcile the evidence before retrying; "
            "a human may abandon recovery with --discard-journal --yes (keeps current targets)"
            % (path, exc)
        ) from exc


def _restore(path: Path, journal: dict[str, Any], root: str) -> list[str]:
    failures: list[tuple[str, OSError]] = []
    for directory in journal["directories"]:
        _clean(Path(root) / directory)
    for entry in journal["targets"]:
        target = Path(root) / entry["path"]
        try:
            if entry["prior"] is None:
                _remove(target)
            else:
                _publish(target, base64.b64decode(entry["prior"]), entry["mode"])
        except OSError as exc:  # noqa: PERF203 -- attempt all restores before raising
            failures.append((str(target), exc))
    if failures:
        raise RollbackError(failures) from failures[0][1]
    _remove(path)
    return [e["path"] for e in journal["targets"]]


def _recover(path: Path, root: str) -> list[str]:
    """Replay originals, or clean a committed journal whose targets all match.

    A committed target must match its recorded intended_sha256. A mismatch
    raises JournalConflict and keeps the journal for reconciliation, without
    restoring targets or accepting a partially restored transaction.
    """
    if not path.exists():
        _clean(path.parent)
        return []
    journal = _validated(path, root)
    if journal["state"] == "committed":
        try:
            for entry in journal["targets"]:
                target = Path(root) / entry["path"]
                current = target.read_bytes() if target.exists() else None
                if _hash(current) != entry["intended_sha256"]:
                    raise ValueError(
                        "committed target differs from intended_sha256 at %s"
                        % entry["path"]
                    )
        except (OSError, ValueError) as exc:
            raise JournalConflict(
                "%s: %s; preserve the journal and reconcile the evidence before retrying; "
                "a human may abandon recovery with --discard-journal --yes (keeps current targets)"
                % (path, exc)
            ) from exc
    _clean(path.parent)
    if journal["state"] == "committed":
        for directory in journal["directories"]:
            _clean(Path(root) / directory)
        _remove(path)
        print("apply_refactor: cleaned committed journal %s" % path, file=sys.stderr)
        return []
    return _restore(path, journal, root)


def _transact(
    spec: dict[str, object],
    planned: list[tuple[str, str, str]],
    root: str,
    path: Path,
    gate: str,
    timeout: int | None,
    gate_runner: GateRunner | None,
) -> dict[str, object]:
    targets: list[dict[str, Any]] = []
    intended_bytes: list[bytes] = []
    for filename, old, new in planned:
        target = Path(filename)
        raw = target.read_bytes()
        newline = _newline(raw)
        if raw.decode("utf-8").replace("\r\n", "\n") != old:
            raise RefactorError("target changed while planning: %s" % filename)
        new = new.replace("\r\n", "\n")
        data = new.replace("\n", newline).encode("utf-8")
        intended_bytes.append(data)
        targets.append(
            {
                "path": str(target.relative_to(root)),
                "prior": base64.b64encode(raw).decode("ascii"),
                "mode": target.stat().st_mode & 0o7777,
                "prior_sha256": _hash(raw),
                "intended_sha256": _hash(data),
            }
        )
    journal: dict[str, Any] = {
        "schema": 1,
        "checkout": _identity(root),
        "state": "prepared",
        "temp_prefix": _TEMP_PREFIX,
        "directories": sorted({str(PurePosixPath(e["path"]).parent) for e in targets}),
        "targets": targets,
    }
    _checkpoint("before_prepared")
    _save(path, journal)
    _checkpoint("prepared")
    try:
        for index, (entry, data) in enumerate(
            zip(targets, intended_bytes, strict=True)
        ):
            _publish(Path(root) / entry["path"], data, entry["mode"])
            _checkpoint("target:%d" % index)
        _checkpoint("targets")
        journal["state"] = "applied"
        _save(path, journal)
        _checkpoint("gate")
        if gate == "none":
            ok, output = True, "(no gate requested)"
        else:
            try:
                token = _ACTIVE_JOURNAL.set((path, journal))
                try:
                    ok, output = (gate_runner or _read_only_gate)(gate, root, timeout)
                finally:
                    _ACTIVE_JOURNAL.reset(token)
                journal.pop("gate_pgid", None)
                _save(path, journal)
            except Exception as exc:  # noqa: BLE001 -- any gate exception is red
                journal.pop("gate_pgid", None)
                ok, output = False, "gate did not complete: %r" % exc
        if ok:
            _checkpoint("green")
            journal["state"] = "committed"
            _save(path, journal)
        else:
            _restore(path, journal, root)
    except RollbackError:
        raise
    except Exception:
        if journal["state"] == "committed":
            journal["state"] = "applied"
            # A publication failure must not bypass restoration of the targets.
            try:
                _save(path, journal)
            finally:
                _restore(path, journal, root)
        else:
            _restore(path, journal, root)
        raise
    if ok:
        _checkpoint("committed")
        _remove(path)
    return {
        "practice": spec.get("practice", ""),
        "gate": gate,
        "applied": ok,
        "rolled_back": not ok,
        "files": [e["path"] for e in targets],
        "gate_output": output,
    }


def _run(
    load: Callable[[], dict[str, object]],
    root: str,
    gate: str,
    timeout: int | None,
    gate_runner: GateRunner | None,
    allow: Sequence[str] | None,
    policy: EditPolicy | None,
    recovered: list[str],
    *,
    dry: bool = False,
) -> dict[str, object]:
    if not gate:
        raise RefactorError("no gate given")
    root = os.path.realpath(root)
    path = _journal_path(root)
    if dry:
        _validate_journal_path(root, path)
        with _locked(path, dry=True):
            pending = path.exists()
            if pending:
                _validated(path, root)
                return {
                    "dry_run": True,
                    "pending_recovery": True,
                    "files": [],
                    "recovered": [],
                }
            dry_spec = load()
            planned = plan_edits(dry_spec, root, allow, policy)
            return {
                "practice": dry_spec.get("practice", ""),
                "dry_run": True,
                "pending_recovery": False,
                "files": [os.path.relpath(p, root) for p, _, _ in planned],
                "recovered": [],
            }
    # Invalid idle proposals leave no transaction artifacts. A pending journal
    # must be replayed before even reading the next proposal.
    spec: dict[str, object] | None = None if path.exists() else load()
    if spec is not None:
        plan_edits(spec, root, allow, policy)
    _validate_journal_path(root, path)
    with _locked(path):
        recovered.extend(_recover(path, root))
        if spec is None:
            spec = load()
        planned = plan_edits(spec, root, allow, policy)
        result = _transact(spec, planned, root, path, gate, timeout, gate_runner)
        result["recovered"] = list(recovered)
        return result


def apply_and_gate(
    spec: dict[str, object],
    root: str,
    gate: str = "verify",
    timeout: int | None = None,
    gate_runner: GateRunner | None = None,
    allow: Sequence[str] | None = None,
    policy: EditPolicy | None = None,
) -> dict[str, object]:
    """Recover, plan, journal and apply one spec under the journal lock.

    Raw prior bytes and modes survive interruption; every pre-commit crash is
    replayed on startup. A green gate commits durably before applied is returned.
    Red gates and apply errors restore all originals; RollbackError retains the
    evidence if any restore fails. Recovery validates the whole journal first;
    JournalConflict preserves conflicting evidence. Gate writes outside planned
    targets are not restored. The result carries recovered paths beside applied.
    """
    return _run(lambda: spec, root, gate, timeout, gate_runner, allow, policy, [])


def _load_spec(path: str | None) -> dict[str, object]:
    text = sys.stdin.read() if path is None or path == "-" else _read(path)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise RefactorError("spec must be a JSON object")
    return data


def _recovery_context(error: Exception, recovered: Sequence[str]) -> str:
    return str(error) + ("; recovered: " + ", ".join(recovered) if recovered else "")


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Recover interrupted edits, then apply one journalled refactor and commit after a green gate."
    )
    ap.add_argument(
        "--spec",
        default="-",
        help="path to the JSON edit spec, or '-' for stdin (default)",
    )
    ap.add_argument(
        "--root", default=".", help="repo root the edit paths are relative to"
    )
    ap.add_argument(
        "--gate",
        default="verify",
        help="Make target to gate on (default: verify); none skips the gate and "
        "is for a human caller only, never an agent",
    )
    ap.add_argument(
        "--allow",
        action="append",
        help="A file this run may edit, repeatable; an edit to any other file is "
        "refused before any write",
    )
    ap.add_argument(
        "--timeout",
        type=int,
        help="gate timeout in seconds (default: config/project.json "
        "make_targets.gate_timeout_seconds)",
    )
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="validate + show the planned files, write nothing",
    )
    mode.add_argument(
        "--recover",
        action="store_true",
        help="recover or clean the journal and exit without reading a spec",
    )
    mode.add_argument(
        "--discard-journal",
        action="store_true",
        help="human only: abandon the journal without touching targets; requires --yes",
    )
    ap.add_argument(
        "--yes",
        action="store_true",
        help="confirm --discard-journal (human only)",
    )
    ap.add_argument("--json", action="store_true", help="emit the result as JSON")
    args = ap.parse_args(argv)
    if not os.path.isdir(args.root):
        return report(
            ExitCode.USAGE,
            "apply_refactor: the root is not an existing directory",
            config_loader.checkout_name(args.root),
            "pass --root a checkout directory that exists, then rerun",
        )
    if args.discard_journal != args.yes:
        return report(
            ExitCode.USAGE,
            "apply_refactor: journal discard requires explicit confirmation",
            "--discard-journal and --yes must be given together",
            "inspect current targets, then use --discard-journal --yes to abandon recovery",
        )
    fault = (
        None
        if args.timeout is None
        else run_make_target.limit_fault(run_make_target.LIMIT_KEYS[0], args.timeout)
    )
    if fault is not None:
        return report(
            ExitCode.USAGE,
            "apply_refactor: --timeout must be %s seconds" % fault,
            "--timeout %s" % run_make_target.shown_value(args.timeout),
            "give a whole number of seconds in that range, or leave --timeout out "
            "to use config/project.json make_targets.gate_timeout_seconds",
        )

    recovered: list[str] = []
    result: dict[str, object]
    try:
        if args.recover or args.discard_journal:
            root = os.path.realpath(args.root)
            path = _journal_path(root)
            _validate_journal_path(root, path)
            with _locked(path):
                discarded = args.discard_journal and path.exists()
                if args.discard_journal:
                    _remove(path)
                else:
                    recovered.extend(_recover(path, root))
            result = {
                "files": [],
                "recovered": recovered,
                "recovery_only": args.recover,
                "discarded_journal": discarded,
            }
        else:
            result = _run(
                lambda: _load_spec(args.spec),
                args.root,
                args.gate,
                args.timeout,
                None,
                args.allow,
                None,
                recovered,
                dry=args.dry_run,
            )
    except (JournalConflict, LockBusy) as exc:
        if args.json:
            json.dump(
                {
                    "error": str(exc),
                    "journal_conflict": isinstance(exc, JournalConflict),
                    "lock_busy": isinstance(exc, LockBusy),
                    "recovered": recovered,
                },
                sys.stdout,
                indent=2,
                sort_keys=True,
            )
            sys.stdout.write("\n")
        return report(
            ExitCode.FAILURE,
            "apply_refactor: journal recovery refused",
            _recovery_context(exc, recovered),
            "inspect the configured journal and lock, reconcile conflicting evidence or wait for the gate, then retry; "
            "a human may abandon recovery with --discard-journal --yes",
        )
    except RollbackError as exc:
        if args.json:
            json.dump(
                {"error": str(exc), "recovered": recovered},
                sys.stdout,
                indent=2,
                sort_keys=True,
            )
            sys.stdout.write("\n")
        return report(
            ExitCode.FAILURE,
            "apply_refactor: RollbackError; per-file restore failed",
            _recovery_context(exc, recovered),
            "restore each named file from the retained journal or version control "
            "and inspect the tree before running another refactor",
        )
    except config_loader.ConfigError as exc:
        if args.json:
            json.dump(
                {"error": str(exc), "recovered": recovered},
                sys.stdout,
                indent=2,
                sort_keys=True,
            )
            sys.stdout.write("\n")
        return report(
            ExitCode.USAGE if config_loader.is_conflict(exc) else ExitCode.CONFIG,
            "apply_refactor: the edit policy in config/project.json `agents` "
            "could not be used",
            _recovery_context(exc, recovered),
            "fix the key the message names; inspect the recovered originals before retrying"
            if recovered
            else "fix the key the message names; nothing was changed",
        )
    except (RefactorError, ValueError, OSError, json.JSONDecodeError) as exc:
        if args.json:
            json.dump(
                {"error": str(exc), "recovered": recovered},
                sys.stdout,
                indent=2,
                sort_keys=True,
            )
            sys.stdout.write("\n")
        return report(
            ExitCode.USAGE,
            "apply_refactor: the edit spec was refused after startup recovery",
            _recovery_context(exc, recovered),
            "correct the spec and run it again",
        )

    # Joined once so the pragma sits ON the line it silences: `ruff format`
    # carried both of these off their expressions during the corpus
    # reformat, and RUF100 is deferred, so nothing reported the orphans.
    files = ", ".join(result["files"])  # type: ignore[arg-type]
    if args.json:
        json.dump(result, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    elif args.recover:
        sys.stdout.write("apply_refactor: recovered %s\n" % ", ".join(recovered))
    elif args.discard_journal:
        sys.stdout.write("apply_refactor: discarded journal; targets unchanged\n")
    elif result.get("pending_recovery"):
        sys.stdout.write(
            "apply_refactor: pending recovery; run without --dry-run to replay the journal\n"
        )
    elif result.get("dry_run"):
        sys.stdout.write("apply_refactor: would edit %s\n" % files)
    else:
        verb = "applied" if result["applied"] else "ROLLED BACK (gate failed)"
        sys.stdout.write(
            "apply_refactor: %s [%s] gate=%s -> %s\n"
            % (files, result["practice"], result["gate"], verb)
        )
    if (
        args.recover
        or args.discard_journal
        or result.get("dry_run")
        or result["applied"]
    ):
        return ExitCode.SUCCESS
    return report(
        ExitCode.FAILURE,
        "apply_refactor: the gate failed; planned files were restored one at a time",
        "`make %s` after editing %s" % (result["gate"], files),
        "read the gate's output, correct the spec and run it again",
    )


if __name__ == "__main__":
    finish(main())
