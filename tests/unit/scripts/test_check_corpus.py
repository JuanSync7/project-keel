"""
title: Unit — check_corpus gates the LOCAL corpus (absent vs stale vs enriched)
kind: tests
layer: n/a
summary: wiki/corpus.json is the gitignored world-model the corpus agents actually query, and until ADR-0008 nothing gated it — the default check built FRESH and never looked at the on-disk file, so it could rot silently (measured 33 nodes behind the tree at a green gate). Now absent is a loud exit 0 (a fresh clone, CI, and a day-one generated project have none — the ADR-0007 absent-vs-drifted split), present-but-stale is exit 1 naming make site-data, and staleness is judged on the DETERMINISTIC PROJECTION so index_enforcer's "generated" summaries and links are enrichment, not rot. A structurally invalid local corpus fails regardless.
"""

import ast
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))

import check_corpus as cc  # noqa: E402
import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit

_MOD = (
    '"""\ntitle: Thing\nsummary: Does things.\n"""\n'
    '__all__ = ["thing"]\n\n\n'
    'def thing():\n    """Return the thing."""\n    return 1\n'
)

# A frontmatter-bearing markdown doc gives the corpus a SECTION node whose
# deterministic summary is empty — the honest target for a "generated" fill.
_DOC = (
    "---\n"
    "title: Guide\n"
    "kind: doc\n"
    "layer: n/a\n"
    "status: stable\n"
    "owner: someone\n"
    "tags: [x]\n"
    "summary: A guide.\n"
    "id: guide\n"
    "created: 2026-01-01\n"
    "updated: 2026-01-01\n"
    "visibility: internal\n"
    "canonical: true\n"
    "---\n"
    "# Guide\n\nProse.\n\n## Part one\n\nMore prose about things.\n\n## Part two\n"
)


@pytest.fixture()
def repo(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "thing.py").write_text(_MOD, encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text(_DOC, encoding="utf-8")
    return tmp_path


def _write_local(root, corpus):
    (root / "wiki").mkdir(exist_ok=True)
    (root / "wiki" / "corpus.json").write_text(cc._dumps(corpus), encoding="utf-8")


def test_absent_local_corpus_is_green_and_loud(repo, capsys):
    """A fresh clone / CI / day-one generated project has no wiki/corpus.json
    (gitignored generated view). That is a real state, not a drift — but it must
    be SAID, or 'no corpus' reads as 'corpus fine'."""
    assert cc.main(["--root", str(repo)]) == 0
    streams = capsys.readouterr()
    assert "make site-data" in streams.out + streams.err


def test_fresh_local_corpus_is_green(repo):
    _write_local(repo, cc._fresh(str(repo), 8))
    assert cc.main(["--root", str(repo)]) == 0


def test_stale_local_corpus_fails_naming_the_fix(repo, capsys):
    """The measured defect: the tree moved on, the corpus agents query did not,
    and the gate stayed green. Now it is an ERROR that names the repair."""
    _write_local(repo, cc._fresh(str(repo), 8))
    (repo / "src" / "later.py").write_text(
        _MOD.replace("Thing", "Later").replace("thing", "later"), encoding="utf-8"
    )
    assert cc.main(["--root", str(repo)]) == 1
    assert "make site-data" in capsys.readouterr().err


def test_generated_enrichment_is_not_staleness(repo):
    """index_enforcer legitimately fills empty summaries (summary_source
    'generated') and semantic links may carry source 'generated'. Enrichment is
    the corpus getting BETTER; only the deterministic projection may drift."""
    corpus = cc._fresh(str(repo), 8)
    nodes = corpus["nodes"]
    section = next(
        n for n in nodes if n["kind"] == "section" and n["summary_source"] == ""
    )
    section["summary"] = "an LLM wrote this"
    section["summary_source"] = "generated"
    module = next(n for n in nodes if n["kind"] == "module")
    module["links"] = list(module.get("links", [])) + [
        {
            "to": section["node_id"],
            "via": "llm",
            "score": 0.9,
            "kind": "semantic",
            "source": "generated",
        }
    ]
    _write_local(repo, corpus)
    assert cc.main(["--root", str(repo)]) == 0


def test_rotten_local_corpus_fails_even_if_fresh(repo, capsys):
    """Staleness and structural rot are different failures; validate() must run
    against the on-disk file too, not only against the fresh build."""
    corpus = cc._fresh(str(repo), 8)
    corpus["nodes"][0].pop("owner")
    _write_local(repo, corpus)
    assert cc.main(["--root", str(repo)]) == 1
    assert "ERROR check_corpus" in capsys.readouterr().err


def test_local_corpus_of_json_null_fails(repo, capsys):
    """`null` parses fine and is not a dict; it must be reported as rot, not
    slip past a `is not None` guard at exit 0 — found by the ADR-0008 review."""
    (repo / "wiki").mkdir()
    (repo / "wiki" / "corpus.json").write_text("null\n", encoding="utf-8")
    assert cc.main(["--root", str(repo)]) == 1
    assert "ERROR check_corpus" in capsys.readouterr().err


@pytest.mark.parametrize(
    "payload", ["[]", "5", '{"nodes": 5, "schema_version": 1, "root": "."}']
)
def test_wrong_shaped_local_corpus_fails_without_a_traceback(repo, payload, capsys):
    """Structural rot must take the designed ERROR path; running the staleness
    projection over a non-graph crashed with a traceback instead."""
    (repo / "wiki").mkdir()
    (repo / "wiki" / "corpus.json").write_text(payload, encoding="utf-8")
    assert cc.main(["--root", str(repo)]) == 1
    assert "ERROR check_corpus" in capsys.readouterr().err


def test_bom_module_is_still_indexed(repo):
    """A UTF-8-BOM file is valid, importable Python (the runtime strips the
    BOM); reading it as plain utf-8 left U+FEFF in the source and the module
    silently vanished from the corpus — the drop class ADR-0008 exists to
    close, re-opened for exactly BOM files. Both twins read utf-8-sig now."""
    mod = _MOD.replace("Thing", "Bom").replace("thing", "bom")
    (repo / "src" / "bom.py").write_bytes(b"\xef\xbb\xbf" + mod.encode("utf-8"))
    fresh = cc._fresh(str(repo), 8)
    assert any(
        n["path"] == "src/bom.py" and n["kind"] == "module" for n in fresh["nodes"]
    )


def test_exported_names_parity_with_the_corpus_reader(repo):
    """check_structure._exported_names and build_corpus's inline __all__ reader
    are the same duplicated logic on either side of the 3.6 boundary; this pins
    them to each other over the forms both claim to read (plain and annotated
    literal assignments)."""
    src = (
        '"""\ntitle: t\nsummary: s\n"""\n'
        '__all__: list[str] = ["a", "b"]\n\n\n'
        'def a():\n    """A."""\n\n\ndef b():\n    """B."""\n'
    )
    (repo / "src" / "ann.py").write_text(src, encoding="utf-8")
    fresh = cc._fresh(str(repo), 8)
    corpus_names = {
        n["node_id"].split("::", 1)[1]
        for n in fresh["nodes"]
        if n["kind"] == "symbol" and n["path"] == "src/ann.py"
    }
    assert corpus_names == set(cs._exported_names(ast.parse(src)))
