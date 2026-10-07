#!/usr/bin/env python3
"""
title: keep_edited_retired — puts back a file the template retired but the project edited
kind: script
layer: n/a
summary: Copier's first `after` migration on update. copier's `_remove_old_files` deletes every file the old render had and the new one lacks before any migration runs, whether the project edited it or not (measured on copier 9.17), so an edit to a file the template retired or moved -- an ADR that became docs/adr/keel/K-NNNN-<slug>.md -- would be lost without a word. This job lists the files the update deleted (`git diff-index --name-only --diff-filter=D HEAD` in the project, read-only: plumbing that writes no index, `--no-optional-locks`, filters off through review_docs' `git_argv`) and compares each one's HEAD bytes with the template's blob at `--from` (the commit the project was generated from). `is_edited` calls a copy unedited only when the two differ in nothing but the frontmatter `updated:` value, read through review_docs' `updated_span`; an edited copy is put back from HEAD with HEAD's mode (an executable, a symlink) and named on stderr with its successor in the template where a rename says so. A file the template renders from `<path>.jinja` cannot be judged byte for byte, so it is put back and named; so is a path the template does not hold at `--from`. The index is never written. An unresolvable `--from` or a git failure puts back every deleted file and exits 2, because without a base nothing may stay deleted. scripts/audit_project.py's `retired` group imports `is_edited`, so the guard and the audit cannot disagree. It runs before the answer-driven `rm` migrations, which still win, and before the restamp, which stays last.
effect: writes
rerun: fixed-point
rerun_proof: test:tests/integration/test_edited_retired_files.py
"""

# 3.6-safe and stdlib-only on purpose: copier runs this under its own
# interpreter in a project that may have no virtualenv yet, and the host
# python3 here is 3.6.
import argparse
import os
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

import child_env  # noqa: E402
import review_docs  # noqa: E402

# git tree modes this job can put back. Any other mode (a submodule, 160000)
# is not a file the template ships, so it is a stated failure, never a guess.
_MODE_FILE = "100644"
_MODE_EXEC = "100755"
_MODE_LINK = "120000"
_RESTORABLE = (_MODE_FILE, _MODE_EXEC, _MODE_LINK)
# check_N's twin suffix, restated rather than imported: this job must not
# import check_structure, whose copy in a project mid-update may be conflicted.
_TEMPLATE_SUFFIX = ".jinja"


class GuardError(Exception):
    """git failed, or a path cannot be judged or put back."""


def is_edited(head_bytes, template_bytes):
    """True when *head_bytes* (the project's copy) differs from *template_bytes*
    (the template's blob it was generated from) in anything but the frontmatter
    `updated:` value. That value alone is discounted because the restamp writer
    moves it on every update; a byte outside it is the project's edit. Bytes
    that are not UTF-8, or a side with no governed stamp, are compared whole."""
    if head_bytes == template_bytes:
        return False
    try:
        head = head_bytes.decode("utf-8")
        tmpl = template_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return True
    head_span = review_docs.updated_span(head)
    tmpl_span = review_docs.updated_span(tmpl)
    if head_span is None or tmpl_span is None:
        return True
    return (
        head[: head_span[0]] + head[head_span[1] :]
        != tmpl[: tmpl_span[0]] + tmpl[tmpl_span[1] :]
    )


def _git(root, *args):
    """git's stdout (bytes) at *root*, read-only and with filters off. Raises
    GuardError on any failure, naming the command."""
    try:
        argv = review_docs.git_argv(root, "--literal-pathspecs", *args)
        env = child_env.build_child_env()
    except (review_docs.GitConfigError, child_env.ChildEnvError) as e:
        raise GuardError("git %s: %s" % (args[0], e)) from e
    try:
        proc = subprocess.run(
            argv,
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
    except OSError as e:
        raise GuardError("git %s: %s" % (args[0], e)) from e
    if proc.returncode != 0:
        raise GuardError(
            "git %s: %s"
            % (" ".join(args), os.fsdecode(proc.stderr).strip() or "failed")
        )
    return proc.stdout


def _z(out):
    """The NUL-separated entries of a `-z` listing, as str paths."""
    return [os.fsdecode(e) for e in out.split(b"\0") if e]


def deleted_paths(project):
    """The files the update deleted from the work tree, relative to *project*,
    sorted. The plumbing `diff-index`, not porcelain `diff`: `git diff HEAD`
    refreshes and rewrites .git/index even under --no-optional-locks (measured
    by tests/integration/test_edited_retired_files.py), and this job never
    writes the project's index."""
    out = _git(
        project,
        "diff-index",
        "--no-renames",
        "--relative",
        "--name-only",
        "--diff-filter=D",
        "-z",
        "HEAD",
    )
    return sorted(_z(out))


def _tree(root, rev, paths, full_tree):
    """{path: (mode, sha)} for each of *paths* that *rev* holds as a blob."""
    if not paths:
        return {}
    args = ["ls-tree", "-r", "-z"]
    if full_tree:
        args.append("--full-tree")
    out = _git(root, *(args + [rev, "--"] + list(paths)))
    found = {}
    for entry in _z(out):
        meta, _, path = entry.partition("\t")
        mode, kind, sha = meta.split(" ")
        if kind == "blob":
            found[path] = (mode, sha)
    return found


def _blob(root, sha):
    return _git(root, "cat-file", "blob", sha)


def _resolve(src, ref):
    """The commit *ref* names in *src*. A ref that reads as an option is refused
    before git sees it."""
    if not ref or ref.startswith("-"):
        raise GuardError("--from %r is not a ref this job will resolve" % ref)
    out = _git(src, "rev-parse", "--verify", "--quiet", ref + "^{commit}")
    return os.fsdecode(out).strip()


def _successors(src, base):
    """{old path: new path} for every rename in *src* between *base* and its
    HEAD, the template revision being applied. Best effort: a failure here only
    costs the `(now ...)` clause, so it returns {} rather than failing."""
    try:
        out = _git(src, "diff", "-M", "--name-status", "-z", base, "HEAD")
    except GuardError:
        return {}
    fields = _z(out)
    found = {}
    i = 0
    while i < len(fields):
        status = fields[i]
        if status.startswith(("R", "C")):
            if status.startswith("R"):
                found[fields[i + 1]] = fields[i + 2]
            i += 3
        else:
            i += 2
    return found


def _restore(project, rel, mode, data):
    """Put *rel* back with HEAD's *data* and *mode*. Writes through a temporary
    file and os.replace, so a reader never sees half a file."""
    full = os.path.join(project, *rel.split("/"))
    if os.path.lexists(full):
        raise GuardError("cannot put back %s: the path is taken" % rel)
    if mode not in _RESTORABLE:
        raise GuardError("cannot put back %s: git mode %s" % (rel, mode))
    parent = os.path.dirname(full)
    os.makedirs(parent, exist_ok=True)
    if mode == _MODE_LINK:
        os.symlink(os.fsdecode(data), full)
        return
    fd, tmp = tempfile.mkstemp(dir=parent, prefix=".keep-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, 0o755 if mode == _MODE_EXEC else 0o644)
        os.replace(tmp, full)
    except BaseException:
        if os.path.lexists(tmp):
            os.unlink(tmp)
        raise


def _restore_all(project, paths):
    """Put back every one of *paths* from HEAD; the ones that failed, as
    messages. Used when nothing can be judged."""
    failed = []
    try:
        heads = _tree(project, "HEAD", paths, False)
    except GuardError as e:
        return ["%s: %s" % (p, e) for p in paths]
    for rel in paths:
        entry = heads.get(rel)
        try:
            if entry is None:
                raise GuardError("HEAD holds no blob at %s" % rel)
            _restore(project, rel, entry[0], _blob(project, entry[1]))
        except (GuardError, OSError) as e:
            failed.append("%s: %s" % (rel, e))
    return failed


def judge(project, src, ref):
    """(kept, stays_deleted, failures): each deleted path either put back with a
    reason, left deleted, or a failure message. Raises GuardError when the
    worklist cannot be read; when *ref* cannot be resolved or git fails while
    judging, every deleted path still missing is put back first, then
    GuardError is raised."""
    paths = deleted_paths(project)
    if not paths:
        return [], [], []
    try:
        return _judge(project, src, ref, paths)
    except GuardError as e:
        missing = [
            p
            for p in paths
            if not os.path.lexists(os.path.join(project, *p.split("/")))
        ]
        failed = _restore_all(project, missing)
        raise GuardError(
            "%s; every deleted file was put back%s"
            % (e, "" if not failed else " except: " + "; ".join(failed))
        ) from e


def _judge(project, src, ref, paths):
    base = _resolve(src, ref)
    heads = _tree(project, "HEAD", paths, False)
    asked = []
    for p in paths:
        asked.extend((p, p + _TEMPLATE_SUFFIX))
    template = _tree(src, base, asked, True)
    successors = _successors(src, base)
    kept, gone, failed = [], [], []
    for rel in paths:
        head = heads.get(rel)
        if head is None:
            failed.append("%s: HEAD holds no blob there" % rel)
            continue
        head_data = _blob(project, head[1])
        if rel in template:
            if not is_edited(head_data, _blob(src, template[rel][1])):
                gone.append(rel)
                continue
            new = successors.get(rel)
            reason = "the project edited it and the template retired it%s" % (
                " (now %s)" % new if new else ""
            )
        elif rel + _TEMPLATE_SUFFIX in template:
            reason = (
                "the template renders it from %s, so whether the project "
                "edited it cannot be judged" % (rel + _TEMPLATE_SUFFIX)
            )
        else:
            reason = (
                "the template holds no %s at %s, so whether the project "
                "edited it cannot be judged" % (rel, ref)
            )
        try:
            _restore(project, rel, head[0], head_data)
        except (GuardError, OSError) as e:
            failed.append("%s: %s" % (rel, e))
            continue
        kept.append((rel, reason))
    return kept, gone, failed


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Put back each file a copier update deleted that the "
        "project had edited. Run from the project root."
    )
    parser.add_argument("--template", required=True, help="the template checkout")
    parser.add_argument(
        "--from",
        dest="ref",
        required=True,
        help="the ref the project was generated from",
    )
    parser.add_argument("--quiet", action="store_true", help="no summary on stdout")
    args = parser.parse_args(argv)
    project = os.getcwd()
    src = os.path.abspath(args.template)
    try:
        kept, gone, failed = judge(project, src, args.ref)
    except GuardError as e:
        sys.stderr.write("keep_edited_retired: %s\n" % e)
        return 2
    for rel, reason in kept:
        sys.stderr.write("kept %s: %s\n" % (rel, reason))
    for message in failed:
        sys.stderr.write("keep_edited_retired: %s\n" % message)
    if not args.quiet:
        total = len(kept) + len(gone) + len(failed)
        sys.stdout.write(
            "keep_edited_retired: %d deleted by the update, %d kept, %d left "
            "deleted, %d failed\n" % (total, len(kept), len(gone), len(failed))
        )
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
