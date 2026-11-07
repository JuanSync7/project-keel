"""
title: Integration — every shipped document has a reachable index link
kind: tests
layer: n/a
summary: Walks Markdown links from the root README through READMEs and form: index documents using Copier's shipping matcher, counts twins once and fails on orphan documents or empty document, index or edge sets. Temporary trees prove disconnected cycles, prose, fenced links and leaf-only links cannot satisfy the contract. Reads the checkout and writes only pytest scratch.
"""

import posixpath
from pathlib import Path
from urllib.parse import unquote

import pytest
from test_doc_drift import (
    _TEMPLATE_ONLY,
    _git_listed,
    _unconditional_exclusions,
    cs,
)

_ROOT = Path(__file__).resolve().parents[2]
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not (_ROOT / "copier.yml").is_file(), reason=_TEMPLATE_ONLY),
]


def index_report(root, files=None):
    """Count the shipped graph and list documents unreachable through indexes."""
    from test_copier_shipping import _matcher

    files = _git_listed(root) if files is None else files
    assert files is not None, "cannot list shipped documents with git"
    excluded = _unconditional_exclusions(root)
    assert excluded is not None, "cannot derive shipping without copier.yml"
    match = _matcher(excluded)
    documents = {}
    for source in sorted(files):
        destination = source.removesuffix(".jinja")
        if not destination.endswith(".md") or match(destination):
            continue
        if not source.endswith(".jinja") and source + ".jinja" in files:
            continue
        documents[destination] = (root / source).read_text(encoding="utf-8")

    graph = {}
    for path, text in documents.items():
        frontmatter, _body = cs.split_frontmatter(text)
        if (
            Path(path).name != "README.md"
            and (frontmatter or {}).get("form") != "index"
        ):
            continue
        targets = set()
        for line in cs._prose_lines(text):
            for link in cs._MD_LINK.finditer(line):
                target = link.group(1) if link.group(1) is not None else link.group(2)
                if link.group().startswith("!") or cs._URL_SCHEME.match(target):
                    continue
                target = unquote(target.partition("#")[0])
                resolved = cs._resolve_link(posixpath.dirname(path), target)
                if resolved in documents:
                    targets.add(resolved)
        graph[path] = targets

    reached = set()
    pending = ["README.md"] if "README.md" in documents else []
    while pending:
        path = pending.pop()
        if path in reached:
            continue
        reached.add(path)
        pending.extend(graph.get(path, set()) - reached)
    return {
        "documents": len(documents),
        "indexes": len(graph),
        "edges": sum(len(targets) for targets in graph.values()),
        "orphans": sorted(documents.keys() - reached),
    }


def assert_indexed(root, files=None):
    """Print graph counts and fail on empty sets or unreachable documents."""
    report = index_report(root, files)
    print(  # noqa: T201 -- graph counts are the gate's requested evidence
        "documents={documents} indexes={indexes} edges={edges} orphans={orphans}".format(
            **{**report, "orphans": len(report["orphans"])}
        )
    )
    for key in ("documents", "indexes", "edges"):
        assert report[key] > 0, f"zero {key} in the shipped document graph"
    assert not report["orphans"], "orphan documents:\n" + "\n".join(report["orphans"])
    return report


def plant(root, documents):
    """Write a small document tree and return its source paths."""
    for path, text in documents.items():
        full = root / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(text, encoding="utf-8")
    return sorted(documents)


@pytest.fixture
def index_tree(tmp_path):
    plant(
        tmp_path,
        {
            "copier.yml": '_exclude: ["copier.yml", "docs/private/"]\n',
            "README.md": "[Docs](docs/README.md)\n",
            "docs/README.md": "[Guide](guide.md)\n",
            "docs/guide.md": "A guide.\n",
        },
    )
    return tmp_path


def source_paths(root):
    """List fixture files independently of git's checkout inventory."""
    return sorted(
        p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()
    )


@pytest.mark.parametrize("kind", ["doc", "adr", "spec"])
def test_linked_guides_adrs_and_specs_pass(index_tree, kind):
    plant(index_tree, {"docs/guide.md": f"---\nkind: {kind}\n---\nA document.\n"})
    report = assert_indexed(index_tree, source_paths(index_tree))
    assert report["orphans"] == []
    assert report["documents"] == 3


@pytest.mark.parametrize(
    "fault", ["orphan", "cycle", "prose", "fence", "inline", "comment", "image", "leaf"]
)
def test_unreachable_documents_fail_with_positive_counts(index_tree, fault):
    mutations = {
        "orphan": {"docs/orphan.md": "An unlisted document.\n"},
        "cycle": {
            "docs/a/README.md": "[B](../b/README.md)\n",
            "docs/b/README.md": "[A](../a/README.md)\n",
        },
        "prose": {"docs/README.md": "[Guide](guide.md)\nSee orphan.md.\n"},
        "fence": {
            "docs/README.md": "[Guide](guide.md)\n```md\n[Hidden](orphan.md)\n```\n"
        },
        "inline": {"docs/README.md": "[Guide](guide.md)\n`[Hidden](orphan.md)`\n"},
        "comment": {
            "docs/README.md": "[Guide](guide.md)\n<!--[Hidden](orphan.md)-->\n"
        },
        "image": {"docs/README.md": "[Guide](guide.md)\n![Hidden](orphan.md)\n"},
        "leaf": {"docs/guide.md": "[Hidden](orphan.md)\n"},
    }
    plant(
        index_tree,
        {
            "docs/orphan.md": "An unlisted document.\n",
            "docs/README.md": "[Guide](guide.md)\n[Listed](orphan.md)\n",
        },
    )
    assert_indexed(index_tree, source_paths(index_tree))
    (index_tree / "docs/README.md").write_text("[Guide](guide.md)\n", encoding="utf-8")
    plant(index_tree, mutations[fault])
    with pytest.raises(AssertionError, match="orphan"):
        assert_indexed(index_tree, source_paths(index_tree))
    report = index_report(index_tree, source_paths(index_tree))
    assert all(report[key] > 0 for key in ("documents", "indexes", "edges"))
    assert "docs/orphan.md" in report["orphans"]
    if fault == "cycle":
        assert {"docs/a/README.md", "docs/b/README.md"} <= set(report["orphans"])


def test_form_index_supplies_edges_and_leaf_frontmatter_does_not(index_tree):
    plant(
        index_tree,
        {
            "docs/README.md": "[Contents](contents.md)\n",
            "docs/contents.md": "---\nkind: doc\nform: index\n---\n[Guide](guide.md)\n",
        },
    )
    report = assert_indexed(index_tree, source_paths(index_tree))
    assert report["indexes"] == 3
    (index_tree / "docs/contents.md").write_text(
        "A leaf.\n```yaml\nform: index\n```\n[Guide](guide.md)\n", encoding="utf-8"
    )
    with pytest.raises(AssertionError, match="docs/guide.md"):
        assert_indexed(index_tree, source_paths(index_tree))


def test_twins_count_once_and_only_the_shipped_twin_supplies_edges(index_tree):
    plant(
        index_tree,
        {
            "docs/README.md": "This copy supplies no links.\n",
            "docs/README.md.jinja": "[Guide](guide.md)\n",
            "docs/guide.md.jinja": "A rendered guide.\n",
        },
    )
    report = assert_indexed(index_tree, source_paths(index_tree))
    assert report["documents"] == 3
    assert report["edges"] == 2
    (index_tree / "docs/README.md.jinja").write_text("No links.\n", encoding="utf-8")
    (index_tree / "docs/README.md").write_text("[Guide](guide.md)\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="docs/guide.md"):
        assert_indexed(index_tree, source_paths(index_tree))


@pytest.mark.parametrize("present", [False, True])
def test_exclusions_and_conditional_absence(index_tree, present):
    plant(
        index_tree,
        {
            "copier.yml": '_exclude: ["copier.yml", "docs/private/", "{% if omit %}optional.md{% endif %}"]\n',
            "docs/private/secret.md": "Excluded.\n",
            "docs/private/nested/README.md": "Excluded index.\n",
            "README.md": "[Docs](docs/README.md)\n[Optional](optional.md)\n",
        },
    )
    if present:
        plant(index_tree, {"optional.md": "Conditional document.\n"})
    report = assert_indexed(index_tree, source_paths(index_tree))
    assert report["documents"] == 3 + int(present)
    assert report["indexes"] == 2
    if present:
        (index_tree / "README.md").write_text(
            "[Docs](docs/README.md)\n", encoding="utf-8"
        )
        with pytest.raises(AssertionError, match="optional.md"):
            assert_indexed(index_tree, source_paths(index_tree))


@pytest.mark.parametrize(
    ("documents", "zero"),
    [
        ({}, "documents"),
        ({"leaf.md": "A leaf.\n"}, "indexes"),
        ({"README.md": "An empty index.\n"}, "edges"),
    ],
)
def test_empty_graph_counts_fail(tmp_path, documents, zero, capsys):
    files = plant(tmp_path, {"copier.yml": '_exclude: ["copier.yml"]\n', **documents})
    with pytest.raises(AssertionError, match=f"zero {zero}"):
        assert_indexed(tmp_path, files)
    output = capsys.readouterr().out
    assert all(
        f"{key}=" in output for key in ("documents", "indexes", "edges", "orphans")
    )


def test_every_shipped_document_is_reachable_from_the_root_readme():
    report = assert_indexed(_ROOT)
    assert report["orphans"] == []


def test_document_index_twin_links_survive_each_copier_answer_set():
    from test_copier_shipping import copier_rules, shipped_paths
    from test_reference_drift import _jinja, answer_sets, copier_questions

    files = _git_listed(_ROOT)
    assert files, "zero template sources"
    answers = answer_sets(copier_questions(_ROOT))
    assert answers, "zero Copier answer sets"
    template = _jinja().from_string(
        (_ROOT / "docs/README.md.jinja").read_text(encoding="utf-8")
    )
    rules = copier_rules(_ROOT)
    for answer in answers:
        rendered = template.render(**answer)
        shipped = shipped_paths(files, rules, answer)
        findings = cs._link_findings("docs/README.md", rendered, {}, shipped)
        assert not findings, f"{answer}:\n" + "\n".join(findings)
