"""
title: Integration — an ignored directory name is ignored as a symlink too
kind: tests
layer: n/a
summary: git treats a symlink as a file, so a `.gitignore` pattern with a trailing slash matches a real directory and never a symlink of the same name; a shared `.venv` linked into a scratch copy is then picked up by `git add -A` and blocks `copier update` as an untracked file. For every plain-name pattern of `.gitignore` and its `.gitignore.jinja` twin (no glob, no anchor slash), a symlink of that name planted in a scratch repository must be ignored by real `git check-ignore`. The patterns come from the files themselves, never a list here; a file with no plain-name pattern fails, and a planted trailing-slash pattern is exactly one finding. Not a writer: it writes only under pytest's tmp_path.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))

import review_docs  # noqa: E402
from child_env import build_child_env  # noqa: E402

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("git") is None, reason="git not installed"),
]

_IGNORE_FILES = (".gitignore", ".gitignore.jinja")
_GLOB = set("*?[")


def plain_names(text):
    """Each pattern that names one entry by its bare name: no glob, no
    negation, no comment and no slash except a trailing one. Such a pattern
    is meant to ignore that name wherever it appears."""
    names = []
    for line in text.splitlines():
        pattern = line.strip()
        if not pattern or pattern.startswith(("#", "!")):
            continue
        bare = pattern.removesuffix("/")
        if "/" in bare or _GLOB & set(bare):
            continue
        names.append(bare)
    return names


def unignored_symlinks(ignore_text, tmp_path):
    """The plain names whose symlink git does not ignore under this text."""
    repo = tmp_path / "repo"
    target = tmp_path / "target"
    repo.mkdir()
    target.mkdir()
    env = build_child_env()
    subprocess.run(
        review_docs.git_argv(str(repo), "init", "-q"),
        cwd=str(repo),
        env=env,
        check=True,
    )
    (repo / ".gitignore").write_text(ignore_text, encoding="utf-8")
    missed = []
    for name in plain_names(ignore_text):
        (repo / name).symlink_to(target, target_is_directory=True)
        # check-ignore exits 0 when the path is ignored and 1 when it is not.
        probe = subprocess.run(
            review_docs.git_argv(str(repo), "check-ignore", "-q", name),
            cwd=str(repo),
            env=env,
        )
        if probe.returncode != 0:
            missed.append(name)
        (repo / name).unlink()
    return missed


@pytest.mark.parametrize("name", _IGNORE_FILES)
def test_every_ignored_name_is_ignored_as_a_symlink(name, tmp_path):
    path = _ROOT / name
    if not path.exists():
        pytest.skip(f"{name} is the template's twin; a generated project has none")
    text = path.read_text(encoding="utf-8")
    assert plain_names(text), f"{name}: no plain-name pattern to check"
    assert unignored_symlinks(text, tmp_path) == [], (
        f"{name}: these names are ignored only as directories, so a symlink "
        "of that name is committed by `git add -A`; drop the trailing slash"
    )


def test_a_planted_trailing_slash_pattern_is_one_finding(tmp_path):
    text = (_ROOT / ".gitignore").read_text(encoding="utf-8")
    planted = text + "\nplanted_env/\n"
    assert unignored_symlinks(planted, tmp_path) == ["planted_env"]
