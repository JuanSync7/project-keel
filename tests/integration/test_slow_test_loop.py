"""
title: Integration — slow tests stay in the gate and durations come from config
kind: tests
layer: n/a
summary: Reads the real make recipes through dry runs and the structure check's recipe reader: unit excludes slow, test and test-ship retain every marker, and verify reaches test without a slow exclusion. The duration count comes from a positive integer loader key with a default; the slow marker is registered in both pytest twins.
"""

import io
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 uses the declared dev dependency.
    import tomli as tomllib

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402
import config_loader  # noqa: E402
from child_env import build_child_env  # noqa: E402

pytestmark = pytest.mark.integration


def _dry_run(target):
    timeout = config_loader.resolve(
        config_loader.read(_ROOT, "config/project.json"),
        [
            row
            for row in config_loader.KEYS
            if row.path == ("tests", "child_timeout_seconds")
        ],
        "config/project.json",
    )[("tests", "child_timeout_seconds")]
    proc = subprocess.run(
        ["make", "-n", target, "PY=" + sys.executable],
        cwd=_ROOT,
        env=build_child_env(),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout


@pytest.mark.parametrize(
    ("target", "selection"),
    [("unit", "unit and not slow"), ("test", None), ("test-ship", None)],
)
def test_only_unit_excludes_slow(target, selection):
    words = shlex.split(_dry_run(target))
    assert words.count("pytest") == 1, words
    args = words[words.index("pytest") + 1 :]
    actual = args[args.index("-m") + 1] if "-m" in args else None
    assert actual == selection, (target, args)
    if selection is None:
        assert not any(arg.startswith("-m") for arg in args), (target, args)
        assert "not slow" not in " ".join(args), (target, args)


def test_verify_reaches_the_full_test_recipe():
    rules = cs.make_target_rules((_ROOT / "Makefile").read_text("utf-8"))
    (verify,) = [rule for rule in rules if rule.target == "verify"]
    (command,) = verify.recipe
    words = shlex.split(command)
    assert words[words.index("--") + 1] == "$(MAKE)", command
    assert "test" in words[words.index("--") + 2 :], command
    assert "not slow" not in command, command


def test_test_reads_its_duration_count_through_config_get():
    command = _dry_run("test")
    assert "scripts/config_get.py tests.durations" in command, command
    assert '--durations "$durations"' in command, command


def _durations_row():
    rows = [row for row in config_loader.KEYS if row.path == ("tests", "durations")]
    assert len(rows) == 1, "tests.durations needs one typed default row"
    return rows[0]


def test_durations_default_is_positive():
    row = _durations_row()
    assert row.type == "int"
    assert row.default == 10
    resolved = config_loader.resolve({}, [row], "defaults", stream=io.StringIO())
    assert resolved[row.path] == row.default


@pytest.mark.parametrize("value", [1, 7, 27])
def test_durations_accepts_positive_counts(value):
    row = _durations_row()
    resolved = config_loader.resolve({"tests": {"durations": value}}, [row], "fixture")
    assert resolved[row.path] == value


@pytest.mark.parametrize("value", [0, -1, True, "5", None])
def test_durations_refuses_zero_and_wrong_types(value):
    row = _durations_row()
    with pytest.raises(config_loader.WrongValue, match=r"tests\.durations"):
        config_loader.resolve(
            {"tests": {"durations": value}}, [row], "fixture", stream=io.StringIO()
        )


def test_slow_marker_is_registered_in_both_pytest_twins():
    text = (_ROOT / "pyproject.toml").read_text("utf-8")
    markers = tomllib.loads(text)["tool"]["pytest"]["ini_options"]["markers"]
    (slow,) = [marker for marker in markers if marker.startswith("slow:")]
    assert "unit" in slow and "gate" in slow, slow
    twin = _ROOT / "pyproject.toml.jinja"
    # Generated projects have no twins; their registered marker still applies.
    if twin.is_file():
        assert '"' + slow + '"' in twin.read_text("utf-8")
