"""
title: Integration — the eval schemas and the parser agree
kind: tests
layer: n/a
summary: config/evals/eval-case.schema.json and evals.parse_cases give the same accept or reject for every shipped case and for each fault twin, under jsonschema's Draft 2020-12 validator (skipped unless the dev extra is installed, a failure when KEEL_REQUIRED_EXTRAS declares it). An id, a hash or an exact answer with a trailing newline is refused by both, since Python's `$` alone would let one through. The rules only the parser can hold, a response hash that does not match its text and a repeated JSON key, are listed as parser-only and must be refused by the parser. The schema's scorer branches name exactly evals.SCORERS with each scorer's required params, its doer enum is evals.DOERS, and its schema_version const is the version the config reads. A real replay report validates against config/evals/eval-report.schema.json, and the report schema's reason, result and outcome vocabularies equal the harness's.
@covers config/evals/eval-case.schema.json
"""

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "tests"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from evals import (  # noqa: E402
    DOERS,
    OUTCOMES,
    REASONS,
    RESULTS,
    SCORERS,
    DatasetError,
    load_config,
    load_suites,
    parse_cases,
)
from test_evals_gate import build_scratch, read_report, run_cli  # noqa: E402

import optional_deps  # noqa: E402

pytestmark = pytest.mark.integration

_CONFIG = load_config(_ROOT)
_SOURCE = "evals/datasets/schema.jsonl"


def _load(rel):
    return json.loads((_ROOT / rel).read_text("utf-8"))


def _validator(rel):
    jsonschema = optional_deps.importorskip("jsonschema", extra="dev")
    schema = _load(rel)
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def _sha(text):
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _base():
    return {
        "schema_version": _CONFIG.schema_version,
        "id": "c-1",
        "input": {"doer": "prompt", "text": "Reply ACK."},
        "scorer": {"name": "exact", "params": {"expected": "ACK"}},
        "recorded": {
            "response": "ACK",
            "sha256": _sha("ACK"),
            "prompt_sha256": _sha("Reply ACK."),
            "source": "authored",
            "model": None,
        },
    }


def _set(path, value):
    obj = _base()
    keys = path.split(".")
    node = obj
    for key in keys[:-1]:
        node = node[key]
    if value is _DROP:
        del node[keys[-1]]
    else:
        node[keys[-1]] = value
    return obj


_DROP = object()

# name -> a case object the parser and the schema must judge alike.
_TWINS = {
    "valid": _base(),
    "model-recording": _set(
        "recorded", dict(_base()["recorded"], source="model", model="m")
    ),
    "missing-top-key": _set("scorer", _DROP),
    "missing-input-key": _set("input.text", _DROP),
    "missing-recorded-key": _set("recorded.prompt_sha256", _DROP),
    "unknown-top-key": _set("note", "x"),
    "unknown-input-key": _set("input.extra", "x"),
    "unknown-scorer-key": _set("scorer.weight", 2),
    "unknown-recorded-key": _set("recorded.when", "today"),
    "schema-version-2": _set("schema_version", 2),
    "bad-id": _set("id", "Bad_Id"),
    "long-id": _set("id", "a" * 65),
    # Python's `$` also matches before a final newline: both sides must close it.
    "id-trailing-newline": _set("id", "c-1\n"),
    "prompt-sha-trailing-newline": _set(
        "recorded.prompt_sha256", _sha("Reply ACK.") + "\n"
    ),
    "exact-trailing-newline": _set("scorer.params.expected", "ACK\n"),
    "unknown-doer": _set("input.doer", "oracle"),
    "empty-text": _set("input.text", ""),
    "unknown-scorer": _set("scorer.name", "judge"),
    "unknown-param": _set("scorer.params.flags", "i"),
    "missing-param": _set("scorer.params", {}),
    "exact-empty": _set("scorer.params.expected", ""),
    "contains-empty": _set("scorer", {"name": "contains", "params": {"substring": ""}}),
    "regex-empty": _set("scorer", {"name": "regex", "params": {"pattern": ""}}),
    "json-fields-empty": _set(
        "scorer", {"name": "json_fields", "params": {"fields": {}}}
    ),
    "json-fields-list": _set(
        "scorer", {"name": "json_fields", "params": {"fields": []}}
    ),
    "response-not-str": _set("recorded.response", 7),
    "bad-sha-pattern": _set("recorded.sha256", "sha256:XYZ"),
    "bad-prompt-sha-pattern": _set("recorded.prompt_sha256", "abc"),
    "unknown-provenance": _set("recorded.source", "guessed"),
    "authored-with-model": _set("recorded.model", "m"),
    "model-without-model": _set("recorded.source", "model"),
    "model-with-empty-model": _set(
        "recorded", dict(_base()["recorded"], source="model", model="")
    ),
}
# Rules a JSON Schema cannot state: the parser alone holds them.
_PARSER_ONLY = {
    "hash-mismatch": json.dumps(_set("recorded.response", "ACK!"), sort_keys=True),
    "duplicate-json-key": '{"id": "a", "id": "b"}',
}


def _parser_accepts(obj):
    try:
        parse_cases(
            json.dumps(obj, sort_keys=True),
            source=_SOURCE,
            schema_version=_CONFIG.schema_version,
        )
    except DatasetError:
        return False
    return True


@pytest.mark.parametrize("name", sorted(_TWINS))
def test_parser_and_schema_agree(name):
    validator = _validator(_CONFIG.case_schema)
    obj = copy.deepcopy(_TWINS[name])
    by_schema = validator.is_valid(obj)
    by_parser = _parser_accepts(obj)
    assert by_schema == by_parser, (name, by_schema, by_parser)
    assert by_parser is (name in ("valid", "model-recording")), name


def test_every_shipped_case_passes_the_schema():
    validator = _validator(_CONFIG.case_schema)
    paths = sorted((_ROOT / _CONFIG.dataset_dir).iterdir())
    assert paths
    lines = [line for p in paths for line in p.read_text("utf-8").splitlines()]
    assert lines
    for line in lines:
        errors = list(validator.iter_errors(json.loads(line)))
        assert not errors, (line, [e.message for e in errors])
    assert sum(len(s.cases) for s in load_suites(_CONFIG, _ROOT)) == len(lines)


@pytest.mark.parametrize("name", sorted(_PARSER_ONLY))
def test_the_parser_only_rules_are_refused(name):
    with pytest.raises(DatasetError):
        parse_cases(_PARSER_ONLY[name], source=_SOURCE, schema_version=1)


def test_the_case_schema_names_the_registries():
    schema = _load(_CONFIG.case_schema)
    assert schema["properties"]["schema_version"]["const"] == _CONFIG.schema_version
    assert set(schema["properties"]["input"]["properties"]["doer"]["enum"]) == set(
        DOERS
    )
    branches = schema["properties"]["scorer"]["oneOf"]
    names = {b["properties"]["name"]["const"]: b for b in branches}
    assert set(names) == set(SCORERS)
    for name, branch in names.items():
        params = branch["properties"]["params"]
        assert set(params["required"]) == set(SCORERS[name].params), name
        assert set(params["properties"]) == set(SCORERS[name].params), name


def test_the_report_schema_names_the_vocabularies():
    schema = _load(_CONFIG.report_schema)
    props = schema["properties"]
    assert props["schema_version"]["const"] == _CONFIG.report_schema_version
    assert set(props["result"]["enum"]) == set(RESULTS)
    assert set(props["reasons"]["items"]["enum"]) == set(REASONS)
    case = props["suites"]["items"]["properties"]["cases"]["items"]
    assert set(case["properties"]["outcome"]["enum"]) == set(OUTCOMES)


def test_a_real_report_validates(tmp_path):
    validator = _validator(_CONFIG.report_schema)
    repo, env = build_scratch(tmp_path)
    assert run_cli(repo, env).returncode == 0
    report = read_report(repo)
    errors = [e.message for e in validator.iter_errors(report)]
    assert not errors, errors
    for fault in ({"extra": 1}, {"result": "maybe"}, {"calls": -1}, {"threshold": 0}):
        assert not validator.is_valid(dict(report, **fault)), fault
    case = report["suites"][0]["cases"][0]
    for field in ("id", "response_sha256"):
        bad = copy.deepcopy(report)
        bad["suites"][0]["cases"][0][field] = case[field] + "\n"
        assert not validator.is_valid(bad), field
