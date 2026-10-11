"""
title: Eval scorers — the closed registry of deterministic judges
layer: n/a
public_api: no
summary: SCORERS maps each scorer name (exact, contains, regex, json_fields) to a Scorer whose check_params refuses an unknown, missing or ill-typed parameter with ValueError and whose score(response, params) returns (passed, detail) without raising on any response text. It is the only place a scorer name is written in code; the case schema's scorer branches are held equal to it by tests/integration/test_evals_schema.py.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

__all__ = ["SCORERS", "Scorer"]

# A detail quotes at most this much of a response: enough to recognise it in a
# report, short enough that one long answer cannot bury the others.
_QUOTE = 60


@dataclass(frozen=True)
class Scorer:
    """One deterministic judge: its required parameter names, a validator for
    them, and a scoring function that never raises on response text."""

    name: str
    params: frozenset[str]
    _check: Callable[[Mapping[str, object]], None]
    _score: Callable[[str, Mapping[str, object]], tuple[bool, str]]

    def check_params(self, params: object) -> None:
        """Raise ValueError unless *params* is an object holding exactly this
        scorer's keys, each of the type and shape the scorer needs."""
        if not isinstance(params, dict):
            raise ValueError("%s: params must be an object" % self.name)
        unknown = sorted(set(params) - self.params)
        missing = sorted(self.params - set(params))
        if unknown:
            raise ValueError(
                "%s: unknown param(s) %s" % (self.name, ", ".join(unknown))
            )
        if missing:
            raise ValueError(
                "%s: missing param(s) %s" % (self.name, ", ".join(missing))
            )
        self._check(params)

    def score(self, response: str, params: Mapping[str, object]) -> tuple[bool, str]:
        """(passed, detail) for *response* under already-checked *params*."""
        return self._score(response, params)


def _quote(text: str) -> str:
    return json.dumps(text[:_QUOTE] + ("..." if len(text) > _QUOTE else ""))


def _non_empty_str(name: str, key: str, value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("%s: %s must be a non-empty string" % (name, key))
    return value


def _check_exact(params: Mapping[str, object]) -> None:
    expected = _non_empty_str("exact", "expected", params["expected"])
    # The response is stripped before comparing, so an expected value with
    # surrounding whitespace could never match: refuse it where it is written.
    if expected != expected.strip():
        raise ValueError("exact: expected has leading or trailing whitespace")


def _score_exact(response: str, params: Mapping[str, object]) -> tuple[bool, str]:
    if response.strip() == params["expected"]:
        return True, "matched"
    return False, "got %s" % _quote(response.strip())


def _check_contains(params: Mapping[str, object]) -> None:
    _non_empty_str("contains", "substring", params["substring"])


def _score_contains(response: str, params: Mapping[str, object]) -> tuple[bool, str]:
    substring = str(params["substring"])
    if substring in response:
        return True, "found"
    return False, "%s not in %s" % (json.dumps(substring), _quote(response))


def _check_regex(params: Mapping[str, object]) -> None:
    pattern = _non_empty_str("regex", "pattern", params["pattern"])
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ValueError("regex: pattern does not compile (%s)" % exc) from exc


def _score_regex(response: str, params: Mapping[str, object]) -> tuple[bool, str]:
    if re.search(str(params["pattern"]), response) is not None:
        return True, "matched"
    return False, "no match in %s" % _quote(response)


def _check_json_fields(params: Mapping[str, object]) -> None:
    fields = params["fields"]
    if not isinstance(fields, dict) or not fields:
        raise ValueError("json_fields: fields must be a non-empty object")


def _refuse_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate key %s" % json.dumps(key))
        out[key] = value
    return out


def _canonical(value: object) -> str:
    # Canonical JSON text, not ==: Python's == calls True equal to 1 and 1 equal
    # to 1.0, which a structured answer must not.
    return json.dumps(value, sort_keys=True)


def _score_json_fields(response: str, params: Mapping[str, object]) -> tuple[bool, str]:
    try:
        answer = json.loads(response.strip(), object_pairs_hook=_refuse_duplicates)
    except ValueError as exc:
        return False, "not JSON (%s)" % exc
    if not isinstance(answer, dict):
        return False, "not a JSON object"
    fields = params["fields"]
    assert isinstance(fields, dict)  # check_params proved it
    for key in sorted(fields):
        if key not in answer:
            return False, "missing field %s" % json.dumps(key)
        if _canonical(answer[key]) != _canonical(fields[key]):
            return False, "field %s is %s, want %s" % (
                json.dumps(key),
                _canonical(answer[key]),
                _canonical(fields[key]),
            )
    return True, "matched %d field(s)" % len(fields)


SCORERS: Mapping[str, Scorer] = MappingProxyType(
    {
        s.name: s
        for s in (
            Scorer("exact", frozenset({"expected"}), _check_exact, _score_exact),
            Scorer(
                "contains", frozenset({"substring"}), _check_contains, _score_contains
            ),
            Scorer("regex", frozenset({"pattern"}), _check_regex, _score_regex),
            Scorer(
                "json_fields",
                frozenset({"fields"}),
                _check_json_fields,
                _score_json_fields,
            ),
        )
    }
)
