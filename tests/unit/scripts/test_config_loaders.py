"""
title: Unit — check_structure config loaders (absent vs malformed)
kind: tests
layer: n/a
summary: Every file the gate reads to decide WHETHER to gate must distinguish two cases — absent (a legitimate downstream shape, degrade in silence) from present-but-unreadable (a gate defect: the checks keyed on that file stop gating while the run still exits 0). Pins the class over both JSON registries (config/practices.json, config/project.json), pyproject.toml and check_G's markdown readers, and pins that one broken file yields exactly one finding, not one per consumer.
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit

# A file that exists but cannot be turned into the data the gate needs. Both
# forms must be reported: JSON that does not parse, and bytes that are not UTF-8.
BAD_JSON = '{"rulesets":'
BAD_BYTES = b"\xff\xfe\x00 not utf-8"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A throwaway repo root with the gate's module-level state isolated."""
    monkeypatch.setattr(cs, "ROOT", str(tmp_path))
    monkeypatch.setattr(cs, "errors", [])
    monkeypatch.setattr(cs, "warnings", [])
    # raising=False so this file runs (and fails for the right reason) against
    # the pre-fix module, which has no read caches yet.
    monkeypatch.setattr(cs, "_CONFIG_READ", {}, raising=False)
    monkeypatch.setattr(cs, "_READ_REPORTED", set(), raising=False)
    (tmp_path / "config").mkdir()
    return tmp_path


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding="utf-8")


def _mentions(findings, name):
    return [f for f in findings if name in f]


def _read_failure(findings, name):
    """Findings that name the file AND say it could not be read.

    Merely mentioning the file is not enough: check_G's degraded path already
    emits a MISLEADING finding against the readable side of the pair ("...'Used
    by' names agents/a but its tools.md omits 'x'"), which would satisfy a
    name-only assertion while the real cause went unreported.
    """
    return [
        f
        for f in _mentions(findings, name)
        if "unreadable" in f or "cannot read" in f or "could not read" in f
    ]


# --- MUST-REPORT: the file is there but the gate cannot read it --------------


@pytest.mark.parametrize(
    "payload", [BAD_JSON, BAD_BYTES], ids=["bad-json", "bad-bytes"]
)
def test_unreadable_practices_json_is_reported(repo, payload):
    """A malformed practices.json turns check_K/L/M off; that must not be silent."""
    _write(repo / "config" / "practices.json", payload)
    assert cs._load_practices() == {}  # still degrades, so no traceback
    assert _mentions(cs.errors, "config/practices.json"), cs.errors


@pytest.mark.parametrize(
    "payload", [BAD_JSON, BAD_BYTES], ids=["bad-json", "bad-bytes"]
)
def test_unreadable_project_json_is_reported_by_profiles_on(repo, payload):
    """_profiles_on() gates check_L; an unreadable manifest must not disable it
    silently, and check_H already errs on this same file (one file, one voice)."""
    _write(repo / "config" / "project.json", payload)
    assert cs._profiles_on() == set()
    assert _mentions(cs.errors, "config/project.json"), cs.errors


@pytest.mark.parametrize(
    "payload", [BAD_JSON, BAD_BYTES], ids=["bad-json", "bad-bytes"]
)
def test_check_M_is_not_silently_disabled_by_an_unreadable_practices_json(
    repo, payload
):
    """The end-to-end shape of the defect: check_M is the meta-gate proving
    pyproject cannot loosen the declared policy. Today an unreadable registry
    makes it return at its first line with no finding at all."""
    _write(repo / "config" / "practices.json", payload)
    _write(repo / "pyproject.toml", '[tool.ruff.lint]\nextend-select = ["I"]\n')
    cs.check_M()
    assert cs.errors + cs.warnings, "check_M went vacuous with no finding"


def test_check_L_is_not_silently_disabled_by_an_unreadable_project_json(repo):
    """check_L is keyed on a profile flag read from project.json: unreadable ->
    'cuda' is absent -> the whole check returns before doing any work."""
    _write(repo / "config" / "project.json", BAD_JSON)
    _write(
        repo / "config" / "practices.json",
        json.dumps({"tokens": {"tensor_base_types": ["Tensor"]}}),
    )
    _write(repo / "src" / "m.py", "def step(x: Tensor):\n    return x\n")
    cs.check_L()
    assert _mentions(cs.errors, "config/project.json"), cs.errors


def test_unreadable_pyproject_is_reported_by_requires_python(repo):
    """_requires_python() feeds check_H's backend-python conformance check."""
    _write(repo / "pyproject.toml", BAD_BYTES)
    assert cs._requires_python() is None
    assert _mentions(cs.errors, "pyproject.toml"), cs.errors


def test_unreadable_tool_spec_is_reported(repo):
    """check_G cross-checks two markdown sides. An unreadable side degrades to
    an empty list, so the governance check goes vacuous — or worse, the ASYMMETRY
    produces a misleading 'omits' error against the readable side."""
    _write(repo / "agents" / "tools" / "x.tool.md", BAD_BYTES)
    _write(repo / "agents" / "a" / "tools.md", "see ../tools/x.tool.md\n")
    cs.check_G()
    assert _read_failure(cs.errors, "x.tool.md"), cs.errors


def test_unreadable_agent_manifest_is_reported(repo):
    """The other side of the same cross-check."""
    _write(repo / "agents" / "tools" / "x.tool.md", "## Used by\n- agents/a\n")
    _write(repo / "agents" / "a" / "tools.md", BAD_BYTES)
    cs.check_G()
    assert _read_failure(cs.errors, "tools.md"), cs.errors


# --- MUST-STAY-SILENT: absent is a legitimate shape, not a defect ------------
#
# copier prunes files a generated project did not select, so "not there" must
# never fail. This is the boundary the fix must not break.


def test_absent_practices_json_degrades_quietly(repo):
    assert cs._load_practices() == {}
    assert cs.errors == [] and cs.warnings == []


def test_absent_project_json_degrades_quietly(repo):
    assert cs._profiles_on() == set()
    assert cs.errors == [] and cs.warnings == []


def test_absent_pyproject_degrades_quietly(repo):
    assert cs._requires_python() is None
    assert cs.errors == [] and cs.warnings == []


def test_absent_practices_json_leaves_check_M_quiet(repo):
    _write(repo / "pyproject.toml", '[tool.ruff.lint]\nextend-select = ["I"]\n')
    cs.check_M()
    assert cs.errors == [] and cs.warnings == []


def test_a_json_null_manifest_is_still_a_shape_error_not_a_read_error(repo):
    """`null` PARSES: the file is readable, it is just not an object. That must
    keep reaching check_H's shape check rather than being mistaken for a failed
    read — the two degrade paths must not collapse back into each other."""
    _write(repo / "config" / "project.json", "null")
    cs.check_H()
    assert _mentions(cs.errors, "top level must be a JSON object"), cs.errors


def test_valid_registries_produce_no_read_findings(repo):
    _write(repo / "config" / "practices.json", json.dumps({"tokens": {}}))
    _write(
        repo / "config" / "project.json",
        json.dumps({"practices": {"profiles": {"cuda": True, "_note": True}}}),
    )
    assert cs._load_practices() == {"tokens": {}}
    assert cs._profiles_on() == {"cuda"}
    assert cs.errors == [] and cs.warnings == []


# --- ONE broken file, ONE finding -------------------------------------------


def test_one_unreadable_registry_is_reported_once_not_once_per_consumer(repo):
    """practices.json has four readers (_load_practices, _defined_profile_names,
    _stdlib_exc_modules and the check_K/L/M consumers). A reader that reports
    per-call would turn one broken file into a wall of duplicate errors."""
    _write(repo / "config" / "practices.json", BAD_JSON)
    _write(repo / "pyproject.toml", '[tool.ruff.lint]\nextend-select = ["I"]\n')
    cs._load_practices()
    cs._load_practices()
    cs._stdlib_exc_modules()
    cs._defined_profile_names()
    cs.check_M()
    hits = _mentions(cs.errors + cs.warnings, "config/practices.json")
    assert len(hits) == 1, hits
