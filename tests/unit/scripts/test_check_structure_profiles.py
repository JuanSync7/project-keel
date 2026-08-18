"""
title: Unit — check_structure check_H (practices.profiles validation)
kind: tests
layer: n/a
summary: check_H's profiles validation errs on a non-boolean enable-flag (provable), only WARNs on an enabled flag that names no defined profile (inert — activates nothing), and suppresses even that WARN whenever the registry's defined-profile set cannot be authoritatively determined — so a registry typo never breaks a consuming repo's build.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit

_DEFINED = {"ai", "cuda", "langgraph"}


def _find(profiles, defined=_DEFINED):
    return cs._profile_flag_findings(profiles, defined)


# --- ERR: a non-boolean enable flag (provable) -------------------------------


@pytest.mark.parametrize("val, kind", [(1, "int"), (1.0, "float"), ("yes", "str")])
def test_non_boolean_flag_errors(val, kind):
    errs, warns = _find({"cuda": val})
    assert len(errs) == 1 and ("not %s" % kind) in errs[0]
    assert warns == []


def test_true_and_false_are_accepted_as_booleans():
    errs, warns = _find({"cuda": True, "ai": False})
    assert errs == [] and warns == []


# --- WARN (not err): enabled flag names an undefined profile -----------------


def test_enabled_undefined_profile_warns_but_does_not_error():
    errs, warns = _find({"quantum": True})
    assert errs == []
    assert len(warns) == 1 and "activate nothing" in warns[0]


def test_disabled_undefined_profile_is_inert_no_warn():
    assert _find({"quantum": False}) == ([], [])


def test_comment_key_is_skipped():
    assert _find({"_comment": "x", "cuda": True}) == ([], [])


# --- cannot-determine defined set (None) suppresses the undefined-WARN --------


def test_undefined_warn_suppressed_when_defined_is_unknown():
    # A registry-side typo (profiles unreadable) must not fail a consuming build.
    errs, warns = _find({"cuda": True}, defined=None)
    assert errs == [] and warns == []
    # ...but a genuine TYPE error still fires regardless of the registry state.
    errs2, _ = _find({"cuda": 1}, defined=None)
    assert len(errs2) == 1


# --- _defined_profile_names reads the real registry --------------------------


def test_defined_profile_names_reads_the_real_registry():
    names = cs._defined_profile_names()
    assert names is not None and {"ai", "cuda", "langgraph"} <= names
