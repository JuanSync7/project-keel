"""
title: Integration — declare_no_app settles a project the update gave a composition root it deleted
kind: tests
layer: n/a
summary: scripts/jobs/declare_no_app.py run as copier's `after` migration runs it, in a real git project whose HEAD is the commit before the update. When HEAD's config/project.json had no `layers.app` and the working tree's names a path the project does not have, the job sets it null, declares the smoke test's marker empty and skips the run target, names that on stderr, and a second run changes no byte (the fixed point check_V's rerun_proof names). A project that declared `layers.app` itself, one that still has its composition root and one whose manifest is mid-conflict are left untouched, and a project outside git exits 2.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import hermetic_git

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

from child_env import build_child_env  # noqa: E402

pytestmark = pytest.mark.integration

_JOB = _ROOT / "scripts" / "jobs" / "declare_no_app.py"
_APP = {"language": "python", "path": "src/app", "module": "app"}
_MAKEFILE = (
    "run: ## [local] Run it\n\t$(PY) scripts/run_app.py\n"
    "smoke: ## [local] Smoke\n\t$(PY) -m pytest -m smoke\n"
)
_SMOKE = "import pytest\n\npytestmark = pytest.mark.smoke\n"


def _manifest(app):
    layers = {"backend": {"path": "src/backend"}}
    if app is not None:
        layers["app"] = app
    return {
        "make_targets": {
            "effect_proof_skip": {"new": "needs DEST"},
            "empty_test_selections": {},
        },
        "layers": layers,
    }


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def project(tmp_path):
    """(root, env, run): a committed project without layers.app or src/app,
    whose working tree then gains layers.app as an update's merge leaves it."""
    work = tmp_path / "gitwork"
    work.mkdir()
    git_env = hermetic_git.git_env(work)
    root = tmp_path / "project"
    _write(root / "Makefile", _MAKEFILE)
    _write(root / "tests" / "smoke" / "test_app_runs.py", _SMOKE)
    _write(
        root / "config" / "project.json",
        json.dumps(_manifest(None), indent=2) + "\n",
    )
    for argv in (
        ["init", "-q", "-b", "main"],
        ["add", "-A"],
        ["commit", "-qm", "generated before layers.app"],
    ):
        r = subprocess.run(
            ["git"] + argv, cwd=str(root), env=git_env, capture_output=True, text=True
        )
        assert r.returncode == 0, r.stderr
    _write(
        root / "config" / "project.json",
        json.dumps(_manifest(_APP), indent=2) + "\n",
    )
    env = build_child_env(
        extra=dict(
            hermetic_git.git_env_vars(work), GIT_CEILING_DIRECTORIES=str(tmp_path)
        )
    )

    def run():
        return subprocess.run(
            [sys.executable, str(_JOB)],
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
        )

    return root, env, run


def _read(root):
    return (root / "config" / "project.json").read_text(encoding="utf-8")


def test_settles_an_introduced_root_and_reaches_a_fixed_point(project):
    root, _, run = project
    r = run()
    assert r.returncode == 0, r.stdout + r.stderr
    assert "src/app is absent" in r.stderr, r.stderr
    settled = json.loads(_read(root))
    assert settled["layers"]["app"] is None
    assert list(settled["make_targets"]["empty_test_selections"]) == ["smoke"]
    assert sorted(settled["make_targets"]["effect_proof_skip"]) == ["new", "run"]
    once = _read(root)
    r = run()
    assert r.returncode == 0 and r.stderr == "", r.stdout + r.stderr
    assert _read(root) == once


def test_a_root_the_project_declared_itself_is_left_to_check_h(project):
    root, env, run = project
    for argv in (["add", "-A"], ["commit", "-qm", "declared layers.app"]):
        subprocess.run(["git"] + argv, cwd=str(root), env=env, check=True)
    before = _read(root)
    r = run()
    assert r.returncode == 0 and r.stderr == "", r.stdout + r.stderr
    assert _read(root) == before


def test_a_present_root_or_a_conflicted_manifest_is_untouched(project):
    root, _, run = project
    (root / "src" / "app").mkdir(parents=True)
    before = _read(root)
    r = run()
    assert r.returncode == 0 and r.stderr == "", r.stdout + r.stderr
    assert _read(root) == before
    (root / "src" / "app").rmdir()
    # Built, not written out: a literal marker in this file reads as an
    # unresolved conflict to test_update_leaves_no_conflicts.
    conflicted = "<" * 7 + " before updating\n" + before
    _write(root / "config" / "project.json", conflicted)
    r = run()
    assert r.returncode == 0 and "not judged" in r.stderr, r.stderr
    assert _read(root) == conflicted


def test_outside_git_exits_2(project):
    root, _, run = project
    shutil.rmtree(str(root / ".git"))
    before = _read(root)
    r = run()
    assert r.returncode == 2, r.stdout + r.stderr
    assert _read(root) == before
