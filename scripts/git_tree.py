"""
title: git_tree — what git lists, and a digest of it
kind: script
layer: n/a
summary: The one definition of "what git lists" in a work tree. tree_snapshot maps every path `git status` reports (modified, staged, deleted, untracked; never an ignored one) to its two-letter porcelain status joined to a digest of its content, and snapshot_digest reduces a snapshot to one `sha256:` value over its canonical JSON. candidate_files lists what a commit could carry (every tracked or staged path and every untracked path git does not ignore, sorted), the one definition of that set, and staged_blob gives the bytes the index holds for one path, or None for no entry, a submodule or a symlink, whose blob is its target's path and not file content. staged_paths lists what the index stages for the next commit, deletions left out as pre-commit leaves them out, and with repo_context=True reads the index a hook's GIT_INDEX_FILE names. is_ignored answers whether git would list a path that may not exist yet, tracked answers which of the given paths git tracks, and head_commit names HEAD's sha or None when there is no commit. log_commits lists the commits `git log` walks for a list of options, so a scan of that range can tell it walked none. A git command that does not answer has three causes, and only two of them mean "no git": NoGitError is raised when git is not installed (the spawn finds no program) or when no repository exists at or above the directory, and GitFailedError, which is not a NoGitError, when git ran and failed for any other reason or could not be started, carrying git's exit status and its stderr cut to STDERR_MAX characters. git exits 128 for "not a git repository" and for a repository it cannot read alike, so the two are told apart on disk, never by the text of stderr: inside_a_repository walks up from the directory for a `.git` entry and stops where git's own discovery stops (a directory GIT_CEILING_DIRECTORIES names, and a filesystem boundary). A caller that treats NoGitError as "nothing is tracked here" must let GitFailedError stop it: an unreadable repository is unknown, not absent. through_symlink names the project-relative paths that reach their file through a symlink, which needs no git and is what a writer asks before it writes or deletes at a path read from config. git runs with the allowlisted environment from scripts/child_env.py, git's repository context left out except where staged_paths is asked for it, and with the developer's global excludes file switched off. Stdlib and 3.6-safe, so scripts/gate_evidence.py can import it under the old interpreter. It decides nothing about what runs or passes (scripts/run_make_target.py and scripts/gate_evidence.py do), and it writes nothing.
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
    "head_commit",
    "inside_a_repository",
    "is_ignored",
    "log_commits",
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


def _run(root, argv, repo_context=False):
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
        return "dir"  # a nested repository git lists as one entry
    return "absent"


def tree_snapshot(root):
    """{repo-relative path: state} for every path `git status` lists under root
    (modified, staged, deleted, untracked — never ignored). The state is the
    two-letter porcelain status joined to the sha256 of the content, so a second
    edit to an already-dirty file and a change to the index alone both show.

    Raises NoGitError when there is no git or no repository, and
    GitFailedError when git ran and failed for another reason."""
    top = _git(root, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    raw = _git(top, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    fields = raw.decode("utf-8", "surrogateescape").split("\0")
    codes = {}
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if len(entry) < 4:
            continue
        code, path = entry[:2], entry[3:]
        codes[path] = code
        # A rename/copy carries its source as the next field, in either column:
        # ` R` is a worktree rename (an intent-to-add file), `R ` a staged one.
        if "R" in code or "C" in code:
            codes[fields[i]] = code + "<"
            i += 1
    return {
        p: "%s|%s" % (codes[p], _digest(os.path.join(top, p))) for p in sorted(codes)
    }


def snapshot_digest(snap):
    """`sha256:<hex>` over the canonical JSON of a tree_snapshot result: one value
    that names the listed content, equal for equal snapshots and for a clean tree."""
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


def staged_paths(root, repo_context=False):
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
    except NoGitError:
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
