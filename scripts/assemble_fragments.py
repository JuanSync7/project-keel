#!/usr/bin/env python3
"""
title: Reference assembly — one independently mergeable file per table entry
kind: script
layer: n/a
summary: Assembles configured reference tables in sorted filename order; --check reports stale outputs without writing, and malformed, duplicate or unregistered sources fail closed.
effect: writes
rerun: fixed-point
rerun_proof: make:check-fragments

Layout: each configured set has head.part, sorted table directories (each with
head.part and one row per other .part file), and tail.part. Table heads include
section prose and the two table header lines, so each header appears once;
tail.part holds fixed text after the final table. The non-.md suffix is configured:
fragments have no frontmatter and are outside check_A and review_docs' Markdown
walks. Their links are relative to the assembled reference, where check_Q reads
them. These folders and this script ship to generated projects.

An entry's first cell names its key (its first code span, or the whole cell).
Sorted tables use percent-encoded keys as filenames. Historical unsorted tables
use six-digit order prefixes followed by the encoded key; append a new entry with
the next prefix, using its distinct key to keep parallel additions independent.
Keys must be unique within a table. Every entry is exactly one complete table row
with the header's column count. Unexpected files, missing heads or registered
folders, duplicate keys and stray folders under the configured root are errors.

The output owns its updated: stamp: assembly retains that line verbatim (the
head supplies it only for a new output). Restamp_docs remains its only date
writer. --check uses the same retention rule, so a later restamp cannot create
an assembly repair loop, including when the newest entry is deleted.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import NoReturn

if __name__ == "__main__":
    sys.dont_write_bytecode = True

import config_loader
from exit_codes import ExitCode, finish, report

_KEY = ("reference_fragments",)


class FragmentError(ValueError):
    """A fragment set cannot be assembled without guessing its meaning."""


class Parser(argparse.ArgumentParser):
    """Route malformed CLI input through the house failure reporter."""

    def error(self, message: str) -> NoReturn:
        raise FragmentError(message)


def _path(root: Path, value: object) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise FragmentError(f"expected a relative project path: {value!r}")
    path = root / value
    if ".." in Path(value).parts or not path.resolve().is_relative_to(root.resolve()):
        raise FragmentError(f"path escapes project: {value}")
    return path


def _text(path: Path) -> str:
    # Byte decoding preserves line endings; the first split must be lossless.
    return path.read_bytes().decode("utf-8")


def _cells(row: str) -> list[str]:
    if not row.startswith("|") or not row.endswith("|\n") or row.count("\n") != 1:
        raise FragmentError(
            "expected exactly one pipe-delimited row ending in a newline"
        )
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", row.strip())[1:-1]]


def _table(folder: Path, suffix: str) -> str:
    head_path = folder / ("head" + suffix)
    head = _text(head_path)
    lines = head.splitlines(keepends=True)
    if len(lines) < 2 or not re.fullmatch(r"[| :\-]+\n", lines[-1]):
        raise FragmentError(f"{head_path}: table head must end with its separator")
    columns = len(_cells(lines[-2]))
    keys: set[str] = set()
    rows = []
    for entry in sorted(folder.iterdir()):
        if entry == head_path:
            continue
        if not entry.is_file() or entry.suffix != suffix:
            raise FragmentError(f"{entry}: unexpected table member")
        row = _text(entry)
        cells = _cells(row)
        if len(cells) != columns or not cells[0]:
            raise FragmentError(f"{entry}: expected {columns} cells and a nonblank key")
        code = re.search(r"`([^`]+)`", cells[0])
        key = code.group(1) if code else cells[0]
        if key in keys:
            raise FragmentError(f"{entry}: duplicate key {key!r}")
        keys.add(key)
        rows.append(row)
    return head + "".join(rows)


def _stamp(text: str) -> re.Match[str] | None:
    frontmatter = re.match(r"\A---\n.*?\n---\n", text, re.DOTALL)
    if frontmatter is None:
        return None
    return re.search(r"(?m)^updated: [^\n]+$", frontmatter.group())


def _render(root: Path, spec: object, suffix: str) -> tuple[Path, str]:
    if not isinstance(spec, dict) or set(spec) != {"output", "head", "folder"}:
        raise FragmentError("each set needs exactly output, head and folder")
    output, head, folder = (
        _path(root, spec[key]) for key in ("output", "head", "folder")
    )
    if head.parent != folder or head.name != "head" + suffix:
        raise FragmentError(f"{head}: head must be the folder's head{suffix}")
    tail = folder / ("tail" + suffix)
    tables = []
    for path in sorted(folder.iterdir()):
        if path in (head, tail):
            continue
        if not path.is_dir():
            raise FragmentError(f"{path}: unexpected fragment member")
        tables.append(path)
    if not tables:
        raise FragmentError(f"{folder}: no table directories")
    rendered = (
        _text(head) + "".join(_table(table, suffix) for table in tables) + _text(tail)
    )
    if output.exists():
        old_stamp, new_stamp = _stamp(_text(output)), _stamp(rendered)
        if old_stamp is None or new_stamp is None:
            raise FragmentError(f"{output}: missing frontmatter updated: line")
        rendered = (
            rendered[: new_stamp.start()]
            + old_stamp.group()
            + rendered[new_stamp.end() :]
        )
    elif _stamp(rendered) is None:
        raise FragmentError(f"{head}: missing frontmatter updated: line")
    return output, rendered


def assemble(root: Path) -> list[tuple[Path, str]]:
    """Validate all configured sets and return their prospective output bytes."""
    config = config_loader.resolve(
        config_loader.read(str(root)),
        config_loader.rows(_KEY),
        config_loader.CONFIG_FILE,
    )[_KEY]
    if set(config) != {"root", "folder_suffix", "suffix", "sets"}:
        raise FragmentError(
            "reference_fragments needs root, folder_suffix, suffix and sets"
        )
    base = _path(root, config["root"])
    folder_suffix, suffix, sets = (
        config[key] for key in ("folder_suffix", "suffix", "sets")
    )
    for value in (folder_suffix, suffix):
        if not isinstance(value, str) or not re.fullmatch(r"\.[a-zA-Z0-9_-]+", value):
            raise FragmentError(
                "fragment suffixes must be a dot followed by letters, digits, _ or -"
            )
    if suffix == ".md" or not isinstance(sets, list):
        raise FragmentError("fragment suffix must not be .md; sets must be a list")
    rendered = [_render(root, spec, suffix) for spec in sets]
    folders = [_path(root, spec["folder"]) for spec in sets]
    outputs = [path for path, _ in rendered]
    if len(set(folders)) != len(folders) or len(set(outputs)) != len(outputs):
        raise FragmentError("duplicate output or fragment folder")
    discovered = set(base.glob("*" + folder_suffix))
    if set(folders) != discovered:
        raise FragmentError(
            f"unregistered or missing fragment folders: {sorted(set(folders) ^ discovered)}"
        )
    return rendered


def main(argv: list[str] | None = None) -> ExitCode:
    """Check or assemble references, reporting every refused input by name."""
    parser = Parser(description="Assemble configured reference-table entry files.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Project root (default: this script's checkout).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report stale references without writing anything.",
    )
    try:
        args = parser.parse_args(argv)
        rendered = assemble(args.root)
        stale = [
            (path, text)
            for path, text in rendered
            if not path.exists() or path.read_bytes() != text.encode("utf-8")
        ]
        if args.check and stale:
            return report(
                ExitCode.FAILURE,
                "stale reference",
                ", ".join(str(p) for p, _ in stale),
                "run make assemble-fragments",
            )
        for path, text in stale:
            with path.open("wb") as stream:
                stream.write(text.encode("utf-8"))
    except config_loader.ConfigError as exc:
        return report(
            ExitCode.USAGE if config_loader.is_conflict(exc) else ExitCode.CONFIG,
            "fragment configuration refused",
            str(exc),
            "fix config/project.json reference_fragments",
        )
    except (FragmentError, OSError, UnicodeError) as exc:
        return report(
            ExitCode.USAGE,
            "reference assembly refused",
            str(exc),
            "fix the named fragment or configuration and rerun",
        )
    return ExitCode.SUCCESS


if __name__ == "__main__":
    finish(main())
