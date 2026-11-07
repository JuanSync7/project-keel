"""
title: Unit — the closed check registry is declared data
summary: The registry has at least one row, unique ids and check names, and a nonempty one-line enforcement claim and twin per row.
"""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
_ROOT = Path(__file__).resolve().parents[3]


def test_check_registry_is_nonempty_literal_data():
    path = _ROOT / "scripts/checks_data.py"
    assert path.is_file(), "CHECK registry absent: declare scripts/checks_data.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    rows = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "CHECKS" for t in node.targets)
    )
    assert len(rows) > 0
    assert len({row["id"] for row in rows}) == len(rows)
    assert len({row["check"] for row in rows}) == len(rows)
    for row in rows:
        assert set(row) == {"id", "check", "enforces", "twin"}
        assert all(isinstance(value, str) and value.strip() for value in row.values())
        assert "\n" not in row["enforces"]
