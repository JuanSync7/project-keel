"""
title: Shared pytest fixtures + the hermetic git environment
summary: Repo-wide fixtures, and the one place the suite's git environment is neutralised (see tests/hermetic_git.py for what is neutralised and why).

Shared pytest fixtures live here.

Also the one place the suite's git environment is neutralised — see the comment
below, and tests/hermetic_git.py for what is neutralised and why.
"""

import atexit
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

import hermetic_git

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Applied at IMPORT time, deliberately, and session-wide rather than per test.
#
# copier drives git through `plumbum`, and `plumbum.local.env` snapshots os.environ
# when plumbum is first imported — so `monkeypatch.setenv` inside a fixture is INERT
# for every git subprocess copier spawns (measured: plumbum reported None for a var
# os.environ had just been given). conftest is imported before any test module, hence
# before plumbum, so this is the last point where that snapshot can still be shaped.
#
# What it guards, concretely: when keel's own tree is dirty — i.e. whenever anyone is
# working on the template — copier does not read the committed HEAD. It stages the
# working tree into a throwaway clone with `git add -A` (copier/_vcs.py:397), and that
# honours the developer's global excludes. With `*.yml` in ~/.config/git/ignore the
# clone loses `copier.yml`, so every `_exclude` and every answer silently stops
# applying and the generated project ships keel's own template meta-tests. Measured on
# this repo: control -> no meta-tests shipped; the identical run under that one ignore
# line -> all three shipped. A green suite on one laptop and a red one on the next,
# for a template that is correct either way.
_GITCONFIG_DIR = tempfile.mkdtemp(prefix="keel-hermetic-git-")
atexit.register(shutil.rmtree, _GITCONFIG_DIR, True)
os.environ.update(hermetic_git.git_env_vars(_GITCONFIG_DIR))


@pytest.fixture(scope="session")
def real_corpus():
    """The repo's own `wiki/corpus.json`, built ONLY IF ABSENT. Returns its path.

    The showcase read model and the wiki agents read the corpus — a *generated
    view*: gitignored, rebuilt by `make site-data`, and therefore absent in a
    freshly generated project and a fresh clone. Nine of a generated project's
    own tests failed on arrival for exactly that reason, while its README told
    the newcomer to run `make verify`: the project was born red through no act of
    its own.

    Built only when ABSENT, and deliberately never REBUILT. A stale corpus must
    stay stale, or this fixture would quietly repair the drift that
    `make check-corpus` exists to report (ADR-0008) — a test that fixes its own
    subject proves nothing. Building it by the same two jobs `make site-data`
    runs, in subprocesses, keeps one definition of how the view is produced.
    """
    path = os.path.join(_ROOT, "wiki", "corpus.json")
    if os.path.isfile(path):
        return path
    for job in ("build_corpus.py", "link_corpus.py"):
        result = subprocess.run(
            [sys.executable, os.path.join("scripts", "jobs", job)],
            cwd=_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            "could not build the corpus this suite reads (%s):\n%s%s"
            % (job, result.stdout, result.stderr)
        )
    return path
