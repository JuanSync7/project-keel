"""
title: Unit — tests/selection_guard.py decides a run that ran zero tests
kind: tests
layer: n/a
summary: The verdict table the suite's end-of-session guard applies. Zero tests ran is exit 5 unless the selection is one bare marker config/project.json `make_targets.empty_test_selections` declares, which is exit 0 with its reason; a declared marker whose tests ran is exit 1 (the declaration is stale); any other run is left alone. A compound `-m` expression, the whole suite and a run narrowed by a path or `-k` are never exempt, and the message names what was selected. A make_targets block the policy rejects raises instead of reading as no declarations.
"""

import json
import runpy
import shlex
import sys
from pathlib import Path

import pytest

import selection_guard as sg

pytestmark = pytest.mark.unit


def test_verdict_table():
    code, msg = sg.verdict(0, "smoke", {})
    assert code == 5 and "make_targets.empty_test_selections" in msg, msg
    code, msg = sg.verdict(0, "smoke", {"smoke": "no smoke surface yet"})
    assert code == 0 and "no smoke surface yet" in msg, msg
    code, msg = sg.verdict(3, "smoke", {"smoke": "r"})
    assert code == 1 and "stale: make_targets.empty_test_selections.smoke" in msg
    assert sg.verdict(3, "smoke", {}) == (None, "")
    assert sg.verdict(3, "", {}) == (None, "")


def test_a_compound_expression_or_the_whole_suite_is_never_exempt():
    assert sg.verdict(0, "smoke and not slow", {"smoke": "r"})[0] == 5
    assert sg.verdict(3, "smoke and not slow", {"smoke": "r"}) == (None, "")
    assert sg.verdict(0, "", {})[0] == 5
    assert sg.verdict(0, "", {"smoke": "r"})[0] == 5


def test_a_narrowed_selection_is_named_and_never_exempt():
    declared = {"smoke": "r"}
    code, msg = sg.verdict(0, "", {}, paths=["tests/test_x.py"])
    assert code == 5 and "the whole suite" not in msg, msg
    assert "tests/test_x.py" in msg, msg
    code, msg = sg.verdict(0, "", {}, keyword="run or smoke")
    assert code == 5 and "-k run or smoke" in msg, msg
    # A declared marker exempts only the bare `-m <marker>` run of the suite.
    code, msg = sg.verdict(0, "smoke", declared, keyword="nomatch")
    assert code == 5 and "-m smoke -k nomatch" in msg, msg
    code, msg = sg.verdict(0, "smoke", declared, paths=["tests/test_x.py"])
    assert code == 5, msg
    # Only the bare marker run is told it may declare; every message names the
    # key so a reader can find the rule.
    assert "declare the marker" in sg.verdict(0, "smoke", {})[1]
    for kwargs in ({"keyword": "k"}, {"paths": ["p"]}):
        msg = sg.verdict(0, "smoke", {}, **kwargs)[1]
        assert "declare the marker" not in msg, msg
        assert "make_targets.empty_test_selections" in msg, msg
    msg = sg.verdict(0, "", {})[1]
    assert "the whole suite" in msg and "declare the marker" not in msg, msg


@pytest.mark.parametrize(
    "markexpr, expect",
    [
        ("smoke", ["smoke"]),
        (" smoke ", ["smoke"]),
        ("", []),
        ("smoke and not slow", []),
        ("not smoke", []),
        ("smoke or e2e", []),
        ("(smoke)", []),
    ],
)
def test_only_a_bare_marker_is_a_declarable_selection(markexpr, expect):
    assert sg.selected_markers(markexpr) == expect


_ROOT = Path(__file__).resolve().parents[2]
_UNSET = object()


def _manifest(value=_UNSET):
    """This project's manifest with empty_test_selections replaced (or removed)."""
    manifest = json.loads((_ROOT / "config" / "project.json").read_text("utf-8"))
    manifest["make_targets"].pop("empty_test_selections", None)
    if value is not _UNSET:
        manifest["make_targets"]["empty_test_selections"] = value
    return manifest


def test_declared_empty_reads_the_policy():
    assert sg.declared_empty(_manifest({"smoke": "r"})) == {"smoke": "r"}


@pytest.mark.parametrize("value", [None, ["smoke"], {"smoke": ""}])
def test_declared_empty_raises_on_a_block_the_policy_rejects(value):
    manifest = _manifest() if value is None else _manifest(value)
    with pytest.raises(RuntimeError, match="empty_test_selections"):
        sg.declared_empty(manifest)


def test_declared_empty_reads_this_projects_config_by_default():
    assert isinstance(sg.declared_empty(), dict)


_NARROWING = [
    ["-k", "test_passes"],
    ["-ktest_passes"],
    ["-k=test_passes"],
    ["-m", "unit"],
    ["-munit"],
    ["-m=unit"],
    ["tests/test_x.py::test_passes"],
    ["--deselect", "tests/test_x.py::test_other"],
    ["--deselect=tests/test_x.py::test_other"],
]


@pytest.mark.parametrize("tokens", _NARROWING)
@pytest.mark.parametrize("source", ["command line", "PYTEST_ADDOPTS"])
def test_full_gate_refuses_each_narrowing(tokens, source, monkeypatch, capsys):
    monkeypatch.setenv(
        "PYTEST_ADDOPTS", shlex.join(tokens) if source != "command line" else ""
    )
    monkeypatch.setattr(
        sys, "argv", [sg.__file__] + (tokens if source == "command line" else [])
    )
    with pytest.raises(SystemExit) as caught:
        runpy.run_path(sg.__file__, run_name="__main__")
    assert caught.value.code == 2
    message = capsys.readouterr().err
    assert source in message and tokens[0] in message, message


@pytest.mark.parametrize(
    "addopts",
    [
        "-q",
        "-p no:cacheprovider",
        "-x",
        "-rA",
        "--tb=short",
        "-W ignore::DeprecationWarning",
    ],
)
def test_full_gate_accepts_harmless_addopts(addopts, monkeypatch):
    monkeypatch.setenv("PYTEST_ADDOPTS", addopts)
    monkeypatch.setattr(sys, "argv", [sg.__file__])
    with pytest.raises(SystemExit) as caught:
        runpy.run_path(sg.__file__, run_name="__main__")
    assert caught.value.code == 0


def test_full_gate_refuses_unparseable_addopts(monkeypatch, capsys):
    monkeypatch.setenv("PYTEST_ADDOPTS", "-k 'unterminated")
    monkeypatch.setattr(sys, "argv", [sg.__file__])
    with pytest.raises(SystemExit) as caught:
        runpy.run_path(sg.__file__, run_name="__main__")
    assert caught.value.code == 2
    assert "cannot parse PYTEST_ADDOPTS" in capsys.readouterr().err


@pytest.mark.parametrize(
    "addopts",
    [
        "-xk foo",
        "-qkfoo",
        "--lf",
        "--last-failed",
        "--sw",
        "--ignore=tests/integration",
        "--ignore-glob tests/integration/*",
        "--co",
        "--collect-only",
        "--noconftest",
        "-c other.ini",
        "-o addopts=-kfoo",
        "--rootdir other",
        "--unknown-option",
        "-p otherplugin",
        "-qpotherplugin",
        "-qZ",
        "tests/integration",
        "-W",
        "--tb",
        "--quiet=yes",
    ],
)
@pytest.mark.parametrize("source", ["command line", "PYTEST_ADDOPTS"])
def test_full_gate_requires_positive_option_recognition(addopts, source, capsys):
    args = shlex.split(addopts) if source == "command line" else []
    assert sg.check_full_gate(args, addopts if source == "PYTEST_ADDOPTS" else "") == 2
    message = capsys.readouterr().err
    assert source in message and shlex.split(addopts)[0] in message, message


def test_full_gate_consumes_harmless_values_before_judging_positionals():
    options = [
        "-qvxslrA -W ignore::DeprecationWarning -p=no:cacheprovider",
        "--tb short --color=yes --durations 3 -Wignore::DeprecationWarning",
        "--keel-full-gate -n auto --junitxml=report.xml -W ignore::DeprecationWarning",
    ]
    assert len(options) == 3
    for options_text in options:
        assert sg.check_full_gate(shlex.split(options_text), options_text) == 0
