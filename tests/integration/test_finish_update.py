"""
title: Integration — finish_update replays the after migrations a stopped update never ran
kind: tests
layer: n/a
summary: scripts/jobs/finish_update.py run in a synthetic git project whose HEAD answers record a synthetic template's tag v1 and whose work-tree answers record v2, the state copier leaves when an `after` migration fails. It clones the template from the answers' `_src_path` (or `--template`), checks out v2 and runs that version's migrations, never v1's, in copier.yml's order from the project root: a `when` that renders false is skipped, a list runs as argv and a string under the shell, and every name a migration renders (the answers, `_stage`, `_version_from`, `_version_to`, `_copier_operation`, `_copier_python`, `_copier_conf.src_path`) carries the value copier gives it. A second run changes no byte of the tree or the index (the fixed point check_V's rerun_proof names), and the answers and the index are never written. `--dry-run` prints each kept command as one JSON line and runs nothing. Each precondition exits 2 with one line naming the fix and changes nothing: no update in progress, an unresolvable `_src_path`, a migration key it cannot replay (`version`), a setting it cannot render (`_envops`), a name it does not supply (StrictUndefined), and a conflict hunk in a file it reads, which scripts/jobs/conflict_guard.py refuses naming the file, its line and finish_update's own rerun. A failing step stops the run, exit 2, naming it; no later step runs. `cast_to_bool` agrees with copier's own on every value tried, when copier is installed.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import hermetic_git
import optional_deps

pytestmark = pytest.mark.integration

optional_deps.importorskip("yaml", extra="template")
optional_deps.importorskip("jinja2", extra="template")

_ROOT = Path(__file__).resolve().parents[2]
_FINISH = "scripts/jobs/finish_update.py"
# What finish_update needs from the project to run there: itself, the modules
# it imports and the manifest child_env reads its allowlist from.
_SHIPPED = (
    _FINISH,
    "scripts/jobs/conflict_guard.py",
    "scripts/jobs/review_docs.py",
    "scripts/child_env.py",
    "config/project.json",
)

# A step writes one whole file, so running it twice is a fixed point.
_PUT = (
    "import pathlib, sys\n"
    "p = pathlib.Path('out', sys.argv[1])\n"
    "p.parent.mkdir(exist_ok=True)\n"
    "p.write_text('\\n'.join(sys.argv[2:]) + '\\n')\n"
)
_FAIL = "import sys\nsys.stderr.write('step says no\\n')\nsys.exit(3)\n"


def _migrations(*entries):
    return "_migrations:\n" + "".join(entries)


def _entry(command, when=None, **extra):
    text = "  - command: %s\n" % json.dumps(command)
    if when is not None:
        text += "    when: %s\n" % json.dumps(when)
    for key, value in extra.items():
        text += "    %s: %s\n" % (key, json.dumps(value))
    return text


def _py(*argv):
    return ["{{ _copier_python }}"] + list(argv)


# v1's migrations: a run that picked the commit HEAD records would write this.
_V1 = _migrations(_entry(_py("steps/put.py", "v1.txt", "wrong version")))
# v2's: the order matters (the shell `cp` reads what the first wrote), one
# `when` is false, and the last records every name copier renders.
_V2 = _migrations(
    _entry(_py("steps/put.py", "a.txt", "{{ flavour }}"), "{{ _stage == 'after' }}"),
    _entry(_py("steps/put.py", "skipped.txt", "x"), "{{ flavour == 'other' }}"),
    _entry("cp out/a.txt out/b.txt"),
    _entry(
        _py(
            "steps/put.py",
            "ctx.txt",
            "{{ _version_from }}",
            "{{ _version_to }}",
            "{{ _stage }}",
            "{{ _copier_operation }}",
            "{{ _copier_python }}",
        )
    ),
    _entry(_py("steps/put.py", "src.txt", "{{ _copier_conf.src_path }}")),
)
_EXPECTED = {
    "out/a.txt": "sweet\n",
    "out/b.txt": "sweet\n",
    "out/ctx.txt": "v1\nv2\nafter\nupdate\n%s\n" % sys.executable,
}


def _git(cwd, env, *argv):
    r = subprocess.run(
        ["git"] + list(argv), cwd=str(cwd), env=env, capture_output=True, text=True
    )
    assert r.returncode == 0, "git %s: %s" % (" ".join(argv), r.stderr)
    return r.stdout


def _answers(commit, src):
    return "_commit: %s\n_src_path: %s\nflavour: sweet\n" % (commit, src)


def _make(tmp_path, v2_config=_V2, src=None):
    """(template, project, env): a template tagged v1 then v2, and a project
    whose HEAD answers record v1 and whose work tree records v2."""
    env = hermetic_git.git_env(tmp_path)
    template = tmp_path / "template"
    template.mkdir()
    _git(template, env, "init", "-q", "-b", "main")
    (template / "copier.yml").write_text(_V1)
    _git(template, env, "add", "-A")
    _git(template, env, "commit", "-qm", "v1")
    _git(template, env, "tag", "v1")
    (template / "copier.yml").write_text(v2_config)
    (template / "MARK").write_text("the template at v2\n")
    _git(template, env, "add", "-A")
    _git(template, env, "commit", "-qm", "v2")
    _git(template, env, "tag", "v2")

    project = tmp_path / "project"
    for rel in _SHIPPED:
        (project / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(_ROOT / rel), str(project / rel))
    (project / "steps").mkdir()
    (project / "steps" / "put.py").write_text(_PUT)
    (project / "steps" / "fail.py").write_text(_FAIL)
    source = str(template) if src is None else src
    (project / ".copier-answers.yml").write_text(_answers("v1", source))
    _git(project, env, "init", "-q", "-b", "main")
    _git(project, env, "add", "-A")
    _git(project, env, "commit", "-qm", "generated at v1")
    (project / ".copier-answers.yml").write_text(_answers("v2", source))
    return template, project, env


def _finish(project, env, *argv):
    return subprocess.run(
        [sys.executable, str(project / _FINISH)] + list(argv),
        cwd=str(project),
        env=env,
        capture_output=True,
        text=True,
    )


def _state(root):
    """Every path under *root* but .git with its bytes, plus the index."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(str(root)):
        dirnames[:] = sorted(d for d in dirnames if d != ".git")
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            with open(full, "rb") as fh:
                out[os.path.relpath(full, str(root))] = fh.read()
    out[".git/index"] = (Path(root) / ".git" / "index").read_bytes()
    return out


def _read(project, rel):
    return (project / rel).read_text()


def test_runs_the_new_versions_migrations_in_order_and_reaches_a_fixed_point(
    tmp_path,
):
    template, project, env = _make(tmp_path)
    answers = _read(project, ".copier-answers.yml")
    index = (project / ".git" / "index").read_bytes()

    r = _finish(project, env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "update finished (4 steps ran); review the changes and commit" in r.stderr

    for rel, text in _EXPECTED.items():
        assert _read(project, rel) == text, rel
    # The `when` that rendered false, and v1's migrations, never ran.
    assert not (project / "out" / "skipped.txt").exists()
    assert not (project / "out" / "v1.txt").exists()
    # _copier_conf.src_path was a checkout of v2, removed afterwards.
    src = _read(project, "out/src.txt").strip()
    assert src != str(template)
    assert not os.path.exists(src), src
    # Never stages, never edits the answers.
    assert _read(project, ".copier-answers.yml") == answers
    assert (project / ".git" / "index").read_bytes() == index

    first = _state(project)
    again = _finish(project, env)
    assert again.returncode == 0, again.stdout + again.stderr
    after = _state(project)
    # Only the checkout path a step records may differ (a fresh temp dir).
    first.pop("out/src.txt")
    after.pop("out/src.txt")
    assert after == first


def test_dry_run_prints_each_kept_command_and_runs_nothing(tmp_path):
    _template, project, env = _make(tmp_path)
    before = _state(project)
    r = _finish(project, env, "--dry-run")
    assert r.returncode == 0, r.stdout + r.stderr
    lines = [json.loads(line) for line in r.stdout.splitlines()]
    py = sys.executable
    assert lines[:3] == [
        [py, "steps/put.py", "a.txt", "sweet"],
        "cp out/a.txt out/b.txt",
        [py, "steps/put.py", "ctx.txt", "v1", "v2", "after", "update", py],
    ]
    assert len(lines) == 4
    assert lines[3][:3] == [py, "steps/put.py", "src.txt"]
    assert _state(project) == before


def test_a_template_flag_replaces_an_unresolvable_src_path(tmp_path):
    template, project, env = _make(tmp_path, src=str(tmp_path / "gone"))
    before = _state(project)
    r = _finish(project, env)
    assert r.returncode == 2, r.stdout + r.stderr
    assert r.stderr.startswith("finish_update: "), r.stderr
    assert "cannot be found; pass --template" in r.stderr, r.stderr
    assert "Traceback" not in r.stderr
    assert _state(project) == before

    r = _finish(project, env, "--template", str(template))
    assert r.returncode == 0, r.stdout + r.stderr
    assert _read(project, "out/b.txt") == "sweet\n"


def test_no_update_in_progress_changes_nothing(tmp_path):
    _template, project, env = _make(tmp_path)
    _git(project, env, "commit", "-qam", "the update, committed")
    before = _state(project)
    r = _finish(project, env)
    assert r.returncode == 2, r.stdout + r.stderr
    assert (
        "no update in progress: .copier-answers.yml records the commit HEAD "
        "does (v2)" in r.stderr
    ), r.stderr
    assert _state(project) == before


@pytest.mark.parametrize(
    "config, named",
    [
        (_migrations(_entry(_py("steps/put.py", "a.txt"), version="v2")), "version"),
        (
            _migrations(_entry(_py("steps/put.py", "a.txt"), working_directory="out")),
            "working_directory",
        ),
        ("_envops:\n  autoescape: true\n" + _V2, "_envops"),
        ("_jinja_extensions: [jinja2.ext.do]\n" + _V2, "_jinja_extensions"),
        ("_answers_file: .answers.yml\n" + _V2, ".answers.yml"),
        # StrictUndefined: copier would render the unknown name empty.
        (
            _V2 + _entry(_py("steps/put.py", "late.txt", "{{ no_such_answer }}")),
            "no_such_answer",
        ),
    ],
    ids=[
        "version",
        "working_directory",
        "envops",
        "extensions",
        "answers",
        "undefined",
    ],
)
def test_what_it_cannot_replay_as_copier_does_is_refused_before_any_step(
    tmp_path, config, named
):
    _template, project, env = _make(tmp_path, v2_config=config)
    before = _state(project)
    r = _finish(project, env)
    assert r.returncode == 2, r.stdout + r.stderr
    assert r.stderr.startswith("finish_update: "), r.stderr
    assert named in r.stderr, r.stderr
    assert len(r.stderr.strip().splitlines()) == 1, r.stderr
    assert _state(project) == before


def test_a_failing_step_stops_the_run_and_is_named(tmp_path):
    config = _migrations(
        _entry(_py("steps/put.py", "a.txt", "{{ flavour }}")),
        _entry(_py("steps/fail.py")),
        _entry(_py("steps/put.py", "late.txt", "x")),
    )
    _template, project, env = _make(tmp_path, v2_config=config)
    r = _finish(project, env)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "step says no" in r.stderr
    assert "finish_update: step 2 of 3 exited 3: " in r.stderr, r.stderr
    assert _read(project, "out/a.txt") == "sweet\n"
    assert not (project / "out" / "late.txt").exists()


@pytest.mark.parametrize("rel", ["config/project.json", ".copier-answers.yml"])
def test_a_conflicted_file_it_reads_is_refused_with_its_own_rerun(tmp_path, rel):
    template, project, env = _make(tmp_path)
    sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))
    try:
        import conflict_guard
    finally:
        sys.path.pop(0)
    path = project / rel
    lines = path.read_text().split("\n")
    hunk = "%s ours\n%s\n%s theirs" % (
        conflict_guard.OPEN,
        conflict_guard.SPLIT,
        conflict_guard.CLOSE,
    )
    path.write_text("\n".join(lines[:1] + [hunk] + lines[1:]))
    before = _state(project)
    r = _finish(project, env, "--template", str(template))
    assert r.returncode == 2, r.stdout + r.stderr
    found = conflict_guard.read_refusals(r.stderr)
    rerun = conflict_guard.rerun_command(
        str(project / _FINISH), str(project), ["--template", str(template)]
    )
    assert found == [("finish_update", [(rel, 2)], rerun)], r.stderr
    assert "Traceback" not in r.stderr
    assert _state(project) == before


def _module():
    spec = importlib.util.spec_from_file_location(
        "finish_update_under_test", str(_ROOT / _FINISH)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cast_to_bool_agrees_with_copiers_own():
    tools = optional_deps.importorskip("copier._tools", extra="template")
    values = [
        True, False, None, 0, 1, 2, 0.0, -1.5, "", "  ", "0", "1", "0.0", "2",
        "y", "Yes", " TRUE ", "t", "on", "n", "No", "false", "F", "off", "~",
        "null", "None", "nan", "inf", "maybe", [], [0], {}, {"a": 1},
    ]  # fmt: skip
    ours = _module().cast_to_bool
    assert [ours(v) for v in values] == [tools.cast_to_bool(v) for v in values]
