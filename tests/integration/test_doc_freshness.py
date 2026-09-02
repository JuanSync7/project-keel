"""
title: Integration — every governed document is stamped no earlier than its last commit
kind: tests
layer: n/a
summary: The freshness rule of scripts/review_docs.py as a gate: `updated:` is never earlier than the file's last commit, and a document modified in the working tree carries today's date. Not a check_* letter on purpose (ADR-0009): check_structure.py is stdlib-only and 3.6-safe and does not shell to git. Absent is not broken — no git, or not a repository, is a stated skip. Landed with every stamp normalised in the same commit, so the tree complied on arrival.
"""

import datetime
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import review_docs  # noqa: E402

pytestmark = pytest.mark.integration


def test_every_governed_document_is_fresh():
    """A stale `updated:` is a document lying about itself to every reader and
    to the corpus that ranks by recency (CONVENTIONS §1). The remedy is one
    line: set `updated:` to today in the change that touches the file."""
    records = review_docs.collect(str(_ROOT))
    if records is None:
        pytest.skip("no git repository -- freshness cannot be compared")
    stale = review_docs.stale_findings(records, datetime.date.today().isoformat())
    assert not stale, "%d stale document(s):\n%s" % (
        len(stale),
        "\n".join("  %s: %s" % (f["path"], f["reason"]) for f in stale),
    )
