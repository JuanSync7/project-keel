"""
title: Integration — the install recipes pass config/project.json install_sources to npm and the browser runner
kind: tests
layer: n/a
summary: A real `make fe-install` and `make fe-browsers` on a copy of this project with one stub app, a stub `node` printing the configured major and a stub `npm` that records its arguments and PLAYWRIGHT_DOWNLOAD_HOST. With `install_sources.npm_registry` and `browser_download_host` null, npm is called as plain `npm install` and the browser runner sees no PLAYWRIGHT_DOWNLOAD_HOST, so the user's own .npmrc and the runner's default host hold; set, npm gets `--registry <url>` and the runner gets the host, each read from the copy's config and never a literal. Every workflow step under .github/workflows that runs `pip install` or `npm ci`/`npm install` is run for real under `bash -e`, from its working-directory in a copy whose config sets the sources, with stub `pip` and `npm`: each passes `--index-url` or `--registry` with the configured URL, and with the sources null it passes neither; a workflow tree with no such step is a failure, not a pass. A value with a URL user part stops each target before npm runs, its recipe ending 14 (CONFIG), the refusal naming the key and never the user part.
@covers Makefile
@covers scripts/install_sources.py
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
import optional_deps

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import config_loader  # noqa: E402
from child_env import build_child_env  # noqa: E402
from exit_codes import ExitCode  # noqa: E402

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("make") is None, reason="make not installed"),
]

_REGISTRY = "https://npm.mirror.example.invalid/registry/"
_HOST = "https://browsers.mirror.example.invalid"
_TOKEN = "tok-SENTINEL"


def _stub(folder, name, body):
    path = folder / name
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)


def _copy(tmp_path, sources):
    """A copy of this project whose config sets install_sources to *sources*,
    with one stub app that already has node_modules."""
    work = tmp_path / "work"
    makefile_copy.copy_makefiles(work, _ROOT)
    shutil.copytree(
        str(_ROOT / "scripts"),
        str(work / "scripts"),
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    (work / "config").mkdir()
    config = json.loads((_ROOT / config_loader.CONFIG_FILE).read_text("utf-8"))
    config["install_sources"].update(sources)
    (work / config_loader.CONFIG_FILE).write_text(json.dumps(config, indent=2))
    app = work / "src" / "frontend" / "stub"
    (app / "node_modules").mkdir(parents=True)
    (app / "package.json").write_text(json.dumps({"name": "stub"}))
    return work, config["toolchain"]["node_major"]


def _make(tmp_path, work, major, target):
    """Run *target* in *work* with stub node and npm. -> (completed, the npm
    calls recorded, one line each: its arguments, then the host it saw)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log = tmp_path / "npm-calls"
    _stub(bin_dir, "node", "echo v%d.0.0\n" % major)
    _stub(
        bin_dir,
        "npm",
        'printf "%%s|%%s\\n" "$*" "${PLAYWRIGHT_DOWNLOAD_HOST-<unset>}" >> %s\n'
        % shlex.quote(str(log)),
    )
    path = os.pathsep.join([str(bin_dir), os.environ.get("PATH", "")])
    ran = subprocess.run(
        ["make", "--no-print-directory", "PY=" + sys.executable, target],
        cwd=str(work),
        env=build_child_env(extra={"PATH": path}),
        capture_output=True,
        text=True,
        timeout=300,
    )
    calls = log.read_text().splitlines() if log.exists() else []
    return ran, calls


def test_null_sources_pass_nothing_so_the_tools_own_setting_holds(tmp_path):
    work, major = _copy(tmp_path, {"npm_registry": None, "browser_download_host": None})
    ran, calls = _make(tmp_path, work, major, "fe-install")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert calls == ["install|<unset>"], calls
    ran, calls = _make(tmp_path, work, major, "fe-browsers")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert len(calls) == 2 and calls[1].endswith("|<unset>"), calls


def test_a_configured_mirror_reaches_npm_and_the_browser_runner(tmp_path):
    work, major = _copy(
        tmp_path, {"npm_registry": _REGISTRY, "browser_download_host": _HOST}
    )
    ran, calls = _make(tmp_path, work, major, "fe-install")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert calls[0].split("|")[0].split() == ["install", "--registry", _REGISTRY]
    ran, calls = _make(tmp_path, work, major, "fe-browsers")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    args, host = calls[1].split("|")
    assert args.split()[:2] == ["run", "--silent"], calls
    assert host == _HOST, calls


@pytest.mark.parametrize(
    "target, key",
    [("fe-install", "npm_registry"), ("fe-browsers", "browser_download_host")],
)
def test_a_user_part_stops_the_target_before_npm_and_is_never_shown(
    tmp_path, target, key
):
    url = "https://u:%s@mirror.example.invalid/" % _TOKEN
    work, major = _copy(tmp_path, {key: url})
    ran, calls = _make(tmp_path, work, major, target)
    # make ends 2 on any failed recipe and names the recipe's own status.
    assert ran.returncode == 2, ran.stdout + ran.stderr
    assert "Error %d" % ExitCode.CONFIG in ran.stderr, ran.stderr
    assert calls == [], calls
    assert "install_sources." + key in ran.stderr, ran.stderr
    assert "SENTINEL" not in ran.stdout + ran.stderr


_WORKFLOWS = _ROOT / ".github" / "workflows"
_FLAG = {"pip": "--index-url", "npm": "--registry"}


def _install_steps():
    """Every (workflow, step) whose run line calls pip or npm to install."""
    yaml = optional_deps.importorskip("yaml", extra="template")
    found = []
    for path in sorted(_WORKFLOWS.glob("*.yml")):
        for job in (yaml.safe_load(path.read_text("utf-8")) or {})["jobs"].values():
            for step in job.get("steps", []):
                run = step.get("run", "")
                if "pip install" in run or "npm ci" in run or "npm install" in run:
                    found.append((path.name, step))
    return found


def _run_step(tmp_path, step, sources, tag):
    work = tmp_path / ("ws-" + tag)
    if not work.exists():
        shutil.copytree(
            str(_ROOT / "scripts"),
            str(work / "scripts"),
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        (work / "config").mkdir()
        config = json.loads((_ROOT / config_loader.CONFIG_FILE).read_text("utf-8"))
        config["install_sources"].update(sources)
        (work / config_loader.CONFIG_FILE).write_text(json.dumps(config))
    cwd = work / step.get("working-directory", ".")
    cwd.mkdir(parents=True, exist_ok=True)
    bin_dir = tmp_path / ("bin-" + tag)
    bin_dir.mkdir(exist_ok=True)
    log = tmp_path / ("calls-" + tag)
    if log.exists():
        log.unlink()
    for tool in ("pip", "npm"):
        _stub(bin_dir, tool, 'echo "%s $*" >> %s\n' % (tool, shlex.quote(str(log))))
    _stub(bin_dir, "python", 'exec %s "$@"\n' % shlex.quote(sys.executable))
    path = os.pathsep.join([str(bin_dir), os.environ.get("PATH", "")])
    ran = subprocess.run(
        ["bash", "-e", "-c", step["run"]],
        cwd=str(cwd),
        env=build_child_env(extra={"PATH": path}),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert ran.returncode == 0, ran.stdout + ran.stderr
    return log.read_text().splitlines() if log.exists() else []


def test_every_workflow_install_step_takes_the_configured_mirror(tmp_path):
    steps = _install_steps()
    assert steps, "no workflow step under %s installs: nothing was judged" % _WORKFLOWS
    index = "https://pypi.mirror.example.invalid/simple/"
    configured = {"python_index": index, "npm_registry": _REGISTRY}
    nulls = {"python_index": None, "npm_registry": None}
    for name, step in steps:
        tool = "pip" if "pip install" in step["run"] else "npm"
        flag = _FLAG[tool]
        url = index if tool == "pip" else _REGISTRY
        calls = _run_step(tmp_path, step, configured, "set")
        assert len(calls) == 1, (name, calls)
        words = calls[0].split()
        assert words[0] == tool and flag in words, (name, calls)
        assert words[words.index(flag) + 1] == url, (name, calls)
        calls = _run_step(tmp_path, step, nulls, "null")
        assert len(calls) == 1 and flag not in calls[0].split(), (name, calls)
