"""
title: Unit — check_structure check_Q (cross-references resolve)
kind: tests
layer: n/a
summary: check_Q errors when a document's outbound reference names nothing — a relative Markdown link (file, directory, or `#anchor`) whose target does not exist, or a `§N` section citation that no numbered heading answers. The tree resolves today (58 links, 120 citations, none dead), so this is a regression barrier for the one edit that silently rots a knowledge graph — renumbering CONVENTIONS.md or moving a doc — and for a generated project, whose pruned tree must not inherit a link to a file it was never given. Links inside fenced or inline code are syntax illustrations, not references, and are not checked.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit

# The section sign, spelled as an escape: check_Q reads this file's SOURCE too,
# and a literal sign inside a fixture would be a citation the real tree must answer.
_S = "\u00a7"

_CONVENTIONS = "# Conventions\n\n## 1. Frontmatter\n\ntext\n\n## 2. Taxonomy\n\ntext\n"


def _tree_of(files):
    """Every path a walk would see: the files plus each ancestor directory."""
    tree = set()
    for relpath in files:
        tree.add(relpath)
        parts = relpath.split("/")
        for i in range(1, len(parts)):
            tree.add("/".join(parts[:i]))
    return tree


def _find(files, extra_paths=()):
    """files: {relpath: text}. extra_paths: non-text entries (dirs, binaries) the
    tree also holds. -> check_Q's error strings."""
    return cs._crossref_findings(files, _tree_of(files) | set(extra_paths))


# --- relative links -----------------------------------------------------------


def test_a_link_to_an_existing_sibling_passes():
    assert _find({"docs/a.md": "see [b](b.md)\n", "docs/b.md": "# B\n"}) == []


def test_a_link_to_a_missing_file_errors_with_the_resolved_path():
    errs = _find({"docs/a.md": "see [b](../guides/b.md)\n"})
    assert len(errs) == 1, errs
    assert "docs/a.md:1" in errs[0] and "../guides/b.md" in errs[0]
    assert (
        "guides/b.md" in errs[0]
    )  # the resolved path, so the reader need not compute it


def test_a_link_to_a_directory_passes_when_the_directory_exists():
    files = {"docs/a.md": "see [pkg](../src/backend/pkg/)\n"}
    assert _find(files, extra_paths={"src", "src/backend", "src/backend/pkg"}) == []


def test_a_root_relative_link_resolves_from_the_repository_root():
    assert (
        _find({"docs/deep/a.md": "[c](/CONVENTIONS.md)\n", "CONVENTIONS.md": "x\n"})
        == []
    )


def test_a_link_that_escapes_the_repository_errors():
    errs = _find({"a.md": "[x](../../etc/passwd)\n"})
    assert len(errs) == 1 and "escapes" in errs[0], errs


def test_an_image_link_is_a_link():
    errs = _find({"a.md": "![diagram](img/arch.png)\n"})
    assert len(errs) == 1 and "img/arch.png" in errs[0], errs


def test_a_link_title_and_angle_brackets_are_not_part_of_the_target():
    files = {"a.md": '[b](<b.md> "the B doc")\n', "b.md": "x\n"}
    assert _find(files) == []


@pytest.mark.parametrize(
    "target",
    ["https://example.org/x.md", "http://h/", "mailto:a@b.c", "ftp://h/f"],
)
def test_urls_are_not_relative_links(target):
    assert _find({"a.md": "[x](%s)\n" % target}) == []


def test_every_dead_link_is_reported_with_its_own_line():
    errs = _find({"a.md": "[x](one.md)\n\n[y](two.md)\n"})
    assert sorted(e.split(":")[1] for e in errs) == ["1", "3"]


# --- anchors -----------------------------------------------------------------


def test_an_anchor_to_a_heading_in_the_target_passes():
    files = {
        "a.md": "[b](b.md#the-second-part)\n",
        "b.md": "# B\n\n## The second part\n",
    }
    assert _find(files) == []


def test_an_anchor_to_a_missing_heading_errors():
    errs = _find({"a.md": "[b](b.md#nope)\n", "b.md": "# B\n"})
    assert len(errs) == 1 and "#nope" in errs[0] and "b.md" in errs[0], errs


def test_a_same_document_anchor_resolves_against_its_own_headings():
    assert _find({"a.md": "## Setup\n\n[up](#setup)\n"}) == []
    errs = _find({"a.md": "## Setup\n\n[up](#teardown)\n"})
    assert len(errs) == 1 and "#teardown" in errs[0], errs


@pytest.mark.parametrize(
    "heading, anchor",
    [
        ("## [Unreleased]", "unreleased"),
        ("## [0.1.0] — 2026-09-02", "010--2026-09-02"),
        (
            "## The `__init__.py` boundary rule (the important one)",
            "the-__init__py-boundary-rule-the-important-one",
        ),
        ("## 3. Triggers vs doers", "3-triggers-vs-doers"),
        ("## Closing hashes ##", "closing-hashes"),
    ],
)
def test_anchors_follow_the_renderers_slug_rule(heading, anchor):
    """GitHub's rule: lowercase, drop everything but word characters, spaces and
    hyphens, then spaces become hyphens. Backticks and brackets vanish."""
    assert cs._heading_slug(heading) == anchor


def test_duplicate_headings_get_numbered_anchors():
    files = {"a.md": "[x](b.md#notes-1)\n", "b.md": "## Notes\n\n## Notes\n"}
    assert _find(files) == []


def test_a_heading_inside_a_code_fence_is_not_an_anchor():
    files = {"a.md": "[x](b.md#fake)\n", "b.md": "```\n## Fake\n```\n"}
    errs = _find(files)
    assert len(errs) == 1 and "#fake" in errs[0], errs


# --- what is NOT a reference -------------------------------------------------


def test_a_link_inside_a_fenced_code_block_is_an_illustration():
    files = {"a.md": "```md\n[x](nowhere.md)\n```\n\n~~~\n[y](nowhere.md)\n~~~\n"}
    assert _find(files) == []


def test_a_link_inside_an_inline_code_span_is_an_illustration():
    assert _find({"a.md": "write `[text](path.md)` to link\n"}) == []


def test_link_text_that_is_itself_code_still_leaves_the_target_checked():
    """`[`b.md`](b.md)` is the house style for a path link: the span is the
    text, the target is outside it and must resolve."""
    errs = _find({"a.md": "[`b.md`](b.md)\n"})
    assert len(errs) == 1 and "b.md" in errs[0], errs


def test_jinja_twins_are_not_scanned_for_links():
    """A twin's rendered links are the generation tests' business; unrendered
    `{% if %}` blocks around a pruned doc are not dead links."""
    assert _find({"README.md.jinja": "{% if x %}[g](docs/g.md){% endif %}\n"}) == []


# --- section citations ---------------------------------------------------------


def test_a_section_citation_that_conventions_answers_passes():
    files = {
        "CONVENTIONS.md": _CONVENTIONS,
        "docs/a.md": "see CONVENTIONS " + _S + "2 and (" + _S + "1)\n",
    }
    assert _find(files) == []


def test_a_section_citation_nothing_answers_errors_naming_what_exists():
    files = {"CONVENTIONS.md": _CONVENTIONS, "docs/a.md": "see " + _S + "7\n"}
    errs = _find(files)
    assert len(errs) == 1, errs
    assert "docs/a.md:1" in errs[0] and _S + "7" in errs[0] and "1, 2" in errs[0]


def test_citations_are_checked_in_code_and_config_not_only_prose():
    """A section citation in a docstring or a Makefile help string rots exactly as one in
    a guide does — and check_structure's own docstring cites sections."""
    files = {
        "CONVENTIONS.md": _CONVENTIONS,
        "src/a.py": '"""\ntitle: x\nsummary: y (' + _S + '9)\n"""\n',
        "Makefile": "advise: ## smells (CONVENTIONS " + _S + "8)\n",
        "config/x.example.yaml": "# " + _S + "2 is fine\n",
    }
    errs = _find(files)
    assert sorted(e.split(":")[0] for e in errs) == ["Makefile", "src/a.py"], errs


def test_a_citation_naming_another_document_resolves_against_that_document():
    files = {
        "CONVENTIONS.md": _CONVENTIONS,
        "docs/style.md": "## 1. Names\n\n## 2. Layout\n\n## 3. Errors\n",
        "docs/a.md": "as docs/style.md " + _S + "3 says\n",
    }
    assert _find(files) == []
    files["docs/a.md"] = "as docs/style.md " + _S + "4 says\n"
    errs = _find(files)
    assert len(errs) == 1 and "docs/style.md" in errs[0] and _S + "4" in errs[0], errs


def test_conventions_own_citations_resolve_against_itself():
    conv = _CONVENTIONS + "\nsee " + _S + "1 above and " + _S + "2\n"
    assert _find({"CONVENTIONS.md": conv}) == []


def test_a_citation_with_no_conventions_file_at_all_errors():
    """Absent is not silent here: a citation TO a file is broken when the file
    is gone, and CONVENTIONS.md ships verbatim into every generated project."""
    errs = _find({"docs/a.md": "see " + _S + "2\n"})
    assert len(errs) == 1 and "CONVENTIONS.md" in errs[0], errs


def test_a_section_sign_without_a_number_is_prose():
    files = {
        "CONVENTIONS.md": _CONVENTIONS,
        "docs/a.md": "write `" + _S + "N` after the rule\n",
    }
    assert _find(files) == []


def test_a_bare_tree_with_no_references_is_silent():
    assert _find({"README.md": "hello\n", "src/a.py": "X = 1\n"}) == []
