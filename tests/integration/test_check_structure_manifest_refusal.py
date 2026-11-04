"""
title: Integration — a manifest the loader refuses fails `make check` with one finding
kind: tests
layer: n/a
summary: scripts/check_structure.py reads config/project.json through scripts/config_loader.py, so a key written twice, a merge-conflict hunk, bytes that are not UTF-8, an empty file and a top level that is not an object each give exactly one error that names the file and the fault, and the gate's exit is 1. Before this the last duplicate value won in silence (exit 0) and a hunk at line 1 broke every check into dozens of findings. The registry config/practices.json is read the same way. A walk over zero planted faults is a failure.
"""

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
    "a merge-conflict hunk": (
        ("%s ours\n{}\n%s\n{}\n%s theirs\n" % (_OPEN, _SPLIT, _CLOSE)).encode(),
        "merge-conflict hunk at line 1",
    ),
    "bytes that are not UTF-8": (b'{"a": "\xff"}', "not UTF-8"),
    "an empty file": (b"", "cannot be read as JSON"),
    "a top level that is not an object": (b"[]", "top level"),
}


def _plant(tmp_path, body):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.json").write_bytes(body)
    return tmp_path


def _manifest_findings(root):
    return [
        m
        for _letter, tier, m in cs.run_checks(str(root), project_checks=False)
        if tier == "error" and "config/project.json" in m
    ]


def test_the_table_plants_a_fault():
    assert len(_FAULTS) > 0


@pytest.mark.parametrize("fault", sorted(_FAULTS))
def test_a_manifest_the_loader_refuses_is_one_finding_naming_the_file(tmp_path, fault):
    body, says = _FAULTS[fault]
    found = _manifest_findings(_plant(tmp_path, body))
    assert len(found) == 1, found
    assert says in found[0], found


def test_a_key_written_twice_in_the_manifest_fails_check(tmp_path):
    root = _plant(tmp_path, (_ROOT / "config" / "project.json").read_bytes())
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
