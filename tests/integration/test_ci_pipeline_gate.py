"""
title: Integration — every CI adapter runs exactly config/project.json ci_pipeline.steps, in order
kind: tests
layer: n/a
summary: config/project.json `ci_pipeline.steps` is the one statement of what CI runs, and each adapter file present (`ci_pipeline.adapters`: .github/workflows/ci.yml, .gitlab-ci.yml) is held to it through tests/ci_adapters.py parity_faults. The GitHub workflow has exactly its shipped top-level keys, triggers, job set, per-job and per-step keys, setup values and configured env maps: foreign keys and every missing mapping key, added jobs or steps, job or step conditions, changed triggers, boolean checkout depth, duplicate or merged keys and unreadable YAML are rejected with file/key diagnostics; equivalent YAML passes. The adapters in this tree have no fault; an empty step list, a tree with no adapter, a missing marker line or one that is not the whole line, a dropped, added, reordered or changed step, a changed env value, and a GitLab image or GIT_DEPTH other than the configured one each turn the judge red on a copy, and so does each GitLab key the shipped file lacks, however it is quoted or written (`when: manual`, `"when"`, `? when`, `'rules'`, `needs`, `allow_failure`, a `<<` merge, `MAKEFLAGS: "-n"` at either level, `default:`, `workflow`, `include`, a global `image`, `services`, `cache` or `after_script`, an unquoted `GIT_DEPTH: 1` or `false`, a long-form image naming another image or adding a key), with one fault naming its key path, and a hidden key the `test` job reads through a merge, an anchor, `extends` or `!reference` is a fault too, a key it has that the file lacks, a key set twice (named by both lines), a `<<` merge key set twice even when each merge brings only allowed keys, a file YAML cannot read, a control character in it or in the answers file (named by the file, never raised), a step shell words cannot split (`FOO=\"a b\"`, named by its step), a script item that is not a line, a NAME=value word alone on its line, in a multi-line step or a step of its own (named by its step), and a missing pyyaml; an env prefix never reaches across a line break. A file that differs only in what YAML does not read (comments, key order, quoting, a flow, nested or one-string script) has no fault, and so does one that says where keel's job runs or what else the project runs (`tags`, `stage`, `stages`, `interruptible`, `timeout`, `retry`, another job, a hidden job only another job merges, extends or references, a long-form image, an unquoted `GIT_DEPTH: 0`); the rule reads the same in tests/ci_adapters.py, features.md and deterministic-checks.md. In a project, the `ci_pipeline` answer in .copier-answers.yml picks what is judged: a chosen adapter that is missing, or one that lost its marker, is a fault, and so is an answers file with no valid answer (shown by its line as written), one that answers twice however the second key is written (`"ci_pipeline"`, `ci_pipeline :`, `? ci_pipeline`; named by both lines), and one YAML cannot read; a quoted answer with a trailing comment reads as copier reads it; an unchosen file the project wrote, with no marker, is not judged, and an unchosen one carrying the marker still is. The GitLab cases copy a generated project's judged adapter or render the template's .gitlab-ci.yml.jinja with the configured toolchain answer, so GitLab-only projects run the judge and the shipped twin is judged too, and yaml reads the rendered file to the same script lines the stdlib scanner does and to exactly ci_adapters.gitlab_document.
"""

import json
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from scripts import config_loader
from scripts.child_env import build_child_env

import ci_adapters
import optional_deps

_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.integration


def test_every_adapter_present_runs_the_configured_steps_in_order():
    faults = ci_adapters.parity_faults(_ROOT)
    assert faults == [], "\n".join(faults)


@pytest.mark.parametrize("name", ["github", "gitlab"])
def test_bom_adapter_preserves_marker_and_steps(tmp_path, name):
    root = _copy(tmp_path, gitlab=True, github=name == "github")
    path = ci_adapters.present(root)[name]
    steps = ci_adapters.adapter_steps(path, name)
    path.write_text(path.read_text("utf-8"), encoding="utf-8-sig")
    assert ci_adapters.adapter_steps(path, name) == steps
    assert ci_adapters.parity_faults(root) == []
    names = sorted(ci_adapters.present(root))
    choice = "both" if len(names) == 2 else name
    (root / ci_adapters.ANSWERS).write_text(
        "ci_pipeline: %s\n" % choice, encoding="utf-8-sig"
    )
    assert ci_adapters.chosen(root) == (names, None)
    assert ci_adapters.parity_faults(root) == []


def test_bom_answers_diagnostic_has_the_written_line_without_bom(tmp_path):
    root = _copy(tmp_path)
    (root / ci_adapters.ANSWERS).write_text(
        "ci_pipeline: invalid\n", encoding="utf-8-sig"
    )
    chosen, fault = ci_adapters.chosen(root)
    assert chosen == []
    assert "`ci_pipeline: invalid`" in fault
    assert "\ufeff" not in fault


def _copy(tmp_path, *, gitlab=False, github=False):
    """A copy of this project's judged adapters and config, rendering the
    template's GitLab twin when *gitlab* requests it. Only GitHub-specific
    cases request *github* and skip when the project ships no such adapter."""
    found = ci_adapters.judged(_ROOT)
    if github and "github" not in found:
        pytest.skip("this project ships no judged GitHub adapter (ci_pipeline choice)")
    if gitlab:
        shipped = ci_adapters.shipped(_ROOT)
        if "gitlab" not in shipped:
            pytest.skip("this project ships no GitLab adapter (ci_pipeline choice)")
        found = {**found, "gitlab": shipped["gitlab"]}
    root = tmp_path / "root"
    (root / "config").mkdir(parents=True)
    shutil.copyfile(str(_ROOT / ci_adapters.CONFIG), str(root / ci_adapters.CONFIG))
    adapters = ci_adapters.pipeline(root)["adapters"]
    for name, source in found.items():
        target = root / adapters[name]
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix == ".jinja":
            jinja2 = optional_deps.importorskip("jinja2", extra="template")
            python = config_loader.resolve(
                config_loader.read(str(root)),
                config_loader.rows(("toolchain", "python")),
                str(ci_adapters.CONFIG),
                environ={},
            )[("toolchain", "python")]
            text = jinja2.Template(
                source.read_text(), keep_trailing_newline=True
            ).render(toolchain_python=python)
            target.write_text(text)
        else:
            shutil.copyfile(str(source), str(target))
    return root


def _edit(path, old, new):
    text = path.read_text()
    assert text.count(old) == 1, (path, old)
    path.write_text(text.replace(old, new))


def _set_config(root, change):
    path = root / ci_adapters.CONFIG
    config = json.loads(path.read_text())
    change(config["ci_pipeline"])
    path.write_text(json.dumps(config))


@pytest.mark.parametrize(
    "foreign_github", [False, True], ids=["absent", "project-owned"]
)
def test_a_gitlab_only_project_still_judges_a_planted_gitlab_fault(
    tmp_path, monkeypatch, foreign_github
):
    """A generated GitLab-only root has answers and a rendered adapter,
    without GitHub or template files; its GitLab cases must run."""
    source = _copy(tmp_path / "source", gitlab=True)
    (source / ".github/workflows/ci.yml").unlink(missing_ok=True)
    _answer(source, "ci_pipeline: gitlab")
    if foreign_github:
        path = source / ".github/workflows/ci.yml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("name: the project's own workflow\n")
    assert ci_adapters.chosen(source) == (["gitlab"], None)
    assert set(ci_adapters.shipped(source)) == {"gitlab"}
    monkeypatch.setattr(sys.modules[__name__], "_ROOT", source)
    try:
        root = _copy(tmp_path / "case", gitlab=True)
    except pytest.skip.Exception as exc:
        pytest.fail("a GitLab-only fixture must run: %s" % exc)
    assert set(ci_adapters.present(root)) == {"gitlab"}
    assert ci_adapters.parity_faults(root) == []
    _edit(root / ".gitlab-ci.yml", "test:\n", "test:\n  when: manual\n")
    faults = ci_adapters.parity_faults(root)
    assert len(faults) == 1 and "`test.when`" in faults[0], faults
    with pytest.raises(pytest.skip.Exception, match="no judged GitHub adapter"):
        _copy(tmp_path / "github-case", github=True)


def test_gitlab_cases_run_in_a_gitlab_only_project(tmp_path, request):
    """Run every case against a rendered project; only GitHub cases may skip."""
    root = _copy(tmp_path / "project", gitlab=True)
    shutil.rmtree(root / ".github", ignore_errors=True)  # noqa: DROP003 -- the copied project may already have no GitHub directory
    _answer(root, "ci_pipeline: gitlab")
    module = Path(__file__).resolve()
    relative = Path("tests/integration") / module.name
    # The copied module derives _ROOT from its location. Docs are inputs to
    # its wording check; no template or GitHub file belongs in this project.
    for source, target in (
        (module, relative),
        (_ROOT / "docs/reference/features.md", Path("docs/reference/features.md")),
        (
            _ROOT / "docs/guides/deterministic-checks.md",
            Path("docs/guides/deterministic-checks.md"),
        ),
    ):
        destination = root / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    assert not (root / ".github").exists()
    assert not (root / ".gitlab-ci.yml.jinja").exists()
    assert ci_adapters.chosen(root) == (["gitlab"], None)
    report = tmp_path / "child.xml"
    timeout_key = ("tests", "child_timeout_seconds")
    timeout = config_loader.resolve(
        config_loader.read(str(_ROOT)),
        config_loader.rows(timeout_key),
        str(ci_adapters.CONFIG),
    )[timeout_key]
    ran = subprocess.run(
        [
            "nice",
            "-n",
            "10",
            sys.executable,
            "-B",
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "-c",
            str(_ROOT / "pyproject.toml"),
            "--rootdir",
            str(root),
            "--confcutdir",
            str(root),
            "--basetemp",
            str(tmp_path / "child-scratch"),
            "--junitxml",
            str(report),
            "--deselect",
            "%s::%s" % (relative, request.node.originalname),
            str(relative),
        ],
        cwd=root,
        env=build_child_env(
            extra={
                "PYTHONPATH": ":".join(
                    str(path) for path in (_ROOT / "src", _ROOT, _ROOT / "tests")
                ),
                "PYTHONDONTWRITEBYTECODE": "1",
                "TMPDIR": str(tmp_path),
                "KEEL_TEST_SCRATCH": str(tmp_path / "child-scratch"),
            }
        ),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    assert ran.returncode == 0, ran.stdout + ran.stderr
    cases = ET.parse(report).findall(".//testcase")
    gitlab = [case for case in cases if "gitlab" in case.attrib["name"]]
    assert gitlab, "the child must collect GitLab cases"
    skipped = [
        case.attrib["name"] for case in cases if case.find("skipped") is not None
    ]
    assert not [name for name in skipped if "gitlab" in name], skipped
    # These cases select GitHub in their answers, so they need its adapter
    # even though their names describe the choice rather than the vendor.
    github_choices = {
        "test_an_unchosen_file_the_project_wrote_is_not_judged",
        "test_an_unchosen_file_carrying_the_marker_is_still_judged",
        "test_a_chosen_adapter_that_lost_its_marker_is_still_judged",
    }
    assert not [
        name for name in skipped if "github" not in name and name not in github_choices
    ], skipped


@pytest.mark.parametrize("images", [["debian-12"], ["debian-12", "ubuntu-24.04"]])
def test_github_runner_follows_the_configured_image_membership(tmp_path, images):
    """Changing the allowlist faults the shipped runner only when it is
    absent; a configured runner need not be the list's first entry."""
    root = _copy(tmp_path, github=True)
    path = root / ci_adapters.CONFIG
    config = config_loader.read(str(root))
    config["toolchain"]["runner_images"] = images
    path.write_text(json.dumps(config))
    faults = ci_adapters.parity_faults(root)
    if "ubuntu-24.04" in images:
        assert faults == [], faults
    else:
        assert len(faults) == 1 and "`jobs.test.runs-on`" in faults[0], faults
        assert "debian-12" in faults[0], faults


def test_the_rendered_gitlab_twin_has_no_fault_and_yaml_reads_the_same_lines(tmp_path):
    root = _copy(tmp_path, gitlab=True)
    assert ci_adapters.parity_faults(root) == []
    yaml = optional_deps.importorskip("yaml", extra="template")
    doc = yaml.safe_load((root / ".gitlab-ci.yml").read_text())
    steps = ci_adapters.pipeline(root)["steps"]
    assert doc["test"]["script"] == [ci_adapters.gitlab_line(s) for s in steps]
    assert doc["variables"]["GIT_DEPTH"] == "0"
    # The judge holds a project's file to gitlab_document, so the twin keel
    # ships must read as exactly that document, no key more or less.
    assert doc == ci_adapters.gitlab_document(root)


def test_an_empty_step_list_is_a_fault_not_a_pass(tmp_path):
    root = _copy(tmp_path)
    _set_config(root, lambda block: block.update(steps=[]))
    assert ci_adapters.parity_faults(root) == [
        "config/project.json ci_pipeline.steps is empty: no adapter is judged"
    ]


def test_a_tree_with_no_adapter_is_a_fault_not_a_pass(tmp_path):
    root = _copy(tmp_path)
    for path in ci_adapters.present(root).values():
        path.unlink()
    faults = ci_adapters.parity_faults(root)
    assert len(faults) == 1 and "the pipeline runs nowhere" in faults[0], faults


_GITHUB_FAULTS = [
    ("marker", "# keel-adapter: github\n", ""),
    (
        "marker not a whole line",
        "# keel-adapter: github\n",
        "  # keel-adapter: github (copied)\n",
    ),
    ("dropped step", "      - run: make trace\n", ""),
    (
        "added step",
        "      - run: make trace\n",
        "      - run: make trace\n      - run: make docs\n",
    ),
    (
        "reordered",
        "      - run: make lint\n      - run: make typecheck\n",
        "      - run: make typecheck\n      - run: make lint\n",
    ),
    ("changed step", "      - run: make eval\n", "      - run: make eval || true\n"),
    ("changed env", '"template,dev,transport,secrets"', '"dev,transport,secrets"'),
]


@pytest.mark.parametrize(
    "old, new", [c[1:] for c in _GITHUB_FAULTS], ids=[c[0] for c in _GITHUB_FAULTS]
)
def test_a_github_adapter_that_drifts_is_a_fault(tmp_path, old, new):
    root = _copy(tmp_path, github=True)
    _edit(root / ".github/workflows/ci.yml", old, new)
    assert ci_adapters.parity_faults(root) != []


_GITHUB_SHAPE_FAULTS = [
    ("top-level key", "name: ci\n", "name: ci\npermissions: {}\n", "permissions"),
    ("changed on", "on: [push, pull_request]", "on: [workflow_dispatch]", "on"),
    ("job if", "  test:\n", "  test:\n    if: false\n", "jobs.test.if"),
    ("added job", "jobs:\n", "jobs:\n  extra: {}\n", "jobs.extra"),
    (
        "job key",
        "  test:\n",
        "  test:\n    continue-on-error: true\n",
        "jobs.test.continue-on-error",
    ),
    ("global env", "name: ci\n", "name: ci\nenv: {MAKEFLAGS: -n}\n", "env"),
    ("job env", "  test:\n", "  test:\n    env: {MAKEFLAGS: -n}\n", "jobs.test.env"),
    (
        "step if",
        "      - run: make trace\n",
        "      - run: make trace\n        if: false\n",
        "jobs.test.steps.13.if",
    ),
    (
        "extra setup step",
        "      - uses: actions/setup-python@v6\n",
        "      - run: echo bypass\n      - uses: actions/setup-python@v6\n",
        "jobs.test.steps.2",
    ),
    (
        "extra step",
        "      - run: make test-sh\n",
        "      - run: make test-sh\n      - uses: example/action@v1\n",
        "jobs.test.steps.18",
    ),
    (
        "step env key",
        '          KEEL_REQUIRED_EXTRAS: "template,dev,transport,secrets"\n',
        '          KEEL_REQUIRED_EXTRAS: "template,dev,transport,secrets"\n'
        '          MAKEFLAGS: "-n"\n',
        "jobs.test.steps.12.env.MAKEFLAGS",
    ),
    (
        "boolean fetch depth",
        "fetch-depth: 0",
        "fetch-depth: false",
        "jobs.test.steps.0.with.fetch-depth",
    ),
]


@pytest.mark.parametrize(
    "old, new, key",
    [case[1:] for case in _GITHUB_SHAPE_FAULTS],
    ids=[case[0] for case in _GITHUB_SHAPE_FAULTS],
)
def test_a_github_shape_mutation_names_the_file_and_key(tmp_path, old, new, key):
    root = _copy(tmp_path, github=True)
    _edit(root / ".github/workflows/ci.yml", old, new)
    faults = ci_adapters.parity_faults(root)
    assert any("ci.yml" in fault and "`%s" % key in fault for fault in faults), faults


def _github_mappings(value, path=()):
    if isinstance(value, dict):
        yield path, value
        for key, child in value.items():
            yield from _github_mappings(child, path + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _github_mappings(child, path + (index,))


@pytest.mark.parametrize("change", ["added", "removed"])
def test_every_github_mapping_has_a_closed_key_set(tmp_path, change):
    """Every mapping rejects a foreign key and losing any shipped key."""
    root = _copy(tmp_path, github=True)
    path = root / ".github/workflows/ci.yml"
    yaml = optional_deps.importorskip("yaml", extra="dev")
    # PyYAML's default YAML 1.1 reader treats `on` as True, so quote this
    # key to keep the independent mutation writer faithful to GitHub's YAML.
    text = path.read_text().replace("on:", "'on':", 1)
    document = yaml.safe_load(text)
    for parents, mapping in _github_mappings(document):
        keys = ["foreign-key"] if change == "added" else list(mapping)
        for key in keys:
            mutated = yaml.safe_load(text)
            target = mutated
            for parent in parents:
                target = target[parent]
            if change == "added":
                target[key] = "unexpected"
            else:
                del target[key]
            path.write_text("# keel-adapter: github\n" + yaml.safe_dump(mutated))
            faults = ci_adapters.parity_faults(root)
            key_path = ".".join(map(str, parents + (key,)))
            assert any(
                "ci.yml" in fault and "`%s`" % key_path in fault for fault in faults
            ), (change, key_path, faults)


@pytest.mark.parametrize(
    "old, new, key",
    [
        ("name: ci\n", "name: ci\nname: another\n", "name"),
        ("  test:\n", "  test:\n    'if': false\n", "jobs.test.if"),
        ("  test:\n", "  test:\n    <<: {if: false}\n", "jobs.test.if"),
        ("on: [push, pull_request]", "on: [", "ci.yml"),
    ],
    ids=["duplicate", "quoted", "merged", "invalid yaml"],
)
def test_github_yaml_cannot_hide_a_shape_fault(tmp_path, old, new, key):
    root = _copy(tmp_path, github=True)
    _edit(root / ".github/workflows/ci.yml", old, new)
    faults = ci_adapters.parity_faults(root)
    assert any("ci.yml" in fault and key in fault for fault in faults), faults


def test_equivalent_github_yaml_has_no_fault(tmp_path):
    root = _copy(tmp_path, github=True)
    path = root / ".github/workflows/ci.yml"
    yaml = optional_deps.importorskip("yaml", extra="dev")
    document = yaml.safe_load(path.read_text().replace("on:", "'on':", 1))
    path.write_text("# keel-adapter: github\n" + yaml.safe_dump(document))
    assert ci_adapters.parity_faults(root) == []


def test_without_pyyaml_a_github_file_is_a_fault(tmp_path, monkeypatch):
    root = _copy(tmp_path, github=True)
    for name, path in ci_adapters.present(root).items():
        if name != "github":
            path.unlink()
    monkeypatch.setitem(sys.modules, "yaml", None)
    faults = ci_adapters.parity_faults(root)
    assert len(faults) == 1 and "ci.yml" in faults[0] and "pyyaml" in faults[0], faults


_GITLAB_FAULTS = [
    ("marker", "# keel-adapter: gitlab\n", ""),
    ("dropped step", "    - make trace\n", ""),
    (
        "reordered",
        "    - make lint\n    - make typecheck\n",
        "    - make typecheck\n    - make lint\n",
    ),
    (
        "changed env",
        "KEEL_REQUIRED_EXTRAS=template,dev,transport,secrets",
        "KEEL_REQUIRED_EXTRAS=dev",
    ),
    (
        "lost env",
        "KEEL_REQUIRED_EXTRAS=template,dev,transport,secrets make test",
        "make test",
    ),
    ("image", "image: ci-image.example.invalid/python", "image: python:"),
    ("git depth", 'GIT_DEPTH: "0"', 'GIT_DEPTH: "1"'),
]


@pytest.mark.parametrize(
    "old, new", [c[1:] for c in _GITLAB_FAULTS], ids=[c[0] for c in _GITLAB_FAULTS]
)
def test_a_gitlab_adapter_that_drifts_is_a_fault(tmp_path, old, new):
    root = _copy(tmp_path, gitlab=True)
    _edit(root / ".gitlab-ci.yml", old, new)
    assert ci_adapters.parity_faults(root) != []


# Shapes that pass a step check while the job runs no step, or a step other
# than keel's, each measured passing a judge that rejected key names: (id, the
# line it is planted after, the planted text, the key paths the faults name,
# one fault each). The judge names them because keel's file has none of them.
_GITLAB_FOREIGN = [
    ("when", "test:\n", "  when: manual\n", ["test.when"]),
    ("quoted when", "test:\n", '  "when": manual\n', ["test.when"]),
    ("explicit when", "test:\n", "  ? when\n  : manual\n", ["test.when"]),
    ("quoted rules", "test:\n", "  'rules': [when: never]\n", ["test.rules"]),
    ("only", "test:\n", "  only:\n    - tags\n", ["test.only"]),
    ("except", "test:\n", "  except:\n    - branches\n", ["test.except"]),
    ("needs", "test:\n", "  needs: [build]\n", ["test.needs"]),
    ("allow_failure", "test:\n", "  allow_failure: true\n", ["test.allow_failure"]),
    (
        "job before_script",
        "test:\n",
        "  before_script:\n    - exit 0\n",
        ["test.before_script"],
    ),
    ("extends", "test:\n", "  extends: .quiet\n", ["test.extends"]),
    ("merge key", "test:\n", "  <<: {when: manual}\n", ["test.when"]),
    (
        "job MAKEFLAGS",
        "test:\n",
        '  variables:\n    MAKEFLAGS: "-n"\n',
        ["test.variables"],
    ),
    ("MAKEFLAGS", 'GIT_DEPTH: "0"\n', '  MAKEFLAGS: "-n"\n', ["variables.MAKEFLAGS"]),
    (
        "default",
        'GIT_DEPTH: "0"\n',
        "default:\n  before_script:\n    - exit 0\n",
        ["default"],
    ),
    (
        "before_script",
        'GIT_DEPTH: "0"\n',
        "before_script:\n  - exit 0\n",
        ["before_script"],
    ),
    (
        "workflow",
        'GIT_DEPTH: "0"\n',
        "workflow:\n  rules:\n    - when: never\n",
        ["workflow"],
    ),
    (
        "quoted workflow",
        'GIT_DEPTH: "0"\n',
        '"workflow":\n  rules:\n    - when: never\n',
        ["workflow"],
    ),
    ("include", 'GIT_DEPTH: "0"\n', "include:\n  - local: more-ci.yml\n", ["include"]),
    ("global image", 'GIT_DEPTH: "0"\n', "image: busybox\n", ["image"]),
    ("services", 'GIT_DEPTH: "0"\n', "services: [docker:dind]\n", ["services"]),
    ("cache", 'GIT_DEPTH: "0"\n', "cache:\n  paths: [.venv]\n", ["cache"]),
    ("after_script", 'GIT_DEPTH: "0"\n', "after_script: [exit 0]\n", ["after_script"]),
]


@pytest.mark.parametrize(
    "after, planted, paths",
    [c[1:] for c in _GITLAB_FOREIGN],
    ids=[c[0] for c in _GITLAB_FOREIGN],
)
def test_a_gitlab_key_keel_does_not_ship_is_a_fault_naming_its_path(
    tmp_path, after, planted, paths
):
    """A key read as GitLab reads it, however it is quoted or written, that
    keel's file lacks is one fault naming its key path, and nothing else."""
    root = _copy(tmp_path, gitlab=True)
    _edit(root / ".gitlab-ci.yml", after, after + planted)
    faults = ci_adapters.parity_faults(root)
    assert len(faults) == len(paths), faults
    for path, fault in zip(paths, faults, strict=True):
        assert "`%s`" % path in fault, faults


_TOP = "# keel-adapter: gitlab\n"
_JOB = "test:\n"

# Shapes where the `test` job reads another top-level key, through a YAML
# anchor or merge, `extends` or `!reference`: (id, the text planted after the
# marker line, the text planted in the job, the key paths the faults name).
_GITLAB_REACH = [
    (
        "merged hidden job",
        ".quiet: &quiet\n  when: manual\n",
        "  <<: *quiet\n",
        [".quiet", "test.when"],
    ),
    (
        "merged hidden job of placement keys",
        ".runner: &runner\n  tags: [ours]\n",
        "  <<: *runner\n",
        [".runner"],
    ),
    (
        "extended hidden job",
        ".quiet:\n  when: manual\n",
        "  extends: .quiet\n",
        [".quiet", "test.extends"],
    ),
    (
        "referenced hidden job",
        ".setup:\n  script: [exit 0]\n",
        "  before_script: !reference [.setup, script]\n",
        [".setup", "test.before_script"],
    ),
    (
        "aliased variables",
        ".vars: &vars\n  MAKEFLAGS: -n\n",
        "  variables: *vars\n",
        [".vars", "test.variables"],
    ),
]


@pytest.mark.parametrize(
    "top, job, paths",
    [c[1:] for c in _GITLAB_REACH],
    ids=[c[0] for c in _GITLAB_REACH],
)
def test_a_key_the_test_job_reads_is_judged_wherever_it_sits(tmp_path, top, job, paths):
    """A hidden job the `test` job merges, extends or references changes what
    it runs, so it is judged as keel's own keys are, and fails: keel's file
    has none."""
    root = _copy(tmp_path, gitlab=True)
    _edit(root / ".gitlab-ci.yml", _TOP, _TOP + top)
    _edit(root / ".gitlab-ci.yml", _JOB, _JOB + job)
    faults = ci_adapters.parity_faults(root)
    assert len(faults) == len(paths), faults
    for path, fault in zip(paths, faults, strict=True):
        assert "`%s`" % path in fault, faults


_IMAGE = "  image: ci-image.example.invalid/python"
# Shapes GitLab reads as keel's job in another place or beside the project's
# own jobs, each running exactly keel's steps: (id, old text, new text).
_GITLAB_PLACED = [
    ("tags", _JOB, _JOB + "  tags: [ours]\n"),
    ("stage", _JOB, _JOB + "  stage: test\n"),
    ("stages", _TOP, _TOP + "stages: [build, test, deploy]\n"),
    (
        "interruptible, timeout and retry",
        _JOB,
        _JOB + "  interruptible: true\n  timeout: 2h\n  retry: 2\n",
    ),
    (
        "another job",
        _TOP,
        _TOP + "deploy:\n  stage: deploy\n  when: manual\n  script: [make dist]\n",
    ),
    (
        "hidden job merged by another job",
        _TOP,
        _TOP + ".base: &base\n  when: manual\n"
        "deploy:\n  <<: *base\n  script: [make dist]\n",
    ),
    (
        "hidden job extended by another job",
        _TOP,
        _TOP + ".base:\n  when: manual\ndeploy:\n  extends: .base\n"
        "  script: [make dist]\n",
    ),
    (
        "hidden job referenced by another job",
        _TOP,
        _TOP + ".setup:\n  script: [make dist]\n"
        "deploy:\n  script: !reference [.setup, script]\n",
    ),
    ("image long form", _IMAGE, "  image:\n    name: ci-image.example.invalid/python"),
    ("unquoted GIT_DEPTH", 'GIT_DEPTH: "0"', "GIT_DEPTH: 0"),
]


@pytest.mark.parametrize(
    "old, new", [c[1:] for c in _GITLAB_PLACED], ids=[c[0] for c in _GITLAB_PLACED]
)
def test_where_keel_s_job_runs_and_what_else_the_project_runs_is_not_judged(
    tmp_path, old, new
):
    """The judge guards whether keel's `test` job runs and exactly what it
    runs, never where it runs or what else the project runs."""
    root = _copy(tmp_path, gitlab=True)
    _edit(root / ".gitlab-ci.yml", old, new)
    assert ci_adapters.parity_faults(root) == []


@pytest.mark.parametrize(
    "old, new, path",
    [
        (
            _IMAGE,
            "  image:\n    name: busybox\n    x: ci-image.example.invalid/python",
            "test.image",
        ),
        (
            _IMAGE,
            "  image:\n    entrypoint: ['/bin/true']\n    name: ci-image.example.invalid/python",
            "test.image",
        ),
        ('GIT_DEPTH: "0"', "GIT_DEPTH: 1", "variables.GIT_DEPTH"),
        ('GIT_DEPTH: "0"', "GIT_DEPTH: false", "variables.GIT_DEPTH"),
    ],
    ids=["long form, other image", "long form, entrypoint", "depth 1", "depth false"],
)
def test_an_image_or_variable_gitlab_reads_otherwise_is_a_fault(
    tmp_path, old, new, path
):
    root = _copy(tmp_path, gitlab=True)
    _edit(root / ".gitlab-ci.yml", old, new)
    faults = ci_adapters.parity_faults(root)
    assert len(faults) == 1 and "`%s`" % path in faults[0], faults


def test_the_gitlab_rule_reads_the_same_in_the_module_and_both_docs():
    """The rule is stated once in each of three places, in the same words,
    and names every key of the module's closed vocabularies."""
    words = " ".join(ci_adapters.__doc__.split())
    start = words.index("The GitLab judge guards whether")
    rule = words[start : words.index('equals `"0"`.', start) + len('equals `"0"`.')]
    for doc in ("docs/reference/features.md", "docs/guides/deterministic-checks.md"):
        assert rule in " ".join((_ROOT / doc).read_text("utf-8").split()), doc
    for key in ci_adapters.GITLAB_GLOBAL_KEYS | ci_adapters.GITLAB_PLACEMENT_KEYS:
        assert "`%s`" % key in rule, key


def test_a_gitlab_key_keel_ships_that_is_missing_is_a_fault(tmp_path):
    root = _copy(tmp_path, gitlab=True)
    _edit(root / ".gitlab-ci.yml", "variables:\n", "x-variables:\n")
    faults = ci_adapters.parity_faults(root)
    assert len(faults) == 1 and "`variables` is missing" in faults[0], faults


def test_a_gitlab_key_set_twice_is_a_fault_naming_both_lines(tmp_path):
    """YAML keeps the last of two `script` keys, so a second one would run
    alone: the judge reads no file that sets a key twice."""
    root = _copy(tmp_path, gitlab=True)
    path = root / ".gitlab-ci.yml"
    path.write_text(path.read_text() + '  script: ["true"]\n')
    lines = path.read_text().splitlines()
    first = lines.index("  script:") + 1
    faults = ci_adapters.parity_faults(root)
    assert len(faults) == 1, faults
    for said in (
        "`script`",
        "line %d `  script:`" % first,
        'line %d `  script: ["true"]`' % len(lines),
    ):
        assert said in faults[0], faults


def test_a_gitlab_merge_key_set_twice_is_a_fault_naming_both_lines(tmp_path):
    """YAML readers differ on a mapping with two `<<` keys, merging both or
    keeping one, so the judge reads no such file, even when each merge brings
    only keys it would allow."""
    root = _copy(tmp_path, gitlab=True)
    _edit(
        root / ".gitlab-ci.yml",
        _JOB,
        _JOB + "  <<: {tags: [ours]}\n  <<: {timeout: 2h}\n",
    )
    lines = (root / ".gitlab-ci.yml").read_text().splitlines()
    first = lines.index("  <<: {tags: [ours]}") + 1
    faults = ci_adapters.parity_faults(root)
    assert len(faults) == 1, faults
    for said in (
        "`<<`",
        "line %d `  <<: {tags: [ours]}`" % first,
        "line %d `  <<: {timeout: 2h}`" % (first + 1),
    ):
        assert said in faults[0], faults


def test_a_gitlab_file_yaml_cannot_read_is_one_fault(tmp_path):
    root = _copy(tmp_path, gitlab=True)
    _edit(root / ".gitlab-ci.yml", "test:\n", "test:\n  <<: *nowhere\n")
    faults = ci_adapters.parity_faults(root)
    assert len(faults) == 1 and faults[0].startswith(".gitlab-ci.yml: "), faults


@pytest.mark.parametrize("answers", [False, True], ids=["gitlab file", "answers file"])
def test_a_control_character_is_a_fault_naming_the_file(tmp_path, answers):
    """YAML refuses a control character before it reads a key, so the judge
    names the file rather than raising."""
    root = _copy(tmp_path, gitlab=True)
    if answers:
        _answer(root, "ci_pipeline: gitlab # \x01")
        name = ci_adapters.ANSWERS.name
    else:
        _edit(root / ".gitlab-ci.yml", _TOP, _TOP + "# \x01\n")
        name = ".gitlab-ci.yml"
    faults = ci_adapters.parity_faults(root)
    assert len(faults) == 1 and faults[0].startswith(name + ": "), faults


def test_a_step_shell_cannot_split_is_a_fault_naming_the_step(tmp_path):
    """`FOO="a b"` is one shell word the env prefix reads only up to its
    space, so the judge cannot split the step and says so, not raising."""
    root = _copy(tmp_path, gitlab=True)
    _edit(
        root / ".gitlab-ci.yml", "    - %s\n" % _ENV_STEP, '    - FOO="a b" make test\n'
    )
    faults = ci_adapters.parity_faults(root)
    assert faults[0].startswith(".gitlab-ci.yml: `test.script` step 9 "), faults
    assert "FOO" in faults[0], faults


def test_without_pyyaml_a_gitlab_file_is_a_fault_not_a_pass(tmp_path, monkeypatch):
    root = _copy(tmp_path, gitlab=True)
    (root / ".github/workflows/ci.yml").unlink(missing_ok=True)
    monkeypatch.setitem(sys.modules, "yaml", None)
    faults = ci_adapters.parity_faults(root)
    assert len(faults) == 1 and "pyyaml" in faults[0], faults


def _flow(lines):
    return "[%s]" % ", ".join(json.dumps(line) for line in lines)


def test_a_gitlab_file_written_another_way_yaml_reads_the_same_has_no_fault(
    tmp_path,
):
    """The edits keel allows are the ones YAML does not read: comments, blank
    lines, key order, quoting and flow or block style, and a script list
    nested the way GitLab flattens it."""
    root = _copy(tmp_path, gitlab=True)
    doc = ci_adapters.gitlab_document(root)
    lines = doc["test"]["script"]
    (root / ".gitlab-ci.yml").write_text(
        "# keel-adapter: gitlab\n"
        "# Our runner's notes.\n"
        "test:\n"
        "  script: [%s, %s]\n"
        "\n"
        "  image: '%s'\n"
        "variables: {GIT_DEPTH: '0'}  # full history\n"
        % (
            _flow(lines[:2]),
            ", ".join(json.dumps(x) for x in lines[2:]),
            doc["test"]["image"],
        )
    )
    assert ci_adapters.parity_faults(root) == []


@pytest.mark.parametrize("script", ["make check", '"make check"', "[make check]"])
def test_a_one_step_gitlab_script_may_be_one_string(tmp_path, script):
    root = _copy(tmp_path, gitlab=True)
    (root / ".github/workflows/ci.yml").unlink(missing_ok=True)
    _set_config(root, lambda block: block.update(steps=[{"run": "make check"}]))
    path = root / ".gitlab-ci.yml"
    text = path.read_text()
    path.write_text(text[: text.index("  script:\n")] + "  script: %s\n" % script)
    assert ci_adapters.parity_faults(root) == []
    _set_config(
        root,
        lambda block: block.update(steps=[{"run": "make check"}, {"run": "make lint"}]),
    )
    faults = ci_adapters.parity_faults(root)
    assert len(faults) == 1 and ".gitlab-ci.yml runs" in faults[0], faults


def test_a_gitlab_script_item_that_is_not_a_line_is_a_fault(tmp_path):
    root = _copy(tmp_path, gitlab=True)
    _edit(root / ".gitlab-ci.yml", "    - make trace\n", "    - {make: trace}\n")
    faults = ci_adapters.parity_faults(root)
    assert len(faults) == 1 and "`test.script`" in faults[0], faults


def test_a_config_step_no_adapter_runs_is_a_fault(tmp_path):
    root = _copy(tmp_path, gitlab=True)
    _set_config(root, lambda block: block["steps"].append({"run": "make docs"}))
    faults = ci_adapters.parity_faults(root)
    if "github" in ci_adapters.present(root):
        assert len(faults) == 2, faults
    else:
        assert len(faults) == len(ci_adapters.judged(root)), faults


def test_a_gitlab_image_key_the_file_does_not_follow_is_a_fault(tmp_path):
    root = _copy(tmp_path, gitlab=True)
    _set_config(
        root, lambda block: block.update(gitlab_image="mirror.invalid/ci:{python}")
    )
    faults = ci_adapters.parity_faults(root)
    assert len(faults) == 1 and "image" in faults[0], faults


def _answer(root, line):
    (root / ci_adapters.ANSWERS).write_text(
        "_commit: abc\n%s\nproject_name: demo\n" % line
    )


def test_a_chosen_adapter_that_is_missing_is_a_fault(tmp_path):
    root = _copy(tmp_path)
    _answer(root, "ci_pipeline: both")
    adapters = ci_adapters.pipeline(root)["adapters"]
    missing = sorted(set(adapters) - set(ci_adapters.present(root)))
    if not missing:
        missing = ["gitlab"]
        (root / adapters["gitlab"]).unlink()
    faults = ci_adapters.parity_faults(root)
    assert faults == [
        "the chosen adapter %s (%s) is missing" % (name, adapters[name])
        for name in missing
    ], faults


def test_an_answers_file_with_no_valid_choice_is_a_fault(tmp_path):
    root = _copy(tmp_path)
    for line, said in (
        ("frontend_stack: none", "records no ci_pipeline"),
        ("ci_pipeline: jenkins", "jenkins"),
    ):
        _answer(root, line)
        faults = ci_adapters.parity_faults(root)
        assert len(faults) == 1 and said in faults[0], faults


def test_a_ci_pipeline_answered_twice_is_a_fault_naming_both_lines(tmp_path):
    """YAML reads the last of two `ci_pipeline:` lines and a line scan the
    first, so neither may decide: the judge fails closed and names both."""
    root = _copy(tmp_path, gitlab=True)
    _answer(root, "ci_pipeline: github\nci_pipeline: gitlab")
    faults = ci_adapters.parity_faults(root)
    assert len(faults) == 1, faults
    for said in ("line 2", "`ci_pipeline: github`", "line 3", "`ci_pipeline: gitlab`"):
        assert said in faults[0], faults


@pytest.mark.parametrize(
    "second",
    ['"ci_pipeline": github', "ci_pipeline : github", "? ci_pipeline\n: github"],
)
def test_a_second_ci_pipeline_written_another_way_is_a_fault_naming_both_lines(
    tmp_path, second
):
    """copier's YAML reads a quoted, spaced or explicit key as `ci_pipeline`
    and keeps the last, so the judge reads the answers the same way and fails
    the file that answers twice however the second is written."""
    root = _copy(tmp_path, gitlab=True)
    _answer(root, "ci_pipeline: gitlab\n" + second)
    faults = ci_adapters.parity_faults(root)
    assert len(faults) == 1, faults
    for said in (
        "line 2",
        "`ci_pipeline: gitlab`",
        "line 3",
        "`%s`" % second.split("\n")[0],
    ):
        assert said in faults[0], faults


def test_an_answer_reads_as_copier_reads_it(tmp_path):
    """A quoted value with a trailing comment is the value copier reads, so a
    project that chose gitlab that way has its GitLab file judged and no
    fault; an unknown value written that way is shown as the file has it."""
    root = _copy(tmp_path, gitlab=True)
    (root / ".github/workflows/ci.yml").unlink(missing_ok=True)
    _answer(root, "ci_pipeline: 'gitlab' # c")
    assert ci_adapters.chosen(root) == (["gitlab"], None)
    assert ci_adapters.parity_faults(root) == []
    _answer(root, "ci_pipeline: 'jenkins' # c")
    faults = ci_adapters.parity_faults(root)
    assert len(faults) == 1, faults
    assert "line 2 `ci_pipeline: 'jenkins' # c`" in faults[0], faults


def test_an_answers_file_yaml_cannot_read_is_a_fault(tmp_path):
    root = _copy(tmp_path)
    _answer(root, "ci_pipeline: [github")
    faults = ci_adapters.parity_faults(root)
    assert len(faults) == 1 and faults[0].startswith(".copier-answers.yml: "), faults


def test_an_unchosen_file_the_project_wrote_is_not_judged(tmp_path):
    """A .gitlab-ci.yml without keel's marker in a github project is the
    project's own, kept by update, so it is not held to keel's steps."""
    root = _copy(tmp_path, github=True)
    _answer(root, "ci_pipeline: github")
    (root / ".gitlab-ci.yml").write_text("lint:\n  script:\n    - make lint\n")
    assert ci_adapters.parity_faults(root) == []


def test_an_unchosen_file_carrying_the_marker_is_still_judged(tmp_path):
    root = _copy(tmp_path, gitlab=True, github=True)
    _answer(root, "ci_pipeline: github")
    _edit(root / ".gitlab-ci.yml", "    - make trace\n", "")
    faults = ci_adapters.parity_faults(root)
    assert len(faults) == 1 and ".gitlab-ci.yml runs" in faults[0], faults


def test_a_chosen_adapter_that_lost_its_marker_is_still_judged(tmp_path):
    root = _copy(tmp_path, github=True)
    _answer(root, "ci_pipeline: github")
    _edit(root / ".github/workflows/ci.yml", "# keel-adapter: github\n", "")
    faults = ci_adapters.parity_faults(root)
    assert faults == ["ci.yml: no line `# keel-adapter: github`"], faults


_ENV_STEP = "KEEL_REQUIRED_EXTRAS=template,dev,transport,secrets make test"
_ENV_ALONE = [
    (
        "block step",
        "    - |-\n"
        "      KEEL_REQUIRED_EXTRAS=template,dev,transport,secrets\n"
        "      make test\n",
        9,
    ),
    (
        "two steps",
        "    - KEEL_REQUIRED_EXTRAS=template,dev,transport,secrets\n    - make test\n",
        9,
    ),
]


@pytest.mark.parametrize(
    "planted, step", [c[1:] for c in _ENV_ALONE], ids=[c[0] for c in _ENV_ALONE]
)
def test_an_env_word_alone_on_its_line_is_a_fault_naming_the_step(
    tmp_path, planted, step
):
    """bash passes `NAME=value` to a command only on the command's own line:
    alone on a line it sets an unexported shell variable, so `make test`
    runs without KEEL_REQUIRED_EXTRAS and a missing surface skips."""
    root = _copy(tmp_path, gitlab=True)
    _edit(root / ".gitlab-ci.yml", "    - %s\n" % _ENV_STEP, planted)
    faults = ci_adapters.parity_faults(root)
    said = "step %d sets `KEEL_REQUIRED_EXTRAS=template,dev,transport,secrets`" % step
    assert said in faults[0], faults


@pytest.mark.parametrize("space, faults", [("\\t", 0), ("\\v", 1)], ids=["tab", "vt"])
def test_an_env_prefix_ends_only_at_a_space_or_a_tab(tmp_path, space, faults):
    """bash splits words at a space or a tab, so `NAME=value<TAB>make test`
    passes NAME to make; a vertical tab, which a regex `\\s` also matches, is
    part of the word, and the line runs no `make test` with that env."""
    root = _copy(tmp_path, gitlab=True)
    _edit(
        root / ".gitlab-ci.yml",
        "    - %s\n" % _ENV_STEP,
        '    - "%s"\n' % _ENV_STEP.replace(" make", space + "make"),
    )
    assert len(ci_adapters.parity_faults(root)) == faults
