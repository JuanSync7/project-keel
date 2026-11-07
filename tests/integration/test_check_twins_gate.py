"""
title: Integration — every structure check names a fault-injection twin
summary: Compare the closed check registry with source definitions and resolve pytest twins statically. Missing rows, stale rows, missing test functions, empty twins and zero judged rows fail with an id and a remedy. Parsing never imports or executes a twin.
"""

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration
_ROOT = Path(__file__).resolve().parents[2]


def _read_rows(root):
    path = root / "scripts/checks_data.py"
    assert path.is_file(), (
        "CHECK registry absent: add scripts/checks_data.py with ids and twins"
    )
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    values = [
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "CHECKS" for t in node.targets)
    ]
    assert len(values) == 1, (
        "CHECK registry: declare exactly one literal CHECKS registry"
    )
    return ast.literal_eval(values[0])


def _twin_exists(root, twin):
    parts = twin.split("::")
    path = Path(parts[0])
    if (
        len(parts) != 2
        or path.is_absolute()
        or ".." in path.parts
        or not path.parts
        or path.parts[0] != "tests"
        or not path.name.startswith("test_")
        or path.suffix != ".py"
        or not parts[1].startswith("test_")
    ):
        return False
    try:
        source = (root / path).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, UnicodeError, SyntaxError):  # noqa: DROP001 -- an unreadable twin fails resolution and is reported by the caller
        return False
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == parts[1]
        for node in tree.body
    )


def _findings(root, rows):
    tree = ast.parse((root / "scripts/check_structure.py").read_text(encoding="utf-8"))
    defined = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and re.fullmatch(r"check_[A-Z]+", node.name)
    }
    found = []
    if not rows:
        found.append("CHECK registry: zero rows judged; restore the check registry")
    seen_ids, seen_checks = set(), set()
    for row in rows:
        cid, check = row["id"], row["check"]
        if not re.fullmatch(r"CHECK-[A-Z]+", cid) or cid != check.replace(
            "check_", "CHECK-", 1
        ):
            found.append(
                "%s: invalid check id; match the check's dispatch letter" % cid
            )
        if cid in seen_ids or check in seen_checks:
            found.append("%s: duplicate registry row; keep one row per check" % cid)
        seen_ids.add(cid)
        seen_checks.add(check)
        if check not in defined:
            found.append(
                "%s: no such check %s; remove or repair the row" % (cid, check)
            )
        if not row["enforces"].strip() or "\n" in row["enforces"]:
            found.append(
                "%s: missing enforcement sentence; describe the rule in one line" % cid
            )
        if not _twin_exists(root, row["twin"]):
            found.append(
                "%s: twin %r does not resolve; name an existing fault-injection test"
                % (cid, row["twin"])
            )
    found.extend(
        "%s: no registry row; add its rule and fault-injection twin"
        % check.replace("check_", "CHECK-", 1)
        for check in sorted(defined - seen_checks)
    )
    return found


def test_every_structure_check_has_an_id_and_twin():
    rows = _read_rows(_ROOT)
    assert len(rows) > 0, "CHECK registry: zero rows judged; restore the registry"
    assert _findings(_ROOT, rows) == []


@pytest.fixture
def registry_tree(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/check_structure.py").write_text(
        "def check_A(): pass\ndef check_frontmatter(): pass\n", encoding="utf-8"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_fault.py").write_text(
        "raise RuntimeError('never execute twins')\ndef test_fault(): assert False\n",
        encoding="utf-8",
    )
    row = {
        "id": "CHECK-A",
        "check": "check_A",
        "enforces": "A rule.",
        "twin": "tests/test_fault.py::test_fault",
    }
    return tmp_path, [row]


def test_static_resolution_accepts_a_real_function_without_executing_it(registry_tree):
    root, rows = registry_tree
    assert len(rows) > 0
    assert _findings(root, rows) == []


@pytest.mark.parametrize(
    "fault, expected",
    [
        ("missing-row", "CHECK-B: no registry row"),
        ("stale-row", "CHECK-B: no such check"),
        ("missing-file", "CHECK-A: twin"),
        ("missing-function", "CHECK-A: twin"),
        ("nested-function", "CHECK-A: twin"),
        ("invalid-source", "CHECK-A: twin"),
        ("empty-twin", "CHECK-A: twin"),
        ("duplicate", "CHECK-A: duplicate"),
        ("empty-rule", "CHECK-A: missing enforcement"),
        ("bad-id", "other: invalid check id"),
        ("zero", "zero rows judged"),
    ],
)
def test_registry_fault_names_the_id_and_remedy(registry_tree, fault, expected):
    root, rows = registry_tree
    if fault == "missing-row":
        (root / "scripts/check_structure.py").write_text(
            "def check_A(): pass\ndef check_B(): pass\n"
        )
    elif fault == "stale-row":
        rows.append(dict(rows[0], id="CHECK-B", check="check_B"))
    elif fault == "missing-file":
        (root / "tests/test_fault.py").unlink()
    elif fault == "missing-function":
        rows[0]["twin"] = "tests/test_fault.py::test_absent"
    elif fault == "nested-function":
        (root / "tests/test_fault.py").write_text(
            "def helper():\n    def test_fault(): pass\n"
        )
    elif fault == "invalid-source":
        (root / "tests/test_fault.py").write_text("def test_fault(:\n")
    elif fault == "empty-twin":
        rows[0]["twin"] = ""
    elif fault == "duplicate":
        rows.append(dict(rows[0]))
    elif fault == "empty-rule":
        rows[0]["enforces"] = ""
    elif fault == "bad-id":
        rows[0]["id"] = "other"
    elif fault == "zero":
        rows.clear()
    found = _findings(root, rows)
    assert len(found) > 0
    assert any(expected in message and ";" in message for message in found), found
