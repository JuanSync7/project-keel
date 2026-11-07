"""
title: Unit — CommonMark HTML block tag registry
summary: Pins the complete, nonempty type-6 tag vocabulary against CommonMark 4.6 independently of the scanners.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

pytestmark = pytest.mark.unit


def test_type_six_tags_match_commonmark():
    import markdown_html_data

    expected = {
        "address",
        "article",
        "aside",
        "base",
        "basefont",
        "blockquote",
        "body",
        "caption",
        "center",
        "col",
        "colgroup",
        "dd",
        "details",
        "dialog",
        "dir",
        "div",
        "dl",
        "dt",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "frame",
        "frameset",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "head",
        "header",
        "hr",
        "html",
        "iframe",
        "legend",
        "li",
        "link",
        "main",
        "menu",
        "menuitem",
        "nav",
        "noframes",
        "ol",
        "optgroup",
        "option",
        "p",
        "param",
        "search",
        "section",
        "source",
        "summary",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "title",
        "tr",
        "track",
        "ul",
    }
    assert len(expected) == 63
    actual = markdown_html_data.HTML_BLOCK_TYPE_6_TAGS
    assert len(actual) == len(expected)
    assert set(actual) == expected
