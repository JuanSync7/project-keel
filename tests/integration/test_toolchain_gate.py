"""
title: Integration — one configured toolchain: the runner images, Node and Python CI install, and the Node fe-install accepts
kind: tests
layer: n/a
summary: config/project.json `toolchain` is the one statement of the machine the gate is built on, and every consumer is held to it. Every `runs-on` of every workflow under .github/workflows is a member of `toolchain.runner_images` and never a moving `*-latest` label, a job naming no runner or zero workflows found being a failure, not a pass. Each actions/setup-node step takes `node-version` and each actions/setup-python step takes `python-version` from the outputs of a step with id `toolchain`, earlier in the same job, that runs `scripts/check_toolchain.py versions` (which prints `toolchain.node_major` and `toolchain.python`), so no workflow carries a literal version; at least one setup step is found. `toolchain.python` satisfies both config/project.json `layers.backend.python` and pyproject.toml `requires-python`, parsed as version specifiers. The Makefile's `fe-install` recipe runs `scripts/check_toolchain.py node` before its `npm install`, and a real `make fe-install` on a copy, with a stub `node` on PATH, stops before npm when the major differs and reaches npm when it matches. Each check is a function a fixture is fed to as well: a `ubuntu-latest` runner, an unlisted image, a literal node-version, a floor the configured Python misses and a recipe that installs before it checks each make it fail, and the loader refuses a `toolchain.runner_images` list that is empty or names a blank or `-latest` label. The workflows are read with yaml, the `template` surface's parser (tests/optional_deps.py).
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

yaml = optional_deps.importorskip("yaml", extra="template")
# packaging is pytest's own dependency, so wherever this suite runs it is there.
from packaging.specifiers import SpecifierSet  # noqa: E402
from packaging.version import Version  # noqa: E402

try:
    import tomllib
except ModuleNotFoundError:  # before 3.11; pytest itself depends on tomli there
    import tomli as tomllib

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402
import config_loader  # noqa: E402
from child_env import build_child_env  # noqa: E402

pytestmark = pytest.mark.integration

_WORKFLOWS = Path(".github") / "workflows"
# The step id the setup steps read their versions from: a contract between
# each workflow and this test, documented in config/project.json `toolchain`.
_STEP_ID = "toolchain"
_CHECKER = "scripts/check_toolchain.py"
# action name -> (its version input, the check_toolchain output it must read)
_SETUP = {
    "actions/setup-node": ("node-version", "node"),
    "actions/setup-python": ("python-version", "python"),
}
_MOVING = "-latest"
_FE_INSTALL = "fe-install"
_KEYS = (
    ("toolchain", "node_major"),
    ("toolchain", "python"),
    ("toolchain", "runner_images"),
)


def _toolchain(root=_ROOT):
    """{key: value} of config/project.json `toolchain`, through the loader."""
    loaded = config_loader.read(str(root))
    rows = config_loader.rows(*_KEYS)
    values = config_loader.resolve(loaded, rows, config_loader.CONFIG_FILE)
    return {path[-1]: value for path, value in values.items()}


def _workflows(root=_ROOT):
    """{file name: parsed workflow} for every workflow file under *root*."""
    folder = Path(root) / _WORKFLOWS
    if not folder.is_dir():
        return {}
    return {
        p.name: yaml.safe_load(p.read_text(encoding="utf-8"))
        for p in sorted(folder.iterdir())
        if p.suffix in (".yml", ".yaml")
    }


def _jobs(workflows):
    """(file, job id, job) for every job of every parsed workflow."""
    for name, doc in sorted(workflows.items()):
        jobs = doc.get("jobs") if isinstance(doc, dict) else None
        for job_id, job in sorted((jobs or {}).items()):
            yield name, job_id, job if isinstance(job, dict) else {}


def _labels(runs_on):
    """The runner labels a `runs-on` value names: a string, a list of them, or
    a `{group, labels}` object."""
    if isinstance(runs_on, str):
        return [runs_on]
    if isinstance(runs_on, list):
        return list(runs_on)
    if isinstance(runs_on, dict):
        return _labels(runs_on.get("labels"))
    return []


def runner_faults(workflows, images):
    """(labels judged, one line per runner that is not a configured image)."""
    judged, faults = [], []
    for name, job_id, job in _jobs(workflows):
        if "uses" in job:
            continue  # a reusable-workflow call: the called file names its runner
        labels = _labels(job.get("runs-on"))
        if not labels:
            faults.append("%s job %s names no runner (runs-on)" % (name, job_id))
        for label in labels:
            judged.append(label)
            if not isinstance(label, str) or label.endswith(_MOVING):
                faults.append(
                    "%s job %s runs on %r, a moving label; name an image "
                    "toolchain.runner_images lists" % (name, job_id, label)
                )
            elif label not in images:
                faults.append(
                    "%s job %s runs on %r, which config/project.json "
                    "toolchain.runner_images (%s) does not list"
                    % (name, job_id, label, images)
                )
    return judged, faults


def _runs_versions(step):
    """True when *step* is the toolchain step: it runs the checker's versions mode."""
    run = step.get("run")
    if step.get("id") != _STEP_ID or not isinstance(run, str):
        return False
    words = shlex.split(run)
    return _CHECKER in words and "versions" in words


def _expression(output):
    return "${{ steps.%s.outputs.%s }}" % (_STEP_ID, output)


def setup_faults(workflows):
    """(setup steps judged, one line per setup step that does not take its
    version from an earlier toolchain step of its own job)."""
    judged, faults = 0, []
    for name, job_id, job in _jobs(workflows):
        steps = job.get("steps") or []
        source = None
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            if source is None and _runs_versions(step):
                source = i
            action = str(step.get("uses", "")).split("@", 1)[0]
            if action not in _SETUP:
                continue
            judged += 1
            field, output = _SETUP[action]
            given = (step.get("with") or {}).get(field)
            if given != _expression(output):
                faults.append(
                    "%s job %s step %d: %s %s is %r, not %s"
                    % (name, job_id, i, action, field, given, _expression(output))
                )
            if source is None:
                faults.append(
                    "%s job %s step %d: no earlier step with id %r runs `%s versions`"
                    % (name, job_id, i, _STEP_ID, _CHECKER)
                )
    return judged, faults


def python_faults(python, floors):
    """One line per (source, specifier) the configured Python does not satisfy."""
    faults = []
    for source, spec in floors:
        if not SpecifierSet(spec).contains(Version(python)):
            faults.append(
                "toolchain.python %s does not satisfy %s %r; set config/project.json "
                "toolchain.python to a version it allows" % (python, source, spec)
            )
    return faults


def _floors(root=_ROOT):
    """The Python floors a project declares: the manifest's and pyproject's."""
    loaded = config_loader.read(str(root))
    pyproject = tomllib.loads((Path(root) / "pyproject.toml").read_text("utf-8"))
    return [
        (
            "config/project.json layers.backend.python",
            loaded["layers"]["backend"]["python"],
        ),
        ("pyproject.toml requires-python", pyproject["project"]["requires-python"]),
    ]


def recipe_faults(makefile_text):
    """One line when fe-install's recipe installs before it checks Node."""
    rules = [r for r in cs.make_target_rules(makefile_text) if r.target == _FE_INSTALL]
    if not rules:
        return ["the Makefile has no %s target" % _FE_INSTALL]
    check = install = None
    for i, line in enumerate(rules[0].recipe):
        for mark in ";()":
            line = line.replace(mark, " %s " % mark)
        words = shlex.split(line)
        if check is None and _CHECKER in words and "node" in words:
            check = i
        if install is None and "npm" in words and "install" in words:
            install = i
    if check is None or install is None or check >= install:
        return [
            "%s runs `%s node` at recipe line %s and `npm install` at %s; the "
            "check must come first" % (_FE_INSTALL, _CHECKER, check, install)
        ]
    return []


def test_every_workflow_runner_is_a_configured_pinned_image():
    images = _toolchain()["runner_images"]
    workflows = _workflows()
    assert workflows, "no workflow under %s: nothing was judged" % _WORKFLOWS
    judged, faults = runner_faults(workflows, images)
    assert judged, "no job of %s names a runner" % sorted(workflows)
    assert faults == [], "\n".join(faults)

    def one(runs_on):
        return {"w.yml": {"on": {"push": None}, "jobs": {"j": {"runs-on": runs_on}}}}

    assert runner_faults(one("ubuntu-latest"), images)[1]
    assert runner_faults(one("ubuntu-22.04"), images)[1]
    assert runner_faults(one(["self-hosted", "ubuntu-latest"]), images)[1]
    assert runner_faults({"w.yml": {"jobs": {"j": {"steps": []}}}}, images)[1]
    assert runner_faults(one(images[0]), images)[1] == []


def test_the_loader_refuses_a_runner_list_that_pins_nothing():
    rows = config_loader.rows(("toolchain", "runner_images"))

    def resolved(images):
        loaded = {"toolchain": {"runner_images": images}}
        return config_loader.resolve(loaded, rows, config_loader.CONFIG_FILE)

    # A list naming a moving label, a blank label, or no label at all pins no
    # image, so the gate above would judge against nothing it can hold.
    # A space around a moving label still names it: the label is judged stripped.
    for images in (
        [],
        ["ubuntu-latest"],
        ["ubuntu-24.04", "macos-latest"],
        [" "],
        ["ubuntu-latest "],
        ["ubuntu-24.04", " macos-latest\t"],
    ):
        with pytest.raises(config_loader.ConfigError) as refused:
            resolved(images)
        assert "toolchain.runner_images" in "\n".join(refused.value.lines), images
    pinned = ["ubuntu-24.04", "ubuntu-22.04-arm"]
    assert resolved(pinned)[("toolchain", "runner_images")] == pinned


def test_setup_node_and_setup_python_read_the_toolchain_step():
    judged, faults = setup_faults(_workflows())
    assert judged, "no setup-node or setup-python step found: nothing was judged"
    assert faults == [], "\n".join(faults)

    toolchain = {
        "id": _STEP_ID,
        "run": 'python3 %s versions >> "$GITHUB_OUTPUT"' % (_CHECKER),
    }
    node = {"uses": "actions/setup-node@v6", "with": {"node-version": "22"}}
    fed = {
        "uses": "actions/setup-node@v6",
        "with": {"node-version": _expression("node")},
    }

    def job(*steps):
        return {"w.yml": {"jobs": {"j": {"runs-on": "x", "steps": list(steps)}}}}

    assert setup_faults(job(toolchain, node))[1], "a literal node-version passed"
    assert setup_faults(job(fed, toolchain))[1], "a setup before its source passed"
    assert setup_faults(job(fed))[1], "a setup with no toolchain step passed"
    assert setup_faults(job(toolchain, fed)) == (1, [])


def test_the_configured_python_satisfies_the_backend_floor_and_requires_python():
    python = _toolchain()["python"]
    floors = _floors()
    assert len(floors) == 2
    faults = python_faults(python, floors)
    assert faults == [], "\n".join(faults)

    bad = python_faults("3.11", [("layers.backend.python", ">=3.12")])
    assert bad and "toolchain.python" in bad[0]
    assert python_faults("3.12", [("layers.backend.python", ">=3.10,<3.13")]) == []


def _stub(folder, name, body):
    path = folder / name
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)


def _fe_install_copy(tmp_path, node_prints):
    """`make fe-install` on a copy of this project with one stub app, a stub
    `node` printing *node_prints* and a stub `npm` that records its call."""
    work = tmp_path / ("major-" + node_prints)
    makefile_copy.copy_makefiles(work, _ROOT)
    shutil.copytree(
        str(_ROOT / "scripts"),
        str(work / "scripts"),
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    (work / "config").mkdir()
    shutil.copy(str(_ROOT / config_loader.CONFIG_FILE), str(work / "config"))
    app = work / "src" / "frontend" / "stub"
    app.mkdir(parents=True)
    (app / "package.json").write_text(json.dumps({"name": "stub"}))
    bin_dir = tmp_path / ("bin-" + node_prints)
    bin_dir.mkdir()
    called = tmp_path / ("npm-called-" + node_prints)
    _stub(bin_dir, "node", "echo %s\n" % node_prints)
    _stub(bin_dir, "npm", "touch %s\n" % shlex.quote(str(called)))
    path = os.pathsep.join([str(bin_dir), os.environ.get("PATH", "")])
    ran = subprocess.run(
        ["make", "--no-print-directory", "PY=" + sys.executable, _FE_INSTALL],
        cwd=str(work),
        env=build_child_env(extra={"PATH": path}),
        capture_output=True,
        text=True,
        timeout=300,
    )
    return ran, called.exists()


@pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
def test_fe_install_checks_node_before_npm(tmp_path):
    makefile = (_ROOT / "Makefile").read_text(encoding="utf-8")
    assert recipe_faults(makefile) == []
    reordered = "%s:\n\t(cd x && npm install)\n\t$(PY) %s node\n" % (
        _FE_INSTALL,
        _CHECKER,
    )
    assert recipe_faults(reordered), "an install before the check passed"

    major = _toolchain()["node_major"]
    ran, npm_ran = _fe_install_copy(tmp_path, "v1.0.0")
    assert ran.returncode != 0, ran.stdout + ran.stderr
    assert not npm_ran, "npm ran under a node whose major is not configured"
    assert "toolchain.node_major" in ran.stderr, ran.stderr
    # The differential: the same copy with the configured major reaches npm.
    ran, npm_ran = _fe_install_copy(tmp_path, "v%d.0.0" % major)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert npm_ran, "the configured major never reached npm"
