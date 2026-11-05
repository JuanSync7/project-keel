"""
title: Unit — shared Markdown fence boundaries
summary: The shared scanner preserves line numbers, rejects backticks in a backtick opener's info string, and closes only on the same character, at least as long, with whitespace alone after it and at most three leading spaces. Simple list indentation works; container prefixes and deeper list indentation remain outside this line scanner.
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
        # Container parsing is a stated gap: CommonMark renders these as code,
        # while this scanner leaves their text visible to its callers.
        ("> ```\n> check_missing\n> ```", ["> ```", "> check_missing", "> ```"], 0),
        (
            "- item\n\n    ```\n    check_missing\n    ```",
            ["- item", "", "    ```", "    check_missing", "    ```"],
            0,
        ),
    ],
)
def test_commonmark_fence_boundaries_and_container_gaps(text, lines, opened):
    assert cs._fence_scan(text) == (lines, opened)
    assert cs._unfenced_lines(text) == lines
