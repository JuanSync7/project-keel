#!/usr/bin/env python3
"""
title: keep_edited_retired — puts back a file the template retired but the project edited
kind: script
layer: n/a
summary: Copier's first `after` migration on update. copier's `_remove_old_files` deletes every file the old render had and the new one lacks before any migration runs, whether the project edited it or not (measured on copier 9.17), so an edit to a file the template retired or moved -- an ADR that became docs/adr/keel/K-NNNN-<slug>.md -- would be lost without a word. This job lists the files the update deleted (`git diff-index --name-only --diff-filter=D HEAD` in the project, read-only: plumbing that writes no index, `--no-optional-locks`, filters off through review_docs' `git_argv`) and compares each one's HEAD bytes with the template's blob at `--from` (the commit the project was generated from). `is_edited` calls a copy unedited only when the two differ in nothing but the frontmatter `updated:` value, read through review_docs' `updated_span`; an edited copy is put back from HEAD with HEAD's mode (an executable, a symlink) and named on stderr with its successor in the template where a rename says so. A file the template renders from `<path>.jinja` is judged against that twin rendered (jinja2's sandbox, strict undefined) with the answers file HEAD holds (`--answers`); one that will not render is put back and named, and so is a path the template does not hold at `--from`. Each `--retire NAME:PATH` is a CI adapter the `ci_pipeline` answer declines, judged in the same run by the same verdict, so one file never gets two: removed when it is byte-equal to keel's render, else kept with one stderr line that says whether it carries the `--marker` line filled with NAME, why it is kept, and that CI runs it beside the chosen adapter until `git rm PATH`. The index is never written. An unresolvable `--from` or a git failure puts back every deleted file and exits 2, because without a base nothing may stay deleted. scripts/audit_project.py's `retired` group imports `is_edited`, so the guard and the audit cannot disagree. It runs before the other answer-driven `rm` migrations, which still win, and before the restamp, which stays last. Run as a script, it first asks scripts/jobs/conflict_guard.py whether a module it imports from the project, or a fixed project file those modules declare reading in `PROJECT_READS`, holds a conflict hunk, and if one does it names each file and the rerun command (run as a migration with `--finish-with`, the command that finishes the update) and exits 2 instead of dying on the import or the read.
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

import conflict_guard  # noqa: E402

# Before every import below: copier runs this in a project mid-update,
# where a module it imports may hold conflict markers, and that import
# would die on a SyntaxError traceback naming neither the file nor the
# remedy. Only when run as a script: an importer's imports are its own.
if __name__ == "__main__":
    conflict_guard.exit_if_conflicted(
        __file__,
        os.path.dirname(_SCRIPTS),
        "keep_edited_retired",
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
from exit_codes import ExitCode, finish, report  # noqa: E402

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


def judge(project, src, ref, retire=None, marker=None, answers_rel=None):
    """(kept, stays_deleted, failures): each judged path either kept with a
    reason, left deleted (or removed), or a failure message. The paths judged
    are the ones the update deleted plus each path of *retire* ({path: adapter
    name}, the files the answers retire) still on disk; *marker* is the line
    format keel's adapter carries and the answers file a `.jinja`
    twin renders with (*answers_rel*, read from HEAD). Raises GuardError when the worklist cannot be read;
    when *ref* cannot be resolved or git fails while judging, every deleted
    path still missing is put back first, then GuardError is raised."""
    retire = retire or {}
    paths = deleted_paths(project)
    on_disk = [
        p
        for p in sorted(retire)
        if p not in paths and os.path.lexists(os.path.join(project, *p.split("/")))
    ]
    if not paths and not on_disk:
        return [], [], []
    try:
        return _judge(project, src, ref, paths, on_disk, retire, marker, answers_rel)
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


def _answers(project, entry):
    """The answers *entry* (HEAD's (mode, sha) of the answers file) records, as
    a dict, or None when there is none or it cannot be read: yaml is copier's
    own dependency, so it is imported only here, and its absence only leaves a
    twin unjudged."""
    if entry is None:
        return None
    try:
        import yaml
    except ImportError:
        return None
    try:
        found = yaml.safe_load(_blob(project, entry[1]).decode("utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError):
        return None
    return found if isinstance(found, dict) else None


def _render(data, answers):
    """*data*, a `.jinja` blob, rendered with *answers* the way copier renders
    a file (jinja2's sandbox, the trailing newline kept, an undefined name an
    error), or None when it cannot be: no answers, no jinja2, or a template
    error. None only ever keeps a file, never removes one."""
    if answers is None:
        return None
    try:
        from jinja2 import StrictUndefined, TemplateError
        from jinja2.sandbox import SandboxedEnvironment
    except ImportError:
        return None
    env = SandboxedEnvironment(keep_trailing_newline=True, undefined=StrictUndefined)
    try:
        return env.from_string(data.decode("utf-8")).render(answers).encode("utf-8")
    except (TemplateError, UnicodeDecodeError, TypeError):
        return None


def _keel_render(src, template, rel, answers):
    """(the bytes keel rendered at *rel* at the base, why not): the template's
    blob, or its `.jinja` twin rendered with the project's answers; None with
    "absent" when the template held neither, "twin" when the twin would not
    render."""
    if rel in template:
        return _blob(src, template[rel][1]), None
    if rel + _TEMPLATE_SUFFIX in template:
        rendered = _render(_blob(src, template[rel + _TEMPLATE_SUFFIX][1]), answers)
        return rendered, None if rendered is not None else "twin"
    return None, "absent"


def _has_line(data, line):
    try:
        return line in data.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return False


def _retired_reason(rel, ref, data, keel, why, name, marker):
    """Why an answer-retired file is kept, and what the user must do, in one
    clause pair: whether it still carries keel's marker line, and that the
    adapter it is keeps running until the user removes it."""
    line = marker.format(adapter=name)
    if why == "absent":
        reason = "the template held no %s at %s, so keel did not write it" % (rel, ref)
    elif why == "twin":
        reason = (
            "the template renders it from %s, which would not render with the "
            "project's answers, so whether the project edited it cannot be "
            "judged" % (rel + _TEMPLATE_SUFFIX)
        )
    elif _has_line(data, line):
        reason = (
            "it carries the line `%s`, so keel wrote it, and the project edited it"
            % line
        )
    elif _has_line(keel, line):
        reason = (
            "it has no line `%s`, so the project wrote it or removed that line" % line
        )
    else:
        reason = (
            "it has no line `%s` because keel wrote it before that line "
            "existed, and the project edited it" % line
        )
    return (
        "%s; ci_pipeline no longer chooses %s, so CI keeps running this file's "
        "steps beside the chosen adapter's until you remove it (`git rm %s`)"
        % (reason, name, rel)
    )


def _judge(project, src, ref, paths, on_disk, retire, marker, answers_rel):
    base = _resolve(src, ref)
    worklist = sorted(set(paths) | set(on_disk))
    heads = _tree(
        project, "HEAD", worklist + ([answers_rel] if answers_rel else []), False
    )
    answers = _answers(project, heads.get(answers_rel)) if answers_rel else None
    asked = []
    for p in worklist:
        asked.extend((p, p + _TEMPLATE_SUFFIX))
    template = _tree(src, base, asked, True)
    successors = _successors(src, base)
    kept, gone, failed = [], [], []
    for rel in worklist:
        full = os.path.join(project, *rel.split("/"))
        if rel in on_disk:
            # Still on disk (copier did not delete it), so its own bytes are
            # what a removal would lose.
            if os.path.islink(full) or not os.path.isfile(full):
                kept.append((rel, "it is not a regular file, so it is not keel's"))
                continue
            with open(full, "rb") as fh:
                data = fh.read()
            head = None
        else:
            head = heads.get(rel)
            if head is None:
                failed.append("%s: HEAD holds no blob there" % rel)
                continue
            data = _blob(project, head[1])
        keel, why = _keel_render(src, template, rel, answers)
        if keel is not None and not is_edited(data, keel):
            if head is None:
                try:
                    os.unlink(full)
                except OSError as e:
                    failed.append("%s: cannot remove it: %s" % (rel, e))
                    continue
            gone.append(rel)
            continue
        if rel in retire:
            reason = _retired_reason(rel, ref, data, keel, why, retire[rel], marker)
        elif why == "absent":
            reason = (
                "the template holds no %s at %s, so whether the project "
                "edited it cannot be judged" % (rel, ref)
            )
        elif why == "twin":
            reason = (
                "the template renders it from %s, so whether the project "
                "edited it cannot be judged" % (rel + _TEMPLATE_SUFFIX)
            )
        else:
            new = successors.get(rel)
            reason = "the project edited it and the template retired it%s" % (
                " (now %s)" % new if new else ""
            )
        if head is not None:
            try:
                _restore(project, rel, head[0], data)
            except (GuardError, OSError) as e:
                failed.append("%s: %s" % (rel, e))
                continue
        kept.append((rel, reason))
    return kept, gone, failed


def _retire_map(values, marker):
    """{path: adapter name} from each `--retire NAME:PATH`; an empty value, the
    form copier renders when the answer retires nothing, is skipped. Raises
    GuardError on a value that is not NAME:PATH, or on one given without
    `--marker`."""
    found = {}
    for value in values:
        if not value:
            continue
        name, sep, path = value.partition(":")
        if not sep or not name or not path:
            raise GuardError("--retire %r is not NAME:PATH" % value)
        found[path] = name
    if found and not marker:
        raise GuardError("--retire needs --marker, the line keel's adapter carries")
    return found


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
    parser.add_argument(
        "--retire",
        action="append",
        default=[],
        metavar="NAME:PATH",
        help="a CI adapter the answers no longer choose: removed when unedited, "
        "else kept and named; an empty value retires nothing",
    )
    parser.add_argument(
        "--marker",
        default=None,
        help="the line keel's adapter carries, with {adapter} for its name",
    )
    parser.add_argument(
        "--answers",
        default=None,
        help="the answers file a `.jinja` twin renders with, read from HEAD",
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
    project = os.getcwd()
    src = os.path.abspath(args.template)
    try:
        retire = _retire_map(args.retire, args.marker)
        kept, gone, failed = judge(
            project, src, args.ref, retire, args.marker, args.answers
        )
    except GuardError as e:
        return report(
            ExitCode.USAGE,
            "keep_edited_retired: cannot judge the files the update deleted",
            str(e),
            "fix what it names, then finish the update",
        )
    for rel, reason in kept:
        sys.stderr.write("kept %s: %s\n" % (rel, reason))
    for message in failed:
        sys.stderr.write("keep_edited_retired: %s\n" % message)
    if not args.quiet:
        total = len(kept) + len(gone) + len(failed)
        sys.stdout.write(
            "keep_edited_retired: %d judged, %d kept, %d left deleted, "
            "%d failed\n" % (total, len(kept), len(gone), len(failed))
        )
    if not failed:
        return ExitCode.SUCCESS
    return report(
        ExitCode.USAGE,
        "keep_edited_retired: an edited file the update deleted was not put back",
        "%d file(s), each named above" % len(failed),
        "restore each from git by hand, then finish the update",
    )


if __name__ == "__main__":
    finish(main())
