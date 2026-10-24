"""
title: Integration — every CI adapter runs exactly config/project.json ci_pipeline.steps, in order
kind: tests
layer: n/a
summary: config/project.json `ci_pipeline.steps` is the one statement of what CI runs, and each adapter file present (`ci_pipeline.adapters`: .github/workflows/ci.yml, .gitlab-ci.yml) is held to it through tests/ci_adapters.py parity_faults. The adapters in this tree have no fault; an empty step list, a tree with no adapter, a missing marker line or one that is not the whole line, a dropped, added, reordered or changed step, a changed env value, and a GitLab image or GIT_DEPTH other than the configured one each turn the judge red on a copy, and so does each GitLab key that decides whether or how the `test` job runs (`when: manual`, `rules` with `when: never`, `only`, `except`, a job or `default:` `before_script` that exits 0, `extends`, top-level `before_script`, `workflow` and `include`), with one fault naming the key. In a project, the `ci_pipeline` answer in .copier-answers.yml picks what is judged: a chosen adapter that is missing, or one that lost its marker, is a fault, and so is an answers file with no valid answer; an unchosen file the project wrote, with no marker, is not judged, and an unchosen one carrying the marker still is. The GitLab cases render the template's .gitlab-ci.yml.jinja with the toolchain answer, so the shipped twin is judged too, and yaml reads the rendered file to the same script lines the stdlib scanner does.
"""

import json
import shutil
from pathlib import Path

import pytest

import ci_adapters
import optional_deps

_ROOT = Path(__file__).resolve().parents[2]
_JINJA = _ROOT / ".gitlab-ci.yml.jinja"

pytestmark = pytest.mark.integration


def test_every_adapter_present_runs_the_configured_steps_in_order():
    faults = ci_adapters.parity_faults(_ROOT)
    assert faults == [], "\n".join(faults)


def _copy(tmp_path, gitlab=False):
    """A tree with this config, ci.yml and, with *gitlab*, the GitLab twin
    rendered under the configured toolchain python."""
    root = tmp_path / "root"
    (root / "config").mkdir(parents=True)
    shutil.copyfile(str(_ROOT / ci_adapters.CONFIG), str(root / ci_adapters.CONFIG))
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True)
    shutil.copyfile(str(_ROOT / ".github/workflows/ci.yml"), str(workflows / "ci.yml"))
    if gitlab:
        if not _JINJA.is_file():
            pytest.skip("no .gitlab-ci.yml.jinja: this is a generated project")
        jinja2 = optional_deps.importorskip("jinja2", extra="template")
        python = json.loads((root / ci_adapters.CONFIG).read_text())["toolchain"][
            "python"
        ]
        text = jinja2.Template(_JINJA.read_text(), keep_trailing_newline=True).render(
            toolchain_python=python
        )
        (root / ".gitlab-ci.yml").write_text(text)
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


def test_the_rendered_gitlab_twin_has_no_fault_and_yaml_reads_the_same_lines(tmp_path):
    root = _copy(tmp_path, gitlab=True)
    assert ci_adapters.parity_faults(root) == []
    yaml = optional_deps.importorskip("yaml", extra="template")
    doc = yaml.safe_load((root / ".gitlab-ci.yml").read_text())
    steps = ci_adapters.pipeline(root)["steps"]
    assert doc["test"]["script"] == [ci_adapters.gitlab_line(s) for s in steps]
    assert doc["variables"]["GIT_DEPTH"] == "0"


def test_an_empty_step_list_is_a_fault_not_a_pass(tmp_path):
    root = _copy(tmp_path)
    _set_config(root, lambda block: block.update(steps=[]))
    assert ci_adapters.parity_faults(root) == [
        "config/project.json ci_pipeline.steps is empty: no adapter is judged"
    ]


def test_a_tree_with_no_adapter_is_a_fault_not_a_pass(tmp_path):
    root = _copy(tmp_path)
    (root / ".github/workflows/ci.yml").unlink()
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
    root = _copy(tmp_path)
    _edit(root / ".github/workflows/ci.yml", old, new)
    assert ci_adapters.parity_faults(root) != []


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


# Each key that decides whether, or how, the GitLab `test` job runs its
# script, as a shape the review measured passing the judge: (key named in the
# fault, the line it is planted after, the planted text). keel's twin sets
# none of them.
_GITLAB_RUN_KEYS = [
    ("test.when", "test:\n", "  when: manual\n"),
    ("test.rules", "test:\n", "  rules:\n    - when: never\n"),
    ("test.only", "test:\n", "  only:\n    - tags\n"),
    ("test.except", "test:\n", "  except:\n    - branches\n"),
    ("test.before_script", "test:\n", "  before_script:\n    - exit 0\n"),
    ("test.extends", "test:\n", "  extends: .quiet\n"),
    ("test.<<", "test:\n", "  <<: *quiet\n"),
    ("default", 'GIT_DEPTH: "0"\n', "default:\n  before_script:\n    - exit 0\n"),
    ("before_script", 'GIT_DEPTH: "0"\n', "before_script:\n  - exit 0\n"),
    ("workflow", 'GIT_DEPTH: "0"\n', "workflow:\n  rules:\n    - when: never\n"),
    ("include", 'GIT_DEPTH: "0"\n', "include:\n  - local: more-ci.yml\n"),
]


@pytest.mark.parametrize(
    "key, after, planted",
    _GITLAB_RUN_KEYS,
    ids=[c[0] for c in _GITLAB_RUN_KEYS],
)
def test_a_gitlab_key_that_decides_whether_the_job_runs_is_a_fault(
    tmp_path, key, after, planted
):
    """A `test` job whose steps match but that runs them only by hand, never,
    on tags only, or after a `before_script` that exits 0 passes no step: the
    judge names the key, and nothing else."""
    root = _copy(tmp_path, gitlab=True)
    _edit(root / ".gitlab-ci.yml", after, after + planted)
    faults = ci_adapters.parity_faults(root)
    assert len(faults) == 1, faults
    assert "`%s`" % key in faults[0], faults


def test_a_config_step_no_adapter_runs_is_a_fault(tmp_path):
    root = _copy(tmp_path, gitlab=True)
    _set_config(root, lambda block: block["steps"].append({"run": "make docs"}))
    faults = ci_adapters.parity_faults(root)
    assert len(faults) == 2, faults


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
    faults = ci_adapters.parity_faults(root)
    assert faults == ["the chosen adapter gitlab (.gitlab-ci.yml) is missing"], faults


def test_an_answers_file_with_no_valid_choice_is_a_fault(tmp_path):
    root = _copy(tmp_path)
    for line, said in (
        ("frontend_stack: none", "records no ci_pipeline"),
        ("ci_pipeline: jenkins", "jenkins"),
    ):
        _answer(root, line)
        faults = ci_adapters.parity_faults(root)
        assert len(faults) == 1 and said in faults[0], faults


def test_an_unchosen_file_the_project_wrote_is_not_judged(tmp_path):
    """A .gitlab-ci.yml without keel's marker in a github project is the
    project's own, kept by update, so it is not held to keel's steps."""
    root = _copy(tmp_path)
    _answer(root, "ci_pipeline: github")
    (root / ".gitlab-ci.yml").write_text("lint:\n  script:\n    - make lint\n")
    assert ci_adapters.parity_faults(root) == []


def test_an_unchosen_file_carrying_the_marker_is_still_judged(tmp_path):
    root = _copy(tmp_path, gitlab=True)
    _answer(root, "ci_pipeline: github")
    _edit(root / ".gitlab-ci.yml", "    - make trace\n", "")
    faults = ci_adapters.parity_faults(root)
    assert len(faults) == 1 and ".gitlab-ci.yml runs" in faults[0], faults


def test_a_chosen_adapter_that_lost_its_marker_is_still_judged(tmp_path):
    root = _copy(tmp_path)
    _answer(root, "ci_pipeline: github")
    _edit(root / ".github/workflows/ci.yml", "# keel-adapter: github\n", "")
    faults = ci_adapters.parity_faults(root)
    assert faults == ["ci.yml: no line `# keel-adapter: github`"], faults
