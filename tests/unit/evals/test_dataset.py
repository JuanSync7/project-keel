"""
title: Unit — eval dataset parser
kind: tests
layer: n/a
summary: parse_cases reads a JSONL string with no disk: a valid case parses, a byte-order mark and CRLF endings are tolerated, and every malformed shape the case schema forbids (invalid JSON, a non-object, a blank interior line, a duplicate key, a missing or unknown key at any level, a wrong schema_version, id, doer, scorer, param or hash pattern, an id or hash with a trailing newline, a response hash that does not match, and provenance that contradicts itself) is a DatasetError naming source:line; a duplicate id names both lines and an empty text is "no cases", never an empty pass.
"""

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from evals import SCORERS, DatasetError, parse_cases  # noqa: E402

pytestmark = pytest.mark.unit

SOURCE = "evals/datasets/unit.jsonl"
SHA_ZERO = "sha256:" + "0" * 64


def _sha(text):
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _case(case_id="c-1", response="ACK\n"):
    return {
        "schema_version": 1,
        "id": case_id,
        "input": {"doer": "prompt", "text": "Reply ACK."},
        "scorer": {"name": "exact", "params": {"expected": "ACK"}},
        "recorded": {
            "response": response,
            "sha256": _sha(response),
            "prompt_sha256": SHA_ZERO,
            "source": "authored",
            "model": None,
        },
    }


def _line(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _parse(text):
    return parse_cases(text, source=SOURCE, schema_version=1, scorers=SCORERS)


def _mutated(path, value):
    """A copy of _case() with the dotted *path* set to *value*, or removed
    when *value* is _DROP."""
    obj = copy.deepcopy(_case())
    keys = path.split(".")
    node = obj
    for key in keys[:-1]:
        node = node[key]
    if value is _DROP:
        del node[keys[-1]]
    else:
        node[keys[-1]] = value
    return _line(obj)


_DROP = object()


def test_a_valid_case_parses_into_a_typed_case():
    (case,) = _parse(_line(_case()) + "\n")
    assert case.id == "c-1"
    assert case.suite == "unit"
    assert case.source == SOURCE + ":1"
    assert (case.doer, case.text) == ("prompt", "Reply ACK.")
    assert (case.scorer_name, case.params) == ("exact", {"expected": "ACK"})
    assert case.response == "ACK\n"
    assert case.response_sha256 == _sha("ACK\n")
    assert case.prompt_sha256 == SHA_ZERO
    assert (case.rec_source, case.rec_model) == ("authored", None)


def test_a_bom_crlf_and_a_missing_final_newline_are_tolerated():
    text = "﻿" + _line(_case("a")) + "\r\n" + _line(_case("b"))
    assert [c.id for c in _parse(text)] == ["a", "b"]


_FAULTS = [
    ("invalid-json", "{not json", ":1:"),
    ("non-object", "[1, 2]", ":1:"),
    ("blank-interior", _line(_case("a")) + "\n\n" + _line(_case("b")), ":2:"),
    ("duplicate-key", '{"id": "a", "id": "b"}', ":1:"),
    ("missing-top-key", _mutated("scorer", _DROP), ":1:"),
    ("missing-input-key", _mutated("input.text", _DROP), ":1:"),
    ("missing-recorded-key", _mutated("recorded.prompt_sha256", _DROP), ":1:"),
    ("unknown-top-key", _mutated("note", "x"), ":1:"),
    ("unknown-input-key", _mutated("input.extra", "x"), ":1:"),
    ("unknown-scorer-key", _mutated("scorer.weight", 2), ":1:"),
    ("unknown-recorded-key", _mutated("recorded.when", "today"), ":1:"),
    ("schema-version-2", _mutated("schema_version", 2), ":1:"),
    ("schema-version-bool", _mutated("schema_version", True), ":1:"),
    ("bad-id", _mutated("id", "Bad_Id"), ":1:"),
    # `$` alone also matches before a final newline; the formats are closed.
    ("id-trailing-newline", _mutated("id", "c-1\n"), ":1:"),
    ("unknown-doer", _mutated("input.doer", "oracle"), ":1:"),
    ("empty-text", _mutated("input.text", ""), ":1:"),
    ("unknown-scorer", _mutated("scorer.name", "judge"), ":1:"),
    ("unknown-param", _mutated("scorer.params.flags", "i"), ":1:"),
    ("missing-param", _mutated("scorer.params", {}), ":1:"),
    ("response-not-str", _mutated("recorded.response", 7), ":1:"),
    ("bad-sha-pattern", _mutated("recorded.sha256", "sha256:XYZ"), ":1:"),
    ("bad-prompt-sha-pattern", _mutated("recorded.prompt_sha256", "abc"), ":1:"),
    (
        "prompt-sha-trailing-newline",
        _mutated("recorded.prompt_sha256", SHA_ZERO + "\n"),
        ":1:",
    ),
    ("unknown-provenance", _mutated("recorded.source", "guessed"), ":1:"),
    ("authored-with-model", _mutated("recorded.model", "gpt"), ":1:"),
    (
        "model-without-model",
        _mutated("recorded.source", "model"),
        ":1:",
    ),
]


@pytest.mark.parametrize(
    "text, where", [(t, w) for _n, t, w in _FAULTS], ids=[n for n, _t, _w in _FAULTS]
)
def test_parse_refuses_each_malformed_shape(text, where):
    with pytest.raises(DatasetError) as info:
        _parse(text)
    assert SOURCE + where in str(info.value), str(info.value)


def test_a_response_hash_mismatch_names_the_actual_hash():
    obj = _case()
    obj["recorded"]["response"] = "ACK!"
    with pytest.raises(DatasetError) as info:
        _parse(_line(obj))
    assert _sha("ACK!") in str(info.value), str(info.value)
    assert SOURCE + ":1:" in str(info.value)


def test_duplicate_id_and_empty_dataset_are_errors():
    text = _line(_case("dup")) + "\n" + _line(_case("ok")) + "\n" + _line(_case("dup"))
    with pytest.raises(DatasetError) as info:
        _parse(text)
    message = str(info.value)
    assert SOURCE + ":1" in message and SOURCE + ":3" in message, message
    for empty in ("", "\n", "﻿"):
        with pytest.raises(DatasetError) as info:
            _parse(empty)
        assert "no cases" in str(info.value), str(info.value)


def test_a_model_recording_carries_its_model_name():
    obj = _case()
    obj["recorded"]["source"] = "model"
    obj["recorded"]["model"] = "openai-compatible"
    (case,) = _parse(_line(obj))
    assert (case.rec_source, case.rec_model) == ("model", "openai-compatible")
