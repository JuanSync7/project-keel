"""
title: Unit — cache shape and git write authorization
summary: check_H and structural walks judge relative cache spelling and confinement without git. cache_path refuses tracked and unignored paths in a real repository, accepts an ignored directory, and fails closed without git; the loader declares the default.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import changed_cache  # noqa: E402
import check_structure as cs  # noqa: E402
import config_loader  # noqa: E402
from child_env import build_child_env  # noqa: E402

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

    def refuse_git(*_args):
        raise AssertionError("structural cache validation must not consult git")

    for name in ("is_ignored", "tracked", "candidate_files"):
        monkeypatch.setattr(cs.git_tree, name, refuse_git)
    return root


@pytest.mark.parametrize(
    "path",
    [
        "/absolute",
        "../outside",
        ".cache/../../outside",
        "C:/absolute",
        ".",
        "cache//loop",
        "cache/./loop",
        "cache/",
        "cache\\loop",
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


def test_structure_accepts_a_nested_cache_without_git(project):
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
        for relative in (".cache/loop", ".cache/tracked", "authored/loop"):
            assert (relative not in walked) == (path == relative), walked


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


@pytest.mark.parametrize("kind", ["tracked", "unignored", "holds-tracked", "ignored"])
def test_cache_write_authorization_asks_a_real_repository(tmp_path, kind):
    root = tmp_path / "project"
    (root / "config").mkdir(parents=True)
    (root / "config/project.json").write_text(
        json.dumps({"tests": {"cache_dir": "cache"}})
    )

    def git(*args):
        subprocess.run(
            ["git", *args],
            cwd=root,
            env=build_child_env(),
            check=True,
            capture_output=True,
        )

    git("init", "--quiet")
    if kind != "unignored":
        (root / ".gitignore").write_text("cache\n")
    if kind == "tracked":
        (root / "cache").write_text("tracked data\n")
        git("add", "--force", "cache")
    elif kind == "holds-tracked":
        (root / "cache").mkdir()
        (root / "cache/data").write_text("tracked data\n")
        git("add", "--force", "cache/data")
    if kind == "ignored":
        assert changed_cache.cache_path(str(root)) == str(root / "cache")
    else:
        with pytest.raises(ValueError, match="tracked|git-ignored"):
            changed_cache.cache_path(str(root))


def test_cache_write_authorization_fails_closed_without_git(tmp_path):
    with pytest.raises(cs.git_tree.NoGitError):
        changed_cache.cache_path(str(tmp_path), {"tests": {"cache_dir": "cache"}})
