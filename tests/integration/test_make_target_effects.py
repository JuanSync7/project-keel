"""
title: Integration — every [local] make target leaves the tree as it found it
kind: tests
layer: n/a
summary: The runtime half of check_W. A label is a claim, and only running the target can test it, so this runs every make target whose label (closed over its prerequisites) is exactly [local] through scripts/run_make_target.py, in a hermetic clone of the working tree, and fails any that is red or changes what git sees. A target that cannot run unattended is skipped only by name and reason in config/project.json `make_targets.effect_proof_skip`, every skip is printed, a skip naming no [local] target is stale, and a sweep that ran nothing fails. A planted `poison` target proves the sweep can fail.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import hermetic_git

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402
import run_make_target as rmt  # noqa: E402

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("make") is None, reason="make not installed"),
]

# A whole-suite target in the sweep runs for minutes; one that runs for longer is
# a hang, and a hang must fail rather than stall the suite.
_TARGET_TIMEOUT = 1800
_LOCAL = ("local",)


def _policy(root):
    with open(
        os.path.join(str(root), "config", "project.json"), encoding="utf-8"
    ) as fh:
        policy, errs = cs.make_targets_policy(json.load(fh))
    assert errs == [], errs
    return policy


def _local_targets(root):
    return sorted(
        t for t, (labels, _) in cs.target_effects(str(root)).items() if labels == _LOCAL
    )


def _sweep(root, py):
    """Run every [local] target not skipped through the gate runner.

    -> (ran, failures, skipped). A failure is red, refused, or changed the tree;
    each carries what a reader needs to act on it."""
    skip = _policy(root)["effect_proof_skip"]
    ran, failures, skipped = [], [], []
    for target in _local_targets(root):
        if target in skip:
            skipped.append((target, skip[target]))
            continue
        res = rmt.run_target(
            target, cwd=str(root), timeout=_TARGET_TIMEOUT, extra=["PY=" + py]
        )
        ran.append(target)
        if not res["ok"]:
            failures.append(
                {
                    "target": target,
                    "returncode": res["returncode"],
                    "refused": res["refused"],
                    "changed": res["changed"],
                    "output": str(res["output"])[-1500:],
                }
            )
    return ran, failures, skipped


def _in_git(root):
    probe = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    return probe.returncode == 0 and probe.stdout.strip() == "true"


@pytest.fixture(scope="module")
def clone(tmp_path_factory):
    if shutil.which("git") is None or not _in_git(_ROOT):
        pytest.skip("cannot prove a read-only run without git")
    work = tmp_path_factory.mktemp("effects")
    return hermetic_git.clone_including_worktree(_ROOT, work / "repo", work)


def test_every_local_target_leaves_the_tree_as_it_found_it(clone):
    ran, failures, skipped = _sweep(clone, sys.executable)
    # stdout, not a logger: pytest shows it under -s and on a failure, which is
    # where a reader needs to see what the proof did not cover.
    for target, reason in skipped:
        sys.stdout.write("effect proof skipped `make %s`: %s\n" % (target, reason))
    sys.stdout.write("effect proof ran %d target(s): %s\n" % (len(ran), ", ".join(ran)))
    assert ran, "the sweep ran no target -- a pass over nothing proves nothing"
    assert failures == [], json.dumps(failures, indent=2)


def test_every_skip_names_a_local_target():
    """A skip outlives its reason silently: the target is renamed, relabelled or
    removed and the entry keeps a [local] claim out of the proof for nothing."""
    skip = _policy(_ROOT)["effect_proof_skip"]
    stale = sorted(set(skip) - set(_local_targets(_ROOT)))
    assert stale == [], "effect_proof_skip names no [local] target: %s" % stale


def _git(root, *argv):
    r = subprocess.run(
        ("git",) + argv,
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    assert r.returncode == 0, r.stdout


def test_a_poisoned_local_target_fails_the_sweep(tmp_path):
    """Fault injection: the sweep above is only evidence if it can go red."""
    (tmp_path / "config").mkdir()
    shutil.copy(str(_ROOT / "config" / "project.json"), str(tmp_path / "config"))
    data = json.loads((tmp_path / "config" / "project.json").read_text("utf-8"))
    data["make_targets"]["effect_proof_skip"] = {}
    (tmp_path / "config" / "project.json").write_text(json.dumps(data), "utf-8")
    (tmp_path / "tracked.txt").write_text("before\n", encoding="utf-8")
    (tmp_path / "Makefile").write_text(
        "clean-check: ## [local] Reads only\n\t@cat tracked.txt >/dev/null\n"
        "poison: ## [local] Claims local, writes a file\n\t@echo x > poisoned.txt\n"
        "edits: ## [local] Claims local, edits a tracked file\n"
        "\t@echo after > tracked.txt\n",
        encoding="utf-8",
    )
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "fixture")
    ran, failures, _ = _sweep(tmp_path, sys.executable)
    assert ran == ["clean-check", "edits", "poison"]
    assert [(f["target"], f["changed"]) for f in failures] == [
        ("edits", ["tracked.txt"]),
        ("poison", ["poisoned.txt"]),
    ]
