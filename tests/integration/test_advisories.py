"""
title: Integration — advisory doers never fail the build
kind: tests
layer: n/a
summary: check_practices scans the real tree (config + src/agents) and always exits 0 — an advisory reports, it never gates (CONVENTIONS §18).
"""

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
    parse and the domain profiles default to off (none enabled in this repo)."""
    registry = cp.load_registry()
    assert registry.get("practices"), "practices.json should be present and non-empty"
    assert cp.profiles_on() == set(), "no domain profile is enabled by default"
