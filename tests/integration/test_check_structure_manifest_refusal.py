"""
title: Integration — a manifest the loader refuses fails `make check` with one finding
kind: tests
layer: n/a
summary: scripts/check_structure.py reads config/project.json through scripts/config_loader.py, so a key written twice, a merge-conflict hunk, bytes that are not UTF-8, an empty file and a top level that is not an object each give exactly one error that names the file and the fault, and the gate's exit is 1. Before this the last duplicate value won in silence (exit 0) and a hunk at line 1 broke every check into dozens of findings. The registry config/practices.json is read the same way. A walk over zero planted faults is a failure.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "tests" / "integration"))

import check_structure as cs  # noqa: E402
from child_env import build_child_env  # noqa: E402
from test_scratch_root_gate import child_timeout  # noqa: E402

pytestmark = pytest.mark.integration

_OPEN, _SPLIT, _CLOSE = "<" * 7, "=" * 7, ">" * 7

# fault -> (bytes written to config/project.json, what the one finding says)
_FAULTS = {
    "a key written twice": (b'{"zz": 1, "zz": 2}', "appears twice"),
    "a nested key written twice": (b'{"a": {"zz": 1, "zz": 2}}', "appears twice"),
    "a merge-conflict hunk": (
        ("%s ours\n{}\n%s\n{}\n%s theirs\n" % (_OPEN, _SPLIT, _CLOSE)).encode(),
        "merge-conflict hunk at line 1",
    ),
    "bytes that are not UTF-8": (b'{"a": "\xff"}', "not UTF-8"),
    "a UTF-8 BOM": (b"\xef\xbb\xbf{}", "cannot be read as JSON"),
    "NaN": (b'{"a": NaN}', "cannot be read as JSON"),
    "null": (b"null", "top level"),
    "an empty file": (b"", "cannot be read as JSON"),
    "a top level that is not an object": (b"[]", "top level"),
    "permission denied": (None, "cannot be read ("),
}


@pytest.fixture
def populated_tree(tmp_path):
    """Keep the real owned documents, twins and rosters that expose fallbacks."""
    return Path(
        shutil.copytree(
            _ROOT,
            tmp_path / "repo",
            symlinks=True,
            ignore=shutil.ignore_patterns(*cs.IGNORE_DIRS, ".codex-review"),
        )
    )


def _errors(root):
    return [
        m
        for _letter, tier, m in cs.run_checks(str(root), project_checks=False)
        if tier == "error"
    ]


def test_the_table_plants_a_fault():
    assert len(_FAULTS) > 0


def test_the_populated_tree_starts_clean(populated_tree):
    assert _errors(populated_tree) == []


@pytest.mark.parametrize("filename", cs.JSON_CONFIGS)
def test_a_config_directory_in_a_populated_tree_is_one_refusal(
    populated_tree, filename
):
    path = populated_tree / filename
    path.unlink()
    path.mkdir()
    found = _errors(populated_tree)
    assert len(found) == 1, found
    assert filename in found[0], found
    assert "cannot be read (" in found[0], found


@pytest.mark.parametrize("filename", cs.JSON_CONFIGS)
@pytest.mark.parametrize("fault", sorted(_FAULTS))
def test_a_manifest_the_loader_refuses_is_one_finding_naming_the_file(
    populated_tree, fault, filename
):
    body, says = _FAULTS[fault]
    path = populated_tree / filename
    mode = path.stat().st_mode
    if body is None:
        if not hasattr(os, "geteuid") or os.geteuid() == 0:
            pytest.skip(
                "chmod 000 cannot prove permission denial on this platform/user"
            )
        try:
            path.chmod(0)
        except (OSError, NotImplementedError) as exc:
            pytest.skip("chmod 000 is unavailable: %s" % exc)
        try:
            path.read_bytes()
        except PermissionError:  # noqa: DROP001 -- the denial is the fault this case exercises
            pass
        else:
            path.chmod(mode)
            pytest.skip("this filesystem permits reading after chmod 000")
    else:
        path.write_bytes(body)
    try:
        found = _errors(populated_tree)
    finally:
        path.chmod(mode)
    assert len(found) == 1, found
    assert filename in found[0], found
    assert says in found[0], found


def test_a_key_written_twice_in_the_manifest_fails_check(populated_tree):
    root = populated_tree
    own = (_ROOT / "config" / "project.json").read_text(encoding="utf-8")
    assert own.rstrip().endswith("}")
    (root / "config" / "project.json").write_text(
        own.rstrip()[:-1].rstrip() + ',\n  "zz": 1,\n  "zz": 2\n}\n', encoding="utf-8"
    )
    done = subprocess.run(
        [
            sys.executable,
            "-B",
            str(_ROOT / "scripts" / "check_structure.py"),
            "--root",
            str(root),
        ],
        capture_output=True,
        text=True,
        env=build_child_env(),
        timeout=child_timeout(),
    )
    assert done.returncode == 1, done.stdout + done.stderr
    assert "appears twice" in done.stdout, done.stdout
    assert "check_structure: 1 error(s)" in done.stdout, done.stdout
