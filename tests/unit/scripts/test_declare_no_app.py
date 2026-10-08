"""
title: Unit — scripts/jobs/declare_no_app.py settles a project whose composition root is gone
kind: tests
layer: n/a
summary: The pure half of the copier migration that keeps a project green when `copier update` brings `layers.app` to a project that had deleted its composition root. `settle` rewrites config/project.json as text, so every byte it does not mean to change stays: `layers.app` becomes null, each smoke marker is declared in `make_targets.empty_test_selections` and each run target added to `make_targets.effect_proof_skip`, an entry already there is kept as written, and the result parses to exactly the intended manifest or it raises. A second settle changes nothing. `runner_targets` reads the targets whose recipe runs scripts/run_app.py from the Makefile and `module_markers` the bare marks of a test module's `pytestmark`, so neither name is written into the job. `needs_settling` acts only when the declared path is absent and the pre-update manifest had no `layers.app`.
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))

import declare_no_app as dna  # noqa: E402

pytestmark = pytest.mark.unit

# The shape copier renders: hand-formatted, inline arrays, a comment that
# names the keys without quoting them.
_TEXT = """{
  "_comment": "effect_proof_skip keeps a target out; empty_test_selections names a marker",
  "make_targets": {
    "gate_effects": ["local", "read"],
    "effect_proof_skip": {
      "new": "needs DEST"
    },
    "empty_test_selections": {},
    "gate_vars": ["PY"]
  },
  "layers": {
    "backend": {
      "language": "python",
      "path": "src/backend"
    },
    "app": {
      "language": "python",
      "path": "src/app",
      "module": "app"
    }
  }
}
"""


def _settled(text=_TEXT, markers=("smoke",), targets=("run",)):
    return dna.settle(text, list(markers), list(targets))


def test_settle_nulls_app_and_declares_both_consequences():
    out = json.loads(_settled())
    assert out["layers"]["app"] is None
    assert out["make_targets"]["empty_test_selections"] == {"smoke": dna.SMOKE_REASON}
    assert out["make_targets"]["effect_proof_skip"] == {
        "run": dna.RUN_REASON,
        "new": "needs DEST",
    }


def test_settle_changes_no_other_byte():
    expected = (
        _TEXT.replace(
            """"app": {
      "language": "python",
      "path": "src/app",
      "module": "app"
    }""",
            '"app": null',
        )
        .replace(
            '"effect_proof_skip": {\n',
            '"effect_proof_skip": {\n      "run": %s,\n' % json.dumps(dna.RUN_REASON),
        )
        .replace(
            '"empty_test_selections": {}',
            '"empty_test_selections": {\n      "smoke": %s\n    }'
            % json.dumps(dna.SMOKE_REASON),
        )
    )
    assert _settled() == expected


def test_settle_is_a_fixed_point():
    once = _settled()
    assert _settled(once) == once


def test_an_entry_already_declared_is_kept_as_written():
    text = _TEXT.replace(
        '"empty_test_selections": {}', '"empty_test_selections": {"smoke": "mine"}'
    )
    out = json.loads(_settled(text))
    assert out["make_targets"]["empty_test_selections"] == {"smoke": "mine"}


def test_no_markers_and_no_targets_only_null_the_app():
    out = json.loads(_settled(markers=(), targets=()))
    assert out["layers"]["app"] is None
    assert out["make_targets"]["empty_test_selections"] == {}
    assert out["make_targets"]["effect_proof_skip"] == {"new": "needs DEST"}


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        json.dumps({"layers": {"app": {"path": "src/app", "module": "app"}}}),
        _TEXT.replace('"empty_test_selections": {},', ""),
        # Two objects equal to layers.app: which one to null is a guess.
        _TEXT.replace(
            '"backend": {',
            '"x": {"app": {"language": "python", '
            '"path": "src/app", "module": "app"}},\n    "backend": {',
        ),
    ],
)
def test_settle_raises_rather_than_guess(text):
    with pytest.raises(dna.SettleError):
        _settled(text)


def test_an_edit_that_lands_in_the_wrong_object_is_refused():
    """The text edit finds a block by its key at the start of a line. Here the
    real `make_targets.empty_test_selections` shares a line with its parent,
    and another object's key of that name starts a line, so the edit lands
    there: only the parse-back comparison notices."""
    text = (
        _TEXT.replace('"empty_test_selections": {},\n', "")
        .replace(
            '"make_targets": {\n',
            '"make_targets": {"empty_test_selections": {},\n',
        )
        .replace(
            '  "layers": {\n',
            '  "elsewhere": {\n    "empty_test_selections": {}\n  },\n  "layers": {\n',
        )
    )
    assert json.loads(text)["make_targets"]["empty_test_selections"] == {}
    with pytest.raises(dna.SettleError, match="intended manifest"):
        _settled(text)


def test_runner_targets_reads_the_makefile():
    makefile = (
        "run: check-python ## [local] Run it\n"
        "\tPYTHONPATH=$(PYTHONPATH) $(PY) scripts/run_app.py\n"
        "serve:\n\t$(PY) scripts/run_app.py --port 1\n"
        "test: ## [local] Tests\n\t$(PY) -m pytest\n"
        "# run_app.py named in a comment is not a recipe\n"
    )
    assert dna.runner_targets(makefile) == ["run", "serve"]
    assert dna.runner_targets("") == []


def test_module_markers_reads_bare_pytestmark():
    assert dna.module_markers("import pytest\npytestmark = pytest.mark.smoke\n") == [
        "smoke"
    ]
    listed = (
        "import pytest\npytestmark = [pytest.mark.smoke, pytest.mark.slow,\n"
        "    pytest.mark.skipif(True, reason='x')]\n"
    )
    assert dna.module_markers(listed) == ["slow", "smoke"]
    assert dna.module_markers("x = 1\n") == []


def test_needs_settling_only_for_an_introduced_and_absent_root(tmp_path):
    manifest = {"layers": {"app": {"path": "src/app", "module": "app"}}}
    before = {"layers": {}}
    root = str(tmp_path)
    assert dna.needs_settling(manifest, before, root)
    assert dna.needs_settling(manifest, None, root)
    # The project declared it itself: check_H judges, this job does not.
    assert not dna.needs_settling(manifest, manifest, root)
    assert not dna.needs_settling({"layers": {"app": None}}, before, root)
    assert not dna.needs_settling({"layers": {}}, before, root)
    (tmp_path / "src" / "app").mkdir(parents=True)
    assert not dna.needs_settling(manifest, before, root)
