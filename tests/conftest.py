"""Shared pytest fixtures live here.

Also the one place the suite's git environment is neutralised — see the comment
below, and tests/hermetic_git.py for what is neutralised and why.
"""
import atexit
import os
import shutil
import tempfile

import hermetic_git

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
