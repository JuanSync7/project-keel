"""
title: Unit — the structure gate confines the changed-tests cache
summary: check_H refuses absolute, parent-escaping, symlink-escaping, tracked and unignored cache paths; a nested ignored path passes and the loader declares the default.
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402
import config_loader  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / "project"
    (root / "config").mkdir(parents=True)
    monkeypatch.setattr(cs, "ROOT", str(root))
    monkeypatch.setattr(cs, "errors", [])
    monkeypatch.setattr(cs, "warnings", [])
    monkeypatch.setattr(cs, "_CONFIG_READ", {})
    monkeypatch.setattr(cs, "_READ_REPORTED", set())
    monkeypatch.setattr(
        cs.git_tree, "is_ignored", lambda root, path: path.startswith(".cache/")
    )
    monkeypatch.setattr(
        cs.git_tree, "tracked", lambda root, paths: {"tracked"}.intersection(paths)
    )
    monkeypatch.setattr(
        cs.git_tree, "candidate_files", lambda root: [".cache/tracked/file.py"]
    )
    return root


@pytest.mark.parametrize(
    "path",
    [
        "/absolute",
        "../outside",
        ".cache/../../outside",
        "C:/absolute",
        "tracked",
        "visible",
        ".",
        ".cache/tracked",
        "",
        None,
        1,
    ],
)
def test_structure_refuses_unsafe_cache_paths(project, path):
    (project / "config/project.json").write_text(
        json.dumps({"tests": {"cache_dir": path}})
    )
    cs.check_H()
    assert any("tests.cache_dir" in error for error in cs.errors), cs.errors


def test_structure_refuses_a_symlink_escape(project, tmp_path):
    (project / ".cache").symlink_to(tmp_path, target_is_directory=True)
    (project / "config/project.json").write_text(
        json.dumps({"tests": {"cache_dir": ".cache/loop"}})
    )
    cs.check_H()
    assert any("tests.cache_dir" in error for error in cs.errors), cs.errors


def test_structure_accepts_a_nested_ignored_cache(project):
    (project / "config/project.json").write_text(
        json.dumps({"tests": {"cache_dir": ".cache/loop"}})
    )
    cs.check_H()
    assert cs.errors == []


def test_cache_path_has_a_typed_default():
    key = ("tests", "cache_dir")
    rows = config_loader.rows(key)
    assert len(rows) == 1 and rows[0].type == "nonempty_str"
    assert (
        config_loader.resolve({}, rows, config_loader.CONFIG_FILE)[key]
        == ".pytest_cache"
    )


@pytest.mark.parametrize("path", [".cache/loop", ".cache/tracked", "authored/loop"])
def test_structural_walks_skip_only_the_validated_cache(project, path):
    (project / "config/project.json").write_text(
        json.dumps({"tests": {"cache_dir": path}})
    )
    for relative in (".cache/loop", ".cache/tracked", "authored/loop"):
        directory = project / relative
        directory.mkdir(parents=True)
        (directory / "README.md").write_text("generated or authored text\n")
    for walker in (cs.walk, cs.sorted_walk):
        walked = {
            Path(path).relative_to(project).as_posix() for path, _, _ in walker(project)
        }
        assert (".cache/loop" not in walked) == (path == ".cache/loop"), walked
        assert ".cache/tracked" in walked, walked
        assert "authored/loop" in walked, walked


def _walked(walker, root):
    return {Path(path).relative_to(root).as_posix() for path, _, _ in walker(root)}


def test_a_walk_of_another_tree_leaves_out_that_tree_s_cache(project, tmp_path):
    (project / "config/project.json").write_text(
        json.dumps({"tests": {"cache_dir": ".cache/loop"}})
    )
    other = tmp_path / "other"
    (other / "config").mkdir(parents=True)
    (other / "config/project.json").write_text(
        json.dumps({"tests": {"cache_dir": ".cache/other"}})
    )
    for relative in (".cache/loop", ".cache/other"):
        (other / relative).mkdir(parents=True)
        (other / relative / "README.md").write_text("cache\n")
    for walker in (cs.walk, cs.sorted_walk):
        walked = _walked(walker, other)
        assert ".cache/other" not in walked, walked
        assert ".cache/loop" in walked, walked


def test_a_walk_of_a_tree_without_a_manifest_asks_git_nothing(
    project, tmp_path, monkeypatch
):
    (project / "config/project.json").write_text(
        json.dumps({"tests": {"cache_dir": ".cache/loop"}})
    )

    def refuse(*_args):
        raise AssertionError("a tree with no manifest declares no cache to confine")

    for name in ("is_ignored", "tracked", "candidate_files", "confined_path"):
        monkeypatch.setattr(cs.git_tree, name, refuse)
    other = tmp_path / "other"
    (other / ".cache/loop").mkdir(parents=True)
    assert ".cache/loop" in _walked(cs.walk, other)


def test_a_walk_of_a_subtree_keeps_the_checkout_s_cache(project):
    (project / "config/project.json").write_text(
        json.dumps({"tests": {"cache_dir": ".cache/loop"}})
    )
    (project / ".cache/loop").mkdir(parents=True)
    (project / ".cache/kept").mkdir(parents=True)
    walked = _walked(cs.walk, project / ".cache")
    assert "loop" not in walked and "kept" in walked, walked
