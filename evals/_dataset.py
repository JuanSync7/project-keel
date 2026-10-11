"""
title: Eval datasets — JSONL suites parsed into typed cases
layer: n/a
public_api: no
summary: parse_cases reads one suite's JSONL text into frozen Case records, holding each line to the shape config/evals/eval-case.schema.json states (no unknown or missing key at any level, a closed doer and scorer vocabulary, the scorer's own parameter check, sha256 patterns, provenance that agrees with itself) plus what a schema cannot state (a repeated JSON key, a response hash that does not match its text, a repeated id); load_suites reads every file in config/project.json `evals.dataset_dir`. Every fault is a DatasetError naming path:line, and an empty suite, an empty directory or a stray file is an error, never a skip.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from ._config import EvalConfig
from ._doers import DOERS, sha256_text
from ._scorers import SCORERS, Scorer

__all__ = ["Case", "DatasetError", "Suite", "load_suites", "parse_cases"]

# Applied with fullmatch: a `$`-anchored match would also accept a value with
# one trailing newline, so "c-1\n" would pass as an id beside "c-1".
_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
_SHA = re.compile(r"sha256:[0-9a-f]{64}")
_SUFFIX = ".jsonl"
_BOM = "﻿"
_TOP = frozenset({"schema_version", "id", "input", "scorer", "recorded"})
_INPUT = frozenset({"doer", "text"})
_SCORER = frozenset({"name", "params"})
_RECORDED = frozenset({"response", "sha256", "prompt_sha256", "source", "model"})
_SOURCES = ("authored", "model")


class DatasetError(Exception):
    """A dataset cannot be judged; the message starts with path:line."""


@dataclass(frozen=True)
class Case:
    """One eval case: what to run, how to judge it, and what was recorded."""

    id: str
    suite: str
    source: str
    doer: str
    text: str
    scorer_name: str
    params: Mapping[str, object]
    response: str
    response_sha256: str
    prompt_sha256: str
    rec_source: str
    rec_model: str | None


@dataclass(frozen=True)
class Suite:
    """One dataset file: its name (the file stem), path and cases in file order."""

    name: str
    dataset: str
    cases: list[Case] = field(default_factory=list)


class _LineError(Exception):
    """A fault in one line; parse_cases adds the path:line prefix."""


def _refuse_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in pairs:
        if key in out:
            # json.loads would silently keep the last value.
            raise _LineError("repeated JSON key %s" % json.dumps(key))
        out[key] = value
    return out


def _object(value: object, where: str, keys: frozenset[str]) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _LineError("%s must be an object" % where)
    unknown = sorted(set(value) - keys)
    if unknown:
        raise _LineError("unknown key %s.%s" % (where, unknown[0]))
    missing = sorted(keys - set(value))
    if missing:
        raise _LineError("missing key %s.%s" % (where, missing[0]))
    return value


def _string(value: object, where: str, non_empty: bool = True) -> str:
    if not isinstance(value, str) or (non_empty and not value):
        raise _LineError(
            "%s must be a %sstring" % (where, "non-empty " if non_empty else "")
        )
    return value


def _sha(value: object, where: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise _LineError("%s must match sha256:<64 hex>" % where)
    return value


def _case(
    obj: object,
    suite: str,
    where: str,
    schema_version: int,
    scorers: Mapping[str, Scorer],
) -> Case:
    top = _object(obj, "case", _TOP)
    version = top["schema_version"]
    if version != schema_version or isinstance(version, bool):
        raise _LineError(
            "schema_version is %r; this harness reads %d" % (version, schema_version)
        )
    case_id = _string(top["id"], "id")
    if not _ID.fullmatch(case_id):
        raise _LineError("id %r must match %s" % (case_id, _ID.pattern))
    inp = _object(top["input"], "input", _INPUT)
    doer = _string(inp["doer"], "input.doer")
    if doer not in DOERS:
        raise _LineError("input.doer %r is not one of %s" % (doer, sorted(DOERS)))
    text = _string(inp["text"], "input.text")
    scorer = _object(top["scorer"], "scorer", _SCORER)
    name = _string(scorer["name"], "scorer.name")
    if name not in scorers:
        raise _LineError("scorer.name %r is not one of %s" % (name, sorted(scorers)))
    params = scorer["params"]
    try:
        scorers[name].check_params(params)
    except ValueError as exc:
        raise _LineError("scorer.params: %s" % exc) from exc
    assert isinstance(params, dict)  # check_params proved it
    rec = _object(top["recorded"], "recorded", _RECORDED)
    response = _string(rec["response"], "recorded.response", non_empty=False)
    response_sha = _sha(rec["sha256"], "recorded.sha256")
    prompt_sha = _sha(rec["prompt_sha256"], "recorded.prompt_sha256")
    source = rec["source"]
    if source not in _SOURCES:
        raise _LineError(
            "recorded.source %r is not one of %s" % (source, list(_SOURCES))
        )
    model = rec["model"]
    if source == "authored" and model is not None:
        raise _LineError("recorded.model must be null when recorded.source is authored")
    if source == "model" and (not isinstance(model, str) or not model):
        raise _LineError(
            "recorded.model must name the model when recorded.source is model"
        )
    actual = sha256_text(response)
    if actual != response_sha:
        raise _LineError(
            "recorded.sha256 is %s but the response hashes to %s"
            % (response_sha, actual)
        )
    return Case(
        id=case_id,
        suite=suite,
        source=where,
        doer=doer,
        text=text,
        scorer_name=name,
        params=dict(params),
        response=response,
        response_sha256=response_sha,
        prompt_sha256=prompt_sha,
        rec_source=str(source),
        rec_model=model if isinstance(model, str) else None,
    )


def parse_cases(
    text: str,
    *,
    source: str,
    schema_version: int,
    scorers: Mapping[str, Scorer] = SCORERS,
) -> list[Case]:
    """The cases in one suite's JSONL *text*, read from *source* (a
    project-relative path; its stem names the suite). Raises DatasetError."""
    suite = PurePosixPath(source).stem
    text = text.removeprefix(_BOM)
    if not text.strip():
        raise DatasetError(
            "%s: no cases; a suite judged over nothing is not a pass" % source
        )
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()  # the one trailing newline a file ends with
    cases: list[Case] = []
    first_seen: dict[str, str] = {}
    for number, raw in enumerate(lines, start=1):
        where = "%s:%d" % (source, number)
        line = raw.removesuffix("\r")
        try:
            if not line.strip():
                raise _LineError("blank line inside the suite")
            obj = json.loads(line, object_pairs_hook=_refuse_duplicates)
            case = _case(obj, suite, where, schema_version, scorers)
        except _LineError as exc:
            raise DatasetError("%s: %s" % (where, exc)) from exc
        except ValueError as exc:
            raise DatasetError("%s: not valid JSON (%s)" % (where, exc)) from exc
        if case.id in first_seen:
            raise DatasetError(
                "%s: duplicate id %r (first at %s)"
                % (where, case.id, first_seen[case.id])
            )
        first_seen[case.id] = where
        cases.append(case)
    return cases


def load_suites(cfg: EvalConfig, root: str | os.PathLike[str]) -> list[Suite]:
    """Every suite in *cfg*.dataset_dir under *root*, sorted by file name, with
    ids unique across all of them. Raises DatasetError."""
    rel_dir = PurePosixPath(cfg.dataset_dir)
    base = os.path.join(os.fspath(root), *rel_dir.parts)
    if not os.path.isdir(base):
        raise DatasetError(
            "%s: no such directory (config/project.json evals.dataset_dir)" % rel_dir
        )
    suites: list[Suite] = []
    first_seen: dict[str, str] = {}
    for name in sorted(os.listdir(base)):
        rel = (rel_dir / name).as_posix()
        path = os.path.join(base, name)
        if not name.endswith(_SUFFIX) or not os.path.isfile(path):
            raise DatasetError(
                "%s: only %s suite files belong in evals.dataset_dir" % (rel, _SUFFIX)
            )
        stem = name[: -len(_SUFFIX)]
        if not _ID.fullmatch(stem):
            raise DatasetError("%s: a suite name must match %s" % (rel, _ID.pattern))
        try:
            with open(path, encoding="utf-8", newline="") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError) as exc:
            raise DatasetError("%s: unreadable (%s)" % (rel, exc)) from exc
        cases = parse_cases(text, source=rel, schema_version=cfg.schema_version)
        for case in cases:
            if case.id in first_seen:
                raise DatasetError(
                    "%s: duplicate id %r (first at %s)"
                    % (case.source, case.id, first_seen[case.id])
                )
            first_seen[case.id] = case.source
        suites.append(Suite(stem, rel, cases))
    if not suites:
        raise DatasetError(
            "%s: no suite files; an eval over zero cases is not a pass" % rel_dir
        )
    return suites
