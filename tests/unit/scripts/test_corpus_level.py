"""
title: Unit — the level a file states on disk, read the corpus build's way
kind: tests
layer: n/a
summary: scripts/corpus_level.py `stated_now` reads a Markdown file's frontmatter or a Python module's docstring again and returns its own level followed by each README.md's on its chain, the list build_corpus ranks; it returns None, never a level, for no path, a missing file, bytes that are not UTF-8, a Markdown file with no frontmatter, a module that does not parse or has no docstring, and any other kind of file. A README that cannot be read passes on UNREADABLE_VISIBILITY. A symlinked doc also takes the README.md chain of the directory it really is in, so it is not served once that README turns confidential, and a doc and a README.md saved with a UTF-8 byte-order mark state their levels. build_corpus gives a node config_loader.chain_level of the same list, so the build and a reader that checks a file now cannot disagree on a file's level.
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


_SERVED = frozenset({"public", "internal"})


def test_a_symlinked_doc_takes_its_real_directorys_readme_too(tmp_path):
    """A doc reached by a symlink in an open directory is ranked by the
    README.md chain of the directory it really is in as well, so it stops
    being served once that README turns confidential."""
    _write(tmp_path, "open/README.md", "---\ntitle: O\nvisibility: public\n---\n")
    _write(tmp_path, "secret/README.md", "---\ntitle: S\nvisibility: public\n---\n")
    _write(tmp_path, "secret/real.md", "---\ntitle: R\nvisibility: public\n---\n")
    (tmp_path / "open" / "link.md").symlink_to(tmp_path / "secret" / "real.md")
    node = {"visibility": "public"}

    def now():
        return corpus_level.stated_now(str(tmp_path), "open/link.md")

    assert now() == ["public", "public", "public"]
    assert config_loader.is_served_now(node, _SERVED, now())
    _write(
        tmp_path, "secret/README.md", "---\ntitle: S\nvisibility: confidential\n---\n"
    )
    assert now() == ["public", "public", "confidential"]
    assert not config_loader.is_served_now(node, _SERVED, now())


def test_a_file_saved_with_a_byte_order_mark_states_its_level(tmp_path):
    """A doc and a README.md saved with a UTF-8 BOM state their levels, as the
    corpus build reads them, rather than being read as having none."""
    bom = "﻿"
    _write(
        tmp_path, "docs/README.md", bom + "---\ntitle: D\nvisibility: restricted\n---\n"
    )
    _write(tmp_path, "docs/a.md", bom + "---\ntitle: A\nvisibility: public\n---\n# A\n")
    assert corpus_level.stated_now(str(tmp_path), "docs/a.md") == [
        "public",
        "restricted",
    ]


# ---- a corpus and the checkout its files are read in -----------------------


def test_a_root_gives_its_own_corpus_and_a_corpus_its_own_checkout(
    tmp_path, monkeypatch
):
    """The one is derived from the other, absolute, a relative one taken from
    the caller's directory; neither given is the default checkout's corpus."""
    monkeypatch.chdir(tmp_path)
    own = str(tmp_path / "b" / "wiki" / "corpus.json")
    (tmp_path / "b" / "wiki").mkdir(parents=True)
    Path(own).write_text("{}")
    assert corpus_level.checkout("b", None, "/x") == (str(tmp_path / "b"), own)
    assert corpus_level.checkout(None, "b/wiki/corpus.json", "/x") == (
        str(tmp_path / "b"),
        own,
    )
    assert corpus_level.checkout(None, None, str(tmp_path / "b")) == (
        str(tmp_path / "b"),
        own,
    )
    assert corpus_level.CORPUS_PATH == "wiki/corpus.json"


@pytest.mark.parametrize(
    "corpus",
    ["corpus.json", "b/corpus.json", "b/wiki/other.json", "b/docs/corpus.json"],
)
def test_a_corpus_outside_a_checkouts_wiki_is_refused(tmp_path, monkeypatch, corpus):
    """A corpus is read only where a checkout keeps it, so one anywhere else
    has no checkout to read its files in and is refused, naming the path and
    where a corpus lives."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(corpus_level.NotACheckout) as raised:
        corpus_level.checkout(None, corpus, "/x")
    what, on, next_step = raised.value.parts
    assert on == str(tmp_path / corpus)
    assert "wiki/corpus.json" in next_step
    assert isinstance(raised.value, ValueError)


def test_a_named_corpus_that_does_not_exist_is_refused(tmp_path, monkeypatch):
    """A corpus named in a folder that keeps none would answer from nothing
    with no sign, so it is refused, naming the path and how to build it; a
    root with no corpus yet still names its own."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "d").mkdir()
    with pytest.raises(corpus_level.NotACheckout) as raised:
        corpus_level.checkout(None, "d/wiki/corpus.json", "/x")
    what, on, next_step = raised.value.parts
    assert on == str(tmp_path / "d" / "wiki" / "corpus.json")
    assert "make site-data" in next_step
    assert corpus_level.checkout("d", None, "/x") == (
        str(tmp_path / "d"),
        str(tmp_path / "d" / "wiki" / "corpus.json"),
    )


def test_a_root_and_a_corpus_given_together_are_refused(tmp_path):
    """Two independent choices could pair one checkout's corpus with another's
    files, so a caller names one and the other is derived."""
    with pytest.raises(corpus_level.NotACheckout) as raised:
        corpus_level.checkout(
            str(tmp_path / "a"), str(tmp_path / "a" / "wiki" / "corpus.json"), "/x"
        )
    assert "not both" in str(raised.value)
