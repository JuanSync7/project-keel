"""
title: Integration — refactor doers (apply_refactor + run_make_target)
kind: tests
layer: n/a
summary: apply_and_gate writes the edit and keeps it when the (injected) gate passes, but reverts EVERY file when it fails — the safety net that keeps the tree green; run_make_target drives a real `make` subprocess and reports its pass/fail. Together they are the refactor loop's hands + gate.
"""
import shutil
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import apply_refactor as ar  # noqa: E402
import run_make_target as rmt  # noqa: E402

pytestmark = pytest.mark.integration


def _pass_gate(gate, cwd, timeout):
    return True, "gate ok"


def _fail_gate(gate, cwd, timeout):
    return False, "gate FAILED\n1 error"


def test_apply_keeps_the_edit_when_the_gate_passes(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("class Hot:\n    pass\n", encoding="utf-8")
    spec = {"practice": "slots-hot-path",
            "edits": [{"file": "m.py", "find": "    pass", "replace": "    __slots__ = ()"}]}
    res = ar.apply_and_gate(spec, str(tmp_path), gate_runner=_pass_gate)
    assert res["applied"] is True and res["rolled_back"] is False
    assert f.read_text(encoding="utf-8") == "class Hot:\n    __slots__ = ()\n"
    assert res["files"] == ["m.py"] and res["practice"] == "slots-hot-path"


def test_apply_rolls_back_every_file_when_the_gate_fails(tmp_path):
    original = "class Hot:\n    pass\n"
    f = tmp_path / "m.py"
    f.write_text(original, encoding="utf-8")
    spec = {"edits": [{"file": "m.py", "find": "    pass", "replace": "    __slots__ = ()"}]}
    res = ar.apply_and_gate(spec, str(tmp_path), gate_runner=_fail_gate)
    assert res["applied"] is False and res["rolled_back"] is True
    assert f.read_text(encoding="utf-8") == original      # reverted byte-for-byte
    assert "FAILED" in res["gate_output"]


def test_multiple_edits_to_one_file_compose(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("a = 1\nb = 2\n", encoding="utf-8")
    spec = {"edits": [{"file": "m.py", "find": "a = 1", "replace": "a = 10"},
                      {"file": "m.py", "find": "b = 2", "replace": "b = 20"}]}
    res = ar.apply_and_gate(spec, str(tmp_path), gate="none")
    assert res["applied"] is True
    assert f.read_text(encoding="utf-8") == "a = 10\nb = 20\n"


def test_rollback_restores_all_files_across_a_multi_file_edit(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("y = 1\n", encoding="utf-8")
    spec = {"edits": [{"file": "a.py", "find": "x = 1", "replace": "x = 2"},
                      {"file": "b.py", "find": "y = 1", "replace": "y = 2"}]}
    res = ar.apply_and_gate(spec, str(tmp_path), gate_runner=_fail_gate)
    assert res["rolled_back"] is True
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "x = 1\n"
    assert (tmp_path / "b.py").read_text(encoding="utf-8") == "y = 1\n"


def test_plan_edits_rejects_a_missing_file_before_writing(tmp_path):
    with pytest.raises(ar.RefactorError):
        ar.plan_edits({"edits": [{"file": "nope.py", "find": "a", "replace": "b"}]}, str(tmp_path))


def test_dry_run_writes_nothing(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("keep = 1\n", encoding="utf-8")
    planned = ar.plan_edits(
        {"edits": [{"file": "m.py", "find": "keep = 1", "replace": "keep = 2"}]}, str(tmp_path))
    assert planned[0][2] == "keep = 2\n"                  # the planned NEW text
    assert f.read_text(encoding="utf-8") == "keep = 1\n"  # ...but disk is untouched


@pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
def test_run_make_target_drives_a_real_make(tmp_path):
    (tmp_path / "Makefile").write_text("ok:\n\t@true\nbad:\n\t@false\n", encoding="utf-8")
    assert rmt.run_target("ok", cwd=str(tmp_path))["ok"] is True
    bad = rmt.run_target("bad", cwd=str(tmp_path))
    assert bad["ok"] is False and bad["returncode"] != 0
