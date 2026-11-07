"""
title: Unit — the static export snapshots only the levels the project serves
kind: tests
layer: n/a
summary: scripts/jobs/export_showcase_static.py writes the showcase API and the agent front door to static files that make site-static publishes; a node outside config/project.json corpus.served_visibilities is absent from every file it writes, the configured list rather than a literal decides which nodes those are, and a refused level exits CONFIG with nothing written.
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))

import build_corpus as bc  # noqa: E402
import export_showcase_static as export  # noqa: E402
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


def test_no_file_the_export_writes_holds_a_confidential_node(tmp_path):
    hidden = _project(tmp_path)
    out = tmp_path / "site"
    assert (
        export.main(["--root", str(tmp_path), "--out-dir", str(out)])
        is ExitCode.SUCCESS
    )
    written = _written(out)
    for rel, text in written.items():
        assert _CODEWORD not in text, rel
    nodes = json.loads(written["api/wiki/nodes.json"])
    assert "open" in nodes
    assert not set(hidden) & set(nodes)


def test_the_export_serves_the_configured_levels(tmp_path):
    """With `["public"]` configured, the internal doc is absent too."""
    _project(tmp_path, served=["public"])
    out = tmp_path / "site"
    assert (
        export.main(["--root", str(tmp_path), "--out-dir", str(out)])
        is ExitCode.SUCCESS
    )
    assert json.loads(_written(out)["api/wiki/nodes.json"]) == {}


def test_a_refused_served_level_writes_nothing(tmp_path, capsys):
    _project(tmp_path, served=["unreadable-readme"])
    out = tmp_path / "site"
    assert (
        export.main(["--root", str(tmp_path), "--out-dir", str(out)]) is ExitCode.CONFIG
    )
    assert not out.exists()
    assert "corpus.served_visibilities" in capsys.readouterr().err


@pytest.mark.parametrize(
    "spelling", ["dotdot", "parent-link", "leaf-link", "late-leaf-link"]
)
def test_manifest_escape(tmp_path, spelling):
    root = tmp_path / "project"
    _project(root)
    outside = tmp_path / "outside"
    sentinel = outside / "astro/public/api/overview.json"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_bytes(b"external sentinel\n")
    frontend = "../outside"
    if spelling == "parent-link":
        (root / "frontend").symlink_to(outside, target_is_directory=True)
        frontend = "frontend"
    elif spelling in ("leaf-link", "late-leaf-link"):
        frontend = "frontend"
        api = root / "frontend/astro/public/api"
        api.mkdir(parents=True)
        leaf = (
            api / "overview.json"
            if spelling == "leaf-link"
            else api.parent / "llms-full.txt"
        )
        leaf.symlink_to(sentinel)
    config = root / "config/project.json"
    config.write_text(
        json.dumps({"layers": {"frontend": {"root": frontend, "stack": "astro"}}})
    )
    result = export.main(["--root", str(root)])
    assert sentinel.read_bytes() == b"external sentinel\n"
    assert result == ExitCode.CONFIG
    assert not (root / "frontend/astro/public/llms.txt").exists()


def test_explicit_out_outside_root_is_unchanged(tmp_path):
    root = tmp_path / "project"
    _project(root)
    outside = tmp_path / "outside"
    assert (
        export.main(["--root", str(root), "--out-dir", str(outside)])
        == ExitCode.SUCCESS
    )
    assert "api/overview.json" in _written(outside)


def test_relative_out_escape(tmp_path):
    root = tmp_path / "project"
    _project(root)
    sentinel = tmp_path / "outside/api/overview.json"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_bytes(b"external sentinel\n")
    result = export.main(["--root", str(root), "--out-dir", "../outside"])
    assert sentinel.read_bytes() == b"external sentinel\n"
    assert result == ExitCode.USAGE


def test_relative_root_and_out_escape(tmp_path, monkeypatch):
    root = tmp_path / "project"
    _project(root)
    sentinel = tmp_path / "outside/api/overview.json"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_bytes(b"external sentinel\n")
    (root / "site").symlink_to(sentinel.parents[1], target_is_directory=True)
    monkeypatch.chdir(tmp_path)
    result = export.main(["--root", "project", "--out-dir", "site"])
    assert sentinel.read_bytes() == b"external sentinel\n"
    assert result == ExitCode.USAGE


@pytest.mark.parametrize("linked", [False, True])
def test_missing_target_created(tmp_path, linked):
    _project(tmp_path)
    (tmp_path / "actual").mkdir()
    if linked:
        (tmp_path / "site").symlink_to("actual", target_is_directory=True)
    out = "site/nested"
    assert export.main(["--root", str(tmp_path), "--out-dir", out]) == ExitCode.SUCCESS
    assert "api/overview.json" in _written(tmp_path / out)


def test_export_uses_resolved_destinations(tmp_path, monkeypatch):
    _project(tmp_path)
    out = tmp_path / "site"
    out.mkdir()
    real, outside = out / "real", tmp_path / "outside"
    real.mkdir()
    outside.mkdir()
    link = out / "api"
    link.symlink_to(real, target_is_directory=True)
    sentinel = outside / "overview.json"
    sentinel.write_bytes(b"external sentinel")
    original = export.confined_path

    def checked(boundary, path):
        result = original(boundary, path)
        if path.endswith("llms-full.txt"):
            link.unlink()
            link.symlink_to(outside, target_is_directory=True)
        return result

    monkeypatch.setattr(export, "confined_path", checked)
    assert (
        export.main(["--root", str(tmp_path), "--out-dir", str(out)])
        == ExitCode.SUCCESS
    )
    assert sentinel.read_bytes() == b"external sentinel"
    assert (real / "overview.json").is_file()
