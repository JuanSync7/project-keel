"""
title: Unit — corpus fixture child bounds
kind: tests
layer: n/a
summary: Each corpus job receives the configured child timeout; either job timing out fails with its command and bound, and a cached corpus starts no child.
"""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

_CONFTEST = Path(__file__).resolve().parents[1] / "conftest.py"


@pytest.fixture
def fixtures(pytestconfig):
    """The tests/conftest.py module pytest loaded, found by its file."""
    # `import conftest` names whichever conftest module registered last, and a
    # full run also loads tests/e2e/conftest.py, so the name is not this one.
    # Importing the file again would rerun its environment and scratch setup.
    for plugin in pytestconfig.pluginmanager.get_plugins():
        location = getattr(plugin, "__file__", None)
        if location and Path(location).resolve() == _CONFTEST:
            return plugin
    pytest.fail("pytest did not load %s as a plugin" % _CONFTEST)


@pytest.mark.parametrize("bound", [1, 37])
@pytest.mark.parametrize("stop", [None, "build_corpus.py", "link_corpus.py"])
def test_corpus_children_have_configured_bounds(
    fixtures, tmp_path, monkeypatch, bound, stop
):
    config = tmp_path / "config" / "project.json"
    config.parent.mkdir()
    config.write_text(
        json.dumps({"tests": {"child_timeout_seconds": bound}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(fixtures, "_ROOT", str(tmp_path))
    expected = bound
    calls = []

    def run(command, **kwargs):
        calls.append(Path(command[-1]).name)
        assert kwargs.get("timeout") == expected
        assert "env" in kwargs
        if calls[-1] == stop:
            raise subprocess.TimeoutExpired(command, expected)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    if stop:
        with pytest.raises(pytest.fail.Exception) as caught:
            fixtures.real_corpus.__wrapped__()
        message = str(caught.value)
        assert stop in message and str(expected) in message
        assert "tests.child_timeout_seconds" in message
        assert "scripts/jobs/" in message
    else:
        assert fixtures.real_corpus.__wrapped__() == str(tmp_path / "wiki/corpus.json")
    assert calls == (
        ["build_corpus.py"]
        if stop == "build_corpus.py"
        else ["build_corpus.py", "link_corpus.py"]
    )


def test_missing_child_timeout_is_a_config_failure(
    fixtures, tmp_path, monkeypatch, capsys
):
    config = tmp_path / "config" / "project.json"
    config.parent.mkdir()
    config.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(fixtures, "_ROOT", str(tmp_path))

    def unexpected(*args, **kwargs):
        pytest.fail("missing child timeout must fail before starting a child")

    monkeypatch.setattr(subprocess, "run", unexpected)
    with pytest.raises(fixtures.config_loader.NotSet):
        fixtures.real_corpus.__wrapped__()
    assert "tests.child_timeout_seconds" in capsys.readouterr().err


def test_cached_corpus_starts_no_child(fixtures, tmp_path, monkeypatch):
    path = tmp_path / "wiki" / "corpus.json"
    path.parent.mkdir()
    path.write_text('{"nodes": []}', encoding="utf-8")
    monkeypatch.setattr(fixtures, "_ROOT", str(tmp_path))

    def unexpected(*args, **kwargs):
        pytest.fail("a cached corpus must start no child")

    monkeypatch.setattr(subprocess, "run", unexpected)
    assert fixtures.real_corpus.__wrapped__() == str(path)
