"""
title: Unit — eval configuration, refused by its dotted key
kind: tests
layer: n/a
summary: parse_config reads the config/project.json `evals` block from a dict and the case and report schemas through an injected reader, so no disk is touched; each bad value (a threshold outside 0 < t <= 1 or of the wrong type, a negative or non-integer max_calls, an empty or non-string model, non-object model_options, an absolute or parent-escaping path, a missing block, a missing or unknown key) is a ConfigError naming the dotted key, an int threshold of 1 is accepted, and schema_version comes from the schema's const, never from code. A refusal carries the `evals.report_dir` it could still read as a safe relative path (None when that key itself is bad), so the CLI can remove a stale report.
"""

import copy
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from evals import ConfigError, parse_config  # noqa: E402

pytestmark = pytest.mark.unit

_BLOCK = {
    "_comment": "x",
    "case_schema": "config/evals/eval-case.schema.json",
    "report_schema": "config/evals/eval-report.schema.json",
    "dataset_dir": "evals/datasets",
    "report_dir": ".evidence/evals",
    "threshold": 1.0,
    "live": {"model": None, "max_calls": 0, "model_options": {}},
}


def _schema(version=1):
    return {"properties": {"schema_version": {"const": version}}}


def _parse(block, read=None):
    return parse_config({"evals": block}, read or (lambda _rel: _schema()))


def _with(path, value):
    block = copy.deepcopy(_BLOCK)
    keys = path.split(".")
    node = block
    for key in keys[:-1]:
        node = node[key]
    if value is _DROP:
        del node[keys[-1]]
    else:
        node[keys[-1]] = value
    return block


_DROP = object()


def test_the_shipped_shape_parses():
    cfg = _parse(copy.deepcopy(_BLOCK))
    assert cfg.threshold == 1.0
    assert (cfg.live_model, cfg.live_max_calls, cfg.live_model_options) == (None, 0, {})
    assert (cfg.dataset_dir, cfg.report_dir) == ("evals/datasets", ".evidence/evals")
    assert (cfg.schema_version, cfg.report_schema_version) == (1, 1)
    assert _parse(_with("threshold", 1)).threshold == 1
    assert _parse(_with("live.model", "fake")).live_model == "fake"


@pytest.mark.parametrize(
    "path, value, key",
    [
        ("threshold", 0, "evals.threshold"),
        ("threshold", 1.5, "evals.threshold"),
        ("threshold", True, "evals.threshold"),
        ("threshold", "1", "evals.threshold"),
        ("threshold", _DROP, "evals.threshold"),
        ("live.max_calls", -1, "evals.live.max_calls"),
        ("live.max_calls", True, "evals.live.max_calls"),
        ("live.max_calls", 1.5, "evals.live.max_calls"),
        ("live.model", "", "evals.live.model"),
        ("live.model", 3, "evals.live.model"),
        ("live.model_options", [], "evals.live.model_options"),
        ("live", [], "evals.live"),
        ("live.extra", 1, "evals.live.extra"),
        ("dataset_dir", "/abs/datasets", "evals.dataset_dir"),
        ("dataset_dir", "", "evals.dataset_dir"),
        ("report_dir", "../outside", "evals.report_dir"),
        ("report_dir", 7, "evals.report_dir"),
        ("case_schema", _DROP, "evals.case_schema"),
        ("extra", 1, "evals.extra"),
    ],
)
def test_config_refuses_each_bad_value_by_dotted_key(path, value, key):
    with pytest.raises(ConfigError) as info:
        _parse(_with(path, value))
    assert key in str(info.value), str(info.value)


def test_a_missing_block_or_schema_version_is_refused():
    with pytest.raises(ConfigError) as info:
        parse_config({}, lambda _rel: _schema())
    assert "evals" in str(info.value)
    with pytest.raises(ConfigError) as info:
        parse_config({"evals": []}, lambda _rel: _schema())
    assert "evals" in str(info.value)
    with pytest.raises(ConfigError) as info:
        _parse(copy.deepcopy(_BLOCK), lambda _rel: {"properties": {}})
    assert "config/evals/eval-case.schema.json" in str(info.value)
    with pytest.raises(ConfigError):
        _parse(copy.deepcopy(_BLOCK), lambda _rel: _schema(True))
    read = []
    _parse(copy.deepcopy(_BLOCK), lambda rel: read.append(rel) or _schema(7))
    assert sorted(read) == sorted([_BLOCK["case_schema"], _BLOCK["report_schema"]])
    assert _parse(copy.deepcopy(_BLOCK), lambda _rel: _schema(7)).schema_version == 7


@pytest.mark.parametrize(
    "path, value, hint",
    [
        ("threshold", 2, ".evidence/evals"),
        ("extra", 1, ".evidence/evals"),
        ("live.max_calls", -1, ".evidence/evals"),
        ("report_dir", "../outside", None),
        ("report_dir", _DROP, None),
    ],
)
def test_a_refusal_names_the_report_dir_it_could_still_read(path, value, hint):
    with pytest.raises(ConfigError) as info:
        _parse(_with(path, value))
    assert info.value.report_dir == hint
    with pytest.raises(ConfigError) as info:
        parse_config({}, lambda _rel: _schema())
    assert info.value.report_dir is None
    with pytest.raises(ConfigError) as info:
        _parse(copy.deepcopy(_BLOCK), lambda _rel: {"properties": {}})
    assert info.value.report_dir == ".evidence/evals"
