#!/usr/bin/env python3
"""
title: canary — each configured answer set rendered fresh and as an update, then its own make verify
kind: script
layer: n/a
summary: Answers "does a project keel generates today pass its own gate, and does one generated from the last release still pass after `copier update`?" for each config/project.json `canary.answer_sets` set, before a release is pushed. A set key that is not a question copier.yml asks is refused with CONFIG before anything renders, because copier would ignore it and render the default. The update path needs the previous release first: the newest dated `## [X.Y.Z] — YYYY-MM-DD` heading of CHANGELOG.md whose tag (`vX.Y.Z`, else `X.Y.Z`) exists and is a strict ancestor of HEAD, so a run on the release commit updates from the release before; with none it refuses with USAGE before anything renders, and `--path fresh` needs no tag. The checkout as it stands, uncommitted edits included, is snapshotted once with scripts/template_snapshot.py into `<canary.scratch_root>/<run-id>/template`; each set and path then renders into `<run-id>/<set>-<path>` in a pool of `canary.workers`, every future waited on and no set skipped after a red one. The fresh path is `copier copy --vcs-ref HEAD` and a commit; the update path is `copier copy --vcs-ref <tag>`, a commit, `copier update --data-file <the set> --vcs-ref HEAD --conflict inline`, the set given again so a question the tag did not ask takes the set's answer, which fails the step `update` when git lists an unmerged path or a file holds a conflict hunk (scripts/jobs/conflict_guard.py `has_conflict`), and a commit. Both then run `make fe-install` and `make fe-browsers`, which exit 0 when the project's Makefile `FE_APPS` names no frontend app, then `make verify`, each step killed past `canary.step_timeout_minutes`. Each set and path prints `<set> <path> <last step reached> <pass|fail> <log> <elapsed>s`; a passing project is deleted and a failing one kept and named on stderr, with its log beside it. The scratch root is refused (CONFIG) under the system temporary directory, and inside the checkout unless git ignores it and tracks nothing in it. `--set NAME` (repeatable) and `--path` choose the work, so the farm can run one job per set. Every child runs with `child_env.build_child_env(extra=...)` and the hermetic git `template_snapshot.scratch_env` writes. Keel-only: copier.yml excludes it, and a generated project's `make canary` is a stub naming the template checkout.
effect: writes
rerun: fixed-point
rerun_proof: test:tests/unit/scripts/test_canary.py
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures
import datetime
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import traceback

_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
for _dir in (_SCRIPTS, os.path.join(_SCRIPTS, "jobs")):
    if _dir not in sys.path:
        sys.path.insert(0, _dir)

import child_env  # noqa: E402
import config_loader  # noqa: E402
import conflict_guard  # noqa: E402
import run_date  # noqa: E402
from exit_codes import ExitCode, finish, report  # noqa: E402
from template_snapshot import (  # noqa: E402
    SnapshotError,
    scratch_env,
    snapshot_working_tree,
)

# The template checkout the canary renders: the one this file ships in.
ROOT = os.path.dirname(_SCRIPTS)
CHANGELOG = "CHANGELOG.md"
PATHS = ("fresh", "update")

_KEYS = (
    ("canary", "answer_sets"),
    ("canary", "scratch_root"),
    ("canary", "step_timeout_minutes"),
    ("canary", "workers"),
)
# A set name becomes a directory and a file name, so it is one plain segment.
_SET_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
# A released version's heading: `## [X.Y.Z] — YYYY-MM-DD` at column 0. The
# date is parsed below, so `2026-13-40` names no release.
_RELEASE = re.compile(r"^## \[(\d+\.\d+\.\d+)\] — (\d{4}-\d{2}-\d{2})\s*$")

# Every callable is (args, cwd, log) -> (status, log): copier and make take
# their own arguments, git its subcommand and arguments, and each appends the
# child's output to *log*. remove(path) deletes a passing project. A None field
# is the real tool, bound to the run's environment and step timeout.
Runner = collections.namedtuple(
    "Runner", "copier git make remove", defaults=(None, None, None, None)
)

_Result = collections.namedtuple("_Result", "name path step verdict log elapsed dest")


class CanaryError(Exception):
    """A question about the template checkout got no usable answer: git
    exited with a status that means neither yes nor no, or copier.yml could
    not be read."""


def asked_questions(root):
    """The names of the questions copier.yml at *root* asks: its top-level
    keys not starting with `_`, less any whose `when` is literally false,
    which copier computes and never takes from an answer."""
    # Imported here: PyYAML comes with copier (the template extra), which the
    # real canary needs anyway, while the unit tests run without it.
    try:
        import yaml
    except ImportError as exc:
        raise CanaryError(
            "PyYAML, which copier brings, is not importable: %s" % exc
        ) from exc
    path = os.path.join(root, "copier.yml")
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError) as exc:
        raise CanaryError("%s: %s" % (path, exc)) from exc
    if not isinstance(data, dict):
        raise CanaryError("%s: the top level is not a mapping" % path)
    return {
        str(key)
        for key, spec in data.items()
        if not str(key).startswith("_")
        and not (isinstance(spec, dict) and spec.get("when") is False)
    }


def released_versions(text):
    """The X.Y.Z of each dated release heading of CHANGELOG *text*, in file
    order (newest first)."""
    out = []
    for line in text.splitlines():
        match = _RELEASE.match(line)
        if not match:
            continue
        try:
            datetime.datetime.strptime(match.group(2), "%Y-%m-%d")
        except ValueError:
            continue
        out.append(match.group(1))
    return out


def _yes(git, args, cwd):
    """True for status 0, False for 1, CanaryError for any other."""
    status, _ = git(list(args), cwd, os.devnull)
    if status not in (0, 1):
        raise CanaryError("git %s exited %s" % (" ".join(args), status))
    return status == 0


def previous_tag(text, git, cwd):
    """The tag of the newest released heading of CHANGELOG *text* that exists
    in the repository at *cwd* and is a strict ancestor of its HEAD, or None."""
    for version in released_versions(text):
        for tag in ("v" + version, version):
            if not _yes(
                git, ["rev-parse", "--verify", "--quiet", tag + "^{commit}"], cwd
            ):
                continue
            # A tag on HEAD itself is the release being made, not the last one.
            if _yes(
                git, ["merge-base", "--is-ancestor", tag, "HEAD"], cwd
            ) and not _yes(git, ["merge-base", "--is-ancestor", "HEAD", tag], cwd):
                return tag
    return None


def _spawn(argv, cwd, log, extra, timeout):
    """(status, log) of *argv* at *cwd*, its output appended to *log*; the
    child's whole process group is killed past *timeout* seconds."""
    with open(log, "a", encoding="utf-8") as fh:
        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=fh,
            stderr=subprocess.STDOUT,
            env=child_env.build_child_env(extra=extra),
            # Its own group, so a timeout kills npm's and make's grandchildren too.
            start_new_session=True,
        )
        try:
            status = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            fh.write(
                "\ncanary: killed after %d s (config/project.json "
                "canary.step_timeout_minutes)\n" % timeout
            )
            return proc.returncode, log
        except BaseException:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            raise
    return status, log


def _bound(runner, extra, timeout):
    """*runner* with each None field replaced by the real tool."""

    def copier(args, cwd, log):
        return _spawn(
            [sys.executable, "-m", "copier"] + list(args), cwd, log, extra, timeout
        )

    def git(args, cwd, log):
        return _spawn(["git"] + list(args), cwd, log, extra, timeout)

    def make(args, cwd, log):
        venv = os.path.join(cwd, ".venv", "bin", "python")
        py = venv if os.path.isfile(venv) else sys.executable
        return _spawn(["make", "PY=%s" % py] + list(args), cwd, log, extra, timeout)

    return Runner(
        copier=runner.copier or copier,
        git=runner.git or git,
        make=runner.make or make,
        remove=runner.remove or shutil.rmtree,
    )


def _under(path, root):
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def _scratch_fault(scratch, git):
    """Why *scratch* (a realpath) may not hold the canary's projects, or None."""
    systemp = os.path.realpath(tempfile.gettempdir())
    # /tmp is often memory-backed and shared: four rendered projects with their
    # node_modules and browsers do not belong there.
    if _under(scratch, systemp):
        return "%s is under the system temporary directory %s" % (scratch, systemp)
    root = os.path.realpath(ROOT)
    if not _under(scratch, root):
        return None
    rel = os.path.relpath(scratch, root).replace(os.sep, "/")
    # A tracked file under it would be deleted by the run that replaces it.
    if rel == "." or _yes(git, ["ls-files", "--error-unmatch", "--", rel], root):
        return "%s holds files git tracks" % rel
    if not _yes(git, ["check-ignore", "-q", "--no-index", rel + "/"], root):
        return "%s is inside the checkout and git does not ignore it" % rel
    return None


def _say(lock, text):
    with lock:
        sys.stderr.write("canary: %s\n" % text)
        sys.stderr.flush()


def _write_header(log, args, cwd):
    with open(log, "a", encoding="utf-8") as fh:
        fh.write("$ %s  (in %s)\n" % (" ".join(shlex.quote(a) for a in args), cwd))


def _marked(dest):
    """The first file under *dest* holding a conflict hunk, or None."""
    for here, dirs, files in os.walk(dest):
        dirs[:] = sorted(d for d in dirs if d != ".git")
        for name in sorted(files):
            path = os.path.join(here, name)
            if os.path.islink(path):
                continue
            with open(path, "rb") as fh:
                text = fh.read().decode("utf-8", "replace")
            if conflict_guard.has_conflict(text):
                return os.path.relpath(path, dest)
    return None


class _Pair(object):
    """One set and path: its steps, run in order until one fails."""

    def __init__(self, name, path, run, snap, answers, tag, tools, lock):
        self.name, self.path, self.run = name, path, run
        self.snap, self.answers, self.tag = snap, answers, tag
        self.tools, self.lock = tools, lock
        self.dest = os.path.join(run, "%s-%s" % (name, path))
        self.log = self.dest + ".log"
        self.step = None

    def _call(self, tool, step, args, cwd):
        self.step = step
        _write_header(self.log, args, cwd)
        status, _ = getattr(self.tools, tool)(list(args), cwd, self.log)
        if status != 0:
            with open(self.log, "a", encoding="utf-8") as fh:
                fh.write("canary: %s exited %s\n" % (step, status))
        return status == 0

    def _commit(self, message):
        return all(
            self._call("git", "commit", args, self.dest)
            for args in (
                ["init", "-q"],
                ["add", "-A"],
                ["commit", "-q", "--allow-empty", "-m", message],
            )
        )

    def _copy(self, ref):
        return self._call(
            "copier",
            "copy",
            [
                "copy",
                "--trust",
                "--defaults",
                "--data-file",
                self.answers,
                "--vcs-ref",
                ref,
                self.snap,
                self.dest,
            ],
            self.run,
        )

    def _update_is_clean(self):
        ok = self._call(
            "copier",
            "update",
            [
                "update",
                "--trust",
                "--defaults",
                "--skip-answered",
                "--quiet",
                # The set again: the copy from the tag ignored any answer to a
                # question the tag does not ask, and the update would otherwise
                # take that question's default.
                "--data-file",
                self.answers,
                "--vcs-ref",
                "HEAD",
                "--conflict",
                "inline",
                self.dest,
            ],
            self.dest,
        )
        if not ok:
            return False
        unmerged = self.dest + ".unmerged"
        with open(unmerged, "w", encoding="utf-8"):
            pass
        status, _ = self.tools.git(["ls-files", "-u", "-z"], self.dest, unmerged)
        with open(unmerged, encoding="utf-8") as fh:
            listed = fh.read()
        marked = _marked(self.dest)
        with open(self.log, "a", encoding="utf-8") as fh:
            if status != 0:
                fh.write("canary: git ls-files -u exited %s\n" % status)
            if listed.strip("\0\n "):
                fh.write("canary: the update left unmerged paths:\n%s\n" % listed)
            if marked:
                fh.write("canary: the update left a conflict hunk in %s\n" % marked)
        return status == 0 and not listed.strip("\0\n ") and marked is None

    def steps(self):
        if self.path == "fresh":
            if not (self._copy("HEAD") and self._commit("canary: fresh render")):
                return False
        else:
            if not (
                self._copy(self.tag) and self._commit("canary: render %s" % self.tag)
            ):
                return False
            if not self._update_is_clean():
                return False
            if not self._commit("canary: update to HEAD"):
                return False
        # Both targets exit 0 in a project with no frontend app: the Makefile's
        # FE_APPS is the one statement of where apps live.
        for target in ("fe-install", "fe-browsers"):
            if not self._call("make", target, [target], self.dest):
                return False
        return self._call("make", "verify", ["verify"], self.dest)

    def __call__(self):
        began = time.monotonic()
        passed = False
        try:
            passed = self.steps()
        except Exception:  # noqa: BLE001 — any raise fails this pair, traceback logged
            with open(self.log, "a", encoding="utf-8") as fh:
                fh.write(
                    "canary: the %s step raised\n%s"
                    % (self.step, traceback.format_exc())
                )
        finally:
            if passed:
                if os.path.lexists(self.dest):
                    self.tools.remove(self.dest)
            else:
                _say(
                    self.lock,
                    "kept %s (%s %s failed at %s; log %s)"
                    % (self.dest, self.name, self.path, self.step, self.log),
                )
        return _Result(
            self.name,
            self.path,
            self.step,
            "pass" if passed else "fail",
            self.log,
            int(round(time.monotonic() - began)),
            None if passed else self.dest,
        )


def _settings():
    """{key: value} of the canary rows; ConfigError from the loader."""
    loaded = config_loader.read(ROOT)
    values = config_loader.resolve(
        loaded, config_loader.rows(*_KEYS), config_loader.CONFIG_FILE
    )
    return {path[-1]: value for path, value in values.items()}


def _parse(argv):
    parser = argparse.ArgumentParser(
        prog="scripts/canary.py",
        description="Render each config/project.json canary.answer_sets set fresh "
        "and as an update from the previous release tag, and run its make verify.",
    )
    parser.add_argument(
        "--set",
        action="append",
        dest="sets",
        metavar="NAME",
        help="Run only this answer set; repeat for more (default: every set).",
    )
    parser.add_argument(
        "--path",
        choices=("fresh", "update", "both"),
        default="both",
        help="Render fresh, as an update from the previous release, or both.",
    )
    return parser.parse_args(argv)


def main(argv=None, runner=None):
    args = _parse(argv)
    try:
        settings = _settings()
        scratch_var = config_loader.rows(("canary", "scratch_root"))[0].env
        from_env = config_loader.env(scratch_var) is not None
    except config_loader.ConfigError as exc:
        return report(
            ExitCode.CONFIG,
            "the canary settings are refused",
            "; ".join(exc.lines),
            "fix the canary block of config/project.json, then rerun",
        )
    sets = settings["answer_sets"]
    bad = sorted(
        name
        for name, answers in sets.items()
        if not _SET_NAME.match(name) or not isinstance(answers, dict)
    )
    if bad:
        return report(
            ExitCode.CONFIG,
            "an answer set is not a plain name mapped to an object of answers",
            "config/project.json canary.answer_sets: %s" % ", ".join(bad),
            "name each set with letters, digits, `.`, `_` or `-` and give it an object",
        )
    try:
        asked = asked_questions(ROOT)
    except CanaryError as exc:
        return report(
            ExitCode.FAILURE,
            "the template's copier.yml could not be read",
            str(exc),
            "install the template extra (pip install -e '.[template]') or fix "
            "copier.yml, then rerun",
        )
    # copier ignores a data key that is not a question and renders the
    # default, so an unasked key would verify a project the set never named.
    unasked = sorted(
        "%s.%s" % (name, key)
        for name, answers in sets.items()
        for key in answers
        if key not in asked
    )
    if unasked:
        return report(
            ExitCode.CONFIG,
            "an answer set names a question copier.yml does not ask",
            "config/project.json canary.answer_sets: %s" % ", ".join(unasked),
            "name only questions copier.yml asks, spelled as it spells them",
        )
    chosen = sorted(sets) if args.sets is None else sorted(set(args.sets))
    unknown = [name for name in chosen if name not in sets]
    if unknown:
        return report(
            ExitCode.USAGE,
            "no such answer set: %s" % ", ".join(unknown),
            "--set; config/project.json canary.answer_sets has %s"
            % (", ".join(sorted(sets)) or "none"),
            "name one of those sets, or add the set to config/project.json",
        )
    if not chosen:
        return report(
            ExitCode.NOTHING_JUDGED,
            "there is no answer set to render",
            "config/project.json canary.answer_sets",
            "add a set to canary.answer_sets, then rerun",
        )
    paths = PATHS if args.path == "both" else (args.path,)

    raw = settings["scratch_root"]
    scratch = os.path.realpath(os.path.join(ROOT, os.path.expanduser(raw)))
    timeout = settings["step_timeout_minutes"] * 60
    # Queries of the checkout run before any scratch exists, so the hermetic
    # environment is not there yet; they read and write nothing.
    query = _bound(runner or Runner(), None, timeout)
    named = (
        "%s, which sets canary.scratch_root" % scratch_var
        if from_env
        else "config/project.json canary.scratch_root"
    )
    try:
        fault = _scratch_fault(scratch, query.git)
        tag = (
            previous_tag(_read_changelog(), query.git, ROOT)
            if "update" in paths
            else None
        )
    except (CanaryError, OSError) as exc:
        return report(
            ExitCode.FAILURE,
            "git could not answer about the template checkout",
            "%s: %s" % (ROOT, exc),
            "run the canary from a keel git checkout",
        )
    if fault:
        return report(
            ExitCode.CONFIG,
            "the canary's scratch root is refused: %s" % fault,
            named,
            "point it at a git-ignored directory of the checkout or at local "
            "disk outside the system temporary directory",
        )
    if "update" in paths and tag is None:
        return report(
            ExitCode.USAGE,
            "no previous release to update from",
            "CHANGELOG.md headings and git tag --list",
            "tag the last release or run with --path fresh",
        )

    try:
        today = run_date.today(os.environ, run_date.load(ROOT))
    except run_date.RunDateError as exc:
        return report(
            ExitCode.CONFIG,
            "the run date is refused",
            str(exc),
            "fix config/project.json evidence.run_date or the variable it names",
        )
    run_id = "%s-%s" % ("+".join(chosen) if args.sets else "all", args.path)
    run = os.path.join(scratch, run_id)
    # A run replaces its own directory, so a second run leaves the same tree.
    if os.path.lexists(run):
        shutil.rmtree(run)
    os.makedirs(run)
    extra = scratch_env(run, today)
    tools = _bound(runner or Runner(), extra, timeout)
    inside = _under(scratch, os.path.realpath(ROOT))
    try:
        snap, not_checked = snapshot_working_tree(
            ROOT,
            run,
            extra,
            # A snapshot that copied the scratch root would copy itself.
            skip=(os.path.relpath(scratch, os.path.realpath(ROOT)),) if inside else (),
            label="canary",
        )
    except SnapshotError as exc:
        return report(
            ExitCode.FAILURE,
            "the template checkout could not be snapshotted",
            str(exc),
            "fix the checkout's git state, then rerun",
        )
    lock = threading.Lock()
    for item in not_checked:
        _say(lock, "not rendered: %s (%s)" % (item["item"], item["reason"]))

    pairs = []
    for name in chosen:
        answers = os.path.join(run, "%s.yml" % name)
        # JSON is YAML, so copier reads the answers with no YAML writer here.
        with open(answers, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(sets[name], sort_keys=True) + "\n")
        pairs.extend(
            _Pair(name, path, run, snap, answers, tag, tools, lock) for path in paths
        )
    with concurrent.futures.ThreadPoolExecutor(max_workers=settings["workers"]) as pool:
        futures = [pool.submit(pair) for pair in pairs]
        results = [future.result() for future in futures]

    for res in results:
        print(
            "%s %s %s %s %s %ds"
            % (res.name, res.path, res.step, res.verdict, res.log, res.elapsed)
        )
    sys.stdout.flush()
    failed = [res for res in results if res.verdict == "fail"]
    if failed:
        return report(
            ExitCode.FAILURE,
            "%d of %d canary projects failed: %s"
            % (
                len(failed),
                len(results),
                "; ".join("%s %s at %s" % (r.name, r.path, r.step) for r in failed),
            ),
            "kept: %s" % ", ".join(r.dest for r in failed),
            "read each log beside its kept project, fix keel, and rerun with "
            "CANARY_FLAGS='--set NAME --path PATH'",
        )
    for left in ("template", "cache", "tmp"):
        if os.path.lexists(os.path.join(run, left)):
            shutil.rmtree(os.path.join(run, left))
    return ExitCode.SUCCESS


def _read_changelog():
    with open(os.path.join(ROOT, CHANGELOG), encoding="utf-8") as fh:
        return fh.read()


if __name__ == "__main__":
    finish(main())
