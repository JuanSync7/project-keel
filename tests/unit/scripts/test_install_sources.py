"""
title: Unit — install_sources (the configured mirror for each install source)
kind: tests
layer: n/a
summary: scripts/install_sources.py driven with an injected config object, so no case reads config/project.json. For each source config/project.json `install_sources` names (`python_index`, `npm_registry`, `browser_download_host`) a configured https URL is printed alone on one line, from config and never a literal, and null prints nothing, so a caller passes no flag and the tool's own setting holds. An http URL, a query, a fragment, whitespace and a URL user part are each CONFIG naming the key, and a user part is never printed: the refusal shows `<hidden: it holds a user part>`. A source outside the closed list is USAGE. Keel's own config sets every source, so resolving them writes nothing to stderr.
@covers scripts/install_sources.py
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import config_loader  # noqa: E402
import install_sources  # noqa: E402
from exit_codes import ExitCode  # noqa: E402

pytestmark = pytest.mark.unit

_SOURCES = ("python_index", "npm_registry", "browser_download_host")
_TOKEN = "tok-SENTINEL"


def _config(**values):
    block = dict.fromkeys(_SOURCES)
    block.update(values)
    return {"install_sources": block}


@pytest.mark.parametrize("source", _SOURCES)
def test_a_configured_mirror_is_printed_alone(source, capsys):
    url = "https://mirror.example.invalid/%s/" % source
    status = install_sources.main([source], _config(**{source: url}))
    assert status is ExitCode.SUCCESS
    captured = capsys.readouterr()
    assert captured.out == url + "\n"
    assert captured.err == ""


@pytest.mark.parametrize("source", _SOURCES)
def test_null_prints_nothing_so_the_tools_own_setting_holds(source, capsys):
    others = {n: "https://other.example.invalid/" for n in _SOURCES if n != source}
    assert install_sources.main([source], _config(**others)) is ExitCode.SUCCESS
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


@pytest.mark.parametrize(
    "url",
    [
        "http://mirror.example.invalid/simple",
        "https://mirror.example.invalid/simple?token=x",
        "https://mirror.example.invalid/simple#frag",
        "https://mirror.example.invalid/a b",
        "https:///simple",
        "",
    ],
    ids=["http", "query", "fragment", "whitespace", "no-host", "empty"],
)
def test_a_url_a_mirror_cannot_take_is_config(url, capsys):
    status = install_sources.main(["npm_registry"], _config(npm_registry=url))
    assert status is ExitCode.CONFIG
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "install_sources.npm_registry" in captured.err


@pytest.mark.parametrize(
    "url",
    [
        "https://user:%s@mirror.example.invalid/simple" % _TOKEN,
        "https://%s@mirror.example.invalid/simple" % _TOKEN,
    ],
    ids=["user-and-password", "token-as-user"],
)
def test_a_user_part_is_refused_and_never_printed(url, capsys):
    status = install_sources.main(["python_index"], _config(python_index=url))
    assert status is ExitCode.CONFIG
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "SENTINEL" not in captured.err and "mirror.example" not in captured.err
    assert "install_sources.python_index" in captured.err
    assert "<hidden: it holds a user part>" in captured.err
    assert "no user part" in captured.err


def test_a_source_outside_the_closed_list_is_usage(capsys):
    assert install_sources.main(["apt_mirror"], _config()) is ExitCode.USAGE
    assert capsys.readouterr().out == ""


def test_the_closed_list_is_the_loaders_install_sources_rows():
    declared = sorted(
        k.path[1] for k in config_loader.KEYS if k.path[0] == "install_sources"
    )
    assert sorted(install_sources.SOURCES) == declared == sorted(_SOURCES)


def test_keels_own_config_sets_every_source(capsys):
    for source in _SOURCES:
        assert install_sources.main([source]) is ExitCode.SUCCESS
    assert capsys.readouterr().err == ""
