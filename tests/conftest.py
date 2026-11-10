"""
title: Shared pytest fixtures + the test scratch root + the hermetic git environment + the isolation guard + the zero-tests guard + the expiring-tier recorder + the check_structure state guard
summary: Selects the session scratch root before test imports. tempfile, pytest basetemp and the hermetic git directory use that root. A session autouse fixture directs each test-running process's child environment to its own fixed scratch directory. The fixture restores the changed environment variables at teardown. The xdist controller keeps the session root in the environment it hands its workers. The isolation guard fails tests that reach outside their tier rules. store_copy supplies private copies of listed stores. The selection guard fails runs in which zero tests ran. The expiring-tier recorder writes requested findings as canonical JSON. The state guard puts back, after every test, the scripts/check_structure.py globals run_checks rebinds, so a test that judges a temporary tree never hands a later test its root or config memo (see tests/gate_state.py for how the names are read).

Shared pytest fixtures live here.

Also the one place the suite's git environment is neutralised, and the parent's
repository context (a hook's GIT_DIR, GIT_INDEX_FILE, ...) removed — see the
comments below, and tests/hermetic_git.py for what is neutralised and why.
"""

import atexit
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

import gate_state
import hermetic_git
import isolation_guard
import selection_guard

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "scripts"))

import config_loader  # noqa: E402
from child_env import build_child_env  # noqa: E402

# Test scratch, at import: before pytest makes its basetemp (from
# tempfile.gettempdir()), before the hermetic git directory below and the
# isolation guard's roots are taken from tempfile, and before plumbum
# snapshots os.environ, so every one of them sees the session root.
# A refused root raises here and pytest stops before any test runs (exit 4).
_SCRATCH = isolation_guard.choose_scratch(_ROOT)
isolation_guard.point_temp_at(_SCRATCH.path, os.environ)

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
#
# mkdtemp lands under the scratch root: tempfile was pointed there above, and
# os.environ already carries the moved TMPDIR when plumbum takes its snapshot.
_GITCONFIG_DIR = tempfile.mkdtemp(prefix="keel-hermetic-git-")
atexit.register(shutil.rmtree, _GITCONFIG_DIR, ignore_errors=True)  # noqa: DROP003 -- a scratch dir left at exit is harmless
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

# The isolation guard, installed at import so it is in place before any test
# module is imported; it judges nothing until a test's phase begins. A config
# fault raises here and pytest refuses to start, so a blank exemption reason
# is never a run in which the exemption silently holds.
_ISOLATION = isolation_guard.load_policy(_ROOT)
isolation_guard.install(_ISOLATION)


@pytest.fixture(scope="session", autouse=True)
def child_scratch():
    """Give this test-running process's children their own scratch root and
    restore the environment when the session ends."""
    # The controller imports conftest before spawning workers. Moving the
    # child environment at import would make workers inherit its child root
    # as their session root instead of sharing the intended session root.
    environ = dict(os.environ)
    isolation_guard.point_children_at(_SCRATCH.path, environ)
    with pytest.MonkeyPatch.context() as patch:
        for name, value in environ.items():
            if os.environ.get(name) != value:
                patch.setenv(name, value)
        yield


def pytest_report_header(config):
    """Names the scratch root in use and where it came from, so a session
    that fell back from memory to disk says so, with the reason."""
    note = ": %s" % _SCRATCH.note if _SCRATCH.note else ""
    return "scratch: %s (%s%s)" % (_SCRATCH.path, _SCRATCH.medium, note)


_RECORD_OPTION = "--expiring-tier-record"


def pytest_addoption(parser):
    parser.addoption(
        "--keel-full-gate",
        action="store_true",
        help="refuse narrowed selections for make test and make verify",
    )
    parser.addoption(
        _RECORD_OPTION,
        metavar="PATH",
        default=None,
        help="write the finding lines each scripts/expiring_tier.py check was "
        "handed to PATH as JSON (scripts/record_gate_baseline.py)",
    )


def _tier():
    # Imported only when recording: scripts/ is not on every session's path,
    # and the gate tests import the module under this same name, so both
    # reach the one module object and its one record.
    scripts = os.path.join(_ROOT, "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import expiring_tier

    return expiring_tier


def pytest_configure(config):
    if config.getoption("--keel-full-gate") and selection_guard.check_full_gate(
        config.invocation_params.args, os.environ.get("PYTEST_ADDOPTS", "")
    ):
        raise pytest.UsageError(
            "full gate refused a narrowed run; see the selection_guard refusal"
        )
    if not config.getoption(_RECORD_OPTION):
        return
    if getattr(config.option, "numprocesses", None):
        # Each worker would write its own share of the record to one PATH,
        # and the last to finish would stand as the whole of it.
        raise pytest.UsageError(
            "%s records one process's findings; run it without -n "
            "(pytest-xdist workers)" % _RECORD_OPTION
        )
    _tier().start_recording()


def _write_record(config):
    path = config.getoption(_RECORD_OPTION)
    if not path:
        return
    lines = _tier().recorded() or {}
    # Canonical JSON, so the same findings write the same bytes.
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(lines, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")


def pytest_sessionstart(session):
    # pytest's basetemp may sit outside the system temporary directory
    # (--basetemp), and tmp_path lives under it.
    isolation_guard.add_root(str(session.config._tmp_path_factory.getbasetemp()))


def _judged(item, phase):
    names = [mark.name for mark in item.iter_markers()]
    isolation_guard.begin(
        item.nodeid, phase, isolation_guard.rule_for(_ISOLATION, names)
    )
    try:
        result = yield
    except (KeyboardInterrupt, isolation_guard.IsolationError):
        isolation_guard.end()
        raise
    except BaseException as exc:
        # The violation outranks the test's own failure, skip or exit: the
        # test may have failed because the reach was refused.
        _refuse(isolation_guard.end(), exc)
        raise
    _refuse(isolation_guard.end(), None)
    return result


def _refuse(found, cause):
    if not found:
        return
    error = isolation_guard.IsolationError("\n".join(v.message() for v in found))
    if cause is None:
        # The test caught the refusal itself, so only this names it.
        raise error
    raise error from cause


@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item):
    return (yield from _judged(item, "setup"))


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    return (yield from _judged(item, "call"))


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item, nextitem):
    return (yield from _judged(item, "teardown"))


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    # An expected failure must not hide a reach: xfail turns any exception
    # into the pass it expected, the refusal included.
    if (
        call.excinfo is not None
        and call.excinfo.errisinstance(isolation_guard.IsolationError)
        and hasattr(report, "wasxfail")
    ):
        del report.wasxfail
        report.outcome = "failed"
    return report


@pytest.fixture
def store_copy(tmp_path):
    """A function that copies a store config/project.json
    `tests.isolation.stores` lists, with its sqlite siblings, into this test's
    own directory and returns the copy's path; the test may change the copy.
    Fails the test, naming the key, for a store the list does not name."""

    def copy(name):
        try:
            return isolation_guard.copy_store(
                _ISOLATION, _ROOT, str(name), str(tmp_path / "stores")
            )
        except isolation_guard.StoreError as exc:
            pytest.fail(str(exc), pytrace=False)

    return copy


@pytest.fixture(autouse=True)
def _check_structure_state():
    """Put back the check_structure globals run_checks rebinds once the test
    ends, when the module is imported."""
    # A test that calls run_checks on a temporary tree leaves ROOT and the
    # config memo there, and the next in-process reader judges that deleted
    # tree unless some later test happens to judge the real one first.
    module = sys.modules.get("check_structure")
    saved = gate_state.snapshot(module) if module is not None else None
    yield
    if saved is not None:
        gate_state.restore(module, saved)


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

    Built by one xdist worker at a time, under an exclusive lock on a file in
    the scratch root named for the corpus path: the lock keeps workers from
    reading the build before the link job has finished. Each job publishes a
    complete file atomically. The kernel drops the lock if its holder dies,
    so a crashed worker leaves no stale lock. Each child is bounded by
    tests.child_timeout_seconds; a timeout fails with the command and bound.
    """
    path = os.path.join(_ROOT, "wiki", "corpus.json")
    digest = hashlib.sha256(path.encode("utf-8")).hexdigest()[:16]
    lock = os.path.join(tempfile.gettempdir(), "keel-corpus-%s.lock" % digest)
    with open(lock, "a", encoding="utf-8") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        if os.path.isfile(path):
            return path
        key = ("tests", "child_timeout_seconds")
        timeout = config_loader.resolve(
            config_loader.read(_ROOT),
            config_loader.rows(key),
            config_loader.CONFIG_FILE,
        )[key]
        for job in ("build_corpus.py", "link_corpus.py"):
            command = [sys.executable, os.path.join("scripts", "jobs", job)]
            try:
                result = subprocess.run(
                    command,
                    cwd=_ROOT,
                    capture_output=True,
                    text=True,
                    env=build_child_env(),
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired:
                pytest.fail(
                    "corpus command %s exceeded tests.child_timeout_seconds=%s seconds"
                    % (command, timeout),
                    pytrace=False,
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


def _say(config, message):
    reporter = config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write_line(message)
    else:
        sys.stderr.write(message + "\n")


# Parallel workers (pytest-xdist). `make test` asks for `-n auto`, and the
# count is config/project.json tests.workers, so it is set in one place; 0
# runs the session in this process. Each worker judges its own tests, so the
# unused-exemption check moves to the controller: a worker hands over what it
# saw, and a worker that ended without handing it over leaves the check
# unable to judge its tests, which fails the run rather than passing it.
_USAGE = "isolation_usage"
_LOST = []


@pytest.hookimpl(optionalhook=True)
def pytest_xdist_auto_num_workers(config):
    try:
        return isolation_guard.worker_count(_ROOT)
    except isolation_guard.ConfigError as exc:
        # A usage error stops pytest before any test runs (exit 4), as a
        # refused scratch root does, rather than as an internal error.
        raise pytest.UsageError(str(exc)) from exc


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(node, error):
    record = getattr(node, "workeroutput", {}).get(_USAGE)
    if record is None:
        _LOST.append(node.gateway.id)
        return
    isolation_guard.merge_usage(record)


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    config = session.config
    _write_record(config)
    if hasattr(config, "workerinput"):
        config.workeroutput[_USAGE] = isolation_guard.usage()
        return  # the controller judges, over every worker's tests
    unused = isolation_guard.unused_exemptions() + [
        "isolation guard: worker %s ended without its exemption record, so the "
        "unused-exemption check could not judge its tests; run again" % gateway
        for gateway in sorted(_LOST)
    ]
    if unused:
        _say(config, "\n".join(unused))
        if exitstatus == 0:
            exitstatus = session.exitstatus = pytest.ExitCode.TESTS_FAILED
    if (
        config.option.collectonly
        or getattr(config.option, "setupplan", False)
        or getattr(config.option, "setuponly", False)
    ):
        # A listing, --setup-plan and --setup-only execute no test by design.
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
    _say(config, message)


@pytest.fixture
def escaped(tmp_path):
    """A project with an escaping parent link and an outside sentinel directory."""
    root, outside = tmp_path / "project", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "linked").symlink_to(outside, target_is_directory=True)
    return root, outside
