"""
title: Integration — every Python workflow caches downloads by its pip inputs
kind: tests
layer: n/a
summary: Derives every setup-python step from the shared workflow YAML reader, fails missing pip caching or cache keys that differ from existing local install inputs, and requires an unconditional install after each setup. Empty workflow and setup sets fail. Fixtures exercise additional workflows, requirements, constraints, working directories, missing inputs and cache-hit conditions.
"""

from pathlib import Path

import pytest
from test_install_sources_gate import _commands, _install_kind
from test_toolchain_gate import _jobs, _workflows

_ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration


def _input_path(root, directory, value):
    """Return an install input as a root-relative path, asserting it exists."""
    path = directory / value
    relative = path.resolve().relative_to(root.resolve())
    assert path.is_file(), "install input does not exist: %s" % relative
    return relative.as_posix()


def _requirements(root, directory, value, seen, install_directory):
    """Add a requirements or constraints file and every input it reads to seen."""
    relative = _input_path(root, directory, value)
    if relative in seen:
        return
    seen.add(relative)
    path = root / relative
    for words in _commands(path.read_text("utf-8")):
        _file_options(root, path.parent, words, seen, install_directory)
        seen.update(_project_inputs(root, install_directory, words))


def _file_options(root, directory, words, seen, install_directory=None):
    """Follow each -r and -c option in one pip command into seen."""
    if install_directory is None:
        install_directory = directory
    index = 0
    while index < len(words):
        word = words[index]
        if word in ("-r", "--requirement", "-c", "--constraint"):
            index += 1
            assert index < len(words), "missing file after %s" % word
            _requirements(root, directory, words[index], seen, install_directory)
        elif word.startswith(("--requirement=", "--constraint=")):
            _requirements(
                root, directory, word.split("=", 1)[1], seen, install_directory
            )
        elif word.startswith(("-r", "-c")) and len(word) > 2:
            _requirements(root, directory, word[2:], seen, install_directory)
        index += 1


def _project_inputs(root, directory, words):
    """Return the pyproject.toml of each local project a pip command installs."""
    inputs = set()
    for word in words:
        local = word.split("[", 1)[0]
        if local.startswith("--editable="):
            local = local.split("=", 1)[1]
        elif local.startswith("-e") and not local.startswith("--"):
            local = local[2:]
        if (local == "." or local.startswith(("./", "../"))) and (
            directory / local
        ).is_dir():
            inputs.add(_input_path(root, directory, local + "/pyproject.toml"))
    return inputs


def _install_inputs(root, directory, words):
    """Return every local file one pip install command reads."""
    inputs = _project_inputs(root, directory, words)
    _file_options(root, directory, words, inputs)
    return inputs


def cache_faults(root, workflows):
    """Return the setup count and faults for cache keys and unconditional installs."""
    judged, faults = 0, []
    for name, job_id, job in _jobs(workflows):
        steps = job.get("steps") or []
        defaults = workflows[name].get("defaults", {}).get("run", {})
        defaults = {**defaults, **job.get("defaults", {}).get("run", {})}
        for index, setup in enumerate(steps):
            if str(setup.get("uses", "")).split("@", 1)[0] != "actions/setup-python":
                continue
            judged += 1
            label = "%s job %s step %d" % (name, job_id, index)
            settings = setup.get("with") or {}
            if settings.get("cache") != "pip":
                faults.append("%s: cache must be pip" % label)
            given = settings.get("cache-dependency-path")
            paths = given.splitlines() if isinstance(given, str) else []
            paths = {path.strip() for path in paths if path.strip()}
            expected, installs = set(), 0
            for step in steps[index + 1 :]:
                if str(step.get("uses", "")).split("@", 1)[0] == "actions/setup-python":
                    break
                for words in _commands(step.get("run", "")):
                    if _install_kind(words) != "pip":
                        continue
                    installs += 1
                    if (
                        "if" in step
                        or step.get("continue-on-error")
                        or "cache-hit" in step.get("run", "")
                    ):
                        faults.append(
                            "%s: pip install must run unconditionally" % label
                        )
                    directory = root / step.get(
                        "working-directory", defaults.get("working-directory", ".")
                    )
                    expected.update(_install_inputs(root, directory, words))
            if not installs:
                faults.append("%s: no pip install after setup-python" % label)
            if not expected:
                faults.append(
                    "%s: no local dependency file read by pip install" % label
                )
            faults.extend(
                "%s: cache input does not exist: %s" % (label, path)
                for path in sorted(paths)
                if not (root / path).is_file()
            )
            if paths != expected:
                faults.append(
                    "%s: cache-dependency-path %s differs from install inputs %s"
                    % (label, sorted(paths), sorted(expected))
                )
    if not judged:
        faults.append("no setup-python steps found: nothing was judged")
    return judged, faults


def test_every_setup_python_caches_pip_downloads_by_install_inputs():
    judged, faults = cache_faults(_ROOT, _workflows())
    assert judged, "no setup-python steps found: nothing was judged"
    assert faults == [], "\n".join(faults)


def _workflow(tmp_path, *, install="pip install -e .", paths="pyproject.toml"):
    """Write a one-job workflow fixture and its pyproject.toml under tmp_path."""
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "fixture"\n')
    setup = {
        "uses": "actions/setup-python@v6",
        "with": {"cache": "pip", "cache-dependency-path": paths},
    }
    run = {"run": install}
    return {"extra.yaml": {"jobs": {"build": {"steps": [setup, run]}}}}, setup, run


@pytest.mark.parametrize(
    "fault",
    [
        "missing-cache",
        "wrong-cache",
        "missing-path",
        "missing-file",
        "unread-file",
        "missing-install",
        "conditional-install",
        "shell-conditional-install",
        "soft-install",
        "missing-setup",
    ],
)
def test_cache_faults_fail_closed(tmp_path, fault):
    workflows, setup, run = _workflow(tmp_path)
    assert cache_faults(tmp_path, workflows) == (1, [])
    if fault == "missing-cache":
        del setup["with"]["cache"]
    elif fault == "wrong-cache":
        setup["with"]["cache"] = "poetry"
    elif fault == "missing-path":
        del setup["with"]["cache-dependency-path"]
    elif fault == "missing-file":
        setup["with"]["cache-dependency-path"] = "missing.lock"
    elif fault == "unread-file":
        (tmp_path / "unread.lock").write_text("")
        setup["with"]["cache-dependency-path"] += "\nunread.lock"
    elif fault == "missing-install":
        run["run"] = "echo no-install"
    elif fault == "conditional-install":
        run["if"] = "steps.python.outputs.cache-hit != true"
    elif fault == "shell-conditional-install":
        run["run"] = (
            "[ '${{ steps.python.outputs.cache-hit }}' != true ] && pip install -e ."
        )
    elif fault == "soft-install":
        run["continue-on-error"] = True
    elif fault == "missing-setup":
        del setup["uses"]
    assert cache_faults(tmp_path, workflows)[1], fault


@pytest.mark.parametrize("installer", ["pip", "pip3", "python -m pip"])
def test_requirements_constraints_and_working_directories_are_keyed(
    tmp_path, installer
):
    package = tmp_path / "package"
    package.mkdir()
    workflows, _, run = _workflow(
        tmp_path,
        install=installer
        + " install -e ./package --requirement=reqs.txt -cconstraints.lock",
        paths="package/pyproject.toml\nreqs.txt\nconstraints.lock\nnested.txt",
    )
    (package / "pyproject.toml").write_text('[project]\nname = "fixture"\n')
    (tmp_path / "reqs.txt").write_text("-r nested.txt\n")
    (tmp_path / "nested.txt").write_text("example==1\n")
    (tmp_path / "constraints.lock").write_text("example==1\n")
    assert cache_faults(tmp_path, workflows) == (1, [])
    run["working-directory"] = "package"
    run["run"] = (
        installer + " install -e . -r../reqs.txt --constraint=../constraints.lock"
    )
    assert cache_faults(tmp_path, workflows) == (1, [])
    setup = workflows["extra.yaml"]["jobs"]["build"]["steps"][0]
    setup["with"]["cache-dependency-path"] = "package/pyproject.toml"
    assert cache_faults(tmp_path, workflows)[1], "unkeyed requirements passed"


def test_reader_discovers_additional_workflows_and_all_setup_steps(tmp_path):
    _workflow(tmp_path)
    folder = tmp_path / ".github" / "workflows"
    folder.mkdir(parents=True)
    for name in ("first.yml", "additional.yaml"):
        (folder / name).write_text(
            "jobs:\n  build:\n    steps:\n"
            "      - uses: actions/setup-python@v6\n"
            "        with:\n          cache: pip\n"
            "          cache-dependency-path: pyproject.toml\n"
            "      - run: pip install -e .\n"
            "      - uses: actions/setup-python@v6\n"
            "        with:\n          cache: pip\n"
            "          cache-dependency-path: pyproject.toml\n"
            "      - run: pip install -e .\n"
        )
    assert cache_faults(tmp_path, _workflows(tmp_path)) == (4, [])
    assert cache_faults(tmp_path, {})[1], "zero setup steps passed"


def test_missing_install_input_is_a_failure(tmp_path):
    workflows, _, _ = _workflow(tmp_path, install="pip install -r absent.txt")
    with pytest.raises(AssertionError, match="install input does not exist"):
        cache_faults(tmp_path, workflows)


@pytest.mark.parametrize("editable", ["--editable=.[dev]", "-e.[dev]"])
def test_attached_editable_options_read_the_project(tmp_path, editable):
    workflows, _, _ = _workflow(tmp_path, install="pip install " + editable)
    assert cache_faults(tmp_path, workflows) == (1, [])


def test_a_project_named_in_requirements_is_also_keyed(tmp_path):
    workflows, setup, _ = _workflow(
        tmp_path,
        install="pip install -r requirements.txt",
        paths="requirements.txt\npyproject.toml",
    )
    (tmp_path / "requirements.txt").write_text("-e .\n")
    assert cache_faults(tmp_path, workflows) == (1, [])
    setup["with"]["cache-dependency-path"] = "requirements.txt"
    assert cache_faults(tmp_path, workflows)[1], "unkeyed editable project passed"
