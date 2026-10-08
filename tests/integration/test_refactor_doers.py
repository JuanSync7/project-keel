"""
title: Integration — refactor doers (apply_refactor + run_make_target)
kind: tests
layer: n/a
summary: apply_and_gate writes the edit and keeps it when the (injected) gate passes, but reverts EVERY file when it fails — the safety net that keeps the tree green; run_make_target drives a real `make` subprocess in a git work tree and reports its pass/fail, failing a run that changed what git sees (content, index state, or a worktree rename's two paths) and refusing a tree without git, a target annotated [local] then [write], and a variable that would smuggle a [write] target into the run. Together they are the refactor loop's hands + gate.
"""

import json
import shutil
import subprocess
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


def _timeout_gate(gate, cwd, timeout):
    # A gate that never returns a verdict — the make subprocess hung and was killed.
    raise subprocess.TimeoutExpired(["make", gate], timeout)


def test_apply_keeps_the_edit_when_the_gate_passes(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("class Hot:\n    pass\n", encoding="utf-8")
    spec = {
        "practice": "slots-hot-path",
        "edits": [
            {"file": "m.py", "find": "    pass", "replace": "    __slots__ = ()"}
        ],
    }
    res = ar.apply_and_gate(spec, str(tmp_path), gate_runner=_pass_gate)
    assert res["applied"] is True and res["rolled_back"] is False
    assert f.read_text(encoding="utf-8") == "class Hot:\n    __slots__ = ()\n"
    assert res["files"] == ["m.py"] and res["practice"] == "slots-hot-path"


def test_apply_rolls_back_every_file_when_the_gate_fails(tmp_path):
    original = "class Hot:\n    pass\n"
    f = tmp_path / "m.py"
    f.write_text(original, encoding="utf-8")
    spec = {
        "edits": [{"file": "m.py", "find": "    pass", "replace": "    __slots__ = ()"}]
    }
    res = ar.apply_and_gate(spec, str(tmp_path), gate_runner=_fail_gate)
    assert res["applied"] is False and res["rolled_back"] is True
    assert f.read_text(encoding="utf-8") == original  # reverted byte-for-byte
    assert "FAILED" in res["gate_output"]


def test_apply_rolls_back_when_the_gate_raises_or_times_out(tmp_path):
    # The transactional guarantee must hold even when the gate never returns a
    # verdict (a hung/timed-out/killed `make`), not only when it returns red.
    original = "class Hot:\n    pass\n"
    f = tmp_path / "m.py"
    f.write_text(original, encoding="utf-8")
    spec = {
        "edits": [{"file": "m.py", "find": "    pass", "replace": "    __slots__ = ()"}]
    }
    res = ar.apply_and_gate(spec, str(tmp_path), gate_runner=_timeout_gate)
    assert res["applied"] is False and res["rolled_back"] is True
    assert f.read_text(encoding="utf-8") == original  # reverted despite the hung gate
    assert "did not complete" in res["gate_output"]


def test_multiple_edits_to_one_file_compose(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("a = 1\nb = 2\n", encoding="utf-8")
    spec = {
        "edits": [
            {"file": "m.py", "find": "a = 1", "replace": "a = 10"},
            {"file": "m.py", "find": "b = 2", "replace": "b = 20"},
        ]
    }
    res = ar.apply_and_gate(spec, str(tmp_path), gate="none")
    assert res["applied"] is True
    assert f.read_text(encoding="utf-8") == "a = 10\nb = 20\n"


def test_rollback_restores_all_files_across_a_multi_file_edit(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("y = 1\n", encoding="utf-8")
    spec = {
        "edits": [
            {"file": "a.py", "find": "x = 1", "replace": "x = 2"},
            {"file": "b.py", "find": "y = 1", "replace": "y = 2"},
        ]
    }
    res = ar.apply_and_gate(spec, str(tmp_path), gate_runner=_fail_gate)
    assert res["rolled_back"] is True
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "x = 1\n"
    assert (tmp_path / "b.py").read_text(encoding="utf-8") == "y = 1\n"


def test_plan_edits_rejects_a_missing_file_before_writing(tmp_path):
    with pytest.raises(ar.RefactorError):
        ar.plan_edits(
            {"edits": [{"file": "nope.py", "find": "a", "replace": "b"}]}, str(tmp_path)
        )


def test_plan_edits_rejects_a_path_that_escapes_the_root(tmp_path):
    outside = tmp_path.parent / "escape.py"
    outside.write_text("secret = 1\n", encoding="utf-8")
    try:
        with pytest.raises(ar.RefactorError):
            ar.plan_edits(
                {
                    "edits": [
                        {"file": "../escape.py", "find": "secret = 1", "replace": "x"}
                    ]
                },
                str(tmp_path),
            )
        assert outside.read_text(encoding="utf-8") == "secret = 1\n"  # untouched
    finally:
        outside.unlink()


def test_dry_run_writes_nothing(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("keep = 1\n", encoding="utf-8")
    planned = ar.plan_edits(
        {"edits": [{"file": "m.py", "find": "keep = 1", "replace": "keep = 2"}]},
        str(tmp_path),
    )
    assert planned[0][2] == "keep = 2\n"  # the planned NEW text
    assert f.read_text(encoding="utf-8") == "keep = 1\n"  # ...but disk is untouched


_GATE_POLICY = {
    "unattended_vars": ["CI", "RALPH"],
    "gate_runner_var": "RALPH",
    "gate_effects": ["local", "read"],
    "write_shapes": [],
    "area_dir": None,
    "effect_proof_skip": {},
    "effect_proof_kept_dirs": {"XDG_CONFIG_HOME": ".config"},
    "write_shape_exempt": {},
    "empty_test_selections": {},
    "gate_vars": ["PY"],
}


def _gate_repo(root, makefile, git=True):
    """A project the gate runner can read: a labelled Makefile, the policy, and
    (unless `git` is False) one commit, so a run can be proven read-only."""
    (root / "config").mkdir()
    (root / "config" / "project.json").write_text(
        json.dumps({"make_targets": _GATE_POLICY}), encoding="utf-8"
    )
    (root / "Makefile").write_text(makefile, encoding="utf-8")
    if git:
        for argv in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "fixture"]):
            r = subprocess.run(["git"] + argv, cwd=str(root), capture_output=True)
            assert r.returncode == 0, r.stderr
    return root


@pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
def test_run_make_target_drives_a_real_make(tmp_path):
    _gate_repo(
        tmp_path,
        "ok: ## [local] green\n\t@true\n"
        "bad: ## [local] red\n\t@false\n"
        "dirty: ## [local] claims local, writes\n\t@echo x > stray.txt\n",
    )
    ok = rmt.run_target("ok", cwd=str(tmp_path))
    assert ok["ok"] is True and ok["changed"] == [], ok
    bad = rmt.run_target("bad", cwd=str(tmp_path))
    assert bad["ok"] is False and bad["returncode"] != 0
    dirty = rmt.run_target("dirty", cwd=str(tmp_path))
    assert dirty["ok"] is False and dirty["returncode"] == 0
    assert dirty["changed"] == ["stray.txt"], dirty


@pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
def test_a_modification_to_an_already_dirty_file_is_seen(tmp_path):
    """The snapshot hashes what git lists, so a second edit to a file that was
    already modified before the run still counts as a change."""
    _gate_repo(tmp_path, "touch-it: ## [local] claims local\n\t@echo more >> a.txt\n")
    (tmp_path / "a.txt").write_text("dirty before the run\n", encoding="utf-8")
    res = rmt.run_target("touch-it", cwd=str(tmp_path))
    assert res["ok"] is False and res["changed"] == ["a.txt"], res


def test_run_make_target_refuses_without_git(tmp_path):
    _gate_repo(tmp_path, "ok: ## [local] green\n\t@true\n", git=False)
    res = rmt.run_target("ok", cwd=str(tmp_path))
    assert res["refused"].startswith("cannot prove a read-only run without git"), res


def _git(root, *argv):
    r = subprocess.run(["git"] + list(argv), cwd=str(root), capture_output=True)
    assert r.returncode == 0, r.stderr
    return r


@pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
def test_a_change_to_the_index_alone_is_seen(tmp_path):
    """Staging changes what git lists without changing a byte on disk, so the
    snapshot carries each path's two-letter status as well as its content."""
    _gate_repo(
        tmp_path, "stage: ## [local] claims local, stages\n\tgit add dirty.txt\n"
    )
    (tmp_path / "dirty.txt").write_text("a\n", encoding="utf-8")
    _git(tmp_path, "add", "dirty.txt")
    _git(tmp_path, "commit", "-qm", "dirty")
    (tmp_path / "dirty.txt").write_text("b\n", encoding="utf-8")
    res = rmt.run_target("stage", cwd=str(tmp_path))
    assert res["ok"] is False and res["changed"] == ["dirty.txt"], res


def test_a_worktree_rename_keeps_both_paths_inside_the_repo(tmp_path):
    """`git add -N` on a moved file reports ` R new\\0old` -- the rename code in
    the second column -- and the source path is the next field, not an entry."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "old.py").write_text("hello world content\n", "utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "i")
    (tmp_path / "src" / "old.py").rename(tmp_path / "src" / "new.py")
    _git(tmp_path, "add", "-N", "src/new.py")
    snap = rmt.tree_snapshot(str(tmp_path))
    assert sorted(snap) == ["src/new.py", "src/old.py"], snap
    assert "absent" in snap["src/old.py"] and "sha:" in snap["src/new.py"], snap


@pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
def test_a_variable_cannot_smuggle_a_write_target_into_a_gate_run(tmp_path):
    """Measured before the fix: `show` [local] ran `deploy-apply` [write], with
    the guard emptied on the sub-make's command line, and the marker appeared."""
    marker = tmp_path.parent / (tmp_path.name + "-deployed.marker")
    _gate_repo(
        tmp_path,
        'WRITE_GUARD = @if [ -n "$(CI)$(RALPH)" ]; then exit 1; fi\n'
        'show: ## [local] runs py\n\t$(PY) -c "print(1)"\n'
        "deploy-apply: ## [write] deploys\n\t$(WRITE_GUARD)\n\ttouch %s\n" % marker,
    )
    for extra in (
        ["PY=make deploy-apply RALPH= CI= ; true"],
        ["MAKEFILES=evil.mk"],
        ["WRITE_GUARD="],
    ):
        res = rmt.run_target("show", cwd=str(tmp_path), extra=extra)
        assert res["refused"], (extra, res)
    assert not marker.exists()


@pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
def test_a_target_annotated_local_then_write_is_refused(tmp_path):
    """Measured before the fix: the first label won, `publish` ran as [local]
    and wrote outside the tree, where the snapshot cannot see it."""
    marker = tmp_path.parent / (tmp_path.name + "-published.marker")
    _gate_repo(
        tmp_path,
        "publish: ## [local] checks the bundle\n"
        "publish: ## [write] pushes the bundle\n\techo P > %s\n" % marker,
    )
    res = rmt.run_target("publish", cwd=str(tmp_path))
    assert res["refused"] and "[write]" in res["refused"], res
    assert not marker.exists()
