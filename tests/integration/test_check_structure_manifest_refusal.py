"""
title: Integration — a manifest the loader refuses fails `make check` with one finding
kind: tests
layer: n/a
summary: scripts/check_structure.py reads config/project.json through scripts/config_loader.py, so a key written twice, a merge-conflict hunk, bytes that are not UTF-8, an empty file and a top level that is not an object each give exactly one error that names the file and the fault, and run_checks returns that finding; the CLI refuses either project or practices input with one stderr line and exit 14 (2 for a hunk). Practices sections fully match [0-9]{1,4} and section faults exit CONFIG without exposing an @ payload; malformed source proof sections stay one FAILURE finding. Repeated runs reset section and loader-refusal provenance. Before this the last duplicate value won in silence (exit 0) and a hunk at line 1 broke every check into dozens of findings. The registry config/practices.json is read the same way. A walk over zero planted faults is a failure.
"""

import json
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
    assert _SECTIONS


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
        except PermissionError as exc:
            assert exc.filename == str(path)
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
    assert done.returncode == 14, done.stdout + done.stderr
    assert "appears twice" in done.stderr, done.stderr
    assert len(done.stderr.splitlines()) == 1
    assert done.stdout == ""


@pytest.mark.parametrize("filename", cs.JSON_CONFIGS)
@pytest.mark.parametrize(
    "fault, expected", [("a key written twice", 14), ("a merge-conflict hunk", 2)]
)
def test_main_refuses_either_config_with_the_named_exit(
    populated_tree, capsys, filename, fault, expected
):
    body, says = _FAULTS[fault]
    (populated_tree / filename).write_bytes(body)
    assert cs.main(["--root", str(populated_tree)]) == expected
    out, err = capsys.readouterr()
    assert out == "" and filename in err and says in err, (out, err)
    assert "Traceback" not in err and len(err.splitlines()) == 1, err


_SECTIONS = [
    (i, j)
    for i, entry in enumerate(
        json.loads((_ROOT / "config/practices.json").read_text())["practices"]
    )
    for j, ref in enumerate(entry["enforced_by"])
    if " §" in ref
]


def _plant_section_fault(populated_tree, position):
    path = populated_tree / "config/practices.json"
    registry = json.loads(path.read_text())
    i, j = position
    registry["practices"][i]["enforced_by"][j] += "@private-payload"
    path.write_text(json.dumps(registry))


@pytest.mark.parametrize("position", _SECTIONS)
def test_each_practice_section_fault_remains_one_redacted_finding(
    populated_tree, position
):
    """Control: the base already reports these faults without a traceback."""
    _plant_section_fault(populated_tree, position)
    found = _errors(populated_tree)
    assert len(found) == 1 and "section" in found[0], found
    assert "private-payload" not in found[0]


@pytest.mark.parametrize("position", _SECTIONS)
def test_each_practice_section_fault_is_config_without_payload(
    populated_tree, capsys, position
):
    _plant_section_fault(populated_tree, position)
    assert cs.main(["--root", str(populated_tree)]) == 14
    i, j = position
    assert set(cs._PRACTICE_SECTION_FAULTS) == {("config/practices.json", i, j)}
    out, err = capsys.readouterr()
    assert "config/practices.json" in err and "private-payload" not in out + err
    assert "Traceback" not in out + err


@pytest.mark.parametrize(
    "section, expected", [("x", 14), ("0_3", 14), ("٣", 14), ("9999", 1), ("3", 0)]
)
def test_an_existing_adr_section_uses_the_grammar(
    populated_tree, capsys, section, expected
):
    path = populated_tree / "config/practices.json"
    registry = json.loads(path.read_text())
    adr = next((populated_tree / "docs/adr/keel").glob("*.md"))
    adr.write_text(adr.read_text() + "\n## 3. Section\n")
    relative = adr.relative_to(populated_tree).as_posix()
    with (populated_tree / "AGENT.md").open("a") as rules:
        rules.write("\nRead `" + relative + "`.\n")
    registry["practices"].append(
        {
            "id": "section-control",
            "enforced_by": ["doc:" + relative + " \u00a7" + section],
        }
    )
    path.write_text(json.dumps(registry))
    assert cs.main(["--root", str(populated_tree)]) == expected
    out, err = capsys.readouterr()
    assert "Traceback" not in out + err
    if expected:
        assert "config/practices.json" in out + err


@pytest.mark.parametrize("shell", [False, True])
def test_source_proof_section_fault_stays_failure(
    populated_tree, capsys, monkeypatch, shell
):
    fields = "title: T\nsummary: S\neffect: writes\nrerun: fixed-point\nrerun_proof: doc:docs/guides/idempotency.md \u00a7x\n"
    source = (
        "#!/bin/sh\n" + "".join("# " + line + "\n" for line in fields.splitlines())
        if shell
        else '"""\n' + fields + '"""\nopen(p, "w")\n'
    )
    path = populated_tree / "scripts" / ("proof.sh" if shell else "proof.py")
    path.write_text(source)
    monkeypatch.setattr(cs, "CHECKS", (("V", cs.check_V),))
    assert cs.main(["--root", str(populated_tree)]) == 1
    out, err = capsys.readouterr()
    assert "rerun_proof" in out and "Traceback" not in out + err
    assert "1 error(s)" in out, out


@pytest.mark.parametrize("fault", ["section", "duplicate", "conflict"])
def test_run_checks_resets_section_and_refusal_provenance(
    populated_tree, capsys, fault
):
    path = populated_tree / "config/practices.json"
    own = path.read_bytes()
    if fault == "section":
        registry = json.loads(own)
        i, j = _SECTIONS[0]
        registry["practices"][i]["enforced_by"][j] += "@private"
        path.write_text(json.dumps(registry))
    else:
        name = (
            "a key written twice" if fault == "duplicate" else "a merge-conflict hunk"
        )
        path.write_bytes(_FAULTS[name][0])
    assert cs.main(["--root", str(populated_tree)]) == (
        2 if fault == "conflict" else 14
    )
    capsys.readouterr()
    assert len(_errors(populated_tree)) == 1
    if fault == "section":
        assert cs._PRACTICE_SECTION_FAULTS and not cs._CONFIG_REFUSALS
    else:
        assert cs._CONFIG_REFUSALS and not cs._PRACTICE_SECTION_FAULTS
    path.write_bytes(own)
    assert _errors(populated_tree) == []
    assert cs._PRACTICE_SECTION_FAULTS == {} and cs._CONFIG_REFUSALS == {}
    assert cs.main(["--root", str(populated_tree)]) == 0
    out, err = capsys.readouterr()
    assert "Traceback" not in out + err
