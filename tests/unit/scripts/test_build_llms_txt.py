"""
title: Unit — llms.txt and llms-full.txt hold only the levels the project serves
kind: tests
layer: n/a
summary: scripts/jobs/build_llms_txt.py writes the agent front door into wiki/; a node outside config/project.json corpus.served_visibilities is absent from both files, the configured list rather than a literal decides which nodes those are, and a refused level exits CONFIG with nothing written.
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))

import build_corpus as bc  # noqa: E402
import build_llms_txt as llms  # noqa: E402
from exit_codes import ExitCode  # noqa: E402

pytestmark = pytest.mark.unit

_CODEWORD = "CODEWORD-ZEBRA"


def _doc(doc_id, body, visibility=None):
    head = "---\ntitle: %s\nkind: doc\nsummary: About %s.\nid: %s\nowner: alice\n" % (
        doc_id,
        doc_id,
        doc_id,
    )
    if visibility is not None:
        head += "visibility: %s\n" % visibility
    return head + "---\n# %s\n\n## Zebra part\n\n%s\n" % (doc_id, body)


def _project(root, served=None):
    """A scratch project with an internal doc and a confidential README whose
    body is the codeword, its corpus built; returns the confidential node ids."""
    config = {} if served is None else {"corpus": {"served_visibilities": served}}
    files = {
        "config/project.json": json.dumps(config),
        "docs/open.md": _doc("open", "zebra text"),
        "docs/secret/README.md": _doc("secret", _CODEWORD, "confidential"),
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    nodes = bc.build_corpus(str(root))["nodes"]
    (root / "wiki").mkdir()
    (root / "wiki" / "corpus.json").write_text(
        json.dumps({"schema_version": 1, "nodes": nodes}), encoding="utf-8"
    )
    hidden = sorted(n["node_id"] for n in nodes if n["visibility"] == "confidential")
    assert hidden, "the scratch corpus must hold a confidential node"
    return hidden


def _written(out):
    files = sorted(p for p in out.rglob("*") if p.is_file())
    assert files, "the export wrote nothing"
    return {p.relative_to(out).as_posix(): p.read_text(encoding="utf-8") for p in files}


def test_neither_llms_file_holds_a_confidential_node(tmp_path):
    _project(tmp_path)
    out = tmp_path / "site"
    assert (
        llms.main(["--root", str(tmp_path), "--out-dir", str(out)]) is ExitCode.SUCCESS
    )
    written = _written(out)
    assert sorted(written) == ["llms-full.txt", "llms.txt"]
    for rel, text in written.items():
        assert _CODEWORD not in text, rel
        assert "docs/secret" not in text, rel
    assert "zebra text" in written["llms-full.txt"]


def test_llms_full_serves_the_configured_levels(tmp_path):
    """With `["public"]` configured, the internal doc is absent too."""
    _project(tmp_path, served=["public"])
    out = tmp_path / "site"
    assert (
        llms.main(["--root", str(tmp_path), "--out-dir", str(out)]) is ExitCode.SUCCESS
    )
    assert "zebra text" not in _written(out)["llms-full.txt"]


def test_a_refused_served_level_writes_nothing(tmp_path, capsys):
    _project(tmp_path, served=["unreadable-readme"])
    out = tmp_path / "site"
    assert (
        llms.main(["--root", str(tmp_path), "--out-dir", str(out)]) is ExitCode.CONFIG
    )
    assert not out.exists()
    assert "corpus.served_visibilities" in capsys.readouterr().err
