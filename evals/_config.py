"""
title: Eval configuration — the evals block of config/project.json, checked
layer: n/a
public_api: no
summary: parse_config turns the config/project.json `evals` block into a frozen EvalConfig and reads each schema's version from its `properties.schema_version.const`, the only owner of that number; load_config reads the files for it. It is a typed view over scripts/config_loader.py, not a second loader: load_config reads the manifest through `read`, and parse_config resolves the block's eight keys through `resolve` against that module's KEYS rows, which hold each key's type and bound (a threshold with 0 < t <= 1, an integer call cap >= 0, a null or non-empty model name, object model options, and a path that is non-empty, not absolute and with no `..` part), so every key that is missing or ill-typed is named in one refusal, one loader line each, written to stderr. It adds what a row cannot say: a key the block or `evals.live` does not know is refused by its dotted name. Each refusal here is a ConfigError carrying the loader's `lines` and `in_config`, true when an edit to config/project.json clears it and false, the default, for a schema file that cannot be read or has no positive integer version. A ConfigError from parse_config carries `evals.report_dir` whenever that key alone is still a safe relative path, so the caller can remove an earlier report rather than leave it standing.
"""

from __future__ import annotations

import io
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from scripts import config_loader

__all__ = ["ConfigError", "EvalConfig", "load_config", "parse_config"]

_MANIFEST = "config/project.json"
_BLOCK = "evals"
_COMMENT = "_comment"
_PATHS = ("case_schema", "report_schema", "dataset_dir", "report_dir")
_KEYS = frozenset(_PATHS + ("threshold", "live"))
_LIVE_KEYS = frozenset({"model", "max_calls", "model_options"})
_LIVE = (_BLOCK, "live")
# The block's rows in scripts/config_loader.py KEYS: the one statement of each
# key's type, bound and default (none has one).
_ROWS = config_loader.rows(
    *[(_BLOCK, key) for key in _PATHS + ("threshold",)],
    *[_LIVE + (key,) for key in sorted(_LIVE_KEYS)],
)
_REPORT_DIR_ROW = config_loader.rows((_BLOCK, "report_dir"))


class ConfigError(Exception):
    """config/project.json `evals`, or a schema it names, cannot be used; the
    message names the dotted key at fault. *lines* are scripts/config_loader.py's
    lines for it (empty for a fault that is not a config value), *in_config*
    is true when an edit to config/project.json clears it, and *report_dir* is
    `evals.report_dir` when that key alone still reads as a safe relative
    path, else None."""

    def __init__(
        self,
        message: str,
        report_dir: str | None = None,
        lines: list[str] | None = None,
        in_config: bool = False,
    ) -> None:
        super().__init__(message)
        self.report_dir = report_dir
        self.lines = list(lines or [])
        self.in_config = in_config


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


def _from_loader(exc: config_loader.ConfigError) -> ConfigError:
    return ConfigError("; ".join(exc.lines), lines=exc.lines, in_config=True)


def _unknown(block: Mapping[str, object], where: str, allowed: frozenset[str]) -> None:
    unknown = sorted(set(block) - allowed - {_COMMENT})
    if unknown:
        line = "%s: unknown key `%s.%s`" % (_MANIFEST, where, unknown[0])
        raise ConfigError(line, lines=[line], in_config=True)


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
    # A scratch stream: the refusal has already written its lines, and the
    # hint is a second reading of one key, not a second fault to tell.
    try:
        values = config_loader.resolve(
            manifest, _REPORT_DIR_ROW, _MANIFEST, stream=io.StringIO()
        )
    except config_loader.ConfigError:
        return None
    hint: str = values[(_BLOCK, "report_dir")]
    return hint


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
    if isinstance(block, dict):
        _unknown(block, _BLOCK, _KEYS)
        live = block.get("live")
        if isinstance(live, dict):
            _unknown(live, ".".join(_LIVE), _LIVE_KEYS)
    try:
        values: dict[tuple[str, ...], Any] = config_loader.resolve(
            manifest, _ROWS, _MANIFEST
        )
    except config_loader.ConfigError as exc:
        raise _from_loader(exc) from exc
    paths = {key: values[(_BLOCK, key)] for key in _PATHS}
    return EvalConfig(
        case_schema=paths["case_schema"],
        report_schema=paths["report_schema"],
        dataset_dir=paths["dataset_dir"],
        report_dir=paths["report_dir"],
        threshold=values[(_BLOCK, "threshold")],
        live_model=values[_LIVE + ("model",)],
        live_max_calls=values[_LIVE + ("max_calls",)],
        live_model_options=dict(values[_LIVE + ("model_options",)]),
        schema_version=_version(read_schema, paths["case_schema"], "case_schema"),
        report_schema_version=_version(
            read_schema, paths["report_schema"], "report_schema"
        ),
    )


def _read_schema(path: str) -> object:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_config(root: str | os.PathLike[str]) -> EvalConfig:
    """The EvalConfig of the project at *root*, its manifest read through
    scripts/config_loader.py `read`. Raises ConfigError."""
    base = os.fspath(root)
    try:
        manifest = config_loader.read(base)
    except config_loader.ConfigError as exc:
        raise _from_loader(exc) from exc
    return parse_config(manifest, lambda rel: _read_schema(os.path.join(base, rel)))
