"""
title: Unit — check_structure check_U (policy documents are reachable)
kind: tests
layer: n/a
summary: A practice whose enforcement IS a document is unenforceable if no agent ever reads that document. check_U holds every `doc:` mechanism in config/practices.json to one hop from the root AGENT.md, the file always in an agent's context: named there, or named in a document named there. Measured before the rule landed: python-style.md was named directly and coding-practices.md at one hop, while docs/guides/doc-style.md — the canonical statement of how documentation is written, cited by four practices — was reachable from nothing an agent reads automatically.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit

_S = "§"  # spelled as an escape: check_Q reads this file's source too


def _registry(*refs):
    return {
        "practices": [{"id": "p%d" % i, "enforced_by": [r]} for i, r in enumerate(refs)]
    }


def _find(registry, docs):
    return cs._policy_reachability_findings(registry, docs)


# --- reachability ---------------------------------------------------------------


def test_a_policy_named_directly_in_the_agent_rules_passes():
    docs = {
        "AGENT.md": "Write to `docs/guides/style.md`.\n",
        "docs/guides/style.md": "# S\n",
    }
    assert _find(_registry("doc:docs/guides/style.md"), docs) == []


def test_a_policy_named_one_hop_away_passes():
    """AGENT.md names python-style.md, which names its twin. An agent told to open
    the first is handed the second."""
    docs = {
        "AGENT.md": "Write Python to `docs/guides/python-style.md`.\n",
        "docs/guides/python-style.md": "Its twin is `docs/guides/doc-style.md`.\n",
        "docs/guides/doc-style.md": "# D\n",
    }
    assert _find(_registry("doc:docs/guides/doc-style.md"), docs) == []


def test_a_policy_two_hops_away_errors():
    """Two hops is not discoverable: nothing an agent reads by default leads there."""
    docs = {
        "AGENT.md": "See `docs/guides/a.md`.\n",
        "docs/guides/a.md": "See `docs/guides/b.md`.\n",
        "docs/guides/b.md": "See `docs/guides/c.md`.\n",
        "docs/guides/c.md": "# C\n",
    }
    errs = _find(_registry("doc:docs/guides/c.md"), docs)
    assert len(errs) == 1 and "docs/guides/c.md" in errs[0] and "AGENT.md" in errs[0], (
        errs
    )


def test_a_policy_nothing_names_errors_naming_the_practice_and_the_remedy():
    docs = {"AGENT.md": "Nothing here.\n", "docs/guides/doc-style.md": "# D\n"}
    errs = _find(_registry("doc:docs/guides/doc-style.md"), docs)
    assert len(errs) == 1
    assert "p0" in errs[0] and "docs/guides/doc-style.md" in errs[0] and "--" in errs[0]


def test_the_section_suffix_is_not_part_of_the_path():
    docs = {
        "AGENT.md": "Read `docs/guides/style.md`.\n",
        "docs/guides/style.md": "# S\n",
    }
    assert _find(_registry("doc:docs/guides/style.md " + _S + "4"), docs) == []


def test_every_unreachable_policy_is_reported_once_not_once_per_practice():
    """Four practices cite doc-style.md sections; the fix is one edit, so it is
    one finding."""
    docs = {"AGENT.md": "\n", "docs/guides/d.md": "# D\n"}
    reg = _registry(*["doc:docs/guides/d.md " + _S + str(n) for n in (2, 4, 5, 6)])
    errs = _find(reg, docs)
    assert len(errs) == 1 and "p0, p1, p2, p3" in errs[0], errs


# --- what counts as naming a document -------------------------------------------


def test_a_markdown_link_counts_as_a_reference():
    docs = {
        "AGENT.md": "See [the guide](docs/guides/style.md).\n",
        "docs/guides/style.md": "# S\n",
    }
    assert _find(_registry("doc:docs/guides/style.md"), docs) == []


def test_a_relative_link_from_a_guide_resolves_to_its_target():
    docs = {
        "AGENT.md": "Read `docs/guides/python-style.md`.\n",
        "docs/guides/python-style.md": "and [its twin](doc-style.md)\n",
        "docs/guides/doc-style.md": "# D\n",
    }
    assert _find(_registry("doc:docs/guides/doc-style.md"), docs) == []


def test_a_reference_inside_a_fenced_block_is_an_illustration_and_does_not_count():
    docs = {
        "AGENT.md": "```\nsee docs/guides/style.md\n```\n",
        "docs/guides/style.md": "# S\n",
    }
    errs = _find(_registry("doc:docs/guides/style.md"), docs)
    assert len(errs) == 1, errs


# --- what the check does not police ---------------------------------------------


@pytest.mark.parametrize(
    "ref",
    ["check:O", "script:scripts/x.py", "test:tests/x.py", "make:verify", "ruff:B904"],
)
def test_only_doc_mechanisms_are_held_to_reachability(ref):
    assert _find(_registry(ref), {"AGENT.md": "\n"}) == []


def test_a_policy_document_that_does_not_exist_is_check_ts_business_not_this_one():
    """check_T already errors on a doc: path that is not in the tree; reporting it
    twice would make one edit look like two defects."""
    assert _find(_registry("doc:docs/guides/gone.md"), {"AGENT.md": "\n"}) == []


# --- absent is not broken --------------------------------------------------------


def test_no_practices_registry_is_silent():
    assert _find({}, {"AGENT.md": "\n"}) == []


def test_no_agent_rules_file_is_silent():
    """A tree with no root AGENT.md has no always-in-context surface to hold
    anything to; check_I and check_B own that absence."""
    assert (
        _find(_registry("doc:docs/guides/style.md"), {"docs/guides/style.md": "# S\n"})
        == []
    )
