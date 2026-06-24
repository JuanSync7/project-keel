"""
title: Integration — agents are engine-agnostic
kind: tests
layer: backend
summary: index_enforcer / wiki_navigator produce identical dry-run results on inprocess and langgraph.
"""
import os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

pytestmark = pytest.mark.integration

# The LangGraph engine is an optional extra; without it there is nothing to
# compare against, so skip (the inprocess path is covered by the agents' own use).
pytest.importorskip("langgraph")

from agents.index_enforcer import enforce        # noqa: E402
from agents.wiki_navigator import answer          # noqa: E402


def test_index_enforcer_dry_run_identical_across_engines():
    # Dry-run: gate + report run (read-only, no corpus needed); build/link/fill
    # are skipped. The report is the same whichever engine walks the plan.
    a = enforce(execute=False, fix_gaps=True, runtime="inprocess")
    b = enforce(execute=False, fix_gaps=True, runtime="langgraph")
    assert a == b
    assert a.dry_run is True and a.gaps_filled == 0


def test_wiki_navigator_dry_run_identical_across_engines():
    if not os.path.isfile(_ROOT / "wiki" / "corpus.json"):
        pytest.skip("corpus not built; retrieval step needs wiki/corpus.json")
    q = "what are the conventions for frontmatter?"
    a = answer(q, execute=False, runtime="inprocess")
    b = answer(q, execute=False, runtime="langgraph")
    assert a == b
    assert a.dry_run is True
    assert a.text == b.text and a.citations == b.citations
