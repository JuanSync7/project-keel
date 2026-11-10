"""
title: Integration — slow tests stay in the gate and durations come from config
kind: tests
layer: n/a
summary: Uses makefile_judge to prove the real Makefile keeps slow tests and durations through verify's test hop. The duration count comes from a positive integer loader key; the slow marker is registered in both pytest twins.
"""

from __future__ import annotations

import io
import shlex
import sys
from pathlib import Path

import pytest

import makefile_judge as judge

if sys.version_info >= (3, 11):
    import tomllib
else:  # Python 3.10 uses the declared dev dependency.
    import tomli as tomllib

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import config_loader  # noqa: E402

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    ("target", "selection"),
    [("unit", "unit and not slow"), ("test", None), ("test-ship", None)],
)
def test_only_unit_excludes_slow(target: str, selection: str | None) -> None:
    words = shlex.split(judge.dry_run(target))
    assert words.count("pytest") == 1, words
    args = words[words.index("pytest") + 1 :]
    actual = args[args.index("-m") + 1] if "-m" in args else None
    assert actual == selection, (target, args)
    if selection is None:
        assert not any(arg.startswith("-m") for arg in args), (target, args)
        assert "not slow" not in " ".join(args), (target, args)


def test_verify_reaches_the_full_test_recipe() -> None:
    judge.assert_verify_keeps_slow(_ROOT)


def test_test_reads_its_duration_count_through_config_get() -> None:
    command = judge.dry_run("test")
    assert "scripts/config_get.py tests.durations" in command, command
    assert '--durations "$durations"' in command, command


def _durations_row() -> config_loader.Key:
    rows = [row for row in config_loader.KEYS if row.path == ("tests", "durations")]
    assert len(rows) == 1, "tests.durations needs one typed default row"
    return rows[0]


def test_durations_default_is_positive() -> None:
    row = _durations_row()
    assert row.type == "int"
    assert row.default == 10
    resolved = config_loader.resolve({}, [row], "defaults", stream=io.StringIO())
    assert resolved[row.path] == row.default


@pytest.mark.parametrize("value", [1, 7, 27])
def test_durations_accepts_positive_counts(value: object) -> None:
    row = _durations_row()
    resolved = config_loader.resolve({"tests": {"durations": value}}, [row], "fixture")
    assert resolved[row.path] == value


@pytest.mark.parametrize("value", [0, -1, True, "5", None])
def test_durations_refuses_zero_and_wrong_types(value: object) -> None:
    row = _durations_row()
    with pytest.raises(config_loader.WrongValue, match=r"tests\.durations"):
        config_loader.resolve(
            {"tests": {"durations": value}}, [row], "fixture", stream=io.StringIO()
        )


def test_slow_marker_is_registered_in_both_pytest_twins() -> None:
    text = (_ROOT / "pyproject.toml").read_text("utf-8")
    markers = tomllib.loads(text)["tool"]["pytest"]["ini_options"]["markers"]
    (slow,) = [marker for marker in markers if marker.startswith("slow:")]
    assert "unit" in slow and "gate" in slow, slow
    twin = _ROOT / "pyproject.toml.jinja"
    # Generated projects have no twins; their registered marker still applies.
    if twin.is_file():
        assert '"' + slow + '"' in twin.read_text("utf-8")
