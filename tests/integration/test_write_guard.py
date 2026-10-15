"""
title: Integration — a [write] target refuses to run unattended
kind: tests
layer: n/a
summary: Keel's Makefile defines `WRITE_GUARD`, the make-level refusal a [write] target opens its recipe with. Driven through real `make`, a demo [write] target that includes keel's Makefile runs when no unattended variable is set and refuses, writing nothing, when any variable config/project.json `make_targets.unattended_vars` names is set in the environment or on the command line. The guard also holds when make ignores recipe errors: under `-i`, `--ignore-errors`, `MAKEFLAGS=i` or a bare `.IGNORE:` it stops make with an error before the write, for an unattended and an attended run alike, while `-k`, `-j2`, `--no-print-directory` and a command-line variable whose value is `i` leave an attended write to run. scripts/run_make_target.py refuses the same target by its label before make runs, refuses `-i` and `--ignore-errors` as arguments, and refuses `-f`, the argument that would point make at another makefile. The attended cases drop make's inherited MAKEFLAGS, and are re-run through the gate runner, so the suite stays green when a gate run is what started it.
"""

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import makefile_copy

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import run_make_target as rmt  # noqa: E402

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("make") is None, reason="make not installed"),
]

_POLICY = json.loads((_ROOT / "config" / "project.json").read_text("utf-8"))[
    "make_targets"
]
_DEMO = (
    "include Makefile\n"
    "\n"
    "demo-apply: ## [write] Change shared state (a demo)\n"
    "\t$(WRITE_GUARD)\n"
    "\t@echo applied > applied.txt\n"
)


@pytest.fixture
def guarded(tmp_path):
    makefile_copy.copy_makefiles(tmp_path, _ROOT)
    (tmp_path / "demo.mk").write_text(_DEMO, encoding="utf-8")
    return tmp_path


# make hands its command-line variables to every child through these, so a suite
# run under the gate runner (RALPH=1 on make's command line) would otherwise
# reach this test's make as unattended.
_MAKE_INHERITANCE = ("MAKEFLAGS", "MFLAGS", "MAKELEVEL", "MAKEOVERRIDES")


def _make(root, env_over, *args):
    drop = set(_POLICY["unattended_vars"]) | set(_MAKE_INHERITANCE)
    env = {k: v for k, v in os.environ.items() if k not in drop}
    env.update(env_over)
    return subprocess.run(
        ["make", "-s", "-f", "demo.mk", "demo-apply"] + list(args),
        cwd=str(root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )


@pytest.mark.parametrize("env_over", [{}, {"CI": ""}], ids=["unset", "empty"])
def test_a_write_target_runs_when_attended(guarded, env_over):
    r = _make(guarded, env_over)
    assert r.returncode == 0, r.stderr
    assert (guarded / "applied.txt").is_file()


@pytest.mark.parametrize("var", _POLICY["unattended_vars"])
@pytest.mark.parametrize("where", ["environment", "command-line"])
def test_a_write_target_refuses_under_any_unattended_variable(guarded, var, where):
    if where == "environment":
        r = _make(guarded, {var: "1"})
    else:
        r = _make(guarded, {}, var + "=1")
    assert r.returncode != 0, r.stdout
    assert "refusing 'demo-apply'" in r.stderr, r.stderr
    assert "docs/adr/keel/K-0011-make-target-effect-labels.md" in r.stderr, r.stderr
    assert not (guarded / "applied.txt").exists()


# The ways make can be told to carry on past a failing recipe line. The flag
# forms put `i` in MAKEFLAGS' first word, and a bare `.IGNORE:` sets make's
# global ignore-errors switch, which MAKEFLAGS then shows too (GNU Make 4.2.1,
# measured); `.IGNORE: <target>` does neither, so check_W refuses it statically.
_IGNORING = {
    "dash-i": ({}, ["-i"], ""),
    "ignore-errors": ({}, ["--ignore-errors"], ""),
    "makeflags-env": ({"MAKEFLAGS": "i"}, [], ""),
    "bare-ignore-rule": ({}, [], ".IGNORE:\n"),
}


@pytest.mark.parametrize("var", _POLICY["unattended_vars"])
@pytest.mark.parametrize("mode", sorted(_IGNORING))
def test_the_guard_holds_when_make_ignores_errors(guarded, var, mode):
    """Under -i or .IGNORE, make ignores the guard's `exit 1` and runs the write
    (measured with a shell-only guard: `Error 1 (ignored)`, the write ran, rc 0).
    The guard's make-level clause aborts before the recipe's first line runs."""
    env_over, args, extra = _IGNORING[mode]
    if extra:
        with (guarded / "demo.mk").open("a", encoding="utf-8") as fh:
            fh.write(extra)
    r = _make(guarded, dict(env_over, **{var: "1"}), *args)
    assert r.returncode != 0, r.stdout + r.stderr
    assert "refusing 'demo-apply'" in r.stderr, r.stderr
    assert not (guarded / "applied.txt").exists(), r.stdout + r.stderr


@pytest.mark.parametrize(
    "args",
    [["-k"], ["-j2"], ["--no-print-directory"], ["NOT_A_FLAG=i"]],
    ids=["keep-going", "jobs", "long-option-only", "variable-holding-i"],
)
def test_ignoring_errors_alone_does_not_trip_an_attended_plain_target(guarded, args):
    """The clause reads only the single-letter flags in MAKEFLAGS' first word, so
    other flags and a variable whose value holds `i` leave an attended write to
    run."""
    r = _make(guarded, {}, *args)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (guarded / "applied.txt").is_file()


def test_an_attended_write_under_ignore_errors_is_refused_too(guarded):
    """No [write] target is safe under -i, attended or not: a failing step would
    be ignored and the next one would act on its half-done state."""
    r = _make(guarded, {}, "-i")
    assert r.returncode != 0, r.stdout + r.stderr
    assert "ignoring recipe errors" in r.stderr, r.stderr
    assert not (guarded / "applied.txt").exists()


def _gate_repo(tmp_path):
    (tmp_path / "config").mkdir()
    shutil.copy(str(_ROOT / "config" / "project.json"), str(tmp_path / "config"))
    (tmp_path / "Makefile").write_text(
        "quiet: ## [local] Reads nothing, writes nothing\n\t@true\n"
        + _DEMO.replace("include Makefile\n", "include keel.mk\n"),
        encoding="utf-8",
    )
    makefile_copy.copy_makefiles(tmp_path, _ROOT, as_name="keel.mk")
    for argv in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "fixture"]):
        r = subprocess.run(["git"] + argv, cwd=str(tmp_path), capture_output=True)
        assert r.returncode == 0, r.stderr
    return tmp_path


def test_the_gate_runner_refuses_a_write_target_by_its_label(tmp_path):
    repo = _gate_repo(tmp_path)
    res = rmt.run_target("demo-apply", cwd=str(repo))
    assert res["ok"] is False and "[write]" in res["refused"], res
    assert not (repo / "applied.txt").exists()
    # the control: the same runner over the same tree runs a [local] target
    quiet = rmt.run_target("quiet", cwd=str(repo))
    assert quiet["ok"] is True and quiet["changed"] == [], quiet


@pytest.mark.parametrize("extra", [["-f", "demo.mk"], ["--file=demo.mk"]])
def test_the_gate_runner_refuses_another_makefile(tmp_path, extra):
    repo = _gate_repo(tmp_path)
    (repo / "demo.mk").write_text(_DEMO.replace("include Makefile\n", ""), "utf-8")
    res = rmt.run_target("quiet", cwd=str(repo), extra=extra)
    assert res["refused"] and "NAME=VALUE" in res["refused"], res
    assert not (repo / "applied.txt").exists()


@pytest.mark.parametrize("flag", ["-i", "--ignore-errors"])
def test_the_gate_runner_refuses_a_flag_that_ignores_errors(tmp_path, flag):
    """The runner forwards only NAME=VALUE gate variables and drops the caller's
    MAKEFLAGS (scripts/child_env.py), so make's ignore-errors flag cannot reach a
    gate run that way."""
    repo = _gate_repo(tmp_path)
    res = rmt.run_target("quiet", cwd=str(repo), extra=[flag])
    assert res["refused"] and "NAME=VALUE" in res["refused"], res


def test_the_suite_holds_under_the_gate_runner(tmp_path):
    """The gate runner puts RALPH=1 on make's command line, and make hands it to
    every child through MAKEFLAGS; a test that runs make attended must drop that
    inheritance, or `make test` through the runner is red (measured: 2 failed)."""
    repo = _gate_repo(tmp_path)
    (repo / "Makefile").write_text(
        "suite: ## [local] Runs the attended write-guard cases\n"
        "\t@cd %s && PYTHONPATH=src:tests:. %s -m pytest %s -k runs_when_attended "
        "-q -p no:cacheprovider\n"
        % (
            shlex.quote(str(_ROOT)),
            shlex.quote(sys.executable),
            "tests/integration/test_write_guard.py",
        ),
        encoding="utf-8",
    )
    res = rmt.run_target("suite", cwd=str(repo), timeout=300)
    assert res["ok"] is True and "2 passed" in res["output"], res["output"]
