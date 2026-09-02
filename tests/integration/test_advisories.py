"""
title: Integration — advisory doers never fail the build
kind: tests
layer: n/a
summary: check_practices scans the real tree (config + src/agents) and always exits 0 — an advisory reports, it never gates (CONVENTIONS §18).
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_practices as cp  # noqa: E402

pytestmark = pytest.mark.integration


def test_check_practices_exits_zero_on_the_real_repo():
    assert cp.main([]) == 0


def test_check_practices_json_mode_exits_zero():
    assert cp.main(["--json"]) == 0


def test_registry_and_profiles_load_without_error():
    """The advisor reads config/practices.json + project.json by path; both must
    parse, and `profiles_on()` must AGREE with the manifest.

    It used to assert `profiles_on() == set()` — true of keel, and false of any
    project that answered the `profiles` question the template itself asks. That
    reddened a generated project for a legitimate answer (measured: 2 failures),
    which is CONVENTIONS §18 inverted: the expected value was pasted in rather
    than computed. The invariant that actually holds everywhere is agreement, so
    the manifest is re-read here by the DECLARED rule (`true` exactly, `_`-keys
    skipped) rather than by calling the helper under test."""
    registry = cp.load_registry()
    assert registry.get("practices"), "practices.json should be present and non-empty"

    with open(str(_ROOT / "config" / "project.json"), encoding="utf-8") as fh:
        declared = (json.load(fh).get("practices") or {}).get("profiles") or {}
    expected = {
        name for name, on in declared.items() if on is True and not name.startswith("_")
    }
    assert cp.profiles_on() == expected, (
        "the advisor disagrees with config/project.json about which domain "
        "profiles are enabled: advisor=%s manifest=%s" % (cp.profiles_on(), expected)
    )
