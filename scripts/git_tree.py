"""
title: git_tree — what git lists, and a digest of it
kind: script
layer: n/a
summary: The one definition of "what git lists" in a work tree. tree_snapshot records HEAD's commit and branch. It records the index entries of paths `git status` lists, alongside their status, working content and mode, and nested repository identity. changed_paths returns its sorted path keys without tree-identity keys. snapshot_changes names differences between snapshots with paths and readable identity labels. snapshot_digest reduces the whole snapshot to one `sha256:` value over its canonical JSON. candidate_files lists what a commit could carry (every tracked or staged path and every untracked path git does not ignore, sorted), the one definition of that set, and staged_blob gives the bytes the index holds for one path, or None for no entry, a submodule or a symlink, whose blob is its target's path and not file content. staged_paths lists what the index stages for the next commit, deletions left out as pre-commit leaves them out, and with repo_context=True reads the index a hook's GIT_INDEX_FILE names. is_ignored answers whether git would list a path that may not exist yet, tracked answers which of the given paths git tracks, and head_commit names HEAD's sha or None when there is no commit. in_head says whether HEAD's commit holds a path, so a file deleted from the work tree or the index still counts as committed. log_commits lists the commits `git log` walks for a list of options, so a scan of that range can tell it walked none. A git command that does not answer has three causes, and only two of them mean "no git": NoGitError is raised when git is not installed (the spawn finds no program) or when no repository exists at or above the directory, and GitFailedError, which is not a NoGitError, when git ran and failed for any other reason or could not be started, carrying git's exit status and its stderr cut to STDERR_MAX characters. git exits 128 for "not a git repository" and for a repository it cannot read alike, so the two are told apart on disk, never by the text of stderr: inside_a_repository walks up from the directory for a `.git` entry and stops where git's own discovery stops (a directory GIT_CEILING_DIRECTORIES names, and a filesystem boundary). A caller that treats NoGitError as "nothing is tracked here" must let GitFailedError stop it: an unreadable repository is unknown, not absent. through_symlink names the project-relative paths that reach their file through a symlink, which needs no git and is what a writer asks before it writes or deletes at a path read from config. git runs with the allowlisted environment from scripts/child_env.py, git's repository context left out except where staged_paths is asked for it, and with the developer's global excludes file switched off. Stdlib and 3.6-safe, so scripts/gate_evidence.py can import it under the old interpreter. It decides nothing about what runs or passes (scripts/run_make_target.py and scripts/gate_evidence.py do), and it writes nothing.
"""

# NB: stdlib only, no `from __future__ import annotations`, no f-strings, no walrus,
# no `list[str]` or `X | None` annotations. scripts/gate_evidence.py imports this
# module, and a `make verify` whose PY is older than requires-python must still run
# that writer so the record it leaves is red rather than an earlier green one
# (tests/integration/test_gate_scope.py `_old_python_safe`).
# subprocess.run and child_env.build_child_env are looked up on their modules at
# call time on purpose: tests/unit/scripts/test_run_make_target.py patches both
# through run_make_target's module attributes, which are these same modules.

import hashlib
import json
import os
import subprocess

import child_env

__all__ = [
    "STDERR_MAX",
    "GitFailedError",
    "NoGitError",
    "candidate_files",
    "changed_paths",
    "head_commit",
    "in_head",
    "inside_a_repository",
    "is_ignored",
    "log_commits",
    "snapshot_changes",
    "snapshot_digest",
    "staged_blob",
    "staged_paths",
    "through_symlink",
    "tracked",
    "tree_snapshot",
]


# How much of git's stderr a GitFailedError carries: enough for git's own
# sentence, short enough that a caller's one-line message stays one line a
# terminal shows.
STDERR_MAX = 400
# git's own names for the two limits on its search for a repository
# (git(1), ENVIRONMENT VARIABLES).
_CEILINGS = "GIT_CEILING_DIRECTORIES"
_CROSS_FILESYSTEM = "GIT_DISCOVERY_ACROSS_FILESYSTEM"
# NUL cannot occur in a repository path, so identity keys cannot shadow files.
_IDENTITY_PREFIX = "\0"
_HEAD_KEY = _IDENTITY_PREFIX + "HEAD"
_BRANCH_KEY = _IDENTITY_PREFIX + "HEAD branch"


class NoGitError(Exception):
    """There is no git to ask: git is not installed, or no repository exists at
    or above the directory. No before/after comparison of what git lists is
    possible and a read-only claim is unproven."""


class GitFailedError(Exception):
    """git was there and a repository was there, and git still did not answer.

    Not a NoGitError on purpose: a caller that reads "no git" as "nothing is
    tracked, so nothing needs protecting" must not read an unreadable
    repository that way. *returncode* is git's exit status, or None when git
    could not be started; *stderr* is what git wrote, one line, cut to
    STDERR_MAX characters."""

    def __init__(self, returncode, stderr):
        self.returncode = returncode
        self.stderr = " ".join(stderr.split())[:STDERR_MAX]
        if returncode is None:
            message = "git could not be started: %s" % self.stderr
        else:
            message = "git exited %d: %s" % (returncode, self.stderr or "(no stderr)")
        Exception.__init__(self, message)


def inside_a_repository(root, env=None):
    """True when a `.git` entry exists at *root* or at a directory above it that
    git, started in *root* with *env*, would search: the walk stops below a
    directory GIT_CEILING_DIRECTORIES names (never *root* itself, which git
    always searches) and at a filesystem boundary unless
    GIT_DISCOVERY_ACROSS_FILESYSTEM is set. *env* defaults to the allowlisted
    environment git is given here. It does not say the repository is readable:
    that is what a GitFailedError reports."""
    if env is None:
        env = child_env.build_child_env()
    ceilings = {
        os.path.realpath(entry)
        for entry in env.get(_CEILINGS, "").split(os.pathsep)
        if entry
    }
    current = os.path.realpath(root)
    device = os.stat(current).st_dev
    while True:
        if os.path.lexists(os.path.join(current, ".git")):
            return True
        parent = os.path.dirname(current)
        if parent == current or parent in ceilings:
            return False
        if os.stat(parent).st_dev != device and not env.get(_CROSS_FILESYSTEM):
            return False
        current = parent


def _run(root, argv, *, repo_context=False):
    # The developer's global excludes file is ignored ON PURPOSE: a stray file a
    # personal ignore hides is still a change this machine's checkout would carry.
    # The keyword is passed only when set, so a caller that patches
    # build_child_env with a no-argument stand-in still works.
    if repo_context:
        env = child_env.build_child_env(repo_context=True)
    else:
        env = child_env.build_child_env()
    try:
        return subprocess.run(  # noqa: S603 — argv list, never a shell string
            ["git", "-c", "core.excludesFile=" + os.devnull] + list(argv),
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
    except FileNotFoundError as exc:
        # The spawn reports a missing program and a missing working directory
        # with the same error; only the first is "git is not installed".
        if os.path.isdir(root):
            raise NoGitError("git is not installed (%s)" % exc) from exc
        raise GitFailedError(None, str(exc)) from exc
    except OSError as exc:
        raise GitFailedError(None, str(exc)) from exc


def _failed(proc, root):
    """Why a git that ran did not answer: NoGitError when *root* is in no
    repository, else GitFailedError. The filesystem decides, because git's exit
    status is the same for both."""
    stderr = proc.stderr.decode("utf-8", "replace")
    if not inside_a_repository(root):
        return NoGitError(stderr.strip() or "git exited %d" % proc.returncode)
    return GitFailedError(proc.returncode, stderr)


def _git(root, *argv, repo_context=False):
    proc = _run(root, argv, repo_context=repo_context)
    if proc.returncode != 0:
        raise _failed(proc, root)
    return proc.stdout


def _digest(path):
    if os.path.islink(path):
        return "link:" + os.readlink(path)
    if os.path.isfile(path):
        sha = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 16), b""):
                sha.update(chunk)
        return "sha:" + sha.hexdigest()
    if os.path.isdir(path):
        if os.path.lexists(os.path.join(path, ".git")):
            return "repo:" + snapshot_digest(tree_snapshot(path))
        return "dir"
    return "absent"


def _working_state(path):
    content = _digest(path)
    if content == "absent":
        return content
    return "%s|mode:%o" % (content, os.lstat(path).st_mode)


def tree_snapshot(root):
    """Map HEAD identity and every path git status lists to their states.

    Path states contain the two-letter status, working content and lstat mode,
    and the index entries of paths git status lists (mode, blob id and stage).
    A path marked `--assume-unchanged` or `--skip-worktree` is not seen.
    A nested repository or gitlink with a work tree carries its own snapshot
    digest, including HEAD's commit and branch and listed state.
    An uninitialised gitlink retains its index identity when git status lists its path.
    Ignored paths are excluded. Identity keys start with NUL,
    which no repository path can contain: `\\0HEAD` names HEAD's commit or the
    explicit `unborn` marker.
    `\\0HEAD branch` records the branch.head value from the same status read.
    changed_paths returns only the sorted path keys. snapshot_changes names
    differences with paths and readable identity labels `(HEAD commit)` and
    `(HEAD branch)`. Each repository visited takes three git calls: its root,
    status with HEAD, and the whole index in one call.
    The lstat mode check is stricter than git's core.filemode and fails closed.

    Raises NoGitError when there is no git or no repository, and
    GitFailedError when git ran and failed for another reason or status omitted
    the branch.oid header."""
    top = _git(root, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    raw = _git(
        top,
        "status",
        "--porcelain=v2",
        "--branch",
        "-z",
        "--untracked-files=all",
        "--ignore-submodules=none",
    )
    fields = raw.decode("utf-8", "surrogateescape").split("\0")
    snap = {}
    codes = {}
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if entry.startswith("# branch.oid "):
            oid = entry[len("# branch.oid ") :]
            snap[_HEAD_KEY] = "unborn" if oid == "(initial)" else oid
            continue
        if entry.startswith("# branch.head "):
            snap[_BRANCH_KEY] = entry[len("# branch.head ") :]
            continue
        if entry.startswith("? "):
            codes[entry[2:]] = "??"
            continue
        # Porcelain v2 gives each record kind a set number of fields, so splitting at
        # that count keeps spaces, tabs and newlines inside a path name.
        kind = entry[:1]
        widths = {"1": 8, "2": 9, "u": 10}
        if kind not in widths:
            continue
        parts = entry.split(" ", widths[kind])
        code, path = parts[1].replace(".", " "), parts[-1]
        codes[path] = code
        if kind == "2":
            codes[fields[i]] = code + "<"
            i += 1
    if _HEAD_KEY not in snap:
        raise GitFailedError(
            0, "git status omitted # branch.oid; HEAD identity is unknown"
        )
    index = {}
    raw_index = _git(top, "ls-files", "--stage", "-z")
    for entry in raw_index.decode("utf-8", "surrogateescape").split("\0"):
        state, tab, path = entry.partition("\t")
        if tab and path in codes:
            index.setdefault(path, []).append(state)
    for path in sorted(codes):
        snap[path] = "%s|%s|index:%s" % (
            codes[path],
            _working_state(os.path.join(top, path)),
            ",".join(sorted(index.get(path, []))),
        )
    return snap


def changed_paths(snap):
    """The sorted path keys in a snapshot, excluding tree-identity keys."""
    return sorted(path for path in snap if not path.startswith(_IDENTITY_PREFIX))


def snapshot_changes(before, after):
    """Sorted changed paths and readable tree-identity labels, without the NUL prefix.

    Identity labels are (HEAD commit) and (HEAD branch). Path names are kept as written.
    """
    keys = set(before) | set(after)
    changed = (key for key in keys if before.get(key) != after.get(key))
    labels = {_HEAD_KEY: "(HEAD commit)", _BRANCH_KEY: "(HEAD branch)"}
    return sorted(labels.get(key, key) for key in changed)


def snapshot_digest(snap):
    """`sha256:<hex>` over the canonical JSON of a tree_snapshot result: one value
    that names the tree identity and listed state, equal for equal snapshots."""
    text = json.dumps(snap, sort_keys=True, separators=(",", ":"))
    return (
        "sha256:" + hashlib.sha256(text.encode("utf-8", "surrogateescape")).hexdigest()
    )


def candidate_files(root):
    """The sorted root-relative paths a commit made from *root* could carry:
    every tracked or staged path (one deleted from the work tree included) and
    every untracked path git does not ignore. A force-added ignored file is
    tracked, so it is listed. Raises NoGitError when there is no git or no
    repository, and GitFailedError when git ran and failed for another
    reason."""
    raw = _git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    paths = raw.decode("utf-8", "surrogateescape").split("\0")
    # A path both staged and modified is listed once per index stage; a set
    # keeps one.
    return sorted({p for p in paths if p})


# pre-commit's own filter for the files a commit stages (pre_commit/git.py
# get_staged_files): every change but a deletion, so the two agree on when a
# staged hook has something to judge.
_STAGED_FILTER = "--diff-filter=ACMRTUXB"


def staged_paths(root, *, repo_context=False):
    """The sorted root-relative paths the index stages for the next commit,
    deletions left out. With *repo_context* the index is the one a hook's
    GIT_INDEX_FILE names, which `git commit -a` and `git commit <path>` fill
    in place of the default one. Raises NoGitError when there is no git or no
    repository, and GitFailedError when git ran and failed for another
    reason."""
    raw = _git(
        root,
        "diff",
        "--cached",
        "--name-only",
        "--no-renames",
        "-z",
        _STAGED_FILTER,
        repo_context=repo_context,
    )
    return sorted({p for p in raw.decode("utf-8", "surrogateescape").split("\0") if p})


# The index's modes whose object is no file's content: a submodule's entry
# names a commit, and a symlink's blob is the path the link points at.
_GITLINK = "160000"
_SYMLINK = "120000"
_NOT_CONTENT = (_GITLINK, _SYMLINK)


def staged_blob(root, rel):
    """The bytes the index holds for the root-relative path *rel*, which a
    commit would carry whatever the work tree holds now, or None when the
    index holds no file content for it (untracked, a submodule, or a symlink,
    whose blob is its target's path and which a reader judges at the target's
    own path). A path in conflict
    gives its first stage. Raises NoGitError when there is no git or no
    repository, and GitFailedError when git ran and failed for another
    reason."""
    # Literal, so a `*` or `[` in a file name is that name and not a pattern.
    raw = _git(root, "--literal-pathspecs", "ls-files", "-s", "-z", "--", rel)
    for entry in raw.decode("utf-8", "surrogateescape").split("\0"):
        # `<mode> <object> <stage>\t<path>`; a directory's pathspec also lists
        # the files under it, so only the entry for *rel* itself counts.
        fields, _tab, path = entry.partition("\t")
        if path != rel:
            continue
        mode, sha = fields.split(" ")[:2]
        if mode in _NOT_CONTENT:
            return None
        return _git(root, "cat-file", "blob", sha)
    return None


def is_ignored(root, rel):
    """True when git ignores the repo-relative path *rel* (which need not exist
    yet), False when it would list it. A tracked path is never ignored. Raises
    NoGitError when there is no git or no repository, and GitFailedError when
    git ran and failed for another reason."""
    proc = _run(root, ("check-ignore", "-q", "--", rel))
    # check-ignore answers with its exit code: 0 ignored, 1 not; anything else
    # is git failing, which must not read as "not ignored".
    if proc.returncode in (0, 1):
        return proc.returncode == 0
    raise _failed(proc, root)


def tracked(root, rels):
    """The set of the *root*-relative paths *rels* that git tracks (committed
    or staged). An untracked, ignored or absent path is not in it, and nor is
    anything under `.git`, which git never tracks. Each name is matched
    literally, so a `*` in a name stands for itself. Raises NoGitError when
    there is no git or no repository, and GitFailedError when git ran and
    failed for another reason."""
    rels = list(rels)
    if not rels:
        return set()
    raw = _git(root, "--literal-pathspecs", "ls-files", "-z", "--", *rels)
    listed = set(raw.decode("utf-8", "surrogateescape").split("\0"))
    return {rel for rel in rels if rel in listed}


def head_commit(root):
    """The full sha HEAD names, or None when there is none: no commit yet, no
    git or no repository. Raises GitFailedError when git ran and failed for
    another reason: a commit git could not read is unknown, not absent."""
    try:
        proc = _run(root, ("rev-parse", "--verify", "-q", "HEAD^{commit}"))
    except NoGitError:  # noqa: DROP001 -- None when there is no commit or no git, as documented
        return None
    # `--verify -q` answers a HEAD that names no commit with status 1 and no
    # message; anything else that is not 0 is git failing.
    if proc.returncode == 1:
        return None
    if proc.returncode != 0:
        failure = _failed(proc, root)
        if isinstance(failure, NoGitError):
            return None
        raise failure
    return proc.stdout.decode("ascii", "replace").strip() or None


def in_head(root, rel):
    """True when the commit HEAD names holds the *root*-relative path *rel*,
    matched literally; False when it does not, or when there is no commit yet.
    A path deleted from the work tree or the index is still in HEAD. Raises
    NoGitError when there is no git or no repository, and GitFailedError when
    git ran and failed for another reason."""
    # tracked() raises NoGitError where head_commit() would read "no git" as
    # "no commit", and a caller must not take that for "not in HEAD".
    tracked(root, [rel])
    if head_commit(root) is None:
        return False
    raw = _git(
        root, "--literal-pathspecs", "ls-tree", "--name-only", "-z", "HEAD", "--", rel
    )
    return rel in raw.decode("utf-8", "surrogateescape").split("\0")


# The lengths of a full object name, sha1 and sha256, in lowercase hex.
_OBJECT_NAME_LENGTHS = (40, 64)
_HEX = frozenset("0123456789abcdef")


def log_commits(root, options):
    """The full shas of the commits `git log <options>` walks, newest first,
    which is the range a history scan handed those options judges. An option
    after ours that asks for a patch or another format can add lines, so only
    a line that is a whole object name counts. Raises NoGitError when there is
    no git or no repository, and GitFailedError when git ran and failed,
    an option it refuses included: a range git could not walk is unknown,
    not empty."""
    raw = _git(root, "log", "--no-patch", "--format=%H", *options)
    return [
        line
        for line in raw.decode("ascii", "replace").split("\n")
        if len(line) in _OBJECT_NAME_LENGTHS and set(line) <= _HEX
    ]


def through_symlink(root, paths):
    """The project-relative POSIX *paths* that do not resolve to themselves
    under *root*: some component, or the path itself, is a symlink, wherever it
    points. A path that does not exist yet resolves to itself, and *root* itself
    may be reached through a link. Needs no git."""
    real_root = os.path.realpath(root)
    return [
        p
        for p in paths
        if os.path.realpath(os.path.join(root, p))
        != os.path.join(
            real_root, *[part for part in p.split("/") if part not in ("", ".")]
        )
    ]
