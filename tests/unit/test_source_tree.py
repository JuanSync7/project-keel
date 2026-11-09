"""
title: Unit — project imports require Python tree evidence
kind: tests
layer: n/a
summary: A directory name alone does not own an installed import; modules, regular packages and directories holding project Python files own unresolved imports. Unreadable directory evidence raises a named refusal.
"""

import os

import pytest

import source_tree as st

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("head", ["mcp", "docs"])
@pytest.mark.parametrize(
    "statement", ["import {head}.types", "from {head}.types import Item"]
)
def test_directory_alone_does_not_own_an_external_import(tmp_path, head, statement):
    (tmp_path / head).mkdir()
    (tmp_path / "caller.py").write_text(statement.format(head=head), encoding="utf-8")
    assert st.unresolved_imports(tmp_path, ["caller.py"], [""]) == []
    assert st.import_edges(tmp_path, ["caller.py"], [""]) == []


@pytest.mark.parametrize("head", ["mcp", "docs"])
def test_a_regular_package_owns_a_missing_import(tmp_path, head):
    (tmp_path / head).mkdir()
    (tmp_path / head / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "caller.py").write_text(
        f"from {head}.missing import Item", encoding="utf-8"
    )
    assert st.unresolved_imports(tmp_path, ["caller.py"], [""]) == [
        ("caller.py", 1, f"{head}.missing.Item")
    ]


@pytest.mark.parametrize("head", ["mcp", "docs"])
def test_a_resolved_namespace_module_is_a_project_import(tmp_path, head):
    (tmp_path / head).mkdir()
    (tmp_path / head / "local.py").write_text("", encoding="utf-8")
    (tmp_path / "caller.py").write_text(f"import {head}.local", encoding="utf-8")
    assert st.import_edges(tmp_path, ["caller.py"], [""]) == [
        ("caller.py", 1, f"{head}/local.py")
    ]
    assert st.unresolved_imports(tmp_path, ["caller.py"], [""]) == []


@pytest.mark.parametrize("sibling", ["sibling.py", "nested/sibling.py"])
@pytest.mark.parametrize("importer", ["caller.py", "scripts/a.py"])
def test_a_namespace_directory_owns_missing_submodules(tmp_path, sibling, importer):
    head = tmp_path / "scripts"
    (head / sibling).parent.mkdir(parents=True)
    (head / sibling).write_text("", encoding="utf-8")
    (tmp_path / importer).write_text(
        "from scripts import gone\nimport scripts.gone2\n", encoding="utf-8"
    )
    assert st.unresolved_imports(tmp_path, [importer], ["", "scripts/"]) == [
        (importer, 1, "scripts.gone"),
        (importer, 2, "scripts.gone2"),
    ]


def test_a_docs_only_directory_does_not_own_an_external_import(tmp_path):
    (tmp_path / "docs" / "guides").mkdir(parents=True)
    (tmp_path / "docs" / "guides" / "intro.md").write_text("Guide", encoding="utf-8")
    (tmp_path / "caller.py").write_text("import docs.external", encoding="utf-8")
    assert st.unresolved_imports(tmp_path, ["caller.py"], [""]) == []
    assert st.import_edges(tmp_path, ["caller.py"], [""]) == []


def test_unreadable_directory_evidence_refuses_naming_the_head(tmp_path, monkeypatch):
    head = tmp_path / "scripts"
    head.mkdir()
    (tmp_path / "caller.py").write_text("import scripts.gone", encoding="utf-8")
    scandir = os.scandir

    def unreadable(path):
        if os.fspath(path) == str(head):
            raise PermissionError(13, "cannot scan", str(head))
        return scandir(path)

    monkeypatch.setattr(os, "scandir", unreadable)
    with pytest.raises(st.SourceTreeError, match=r"scripts.*cannot classify"):
        st.unresolved_imports(tmp_path, ["caller.py"], [""])
