"""
title: Unit — eval scorers, the closed registry
kind: tests
layer: n/a
summary: Every scorer in evals.SCORERS has a passing and a failing twin in one table held equal to the registry, so a scorer added without both twins, or a score() that always passes, is red; json_fields compares canonical JSON (true is not 1, 1 is not 1.0) and fails a response that is not a JSON object instead of raising; check_params refuses an unknown key, a missing key, an uncompilable or empty pattern, an empty substring, an expected value with surrounding whitespace or of the wrong type, and an empty field object.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from evals import SCORERS  # noqa: E402

pytestmark = pytest.mark.unit

THREE = "line one\nline two\nline three"
TWO = "line one\nline two"
LINES = r"\A[^\n]+\n[^\n]+\n[^\n]+\Z"

# name -> (passing (response, params), failing (response, params)). The set of
# names is held equal to SCORERS below, so a new scorer needs both twins here.
TWINS = {
    "exact": (("ACK\n", {"expected": "ACK"}), ("ACK.", {"expected": "ACK"})),
    "contains": (
        ("disk full", {"substring": "disk"}),
        ("Disk", {"substring": "disk"}),
    ),
    "regex": ((THREE, {"pattern": LINES}), (TWO, {"pattern": LINES})),
    "json_fields": (
        ('{"severity":"high"}', {"fields": {"severity": "high"}}),
        ('{"severity":"low"}', {"fields": {"severity": "high"}}),
    ),
}


def test_the_twin_table_covers_exactly_the_registry():
    assert set(TWINS) == set(SCORERS)
    for name, scorer in SCORERS.items():
        assert scorer.name == name


@pytest.mark.parametrize("name", sorted(TWINS))
def test_each_scorer_has_a_pass_and_a_fail_twin(name):
    scorer = SCORERS[name]
    (good, good_params), (bad, bad_params) = TWINS[name]
    scorer.check_params(good_params)
    scorer.check_params(bad_params)
    passed, detail = scorer.score(good, good_params)
    assert passed is True, detail
    failed, detail = scorer.score(bad, bad_params)
    assert failed is False, detail
    assert isinstance(detail, str) and detail


def test_regex_searches_so_anchoring_is_the_patterns_job():
    # re.search, not re.fullmatch: a pattern matches anywhere unless the case
    # anchors it, as the shipped three-line case does with \A and \Z.
    scorer = SCORERS["regex"]
    passed, detail = scorer.score("the disk is full", {"pattern": "disk"})
    assert passed is True, detail
    passed, detail = scorer.score("the disk is full", {"pattern": r"\Adisk"})
    assert passed is False, detail


@pytest.mark.parametrize(
    "response, fields, expected",
    [
        ('{"n": true}', {"n": 1}, False),
        ('{"n": 1.0}', {"n": 1}, False),
        ('{"n": 1}', {"n": 1}, True),
        ('{"m": 1}', {"n": 1}, False),
        ("[1]", {"n": 1}, False),
        ("not json", {"n": 1}, False),
        ("", {"n": 1}, False),
        ('{"n": 1, "n": 2}', {"n": 2}, False),
        ('{"n": 1, "extra": "kept"}', {"n": 1}, True),
        ('  {"o": {"b": 1, "a": 2}}\n', {"o": {"a": 2, "b": 1}}, True),
    ],
)
def test_json_fields_is_type_strict_and_fails_non_objects(response, fields, expected):
    passed, detail = SCORERS["json_fields"].score(response, {"fields": fields})
    assert passed is expected, detail


@pytest.mark.parametrize(
    "name, params",
    [
        ("exact", {"expected": "ACK", "flags": "i"}),
        ("exact", {}),
        ("exact", {"expected": " ACK"}),
        ("exact", {"expected": ""}),
        ("exact", {"expected": 1}),
        ("contains", {"substring": ""}),
        ("contains", {"substring": None}),
        ("regex", {"pattern": "("}),
        ("regex", {"pattern": ""}),
        ("json_fields", {"fields": {}}),
        ("json_fields", {"fields": ["severity"]}),
    ],
)
def test_check_params_refuses_bad_params(name, params):
    with pytest.raises(ValueError):
        SCORERS[name].check_params(params)


def test_the_registry_is_read_only():
    with pytest.raises(TypeError):
        SCORERS["always"] = SCORERS["exact"]
