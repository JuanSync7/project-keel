"""
title: Integration — one helper says whether a pid a test started still runs
kind: tests
layer: n/a
summary: tests/process_state.py `alive` is the only test code that builds a /proc/<pid>/stat path, as a "/proc/%d/stat" constant or an f-string from "/proc/" to "/stat". Four copies of that answer each guarded a different subset of the reaping races (a zombie, a pid reaped before the open, one reaped during the read), and the one missing the second failed a full verify on a loaded host. The check reads every module under tests/ as Python source, so a path inside a child interpreter's script text, a longer string, is not one; a pass that finds no such path in process_state.py itself is a failure.
@covers tests/process_state.py
"""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_TESTS = Path(__file__).resolve().parents[1]
_HELPER = _TESTS / "process_state.py"
_STAT = "/proc/%d/stat"


def _stat_paths(source, name):
    """Line numbers in *source* that build a /proc/<pid>/stat path."""
    lines = []
    for node in ast.walk(ast.parse(source, name)):
        if isinstance(node, ast.Constant) and node.value == _STAT:
            lines.append(node.lineno)
        elif isinstance(node, ast.JoinedStr) and node.values:
            first, last = node.values[0], node.values[-1]
            if (
                isinstance(first, ast.Constant)
                and str(first.value).startswith("/proc/")
                and isinstance(last, ast.Constant)
                and str(last.value).endswith("/stat")
            ):
                lines.append(node.lineno)
    return lines


@pytest.mark.parametrize(
    ("source", "found"),
    [
        ('open("/proc/%d/stat" % pid)', True),
        ('open(f"/proc/{pid}/stat")', True),
        ("SCRIPT = \"with open('/proc/%d/stat' % pid) as fh:\\n\"", False),
        ('open("/proc/%d/status" % pid)', False),
    ],
    ids=["percent-format", "f-string", "inside-child-script", "another-file"],
)
def test_a_stat_path_is_found_only_where_python_builds_one(source, found):
    assert bool(_stat_paths(source, "<case>")) is found


def test_only_process_state_builds_a_proc_stat_path():
    assert _stat_paths(_HELPER.read_text(encoding="utf-8"), str(_HELPER)), (
        "%s builds no /proc/<pid>/stat path -- zero items" % _HELPER
    )
    found = []
    for path in sorted(_TESTS.rglob("*.py")):
        # This module names the path it looks for.
        if path in (_HELPER, Path(__file__).resolve()):
            continue
        found.extend(
            "%s:%d" % (path.relative_to(_TESTS.parent), line)
            for line in _stat_paths(path.read_text(encoding="utf-8"), str(path))
        )
    assert not found, (
        "use process_state.alive instead of reading /proc/<pid>/stat:\n"
        + "\n".join(found)
    )
