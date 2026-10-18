"""
title: template_snapshot — the template's working tree, committed in a scratch clone
kind: script
layer: n/a
summary: The one way a keel doer renders from the checkout as it stands, uncommitted edits and untracked files included, without copier's own handling of a dirty local template, which runs a plain `git status` in the checkout and rewrites its index. `snapshot_working_tree(template, scratch, extra)` clones *template* into `<scratch>/template` (`git clone --no-hardlinks`), copies each modified and untracked path over the clone, and commits them there with `git add -A` and one commit; it returns the clone's path and a not-checked list naming what it left out: an untracked symlink (a local convenience, such as the link keel's own root carries to a sibling tree) and nothing else. A path under *skip*, root-relative, is never copied: the canary passes its scratch root, which a snapshot that copied it would copy into itself. The template is only read: the clone, scripts/jobs/review_docs.py `modified_paths` (`git --no-optional-locks status`) and `ls-files`. `scratch_env(scratch, today)` is what every child of such a run gets on top of the allowlist: a git config of its own (no user or system config, no hooks, no excludes file, no fsmonitor, no background gc), commit dates and SOURCE_DATE_EPOCH pinned to *today* at midnight UTC, so two snapshots of one tree on one day commit the same sha, and copier's settings, cache and temporary files inside *scratch*. Every child runs with `child_env.build_child_env(extra=...)`. A child that fails raises SnapshotError naming the step and the tail of its output; nothing here ends the process. Imported by scripts/audit_project.py and scripts/canary.py; keel-only, excluded from generated projects with both.
effect: writes
rerun: fixed-point
rerun_proof: test:tests/unit/scripts/test_template_snapshot.py
"""

from __future__ import annotations

import calendar
import os
import shutil
import subprocess
import sys

_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
for _dir in (_SCRIPTS, os.path.join(_SCRIPTS, "jobs")):
    if _dir not in sys.path:
        sys.path.insert(0, _dir)

import child_env  # noqa: E402
import review_docs  # noqa: E402

__all__ = ["GITCONFIG", "SnapshotError", "scratch_env", "snapshot_working_tree"]

# The git every child in a scratch tree runs under: no user or system config
# of the machine, no hook (a commit in a copy must run nothing of the
# project's or the user's), no excludes file, no fsmonitor, no background gc.
GITCONFIG = (
    "[user]\n\tname = keel audit\n\temail = keel-audit@example.invalid\n"
    "[init]\n\tdefaultBranch = main\n"
    "[commit]\n\tgpgsign = false\n"
    "[tag]\n\tgpgSign = false\n"
    "[core]\n\thooksPath = %s\n\texcludesFile = %s\n\tfsmonitor = false\n"
    "[gc]\n\tauto = 0\n"
) % (os.devnull, os.devnull)

# The lines of a failed child's output a SnapshotError carries.
_TAIL = 8

_SYMLINK_REASON = (
    "an untracked symlink in the template checkout: not in the snapshot the "
    "update renders from (`git add` it to include it)"
)


class SnapshotError(Exception):
    """A child of the snapshot failed, or git would not list the checkout."""


def scratch_env(scratch, today):
    """The variables every child of a run under *scratch* gets on top of the
    allowlist (`extra=` of `child_env.build_child_env`), writing the git config
    and copier settings they name and creating `<scratch>/tmp`."""
    gitconfig = os.path.join(scratch, "gitconfig")
    settings = os.path.join(scratch, "copier-settings.yml")
    tmp = os.path.join(scratch, "tmp")
    os.mkdir(tmp)
    with open(gitconfig, "w", encoding="utf-8") as fh:
        fh.write(GITCONFIG)
    with open(settings, "w", encoding="utf-8") as fh:
        fh.write("{}\n")
    epoch = calendar.timegm(today.timetuple())
    date = "@%d +0000" % epoch
    return {
        "GIT_CONFIG_GLOBAL": gitconfig,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_DATE": date,
        "GIT_COMMITTER_DATE": date,
        "SOURCE_DATE_EPOCH": str(epoch),
        "COPIER_SETTINGS_PATH": settings,
        "XDG_CACHE_HOME": os.path.join(scratch, "cache"),
        "TMPDIR": tmp,
        "TMP": tmp,
        "TEMP": tmp,
    }


def _child(argv, cwd, extra, what):
    proc = subprocess.run(
        argv,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        env=child_env.build_child_env(extra=extra),
    )
    if proc.returncode != 0:
        lines = [ln for ln in (proc.stderr or proc.stdout).splitlines() if ln.strip()]
        raise SnapshotError(
            "%s failed (exit %d): %s"
            % (what, proc.returncode, " | ".join(lines[-_TAIL:]) or "no output")
        )
    return proc.stdout


def _untracked(template):
    """The checkout's untracked, not-ignored files, read the judge's way: no
    index write-back and no command the checkout's git config names."""
    try:
        argv = review_docs.git_argv(
            template, "ls-files", "--others", "--exclude-standard", "-z"
        )
    except review_docs.GitConfigError as exc:
        raise SnapshotError(
            "cannot list the template's filter drivers: %s" % exc
        ) from exc
    out = _child(argv, template, None, "listing the template's untracked files")
    return {p for p in out.split("\0") if p and not p.endswith("/")}


def _skipped(rel, skip):
    parts = rel.split("/")
    for root in skip:
        head = [p for p in root.replace(os.sep, "/").split("/") if p not in ("", ".")]
        if head and parts[: len(head)] == head:
            return True
    return False


def snapshot_working_tree(template, scratch, extra, skip=(), label="snapshot"):
    """(path, not_checked): a clone of *template* at `<scratch>/template` with
    its uncommitted state committed on top under the message
    `<label>: checkout state`, and what it left out. *extra* is scratch_env's
    result; a root-relative path in *skip* is never copied."""
    snap = os.path.join(scratch, "template")
    not_checked = []
    _child(
        ["git", "clone", "-q", "--no-hardlinks", template, snap],
        scratch,
        extra,
        "git clone of the template checkout",
    )
    dirty = review_docs.modified_paths(template)
    if dirty is None:
        raise SnapshotError("git refused to list the template checkout's changes")
    untracked = _untracked(template)
    for rel in sorted(dirty | untracked):
        if _skipped(rel, skip):
            continue
        src, dst = os.path.join(template, rel), os.path.join(snap, rel)
        if rel in untracked and os.path.islink(src):
            not_checked.append({"item": rel, "reason": _SYMLINK_REASON})
            continue
        if os.path.lexists(dst) and not os.path.isdir(dst):
            os.remove(dst)
        if os.path.islink(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.symlink(os.readlink(src), dst)
        elif os.path.isfile(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
    if dirty or untracked:
        _child(["git", "add", "-A"], snap, extra, "git add in the snapshot")
        _child(
            [
                "git",
                "commit",
                "-q",
                "--allow-empty",
                "-m",
                "%s: checkout state" % label,
            ],
            snap,
            extra,
            "git commit in the snapshot",
        )
    return snap, not_checked
