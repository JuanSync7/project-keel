"""
title: Integration — a make target that selects tests fails when zero tests ran
kind: tests
layer: n/a
summary: Every Makefile target whose recipe runs pytest (found by parsing the Makefile, never listed here) fails in a scratch project that has no test of its selection, and fails the same way when every selected test is skipped. A marker config/project.json `make_targets.empty_test_selections` declares may run zero tests and prints its reason; the declaration goes stale, and the run fails, once a test of that marker runs. An xfail counts as ran; `--collect-only`, `--setup-plan` and `--setup-only`, which execute no test by design, keep pytest's own exit code; a run narrowed by a path or `-k` is named as such and is never exempt; and a real failure wins over the guard.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import makefile_copy
import script_copy

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402
import config_loader  # noqa: E402
from child_env import build_child_env  # noqa: E402

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("make") is None, reason="make not installed"),
]

# What a test-tier recipe needs to run in a project of its own, beside the
# Makefile and every makefile it includes (tests/makefile_copy.py): pytest's
# configuration and the suite's conftest. Recipe entry scripts and their imports
# are derived; pytest configuration and the manifest are runtime data.
_SHIPPED = (
    "pyproject.toml",
    "config/project.json",
    "tests/conftest.py",
)

_PASS = "def test_passes():\n    assert True\n"
_SKIP = "import pytest\n\n\ndef test_skipped():\n    pytest.skip('not here')\n"
_XFAIL = (
    "import pytest\n\n\n@pytest.mark.xfail(reason='known', strict=True)\n"
    "def test_known():\n    assert False\n"
)
_FAIL = "def test_fails():\n    assert False\n"


def _tiers():
    """target -> its `-m` marker (None: the whole suite), for every recipe that
    runs pytest in this project's Makefile."""
    text = (_ROOT / "Makefile").read_text(encoding="utf-8")
    return cs.pytest_selections([("Makefile", text)])


def _recipe_scripts():
    """Every script a test-tier target's recipe reaches, sorted."""
    rules = cs._make_rules((_ROOT / "Makefile").read_text(encoding="utf-8"))
    scripts = set()
    for target in _tiers():
        scripts.update(cs._scripts_reachable_from(rules, target))
    return tuple(sorted(scripts))


# A module-level name, so tests/integration/test_script_copy.py can evaluate
# the copy roster and prove the copy complete.
_RECIPE_SCRIPTS = _recipe_scripts()

# The ship set the scratch project declares, whatever the host configures: a
# generated project ships an empty tests.ship_set, which test-ship refuses
# before any selection reaches the empty-selection guard.
_SCRATCH_SHIP = ["tests/test_ship_scratch.py"]


def _scratch(tmp_path, selections=None):
    """A project carrying the test tiers and nothing to test; `selections`
    replaces make_targets.empty_test_selections."""
    root = tmp_path / "proj"
    root.mkdir(parents=True)
    makefile_copy.copy_makefiles(root, _ROOT)
    script_copy.copy_with_imports(root, _ROOT, _SHIPPED + _RECIPE_SCRIPTS)
    path = root / "config" / "project.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["tests"]["ship_set"] = _SCRATCH_SHIP
    if selections is not None:
        manifest["make_targets"]["empty_test_selections"] = selections
    path.write_text(json.dumps(manifest), encoding="utf-8")
    # Explicit module selections must exist to reach conftest's session guard;
    # missing paths are pytest usage errors rather than empty selections.
    for rel in _ship_paths(root):
        module = root / rel
        module.parent.mkdir(parents=True, exist_ok=True)
        module.write_text("", encoding="utf-8")
    return root


def _ship_paths(root):
    """Return the configured tests.ship_set paths of the project at root."""
    key = ("tests", "ship_set")
    return config_loader.resolve(
        config_loader.read(str(root)),
        config_loader.rows(key),
        config_loader.CONFIG_FILE,
        environ={},
    )[key]


def _add_test(root, name, marker, body):
    head = "import pytest\n\n"
    if marker:
        head += "pytestmark = pytest.mark.%s\n\n" % marker
    (root / "tests" / ("test_%s.py" % name)).write_text(
        head + body.replace("import pytest\n\n\n", ""), encoding="utf-8"
    )


def _make(root, target, *, addopts=""):
    r = subprocess.run(
        ["make", "--no-print-directory", "PY=" + sys.executable, target],
        cwd=str(root),
        env=build_child_env(extra={"PYTEST_ADDOPTS": addopts}),
        capture_output=True,
        text=True,
        timeout=_child_timeout(),
    )
    return r.returncode, r.stdout + r.stderr


def _child_timeout():
    key = ("tests", "child_timeout_seconds")
    return config_loader.resolve(
        config_loader.read(str(_ROOT)),
        config_loader.rows(key),
        config_loader.CONFIG_FILE,
    )[key]


def _pytest(root, *args, addopts=""):
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider"] + list(args),
        cwd=str(root),
        env=build_child_env(extra={"PYTHONPATH": "src:.", "PYTEST_ADDOPTS": addopts}),
        capture_output=True,
        text=True,
        timeout=_child_timeout(),
    )
    return r.returncode, r.stdout + r.stderr


def test_every_tier_target_fails_over_an_empty_selection(tmp_path):
    tiers = _tiers()
    # A pass over zero derived targets proves nothing: the whole suite and at
    # least one marker tier must have been found.
    assert len(tiers) >= 2 and None in tiers.values(), tiers
    for target, marker in sorted(tiers.items()):
        root = _scratch(tmp_path / target)
        if marker is not None:
            # Something to deselect, so the empty selection is the marker's own.
            _add_test(root, "unmarked", None, _PASS)
        code, out = _make(root, target)
        assert code != 0, (target, out[-2000:])
        assert "make_targets.empty_test_selections" in out, (target, out[-2000:])


def test_a_skip_only_selection_fails(tmp_path):
    root = _scratch(tmp_path)
    _add_test(root, "smoke_skipped", "smoke", _SKIP)
    code, out = _make(root, "smoke")
    assert code != 0 and "zero tests ran" in out, out[-2000:]
    code, out = _make(root, "test")
    assert code != 0 and "zero tests ran" in out, out[-2000:]


def test_ship_paths_run_only_their_tests_and_name_an_empty_narrowing(tmp_path):
    root = _scratch(tmp_path)
    paths = _ship_paths(root)
    assert paths, "the ship recipe must select at least one module"
    selected = root / paths[0]
    selected.write_text(_PASS, encoding="utf-8")
    _add_test(root, "outside_ship", None, _FAIL)
    code, out = _make(root, "test-ship")
    assert code == 0 and "1 passed" in out, out[-2000:]

    code, out = _make(root, "test-ship", addopts="-k zzz_nomatch")
    assert code != 0 and "zero tests ran" in out, out[-2000:]
    assert "make_targets.empty_test_selections" in out, out[-2000:]
    assert paths[0] in out and "-k zzz_nomatch" in out, out[-2000:]

    selected.write_text(_SKIP, encoding="utf-8")
    code, out = _make(root, "test-ship")
    assert code != 0 and "zero tests ran" in out, out[-2000:]
    assert "make_targets.empty_test_selections" in out, out[-2000:]


def test_a_declared_empty_selection_passes_with_its_reason(tmp_path):
    reason = "no smoke surface yet"
    root = _scratch(tmp_path / "empty", {"smoke": reason})
    _add_test(root, "unmarked", None, _PASS)
    code, out = _make(root, "smoke")
    assert code == 0 and reason in out, out[-2000:]

    root = _scratch(tmp_path / "passing")
    _add_test(root, "smoke_passes", "smoke", _PASS)
    code, out = _make(root, "smoke")
    assert code == 0, out[-2000:]

    root = _scratch(tmp_path / "xfail")
    _add_test(root, "smoke_xfail", "smoke", _XFAIL)
    code, out = _make(root, "smoke")
    assert code == 0, out[-2000:]


def test_a_declaration_goes_stale_once_a_test_runs(tmp_path):
    root = _scratch(tmp_path, {"smoke": "no smoke surface yet"})
    _add_test(root, "smoke_passes", "smoke", _PASS)
    code, out = _make(root, "smoke")
    assert code != 0, out[-2000:]
    assert "stale: make_targets.empty_test_selections.smoke" in out, out[-2000:]


def test_collect_only_and_real_failures_are_untouched(tmp_path):
    root = _scratch(tmp_path / "co")
    _add_test(root, "unmarked", None, _PASS)
    code, out = _pytest(root, "--co", "-m", "smoke")
    assert code == 5, out[-2000:]
    assert "make_targets.empty_test_selections" not in out, out[-2000:]
    # --setup-plan and --setup-only run a session with no call phase by design,
    # so, like a listing, they keep pytest's own exit code.
    for mode in ("--setup-plan", "--setup-only"):
        code, out = _pytest(root, mode)
        assert code == 0, (mode, out[-2000:])
        assert "zero tests ran" not in out, (mode, out[-2000:])

    root = _scratch(tmp_path / "fail")
    _add_test(root, "fails", None, _FAIL)
    _add_test(root, "skipped", None, _SKIP)
    code, out = _pytest(root)
    assert code == 1, out[-2000:]


def test_a_narrowed_selection_is_named_and_never_declarable(tmp_path):
    # A run narrowed by a path or -k is not "the whole suite", and a marker
    # declaration cannot exempt it: the message says what was selected.
    root = _scratch(tmp_path, {"smoke": "no smoke surface yet"})
    _add_test(root, "unmarked", None, _PASS)
    code, out = _pytest(root, "tests/test_unmarked.py", "-k", "zzz_nomatch")
    assert code == 5, out[-2000:]
    assert "the whole suite" not in out, out[-2000:]
    assert "tests/test_unmarked.py" in out and "-k zzz_nomatch" in out, out[-2000:]
    code, out = _pytest(root, "-m", "smoke", "-k", "zzz_nomatch")
    assert code == 5, out[-2000:]
    assert "-m smoke -k zzz_nomatch" in out, out[-2000:]


@pytest.mark.parametrize(
    "addopts",
    [
        "-k test_passes",
        "-xk test_passes",
        "-qktest_passes",
        "-munit",
        "--deselect=tests/test_unit.py::test_other",
        "tests/test_unit.py::test_passes",
        "-k 'unterminated",
    ],
)
def test_full_gate_refuses_addopts_but_tiers_and_direct_pytest_can_narrow(
    tmp_path, addopts
):
    root = _scratch(tmp_path)
    _add_test(root, "unit", "unit", _PASS + "\ndef test_other():\n    assert True\n")
    code, out = _make(root, "test", addopts=addopts)
    assert code != 0, out[-2000:]
    assert "full gate" in out and "PYTEST_ADDOPTS" in out, out[-2000:]
    assert "Error 2" in out, out[-2000:]
    if "unterminated" not in addopts:
        code, out = _make(root, "unit", addopts=addopts)
        assert code == 0 and ("1 passed" in out or "2 passed" in out), out[-2000:]
        code, out = _pytest(root, "-k", "test_passes")
        assert code == 0 and "1 passed" in out, out[-2000:]
        code, out = _pytest(root, addopts=addopts)
        assert code == 0 and ("1 passed" in out or "2 passed" in out), out[-2000:]
        code, out = _pytest(root, "--keel-full-gate", addopts=addopts)
        assert code != 0 and "full gate" in out and "PYTEST_ADDOPTS" in out, out[-2000:]
    code, out = _make(root, "test", addopts="-q -p no:cacheprovider -x")
    assert code == 0 and "2 passed" in out, out[-2000:]
    assert not (root / ".evidence").exists()


@pytest.mark.parametrize(
    "args",
    [
        ["-ktest_passes"],
        ["-m=unit"],
        ["tests/test_unit.py::test_passes"],
        ["--deselect=tests/test_unit.py::test_other"],
    ],
)
def test_full_gate_flag_refuses_command_line_narrowing(tmp_path, args):
    root = _scratch(tmp_path)
    _add_test(root, "unit", "unit", _PASS)
    code, out = _pytest(root, "--keel-full-gate", *args)
    assert code != 0 and "full gate" in out and "command line" in out, out[-2000:]
