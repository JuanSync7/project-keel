#!/usr/bin/env python3
"""
title: resolve_stamp_conflicts — resolves a copier conflict whose only hunk is a document's updated: stamp
kind: script
layer: n/a
summary: Copier's `after` migration on update, run after every other migration but before the restamp, which stays last. copier's inline update leaves a document conflicted when the project and the template both moved its frontmatter `updated:` value since the project's `_commit` (projects generated before every render was fresh on arrival, and renders that straddled midnight with no SOURCE_DATE_EPOCH: 95 of bedrock-platform's 111 conflicts, measured). `updated:` means touched and both sides touched it, so such a conflict has one right answer: the later date. This job reads `git ls-files -u` (through review_docs' `git_argv`) and, for each unmerged `*.md` path that is a regular file with a project stage (2) and a template stage (3), hands its bytes to `resolve_stamp_conflict`. That resolves only when copier's markers (read with any label) make exactly one hunk, each side of it is one line, that line is the frontmatter `updated:` value on both sides as review_docs' `updated_span` reads it, the two sides differ in nothing else, and both values are real calendar dates; the diff3 base section is ignored. The file is then written atomically (mode kept) as the project's text with the later date, and one `git update-index --index-info` puts its index entry back to stage 0 at stage 2's mode and sha, so it shows as a cleanly merged ` M` file. Every other unmerged path keeps its bytes and its stages and is named on stderr with a reason from the closed vocabulary `REASONS`; a file that is not unmerged is never opened. Exit 0 when every unmerged path was resolved or left with a reason, 2 on a git or write failure. It does not import check_structure, whose copy in a project mid-update may itself be conflicted, and before importing review_docs it asks scripts/jobs/conflict_guard.py whether a module it imports, or a fixed project file those modules declare reading (child_env's config/project.json), holds a hunk: if one does, it names the files and the rerun command (run as a migration with `--finish-with`, the command that finishes the update) and exits 2.
effect: writes
rerun: fixed-point
rerun_proof: test:tests/integration/test_stamp_conflicts.py
"""

# 3.6-safe and stdlib-only on purpose: copier runs this under its own
# interpreter in a project that may have no virtualenv yet, and the host
# python3 here is 3.6.
import argparse
import datetime
import os
import shutil
import subprocess
import sys
import tempfile

_JOBS = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.dirname(_JOBS)
for _dir in (_JOBS, _SCRIPTS):
    if _dir not in sys.path:
        sys.path.insert(0, _dir)
# copier runs this inside a project it has just written; importing the
# siblings below would otherwise leave __pycache__/*.pyc in it (the reason
# restamp_docs.py sets the same flag). Only when run as a script.
if __name__ == "__main__":
    sys.dont_write_bytecode = True

import conflict_guard  # noqa: E402

# Before every import below: copier runs this in a project mid-update,
# where a module it imports may hold conflict markers, and that import
# would die on a SyntaxError traceback naming neither the file nor the
# remedy. Only when run as a script: an importer's imports are its own.
if __name__ == "__main__":
    conflict_guard.exit_if_conflicted(
        __file__,
        os.path.dirname(_SCRIPTS),
        "resolve_stamp_conflicts",
        conflict_guard.job_rerun(
            __file__,
            os.path.dirname(_SCRIPTS),
            sys.argv[1:],
            conflict_guard.finish_with_arg(sys.argv[1:]),
        ),
        search_path=(_JOBS, _SCRIPTS),
    )

import child_env  # noqa: E402
import review_docs  # noqa: E402

# The closed vocabulary of outcomes. RESOLVED is the only one that writes.
RESOLVED = "resolved"
# Refusals of the pure rule: the bytes are not a stamp-only conflict.
NOT_UTF8 = "not UTF-8"
UNBALANCED = "unbalanced markers"
NO_HUNK = "no conflict hunk"
MORE_THAN_ONE_HUNK = "more than one hunk"
SIDE_NOT_ONE_LINE = "a side is not one line"
LINE_ENDINGS_DIFFER = "line endings differ"
NO_FIELD = "no updated: field"
NOT_THE_STAMP_LINE = "the hunk is not the updated: line"
DIFFERS_OUTSIDE_STAMP = "differs outside the stamp"
UNPARSABLE_DATE = "unparsable date"
REFUSALS = (
    NOT_UTF8,
    UNBALANCED,
    NO_HUNK,
    MORE_THAN_ONE_HUNK,
    SIDE_NOT_ONE_LINE,
    LINE_ENDINGS_DIFFER,
    NO_FIELD,
    NOT_THE_STAMP_LINE,
    DIFFERS_OUTSIDE_STAMP,
    UNPARSABLE_DATE,
)
# Skips of a path whose bytes are never read.
NOT_MARKDOWN = "not a Markdown document"
NO_PROJECT_SIDE = "no project side"
NO_TEMPLATE_SIDE = "no template side"
ABSENT = "absent from the work tree"
SYMLINK = "a symlink"
NOT_A_FILE = "not a regular file"
SKIPS = (NOT_MARKDOWN, NO_PROJECT_SIDE, NO_TEMPLATE_SIDE, ABSENT, SYMLINK, NOT_A_FILE)
REASONS = (RESOLVED,) + REFUSALS + SKIPS

# `git merge-file` markers, any label: conflict_guard owns the grammar, so the
# guard that refuses a conflicted import and this resolver read one marker set.
_OPEN = conflict_guard.OPEN
_BASE = conflict_guard.BASE
_SPLIT = conflict_guard.SPLIT
_CLOSE = conflict_guard.CLOSE
_MD = ".md"
_DATE_FORMAT = "%Y-%m-%d"
_NULL_SHA = "0" * 40


class JobError(Exception):
    """git failed, or a resolved file could not be written."""


_marker = conflict_guard.marker


def _eol(line):
    if line.endswith("\r\n"):
        return "\r\n"
    return "\n" if line.endswith("\n") else ""


def _hunks(text):
    """(prefix, hunk, suffix) when *text* holds exactly one balanced hunk, where
    hunk is (ours_lines, theirs_lines); else a refusal reason. A `=======` line
    outside a hunk is content (a Markdown setext underline); inside the
    template's side it is ambiguous, so unbalanced."""
    out_lines = []
    hunks = []
    state = None
    ours = theirs = None
    for line in text.splitlines(True):
        if state is None:
            if _marker(line, _OPEN):
                state, ours, theirs = "ours", [], []
                hunks.append((len(out_lines), ours, theirs))
            elif _marker(line, _BASE) or _marker(line, _CLOSE):
                return UNBALANCED
            else:
                out_lines.append(line)
        elif state == "ours":
            if _marker(line, _BASE):
                state = "base"
            elif _marker(line, _SPLIT):
                state = "theirs"
            elif _marker(line, _OPEN) or _marker(line, _CLOSE):
                return UNBALANCED
            else:
                ours.append(line)
        elif state == "base":
            if _marker(line, _SPLIT):
                state = "theirs"
            elif _marker(line, _OPEN) or _marker(line, _BASE) or _marker(line, _CLOSE):
                return UNBALANCED
        else:
            if _marker(line, _CLOSE):
                state = None
            elif _marker(line, _OPEN) or _marker(line, _BASE) or _marker(line, _SPLIT):
                return UNBALANCED
            else:
                theirs.append(line)
    if state is not None:
        return UNBALANCED
    if not hunks:
        return NO_HUNK
    if len(hunks) > 1:
        return MORE_THAN_ONE_HUNK
    at, ours, theirs = hunks[0]
    return "".join(out_lines[:at]), (ours, theirs), "".join(out_lines[at:])


def _date(value):
    """*value* as a date, or None when it is not an ISO calendar date."""
    if not review_docs.ISO_DATE.match(value):
        return None
    try:
        return datetime.datetime.strptime(value, _DATE_FORMAT).date()
    except ValueError:
        return None


def resolve_stamp_conflict(data):
    """(bytes, RESOLVED) when *data*, a file copier left conflicted, is a
    stamp-only conflict: the project's text with the later of the two
    `updated:` dates and no marker. (None, reason) otherwise, the reason one of
    REFUSALS. Pure: no I/O."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None, NOT_UTF8
    parsed = _hunks(text)
    if not isinstance(parsed, tuple):
        return None, parsed
    prefix, (ours, theirs), suffix = parsed
    if len(ours) != 1 or len(theirs) != 1:
        return None, SIDE_NOT_ONE_LINE
    if _eol(ours[0]) != _eol(theirs[0]):
        return None, LINE_ENDINGS_DIFFER
    sides = []
    for line in (ours[0], theirs[0]):
        whole = prefix + line + suffix
        span = review_docs.updated_span(whole)
        if span is None:
            return None, NO_FIELD
        if not (len(prefix) <= span[0] and span[1] <= len(prefix) + len(line)):
            return None, NOT_THE_STAMP_LINE
        sides.append((whole, span))
    (o_text, o_span), (t_text, t_span) = sides
    if o_text[: o_span[0]] + o_text[o_span[1] :] != (
        t_text[: t_span[0]] + t_text[t_span[1] :]
    ):
        return None, DIFFERS_OUTSIDE_STAMP
    o_date = _date(o_text[o_span[0] : o_span[1]])
    t_date = _date(t_text[t_span[0] : t_span[1]])
    if o_date is None or t_date is None:
        return None, UNPARSABLE_DATE
    later = max(o_date, t_date).strftime(_DATE_FORMAT)
    out = o_text[: o_span[0]] + later + o_text[o_span[1] :]
    return out.encode("utf-8"), RESOLVED


def _git(root, args, stdin=None):
    """git's stdout (bytes) at *root*, filters off. Raises JobError naming the
    command on any failure."""
    try:
        argv = review_docs.git_argv(root, *args)
        env = child_env.build_child_env()
    except (review_docs.GitConfigError, child_env.ChildEnvError) as e:
        raise JobError("git %s: %s" % (args[0], e)) from e
    try:
        proc = subprocess.run(
            argv,
            cwd=root,
            input=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
    except OSError as e:
        raise JobError("git %s: %s" % (args[0], e)) from e
    if proc.returncode != 0:
        raise JobError(
            "git %s: %s"
            % (" ".join(args), os.fsdecode(proc.stderr).strip() or "failed")
        )
    return proc.stdout


def unmerged(root):
    """{path: {stage: (mode, sha)}} for every path `git ls-files -u` lists."""
    found = {}
    out = _git(root, ["ls-files", "-u", "-z"])
    for entry in out.split(b"\0"):
        if not entry:
            continue
        meta, _, path = os.fsdecode(entry).partition("\t")
        mode, sha, stage = meta.split(" ")
        found.setdefault(path, {})[stage] = (mode, sha)
    return found


def _skip(root, rel, stages):
    """A SKIPS reason when *rel* must not be read, else None."""
    if not rel.endswith(_MD):
        return NOT_MARKDOWN
    if "2" not in stages:
        return NO_PROJECT_SIDE
    if "3" not in stages:
        return NO_TEMPLATE_SIDE
    full = os.path.join(root, *rel.split("/"))
    if os.path.islink(full):
        return SYMLINK
    if not os.path.lexists(full):
        return ABSENT
    if not os.path.isfile(full):
        return NOT_A_FILE
    return None


def _write_atomic(path, data):
    """Replace *path* with *data* in one rename, keeping its mode, so a reader
    or a crash never sees half a document (restamp_docs' shape, restated so
    neither job imports the other)."""
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


def run(root):
    """(resolved, left, failed): the paths resolved, (path, reason) for each
    one left, and failure messages. Raises JobError when the worklist cannot be
    read."""
    resolved, left, failed = [], [], []
    staged = []
    for rel, stages in sorted(unmerged(root).items()):
        reason = _skip(root, rel, stages)
        if reason is not None:
            left.append((rel, reason))
            continue
        full = os.path.join(root, *rel.split("/"))
        try:
            with open(full, "rb") as fh:
                data = fh.read()
        except OSError as e:
            failed.append("%s: %s" % (rel, e))
            continue
        out, reason = resolve_stamp_conflict(data)
        if out is None:
            left.append((rel, reason))
            continue
        try:
            _write_atomic(full, out)
        except OSError as e:
            failed.append("%s: %s" % (rel, e))
            continue
        mode, sha = stages["2"]
        staged.append("0 %s\t%s\0%s %s 0\t%s\0" % (_NULL_SHA, rel, mode, sha, rel))
        resolved.append(rel)
    if staged:
        # One call, mode-0 removal before the stage-0 entry, as copier records
        # the stages itself; -z so no path needs quoting.
        try:
            _git(
                root,
                ["update-index", "-z", "--index-info"],
                os.fsencode("".join(staged)),
            )
        except JobError as e:
            failed.append(
                "%s; the markers are gone from %s but the index still lists "
                "them unmerged" % (e, ", ".join(resolved))
            )
            resolved = []
    return resolved, left, failed


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Resolve each copier conflict whose only hunk is a "
        "document's frontmatter updated: stamp, to the later date. Every other "
        "conflict is left as copier wrote it and named."
    )
    parser.add_argument(
        "--root", default=None, help="the project (default: the current directory)"
    )
    parser.add_argument(
        "--quiet", action="store_true", help="no resolved count; left paths still named"
    )
    parser.add_argument(
        conflict_guard.FINISH_FLAG,
        dest="finish_with",
        metavar="PYTHON",
        default=None,
        help="run as a copier update migration: a refusal names the command "
        "that finishes the update under this interpreter",
    )
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root or os.getcwd())
    try:
        resolved, left, failed = run(root)
    except JobError as e:
        sys.stderr.write("resolve_stamp_conflicts: %s\n" % e)
        return 2
    if not args.quiet and (resolved or left or failed):
        sys.stderr.write("resolved %d stamp-only conflict(s)\n" % len(resolved))
    for rel, reason in left:
        sys.stderr.write("left %s: %s\n" % (rel, reason))
    for message in failed:
        sys.stderr.write("resolve_stamp_conflicts: %s\n" % message)
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
