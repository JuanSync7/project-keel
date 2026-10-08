"""
title: Unit — scripts/run_app.py runs the composition root config declares
kind: tests
layer: n/a
summary: run_app reads config/project.json `layers.app` and runs that module as `__main__`, so `make run` follows the manifest instead of a module name written into the Makefile. A project declaring another module runs that module, the module's own exit code comes back unchanged, and arguments after the script reach it. `--help` (or `-h`) describes the runner and runs nothing, as scripts/AGENT.md asks of every script; an argument after `--` reaches the module verbatim, `--help` included. An absent key and a null one each exit 2 with a message naming why, so a project without a composition root fails loudly rather than running nothing.
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import run_app  # noqa: E402

pytestmark = pytest.mark.unit

_MISSING = object()


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A tmp project root; sys.path, argv and sys.modules restored afterwards."""
    (tmp_path / "config").mkdir()
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(sys, "argv", list(sys.argv))
    before = set(sys.modules)
    yield tmp_path
    for name in set(sys.modules) - before:
        del sys.modules[name]


def _declare(root, app):
    layers = {} if app is _MISSING else {"app": app}
    (root / "config" / "project.json").write_text(
        json.dumps({"layers": layers}), encoding="utf-8"
    )


def _root_module(root, name, body):
    pkg = root / "src" / name
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "__main__.py").write_text(body, encoding="utf-8")


def _exit_code(call):
    """What the process would exit with: main()'s return, or a SystemExit's code."""
    try:
        return call()
    except SystemExit as stop:
        return stop.code


def test_run_app_runs_the_declared_module_and_refuses_an_undeclared_one(project):
    _root_module(project, "demo_root", "raise SystemExit(7)\n")
    _declare(project, {"path": "src/demo_root", "module": "demo_root"})
    assert _exit_code(lambda: run_app.main([], root=str(project))) == 7


def test_arguments_reach_the_module(project, capsys):
    _root_module(
        project,
        "echo_root",
        "import sys\nsys.stdout.write('|'.join(sys.argv[1:]))\n",
    )
    _declare(project, {"path": "src/echo_root", "module": "echo_root"})
    assert _exit_code(lambda: run_app.main(["a", "b c"], root=str(project))) == 0
    assert capsys.readouterr().out == "a|b c"


def test_a_module_that_returns_normally_exits_zero(project):
    _root_module(project, "quiet_root", "x = 1\n")
    _declare(project, {"path": "src/quiet_root", "module": "quiet_root"})
    assert _exit_code(lambda: run_app.main([], root=str(project))) == 0


def test_an_absent_layers_app_exits_2_naming_the_key(project, capsys):
    _declare(project, _MISSING)
    assert _exit_code(lambda: run_app.main([], root=str(project))) == 2
    assert "layers.app" in capsys.readouterr().err


def test_a_null_layers_app_exits_2_naming_no_composition_root(project, capsys):
    _declare(project, None)
    assert _exit_code(lambda: run_app.main([], root=str(project))) == 2
    assert "no composition root" in capsys.readouterr().err


@pytest.mark.parametrize(
    "app",
    [
        "src/app",
        {"path": "src/app"},
        {"path": "src/app", "module": "other.app"},
    ],
)
def test_a_malformed_layers_app_exits_2(project, capsys, app):
    _declare(project, app)
    assert _exit_code(lambda: run_app.main([], root=str(project))) == 2
    assert "layers.app" in capsys.readouterr().err


@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_help_describes_the_runner_and_runs_nothing(project, capsys, flag):
    # scripts/AGENT.md: every script is self-describing through --help.
    _root_module(project, "loud_root", "raise SystemExit(7)\n")
    _declare(project, {"path": "src/loud_root", "module": "loud_root"})
    assert _exit_code(lambda: run_app.main([flag], root=str(project))) == 0
    out = capsys.readouterr().out
    assert "layers.app" in out and "--" in out, out


def test_arguments_after_a_double_dash_reach_the_module_verbatim(project, capsys):
    _root_module(
        project,
        "echo_root",
        "import sys\nsys.stdout.write('|'.join(sys.argv[1:]))\n",
    )
    _declare(project, {"path": "src/echo_root", "module": "echo_root"})
    argv = ["--", "--help", "x"]
    assert _exit_code(lambda: run_app.main(argv, root=str(project))) == 0
    assert capsys.readouterr().out == "--help|x"
