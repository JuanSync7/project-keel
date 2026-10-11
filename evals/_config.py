"""
title: Eval configuration — the evals block of config/project.json, checked
layer: n/a
public_api: no
summary: parse_config turns the config/project.json `evals` block into a frozen EvalConfig and reads each schema's version from its `properties.schema_version.const`, the only owner of that number; load_config reads the files for it. Every missing, unknown or ill-typed key is a ConfigError naming its dotted key (evals.threshold, evals.live.max_calls, ...): a threshold outside 0 < t <= 1, a negative or non-integer call cap, an empty model name, non-object model options, and a path that is absolute or climbs out of the project. A ConfigError from parse_config carries `evals.report_dir` whenever that key alone is still a safe relative path, so the caller can remove an earlier report rather than leave it standing.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import PurePosixPath

__all__ = ["ConfigError", "EvalConfig", "load_config", "parse_config"]

_MANIFEST = "config/project.json"
_BLOCK = "evals"
_COMMENT = "_comment"
_PATHS = ("case_schema", "report_schema", "dataset_dir", "report_dir")
_KEYS = frozenset(_PATHS + ("threshold", "live"))
_LIVE_KEYS = frozenset({"model", "max_calls", "model_options"})


class ConfigError(Exception):
    """config/project.json `evals`, or a schema it names, cannot be used; the
    message names the dotted key at fault. *report_dir* is `evals.report_dir`
    when that key alone still reads as a safe relative path, else None."""

    def __init__(self, message: str, report_dir: str | None = None) -> None:
        super().__init__(message)
        self.report_dir = report_dir


@dataclass(frozen=True)
class EvalConfig:
    """The checked `evals` block, plus the version each schema declares."""

    case_schema: str
    report_schema: str
    dataset_dir: str
    report_dir: str
    threshold: float
    live_model: str | None
    live_max_calls: int
    live_model_options: Mapping[str, object] = field(default_factory=dict)
    schema_version: int = 1
    report_schema_version: int = 1


def _is_number(value: object) -> bool:
    # bool is an int to isinstance; a threshold of `true` is a typo, not 1.
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _keys(block: Mapping[str, object], where: str, allowed: frozenset[str]) -> None:
    unknown = sorted(set(block) - allowed - {_COMMENT})
    if unknown:
        raise ConfigError("%s: unknown key `%s.%s`" % (_MANIFEST, where, unknown[0]))
    missing = sorted(allowed - set(block))
    if missing:
        raise ConfigError("%s: missing key `%s.%s`" % (_MANIFEST, where, missing[0]))


def _rel_path(value: object, key: str) -> str:
    where = "%s.%s" % (_BLOCK, key)
    if not isinstance(value, str) or not value:
        raise ConfigError("%s: `%s` must be a non-empty path" % (_MANIFEST, where))
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or os.path.isabs(value):
        raise ConfigError(
            "%s: `%s` must be relative to the project and stay inside it, got %r"
            % (_MANIFEST, where, value)
        )
    return value


def _version(read_schema: Callable[[str], object], rel: str, key: str) -> int:
    try:
        schema = read_schema(rel)
    except (OSError, ValueError) as exc:
        raise ConfigError(
            "%s (`%s.%s`): unreadable (%s)" % (rel, _BLOCK, key, exc)
        ) from exc
    const: object = None
    if isinstance(schema, dict):
        props = schema.get("properties")
        if isinstance(props, dict) and isinstance(props.get("schema_version"), dict):
            const = props["schema_version"].get("const")
    if not isinstance(const, int) or isinstance(const, bool) or const < 1:
        raise ConfigError(
            "%s (`%s.%s`): properties.schema_version.const must be a positive integer"
            % (rel, _BLOCK, key)
        )
    return const


def _report_dir_hint(manifest: Mapping[str, object]) -> str | None:
    block = manifest.get(_BLOCK)
    if not isinstance(block, dict):
        return None
    try:
        return _rel_path(block.get("report_dir"), "report_dir")
    except ConfigError:
        return None


def parse_config(
    manifest: Mapping[str, object], read_schema: Callable[[str], object]
) -> EvalConfig:
    """The EvalConfig for a parsed config/project.json *manifest*; *read_schema*
    maps a project-relative path to that file's parsed JSON. Raises ConfigError,
    carrying the `evals.report_dir` it could still read."""
    try:
        return _parse(manifest, read_schema)
    except ConfigError as exc:
        # A refused block must not leave an earlier green report standing; the
        # caller can only remove it if it learns where the report lives.
        exc.report_dir = _report_dir_hint(manifest)
        raise


def _parse(
    manifest: Mapping[str, object], read_schema: Callable[[str], object]
) -> EvalConfig:
    block = manifest.get(_BLOCK)
    if not isinstance(block, dict):
        raise ConfigError("%s: `%s` must be an object" % (_MANIFEST, _BLOCK))
    _keys(block, _BLOCK, _KEYS)
    paths = {key: _rel_path(block[key], key) for key in _PATHS}
    threshold = block["threshold"]
    if not _is_number(threshold) or not 0 < threshold <= 1:
        raise ConfigError(
            "%s: `%s.threshold` must be a number with 0 < threshold <= 1, got %r"
            % (_MANIFEST, _BLOCK, threshold)
        )
    live = block["live"]
    if not isinstance(live, dict):
        raise ConfigError("%s: `%s.live` must be an object" % (_MANIFEST, _BLOCK))
    _keys(live, _BLOCK + ".live", _LIVE_KEYS)
    model = live["model"]
    if model is not None and (not isinstance(model, str) or not model):
        raise ConfigError(
            "%s: `%s.live.model` must be null or a non-empty model name"
            % (_MANIFEST, _BLOCK)
        )
    cap = live["max_calls"]
    if not isinstance(cap, int) or isinstance(cap, bool) or cap < 0:
        raise ConfigError(
            "%s: `%s.live.max_calls` must be an integer >= 0, got %r"
            % (_MANIFEST, _BLOCK, cap)
        )
    options = live["model_options"]
    if not isinstance(options, dict):
        raise ConfigError(
            "%s: `%s.live.model_options` must be an object" % (_MANIFEST, _BLOCK)
        )
    return EvalConfig(
        case_schema=paths["case_schema"],
        report_schema=paths["report_schema"],
        dataset_dir=paths["dataset_dir"],
        report_dir=paths["report_dir"],
        threshold=threshold,
        live_model=model,
        live_max_calls=cap,
        live_model_options=dict(options),
        schema_version=_version(read_schema, paths["case_schema"], "case_schema"),
        report_schema_version=_version(
            read_schema, paths["report_schema"], "report_schema"
        ),
    )


def _read_json(path: str) -> object:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_config(root: str | os.PathLike[str]) -> EvalConfig:
    """The EvalConfig of the project at *root*. Raises ConfigError."""
    base = os.fspath(root)
    try:
        manifest = _read_json(os.path.join(base, _MANIFEST))
    except (OSError, ValueError) as exc:
        raise ConfigError("%s: unreadable (%s)" % (_MANIFEST, exc)) from exc
    if not isinstance(manifest, dict):
        raise ConfigError("%s: must be a JSON object" % _MANIFEST)
    return parse_config(manifest, lambda rel: _read_json(os.path.join(base, rel)))
