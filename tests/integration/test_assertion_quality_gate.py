"""
title: Integration — every test function shows it can fail
kind: tests
layer: n/a
summary: The assertion-quality gate. It reads every test function under config/project.json `test_quality.assertions.roots` through tests/assertion_quality.py and fails, naming file, line and function, one with no assertion (in its body or in a helper it calls, followed `test_quality.assertions.helper_depth` calls deep), with only truthy-constant assertions, with a tautology, or with a handler in its body that swallows the exception. A test `test_quality.assertions.exempt` names with a reason is let through, an excuse whose test the gate does not fail is red, and a run that reads no test function fails. tests/unit/test_assertion_quality.py plants each fault in a temporary tree. Not a check_* letter: the letters A to Z are taken.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "tests"))

import assertion_quality as aq  # noqa: E402
import source_tree as st  # noqa: E402

pytestmark = pytest.mark.integration


def test_every_test_function_shows_it_can_fail():
    root = str(_ROOT)
    policy = aq.policy(root)
    count, findings = aq.scan(
        root,
        aq.test_files(root, policy.roots),
        policy.roots,
        policy.helper_depth,
        st.import_layers(root)["search_roots"],
    )
    failures = aq.verdict(count, findings, policy.exempt, policy.roots)
    assert failures == [], (
        "%d of %d test functions cannot show they fail; assert the observable "
        "result, or give the reason it has none in config/project.json %s:\n%s"
        % (len(failures), count, ".".join(aq.EXEMPT), "\n".join(failures))
    )
