"""
title: Integration — copier reproduces every scaffold.py artifact (no loss)
kind: tests
layer: n/a
summary: The scaffold-vs-copier parity gate — copier's generated file set covers every artifact scripts/scaffold.py emits. Content differences are expected (copier ships keel's CURRENT files; scaffold reconstructs from its own literals), so only a coverage GAP fails. This is the evidence that retiring scaffold.py loses nothing. Skipped when the optional copier dep is absent.
"""
import sys
from pathlib import Path

import pytest

pytest.importorskip("copier")  # optional 'template' extra — skip when absent

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import scaffold_parity  # noqa: E402

pytestmark = pytest.mark.integration


def test_copier_reproduces_every_scaffold_artifact():
    """Every path scaffold.py emits is reproduced by copier (react ∪ astro)."""
    r = scaffold_parity.compute_parity()
    assert r["gaps"] == [], (
        "copier is MISSING artifacts scaffold.py emits (a loss): %s" % r["gaps"])
    # copier ships at least everything scaffold does (usually more — keel's real tree).
    assert r["copier_files"] >= r["scaffold_files"]
