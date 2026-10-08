#!/usr/bin/env python3
"""
title: declare_no_app — a project whose composition root is gone stays green across copier update
kind: script
layer: n/a
summary: A copier `after` migration on `copier update`. A project generated before config/project.json carried `layers.app`, and that deleted src/app as the template then advised, receives `"app": {"path": "src/app", ...}` from the update, and check_H errors on a path that does not exist. When the declared path is absent from the tree and the pre-update manifest (`git cat-file blob HEAD:config/project.json`, read-only, through review_docs' `git_argv` and the allowlisted environment) had no `layers.app`, this job makes the three edits src/app/README.md names for a project with no composition root: `layers.app` becomes null; each bare marker of the smoke test that needs the composition root (tests/smoke/test_app_runs.py `pytestmark`) is declared in `make_targets.empty_test_selections`; each Makefile target whose recipe runs scripts/run_app.py is added to `make_targets.effect_proof_skip`. It names what it did on stderr. config/project.json is edited as text, so no other byte moves, and an edit that does not parse back to exactly the intended manifest is refused: nothing is written, the edits are named on stderr, exit 1. A project that declared `layers.app` itself is left to check_H. A manifest that is not JSON (an update conflict) is a stated skip, exit 0; a git failure exits 2. Run as a script, it first asks scripts/jobs/conflict_guard.py whether a module it imports from the project holds a conflict hunk, and if one does it names each file and the rerun command and exits 2 instead of dying on the import.
effect: writes
rerun: fixed-point
rerun_proof: test:tests/integration/test_update_without_app.py
"""

# 3.6-safe and stdlib-only on purpose, like keep_edited_retired.py: copier runs
# this under its own interpreter in a project that may have no virtualenv yet.
import argparse
import ast
import copy
import json
import os
import re
import subprocess
import sys

_JOBS = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.dirname(_JOBS)
for _dir in (_JOBS, _SCRIPTS):
    if _dir not in sys.path:
        sys.path.insert(0, _dir)
# copier runs this inside a project it has just written; importing the
# siblings below would otherwise leave __pycache__/*.pyc in it.
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
        "declare_no_app",
        conflict_guard.rerun_command(__file__, os.path.dirname(_SCRIPTS), sys.argv[1:]),
        search_path=(_JOBS, _SCRIPTS),
    )

import child_env  # noqa: E402
import review_docs  # noqa: E402

MANIFEST = os.path.join("config", "project.json")
# The runner `make run` calls and the test that needs a composition root: the
# two files that decide which target and which marker a project without one
# must declare. The names inside them are read, never restated here.
RUNNER = "scripts/run_app.py"
SMOKE_TEST = os.path.join("tests", "smoke", "test_app_runs.py")
# The reasons src/app/README.md gives a project to write.
SMOKE_REASON = "no composition root to smoke (layers.app is null)"
RUN_REASON = "no composition root (layers.app is null)"

_TARGET = re.compile(r"^([A-Za-z0-9_.-]+)\s*:(?!=)")
_APP = re.compile(r'"app"\s*:\s*(\{[^{}]*\})')


class SettleError(Exception):
    """The manifest cannot be edited so that it parses to the intended one."""


class GitError(Exception):
    """git failed at the project."""


def runner_targets(makefile_text):
    """The Makefile targets, sorted, with a recipe line that runs RUNNER."""
    found = set()
    target = None
    for line in makefile_text.splitlines():
        if line.startswith("\t"):
            if target is not None and RUNNER in line:
                found.add(target)
            continue
        match = _TARGET.match(line)
        target = match.group(1) if match else None
    return sorted(found)


def _mark_name(node):
    """`name` for a bare `pytest.mark.name`, else None (a call such as
    `pytest.mark.skipif(...)` selects nothing)."""
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "mark"
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "pytest"
    ):
        return node.attr
    return None


def module_markers(test_text):
    """The bare marks of a test module's module-level `pytestmark`, sorted."""
    found = set()
    for node in ast.parse(test_text).body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets
        ):
            continue
        values = (
            node.value.elts
            if isinstance(node.value, (ast.List, ast.Tuple))
            else [node.value]
        )
        for value in values:
            name = _mark_name(value)
            if name is not None:
                found.add(name)
    return sorted(found)


def _layers_app(manifest):
    """(present, value) of `layers.app` in a parsed manifest."""
    layers = manifest.get("layers") if isinstance(manifest, dict) else None
    if not isinstance(layers, dict) or "app" not in layers:
        return False, None
    return True, layers["app"]


def needs_settling(manifest, head_manifest, root):
    """True when `layers.app` names a path absent under *root* and the
    pre-update *head_manifest* (None: no manifest at HEAD) had no `layers.app`."""
    present, app = _layers_app(manifest)
    if not present or not isinstance(app, dict):
        return False
    path = app.get("path")
    if not isinstance(path, str) or not path.strip("/"):
        return False  # malformed: check_H names it
    parts = [p for p in path.split("/") if p]
    if os.path.lexists(os.path.join(root, *parts)):
        return False
    return not _layers_app(head_manifest)[0]


def _insert(text, key, entries):
    """*text* with *entries* ([(name, reason)]) added first in the one object
    keyed *key*; raises SettleError when that object is not found once."""
    if not entries:
        return text
    pattern = re.compile(r'^([ \t]*)"%s"\s*:\s*\{' % re.escape(key), re.MULTILINE)
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise SettleError("found %d objects keyed %r" % (len(matches), key))
    match = matches[0]
    indent = match.group(1)
    lines = [
        "%s  %s: %s" % (indent, json.dumps(name), json.dumps(reason))
        for name, reason in entries
    ]
    rest = text[match.end() :]
    empty = re.match(r"\s*\}", rest)
    if empty:
        body = "\n" + ",\n".join(lines) + "\n" + indent + "}"
        return text[: match.end()] + body + rest[empty.end() :]
    return text[: match.end()] + "\n" + ",\n".join(lines) + "," + rest


def settle(text, markers, targets):
    """*text* (config/project.json) with `layers.app` null, each of *markers*
    declared in `make_targets.empty_test_selections` and each of *targets* in
    `make_targets.effect_proof_skip`; an entry already present is kept. Raises
    SettleError unless the result parses to exactly that manifest."""
    try:
        manifest = json.loads(text)
    except ValueError as e:
        raise SettleError("not JSON: %s" % e) from e
    present, app = _layers_app(manifest)
    make_targets = manifest.get("make_targets") if present else None
    if not isinstance(make_targets, dict):
        raise SettleError("no layers.app or no make_targets object")
    expected = copy.deepcopy(manifest)
    expected["layers"]["app"] = None
    edits = []
    for key, names, reason in (
        ("empty_test_selections", markers, SMOKE_REASON),
        ("effect_proof_skip", targets, RUN_REASON),
    ):
        block = make_targets.get(key)
        if not isinstance(block, dict):
            raise SettleError("make_targets.%s is not an object" % key)
        new = [(n, reason) for n in sorted(names) if n not in block]
        expected["make_targets"][key].update(new)
        edits.append((key, new))
    out = text
    if app is not None:
        spans = [m.span(1) for m in _APP.finditer(out) if json.loads(m.group(1)) == app]
        if len(spans) != 1:
            raise SettleError("found %d objects equal to layers.app" % len(spans))
        start, end = spans[0]
        out = out[:start] + "null" + out[end:]
    for key, new in edits:
        out = _insert(out, key, new)
    try:
        result = json.loads(out)
    except ValueError as e:
        raise SettleError("the edit does not parse: %s" % e) from e
    if result != expected:
        raise SettleError("the edit does not parse to the intended manifest")
    return out


def _git(root, *args):
    """git's stdout (bytes) at *root*, read-only; raises GitError."""
    try:
        argv = review_docs.git_argv(root, *args)
        env = child_env.build_child_env()
    except (review_docs.GitConfigError, child_env.ChildEnvError) as e:
        raise GitError("git %s: %s" % (args[0], e)) from e
    try:
        proc = subprocess.run(
            argv, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env
        )
    except OSError as e:
        raise GitError("git %s: %s" % (args[0], e)) from e
    if proc.returncode != 0:
        raise GitError(
            "git %s: %s"
            % (" ".join(args), os.fsdecode(proc.stderr).strip() or "failed")
        )
    return proc.stdout


def head_manifest(root):
    """The manifest at the project's HEAD (the commit before the update), or
    None when HEAD holds none; one that is not JSON reads as None too, since
    it cannot have declared anything a reader could check."""
    _git(root, "rev-parse", "--verify", "--quiet", "HEAD^{commit}")
    listed = _git(root, "ls-tree", "--name-only", "HEAD", "--", "config/project.json")
    if not listed.strip():
        return None
    blob = _git(root, "cat-file", "blob", "HEAD:config/project.json")
    try:
        return json.loads(blob.decode("utf-8"))
    except ValueError:
        return None


def _read(root, rel):
    path = os.path.join(root, rel)
    if not os.path.isfile(path):
        return ""
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _say(message):
    sys.stderr.write("declare_no_app: %s\n" % message)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Copier migration: when config/project.json layers.app names a path "
            "the project does not have and the pre-update manifest had no "
            "layers.app, set it null and declare the smoke marker and the run "
            "target a project with no composition root needs."
        )
    )
    parser.add_argument("--root", default=".", help="the project (default: .)")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    text = _read(root, MANIFEST)
    if not text:
        return 0
    try:
        manifest = json.loads(text)
    except ValueError:
        _say("config/project.json is not JSON (an update conflict?); not judged")
        return 0
    try:
        before = head_manifest(root)
    except GitError as e:
        _say(str(e))
        return 2
    if not needs_settling(manifest, before, root):
        return 0
    path = manifest["layers"]["app"]["path"]
    markers = module_markers(_read(root, SMOKE_TEST) or "")
    targets = runner_targets(_read(root, "Makefile"))
    try:
        out = settle(text, markers, targets)
    except SettleError as e:
        _say(
            "%s is absent and this update introduced layers.app, but "
            "config/project.json could not be edited (%s). Edit it by hand: "
            "set layers.app to null, declare %s in "
            "make_targets.empty_test_selections and add %s to "
            "make_targets.effect_proof_skip"
            % (path, e, markers or "no marker", targets or "no target")
        )
        return 1
    if out != text:
        with open(os.path.join(root, MANIFEST), "w", encoding="utf-8") as fh:
            fh.write(out)
        _say(
            "%s is absent and this update introduced layers.app: set it null, "
            "declared %s in make_targets.empty_test_selections and added %s to "
            "make_targets.effect_proof_skip (no composition root)"
            % (path, markers, targets)
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
