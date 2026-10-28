"""
title: Unit — the level a file states on disk, read the corpus build's way
kind: tests
layer: n/a
summary: scripts/corpus_level.py `stated_now` reads a Markdown file's frontmatter or a Python module's docstring again and returns its own level followed by each README.md's on its chain, the list build_corpus ranks; it returns None, never a level, for no path, a missing file, bytes that are not UTF-8, a Markdown file with no frontmatter, a module that does not parse or has no docstring, and any other kind of file. A README that cannot be read passes on UNREADABLE_VISIBILITY. build_corpus gives a node config_loader.chain_level of the same list, so the build and a reader that reads from disk cannot disagree on a file's level.
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))

import build_corpus  # noqa: E402
import config_loader  # noqa: E402
import corpus_level  # noqa: E402

pytestmark = pytest.mark.unit


def _write(root, rel, text):
    f = root / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text, encoding="utf-8")


def test_a_doc_states_its_own_level_then_each_readme_upward(tmp_path):
    _write(tmp_path, "README.md", "---\ntitle: R\nvisibility: internal\n---\n")
    _write(tmp_path, "docs/README.md", "---\ntitle: D\n---\n")
    _write(tmp_path, "docs/a.md", "---\ntitle: A\nvisibility: public\n---\n# A\n")
    assert corpus_level.stated_now(str(tmp_path), "docs/a.md") == [
        "public",
        None,
        "internal",
    ]


def test_a_module_states_its_level_in_its_docstring(tmp_path):
    _write(tmp_path, "src/m.py", '"""\ntitle: M\nvisibility: restricted\n"""\n')
    assert corpus_level.stated_now(str(tmp_path), "src/m.py") == ["restricted"]


def test_an_unreadable_readme_passes_on_the_marker(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "README.md").write_bytes(b"---\n\xff\n")
    _write(tmp_path, "docs/a.md", "---\ntitle: A\nvisibility: public\n---\n")
    got = corpus_level.stated_now(str(tmp_path), "docs/a.md")
    assert got == ["public", corpus_level.UNREADABLE_VISIBILITY]


@pytest.mark.parametrize(
    "rel, data",
    [
        ("", None),
        ("docs/gone.md", None),
        ("docs/a.md", b"---\ntitle: A\n---\n\xff\xfe"),
        ("docs/a.md", b"# A, no frontmatter\n"),
        ("src/m.py", b"def broken(:\n"),
        ("src/m.py", b"x = 1\n"),
        ("src/m.py", b'"""a\x00b"""\n'),
        ("data/a.json", b'{"visibility": "public"}\n'),
    ],
    ids=[
        "no-path",
        "missing",
        "not-utf8",
        "no-frontmatter",
        "syntax-error",
        "no-docstring",
        "nul-byte",
        "other-kind",
    ],
)
def test_no_level_that_can_be_read_is_none_never_a_level(tmp_path, rel, data):
    if data is not None:
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)
    assert corpus_level.stated_now(str(tmp_path), rel) is None


def test_the_build_and_the_disk_reader_agree_on_each_level(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.json").write_text(json.dumps({}))
    _write(tmp_path, "docs/README.md", "---\ntitle: D\nvisibility: confidential\n---\n")
    _write(
        tmp_path, "docs/a.md", "---\ntitle: A\nid: a\nvisibility: public\n---\n# A\n"
    )
    _write(
        tmp_path, "src/m.py", '"""\ntitle: M\nsummary: s.\nvisibility: public\n"""\n'
    )
    nodes = build_corpus.build_corpus(str(tmp_path))["nodes"]
    for path in ("docs/a.md", "src/m.py"):
        built = {n["visibility"] for n in nodes if n.get("path") == path}
        now = config_loader.chain_level(corpus_level.stated_now(str(tmp_path), path))
        assert built == {now}, path
