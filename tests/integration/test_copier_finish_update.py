"""
title: Integration — an update a conflicted manifest stopped is finished by the command the refusal names
kind: tests
layer: n/a
summary: The defect a downstream project hit updating to 0.2.1, end to end with the real copier CLI. A project generated at v0.2.0 that edited config/project.json's `child_env._comment` is updated to this working tree with `--conflict inline`: the first migration (keep_edited_retired) refuses with scripts/jobs/conflict_guard.py's one line naming config/project.json, the line its hunk opens on, and the command that finishes the update under copier's interpreter, never a JSON parse error. Once the manifest is resolved (the new side plus the same edit) and staged, that printed command (scripts/jobs/finish_update.py) exits 0, and the project is the one a conflict-free update gives: a control generated the same way without the edit, updated, then given the edit, holds the same bytes in every file but config/project.json, which parses equal. Both projects carry the files keel pruned from later renders (its hardening plan, a template-only test), present when the update stops and retired by the finish, so the comparison cannot pass on a finish that ran nothing. The finished project passes check_structure and review_docs --strict, and a second finish (with `--template`) changes no byte. Parity: for several answer sets, the commands finish_update --dry-run lists in a project a conflict-free update just left are the `after` migrations copier itself ran there, in order (its " > Running task" lines), with the template checkout path the only difference. Template-only: it drives copier.yml, which no generated project has; scripts/jobs/finish_update.py's shipped proof is tests/integration/test_finish_update.py.
"""

import ast
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

import hermetic_git
import optional_deps

_ROOT = Path(__file__).resolve().parents[2]

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (_ROOT / "copier.yml").is_file(),
        reason="template-only: needs copier.yml (absent in generated projects)",
    ),
]

yaml = optional_deps.importorskip("yaml", extra="template")
optional_deps.importorskip("copier", extra="template")

sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))
import conflict_guard  # noqa: E402

# The release the downstream project updated from, and a date that pins every
# restamp (2026-10-09, UTC) so two projects stamp alike.
_FROM = "v0.2.0"
_EPOCH = "1791504000"
_MANIFEST = "config/project.json"
_EDIT = "A downstream note. "
# Files copier.yml's `rm -f` migrations retire from projects rendered before
# `_exclude` stopped shipping them: the work the finish must do.
_PRUNED = (
    "docs/design/keel-hardening-plan.md",
    "tests/integration/test_copier_update.py",
)
_FINISH = conflict_guard.FINISH_SCRIPT
_TASK = re.compile(r"^ > Running task (\d+) of (\d+): (.*)$")
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
# copier's clone of the template, and finish_update's checkout: the one value
# `_copier_conf.src_path` renders that must differ between the two runs.
_CHECKOUT = re.compile(
    r"(^|/)(copier\._vcs\.clone\.|finish_update\.)[^/]+(/template)?$"
)


@pytest.fixture(scope="module")
def keel(tmp_path_factory):
    """(template, env): a clone of this working tree, tags included, and the
    hermetic environment every copier and git call below runs in."""
    base = tmp_path_factory.mktemp("finish_e2e")
    work = base / "work"
    work.mkdir()
    env = hermetic_git.git_env(work)
    env["COPIER_CACHE_DIR"] = str(work / "cache")
    env["SOURCE_DATE_EPOCH"] = _EPOCH
    template = base / "template"
    hermetic_git.clone_including_worktree(str(_ROOT), str(template), str(work))
    return template, env


def _run(argv, cwd, env, check=True):
    r = subprocess.run(
        [str(a) for a in argv], cwd=str(cwd), env=env, capture_output=True, text=True
    )
    if check:
        assert r.returncode == 0, "%s: %s%s" % (argv, r.stdout, r.stderr[-4000:])
    return r


def _generate(keel, dest, data=None):
    template, env = keel
    argv = [sys.executable, "-m", "copier", "copy", "--trust", "--defaults"]
    if data:
        answers = dest.parent / (dest.name + "-data.yml")
        answers.write_text(yaml.safe_dump(data))
        argv += ["--data-file", answers]
    _run(argv + ["--vcs-ref", _FROM, template, dest], dest.parent, env)
    _run(["git", "init", "-q", "-b", "main"], dest, env)
    _run(["git", "add", "-A"], dest, env)
    _run(["git", "commit", "-qm", "generated at %s" % _FROM], dest, env)


def _carry_pruned(keel, project):
    """Give *project* the files a project generated before keel pruned them
    still carries, and commit them. A v0.2.0 render holds none, so without
    them every migration finds nothing to do and a finish that ran no step
    would pass the comparison below unseen."""
    _template, env = keel
    for rel in _PRUNED:
        path = project / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("carried from a render before the prune\n")
    _run(["git", "add", "--"] + list(_PRUNED), project, env)
    _run(["git", "commit", "-qm", "carried from an older render"], project, env)


def _update(keel, project, check=True):
    _template, env = keel
    return _run(
        [sys.executable, "-m", "copier", "update", "--trust", "--defaults"]
        + ["--conflict", "inline", "--vcs-ref", "HEAD"],
        project,
        env,
        check=check,
    )


def _edit(text):
    """*text* (config/project.json) with the downstream edit made to its
    `child_env._comment`; the edit must land exactly once."""
    lines = text.split("\n")
    start = next(i for i, line in enumerate(lines) if '"child_env"' in line)
    at = next(
        i
        for i in range(start, len(lines))
        if lines[i].lstrip().startswith('"_comment"')
    )
    edited = lines[at].replace('"_comment": "', '"_comment": "' + _EDIT, 1)
    assert edited != lines[at], lines[at]
    lines[at] = edited
    return "\n".join(lines)


def _files(root):
    out = {}
    for dirpath, dirnames, filenames in os.walk(str(root)):
        dirnames[:] = sorted(d for d in dirnames if d != ".git")
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, str(root))
            out[rel] = (
                os.readlink(full) if os.path.islink(full) else Path(full).read_bytes()
            )
    return out


def _index(root):
    return (Path(root) / ".git" / "index").read_bytes()


@pytest.fixture(scope="module")
def stopped(keel, tmp_path_factory):
    """(project, update result): generated at v0.2.0, the manifest's
    `child_env._comment` edited and committed, then updated and stopped."""
    _template, env = keel
    project = tmp_path_factory.mktemp("stopped") / "project"
    _generate(keel, project)
    _carry_pruned(keel, project)
    manifest = project / _MANIFEST
    manifest.write_text(_edit(manifest.read_text()))
    _run(["git", "commit", "-qam", "the downstream edit"], project, env)
    return project, _update(keel, project, check=False)


@pytest.fixture(scope="module")
def control(keel, tmp_path_factory):
    """(project, update result): generated the same way with no edit, updated
    (no conflict), then given the edit."""
    project = tmp_path_factory.mktemp("control") / "project"
    _generate(keel, project)
    _carry_pruned(keel, project)
    r = _update(keel, project)
    manifest = project / _MANIFEST
    manifest.write_text(_edit(manifest.read_text()))
    return project, r


def test_the_update_stops_naming_the_manifest_and_the_finish(stopped):
    project, r = stopped
    assert r.returncode != 0, r.stdout + r.stderr
    assert "Expecting property name" not in r.stderr, r.stderr[-3000:]
    found = conflict_guard.read_refusals(r.stderr)
    assert len(found) == 1, r.stderr[-3000:]
    job, items, rerun = found[0]
    assert job == "keep_edited_retired"
    assert [path for path, _line in items] == [_MANIFEST]
    line = items[0][1]
    text = (project / _MANIFEST).read_text().split("\n")
    assert conflict_guard.marker(text[line - 1], conflict_guard.OPEN), text[line - 1]
    assert rerun == conflict_guard.finish_rerun(sys.executable)


def _resolve(keel, project):
    """Take the new side of the manifest, make the same edit, and stage it."""
    _template, env = keel
    theirs = _run(["git", "show", ":3:" + _MANIFEST], project, env).stdout
    (project / _MANIFEST).write_text(_edit(theirs))
    _run(["git", "add", _MANIFEST], project, env)


def test_the_printed_command_finishes_it_as_a_clean_update_would(
    keel, stopped, control
):
    template, env = keel
    project, r = stopped
    _job, _items, rerun = conflict_guard.read_refusals(r.stderr)[0]
    _resolve(keel, project)
    # The stop ran no migration after the first, so the finish has work.
    assert [rel for rel in _PRUNED if (project / rel).exists()] == list(_PRUNED)

    done = _run(shlex.split(rerun), project, env, check=False)
    assert done.returncode == 0, done.stdout + done.stderr[-4000:]
    assert "update finished" in done.stderr

    ours, theirs = _files(project), _files(control[0])
    assert sorted(ours) == sorted(theirs)
    differ = sorted(rel for rel in ours if ours[rel] != theirs[rel])
    assert differ in ([], [_MANIFEST]), differ
    assert json.loads(ours[_MANIFEST]) == json.loads(theirs[_MANIFEST])
    assert [rel for rel in _PRUNED if (project / rel).exists()] == []

    for argv in (
        [sys.executable, "scripts/check_structure.py"],
        [sys.executable, "scripts/jobs/review_docs.py", "--strict"],
    ):
        gate = _run(argv, project, env, check=False)
        assert gate.returncode == 0, "%s: %s%s" % (argv, gate.stdout, gate.stderr)

    before, index = _files(project), _index(project)
    again = _run(
        shlex.split(rerun) + ["--template", template], project, env, check=False
    )
    assert again.returncode == 0, again.stdout + again.stderr[-4000:]
    assert _files(project) == before
    assert _index(project) == index


# --- parity: finish_update keeps and renders what copier runs ---------------


def _migration_count(template):
    with open(str(template / "copier.yml"), encoding="utf-8") as fh:
        return len(yaml.safe_load(fh)["_migrations"])


def _normal(command):
    if isinstance(command, list):
        return [_CHECKOUT.sub(r"\1<template checkout>", word) for word in command]
    return command


def _copier_ran(stderr, count):
    """The migrations copier's non-quiet run printed, in order. A list prints
    as its repr, a string as itself; `_tasks` prints with another total."""
    out = []
    for line in stderr.splitlines():
        match = _TASK.match(_ANSI.sub("", line))
        if match and int(match.group(2)) == count:
            text = match.group(3)
            out.append(ast.literal_eval(text) if text.startswith("[") else text)
    return out


def _parity(keel, project, update):
    template, env = keel
    ran = _copier_ran(update.stderr, _migration_count(template))
    assert ran, update.stderr[-3000:]
    dry = _run(
        [sys.executable, _FINISH, "--dry-run", "--template", template], project, env
    )
    listed = [json.loads(line) for line in dry.stdout.splitlines()]
    assert [_normal(c) for c in listed] == [_normal(c) for c in ran]


def test_dry_run_lists_what_copier_ran_on_a_default_project(keel, control):
    project, r = control
    _parity(keel, project, r)


@pytest.mark.parametrize(
    "data",
    [
        {"frontend_stack": "none", "showcase": False, "transports": ["grpc"]},
        {
            "frontend_stack": "astro",
            "showcase": True,
            "transports": ["edge_nginx"],
            "profiles": ["ai"],
        },
    ],
    ids=["no-frontend", "astro"],
)
def test_dry_run_lists_what_copier_ran_for_other_answers(keel, tmp_path, data):
    project = tmp_path / "project"
    _generate(keel, project, data)
    _parity(keel, project, _update(keel, project))
