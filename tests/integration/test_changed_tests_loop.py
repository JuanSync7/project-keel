"""
title: Integration — a failure-only loop keeps its cache out of the gate
summary: Drives test-changed on two synthetic tests, proves only recorded failures rerun, refuses a disabled cache plugin before collection, and holds every other pytest recipe to disabling the cache.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

import makefile_copy
import script_copy

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import config_loader  # noqa: E402
from child_env import build_child_env  # noqa: E402

pytestmark = pytest.mark.integration

_SHIPPED = (
    "config/project.json",
    "scripts/check_python_version.py",
    "scripts/changed_tests.py",
    "pyproject.toml",
    ".gitignore",
)


def _run(root, argv, *, addopts=""):
    key = ("tests", "child_timeout_seconds")
    timeout = config_loader.resolve(
        config_loader.read(str(_ROOT)),
        config_loader.rows(key),
        config_loader.CONFIG_FILE,
    )[key]
    return subprocess.run(
        argv,
        cwd=root,
        env=build_child_env(extra={"PYTEST_ADDOPTS": addopts}),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    makefile_copy.copy_makefiles(root, _ROOT)
    script_copy.copy_with_imports(root, _ROOT, _SHIPPED)
    cfg = root / "config/project.json"
    manifest = json.loads(cfg.read_text())
    manifest["tests"]["cache_dir"] = ".loop-cache/nested"
    cfg.write_text(json.dumps(manifest))
    (root / ".gitignore").write_text(".loop-cache/\n")
    result = _run(root, ["git", "init", "--quiet"])
    assert result.returncode == 0, result.stderr
    (root / "tests").mkdir()
    (root / "tests/test_sample.py").write_text(
        "from pathlib import Path\n"
        "Path('collected').touch()\n"
        "def test_good():\n"
        "    with Path('calls').open('a') as f: f.write('good\\n')\n"
        "    assert True\n"
        "def test_bad():\n"
        "    with Path('calls').open('a') as f: f.write('bad\\n')\n"
        "    assert Path('fixed').exists()\n"
    )
    return root


def _loop(root, *, addopts=""):
    return _run(
        root,
        ["make", "--no-print-directory", "PY=" + sys.executable, "test-changed"],
        addopts=addopts,
    )


def test_recorded_failures_alone_rerun_in_the_configured_cache(project):
    first = _loop(project)
    assert first.returncode != 0 and "1 failed, 1 passed" in first.stdout, (
        first.stdout + first.stderr
    )
    assert (project / ".loop-cache/nested/v/cache/lastfailed").is_file()
    (project / "fixed").touch()
    (project / "calls").write_text("")
    second = _loop(project)
    assert second.returncode == 0, second.stdout + second.stderr
    assert (project / "calls").read_text().splitlines() == ["bad"]
    assert not (project / ".pytest_cache").exists()


@pytest.mark.parametrize("source", ["environment", "addopts", "addopts-list"])
@pytest.mark.parametrize("disabled", ["-p no:cacheprovider", "-pno:cacheprovider"])
def test_cache_disabled_refuses_by_name_before_any_test(project, source, disabled):
    addopts = disabled if source == "environment" else ""
    if source != "environment":
        # Replace the existing section, keeping this fixture independent of its options.
        (project / "pyproject.toml").write_text(
            '[project]\nname = "tiny"\nversion = "0"\nrequires-python = ">=3.11"\n'
            "[tool.pytest.ini_options]\naddopts = "
            + json.dumps(disabled.split() if source == "addopts-list" else disabled)
            + "\n"
        )
    result = _loop(project, addopts=addopts)
    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert (
        "test-changed" in output
        and "cacheprovider" in output
        and "remove" in output.lower()
    ), output
    assert not (project / "calls").exists(), output
    assert not (project / "collected").exists(), output


def test_every_other_pytest_recipe_disables_the_cache():
    text = (_ROOT / "Makefile").read_text()
    recipes = [
        line
        for line in text.splitlines()
        if line.startswith("\t") and "-m pytest" in line
    ]
    assert len(recipes) >= 6
    assert all("-p no:cacheprovider" in line for line in recipes), recipes
    assert "test-changed: check-python ## [local]" in text
    help_line = next(
        line for line in text.splitlines() if line.startswith("test-changed:")
    )
    assert "never the gate" in help_line.lower()
