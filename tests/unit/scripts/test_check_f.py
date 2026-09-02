"""
title: Unit — check_structure check_F (tool spec body contract)
kind: tests
layer: n/a
summary: check_F's body half, pinned: a `kind: tool` spec's body is the seven sections CONVENTIONS §10 names, in that order; its `## Side effects` opens with the word that matches `tool_effect` (READ-ONLY / WRITES / MODEL-CALL); and its `## When to use` carries at least one `- NOT` bullet — the negative-scope line that says what the tool is not for and names the sibling that is. Seven specs complied by discipline (six carried the NOT line); this makes the discipline a rule so the eighth cannot quietly skip it.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit

_BODY = """# query_corpus

## Command

`python scripts/query_corpus.py <q>`

## Purpose

Find nodes.

## When to use

- When an agent needs a node.
- NOT to build or mutate the corpus (that is `build_corpus`).

## Args

- `q` — the query.

## Output

JSON.

## Side effects

READ-ONLY. Reads the corpus; writes nothing.

## Used by

- agents/wiki_navigator
"""


def _find(text=_BODY, effect="read-only", path="agents/tools/query_corpus.tool.md"):
    return cs._tool_spec_body_findings(path, text, effect)


def test_a_conforming_spec_passes():
    assert _find() == []


@pytest.mark.parametrize(
    "section",
    ["Command", "Purpose", "When to use", "Args", "Output", "Side effects", "Used by"],
)
def test_a_missing_section_is_named(section):
    text = _BODY.replace("## %s\n" % section, "## Something else\n")
    errs = _find(text)
    assert len(errs) >= 1 and any(section in e for e in errs), errs


def test_sections_out_of_order_error():
    text = _BODY.replace(
        "## Purpose\n\nFind nodes.\n\n## When to use", "## When to use"
    ).replace("## Args", "## Purpose\n\nFind nodes.\n\n## Args")
    errs = _find(text)
    assert len(errs) == 1 and "order" in errs[0], errs


def test_an_extra_section_between_required_ones_is_allowed():
    text = _BODY.replace("## Args", "## Examples\n\nnone\n\n## Args")
    assert _find(text) == []


@pytest.mark.parametrize(
    "effect, word",
    [("read-only", "READ-ONLY"), ("writes", "WRITES"), ("model-call", "MODEL-CALL")],
)
def test_side_effects_must_open_with_the_word_for_the_declared_effect(effect, word):
    text = _BODY.replace("READ-ONLY. Reads", "%s. Reads" % word)
    assert _find(text, effect) == []


def test_side_effects_disagreeing_with_tool_effect_errors():
    """Frontmatter says writes, the body says READ-ONLY: an agent trusting either
    one is wrong half the time."""
    errs = _find(effect="writes")
    assert len(errs) == 1 and "WRITES" in errs[0] and "READ-ONLY" in errs[0], errs


def test_side_effects_opening_with_prose_errors():
    text = _BODY.replace("READ-ONLY. Reads the corpus", "It reads the corpus")
    errs = _find(text)
    assert len(errs) == 1 and "Side effects" in errs[0], errs


def test_a_when_to_use_without_a_not_line_errors():
    """The negative-scope line is the discriminator between siblings — the
    answer to 'why are these two separate tools?'. accountability_report was
    the one spec without it."""
    text = _BODY.replace(
        "- NOT to build or mutate the corpus (that is `build_corpus`).\n", ""
    )
    errs = _find(text)
    assert len(errs) == 1 and "NOT" in errs[0] and "When to use" in errs[0], errs


def test_a_not_line_in_another_section_does_not_count():
    text = _BODY.replace(
        "- NOT to build or mutate the corpus (that is `build_corpus`).\n", ""
    ).replace("JSON.\n", "JSON.\n\n- NOT a table.\n")
    errs = _find(text)
    assert len(errs) == 1 and "When to use" in errs[0], errs


def test_headings_inside_fenced_code_are_not_sections():
    text = _BODY.replace(
        "`python scripts/query_corpus.py <q>`", "```\n## Fake\npython x\n```"
    )
    assert _find(text) == []
