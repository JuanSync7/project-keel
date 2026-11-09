"""
title: Unit — atomic text and bytes publication
kind: tests
layer: n/a
summary: Published files retain existing permissions or respect the creation umask; failed publication removes temporary files and preserves the previous target, and successful publication flushes to disk before replacement.
"""

import os
import stat
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import atomic_write  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("data", ["snowman: ☃\n", b"binary: \x00\xff\n"])
@pytest.mark.parametrize("mode", [0o640, 0o664, 0o755])
def test_existing_target_keeps_its_mode(tmp_path, data, mode):
    target = tmp_path / "published"
    target.write_bytes(b"old complete file")
    target.chmod(mode)
    previous_umask = os.umask(0o077)
    try:
        assert atomic_write.write_if_changed(str(target), data)
    finally:
        os.umask(previous_umask)
    assert stat.S_IMODE(target.stat().st_mode) == mode
    assert target.read_bytes() == (
        data.encode("utf-8") if isinstance(data, str) else data
    )


@pytest.mark.parametrize("data", ["snowman: ☃\n", b"binary: \x00\xff\n"])
@pytest.mark.parametrize("mask", [0o002, 0o027, 0o077])
def test_new_target_respects_umask(tmp_path, data, mask):
    target = tmp_path / "published"
    previous_umask = os.umask(mask)
    try:
        assert atomic_write.write_if_changed(str(target), data)
    finally:
        os.umask(previous_umask)
    assert stat.S_IMODE(target.stat().st_mode) == 0o666 & ~mask
    assert target.read_bytes() == (
        data.encode("utf-8") if isinstance(data, str) else data
    )


@pytest.mark.parametrize("operation", ["chmod", "fsync", "replace"])
@pytest.mark.parametrize("error_type", [OSError, KeyboardInterrupt])
def test_publication_error_removes_temp_and_preserves_target(
    tmp_path, monkeypatch, operation, error_type
):
    target = tmp_path / "published"
    before = b"old complete file"
    target.write_bytes(before)
    target.chmod(0o640)
    failure = error_type("publication interrupted")

    def refuse(*args, **kwargs):
        raise failure

    monkeypatch.setattr(os, operation, refuse)
    with pytest.raises(error_type) as caught:
        atomic_write.write_if_changed(str(target), b"new complete file")
    assert caught.value is failure
    assert target.read_bytes() == before
    assert stat.S_IMODE(target.stat().st_mode) == 0o640
    assert list(tmp_path.iterdir()) == [target]


def test_failed_first_publication_leaves_no_file(tmp_path, monkeypatch):
    target = tmp_path / "published"

    def refuse(*args):
        raise OSError("publication interrupted")

    monkeypatch.setattr(os, "replace", refuse)
    with pytest.raises(OSError, match="publication interrupted"):
        atomic_write.write_if_changed(str(target), b"new complete file")
    assert list(tmp_path.iterdir()) == []


def test_fsync_precedes_atomic_replacement(tmp_path, monkeypatch):
    target = tmp_path / "published"
    target.write_bytes(b"old complete file")
    target.chmod(0o664)
    data = b"new complete file\n"
    fsync, replace = os.fsync, os.replace
    synced = []

    def sync(handle):
        assert os.fstat(handle).st_size == len(data)
        assert stat.S_IMODE(os.fstat(handle).st_mode) == 0o664
        synced.append(handle)
        fsync(handle)

    def publish(source, destination):
        source = Path(source)
        assert synced
        assert source != target and source.parent == target.parent
        assert source.read_bytes() == data
        assert target.read_bytes() == b"old complete file"
        replace(source, destination)

    monkeypatch.setattr(os, "fsync", sync)
    monkeypatch.setattr(os, "replace", publish)
    assert atomic_write.write_if_changed(str(target), data)
    assert target.read_bytes() == data
    assert list(tmp_path.iterdir()) == [target]


def test_unchanged_target_is_untouched(tmp_path):
    target = tmp_path / "published"
    target.write_text("complete text\n", encoding="utf-8")
    before = target.stat()
    assert not atomic_write.write_if_changed(str(target), "complete text\n")
    after = target.stat()
    assert (after.st_ino, after.st_mtime_ns, after.st_mode) == (
        before.st_ino,
        before.st_mtime_ns,
        before.st_mode,
    )
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize("name", ["published", "nested/published"])
def test_relative_target_and_missing_parent(tmp_path, monkeypatch, name):
    monkeypatch.chdir(tmp_path)
    assert atomic_write.write_if_changed(name, b"complete file")
    assert (tmp_path / name).read_bytes() == b"complete file"
