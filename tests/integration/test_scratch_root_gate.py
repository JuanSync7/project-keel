"""
title: Integration — test scratch lives under the configured root, never the system temporary directory
kind: tests
layer: n/a
summary: The session's basetemp is under config/project.json `tests.scratch_root` (or `KEEL_TEST_SCRATCH` over it), with `~` expanded, and not under the system temporary directory, which a child computes with TMPDIR, TEMP and TMP removed so the moved values cannot hide it. `tempfile.gettempdir()`, TMPDIR and the hermetic git config directory point there too, so a child and an import-time temporary directory follow. A nested session in a scratch project of its own leaves no per-test directory after a pass and keeps the failing test's directory, named after it, with the file it wrote; a nested session given no root inherits this one through KEEL_TEST_SCRATCH and never makes its own project's configured root; a root under the system temporary directory or inside the checkout stops pytest before any test runs (exit 4), naming the key, and is never created. A root that holds the checkout is accepted, and a test that writes into the checkout under it still fails, leaving nothing there. A session given no variable takes `tests.memory_scratch_root` with `-<uid>` appended when its parent exists, naming it `(memory)` in the `scratch:` header line and never making the disk root, and falls back to `tests.scratch_root` when the parent is missing, naming why.
"""

import glob
import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pytest
from test_empty_selection import _SHIPPED

import script_copy

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import config_loader  # noqa: E402
from child_env import build_child_env  # noqa: E402

pytestmark = pytest.mark.integration

_KEY = ("tests", "scratch_root")
_TIMEOUT_KEY = ("tests", "child_timeout_seconds")
# The variables tempfile reads before it falls back to the platform's own
# directory; the outer session has moved them, so the child drops all three.
_TEMP_VARS = ("TMPDIR", "TEMP", "TMP")
# pytest exits 4 when a conftest cannot be imported.
_USAGE_ERROR = 4

_GREEN = (
    "import pytest\n\npytestmark = pytest.mark.unit\n\n\n"
    "def test_green(tmp_path):\n"
    "    (tmp_path / 'kept.txt').write_text('evidence')\n"
)
_RED = (
    "import pytest\n\npytestmark = pytest.mark.unit\n\n\n"
    "def test_red(tmp_path):\n"
    "    (tmp_path / 'kept.txt').write_text('evidence')\n"
    "    assert False\n"
)


def _under(path, root):
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def _system_tempdir():
    """The real path of the directory tempfile picks when no variable moves it."""
    env = build_child_env()
    for name in _TEMP_VARS:
        env.pop(name, None)
    r = subprocess.run(
        [sys.executable, "-c", "import tempfile; print(tempfile.gettempdir())"],
        env=env,
        capture_output=True,
        text=True,
        timeout=child_timeout(),
    )
    assert r.returncode == 0, r.stderr
    return os.path.realpath(r.stdout.strip())


def _setting(key):
    """The value of config/project.json `key`, or the variable over it, read
    through the loader."""
    return config_loader.resolve(
        config_loader.read(str(_ROOT)),
        config_loader.rows(key),
        config_loader.CONFIG_FILE,
    )[key]


def child_timeout():
    """The seconds config/project.json `tests.child_timeout_seconds` lets a
    child this suite starts run."""
    return _setting(_TIMEOUT_KEY)


def _configured_root():
    """The real path config/project.json `tests.scratch_root` names, or the
    variable over it, read through the loader."""
    return os.path.realpath(os.path.expanduser(_setting(_KEY)))


def test_basetemp_is_under_the_scratch_root_and_not_the_system_temp(
    tmp_path_factory, pytestconfig
):
    basetemp = os.path.realpath(str(tmp_path_factory.getbasetemp()))
    systemp = _system_tempdir()
    assert not _under(basetemp, systemp), (basetemp, systemp)
    if pytestconfig.option.basetemp is None:
        # A --basetemp the caller gave is their choice, honoured where it is.
        assert _under(basetemp, _configured_root()), (basetemp, _configured_root())


def test_tempfile_and_tmpdir_point_at_the_root():
    root = _configured_root()
    assert os.path.realpath(tempfile.gettempdir()) == root
    assert os.path.realpath(os.environ["TMPDIR"]) == root


def test_the_hermetic_git_dir_is_under_the_root():
    gitconfig = os.path.realpath(os.environ["GIT_CONFIG_GLOBAL"])
    assert _under(os.path.dirname(gitconfig), _configured_root()), gitconfig


def _project(tmp_path, cases):
    """A scratch project holding the shipped test harness and *cases*, a map
    of unit test file name to its text."""
    root = tmp_path / "proj"
    script_copy.copy_with_imports(root, _ROOT, _SHIPPED)
    (root / "tests" / "unit").mkdir(parents=True)
    for name, text in sorted(cases.items()):
        (root / "tests" / "unit" / name).write_text(text, encoding="utf-8")
    return root


def _run(project, scratch, *args):
    """(exit code, output) of the scratch project's suite with its scratch
    root at *scratch*."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider"] + list(args),
        cwd=str(project),
        env=build_child_env(
            extra={"PYTHONPATH": "src:.", "KEEL_TEST_SCRATCH": str(scratch)}
        ),
        capture_output=True,
        text=True,
        timeout=child_timeout(),
    )
    return r.returncode, r.stdout + r.stderr


def _numbered(scratch):
    """The numbered session directories pytest left under *scratch*."""
    return sorted(glob.glob(str(scratch / "pytest-of-*" / "pytest-[0-9]*")))


def test_a_passing_nested_session_leaves_no_test_dir_and_a_failing_one_keeps_its_named_dir(
    tmp_path,
):
    scratch = tmp_path / "inner-scratch"
    project = _project(tmp_path, {"test_green.py": _GREEN})
    code, out = _run(project, scratch)
    assert code == 0 and "1 passed" in out, out[-3000:]
    # The session used the root, then removed what it made there.
    assert glob.glob(str(scratch / "pytest-of-*")), out[-3000:]
    assert _numbered(scratch) == [], _numbered(scratch)

    (project / "tests" / "unit" / "test_green.py").unlink()
    (project / "tests" / "unit" / "test_red.py").write_text(_RED, encoding="utf-8")
    code, out = _run(project, scratch)
    assert code == 1 and "1 failed" in out, out[-3000:]
    kept = [Path(session) / "test_red0" / "kept.txt" for session in _numbered(scratch)]
    assert [p.read_text(encoding="utf-8") for p in kept if p.is_file()] == [
        "evidence"
    ], _numbered(scratch)


def test_a_nested_session_given_no_root_inherits_this_one(tmp_path):
    project = _project(tmp_path, {"test_green.py": _GREEN})
    own = tmp_path / "own-configured-root"
    path = project / "config" / "project.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["tests"]["scratch_root"] = str(own)
    path.write_text(json.dumps(manifest), encoding="utf-8")
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider"],
        cwd=str(project),
        env=build_child_env(extra={"PYTHONPATH": "src:."}),
        capture_output=True,
        text=True,
        timeout=child_timeout(),
    )
    out = r.stdout + r.stderr
    assert r.returncode == 0 and "1 passed" in out, out[-3000:]
    # The project's own configured root (a generated project's is under the
    # home directory) is never made by a session this suite starts.
    assert not own.exists(), own


_INTO_THE_CHECKOUT = (
    "import pytest\n\npytestmark = pytest.mark.unit\n\n\n"
    "def test_into_the_checkout():\n"
    "    # The session runs with the checkout as its working directory.\n"
    "    open('written-by-a-test.txt', 'w').close()\n"
)


def test_a_root_that_holds_the_checkout_leaves_the_checkout_refused(tmp_path):
    project = _project(tmp_path, {"test_into.py": _INTO_THE_CHECKOUT})
    code, out = _run(project, tmp_path)
    assert code == 1 and "1 failed" in out, out[-3000:]
    assert "IsolationError" in out and "(writes=temp)" in out, out[-3000:]
    assert not (project / "written-by-a-test.txt").exists()


@pytest.mark.parametrize("where", ["system-temp", "checkout"])
def test_a_root_under_the_system_temp_or_inside_the_checkout_is_refused(
    tmp_path, where
):
    project = _project(tmp_path, {"test_green.py": _GREEN})
    if where == "system-temp":
        # Unique per run: tmp_path's name repeats across sessions, and a root
        # a broken refusal once made would fail every later run's precheck.
        scratch = Path(_system_tempdir()) / ("keel-refused-%s" % uuid.uuid4().hex)
    else:
        scratch = project / "scratch"
    assert not scratch.exists(), scratch
    code, out = _run(project, scratch, "--basetemp=%s" % (tmp_path / "inner-bt"))
    assert code == _USAGE_ERROR, out[-3000:]
    assert "tests.scratch_root" in out and "KEEL_TEST_SCRATCH" in out, out[-3000:]
    assert "1 passed" not in out, out[-3000:]
    # Refused before anything was made there; a root left by a broken
    # refusal is named so it can be removed by hand.
    assert not scratch.exists(), "made, remove by hand: %s" % scratch


@pytest.mark.parametrize("host", ["holds-memory", "lacks-memory"])
def test_a_session_given_no_variable_takes_the_memory_root_when_the_host_has_one(
    tmp_path, host
):
    project = _project(tmp_path, {"test_green.py": _GREEN})
    shm = tmp_path / "shm"
    if host == "holds-memory":
        shm.mkdir()
    disk = tmp_path / "own-disk-root"
    path = project / "config" / "project.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["tests"]["scratch_root"] = str(disk)
    manifest["tests"]["memory_scratch_root"] = str(shm / "proj-tests")
    manifest["tests"]["memory_scratch_min_free_mb"] = 0
    path.write_text(json.dumps(manifest), encoding="utf-8")
    env = build_child_env(extra={"PYTHONPATH": "src:."})
    # Without it the session inherits this one's root, as a nested one should.
    env.pop("KEEL_TEST_SCRATCH", None)
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider"],
        cwd=str(project),
        env=env,
        capture_output=True,
        text=True,
        timeout=child_timeout(),
    )
    out = r.stdout + r.stderr
    assert r.returncode == 0 and "1 passed" in out, out[-3000:]
    mine = Path("%s-%d" % (os.path.realpath(str(shm / "proj-tests")), os.getuid()))
    if host == "holds-memory":
        assert "scratch: %s (memory)" % mine in out, out[-3000:]
        # A passed session removes its numbered directory; pytest's own
        # per-user directory stays as the mark it ran there.
        assert glob.glob(str(mine / "pytest-of-*")), mine
        assert not disk.exists(), disk
    else:
        # The header names the root in use and why memory was passed over.
        real_disk = os.path.realpath(str(disk))
        assert "scratch: %s (disk:" % real_disk in out, out[-3000:]
        assert "does not exist on this host" in out, out[-3000:]
        assert glob.glob(os.path.join(real_disk, "pytest-of-*")), real_disk
        assert not shm.exists(), shm
