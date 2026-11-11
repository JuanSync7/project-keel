"""
title: Unit — child environment entry boundary
summary: Refusals from either environment import return CONFIG without ending the process; other exceptions propagate and success returns unchanged.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from exit_codes import ExitCode

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("package_import", [False, True])
def test_child_env_boundary_returns_config_without_ending_process(
    package_import, capsys
):
    import importlib

    from child_env_entry import child_env_errors

    environment = importlib.import_module(
        "scripts.child_env" if package_import else "child_env"
    )

    @child_env_errors
    def entry():
        raise environment.ChildEnvError("HTTPS_PROXY is refused")

    assert entry() is ExitCode.CONFIG
    assert entry.__name__ == "entry"
    message = capsys.readouterr().err
    assert "HTTPS_PROXY" in message
    assert ";" in message
    assert "Traceback" not in message


def test_entry_boundary_preserves_success_and_unrelated_errors(capsys):
    from child_env_entry import child_env_errors

    @child_env_errors
    def success(value):
        return value

    assert success(ExitCode.SUCCESS) is ExitCode.SUCCESS
    assert capsys.readouterr() == ("", "")

    @child_env_errors
    def broken():
        raise OSError("not an environment refusal")

    with pytest.raises(OSError, match="not an environment refusal"):
        broken()
