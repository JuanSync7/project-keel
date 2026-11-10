"""
title: Unit — the changed-tests runner refuses an unauthorized cache
summary: Stubbed refusals and real repositories with tracked or unignored cache paths return CONFIG before pytest can collect tests or write cache data.
"""

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import changed_tests  # noqa: E402
import config_loader  # noqa: E402
from child_env import build_child_env  # noqa: E402
from exit_codes import ExitCode  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "reason", ["tracked cache", "unignored cache", "no repository"]
)
def test_git_refusals_stop_before_pytest(tmp_path, monkeypatch, capsys, reason):
    def refuse(_root):
        if reason == "no repository":
            raise changed_tests.git_tree.NoGitError(reason)
        raise ValueError(reason)

    def unexpected_pytest(*_args, **_kwargs):
        raise AssertionError("an unauthorized cache must never reach pytest")

    monkeypatch.setattr(changed_tests.changed_cache, "cache_path", refuse)
    monkeypatch.setitem(sys.modules, "pytest", SimpleNamespace(main=unexpected_pytest))
    assert changed_tests.main([], root=str(tmp_path)) == ExitCode.CONFIG
    assert reason in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("kind", "cause"),
    [("tracked", "is tracked by git"), ("unignored", "must be git-ignored")],
)
def test_runner_refuses_git_unsafe_cache(tmp_path, monkeypatch, capsys, kind, cause):
    root = tmp_path / "project"
    (root / "config").mkdir(parents=True)
    (root / "config/project.json").write_text(
        json.dumps({"tests": {"cache_dir": "cache"}})
    )
    key = ("tests", "child_timeout_seconds")
    timeout = config_loader.resolve(
        config_loader.read(str(_ROOT)),
        config_loader.rows(key),
        config_loader.CONFIG_FILE,
    )[key]

    def git(*args):
        subprocess.run(
            ["git", *args],
            cwd=root,
            env=build_child_env(),
            check=True,
            capture_output=True,
            timeout=timeout,
        )

    git("init", "--quiet")
    cache = root / "cache"
    if kind == "tracked":
        (root / ".gitignore").write_text("cache\n")
        cache.write_text("tracked data\n")
        git("add", "--force", "cache")
    before = sorted(cache.rglob("*")) if cache.exists() else []
    # A bypass must reach only this synthetic test, even in a nested pytest run.
    (root / "pytest.ini").write_text("[pytest]\n")
    (root / "test_sample.py").write_text(
        "from pathlib import Path\n"
        "Path('collected').touch()\n"
        "def test_sample():\n"
        "    assert True\n"
    )
    monkeypatch.chdir(root)
    result = changed_tests.main(
        ["-q", "-c", "pytest.ini", "--confcutdir", str(root), "test_sample.py"],
        root=str(root),
    )
    output = capsys.readouterr().err
    assert result == ExitCode.CONFIG, output
    assert "tests.cache_dir" in output, output
    # The cause names the git answer, so a shape or manifest fault cannot pass.
    assert cause in output, output
    assert not (root / "collected").exists()
    assert not (root / ".pytest_cache").exists()
    assert sorted(cache.rglob("*")) == before
    if kind == "tracked":
        assert cache.read_text() == "tracked data\n"
    else:
        assert not cache.exists()
