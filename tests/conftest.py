"""
title: Shared pytest fixtures + the hermetic git environment + the zero-tests guard
summary: Repo-wide fixtures; the one place the suite's git environment is neutralised and the parent's git repository context and injected git configuration removed (see tests/hermetic_git.py for what is neutralised and why); and the end-of-session guard that fails a run in which zero tests ran (see tests/selection_guard.py for the verdict).

Shared pytest fixtures live here.

Also the one place the suite's git environment is neutralised, and the parent's
repository context (a hook's GIT_DIR, GIT_INDEX_FILE, ...) removed — see the
comments below, and tests/hermetic_git.py for what is neutralised and why.
"""

import atexit
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

import hermetic_git
import selection_guard

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

# Also at import, for the same plumbum snapshot: the parent's repository context.
# A git hook exports GIT_INDEX_FILE (and, in a linked worktree, GIT_DIR) for the
# repository being committed, and the suite's own git — hermetic_git, copier — is
# not started through build_child_env. Measured under a parent GIT_DIR and
# GIT_INDEX_FILE: hermetic_git.clone_including_worktree wrote a blob into the
# PARENT's index that is missing from the parent's objects (`git status`: "unable
# to read"; fsck: "missing blob", "invalid sha1 pointer in cache-tree"). So a
# pytest started from a pre-commit or pre-push hook would otherwise corrupt the
# repository being committed. The names are config/project.json
# child_env.repo_context_names, the list build_child_env holds back.
for _name in hermetic_git.repo_context_names(_ROOT):
    os.environ.pop(_name, None)
# A parent's `git -c` settings (GIT_CONFIG_PARAMETERS, GIT_CONFIG_COUNT/KEY_n/VALUE_n) override the hermetic GIT_CONFIG_GLOBAL, so they go too, before plumbum snapshots.
hermetic_git.drop_config_injection(os.environ, _ROOT)


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
    `make check-corpus` exists to report (ADR-K-0008) — a test that fixes its own
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


# The zero-tests guard. pytest exits 5 only when nothing is collected; a run
# whose every selected test skipped exits 0 having executed no assertion. So
# count the tests that ran and let tests/selection_guard.py judge the session.
_RAN = []


def pytest_runtest_logreport(report):
    if report.when == "call" and (
        report.passed or report.failed or hasattr(report, "wasxfail")
    ):
        _RAN.append(report.nodeid)


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    config = session.config
    if (
        config.option.collectonly
        or getattr(config.option, "setupplan", False)
        or getattr(config.option, "setuponly", False)
        or hasattr(config, "workerinput")
    ):
        # A listing, --setup-plan and --setup-only execute no test by design;
        # an xdist worker's controller judges.
        return
    if exitstatus not in (0, 5):
        return  # a failure, an interrupt or a usage error already says why
    # Paths count only when the caller gave them, not pyproject's testpaths.
    source = getattr(config, "args_source", None)
    paths = list(config.args) if getattr(source, "name", "") == "ARGS" else []
    code, message = selection_guard.verdict(
        len(_RAN),
        config.option.markexpr,
        selection_guard.declared_empty(),
        keyword=config.option.keyword,
        paths=paths,
    )
    if code is None:
        return
    session.exitstatus = code
    reporter = config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write_line(message)
    else:
        sys.stderr.write(message + "\n")
