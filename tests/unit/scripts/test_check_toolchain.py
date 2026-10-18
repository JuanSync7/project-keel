"""
title: Unit — check_toolchain (the configured Node major, and the versions CI installs)
kind: tests
layer: n/a
summary: scripts/check_toolchain.py driven with an injected config object and an injected runner, so no case reads config/project.json or spawns node. Mode `node` compares the major of `node --version` with config/project.json `toolchain.node_major`: the configured major passes, a pre-release suffix included, another major is FAILURE naming both majors and the key, and a node that is absent, exits non-zero or prints something that is not a version is FAILURE with a message and never a traceback. Mode `versions` prints `node=<toolchain.node_major>` and `python=<toolchain.python>` one per line, for a workflow step's `$GITHUB_OUTPUT`, read from config and checked with non-default values so a literal cannot pass. A value the loader refuses is CONFIG naming the key, and an unknown mode is USAGE.
@covers scripts/check_toolchain.py
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_toolchain  # noqa: E402
from exit_codes import ExitCode  # noqa: E402

pytestmark = pytest.mark.unit


def _config(node_major=24, python="3.11", images=("ubuntu-24.04",)):
    return {
        "toolchain": {
            "node_major": node_major,
            "python": python,
            "runner_images": list(images),
        }
    }


def _prints(text, status=0):
    calls = []

    def runner(argv):
        calls.append(list(argv))
        return status, text

    runner.calls = calls
    return runner


def _absent(argv):
    raise FileNotFoundError(2, "No such file or directory", argv[0])


def test_node_major_is_compared_to_config(capsys):
    runner = _prints("v24.15.0\n")
    assert check_toolchain.main(["node"], runner, _config(24)) is ExitCode.SUCCESS
    assert runner.calls == [["node", "--version"]]

    # A pre-release build still carries its major.
    nightly = _prints("v24.0.0-nightly20260101\n")
    assert check_toolchain.main(["node"], nightly, _config(24)) is ExitCode.SUCCESS

    capsys.readouterr()
    wrong = check_toolchain.main(["node"], _prints("v22.1.0\n"), _config(24))
    assert wrong is ExitCode.FAILURE
    err = capsys.readouterr().err
    for contract in ("22", "24", "toolchain.node_major"):
        assert contract in err, err

    # The comparison follows the config, not a literal: 22 passes when 22 is set.
    assert (
        check_toolchain.main(["node"], _prints("v22.1.0\n"), _config(22))
        is ExitCode.SUCCESS
    )

    for runner in (_absent, _prints("garbage\n"), _prints("", status=1)):
        capsys.readouterr()
        assert check_toolchain.main(["node"], runner, _config(24)) is ExitCode.FAILURE
        err = capsys.readouterr().err
        assert err.strip(), "a refusal with no message"
        assert "Traceback" not in err


def test_versions_mode_prints_the_configured_node_and_python(capsys):
    def never(argv):
        raise AssertionError("versions mode ran %r" % (argv,))

    status = check_toolchain.main(["versions"], never, _config(20, "3.12"))
    assert status is ExitCode.SUCCESS
    assert capsys.readouterr().out == "node=20\npython=3.12\n"


def test_a_refused_value_is_a_config_fault_naming_the_key(capsys):
    for bad, key in (
        (_config(node_major="24"), "toolchain.node_major"),
        (_config(node_major=0), "toolchain.node_major"),
        (_config(python=""), "toolchain.python"),
        (_config(python="3.x"), "toolchain.python"),
        # str.isdigit is true for these; setup-python reads ASCII digits only.
        (_config(python="3.\u00b2"), "toolchain.python"),
        (_config(python="\uff13.\uff11\uff11"), "toolchain.python"),
    ):
        capsys.readouterr()
        status = check_toolchain.main(["versions"], _prints("v24.0.0\n"), bad)
        assert status is ExitCode.CONFIG, bad
        assert key in capsys.readouterr().err


def test_an_unknown_mode_is_a_usage_error(capsys):
    status = check_toolchain.main(["nod"], _prints("v24.0.0\n"), _config())
    assert status is ExitCode.USAGE
    assert check_toolchain.main(["--help"], _prints(""), _config()) is (
        ExitCode.SUCCESS
    )
    assert "node" in capsys.readouterr().out
