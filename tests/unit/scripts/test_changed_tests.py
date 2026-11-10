"""
title: Unit — the changed-tests runner refuses an unauthorized cache
summary: A git refusal returns CONFIG before pytest can collect tests or write cache data.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import changed_tests  # noqa: E402
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
