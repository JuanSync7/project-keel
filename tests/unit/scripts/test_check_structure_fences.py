"""
title: Unit — shared Markdown fence boundaries
summary: The shared scanner preserves line numbers, rejects backticks in a backtick opener's info string, and closes only on the same character, at least as long, with whitespace alone after it and at most three spaces past the container's content column. Containers follow CommonMark paragraph interruption; HTML blocks of types 1 to 5 hide every line they hold, complete inline comments are blanked within one paragraph, and fenced comments stay code.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "text, lines, opened",
    [
        (
            "``` check_missing ```\nUses check_other.",
            ["``` check_missing ```", "Uses check_other."],
            0,
        ),
        ("```markdown\n```python\ncheck_missing\n```", [""] * 4, 0),
        (
            "~~~~markdown\n~~~\n```\n~~~~ trailing\ncheck_missing\n~~~~ \t\nafter",
            [""] * 6 + ["after"],
            0,
        ),
        ("```\n~~~\n``\n``` trailing\ncheck_missing", [""] * 5, 1),
        # Only spaces and tabs may follow a closer; a no-break space may not.
        ("```\n```\u00a0\ncheck_missing\n```", [""] * 4, 0),
        (
            "   ```python\ncheck_missing\n    ```\n   ````\nafter",
            [""] * 4 + ["after"],
            0,
        ),
        ("    ```\ntext\n    ```", ["    ```", "text", "    ```"], 0),
        (
            "- item\n\n  ```\n  check_missing\n  ```\nafter",
            ["- item", ""] + [""] * 3 + ["after"],
            0,
        ),
        ("> ```\n> check_missing\n> ```", [""] * 3, 0),
        (
            "- item\n\n    ```\n    check_missing\n    ```",
            ["- item", ""] + [""] * 3,
            0,
        ),
    ],
)
def test_commonmark_fence_boundaries(text, lines, opened):
    assert cs._fence_scan(text) == (lines, opened)
    assert cs._unfenced_lines(text) == lines


@pytest.mark.parametrize(
    "text, lines, opened",
    [
        pytest.param(
            "- item\n\n  ```\n  code\nafter",
            ["- item", "", "", "", "after"],
            0,
            id="list-end",
        ),
        pytest.param(
            "   - item\n\n      ```\n      code\n      ```\nafter",
            ["   - item", "", "", "", "", "after"],
            0,
            id="marker-column",
        ),
        pytest.param(
            "- item\n1000. continuation\n     ```\n     code\n     ```\nafter",
            [
                "- item",
                "1000. continuation",
                "     ```",
                "     code",
                "     ```",
                "after",
            ],
            0,
            id="ordered-item-full-column",
        ),
        pytest.param(
            ">    ```\n> code\n> ```\nafter",
            ["", "", "", "after"],
            0,
            id="quote-closer-indent",
        ),
        pytest.param(
            "-     item\n     ```\n     code\n     ```\nafter",
            ["-     item", "", "", "", "after"],
            0,
            id="five-space-padding",
        ),
        pytest.param(
            "-\n     ```\n     code\n     ```\nafter",
            ["-", "", "", "", "after"],
            0,
            id="empty-first-line",
        ),
        pytest.param(
            "- item\nlazy continuation\n     ```\n     code\n     ```\nafter",
            ["- item", "lazy continuation", "", "", "", "after"],
            0,
            id="lazy-item-line",
        ),
        pytest.param(
            "- item\n  > ```\n  > code\n  > ```\nafter",
            ["- item", "", "", "", "after"],
            0,
            id="quote-in-list",
        ),
        pytest.param(
            "> - item\n>     ```\n>     code\n>     ```\nafter",
            ["> - item", "", "", "", "after"],
            0,
            id="list-in-quote",
        ),
        pytest.param("> ```\n> code\nafter", ["", "", "after"], 0, id="quote-end"),
        pytest.param(
            "```\n<!--\n```\nafter\n-->\nlast",
            ["", "", "", "after", "-->", "last"],
            0,
            id="comment-in-fence",
        ),
        pytest.param(
            "<pre>\n```\n</pre>\nafter", ["", "", "", "after"], 0, id="html-pre"
        ),
        pytest.param(
            "<?target\n```\n?>\nafter", ["", "", "", "after"], 0, id="html-pi"
        ),
        pytest.param(
            "<!DOCTYPE html\n```\n>\nafter",
            ["", "", "", "after"],
            0,
            id="html-declaration",
        ),
        pytest.param(
            "<!doctype html\n```\ncode\n>\nSee [x](missing.md)",
            ["", "", "", "", "See [x](missing.md)"],
            0,
            id="html-lowercase-declaration",
        ),
        pytest.param(
            "<![CDATA[\n```\n]]>\nafter", ["", "", "", "after"], 0, id="html-cdata"
        ),
    ],
)
def test_container_regressions(text, lines, opened):
    assert cs._fence_scan(text) == (lines, opened)
    assert cs._unfenced_lines(text) == lines


@pytest.mark.parametrize(
    "text, lines, opened",
    [
        pytest.param(
            "<!--\n```\n-->\nafter", ["", "", "", "after"], 0, id="comment-block"
        ),
        pytest.param(
            "paragraph <!--\nstill prose\nafter",
            ["paragraph <!--", "still prose", "after"],
            0,
            id="mid-paragraph-comment",
        ),
        pytest.param(
            "# Heading <!-- hidden --> title",
            ["# Heading  title"],
            0,
            id="inline-heading-comment",
        ),
        pytest.param(
            "<!É>\n~~~\ncode\n~~~\nafter",
            ["<!É>", "", "", "", "after"],
            0,
            id="non-ascii-declaration",
        ),
    ],
)
def test_preservation(text, lines, opened):
    assert cs._fence_scan(text) == (lines, opened)
    assert cs._unfenced_lines(text) == lines


@pytest.mark.parametrize(
    "text, lines, opened",
    [
        pytest.param(
            "- item\n\n  > ~~~\n  > code",
            ["- item", "", "", ""],
            3,
            id="unclosed-nested-line",
        ),
        pytest.param(
            "> paragraph\nlazy\n> ```\n> code\n> ```\nafter",
            ["> paragraph", "lazy", "", "", "", "after"],
            0,
            id="quote-lazy",
        ),
        pytest.param(
            "- paragraph\n-\n     ```\n     code\n     ```",
            ["- paragraph", "-", "", "", ""],
            0,
            id="empty-marker-lazy",
        ),
        pytest.param(
            "> paragraph\n# heading\n    ```\ncode",
            ["> paragraph", "# heading", "    ```", "code"],
            0,
            id="heading-ends-quote",
        ),
        pytest.param(
            "> paragraph\n---\n    ```\ncode",
            ["> paragraph", "---", "    ```", "code"],
            0,
            id="thematic-ends-quote",
        ),
        pytest.param(
            "> paragraph\n- item\n    ```\n    code\n    ```",
            ["> paragraph", "- item", "", "", ""],
            0,
            id="item-ends-quote",
        ),
        pytest.param(
            "> paragraph\n```\ncode\n```\nafter",
            ["> paragraph", "", "", "", "after"],
            0,
            id="fence-ends-quote",
        ),
        pytest.param(
            "> paragraph\n<pre>\n```\n</pre>\nafter",
            ["> paragraph", "", "", "", "after"],
            0,
            id="html-ends-quote",
        ),
        pytest.param(
            "- paragraph\n> ```\n> code\n> ```",
            ["- paragraph", "", "", ""],
            0,
            id="quote-ends-item",
        ),
        pytest.param(
            "- ```\n  code\n- prose\nafter",
            ["", "", "- prose", "after"],
            0,
            id="sibling-item",
        ),
        pytest.param(
            "- > ```\n  > code\n  prose\n  ```\n  code",
            ["", "", "  prose", "", ""],
            4,
            id="drop-inner-quote",
        ),
        pytest.param(
            "- item\n\n\t```\n\tcode\n\t```\nafter",
            ["- item", "", "", "", "", "after"],
            0,
            id="tab-columns",
        ),
        pytest.param(
            "  1.    item\n           ```\n           code\n           ```\nafter",
            ["  1.    item", "", "", "", "after"],
            0,
            id="padding-four",
        ),
        pytest.param(
            "<ScRiPt src=x>\n```\n</STYLE>\n<STYLE>\n~~~\n</pre>\n<textarea\n```\n</textarea>\nafter",
            ["", "", "", "", "", "", "", "", "", "after"],
            0,
            id="html-type-one-tags",
        ),
        pytest.param(
            "> <!--\n> ```\nprose\n- <?target\n  ~~~\nafter",
            ["", "", "prose", "", "", "after"],
            0,
            id="html-container-end",
        ),
        pytest.param(
            "<pre>\n<!--\n```\n</pre>\nafter",
            ["", "", "", "", "after"],
            0,
            id="html-does-not-nest",
        ),
        pytest.param(
            "<?target\n\n```\n?>\nafter",
            ["", "", "", "", "after"],
            0,
            id="html-blank-line",
        ),
        pytest.param(
            "   <![CDATA[\n```\n]]> prose\nafter",
            ["", "", "", "after"],
            0,
            id="html-marker-line",
        ),
        pytest.param(
            "<div>\n```\ncode\n```\nafter",
            ["<div>", "", "", "", "after"],
            0,
            id="type-six-gap",
        ),
        pytest.param(
            "<x>\n```\ncode\n```\nafter",
            ["<x>", "", "", "", "after"],
            0,
            id="type-seven-gap",
        ),
        pytest.param(
            "<prelude>\n```\ncode\n```\nafter",
            ["<prelude>", "", "", "", "after"],
            0,
            id="not-script-tag",
        ),
        pytest.param(
            "    <pre>\n```\ncode\n```\nafter",
            ["    <pre>", "", "", "", "after"],
            0,
            id="four-space-html",
        ),
        pytest.param(
            "-\n\n     ```\n     code\n     ```",
            ["-", "", "     ```", "     code", "     ```"],
            0,
            id="empty-item-blank",
        ),
    ],
)
def test_container_boundaries(text, lines, opened):
    assert cs._fence_scan(text) == (lines, opened)
    assert cs._unfenced_lines(text) == lines


@pytest.mark.parametrize(
    "text, lines",
    [
        pytest.param(
            "- item\n2. ```\n   check_missing\n   ```\nafter",
            ["- item", "", "", "", "after"],
            id="ordered-after-item",
        ),
        pytest.param(
            "> quote\n-\n  <?x\n  y\nafter check_other",
            ["> quote", "-", "", "", "after check_other"],
            id="empty-after-quote",
        ),
        pytest.param(
            "- item\n1000. continuation\n      ```\n      check_missing\n      ```\nafter",
            ["- item", "1000. continuation", "", "", "", "after"],
            id="wide-ordered-after-item",
        ),
        pytest.param(
            "> - item\n> 2. ```\n>    code\n>    ```\nafter",
            ["> - item", "", "", "", "after"],
            id="ordered-after-nested-item",
        ),
        pytest.param(
            "Title\n2. item\n    ```\n    code\n    ```",
            ["Title", "2. item", "    ```", "    code", "    ```"],
            id="ordered-in-root-paragraph",
        ),
        pytest.param(
            "Title\n+\n     ```\n     code\n     ```",
            ["Title", "+", "     ```", "     code", "     ```"],
            id="empty-in-root-paragraph",
        ),
    ],
)
def test_list_interruption_depends_on_continued_containers(text, lines):
    assert cs._fence_scan(text) == (lines, 0)


@pytest.mark.parametrize(
    "text, underline",
    [
        ("Title\n-\n2. ```\n   check_missing\n   ```", "-"),
        ("Title\n--\n2. ```\n   check_missing\n   ```", "--"),
        ("Title\n===\n2. ```\n   check_missing\n   ```", "==="),
    ],
)
def test_setext_underline_ends_paragraph(text, underline):
    assert cs._fence_scan(text) == (["Title", underline, "", "", ""], 0)


@pytest.mark.parametrize(
    "text, lines",
    [
        pytest.param(
            "Prose <!-- a hidden note\nsee [x](missing.md) check_missing\n--> more\nafter",
            ["Prose ", "", " more", "after"],
            id="paragraph-lines",
        ),
        pytest.param(
            "> Prose\nlazy <!-- hidden\nstill hidden\n--> more\nafter",
            ["> Prose", "lazy ", "", " more", "after"],
            id="lazy-line",
        ),
        pytest.param(
            "> Prose <!-- hidden\n\n--> more\nafter",
            ["> Prose <!-- hidden", "", "--> more", "after"],
            id="paragraph-and-container-end",
        ),
        pytest.param(
            "Prose <!-- x\n\nSee [x](missing.md).\n\n--> y",
            ["Prose <!-- x", "", "See [x](missing.md).", "", "--> y"],
            id="blank-line-end",
        ),
        pytest.param(
            "Prose <!-- x\n# See [x](missing.md).\n--> y",
            ["Prose <!-- x", "# See [x](missing.md).", "--> y"],
            id="heading-end",
        ),
        pytest.param(
            "Prose <!-- x\n```\ncode\n```\nSee [x](missing.md).\n--> y",
            ["Prose <!-- x", "", "", "", "See [x](missing.md).", "--> y"],
            id="fence-end",
        ),
        pytest.param(
            "> Prose <!-- x\n# See [x](missing.md).\n--> y",
            ["> Prose <!-- x", "# See [x](missing.md).", "--> y"],
            id="quote-end",
        ),
        pytest.param(
            "- Prose <!-- x\n- See [x](missing.md).\n  --> y",
            ["- Prose <!-- x", "- See [x](missing.md).", "  --> y"],
            id="list-item-end",
        ),
        pytest.param(
            "Prose <!-- x\n***\n--> y",
            ["Prose <!-- x", "***", "--> y"],
            id="thematic-end",
        ),
        pytest.param(
            "Prose <!-- x\n---\n--> y",
            ["Prose <!-- x", "---", "--> y"],
            id="setext-end",
        ),
        pytest.param(
            "Prose <!-- first\n--> middle <!-- second\n--> last",
            ["Prose ", " middle ", " last"],
            id="multiple-comments",
        ),
    ],
)
def test_inline_comments_span_lines(text, lines):
    assert cs._fence_scan(text) == (lines, 0)


@pytest.mark.parametrize(
    "text, lines",
    [
        pytest.param("<!-- c -->\n-", ["", "-"], id="html-end-on-start-line"),
        pytest.param(
            "<pre>\ncode\n</PRE>\nafter",
            ["", "", "", "after"],
            id="html-case-insensitive-end",
        ),
        pytest.param(
            "1234567890. ```\n            code\n            ```\nafter",
            ["1234567890. ```", "            code", "            ```", "after"],
            id="ten-digit-marker",
        ),
        pytest.param(
            "> text\n# heading\n> 2. ```\n>    code\n>    ```",
            ["> text", "# heading", "", "", ""],
            id="heading-interrupts",
        ),
        pytest.param(
            "> text\n***\n> 2. ```\n>    code\n>    ```",
            ["> text", "***", "", "", ""],
            id="thematic-interrupts",
        ),
        pytest.param(
            "text\n1. ```\n   code\n   ```",
            ["text", "", "", ""],
            id="ordered-one-interrupts",
        ),
        pytest.param(
            "- - -\n    ```\n    code\n    ```\nafter",
            ["- - -", "    ```", "    code", "    ```", "after"],
            id="thematic-before-list",
        ),
        pytest.param(
            "text\n    continuation\n2. item\n    ```\n    code\n    ```",
            ["text", "    continuation", "2. item", "    ```", "    code", "    ```"],
            id="indented-paragraph-continuation",
        ),
        pytest.param(
            "  - item\n   ```\n   code\n   ```\nafter",
            ["  - item", "", "", "", "after"],
            id="item-needs-full-column",
        ),
        pytest.param(
            "> text\n    # still paragraph\n> 2. item\n>     ```\n>     code\n>     ```",
            [
                "> text",
                "    # still paragraph",
                "> 2. item",
                ">     ```",
                ">     code",
                ">     ```",
            ],
            id="four-space-interruption-guard",
        ),
    ],
)
def test_commonmark_rule_families(text, lines):
    assert cs._fence_scan(text) == (lines, 0)


@pytest.mark.parametrize(
    "text, lines, opened",
    [
        pytest.param(
            "Title\n####### b\n2. ```\n   code\n   ```",
            ["Title", "####### b", "2. ```", "   code", ""],
            5,
            id="seven-hashes-is-paragraph",
        ),
        pytest.param(
            "    - ```\n      code\nafter",
            ["    - ```", "      code", "after"],
            0,
            id="four-space-marker-is-code",
        ),
        pytest.param(
            "-\n  a\n\n     ```\n     code\n     ```",
            ["-", "  a", "", "", "", ""],
            0,
            id="empty-first-line-clears",
        ),
        pytest.param(
            "    indented\n2. ```\n   code\n   ```",
            ["    indented", "", "", ""],
            0,
            id="indented-code-is-not-paragraph",
        ),
    ],
)
def test_uncovered_rule_families(text, lines, opened):
    assert cs._fence_scan(text) == (lines, opened)


@pytest.mark.parametrize(
    "text, lines, opened",
    [
        # CommonMark 0.31 §4.2: an ATX heading ends the preceding paragraph.
        pytest.param(
            "Prose <!-- a\n# H --> see [x](missing.md)\nafter",
            ["Prose <!-- a", "# H --> see [x](missing.md)", "after"],
            0,
            id="comment-heading-boundary",
        ),
        # CommonMark 0.31 §4.5: a backtick info string contains no backtick.
        pytest.param(
            "- a\n``` x`\n  b\n    ```\n    code",
            ["- a", "``` x`", "  b", "", ""],
            4,
            id="backtick-info-lazy-item",
        ),
        # CommonMark 0.31 §§4.6, 5.1: HTML ends paragraph laziness in a quote.
        pytest.param(
            "> a\n> <pre>\nfoo\n> ```\n> x",
            ["> a", "", "foo", "", ""],
            4,
            id="html-ends-quoted-paragraph",
        ),
        # CommonMark 0.31 §§4.5, 5.1: fences end paragraph laziness in a quote.
        pytest.param(
            "> a\n> ```\nfoo\n> x",
            ["> a", "", "foo", "> x"],
            0,
            id="fence-ends-quoted-paragraph",
        ),
        # CommonMark 0.31 §4.6: a type 1 start tag cannot be followed by /.
        pytest.param(
            "<pre/>\n```\ncode\n```\nafter",
            ["<pre/>", "", "", "", "after"],
            0,
            id="type-one-self-closing-tag",
        ),
        # CommonMark 0.31 §5.1: a quote marker has at most three spaces of indent.
        pytest.param(
            "    > ```\n    > code\n    > ```",
            ["    > ```", "    > code", "    > ```"],
            0,
            id="four-space-quote-is-code",
        ),
    ],
)
def test_paragraph_and_block_start_regressions(text, lines, opened):
    assert cs._fence_scan(text) == (lines, opened)
