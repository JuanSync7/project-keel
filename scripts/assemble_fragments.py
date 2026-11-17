#!/usr/bin/env python3
"""
title: Fragment assembly — independent reference rows and changelog entries
kind: script
layer: n/a
summary: Assembles references and Unreleased entries in sorted filename order; --check never writes, release rotates and consumes entries, and invalid sources fail closed.
effect: writes
rerun: fixed-point
rerun_proof: make:check-fragments

Layout: each configured set has head.part, sorted table directories (each with
head.part and one row per other .part file), and tail.part. Table heads include
section prose and the two table header lines, so each header appears once;
tail.part holds fixed text after the final table. The non-.md suffix is configured:
fragments have no frontmatter and are outside check_A and review_docs' Markdown
walks. Their links are relative to the assembled reference, where check_Q reads
them. Keel's fragment folders are excluded from generation. This script ships;
generated projects list no fragment sets and edit their references by hand.

An entry's first cell names its key (its first code span, or the whole cell).
An entry's file name is its percent-encoded key (urllib quote, nothing safe),
either alone or after a six-digit order prefix and "-"; one table uses one
form. Key-named tables sort by encoded key; prefixed tables keep their
historical order, and a new entry takes the next prefix. A name that does not
encode its key, or a table that mixes the forms, is an error, so two parallel
additions with distinct keys never share a file name.
Keys must be unique within a table. Every entry is exactly one complete table row
with the header's column count. Unexpected files, missing heads or registered
folders, duplicate keys and stray folders under the configured root are errors.

The output owns its updated: stamp: assembly retains that line verbatim (the
head supplies it only for a new output). Restamp_docs remains its only date
writer. --check uses the same retention rule, so a later restamp cannot create
an assembly repair loop, including when the newest entry is deleted.

Changelog entries use a six-digit positive order, '-', a lowercase UUID hex
identity and the configured suffix. Parallel lanes take the next order and
different UUIDs; merging cannot rename or reorder existing entries. Each file
holds one bullet, its continuation lines and intentional blank separators.
Release is a consuming operation: it refuses repetition, validates everything
before writing, atomically publishes the changelog, then deletes its entries.
It never tags. An interrupted deletion needs recovery before another assembly;
atomic publication protects individual outputs, not the multi-file operation.
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path
from typing import NoReturn
from urllib.parse import quote

if __name__ == "__main__":
    sys.dont_write_bytecode = True

import config_loader
from atomic_write import write_if_changed
from exit_codes import ExitCode, finish, report

_KEY = ("reference_fragments",)
_PREFIX = re.compile(r"\d{6}-")
_CHANGELOG_KEYS = (
    ("changelog_fragments", "folder"),
    ("changelog_fragments", "categories"),
    ("changelog_fragments", "unsectioned"),
)
_GOVERNANCE = {"README.md", "AGENT.md", "CLAUDE.md"}


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


def entry_key(cell: str) -> str:
    """Return the key a row's first cell names: its first code span, or itself."""
    code = re.search(r"`([^`]+)`", cell)
    return code.group(1) if code else cell


def entry_stem(key: str) -> str:
    """Return the file stem a key-named entry must have."""
    # safe="" encodes "/" too, so a key never names a subdirectory.
    return quote(key, safe="")


def _form(entry: Path, key: str, suffix: str) -> str:
    stem, name = entry_stem(key), entry.name
    if name == stem + suffix:
        return "key-named"
    prefix = _PREFIX.match(name)
    if prefix and name[prefix.end() :] == stem + suffix:
        return "prefixed"
    raise FragmentError(
        f"{entry}: file name must be {stem}{suffix}, optionally after a "
        "six-digit order prefix and '-', because the name is the encoded key"
    )


def validate_names(entries: list[Path]) -> None:
    """Refuse names exceeding the portable byte limit or differing only by case."""
    names: dict[str, Path] = {}
    for entry in entries:
        if len(entry.name.encode("utf-8")) > 255:
            raise FragmentError(f"{entry}: entry name exceeds 255 bytes")
        folded = entry.name.casefold()
        if folded in names:
            raise FragmentError(
                f"{entry}: case-insensitive name collision with {names[folded]}"
            )
        names[folded] = entry


def _table(folder: Path, suffix: str) -> str:
    head_path = folder / ("head" + suffix)
    head = _text(head_path)
    lines = head.splitlines(keepends=True)
    if len(lines) < 2 or not re.fullmatch(r"[| :\-]+\n", lines[-1]):
        raise FragmentError(f"{head_path}: table head must end with its separator")
    columns = len(_cells(lines[-2]))
    keys: set[str] = set()
    forms: dict[str, Path] = {}
    rows = []
    entries = sorted(folder.iterdir())
    validate_names(entries)
    for entry in entries:
        if entry == head_path:
            continue
        if not entry.is_file() or entry.suffix != suffix:
            raise FragmentError(f"{entry}: unexpected table member")
        row = _text(entry)
        cells = _cells(row)
        if len(cells) != columns or not cells[0]:
            raise FragmentError(f"{entry}: expected {columns} cells and a nonblank key")
        key = entry_key(cells[0])
        if key in keys:
            raise FragmentError(f"{entry}: duplicate key {key!r}")
        keys.add(key)
        forms.setdefault(_form(entry, key, suffix), entry)
        if len(forms) > 1:
            raise FragmentError(
                f"{entry}: table mixes key-named and prefixed entries "
                f"(also {forms['key-named'].name}, {forms['prefixed'].name}); "
                "use one form per table"
            )
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
        paths = ", ".join(
            str(path.relative_to(root)) for path in sorted(set(folders) ^ discovered)
        )
        raise FragmentError(f"unregistered or missing fragment folders: {paths}")
    return rendered


def _release_arguments(version: str | None, date: str | None, *, check: bool) -> None:
    if version is None and date is None:
        return
    if version is None or date is None or check:
        raise FragmentError(
            "--release and --date are required together, without --check"
        )
    if not re.fullmatch(
        r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version
    ):
        raise FragmentError(
            f"malformed release version: {version}; use X.Y.Z without v"
        )
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", date):
        raise FragmentError(f"malformed release date: {date}; use YYYY-MM-DD")
    try:
        datetime.date.fromisoformat(date)
    except ValueError as exc:
        raise FragmentError(f"malformed release date: {date}") from exc


def _changelog_entries(folder: Path, suffix: str) -> tuple[str, list[Path]]:
    entries = sorted(folder.iterdir())
    validate_names(entries)
    texts, sources = [], []
    for entry in entries:
        if entry.name in _GOVERNANCE:
            continue
        if entry.is_symlink() or not entry.is_file():
            raise FragmentError(f"{entry}: expected an entry file")
        if not re.fullmatch(
            r"[0-9]{6}-[0-9a-f]{32}" + re.escape(suffix), entry.name
        ) or entry.name.startswith("000000-"):
            raise FragmentError(
                f"{entry}: name must be a positive six-digit order, '-', "
                f"32 lowercase UUID hex digits and {suffix}"
            )
        text = _text(entry)
        lines = text.strip("\n").splitlines()
        if (
            not text.endswith("\n")
            or not lines
            or not lines[0].startswith("- ")
            or any(line and not line.startswith((" ", "\t")) for line in lines[1:])
        ):
            raise FragmentError(
                f"{entry}: expected one bullet and indented continuations, ending in a newline"
            )
        texts.append(text)
        sources.append(entry)
    return "".join(texts), sources


def changelog_plan(
    root: Path, version: str | None, date: str | None
) -> tuple[list[tuple[Path, str]], list[Path]]:
    """Return a lossless changelog publication and, for a release, consumed files."""
    config = config_loader.resolve(
        config_loader.read(str(root)),
        config_loader.rows(_KEY, *_CHANGELOG_KEYS),
        config_loader.CONFIG_FILE,
    )
    folder, categories, unsectioned = (config[key] for key in _CHANGELOG_KEYS)
    if folder is None:
        if categories or unsectioned is not None or version is not None:
            raise FragmentError(
                "changelog fragments disabled: categories must be empty and unsectioned null; release is unavailable"
            )
        return [], []
    base = _path(root, folder)
    names = [unsectioned, *categories]
    if (
        not categories
        or any(
            not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_-]*", name)
            for name in names
        )
        or len(set(names)) != len(names)
    ):
        raise FragmentError(
            "changelog categories and unsectioned must be distinct lowercase folder names"
        )
    members = sorted(base.iterdir())
    unexpected = [path for path in members if path.name not in {*names, *_GOVERNANCE}]
    if unexpected:
        raise FragmentError(f"{unexpected[0]}: unexpected changelog member")
    suffix = config[_KEY]["suffix"]
    body = "\n"
    sources = []
    for name in names:
        path = _path(root, str(base.relative_to(root) / name))
        text, entries = _changelog_entries(path, suffix)
        sources.extend(entries)
        if entries:
            body += (f"### {name.title()}\n" if name != unsectioned else "") + text
    output = root / "CHANGELOG.md"
    current = _text(output)
    headings = list(re.finditer(r"(?m)^## .*\n", current))
    unreleased = [
        i for i, match in enumerate(headings) if match.group() == "## [Unreleased]\n"
    ]
    if len(unreleased) != 1:
        raise FragmentError(
            "CHANGELOG.md: expected exactly one ## [Unreleased] heading"
        )
    index = unreleased[0]
    heading = headings[index]
    end = headings[index + 1].start() if index + 1 < len(headings) else len(current)
    head, tail = current[: heading.end()], current[end:]
    if version is not None:
        if re.search(r"(?m)^## \[" + re.escape(version) + r"\](?:\s|$)", current):
            raise FragmentError(
                f"CHANGELOG.md: version {version} already has a heading"
            )
        if not sources:
            raise FragmentError("changelog release has no entries")
        body = f"\n## [{version}] — {date}\n" + body
    return [(output, head + body + tail)], sources if version is not None else []


def main(argv: list[str] | None = None) -> ExitCode:
    """Check or assemble references, reporting every refused input by name."""
    parser = Parser(
        description="Assemble configured reference and changelog entry files."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Project root (default: this script's checkout).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report stale references or Unreleased without writing anything.",
    )
    parser.add_argument(
        "--release", help="Rotate entries to version X.Y.Z and delete them; never tag."
    )
    parser.add_argument(
        "--date", help="Explicit release date YYYY-MM-DD (requires --release)."
    )
    try:
        args = parser.parse_args(argv)
        if not args.root.is_dir():
            return report(
                ExitCode.USAGE,
                "assemble_fragments: the root is not an existing directory",
                config_loader.checkout_name(str(args.root)),
                "pass --root a checkout directory that exists, then rerun",
            )
        _release_arguments(args.release, args.date, check=args.check)
        rendered = assemble(args.root)
        changelog, consumed = changelog_plan(args.root, args.release, args.date)
        rendered.extend(changelog)
        stale = [
            (path, text)
            for path, text in rendered
            if not path.exists() or path.read_bytes() != text.encode("utf-8")
        ]
        if args.check and stale:
            return report(
                ExitCode.FAILURE,
                "stale fragment output",
                ", ".join(str(p) for p, _ in stale),
                "run make assemble-fragments",
            )
        for path, text in stale:
            write_if_changed(str(path), text)
        for path in consumed:
            path.unlink()
    except config_loader.ConfigError as exc:
        return report(
            ExitCode.USAGE if config_loader.is_conflict(exc) else ExitCode.CONFIG,
            "fragment configuration refused",
            str(exc),
            "fix config/project.json reference_fragments or changelog_fragments",
        )
    except (FragmentError, OSError, UnicodeError) as exc:
        return report(
            ExitCode.USAGE,
            "fragment assembly refused",
            str(exc),
            "fix the named fragment or configuration and rerun",
        )
    return ExitCode.SUCCESS


if __name__ == "__main__":
    finish(main())
