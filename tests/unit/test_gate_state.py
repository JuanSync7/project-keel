"""
title: Unit — the check_structure state guard puts back what run_checks rebinds
kind: tests
layer: n/a
summary: tests/gate_state.py. `rebound_names` reads ROOT, the config memo and the reported sets from scripts/check_structure.py's run_checks, and refuses a module with no run_checks, one whose source cannot be read, or one that declares no global; a run_checks over a temporary tree followed by `restore` leaves ROOT, the config memo and the profile registry reader as they were, and an in-place append to a saved list is undone.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

import gate_state

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit


def _module(name: str, source: str) -> ModuleType:
    """A module run from *source* in memory, so inspect cannot read it."""
    module = ModuleType(name)
    exec(compile(source, "<%s>" % name, "exec"), module.__dict__)
    return module


def _file_module(tmp_path: Path, name: str, source: str) -> ModuleType:
    """A module imported from a file, so inspect reads its source."""
    path = tmp_path / ("%s.py" % name)
    path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rebound_names_are_read_from_run_checks():
    names = gate_state.rebound_names(cs)
    assert {"ROOT", "errors", "warnings", "_CONFIG_READ", "_READ_REPORTED"} <= names


def test_a_module_without_run_checks_is_refused():
    with pytest.raises(gate_state.GateStateError, match="no run_checks"):
        gate_state.rebound_names(_module("no_run", "X = 1\n"))


def test_a_run_checks_whose_source_cannot_be_read_is_refused():
    module = _module("no_source", "def run_checks(root):\n    return []\n")
    with pytest.raises(gate_state.GateStateError, match="cannot read"):
        gate_state.rebound_names(module)


def test_a_run_checks_that_declares_no_global_is_refused(tmp_path):
    module = _file_module(
        tmp_path, "no_global", "def run_checks(root):\n    return []\n"
    )
    with pytest.raises(gate_state.GateStateError, match="declares no global"):
        gate_state.rebound_names(module)


def test_restore_undoes_a_run_over_a_temporary_tree(tmp_path):
    """The case that failed make unit: a run over a temporary tree, then the
    real registry read in the same process."""
    before_root = cs.ROOT
    before_names = cs._defined_profile_names()
    saved = gate_state.snapshot(cs)
    (tmp_path / "config").mkdir()
    cs.run_checks(str(tmp_path), project_checks=False)
    # Without the restore the reader judges the temporary tree.
    assert str(tmp_path) == cs.ROOT and cs._defined_profile_names() is None
    gate_state.restore(cs, saved)
    assert before_root == cs.ROOT
    assert cs._defined_profile_names() == before_names
    assert before_names is not None and {"ai", "cuda", "langgraph"} <= before_names


def test_restore_undoes_an_in_place_append():
    saved = gate_state.snapshot(cs)
    length = len(cs.errors)
    cs.errors.append("planted")
    gate_state.restore(cs, saved)
    assert len(cs.errors) == length and "planted" not in cs.errors
