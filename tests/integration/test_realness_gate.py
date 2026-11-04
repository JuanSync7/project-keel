"""
title: Integration — an e2e test drives the dependency it claims, not a mock of it
kind: tests
layer: n/a
summary: The realness gate. It tiers every test function under config/project.json `test_quality.realness.roots` through tests/realness.py, from what it uses and the fixtures it requests, autouse and `conftest.py` ones included, and fails one whose tier is `mock`, naming file, line, function and the signal that put it there. A fake, an in-process app, real infrastructure and no replacement at all pass. A test `test_quality.realness.exempt` names with a reason is let through, an excuse whose test is not `mock` is red, and a run that reads no test function fails. tests/unit/test_realness.py plants each signal in a temporary tree. Not a check_* letter: the letters A to Z are taken.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "tests"))

import realness  # noqa: E402
import source_tree  # noqa: E402

pytestmark = pytest.mark.integration


def test_no_e2e_test_replaces_its_dependency_with_a_mock():
    root = str(_ROOT)
    policy = realness.policy(root)
    tiered = realness.scan(
        root,
        realness.test_files(root, policy.roots),
        source_tree.import_layers(root)["search_roots"],
    )
    failures = realness.verdict(tiered, policy.exempt, policy.roots)
    assert failures == [], (
        "%d of %d test functions replace a dependency with a mock; drive the "
        "real part, a fake or the app in process, or give the reason in "
        "config/project.json %s:\n%s"
        % (len(failures), len(tiered), ".".join(realness.EXEMPT), "\n".join(failures))
    )
