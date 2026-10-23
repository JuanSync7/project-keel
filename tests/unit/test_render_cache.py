"""
title: Unit — the render cache makes one render per answer set and hands each test its own copy
kind: tests
layer: n/a
summary: tests/render_cache.py with a stand-in renderer. The same answers on the same day render once and the same answers in another key order are the same set, while other answers, or the same answers on another day, render again; each copy is the render's bytes, symlinks kept as links and every mode restored, and is the caller's to change without reaching the render or a sibling copy; the shared render refuses a write, a new file and a removal; a renderer that raises leaves nothing cached and is asked again, one that writes nothing is refused naming the answers, a copy over an existing directory is refused before anything is rendered, and `close` removes every render.
"""

import datetime
import json
import os
import stat
from pathlib import Path

import pytest

import render_cache

pytestmark = pytest.mark.unit

_DAY = datetime.date(2026, 10, 22)


class _Renderer:
    """A stand-in for copier: writes a small tree that names its answers,
    with an executable script and a symlink, and counts its calls."""

    def __init__(self):
        self.calls = []

    def __call__(self, dest, answers):
        self.calls.append(dict(answers))
        dest = Path(dest)
        (dest / "docs").mkdir(parents=True)
        (dest / "answers.json").write_text(
            json.dumps(answers, sort_keys=True), encoding="utf-8"
        )
        (dest / "AGENT.md").write_text("rules\n", encoding="utf-8")
        os.symlink("AGENT.md", str(dest / "CLAUDE.md"))
        script = dest / "docs" / "run.sh"
        script.write_text("#!/bin/sh\n", encoding="utf-8")
        script.chmod(0o750)


@pytest.fixture
def cache(tmp_path):
    renderer = _Renderer()
    made = render_cache.RenderCache(tmp_path / "renders", renderer)
    yield made, renderer
    made.close()


def _modes(root):
    return {
        str(p.relative_to(root)): stat.S_IMODE(p.lstat().st_mode)
        for p in sorted(Path(root).rglob("*"))
        if not p.is_symlink()
    }


def test_the_same_answers_render_once_whatever_their_order(cache, tmp_path):
    made, renderer = cache
    made.copy_into(tmp_path / "a", {"name": "x", "stack": "none"}, _DAY)
    made.copy_into(tmp_path / "b", {"stack": "none", "name": "x"}, _DAY)
    assert renderer.calls == [{"name": "x", "stack": "none"}]


def test_other_answers_or_another_day_render_again(cache, tmp_path):
    made, renderer = cache
    made.copy_into(tmp_path / "a", {"name": "x"}, _DAY)
    made.copy_into(tmp_path / "b", {"name": "y"}, _DAY)
    made.copy_into(tmp_path / "c", {"name": "x", "transports": ["grpc"]}, _DAY)
    made.copy_into(tmp_path / "d", {"name": "x"}, _DAY + datetime.timedelta(days=1))
    assert len(renderer.calls) == 4, renderer.calls


def test_a_copy_is_the_renders_bytes_links_and_modes(cache, tmp_path):
    made, _renderer = cache
    fresh = tmp_path / "fresh"
    _Renderer()(fresh, {"name": "x"})
    copy = made.copy_into(tmp_path / "copy", {"name": "x"}, _DAY)
    assert copy == tmp_path / "copy"
    assert (copy / "CLAUDE.md").is_symlink()
    assert os.readlink(str(copy / "CLAUDE.md")) == "AGENT.md"
    assert _modes(copy) == _modes(fresh)
    assert (copy / "answers.json").read_bytes() == (fresh / "answers.json").read_bytes()


def test_a_copy_is_the_callers_own(cache, tmp_path):
    made, _renderer = cache
    first = made.copy_into(tmp_path / "a", {"name": "x"}, _DAY)
    (first / "answers.json").write_text("changed", encoding="utf-8")
    (first / "planted.txt").write_text("mine", encoding="utf-8")
    (first / "docs" / "run.sh").unlink()
    second = made.copy_into(tmp_path / "b", {"name": "x"}, _DAY)
    assert (second / "answers.json").read_text(encoding="utf-8") == '{"name": "x"}'
    assert not (second / "planted.txt").exists()
    assert (second / "docs" / "run.sh").is_file()


def test_the_shared_render_refuses_a_write(cache, tmp_path):
    made, _renderer = cache
    made.copy_into(tmp_path / "a", {"name": "x"}, _DAY)
    [render] = made.renders()
    with pytest.raises(PermissionError):
        (render / "answers.json").write_text("changed", encoding="utf-8")
    with pytest.raises(PermissionError):
        (render / "docs" / "planted.txt").write_text("x", encoding="utf-8")
    with pytest.raises(PermissionError):
        (render / "docs" / "run.sh").unlink()
    with pytest.raises(PermissionError):
        (render / "planted.txt").write_text("x", encoding="utf-8")


def test_a_failed_render_is_not_cached(tmp_path):
    calls = []

    def refuse(dest, answers):
        calls.append(answers)
        Path(dest).mkdir()
        (Path(dest) / "half.txt").write_text("partial", encoding="utf-8")
        raise ValueError("refused answers")

    made = render_cache.RenderCache(tmp_path / "renders", refuse)
    try:
        for name in ("a", "b"):
            with pytest.raises(ValueError, match="refused answers"):
                made.copy_into(tmp_path / name, {"name": "x"}, _DAY)
            assert not (tmp_path / name).exists()
        assert len(calls) == 2
        assert made.renders() == []
    finally:
        made.close()


def test_a_render_that_writes_nothing_is_refused(tmp_path):
    made = render_cache.RenderCache(tmp_path / "renders", lambda dest, answers: None)
    try:
        with pytest.raises(render_cache.RenderError, match="'name': 'x'"):
            made.copy_into(tmp_path / "a", {"name": "x"}, _DAY)
    finally:
        made.close()


def test_a_copy_over_an_existing_directory_is_refused(cache, tmp_path):
    made, renderer = cache
    (tmp_path / "a").mkdir()
    with pytest.raises(FileExistsError):
        made.copy_into(tmp_path / "a", {"name": "x"}, _DAY)
    # Refused before the render: a copier render costs about ten seconds.
    assert renderer.calls == []


def test_close_removes_every_render(tmp_path):
    made = render_cache.RenderCache(tmp_path / "renders", _Renderer())
    made.copy_into(tmp_path / "a", {"name": "x"}, _DAY)
    made.copy_into(tmp_path / "b", {"name": "y"}, _DAY)
    assert len(made.renders()) == 2
    made.close()
    assert not (tmp_path / "renders").exists()
    made.close()
