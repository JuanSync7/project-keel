"""
title: Integration — the config loader's one read of a config file
kind: tests
layer: n/a
summary: scripts/config_loader.py `read` is the one open and parse of a config file. A missing file is ConfigAbsent, told apart from ConfigUnreadable, which is every other failure: an OSError, bytes that are not UTF-8, a UTF-8 byte-order mark, text that is not JSON, a NaN or Infinity constant, a top level that is not an object, and a key written twice in one object, which json.load would keep silently. A merge-conflict hunk an update left is named by its line through scripts/jobs/conflict_guard.py's grammar; when that grammar cannot load, the parse error stands and says the markers were not checked. Every refusal is one line naming the file, and the same file read twice gives equal, independent dicts.
@covers scripts/config_loader.py
"""

import os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import config_loader  # noqa: E402
from config_loader import (  # noqa: E402
    CONFIG_FILE,
    PRACTICES_FILE,
    ConfigAbsent,
    ConfigError,
    ConfigUnreadable,
    read,
)

pytestmark = pytest.mark.integration

# Spelled as repetitions so this file holds no marker text: the leftover-marker
# tree scans read it too.
_OPEN, _SPLIT, _CLOSE = b"<" * 7, b"=" * 7, b">" * 7


def _plant(root, data, relpath=CONFIG_FILE):
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_a_missing_file_is_absent_not_unreadable(tmp_path):
    with pytest.raises(ConfigAbsent) as exc:
        read(str(tmp_path))
    assert not isinstance(exc.value, ConfigUnreadable)
    assert exc.value.path == CONFIG_FILE
    assert exc.value.lines == ["%s does not exist" % CONFIG_FILE]


def test_a_readable_object_is_returned_fresh_each_call(tmp_path):
    _plant(tmp_path, b'{"a": {"b": [1]}}')
    first, second = read(str(tmp_path)), read(str(tmp_path))
    assert first == second == {"a": {"b": [1]}}
    first["a"]["b"].append(2)
    assert read(str(tmp_path)) == {"a": {"b": [1]}}


def test_the_practices_file_is_read_through_the_same_door(tmp_path):
    _plant(tmp_path, b'{"practices": []}', PRACTICES_FILE)
    assert read(str(tmp_path), PRACTICES_FILE) == {"practices": []}
    with pytest.raises(ConfigAbsent) as exc:
        read(str(tmp_path))
    assert exc.value.path == CONFIG_FILE


_UNREADABLE = (
    ("not json", b"{not json", "cannot be read as JSON"),
    ("a list", b"[1, 2]", "holds a JSON array at the top level"),
    ("a string", b'"x"', "holds a JSON string at the top level"),
    ("a duplicate key", b'{"a": 1, "a": 2}', "the key `a` appears twice"),
    ("a nested duplicate", b'{"a": {"b": 1, "b": 1}}', "the key `b` appears twice"),
    ("NaN", b'{"a": NaN}', "NaN"),
    ("Infinity", b'{"a": -Infinity}', "Infinity"),
    ("a byte-order mark", b'\xef\xbb\xbf{"a": 1}', "cannot be read as JSON"),
    ("latin-1 bytes", b'{"a": "\xe9"}', "is not UTF-8"),
)


@pytest.mark.parametrize(
    "data,expected", [c[1:] for c in _UNREADABLE], ids=[c[0] for c in _UNREADABLE]
)
def test_every_other_failure_is_unreadable_in_one_line_naming_the_file(
    tmp_path, data, expected
):
    _plant(tmp_path, data)
    with pytest.raises(ConfigUnreadable) as exc:
        read(str(tmp_path))
    assert isinstance(exc.value, ConfigError)
    assert len(exc.value.lines) == 1, exc.value.lines
    (line,) = exc.value.lines
    assert line.startswith(CONFIG_FILE + " "), line
    assert expected in line, line
    assert exc.value.conflict_line is None


def test_an_os_error_is_unreadable(tmp_path):
    (tmp_path / CONFIG_FILE).mkdir(parents=True)
    with pytest.raises(ConfigUnreadable) as exc:
        read(str(tmp_path))
    assert exc.value.lines[0].startswith("%s cannot be read (" % CONFIG_FILE), (
        exc.value.lines
    )


def test_a_conflict_hunk_is_named_by_its_line(tmp_path):
    _plant(
        tmp_path,
        b'{\n  "a": 1,\n%s ours\n  "b": 1\n%s\n  "b": 2\n%s theirs\n}\n'
        % (_OPEN, _SPLIT, _CLOSE),
    )
    with pytest.raises(ConfigUnreadable) as exc:
        read(str(tmp_path))
    assert exc.value.conflict_line == 3
    (line,) = exc.value.lines
    assert line.startswith("%s holds a merge-conflict hunk at line 3;" % CONFIG_FILE), (
        line
    )
    assert exc.value.unchecked is None


def test_a_grammar_that_cannot_load_leaves_the_parse_error_and_says_so(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        config_loader, "_GRAMMAR", os.path.join(str(tmp_path), "absent.py")
    )
    _plant(tmp_path, b"{\n%s ours\n%s\n%s theirs\n}\n" % (_OPEN, _SPLIT, _CLOSE))
    with pytest.raises(ConfigUnreadable) as exc:
        read(str(tmp_path))
    (line,) = exc.value.lines
    assert (
        "cannot be read as JSON" in line and "conflict markers not checked" in line
    ), line
    assert exc.value.conflict_line is None and exc.value.unchecked
