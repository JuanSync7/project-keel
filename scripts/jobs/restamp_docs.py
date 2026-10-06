#!/usr/bin/env python3
"""
title: restamp_docs — the writer that keeps `updated:` true
kind: script
layer: n/a
summary: Sets the frontmatter `updated:` of every governed Markdown document that needs it to the date the judge will demand, and changes no other byte. scripts/jobs/review_docs.py is the judge of the freshness rule; this is the writer that clears its findings, reading the stamp through the judge's own `updated_span` and today through the judge's own `resolve_today` (`--today`, else SOURCE_DATE_EPOCH read in UTC, else the local clock), so the two cannot disagree on what a stamp is or what day it is. The worklist in a git work tree is what git would commit: the untracked documents, the ones changed against HEAD (every tracked one before the first commit), and the ones already committed stale; with no git it is every Markdown file outside check_structure's IGNORE_DIRS. The target is today, raised to the date of the document's last commit when that is later, because the judge reads that date from git, not from a clock. A document's template twin (`<doc>.jinja`, check_N's suffix) is restamped with it, so the parity gate never sees the two stamps differ. A stamp is never moved backwards, and a stamp that is not an ISO date is named on stderr and left alone (exit 1) while the rest are still written; a malformed date source exits 2. `--check` lists and writes nothing. Run by `make restamp-docs`, by copier's `_tasks` on every render (copy, and the scratch renders an update diffs), and by the last `after` migration on update.
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

import check_structure  # noqa: E402
import review_docs  # noqa: E402

ROOT = os.path.dirname(_SCRIPTS)
# The directories no walk descends into, owned by check_structure so the
# writer's notion of "the tree" and the gate's cannot drift apart. Not
# review_docs' list: that one also drops `wiki/` and every dot-dir, and
# governed documents live there.
WALK_SKIP_DIRS = check_structure.IGNORE_DIRS
# A document's template twin is `<doc>` plus this suffix. It is check_N's own
# constant, so the writer moves exactly the twins the parity gate compares.
TWIN_SUFFIX = check_structure._TWIN_SUFFIX
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
    proc = subprocess.run(
        ["git"] + list(args),
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
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


def worklist(root, today):
    """(root-relative path, target date) for each Markdown file that may need a
    stamp, sorted by path.

    With no git work tree it is every Markdown file outside WALK_SKIP_DIRS. In a
    work tree it is what git would commit: the untracked files (not ignored),
    the files changed against HEAD (or, before the first commit, every tracked
    one), and the ones the judge already finds committed stale — that last set
    is what makes the judge's remedy ("run `make restamp-docs`") true. The
    target is never earlier than the file's last commit (`target_date`)."""
    if not _inside_work_tree(root):
        return [(rel, today) for rel in sorted(set(_walk(root)))]
    paths = set(
        _split(_git(root, "ls-files", "-o", "--exclude-standard", "-z", "--", "*.md"))
    )
    if _git(root, "rev-parse", "--verify", "-q", "HEAD") is None:
        paths.update(_split(_git(root, "ls-files", "-z", "--", "*.md")))
    else:
        # --relative: below the repository top, git names a changed file from
        # the top (`sub/docs/a.md`) unless told otherwise, and that name would
        # never match the root-relative ones the rest of this list uses.
        paths.update(
            _split(
                _git(
                    root,
                    "diff",
                    "--name-only",
                    "--relative",
                    "-z",
                    "HEAD",
                    "--",
                    "*.md",
                )
            )
        )
    records = review_docs.collect(root) or []
    floors = {relpath: last_commit for relpath, _u, last_commit, _m in records}
    for finding in review_docs.stale_findings(records, today.isoformat()):
        paths.add(finding["path"])
    return [(rel, target_date(today, floors.get(rel))) for rel in sorted(paths)]


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


def _restamp_file(full, today, check):
    """Restamp one file in place (or only report it, under *check*). Returns
    (rewritten, error): *rewritten* when it was, or would be, rewritten, and
    *error* the reason a stamp could not be read, leaving the file alone. A symlink, a missing path and non-UTF-8 text
    are skipped: a symlink's target carries the date, a deletion has none, and
    the judge cannot read undecodable text either, so it is not governed."""
    if os.path.islink(full) or not os.path.isfile(full):
        return False, None
    with open(full, "rb") as fh:
        raw = fh.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return False, None
    try:
        new = restamp_text(text, today)
    except RestampError as exc:
        return False, str(exc)
    if new is None:
        return False, None
    if not check:
        _write_atomic(full, new.encode("utf-8"))
    return True, None


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
    try:
        work = worklist(root, today)
    except RestampError as exc:
        print("restamp_docs: %s" % exc, file=sys.stderr)
        return 2
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
