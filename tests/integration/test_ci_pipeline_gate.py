"""
title: Integration — every CI adapter runs exactly config/project.json ci_pipeline.steps, in order
kind: tests
layer: n/a
summary: config/project.json `ci_pipeline.steps` is the one statement of what CI runs, and each adapter file present (`ci_pipeline.adapters`: .github/workflows/ci.yml, .gitlab-ci.yml) is held to it through tests/ci_adapters.py parity_faults. The adapters in this tree have no fault; an empty step list, a tree with no adapter, a missing marker line or one that is not the whole line, a dropped, added, reordered or changed step, a changed env value, and a GitLab image or GIT_DEPTH other than the configured one each turn the judge red on a copy, and so does each GitLab key the shipped file lacks, however it is quoted or written (`when: manual`, `"when"`, `? when`, `'rules'`, `needs`, `allow_failure`, a `<<` merge, `MAKEFLAGS: "-n"` at either level, `default:`, `workflow`, `include`, another job), with one fault naming its key path, a key it has that the file lacks, a key set twice (named by both lines), a file YAML cannot read, a script item that is not a line, and a missing pyyaml. A file that differs only in what YAML does not read (comments, key order, quoting, a flow, nested or one-string script) has no fault. In a project, the `ci_pipeline` answer in .copier-answers.yml picks what is judged: a chosen adapter that is missing, or one that lost its marker, is a fault, and so is an answers file with no valid answer, one that answers twice (named by both lines), and one the scanner cannot read (shown as written); an unchosen file the project wrote, with no marker, is not judged, and an unchosen one carrying the marker still is. The GitLab cases render the template's .gitlab-ci.yml.jinja with the toolchain answer, so the shipped twin is judged too, and yaml reads the rendered file to the same script lines the stdlib scanner does and to exactly ci_adapters.gitlab_document.
"""

import json
import shutil
import sys
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
    ("another job", 'GIT_DEPTH: "0"\n', "lint:\n  script: [make lint]\n", ["lint"]),
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


def test_a_gitlab_key_keel_ships_that_is_missing_is_a_fault(tmp_path):
    root = _copy(tmp_path, gitlab=True)
    _edit(root / ".gitlab-ci.yml", "variables:\n", "x-variables:\n")
    faults = ci_adapters.parity_faults(root)
    assert len(faults) == 2, faults
    assert "`x-variables`" in faults[0] and "`variables`" in faults[1], faults


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


def test_a_gitlab_file_yaml_cannot_read_is_one_fault(tmp_path):
    root = _copy(tmp_path, gitlab=True)
    _edit(root / ".gitlab-ci.yml", "test:\n", "test:\n  <<: *nowhere\n")
    faults = ci_adapters.parity_faults(root)
    assert len(faults) == 1 and faults[0].startswith(".gitlab-ci.yml: "), faults


def test_without_pyyaml_a_gitlab_file_is_a_fault_not_a_pass(tmp_path, monkeypatch):
    root = _copy(tmp_path, gitlab=True)
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
    (root / ".github/workflows/ci.yml").unlink()
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


def test_a_ci_pipeline_answered_twice_is_a_fault_naming_both_lines(tmp_path):
    """YAML reads the last of two `ci_pipeline:` lines and a line scan the
    first, so neither may decide: the judge fails closed and names both."""
    root = _copy(tmp_path, gitlab=True)
    _answer(root, "ci_pipeline: github\nci_pipeline: gitlab")
    faults = ci_adapters.parity_faults(root)
    assert len(faults) == 1, faults
    for said in ("line 2", "`ci_pipeline: github`", "line 3", "`ci_pipeline: gitlab`"):
        assert said in faults[0], faults


def test_an_answer_the_scanner_cannot_read_is_shown_as_written(tmp_path):
    """A quoted value with a trailing comment is not read as an adapter name,
    and the fault shows the line as the file has it, not the scanner's
    reading of it."""
    root = _copy(tmp_path)
    _answer(root, "ci_pipeline: 'gitlab' # c")
    faults = ci_adapters.parity_faults(root)
    assert len(faults) == 1, faults
    assert "`ci_pipeline: 'gitlab' # c`" in faults[0], faults


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
