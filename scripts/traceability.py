"""
title: traceability — the requirement-id grammar, the spec reader, the verdicts and the matrix
kind: script
layer: n/a
summary: The one home of requirement traceability's rules, imported by scripts/trace_requirements.py (the command) and tests/integration/test_requirement_traceability.py (the gate test). load_policy reads the `traceability` block of config/project.json and refuses a missing, unknown or mistyped key by its dotted name. parse_id is the only parser of an id: `<prefix><digits>` or `<prefix><digits>#AC-<n>`, where the prefix and its digit count are a row of `traceability.id_prefixes`, the longest listed prefix wins with no fallback, and an unlisted prefix is refused. read_specs defines a requirement from a heading and a criterion from a `- AC-<n>: <text>` line in each `kind: spec` document under `traceability.specs_root`, and refuses by `file:line` whatever was meant as one and is not: an id that is not a plain heading's bare first word, a list item opening with `AC-` in any other form, a fenced block never closed, and a document of another kind that would define a requirement if read as a spec; scan_tests reads `traceability.marker` calls from the files pytest collects under `traceability.tests_root` through scripts/pytest_markers.py, entering no directory pytest's `norecursedirs` skips and counting no definition pytest would not collect; judge gives every unit one verdict from `covered`, `gap` and `uncovered`, and a finding for each fault; build_matrix and render give the canonical JSON the command writes. A bare requirement id never covers a requirement that has numbered criteria. It imports no test and runs none, so it says a test names a requirement and never that the test proves it. It writes nothing and is never run.
"""

from __future__ import annotations

import ast
import json
import keyword
import os
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass

import check_structure as cs
import pytest_markers

__all__ = [
    "AC_SEP",
    "BLOCK",
    "EMPTY_KEY",
    "FAMILIES",
    "FINDING_KINDS",
    "GAPS_KEY",
    "MANIFEST",
    "RESULTS",
    "SOURCES",
    "STATES",
    "VERDICTS",
    "Bounds",
    "Catalogue",
    "Citation",
    "Judgement",
    "Policy",
    "Prefix",
    "Requirement",
    "TraceError",
    "TraceId",
    "Unit",
    "build_matrix",
    "id_shaped",
    "is_prefix_shape",
    "judge",
    "load_policy",
    "parse_criterion_line",
    "parse_id",
    "parse_listed_id",
    "read_bounds",
    "read_specs",
    "render",
    "scan_tests",
    "stopped_matrix",
    "trace_tree",
]

MANIFEST = "config/project.json"
BLOCK = "traceability"
GAPS_KEY = BLOCK + ".gaps"
EMPTY_KEY = BLOCK + ".no_requirements"

# The closed vocabularies. The order is the order config/traceability/
# matrix.schema.json lists them in; tests/unit/scripts/test_traceability.py
# holds the two equal.
FAMILIES = ("requirement", "goal")
SOURCES = ("spine", "self")
VERDICTS = ("covered", "gap", "uncovered")
FINDING_KINDS = (
    "uncovered",
    "marker-malformed-id",
    "marker-undefined-id",
    "marker-unreadable",
    "marker-unattached",
    "gap-malformed-id",
    "gap-undefined-id",
    "gap-redundant",
    "no-requirements",
    "stale-no-requirements",
)
STATES = ("traced", "no-requirements", "incomplete", "refused")
RESULTS = ("pass", "fail", "incomplete", "refused")
_STOPPED = ("incomplete", "refused")

AC_SEP = "#AC-"
_CRITERION_WORD = "AC-"
_LIST_MARKERS = ("-", "*", "+")
_ORDERED_ENDS = (".", ")")
_BLANKS = " \t"
# What Markdown puts around a word: emphasis, a code span, a link or a quote.
_WRAPPERS = "*_`~[]()<>\"'"
# The punctuation a sentence puts after a word.
_CLOSERS = ".,:;!?"
# The deepest indentation at which CommonMark still reads `#` as a heading.
_HEADING_INDENT_MAX = 3

_BLOCK_KEYS = (
    "id_prefixes",
    "specs_root",
    "tests_root",
    "marker",
    "gaps",
    "no_requirements",
    "matrix_path",
    "matrix_schema",
)
_ROW_KEYS = ("prefix", "family", "digits", "source")
_PATH_KEYS = ("specs_root", "tests_root", "matrix_path", "matrix_schema")
# How much of a spec's or config's own text an error message quotes.
_SHOWN_MAX = 80
_SPEC_KIND = "spec"
_SPEC_SUFFIX = ".md"
_TEST_SUFFIX = ".py"


class TraceError(Exception):
    """Traceability cannot be judged: the config block, a spec or a test file
    is malformed or unreadable. Never a verdict; the command exits 2 on it."""


@dataclass(frozen=True)
class Prefix:
    """One `traceability.id_prefixes` row."""

    prefix: str
    family: str
    digits: int
    source: str


@dataclass(frozen=True)
class Policy:
    """The `traceability` block, validated."""

    prefixes: tuple[Prefix, ...]
    specs_root: str
    tests_root: str
    marker: str
    gaps: Mapping[str, str]
    no_requirements: str | None
    matrix_path: str
    matrix_schema: str


@dataclass(frozen=True)
class TraceId:
    """A parsed id: the requirement, and the criterion number or None."""

    req: str
    ac: int | None = None

    def __str__(self) -> str:
        return self.req if self.ac is None else "%s%s%d" % (self.req, AC_SEP, self.ac)


@dataclass(frozen=True)
class Requirement:
    """A requirement a spec defines: where, and where each criterion is."""

    id: str
    where: str
    criteria: Mapping[int, str]


@dataclass(frozen=True)
class Catalogue:
    """Every requirement the specs define, by id."""

    requirements: Mapping[str, Requirement]

    def units(self) -> list[str]:
        """The ids a test must name, in report order: each criterion of a
        requirement that has criteria (by number), else the requirement."""
        out = []
        for req_id in sorted(self.requirements):
            criteria = self.requirements[req_id].criteria
            out.extend(str(TraceId(req_id, n)) for n in sorted(criteria))
            if not criteria:
                out.append(req_id)
        return out


@dataclass(frozen=True)
class Citation:
    """One readable marker call that sits on collected tests: the ids it
    names as written, the tests it applies to, and its `file:line`."""

    ids: tuple[str, ...]
    tests: tuple[str, ...]
    where: str


@dataclass(frozen=True)
class Unit:
    """One judged unit: a criterion, or a requirement that has none."""

    id: str
    req: str
    criterion: int | None
    where: str
    verdict: str
    tests: tuple[str, ...]
    gap: str | None


@dataclass(frozen=True)
class Judgement:
    """What judge decided. `counts` values are None when there was nothing to
    count, which is not the same as zero."""

    units: tuple[Unit, ...]
    findings: list[dict[str, object]]
    whole: Mapping[str, tuple[str, ...]]
    state: str
    result: str
    counts: Mapping[str, int | None]


@dataclass(frozen=True)
class Bounds:
    """What the matrix schema fixes: its version and the two length caps."""

    schema_version: int
    reason_max: int
    id_max: int


# ----------------------------------------------------------------- the grammar


def is_prefix_shape(text: object) -> bool:
    """True when *text* is a prefix a registry row may list: upper-case ASCII
    words (a letter, then letters or digits) each followed by one dash, as in
    `REQ-` or `REQ-SELF-`. The only pattern in this module; an id is parsed by
    slicing against a listed prefix, never by a pattern."""
    return isinstance(text, str) and bool(
        re.fullmatch(r"(?:[A-Z][A-Z0-9]*-)+", text, re.ASCII)
    )


def _ascii_digits(text: str) -> bool:
    # str.isdigit alone accepts digits of other scripts, which int() would
    # then read as the same number: two spellings of one id.
    return text.isascii() and text.isdigit()


def _criterion_number(text: str) -> int | None:
    """The positive integer *text* spells with no leading zero, else None.
    Shared by the id parser and the spec reader so `AC-<n>` reads one way."""
    if not _ascii_digits(text) or text[0] == "0":
        return None
    return int(text)


def _longest(text: str, prefixes: Sequence[Prefix]) -> Prefix | None:
    best = None
    for row in prefixes:
        if text.startswith(row.prefix) and (
            best is None or len(row.prefix) > len(best.prefix)
        ):
            best = row
    return best


def parse_listed_id(text: object, prefixes: Sequence[Prefix]) -> tuple[Prefix, TraceId]:
    """The registry row *text* parses under, and the id. Raises TraceError
    when *text* is not `<prefix><digits>` or `<prefix><digits>#AC-<n>` for the
    longest listed prefix it starts with: there is no falling back to a shorter
    prefix, and whitespace or a line end anywhere is part of the text."""
    if not isinstance(text, str):
        raise TraceError("an id is a string, not %s" % type(text).__name__)
    row = _longest(text, prefixes)
    if row is None:
        raise TraceError(
            "starts with no prefix %s `%s.id_prefixes` lists" % (MANIFEST, BLOCK)
        )
    head, sep, tail = text.partition(AC_SEP)
    number = head[len(row.prefix) :]
    if len(number) != row.digits or not _ascii_digits(number):
        raise TraceError(
            "prefix %s takes exactly %d ASCII digits" % (row.prefix, row.digits)
        )
    if not sep:
        return row, TraceId(head)
    criterion = _criterion_number(tail)
    if criterion is None:
        raise TraceError("`%s` takes a positive number with no leading zero" % AC_SEP)
    return row, TraceId(head, criterion)


def parse_id(text: object, prefixes: Sequence[Prefix]) -> TraceId:
    """The id of a requirement or of one of its criteria. parse_listed_id,
    and the prefix must be of the `requirement` family: a goal is not a unit a
    test covers."""
    row, parsed = parse_listed_id(text, prefixes)
    if row.family != "requirement":
        raise TraceError(
            "prefix %s is of family %s, not requirement" % (row.prefix, row.family)
        )
    return parsed


def id_shaped(token: str, prefixes: Sequence[Prefix]) -> bool:
    """True when *token* is written like an id, so a spec heading that opens
    with it must parse: it starts with a listed prefix, or with any
    prefix-shaped word followed by a digit (`FOO-0001`). `X-ray` is not."""
    if _longest(token, prefixes) is not None:
        return True
    stem, dash, rest = token.partition(AC_SEP)[0].rpartition("-")
    return bool(dash) and is_prefix_shape(stem + dash) and _ascii_digits(rest[:1])


def _bare(word: str) -> str:
    """*word* without the Markdown that can wrap it: emphasis, a code span,
    brackets or quotes at either end."""
    return word.strip(_WRAPPERS)


def _list_item(line: str) -> str | None:
    """The text of the list item *line* opens, however it is written: after
    any indentation and blockquote `>`, a bullet (`-`, `*`, `+`) or an ordered
    marker (`1.`, `1)`), then spaces or tabs. None when it opens no list item."""
    rest = line.lstrip(_BLANKS)
    while rest.startswith(">"):
        rest = rest[1:].lstrip(_BLANKS)
    if rest[:1] in _LIST_MARKERS:
        after = rest[1:]
    else:
        digits = len(rest) - len(rest.lstrip("0123456789"))
        if not digits or rest[digits : digits + 1] not in _ORDERED_ENDS:
            return None
        after = rest[digits + 1 :]
    if after[:1] not in tuple(_BLANKS):
        return None
    return after.lstrip(_BLANKS)


def _opens_with_criterion(item: str) -> bool:
    """True when a list item's text opens with `AC-`, bare or behind a task
    box (`[ ]`, `[x]`) or Markdown wrapping (`**AC-1**`)."""
    if item[:1] == "[" and item[2:3] == "]":
        item = item[3:].lstrip(_BLANKS)
    return item.lstrip(_WRAPPERS).startswith(_CRITERION_WORD)


def parse_criterion_line(line: str) -> int | None:
    """The criterion number a spec line defines, or None when the line is not
    a criterion. Any list item that opens with `AC-` is meant as one, so it
    must be exactly `- AC-<n>: <text>` at the left margin. An indented or
    quoted item, another bullet character, an ordered or task item, more than
    one space after the bullet, a wrapped `**AC-1**`, a leading zero or a
    missing text raises TraceError rather than leaving a criterion the gate
    never saw."""
    item = _list_item(line)
    if item is None or not _opens_with_criterion(item):
        return None
    opener = _LIST_MARKERS[0] + " " + _CRITERION_WORD
    if not line.startswith(opener):
        raise TraceError(
            "a criterion is written `%s<n>: <text>` at the left margin, with "
            "one space after the dash and nothing around `%s<n>`"
            % (opener, _CRITERION_WORD)
        )
    number, colon, text = line[len(opener) :].partition(":")
    criterion = _criterion_number(number)
    if criterion is None or not colon:
        raise TraceError(
            "a criterion is `%s<n>: <text>`, <n> positive with no leading zero" % opener
        )
    if not text.startswith(" ") or not text.strip():
        raise TraceError("criterion %d has no text after `: `" % criterion)
    return criterion


# ------------------------------------------------------------------ the policy


def _key(name: str) -> str:
    return "%s `%s.%s`" % (MANIFEST, BLOCK, name)


def _keys(found: Mapping[str, object], wanted: Sequence[str], where: str) -> None:
    for name in wanted:
        if name not in found:
            raise TraceError("%s is missing" % _key(where + name))
    for name in sorted(found):
        if name not in wanted and name != "_comment":
            raise TraceError("%s is not a key this block has" % _key(where + name))


def _rel_path(value: object, name: str) -> str:
    """A project-relative POSIX path that stays below the root as written.
    Where it resolves (a symlink) is the command's check, made before it
    reads or writes."""
    # An empty part covers a leading, trailing or doubled slash, so an
    # absolute path fails the same test as `a//b`.
    if (
        not isinstance(value, str)
        or "\\" in value
        or any(
            part in ("", ".", "..") or part != part.strip() for part in value.split("/")
        )
    ):
        raise TraceError(
            "%s must be a path below the project root, with no `..`" % _key(name)
        )
    return value


def _prefix_row(row: object, index: int) -> Prefix:
    name = "id_prefixes[%d]" % index
    if not isinstance(row, dict):
        raise TraceError("%s must be an object" % _key(name))
    for field in _ROW_KEYS:
        if field not in row:
            raise TraceError("%s is missing `%s`" % (_key(name), field))
    for field in sorted(row):
        if field not in _ROW_KEYS:
            raise TraceError("%s has an unknown key `%s`" % (_key(name), field))
    if not is_prefix_shape(row["prefix"]):
        raise TraceError(
            "%s `prefix` must be upper-case words each ending in a dash" % _key(name)
        )
    digits = row["digits"]
    if isinstance(digits, bool) or not isinstance(digits, int) or digits < 1:
        raise TraceError("%s `digits` must be a positive integer" % _key(name))
    if row["family"] not in FAMILIES:
        raise TraceError("%s `family` must be one of %s" % (_key(name), FAMILIES))
    if row["source"] not in SOURCES:
        raise TraceError("%s `source` must be one of %s" % (_key(name), SOURCES))
    return Prefix(row["prefix"], row["family"], digits, row["source"])


def load_policy(manifest: object) -> Policy:
    """The validated `traceability` block of a loaded config/project.json.
    Raises TraceError naming the dotted key for a missing block, a missing or
    unknown key, or a value of the wrong type or shape; nothing defaults."""
    block = manifest.get(BLOCK) if isinstance(manifest, dict) else None
    if not isinstance(block, dict):
        raise TraceError("%s has no `%s` object" % (MANIFEST, BLOCK))
    _keys(block, _BLOCK_KEYS, "")

    rows = block["id_prefixes"]
    if not isinstance(rows, list) or not rows:
        raise TraceError("%s must be a non-empty list of rows" % _key("id_prefixes"))
    prefixes = tuple(_prefix_row(row, i) for i, row in enumerate(rows))
    if len({p.prefix for p in prefixes}) != len(prefixes):
        raise TraceError("%s lists a prefix twice" % _key("id_prefixes"))

    paths = {name: _rel_path(block[name], name) for name in _PATH_KEYS}

    marker = block["marker"]
    if (
        not isinstance(marker, str)
        or not marker.isascii()
        or not marker.isidentifier()
        or keyword.iskeyword(marker)
    ):
        raise TraceError("%s must be a marker name (an identifier)" % _key("marker"))

    gaps = block["gaps"]
    if not isinstance(gaps, dict):
        raise TraceError("%s must be an object of id to reason" % _key("gaps"))
    for unit, reason in gaps.items():
        if not isinstance(reason, str) or not reason.strip():
            raise TraceError(
                "%s gives %r no reason; a gap is excused only with one"
                % (_key("gaps"), unit[:_SHOWN_MAX])
            )

    empty = block["no_requirements"]
    if empty is not None and (not isinstance(empty, str) or not empty.strip()):
        raise TraceError(
            "%s must be null, or the reason this project has no requirement yet"
            % _key("no_requirements")
        )
    return Policy(
        prefixes=prefixes,
        specs_root=paths["specs_root"],
        tests_root=paths["tests_root"],
        marker=marker,
        gaps=dict(gaps),
        no_requirements=empty,
        matrix_path=paths["matrix_path"],
        matrix_schema=paths["matrix_schema"],
    )


# ------------------------------------------------------------ reading the tree


def _files_under(
    root: str,
    base: str,
    key: str,
    suffix: str,
    enters: Callable[[str, str], bool] | None = None,
) -> list[str]:
    """The project-relative POSIX paths of the `*suffix` files under
    *root*/*base*, sorted. A symlink that resolves to something else under the
    same directory is an alias of a file the walk already reads and is left
    out; one that resolves anywhere else raises TraceError, as does a missing
    directory. A directory below *base* for which *enters*(path, rel) is false
    is not walked."""
    top = os.path.join(root, *base.split("/"))
    if not os.path.isdir(top):
        raise TraceError("%s %r is not a directory" % (_key(key), base))
    real_top = os.path.realpath(top)

    def alias(path: str, rel: str) -> bool:
        if not os.path.islink(path):
            return False
        target = os.path.realpath(path)
        if os.path.commonpath([real_top, target]) != real_top:
            raise TraceError(
                "%s is a symlink out of %s; a file read through it is not "
                "this project's" % (rel, _key(key))
            )
        return True

    out = []
    for folder, dirs, files in os.walk(top):
        rel_dir = os.path.relpath(folder, root).replace(os.sep, "/")
        dirs[:] = sorted(
            d
            for d in dirs
            if not alias(os.path.join(folder, d), rel_dir + "/" + d)
            and (enters is None or enters(os.path.join(folder, d), rel_dir + "/" + d))
        )
        for name in sorted(files):
            rel = rel_dir + "/" + name
            if name.endswith(suffix) and not alias(os.path.join(folder, name), rel):
                out.append(rel)
    return sorted(out)


def _read(root: str, rel: str) -> str:
    try:
        with open(os.path.join(root, *rel.split("/")), encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        # The exception's own text can quote file bytes; its type says enough.
        raise TraceError("%s cannot be read (%s)" % (rel, type(exc).__name__)) from None


def _heading(lines: Sequence[str], index: int) -> tuple[int, str, bool] | None:
    """(level, text, plain) when `lines[index]` is a Markdown heading, else
    None. *plain* is true for the one form that defines a requirement: `#`
    marks at the left margin. It is false for a heading indented by up to
    three spaces and for a setext heading (a text line with a line of `=` or
    `-` under it), which a renderer shows as headings just the same."""
    line = lines[index]
    plain = cs._ATX_HEADING.match(line)
    if plain is not None:
        return len(line) - len(line.lstrip("#")), plain.group(1), True
    inner = line.lstrip(" ")
    indent = len(line) - len(inner)
    if 0 < indent <= _HEADING_INDENT_MAX:
        indented = cs._ATX_HEADING.match(inner)
        if indented is not None:
            return len(inner) - len(inner.lstrip("#")), indented.group(1), False
    below = lines[index + 1] if index + 1 < len(lines) else ""
    # A list item with a rule under it stays a list item, so a criterion line
    # is never mistaken for a heading's text.
    if (
        line.strip()
        and below.strip()
        and cs._SETEXT_UNDERLINE.match(below)
        and _list_item(line) is None
    ):
        return (1 if "=" in below else 2), line.strip(), False
    return None


def _names_requirement(word: str, prefixes: Sequence[Prefix]) -> bool:
    """True when *word*, without Markdown wrapping or closing punctuation, is
    a whole requirement id under the registry."""
    try:
        row, parsed = parse_listed_id(word.strip(_WRAPPERS + _CLOSERS), prefixes)
    except TraceError:
        return False
    return row.family == "requirement" and parsed.ac is None


def _refuse_a_heading_that_hides_an_id(
    text: str, plain: bool, prefixes: Sequence[Prefix]
) -> None:
    """Raise TraceError for a heading that is not a definition yet reads like
    one to its author: an id-shaped first word on an indented or setext
    heading, an id wrapped in Markdown as the first word, or a requirement id
    that is not the first word. Each would otherwise define nothing, silently."""
    words = text.split()
    if not words:
        return
    first = words[0]
    shown = ascii(first[:_SHOWN_MAX])
    if id_shaped(first, prefixes) or id_shaped(_bare(first), prefixes):
        if not plain:
            raise TraceError(
                "heading id %s sits on an indented or underlined heading; a "
                "requirement is defined by `#` marks at the left margin" % shown
            )
        raise TraceError(
            "heading id %s is wrapped in Markdown; write the id bare as the "
            "heading's first word" % shown
        )
    for word in words[1:]:
        if _names_requirement(word, prefixes):
            raise TraceError(
                "the heading names %s but does not open with it; a heading "
                "defines a requirement only by its first word, so open with "
                "the id or name none"
                % ascii(word.strip(_WRAPPERS + _CLOSERS)[:_SHOWN_MAX])
            )


def _spec_requirements(
    rel: str, text: str, policy: Policy, found: dict[str, Requirement]
) -> None:
    lines, open_fence = cs._fence_scan(text)
    if open_fence:
        # Every line after it is blanked as code, so a requirement written
        # below would define nothing and say nothing.
        raise TraceError(
            "%s:%d: this fenced block is never closed, so everything below it "
            "is read as code" % (rel, open_fence)
        )
    body_starts = cs._frontmatter_end(text.split("\n"))
    open_req: str | None = None
    open_level = 0
    criteria: dict[str, dict[int, str]] = {}
    for number, line in enumerate(lines, 1):
        if number <= body_starts:
            continue
        where = "%s:%d" % (rel, number)
        heading = _heading(lines, number - 1)
        try:
            if heading is None:
                criterion = parse_criterion_line(line)
                if criterion is None:
                    continue
                if open_req is None:
                    raise TraceError("a criterion outside any requirement's section")
                if criterion in criteria[open_req]:
                    raise TraceError(
                        "criterion %d of %s is defined twice" % (criterion, open_req)
                    )
                criteria[open_req][criterion] = where
                continue
            level, title, plain = heading
            words = title.split(None, 1)
            if not plain or not words or not id_shaped(words[0], policy.prefixes):
                _refuse_a_heading_that_hides_an_id(title, plain, policy.prefixes)
                if plain and open_req is not None and level <= open_level:
                    open_req = None
                continue
            if open_req is not None and level <= open_level:
                open_req = None
            try:
                row, parsed = parse_listed_id(words[0], policy.prefixes)
            except TraceError as exc:
                shown = ascii(words[0][:_SHOWN_MAX])
                raise TraceError("heading id %s %s" % (shown, exc)) from None
            if parsed.ac is not None:
                raise TraceError(
                    "a heading defines a requirement; a criterion is a list line"
                )
            if row.family != "requirement":
                continue
            if row.source != "self":
                raise TraceError(
                    "prefix %s has source %s, so its ids are defined elsewhere "
                    "and no spec here may define one" % (row.prefix, row.source)
                )
            if open_req is not None:
                raise TraceError(
                    "%s is defined inside the section of %s; requirements do "
                    "not nest" % (parsed.req, open_req)
                )
            if parsed.req in found or parsed.req in criteria:
                raise TraceError("%s is defined twice" % parsed.req)
        except TraceError as exc:
            raise TraceError("%s: %s" % (where, exc)) from None
        open_req, open_level = parsed.req, level
        criteria[open_req] = {}
        found[open_req] = Requirement(open_req, where, criteria[open_req])


def read_specs(root: str, policy: Policy) -> Catalogue:
    """Every requirement the `kind: spec` documents under
    `traceability.specs_root` define. A heading whose first word is an id of a
    `requirement` prefix defines it; a `- AC-<n>: <text>` line below, before
    the next heading of the same or a higher level, defines a criterion.
    Fenced blocks and comments define nothing. Raises TraceError, by
    `file:line`, for anything written like an id or a criterion that does not
    parse, for a duplicate, and for a document of another kind that, read as a
    spec, would define a requirement or be refused: its requirements would
    otherwise go untraced without a word."""
    found: dict[str, Requirement] = {}
    for rel in _files_under(root, policy.specs_root, "specs_root", _SPEC_SUFFIX):
        text = _read(root, rel)
        front = cs.parse_frontmatter(os.path.join(root, *rel.split("/")))
        if front is None:
            raise TraceError("%s has a missing or unterminated frontmatter block" % rel)
        if front.get("kind") == _SPEC_KIND:
            _spec_requirements(rel, text, policy, found)
            continue
        kind = ascii(str(front.get("kind"))[:_SHOWN_MAX])
        unread: dict[str, Requirement] = {}
        try:
            _spec_requirements(rel, text, policy, unread)
        except TraceError as exc:
            raise TraceError(
                "%s; this document's frontmatter says kind %s, and only `kind: "
                "%s` is traced, so fence the example or make it a spec"
                % (exc, kind, _SPEC_KIND)
            ) from None
        if unread:
            first = next(iter(unread.values()))
            raise TraceError(
                "%s: %s is defined in a document whose frontmatter says kind "
                "%s; only `kind: %s` is traced, so set that kind, fence the "
                "example, or move the document out of %s"
                % (first.where, first.id, kind, _SPEC_KIND, _key("specs_root"))
            )
    return Catalogue(found)


def scan_tests(
    root: str, policy: Policy, rule: Sequence[Sequence[str]]
) -> tuple[list[Citation], list[dict[str, object]]]:
    """(citations, findings) from every file under `traceability.tests_root`
    that pytest collects as a test module under *rule* (python_functions,
    python_classes, python_files, norecursedirs). A file below a directory
    pytest does not enter is not read, so its markers cover nothing. A
    `<marker>(...)` call whose arguments are not string literals, or a bare
    `<marker>` with no call, is a
    `marker-unreadable` finding; a call that applies to no collected test is a
    `marker-unattached` finding per id and its ids cover nothing. No test file
    is imported. Raises TraceError when a collected file does not parse."""
    marker = policy.marker
    cited: list[tuple[tuple[str, int, int], Citation]] = []
    faults: list[tuple[tuple[str, int, int], dict[str, object]]] = []
    norecurse = rule[3]

    def enters(path: str, rel: str) -> bool:
        return pytest_markers.dir_recursed(path, rel, norecurse)

    files = _files_under(root, policy.tests_root, "tests_root", _TEST_SUFFIX, enters)
    for rel in files:
        if not pytest_markers.file_collected(rel, rule[2]):
            continue
        try:
            tree = ast.parse(_read(root, rel))
        except (SyntaxError, ValueError) as exc:
            raise TraceError(
                "%s does not parse (%s), so its markers cannot be read"
                % (rel, type(exc).__name__)
            ) from None
        applies = pytest_markers.marked_tests(tree, marker, rule)
        called = set()
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and pytest_markers.is_marker(node.func, marker)
            ):
                continue
            called.add(id(node.func))
            order = (rel, node.lineno, node.col_offset)
            where = "%s:%d" % (rel, node.lineno)
            ids, unreadable = pytest_markers.marker_ids(node)
            tests = applies.get(id(node), [])
            if unreadable:
                fault = {"kind": "marker-unreadable", "where": where, "id": None}
                faults.append((order, fault))
            elif not tests:
                for one in ids:
                    fault = {"kind": "marker-unattached", "where": where, "id": one}
                    faults.append((order, fault))
            else:
                names = tuple("%s::%s" % (rel, t) for t in tests)
                cited.append((order, Citation(tuple(ids), names, where)))
        for node in ast.walk(tree):
            if pytest_markers.is_marker(node, marker) and id(node) not in called:
                order = (rel, node.lineno, node.col_offset)
                where = "%s:%d" % (rel, node.lineno)
                fault = {"kind": "marker-unreadable", "where": where, "id": None}
                faults.append((order, fault))
    cited.sort(key=lambda pair: pair[0])
    faults.sort(key=lambda pair: (pair[0], str(pair[1]["id"])))
    return [c for _, c in cited], [f for _, f in faults]


# ---------------------------------------------------------------- the verdicts


def _unit_of(
    text: str, catalogue: Catalogue, prefixes: Sequence[Prefix]
) -> TraceId | None:
    """The id *text* parses to when it names a criterion the catalogue
    defines or a defined requirement; None when it names neither. Raises
    TraceError when it does not parse."""
    parsed = parse_id(text, prefixes)
    req = catalogue.requirements.get(parsed.req)
    if req is None or (parsed.ac is not None and parsed.ac not in req.criteria):
        return None
    return parsed


def judge(
    catalogue: Catalogue,
    citations: Iterable[Citation],
    policy: Policy,
    scan_findings: Iterable[Mapping[str, object]] = (),
) -> Judgement:
    """One verdict per unit and one finding per fault.

    A unit is `covered` when a citation names it exactly, else `gap` when a
    `traceability.gaps` row names it, else `uncovered` (a finding). A bare
    requirement id names a unit only when the requirement has no criteria;
    on a requirement that has them it is kept in `whole` and covers nothing.
    A marker or gap id that does not parse, or names nothing defined, and a
    gap for a covered unit, are findings. With no requirement at all the state
    is `no-requirements`: a finding unless `traceability.no_requirements`
    gives a reason, and that reason is itself a finding once a requirement or
    a marker exists."""
    citations = list(citations)
    findings: list[dict[str, object]] = [dict(f) for f in scan_findings]
    gaps_where = "%s %s" % (MANIFEST, GAPS_KEY)
    empty_where = "%s %s" % (MANIFEST, EMPTY_KEY)

    def finding(kind: str, where: str, unit: str | None) -> None:
        findings.append({"kind": kind, "where": where, "id": unit})

    named: dict[str, set[str]] = {}
    whole: dict[str, set[str]] = {}
    for citation in citations:
        for text in citation.ids:
            try:
                parsed = _unit_of(text, catalogue, policy.prefixes)
            except TraceError:
                finding("marker-malformed-id", citation.where, text)
                continue
            if parsed is None:
                finding("marker-undefined-id", citation.where, text)
            elif parsed.ac is None and catalogue.requirements[parsed.req].criteria:
                whole.setdefault(parsed.req, set()).update(citation.tests)
            else:
                named.setdefault(str(parsed), set()).update(citation.tests)

    excused: dict[str, str] = {}
    for text in sorted(policy.gaps):
        try:
            parsed = _unit_of(text, catalogue, policy.prefixes)
        except TraceError:
            finding("gap-malformed-id", gaps_where, text)
            continue
        bare_over_criteria = (
            parsed is not None
            and parsed.ac is None
            and bool(catalogue.requirements[parsed.req].criteria)
        )
        if parsed is None or bare_over_criteria:
            finding("gap-undefined-id", gaps_where, text)
        elif str(parsed) in named:
            finding("gap-redundant", gaps_where, text)
        else:
            excused[str(parsed)] = policy.gaps[text]

    units = []
    for req_id in sorted(catalogue.requirements):
        req = catalogue.requirements[req_id]
        numbers: list[int | None] = sorted(req.criteria) or [None]
        for number in numbers:
            unit_id = str(TraceId(req_id, number))
            where = req.where if number is None else req.criteria[number]
            tests = tuple(sorted(named.get(unit_id, ())))
            if tests:
                verdict = "covered"
            elif unit_id in excused:
                verdict = "gap"
            else:
                verdict = "uncovered"
                finding("uncovered", where, unit_id)
            gap = excused[unit_id] if verdict == "gap" else None
            units.append(Unit(unit_id, req_id, number, where, verdict, tests, gap))

    counts: dict[str, int | None]
    if catalogue.requirements:
        state = "traced"
        counts = {v: sum(1 for u in units if u.verdict == v) for v in VERDICTS}
        if policy.no_requirements is not None:
            finding("stale-no-requirements", empty_where, None)
    else:
        state = "no-requirements"
        counts = dict.fromkeys(VERDICTS)
        if policy.no_requirements is None:
            finding("no-requirements", empty_where, None)
        elif citations:
            finding("stale-no-requirements", empty_where, None)

    findings.sort(key=lambda f: (str(f["kind"]), str(f["where"]), str(f["id"] or "")))
    return Judgement(
        units=tuple(units),
        findings=findings,
        whole={k: tuple(sorted(v)) for k, v in sorted(whole.items())},
        state=state,
        result="fail" if findings else "pass",
        counts=counts,
    )


def trace_tree(
    root: str, policy: Policy, rule: Sequence[Sequence[str]]
) -> tuple[Catalogue, Judgement]:
    """Read the specs and the tests under *root* and judge them: the one
    composition the command and the gate test both run, so neither can judge
    a different tree from the other."""
    catalogue = read_specs(root, policy)
    citations, findings = scan_tests(root, policy, rule)
    return catalogue, judge(catalogue, citations, policy, findings)


# ------------------------------------------------------------------ the matrix


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def read_bounds(schema: object) -> Bounds:
    """The version and the two length caps the loaded matrix schema states,
    so the writer and the schema cannot hold different numbers. Raises
    TraceError when the schema states one of them missing or not positive."""
    try:
        assert isinstance(schema, dict)
        version = schema["properties"]["schema_version"]["const"]
        reason = schema["$defs"]["reason"]["maxLength"]
        cited = schema["$defs"]["cited_id"]["maxLength"]
    except (AssertionError, KeyError, TypeError):
        raise TraceError(
            "the matrix schema must state properties.schema_version.const, "
            "$defs.reason.maxLength and $defs.cited_id.maxLength"
        ) from None
    if not all(_positive_int(v) for v in (version, reason, cited)):
        raise TraceError(
            "the matrix schema's version and length caps must be positive integers"
        )
    return Bounds(schema_version=version, reason_max=reason, id_max=cited)


def _shell(
    policy: Policy, bounds: Bounds, state: str, result: str
) -> dict[str, object]:
    return {
        "schema": policy.matrix_schema,
        "schema_version": bounds.schema_version,
        "state": state,
        "result": result,
        "counts": dict.fromkeys(VERDICTS),
        "requirements": [],
        "findings": [],
    }


def stopped_matrix(policy: Policy, bounds: Bounds, state: str) -> dict[str, object]:
    """The matrix of a run that judged nothing: `incomplete` (written before
    the run, so a killed run leaves red) or `refused` (an input could not be
    read). Counts are null, never zero."""
    if state not in _STOPPED:
        raise ValueError("%r is not a stopped state %s" % (state, _STOPPED))
    return _shell(policy, bounds, state, state)


def build_matrix(
    policy: Policy, bounds: Bounds, catalogue: Catalogue, judgement: Judgement
) -> dict[str, object]:
    """The matrix of a judged run: every requirement with its units, verdicts
    and tests, and every finding. It carries ids, paths, line numbers and the
    config's gap reasons, each cut to the schema's cap; no heading or
    criterion text from a spec, and no machine, user or time."""
    matrix = _shell(policy, bounds, judgement.state, judgement.result)
    matrix["counts"] = dict(judgement.counts)
    by_req: dict[str, list[dict[str, object]]] = {}
    for unit in judgement.units:
        by_req.setdefault(unit.req, []).append(
            {
                "id": unit.id,
                "criterion": unit.criterion,
                "spec": unit.where,
                "verdict": unit.verdict,
                "tests": list(unit.tests),
                "gap": None if unit.gap is None else unit.gap[: bounds.reason_max],
            }
        )
    matrix["requirements"] = [
        {
            "id": req_id,
            "spec": catalogue.requirements[req_id].where,
            "whole_requirement_tests": list(judgement.whole.get(req_id, ())),
            "units": by_req[req_id],
        }
        for req_id in sorted(by_req)
    ]
    matrix["findings"] = [
        {
            "kind": f["kind"],
            "where": f["where"],
            "id": None if f["id"] is None else str(f["id"])[: bounds.id_max],
        }
        for f in judgement.findings
    ]
    return matrix


def render(matrix: Mapping[str, object]) -> str:
    """The canonical text of a matrix: sorted keys, two-space indent, one
    trailing newline, so equal matrices are equal bytes."""
    return json.dumps(matrix, indent=2, sort_keys=True) + "\n"
