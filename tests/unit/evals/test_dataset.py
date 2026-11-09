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
import traceback
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from evals import (  # noqa: E402
    SCORERS,
    Case,
    DatasetError,
    EvalConfig,
    load_suites,
    parse_cases,
)
from scripts import config_loader  # noqa: E402

pytestmark = pytest.mark.unit

SOURCE = "evals/datasets/unit.jsonl"
SHA_ZERO = "sha256:" + "0" * 64


def _sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _case(case_id: str = "c-1", response: str = "ACK\n") -> dict[str, Any]:
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


def _line(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _parse(text: str) -> list[Case]:
    return parse_cases(text, source=SOURCE, schema_version=1, scorers=SCORERS)


def _mutated(path: str, value: object) -> str:
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


def test_a_valid_case_parses_into_a_typed_case() -> None:
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


def test_a_bom_crlf_and_a_missing_final_newline_are_tolerated() -> None:
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
    ("schema-version-bool", _mutated("schema_version", value=True), ":1:"),
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
def test_parse_refuses_each_malformed_shape(text: str, where: str) -> None:
    with pytest.raises(DatasetError) as info:
        _parse(text)
    assert SOURCE + where in str(info.value), str(info.value)


def test_a_response_hash_mismatch_names_the_actual_hash() -> None:
    obj = _case()
    obj["recorded"]["response"] = "ACK!"
    with pytest.raises(DatasetError) as info:
        _parse(_line(obj))
    assert _sha("ACK!") in str(info.value), str(info.value)
    assert SOURCE + ":1:" in str(info.value)


def test_duplicate_id_and_empty_dataset_are_errors() -> None:
    text = _line(_case("dup")) + "\n" + _line(_case("ok")) + "\n" + _line(_case("dup"))
    with pytest.raises(DatasetError) as info:
        _parse(text)
    message = str(info.value)
    assert SOURCE + ":1" in message and SOURCE + ":3" in message, message
    for empty in ("", "\n", "﻿"):
        with pytest.raises(DatasetError) as info:
            _parse(empty)
        assert "no cases" in str(info.value), str(info.value)


def test_a_model_recording_carries_its_model_name() -> None:
    obj = _case()
    obj["recorded"]["source"] = "model"
    obj["recorded"]["model"] = "openai-compatible"
    (case,) = _parse(_line(obj))
    assert (case.rec_source, case.rec_model) == ("model", "openai-compatible")


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "empty",
        "stray",
        "name",
        "unreadable",
        "invalid",
        "duplicate",
        "listing",
    ],
)
def test_load_suites_hides_configured_paths_in_every_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    rel = "datasets/user:DATASET_SENTINEL@host"
    base = tmp_path / rel
    cfg = EvalConfig("case.json", "report.json", rel, "reports", 1.0, None, 0)
    if fault != "missing":
        base.mkdir(parents=True)
    if fault == "listing":
        import os

        real_listdir = os.listdir

        def listdir(path: str) -> list[str]:
            if path == str(base):
                raise OSError(13, "Permission denied", path)
            return real_listdir(path)

        monkeypatch.setattr(os, "listdir", listdir)
    if fault == "stray":
        (base / "stray.txt").write_text("x", encoding="utf-8")
    elif fault == "name":
        (base / "Bad.jsonl").write_text("x", encoding="utf-8")
    elif fault == "unreadable":
        (base / "one.jsonl").write_bytes(b"\xff")
    elif fault == "invalid":
        (base / "one.jsonl").write_text("{}", encoding="utf-8")
    elif fault == "duplicate":
        for name in ("one", "two"):
            (base / (name + ".jsonl")).write_text(_line(_case()), encoding="utf-8")
    with pytest.raises(DatasetError) as refused:
        load_suites(cfg, tmp_path)
    printed = "".join(traceback.format_exception(refused.value))
    assert "DATASET_SENTINEL" not in printed
    assert "<hidden: it holds an @>" in str(refused.value)


def test_load_suites_keeps_actual_paths_in_successful_records(tmp_path: Path) -> None:
    rel = "datasets/user@host"
    base = tmp_path / rel
    base.mkdir(parents=True)
    (base / "one.jsonl").write_text(_line(_case()), encoding="utf-8")
    cfg = EvalConfig("case.json", "report.json", rel, "reports", 1.0, None, 0)
    (suite,) = load_suites(cfg, tmp_path)
    assert suite.dataset == rel + "/one.jsonl"
    assert suite.cases[0].source == rel + "/one.jsonl:1"


@pytest.mark.parametrize(
    "rel", ["datasets/plain", "datasets/user:DETAIL_SENTINEL@host"]
)
@pytest.mark.parametrize(
    "text, detail",
    [
        ("{bad json", ":1: not valid JSON"),
        ("{}", ":1: missing key case.id"),
        (_mutated("scorer.params", {}), ":1: scorer.params:"),
        (_line(_case()) + "\n\n" + _line(_case("other")), ":2: blank line"),
        (
            _line(_case()) + "\n" + _line(_case()),
            ":2: duplicate id 'c-1' (first at {source}:1)",
        ),
        ("", ": no cases;"),
        (
            _mutated("id", "bad@id"),
            ":1: id '<hidden: it holds an @>' must match",
        ),
    ],
    ids=["json", "shape", "params", "blank", "duplicate", "empty", "reason-at"],
)
def test_load_suites_keeps_refusal_detail_and_safe_causes(
    tmp_path: Path, rel: str, text: str, detail: str
) -> None:
    base = tmp_path / rel
    base.mkdir(parents=True)
    (base / "one.jsonl").write_text(text, encoding="utf-8")
    cfg = EvalConfig("case.json", "report.json", rel, "reports", 1.0, None, 0)
    source = rel + "/one.jsonl"
    shown = config_loader.shown(source, bare=True)
    with pytest.raises(DatasetError) as refused:
        load_suites(cfg, tmp_path)
    error = refused.value
    assert str(error).startswith(shown + detail.format(source=shown))
    assert isinstance(error.__cause__, DatasetError)
    if "@" not in source:
        # Ordinary paths must retain the parser's exact diagnostic.
        with pytest.raises(DatasetError) as parsed:
            parse_cases(text, source=source, schema_version=1)
        assert str(error) == str(parsed.value)
    if detail.startswith((":1:", ":2: blank")):
        assert error.__cause__.__cause__ is not None
    # Suppressed contexts still hold exceptions, so inspect both chain links.
    pending: list[BaseException] = [error]
    seen = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if "@" in source:
            assert rel not in str(current)
            assert rel not in repr(current.args)
            assert "DETAIL_SENTINEL" not in str(current)
            assert "DETAIL_SENTINEL" not in repr(current.args)
        pending.extend(
            linked
            for linked in (current.__cause__, current.__context__)
            if linked is not None
        )


@pytest.mark.parametrize(
    "text, detail",
    [
        (_mutated("id", "private@value"), "id '<hidden: it holds an @>' must match"),
        (
            _mutated("input.doer", "private@value"),
            "input.doer '<hidden: it holds an @>' is not one of",
        ),
        (
            _mutated("scorer.name", "private@value"),
            "scorer.name '<hidden: it holds an @>' is not one of",
        ),
        (
            _mutated("recorded.source", "private@value"),
            "recorded.source '<hidden: it holds an @>' is not one of",
        ),
        (
            _mutated("schema_version", {"private@value": 1}),
            "schema_version is <hidden: it holds an @>;",
        ),
        (
            '{"private@value":1,"private@value":2}',
            "repeated JSON key <hidden: it holds an @>",
        ),
        (
            _mutated("scorer.params.private@value", 1),
            "scorer.params: <hidden: it holds an @>",
        ),
        ('"\\qprivate@value"', "not valid JSON (<hidden: it holds an @>)"),
        (_mutated("private@value", 1), "unknown key case.<hidden: it holds an @>"),
        (
            _mutated("input.private@value", 1),
            "unknown key input.<hidden: it holds an @>",
        ),
        (
            _mutated(
                "scorer",
                {"name": "regex", "params": {"pattern": "(?P<private@value>x)"}},
            ),
            "scorer.params: <hidden: it holds an @>",
        ),
    ],
    ids=[
        "id",
        "doer",
        "scorer",
        "recorded-source",
        "schema-version",
        "repeated-key",
        "params-message",
        "json-decode",
        "unknown-key",
        "nested-key",
        "regex-chain",
    ],
)
@pytest.mark.parametrize("via_loader", [False, True])
def test_file_values_are_hidden_throughout_the_exception_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    text: str,
    detail: str,
    *,
    via_loader: bool,
) -> None:
    if text == '"\\qprivate@value"':
        real_loads = json.loads

        def loads(document: str, **kwargs: Any) -> Any:
            # Exercise decoder text that echoes input, independent of Python's wording.
            if document == text:
                raise json.JSONDecodeError(
                    "decoder excerpt: private@value", document, 1
                )
            return real_loads(document, **kwargs)

        monkeypatch.setattr(json, "loads", loads)
    with pytest.raises(DatasetError) as refused:
        if via_loader:
            base = tmp_path / "datasets"
            base.mkdir()
            (base / "one.jsonl").write_text(text, encoding="utf-8")
            cfg = EvalConfig(
                "case.json", "report.json", "datasets", "reports", 1.0, None, 0
            )
            load_suites(cfg, tmp_path)
        else:
            _parse(text)
    assert ":1: " + detail in str(refused.value)
    assert refused.value.__cause__ is not None
    # Both links matter: `from None` would still retain an unsafe context.
    pending: list[BaseException] = [refused.value]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        assert "private@value" not in str(current)
        assert "private@value" not in repr(current.args)
        pending.extend(
            linked
            for linked in (current.__cause__, current.__context__)
            if linked is not None
        )
