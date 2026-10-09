#!/usr/bin/env python3
"""
title: restamp_docs — the writer that keeps `updated:` true
kind: script
layer: n/a
summary: Sets the frontmatter `updated:` of every governed Markdown document that needs it to the date the judge will demand, and changes no other byte. scripts/jobs/review_docs.py is the judge of the freshness rule; this is the writer that clears its findings, reading the stamp through the judge's own `updated_span` and today through the judge's own `resolve_today` (`--today`, else SOURCE_DATE_EPOCH read in UTC, else the local clock), so the two cannot disagree on what a stamp is or what day it is. The worklist in a git work tree is what git would commit: the untracked documents, the ones changed against HEAD (every tracked one before the first commit, else review_docs' `modified_paths`, which reads `git --no-optional-locks status` and so never rewrites .git/index), and the ones already committed stale; with no git it is every Markdown file outside check_structure's IGNORE_DIRS (a copy, `WALK_SKIP_DIRS`, that its unit test pins equal). The target is today, raised to the date of the document's last commit when that is later, because the judge reads that date from git, not from a clock. A document's template twin (`<doc>.jinja`, check_N's suffix) is restamped with it, so the parity gate never sees the two stamps differ. A stamp is never moved backwards, and a stamp that is not an ISO date, or a document that cannot be read, is named on stderr and left alone (exit 1) while the rest are still written; a malformed date source exits 2. `--check` lists and writes nothing, the index included; `pending` is the same list as data (path, current stamp, target), for a caller such as scripts/audit_project.py. A document git lists as unmerged, or one whose text holds a conflict hunk (scripts/jobs/conflict_guard.py's grammar), is left for the merge with its twin and named on stderr, and the exit code is unchanged: rewriting the project's stamp inside an unresolved conflict would decide half of it. Run as a script, it first refuses, exit 2 naming each file and `make restamp-docs`, when a module it imports from the project holds a conflict hunk. A config/project.json an update left conflicted gives no child an allowlist, so no git may start: scripts/jobs/conflict_guard.py refuses the run over it (and over any other fixed project file a module it imports declares reading in `PROJECT_READS`), naming each file, its hunk's line and `make restamp-docs`, or under an update (`--finish-with`) the command that finishes it, and exits 2, listing and writing nothing; a manifest it cannot read for another reason is named the same way. It imports nothing from check_structure, so a conflict in that module, or in a file only the checks read (the Makefile, pyproject.toml), never stops it: the guard refuses a job over every read of each module it imports. Run by `make restamp-docs`, by copier's `_tasks` on every render (copy, and the scratch renders an update diffs), and by the last `after` migration on update.
effect: writes
rerun: fixed-point
rerun_proof: test:tests/integration/test_idempotence.py
"""

# 3.6-safe and stdlib-only on purpose: copier runs this under its own
# interpreter in a project that may have no virtualenv yet, and the host
# python3 here is 3.6.
import argparse
import datetime
import os
import re
import shutil
import subprocess
import sys
import tempfile

_JOBS = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.dirname(_JOBS)
for _dir in (_JOBS, _SCRIPTS):
    if _dir not in sys.path:
        sys.path.insert(0, _dir)
# copier runs this inside a project it has just written; importing the two
# siblings below would otherwise leave scripts/__pycache__/*.pyc in it, which
# made two generations with the same answers differ (measured). Only when run
# as a script: an importer's own bytecode policy is not this module's to change.
if __name__ == "__main__":
    sys.dont_write_bytecode = True

import conflict_guard  # noqa: E402

# Before every import below: copier runs this in a project mid-update,
# where a module it imports may hold conflict markers, and that import
# would die on a SyntaxError traceback naming neither the file nor the
# remedy. Only when run as a script: an importer's imports are its own.
# The make target reruns the task; under an update (`--finish-with`, which
# copier.yml passes the migration) the rerun is the step that finishes it.
_RERUN = "make restamp-docs"


def rerun(finish_with):
    """The command a refusal names: the finish command under an update."""
    return conflict_guard.finish_rerun(finish_with) if finish_with else _RERUN


if __name__ == "__main__":
    conflict_guard.exit_if_conflicted(
        __file__,
        os.path.dirname(_SCRIPTS),
        "restamp_docs",
        rerun(conflict_guard.finish_with_arg(sys.argv[1:])),
        search_path=(_JOBS, _SCRIPTS),
    )

import child_env  # noqa: E402
import review_docs  # noqa: E402

ROOT = os.path.dirname(_SCRIPTS)
# The fixed project file this job reads itself (to name its hunk), declared
# for conflict_guard; child_env declares it too, for the git it starts.
PROJECT_READS = ("config/project.json",)
# The directories no walk descends into: check_structure's IGNORE_DIRS, so
# the writer's notion of "the tree" and the gate's agree;
# tests/unit/scripts/test_restamp_docs.py pins the two equal. Not review_docs'
# list: that one also drops `wiki/` and every dot-dir, and governed documents
# live there. A copy, not an import: conflict_guard refuses a job over every
# file a module it imports reads, and importing check_structure for two
# constants made a conflicted Makefile stop the restamp (measured).
WALK_SKIP_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".astro",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    ".eggs",
    "htmlcov",
}
# A document's template twin is `<doc>` plus this suffix: check_N's own
# `_TWIN_SUFFIX` (pinned equal by the same test), so the writer moves exactly
# the twins the parity gate compares.
TWIN_SUFFIX = ".jinja"
_EPOCH = re.compile(r"^[0-9]+$")


class RestampError(Exception):
    """A stamp or a date source this writer refuses to guess about."""


def restamp_text(text, today):
    """*text* with its frontmatter `updated:` value set to *today* (a date), or
    None when there is nothing to do: no governed stamp, or a stamp already on or
    after *today*. Only the value's own characters change. Raises RestampError
    when the stamp is not an ISO date, because the judge reports that and a
    writer that overwrote it would hide what the author meant."""
    span = review_docs.updated_span(text)
    if span is None:
        return None
    start, end = span
    value = text[start:end]
    if not review_docs.ISO_DATE.match(value):
        raise RestampError("`updated: %s` is not an ISO date (YYYY-MM-DD)" % value)
    stamp = today.isoformat()
    if value >= stamp:
        return None
    return text[:start] + stamp + text[end:]


def resolve_today(argv_today, environ):
    """The writer's today: the judge's own resolver (scripts/jobs/review_docs.py
    `resolve_today` — `--today`, else SOURCE_DATE_EPOCH in UTC, else the local
    clock), so the two can never stand on different days. A malformed source is
    a RestampError, never a silent fallback to the clock."""
    try:
        return review_docs.resolve_today(argv_today, environ)
    except review_docs.DateSourceError as exc:
        raise RestampError(str(exc)) from exc


def target_date(today, last_commit):
    """The date a stamp must reach: *today*, or the ISO date of the file's last
    commit when that is later. The judge's first rule reads the commit date from
    git, not from any clock, so a writer that stamped only its own today left a
    committed-stale document stale whenever today was behind the commit (a
    pinned SOURCE_DATE_EPOCH, or a committer timezone ahead of UTC)."""
    if last_commit is None:
        return today
    if not review_docs.ISO_DATE.match(last_commit):
        raise RestampError("git commit date %r is not an ISO date" % last_commit)
    try:
        committed = datetime.datetime.strptime(last_commit, "%Y-%m-%d").date()
    except ValueError as exc:
        raise RestampError(
            "git commit date %r is not a calendar date" % last_commit
        ) from exc
    return max(today, committed)


def _git(root, *args):
    """git's stdout at *root*, or None when git is absent or the call fails."""
    if shutil.which("git") is None:
        return None
    try:
        # The judge's read-only argv: no index write-back, and no command the
        # repository's own config names (fsmonitor, filters, gpg).
        argv = review_docs.git_argv(root, *args)
    except review_docs.GitConfigError:
        return None
    proc = subprocess.run(
        argv,
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        env=child_env.build_child_env(),
    )
    return proc.stdout if proc.returncode == 0 else None


def _split(out):
    return [p for p in (out or "").split("\0") if p]


def _inside_work_tree(root):
    out = _git(root, "rev-parse", "--is-inside-work-tree")
    return out is not None and out.strip() == "true"


def _walk(root):
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in WALK_SKIP_DIRS)
        for name in filenames:
            if name.endswith(".md"):
                rel = os.path.relpath(os.path.join(dirpath, name), root)
                found.append(rel.replace(os.sep, "/"))
    return found


# Why a document is left out of the run; the remedy is the job's own target.
CONFLICTED = "conflicted; left for the merge, run `make restamp-docs` after resolving"
TWIN_OF_CONFLICTED = "its twin is conflicted; left with it for the merge"


def conflicted_paths(root):
    """The root-relative paths git records as unmerged at *root* (`git ls-files
    -u`, read-only), as a set; empty outside a work tree."""
    paths = set()
    for entry in _split(_git(root, "ls-files", "-u", "-z")):
        path = entry.partition("\t")[2]
        if path:
            paths.add(path)
    return paths


def _holds_conflict(full):
    """True when the file at *full* holds a conflict hunk. A file that cannot be
    read or decoded is not judged here: the restamp names an unreadable one."""
    if os.path.islink(full) or not os.path.isfile(full):
        return False
    try:
        with open(full, "rb") as fh:
            return conflict_guard.has_conflict(fh.read().decode("utf-8"))
    except (OSError, ValueError):
        return False


def _drop_conflicted(root, rows, skipped):
    """*rows* without each document that, or whose twin, is unmerged in the
    index or holds a conflict hunk in the work tree: a stamp inside a merge is
    the merge's to settle, and restamping one side of it turned a stamp-only
    conflict into one with two identical sides (measured). Each one left out is
    appended to *skipped* (a list, or None) as (path, reason)."""
    unmerged = conflicted_paths(root)
    kept = []
    for rel, target_day in rows:
        pair = (rel, rel + TWIN_SUFFIX)
        hit = [
            p for p in pair if p in unmerged or _holds_conflict(os.path.join(root, p))
        ]
        if not hit:
            kept.append((rel, target_day))
            continue
        if skipped is not None:
            for p in pair:
                if p in hit:
                    skipped.append((p, CONFLICTED))
                elif os.path.lexists(os.path.join(root, p)):
                    skipped.append((p, TWIN_OF_CONFLICTED))
    return kept


def worklist(root, today, skipped=None):
    """(root-relative path, target date) for each Markdown file that may need a
    stamp, sorted by path. A document that is conflicted, or whose twin is, is
    left out and, when *skipped* is a list, named in it as (path, reason).

    With no git work tree it is every Markdown file outside WALK_SKIP_DIRS. In a
    work tree it is what git would commit: the untracked files (not ignored),
    the files changed against HEAD (or, before the first commit, every tracked
    one), and the ones the judge already finds committed stale — that last set
    is what makes the judge's remedy ("run `make restamp-docs`") true. The
    target is never earlier than the file's last commit (`target_date`)."""
    if not _inside_work_tree(root):
        rows = [(rel, today) for rel in sorted(set(_walk(root)))]
        return _drop_conflicted(root, rows, skipped)
    paths = set(
        _split(_git(root, "ls-files", "-o", "--exclude-standard", "-z", "--", "*.md"))
    )
    if _git(root, "rev-parse", "--verify", "-q", "HEAD") is None:
        paths.update(_split(_git(root, "ls-files", "-z", "--", "*.md")))
    else:
        # The judge's reader, root-relative below the repository top and
        # read-only: `git diff HEAD` would rewrite .git/index (measured).
        paths.update(
            p for p in review_docs.modified_paths(root) or () if p.endswith(".md")
        )
    records = review_docs.collect(root) or []
    floors = {relpath: last_commit for relpath, _u, last_commit, _m in records}
    for finding in review_docs.stale_findings(records, today.isoformat()):
        paths.add(finding["path"])
    rows = [(rel, target_date(today, floors.get(rel))) for rel in sorted(paths)]
    return _drop_conflicted(root, rows, skipped)


def _write_atomic(path, data):
    """Replace *path* with *data* in one rename, keeping its mode, so a reader
    or a crash never sees half a document."""
    fd, tmp = tempfile.mkstemp(
        dir=os.path.dirname(path),
        prefix="." + os.path.basename(path) + ".",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


class UnreadableError(Exception):
    """A governed file exists but cannot be read; the message says why."""


def _read_stamp(full):
    """(text, current stamp) of a governed file, or None when there is nothing
    to judge: a symlink, a missing path, undecodable text, or no stamp. Raises
    UnreadableError when the file exists and cannot be opened or read."""
    if os.path.islink(full) or not os.path.isfile(full):
        return None
    try:
        with open(full, "rb") as fh:
            raw = fh.read()
    except OSError as exc:
        raise UnreadableError("cannot read (%s)" % (exc.strerror or exc)) from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    span = review_docs.updated_span(text)
    if span is None:
        return None
    return text, text[span[0] : span[1]]


def pending(root, today, errors=None, skipped=None):
    """What a run would rewrite, written nowhere: a sorted list of (root-relative
    path, current stamp, target stamp), a document's template twin included.
    A stamp that is not an ISO date, or a file that cannot be read, is not
    listed; when *errors* is a list, (path, reason) is appended to it instead.
    A conflicted document and its twin are not listed either; when *skipped*
    is a list, (path, reason) is appended to it. Raises RestampError on a
    malformed commit date, as a run would."""
    rows = []
    for rel, target_day in worklist(root, today, skipped):
        for target in (rel, rel + TWIN_SUFFIX):
            try:
                read = _read_stamp(os.path.join(root, target))
            except UnreadableError as exc:
                if errors is not None:
                    errors.append((target, str(exc)))
                continue
            if read is None:
                continue
            text, current = read
            try:
                new = restamp_text(text, target_day)
            except RestampError as exc:
                if errors is not None:
                    errors.append((target, str(exc)))
                continue
            if new is not None:
                rows.append((target, current, target_day.isoformat()))
    return sorted(rows)


def _restamp_file(full, today, check):
    """Restamp one file in place (or only report it, under *check*). Returns
    (rewritten, error): *rewritten* when it was, or would be, rewritten, and
    *error* the reason a stamp could not be read, leaving the file alone. A symlink, a missing path and non-UTF-8 text
    are skipped: a symlink's target carries the date, a deletion has none, and
    the judge cannot read undecodable text either, so it is not governed."""
    try:
        read = _read_stamp(full)
    except UnreadableError as exc:
        return False, str(exc)
    if read is None:
        return False, None
    text = read[0]
    try:
        new = restamp_text(text, today)
    except RestampError as exc:
        return False, str(exc)
    if new is None:
        return False, None
    if not check:
        _write_atomic(full, new.encode("utf-8"))
    return True, None


def _no_allowlist(exc, root, command):
    """The stderr line for a ChildEnvError: no child may start, so no git runs
    and nothing is listed or written. A manifest an update left conflicted is
    the likely cause; then the line is conflict_guard's refusal, naming the
    manifest and its hunk's line, so an audit reads it as the guard's own."""
    manifest = os.path.join("config", "project.json")
    try:
        with open(os.path.join(root, manifest), "rb") as fh:
            line = conflict_guard.conflict_line(fh.read().decode("utf-8"))
    except (OSError, ValueError):
        line = None  # the ChildEnvError itself already says it is unreadable
    if line is not None:
        found = [(manifest.replace(os.sep, "/"), line)]
        return conflict_guard.refusal("restamp_docs", found, command).rstrip("\n")
    return "restamp_docs: cannot start git: %s; resolve it, then run `%s`" % (
        exc,
        command,
    )


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Set a stale frontmatter `updated:` to today; change nothing else."
    )
    ap.add_argument(
        "--root", default=ROOT, help="repository root (default: this checkout)"
    )
    ap.add_argument(
        "--today",
        default=None,
        help="the date to stamp (default: SOURCE_DATE_EPOCH in UTC, else today)",
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="list what would be restamped, write nothing, exit 1 if anything would be",
    )
    ap.add_argument(
        "--quiet", action="store_true", help="do not list the files written"
    )
    ap.add_argument(
        conflict_guard.FINISH_FLAG,
        dest="finish_with",
        metavar="PYTHON",
        default=None,
        help="run as a copier update migration: a refusal names the command "
        "that finishes the update under this interpreter",
    )
    args = ap.parse_args(argv)
    try:
        today = resolve_today(args.today, os.environ)
    except RestampError as exc:
        print("restamp_docs: %s" % exc, file=sys.stderr)
        return 2
    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print("restamp_docs: --root %s is not a directory" % root, file=sys.stderr)
        return 2
    # A skip is named, never a failure: an ordinary content conflict in a
    # governed document must not fail the `copier update` that left it.
    skipped = []
    if args.check:
        errors = []
        try:
            rows = pending(root, today, errors, skipped)
        except RestampError as exc:
            print("restamp_docs: %s" % exc, file=sys.stderr)
            return 2
        except child_env.ChildEnvError as exc:
            print(
                _no_allowlist(exc, root, rerun(args.finish_with)),
                file=sys.stderr,
            )
            return 2
        for target, reason in skipped:
            print("restamp_docs: %s: %s" % (target, reason), file=sys.stderr)
        for target, reason in errors:
            print("restamp_docs: %s: %s" % (target, reason), file=sys.stderr)
        for target, _current, _target_day in rows:
            print(target)
        return 1 if errors or rows else 0
    try:
        work = worklist(root, today, skipped)
    except RestampError as exc:
        print("restamp_docs: %s" % exc, file=sys.stderr)
        return 2
    except child_env.ChildEnvError as exc:
        print(
            _no_allowlist(exc, root, rerun(args.finish_with)),
            file=sys.stderr,
        )
        return 2
    for target, reason in skipped:
        print("restamp_docs: %s: %s" % (target, reason), file=sys.stderr)
    changed, failed = [], False
    for rel, target_day in work:
        # The twin rides with its document: it is never in the worklist itself
        # (it is not `*.md`), and check_N fails a parity twin whose stamp line
        # the plain file no longer carries.
        for target in (rel, rel + TWIN_SUFFIX):
            rewritten, error = _restamp_file(
                os.path.join(root, target), target_day, args.check
            )
            if error is not None:
                print("restamp_docs: %s: %s" % (target, error), file=sys.stderr)
                failed = True
            elif rewritten:
                changed.append(target)
    if args.check or not args.quiet:
        for rel in changed:
            print(rel)
    return 1 if failed or (args.check and changed) else 0


if __name__ == "__main__":
    sys.exit(main())
