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

from scripts import config_loader

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


class _LibraryError(ValueError):
    """A library failure's safe text and original type name."""

    def __init__(self, message: str, type_name: str) -> None:
        super().__init__(message)
        self.type_name = type_name


def _safe_library_error(exc: ValueError) -> ValueError:
    """Copy both chain links without mutating library exceptions.

    No input text holding @ may survive in args or public string/bytes
    attributes. Stand-ins retain sanitized public text, type names and integer
    positions; other library attributes can hold arbitrary input objects.
    Raise outside the handler so its raw exception cannot become context.
    """
    pending: list[BaseException] = [exc]
    originals: list[BaseException] = []
    copies: dict[int, _LibraryError] = {}
    while pending:
        current = pending.pop()
        if id(current) in copies:
            continue
        message = str(current)
        safe = _LibraryError(
            config_loader.shown(message, bare=True) if "@" in message else message,
            config_loader.shown(type(current).__name__, bare=True),
        )
        for name in dir(current):
            if name.startswith("_") or name == "type_name":
                continue
            value = getattr(current, name)
            if isinstance(value, str):
                setattr(safe, name, config_loader.shown(value, bare=True))
            elif isinstance(value, bytes):
                setattr(
                    safe,
                    name,
                    config_loader.shown(str(value), bare=True).encode("utf-8")
                    if b"@" in value
                    else value,
                )
        for name in ("lineno", "colno", "pos"):
            position = getattr(current, name, None)
            if isinstance(position, int):
                setattr(safe, name, position)
        copies[id(current)] = safe
        originals.append(current)
        pending.extend(
            linked
            for linked in (current.__cause__, current.__context__)
            if linked is not None
        )
    for current in originals:
        safe = copies[id(current)]
        if current.__cause__ is not None:
            safe.__cause__ = copies[id(current.__cause__)]
        if current.__context__ is not None:
            safe.__context__ = copies[id(current.__context__)]
        safe.__suppress_context__ = current.__suppress_context__
    return copies[id(exc)]


def _refuse_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in pairs:
        if key in out:
            # json.loads would silently keep the last value.
            raise _LineError("repeated JSON key %s" % config_loader.shown(key))
        out[key] = value
    return out


def _object(value: object, where: str, keys: frozenset[str]) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _LineError("%s must be an object" % where)
    unknown = sorted(set(value) - keys)
    if unknown:
        raise _LineError(
            "unknown key %s.%s" % (where, config_loader.shown(unknown[0], bare=True))
        )
    missing = sorted(keys - set(value))
    if missing:
        raise _LineError("missing key %s.%s" % (where, missing[0]))
    return value


def _string(value: object, where: str, *, non_empty: bool = True) -> str:
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
            "schema_version is %s; this harness reads %d"
            % (config_loader.quoted(version), schema_version)
        )
    case_id = _string(top["id"], "id")
    if not _ID.fullmatch(case_id):
        raise _LineError(
            "id %s must match %s" % (config_loader.quoted(case_id), _ID.pattern)
        )
    inp = _object(top["input"], "input", _INPUT)
    doer = _string(inp["doer"], "input.doer")
    if doer not in DOERS:
        raise _LineError(
            "input.doer %s is not one of %s"
            % (config_loader.quoted(doer), config_loader.quoted(sorted(DOERS)))
        )
    text = _string(inp["text"], "input.text")
    scorer = _object(top["scorer"], "scorer", _SCORER)
    name = _string(scorer["name"], "scorer.name")
    if name not in scorers:
        raise _LineError(
            "scorer.name %s is not one of %s"
            % (config_loader.quoted(name), config_loader.quoted(sorted(scorers)))
        )
    params = scorer["params"]
    params_error: _LineError | None = None
    try:
        scorers[name].check_params(params)
    except ValueError as exc:
        safe = _safe_library_error(exc)
        params_error = _LineError("scorer.params: %s" % safe)
        params_error.__cause__ = safe
    if params_error is not None:
        # Raising in the handler would attach the raw library error as context.
        raise params_error
    assert isinstance(params, dict)  # check_params proved it
    rec = _object(top["recorded"], "recorded", _RECORDED)
    response = _string(rec["response"], "recorded.response", non_empty=False)
    response_sha = _sha(rec["sha256"], "recorded.sha256")
    prompt_sha = _sha(rec["prompt_sha256"], "recorded.prompt_sha256")
    source = rec["source"]
    if source not in _SOURCES:
        raise _LineError(
            "recorded.source %s is not one of %s"
            % (config_loader.quoted(source), list(_SOURCES))
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
            % (config_loader.shown(response_sha, bare=True), actual)
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
    shown_source: str | None = None,
) -> list[Case]:
    """The cases in one suite's JSONL *text*, read from *source* (a
    project-relative path; its stem names the suite). *shown_source* overrides
    the path in diagnostics only. Raises DatasetError."""
    suite = PurePosixPath(source).stem
    display_source = (
        config_loader.shown(source, bare=True) if shown_source is None else shown_source
    )
    text = text.removeprefix(_BOM)
    if not text.strip():
        raise DatasetError(
            "%s: no cases; a suite judged over nothing is not a pass" % display_source
        )
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()  # the one trailing newline a file ends with
    cases: list[Case] = []
    first_seen: dict[str, str] = {}
    for number, raw in enumerate(lines, start=1):
        where = "%s:%d" % (source, number)
        shown_where = "%s:%d" % (display_source, number)
        line = raw.removesuffix("\r")
        refusal: DatasetError | None = None
        try:
            if not line.strip():
                raise _LineError("blank line inside the suite")
            obj = json.loads(line, object_pairs_hook=_refuse_duplicates)
            case = _case(obj, suite, where, schema_version, scorers)
        except _LineError as exc:
            refusal = DatasetError("%s: %s" % (shown_where, exc))
            refusal.__cause__ = exc
        except ValueError as exc:
            safe = _safe_library_error(exc)
            refusal = DatasetError("%s: not valid JSON (%s)" % (shown_where, safe))
            refusal.__cause__ = safe
        if refusal is not None:
            # `from None` only hides context from printing; handlers can read it.
            raise refusal
        if case.id in first_seen:
            raise DatasetError(
                "%s: duplicate id %s (first at %s)"
                % (shown_where, config_loader.quoted(case.id), first_seen[case.id])
            )
        first_seen[case.id] = shown_where
        cases.append(case)
    return cases


def load_suites(cfg: EvalConfig, root: str | os.PathLike[str]) -> list[Suite]:
    """Every suite in *cfg*.dataset_dir under *root*, sorted by file name, with
    ids unique across all of them. Raises DatasetError."""
    rel_dir = PurePosixPath(cfg.dataset_dir)
    base = os.path.join(os.fspath(root), *rel_dir.parts)
    if not os.path.isdir(base):
        raise DatasetError(
            "%s: no such directory (config/project.json evals.dataset_dir)"
            % config_loader.shown(str(rel_dir), bare=True)
        )
    suites: list[Suite] = []
    first_seen: dict[str, str] = {}
    try:
        names = os.listdir(base)
    except OSError as exc:
        # The OS error's path can carry credentials; keep only its reason.
        raise DatasetError(
            "%s: unreadable (%s)"
            % (
                config_loader.shown(str(rel_dir), bare=True),
                config_loader.shown(exc.strerror or str(exc), bare=True),
            )
        ) from None
    for name in sorted(names):
        rel = (rel_dir / name).as_posix()
        path = os.path.join(base, name)
        if not name.endswith(_SUFFIX) or not os.path.isfile(path):
            raise DatasetError(
                "%s: only %s suite files belong in evals.dataset_dir"
                % (config_loader.shown(rel, bare=True), _SUFFIX)
            )
        stem = name[: -len(_SUFFIX)]
        if not _ID.fullmatch(stem):
            raise DatasetError(
                "%s: a suite name must match %s"
                % (config_loader.shown(rel, bare=True), _ID.pattern)
            )
        try:
            with open(path, encoding="utf-8", newline="") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError) as exc:
            # The OS error can quote the configured path, so suppress its cause.
            raise DatasetError(
                "%s: unreadable (%s)"
                % (
                    config_loader.shown(rel, bare=True),
                    config_loader.shown(
                        exc.strerror
                        if isinstance(exc, OSError) and exc.strerror
                        else str(exc),
                        bare=True,
                    ),
                )
            ) from None
        try:
            cases = parse_cases(
                text,
                source=rel,
                shown_source=config_loader.shown(rel, bare=True),
                schema_version=cfg.schema_version,
            )
        except DatasetError as exc:
            # Parser diagnostics already use the display path, including causes.
            raise DatasetError(str(exc)) from exc
        for case in cases:
            if case.id in first_seen:
                raise DatasetError(
                    "%s: duplicate id %s (first at %s)"
                    % (
                        config_loader.shown(case.source, bare=True),
                        config_loader.quoted(case.id),
                        config_loader.shown(first_seen[case.id], bare=True),
                    )
                )
            first_seen[case.id] = case.source
        suites.append(Suite(stem, rel, cases))
    if not suites:
        raise DatasetError(
            "%s: no suite files; an eval over zero cases is not a pass"
            % config_loader.shown(str(rel_dir), bare=True)
        )
    return suites
