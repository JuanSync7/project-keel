"""
title: Integration — the CI Python release is a copier answer held to the backend floor answer
kind: tests
layer: n/a
summary: copier.yml asks `toolchain_python`, the release a generated project's CI installs, after `backend_python`, and config/project.json.jinja renders it into `toolchain.python`, so a project that raises its floor is generated with a release that satisfies it instead of keel's own. Its default is keel's configured `toolchain.python`, read through the loader, and keel's own floor accepts it. Its validator, rendered in a sandboxed jinja environment as copier renders it, refuses a release that is not MAJOR.MINOR or MAJOR.MINOR.PATCH in ASCII digits and a floor clause it cannot judge, and otherwise agrees with packaging's specifier rules over a grid of floors and releases. The real copier refuses `backend_python: '>=3.12'` with the default release and generates the project with `3.12`, whose own toolchain gate then passes. Keel-only: copier.yml excludes every test_copier_*.py from generated projects, and a project that still carries this module skips it, because it has no copier.yml.
"""

import itertools
import json
import subprocess
import sys
from pathlib import Path

import pytest

import optional_deps

yaml = optional_deps.importorskip("yaml", extra="template")
jinja_sandbox = optional_deps.importorskip("jinja2.sandbox", extra="template")
# packaging is pytest's own dependency, so wherever this suite runs it is there.
from packaging.specifiers import SpecifierSet  # noqa: E402
from packaging.version import Version  # noqa: E402

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import config_loader  # noqa: E402
from child_env import build_child_env  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_reference_drift as drift  # noqa: E402

# copier's `_exclude` never retires a file on `copier update`, so a project
# generated before the prune can still carry this module; it reads copier.yml,
# which only the template has, so it skips there instead of failing.
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (_ROOT / "copier.yml").is_file(),
        reason="template-only: needs copier.yml (absent in generated projects)",
    ),
]

_QUESTION = "toolchain_python"
_FLOOR = "backend_python"
_TWIN = _ROOT / "config" / "project.json.jinja"
_GATE = (
    "tests/integration/test_toolchain_gate.py::"
    "test_the_configured_python_satisfies_the_backend_floor_and_requires_python"
)

# Floors packaging can judge and the validator claims to: each operator, a
# wildcard, a compatible release of two and three parts, spaces, and a clause
# list. The releases straddle each boundary the floors draw.
_FLOORS = (
    ">=3.10",
    ">=3.12",
    ">=3",
    ">=3.10,<3.13",
    ">= 3.10 , < 3.12",
    "~=3.11",
    "~=3.11.2",
    "==3.11.*",
    "==3.*",
    "!=3.12.*",
    "==3.12",
    "==3.11.0",
    "!=3.11",
    "<=3.11",
    ">3.11",
    "<3.12",
    ">3.11.0",
    "",
)
_RELEASES = (
    "3.9",
    "3.10",
    "3.11",
    "3.11.0",
    "3.11.2",
    "3.11.9",
    "3.12",
    "3.12.1",
    "3.13",
    "4.0",
)


def _questions():
    return yaml.safe_load((_ROOT / "copier.yml").read_text(encoding="utf-8"))


def _verdict(floor, release):
    """What the validator renders for *floor* and *release*, stripped: empty
    means copier accepts the pair."""
    spec = _questions()[_QUESTION]
    env = jinja_sandbox.SandboxedEnvironment()
    rendered = env.from_string(spec["validator"]).render(
        **{_FLOOR: floor, _QUESTION: release}
    )
    return rendered.strip()


def test_the_question_follows_the_floor_and_has_a_validator():
    questions = _questions()
    names = list(questions)
    assert names.index(_QUESTION) > names.index(_FLOOR), names
    spec = questions[_QUESTION]
    assert spec.get("type") == "str", spec
    assert spec.get("when", True) is not False, "a computed answer is not recorded"
    assert spec.get("validator"), spec


def test_the_validator_judges_a_floor_as_packaging_does():
    judged = 0
    wrong = []
    for floor, release in itertools.product(_FLOORS, _RELEASES):
        expected = SpecifierSet(floor).contains(Version(release))
        verdict = _verdict(floor, release)
        if (verdict == "") != expected:
            wrong.append((floor, release, expected, verdict))
        judged += 1
    assert judged == len(_FLOORS) * len(_RELEASES) > 0
    assert wrong == [], wrong


@pytest.mark.parametrize(
    "release",
    ["3", "3.11.0.1", "3.²", "３.１１", "3.11rc1", "", "3..11", " 3.11"],
)
def test_the_validator_refuses_a_release_that_is_not_dotted_ascii_digits(release):
    verdict = _verdict(">=3.10", release)
    assert _QUESTION in verdict, verdict


@pytest.mark.parametrize(
    "floor", ["~=3", ">=3.*", "===3.11", ">=3.10rc1", "3.11", "=>3.10", ">=3.1.2.3"]
)
def test_the_validator_refuses_a_floor_clause_it_cannot_judge(floor):
    verdict = _verdict(floor, "3.11")
    assert "cannot judge" in verdict and floor.strip() in verdict, verdict


def test_the_default_is_keels_configured_release_and_keels_floor_accepts_it():
    questions = _questions()
    loaded = config_loader.read(str(_ROOT))
    rows = config_loader.rows(("toolchain", "python"))
    configured = config_loader.resolve(loaded, rows, config_loader.CONFIG_FILE)[
        ("toolchain", "python")
    ]
    assert questions[_QUESTION]["default"] == configured
    assert _verdict(questions[_FLOOR]["default"], configured) == ""


def test_the_twin_renders_the_answer_into_toolchain_python():
    jinja2 = optional_deps.importorskip("jinja2", extra="template")
    questions = _questions()
    answers = drift.complete_answers(questions, {_QUESTION: "3.12"})
    rendered = (
        jinja2.Environment(undefined=jinja2.StrictUndefined)
        .from_string(_TWIN.read_text(encoding="utf-8"))
        .render(**answers)
    )
    assert json.loads(rendered)["toolchain"]["python"] == "3.12"


def _copy(dest, **data):
    copier = optional_deps.importorskip("copier", extra="template")
    copier.run_copy(
        str(_ROOT),
        str(dest),
        data=data,
        defaults=True,
        vcs_ref="HEAD",
        unsafe=True,
        quiet=True,
    )


def test_copier_refuses_a_raised_floor_with_the_default_release(tmp_path):
    # copier raises a ValueError naming the question whose validator refused.
    with pytest.raises(ValueError, match="question '%s'" % _QUESTION) as caught:
        _copy(tmp_path / "proj", project_name="demo_proj", backend_python=">=3.12")
    assert "does not satisfy" in str(caught.value), caught.value
    assert not (tmp_path / "proj" / "config" / "project.json").exists()


def test_a_project_generated_with_a_raised_floor_passes_its_toolchain_gate(tmp_path):
    dest = tmp_path / "proj"
    _copy(
        dest,
        project_name="demo_proj",
        backend_python=">=3.12",
        toolchain_python="3.12",
    )
    loaded = config_loader.read(str(dest))
    assert loaded["toolchain"]["python"] == "3.12"
    assert loaded["layers"]["backend"]["python"] == ">=3.12"
    ran = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", _GATE],
        cwd=str(dest),
        env=build_child_env(root=str(dest), extra={"PYTHONPATH": "src:."}),
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert ran.returncode == 0, ran.stdout[-4000:] + ran.stderr[-2000:]
    assert "1 passed" in ran.stdout, ran.stdout[-2000:]
