"""
title: config_loader — the one way a configured value enters a process
kind: script
layer: n/a
summary: Every configured value comes through here: a key of config/project.json or config/practices.json, or an environment variable the config declares. KEYS is the one table of declared keys, each row a Key giving its path (a tuple of segments, since a segment may hold a dot), its type from the closed set TYPES, its default or NONE (required exactly when the default is NONE, so a default of null stays distinct from no default), whether it is a secret, a one-line meaning, the variable that may set it, the file it lives in (None for a variable-only row) and an optional bound. `read(root, relpath)` is the one open and parse of a config file: a missing file is ConfigAbsent, and an OSError, bytes that are not UTF-8, text that is not JSON (a NaN constant, a byte-order mark and a key written twice in one object included), or a top level that is not an object is ConfigUnreadable, naming a merge-conflict hunk an update left by its line through scripts/jobs/conflict_guard.py's grammar, loaded by path (when it cannot load, the parse error says the markers were not checked). `resolve(loaded, rows, where)` walks the rows in sorted path order. Precedence: a row that names a variable takes that variable when it is set and not empty, else the file's value; a row with no variable reads the file only; a variable-only row reads its variable only; an empty variable is not set. A set value of the wrong type or out of its bound is one line `<where>: <key> is <JSON type>[ <value>]; accepted: <what>` (a null shown by its type alone), a refused list of strings ending `; refused members: <each member refused on its own>` or, when only a repeat is refused, `; repeated members: <them>`, naming the environment and the variable instead when the value came from a variable, the value never shown for a secret, and a string holding an `@` anywhere, which may begin a URL user part (a credential under any key name) however the URL is spelled, shown as `<hidden: it holds an @>`. A URL bound refuses whitespace, a control character, `@`, `?`, `#`, a backslash, and a value urllib cannot split or whose port it cannot read, so a malformed URL is a refusal and never a traceback. An unset key with a default takes it and writes `[using default] <key> = <canonical JSON value>  (not set; to change it, set <key> in <where>)` to stderr once per (where, key) per process, a secret's value written `<hidden>`. Each unset required key is `[not set] <key>  (required, no default; set <key> in <where>)`; every wrong and every not-set line is written before one raise, WrongValue when any value is wrong, else NotSet carrying the sorted keys. It never ends the process: the entry point that called it returns report(ExitCode.CONFIG, ...). `env(name)` is the one literal-name read of a declared variable and refuses a name neither a row nor the config declares (declared_variables). `is_owner_token` and `is_unowned` are CONVENTIONS §12's owner grammar and its `TBD` placeholder in any letter case, shared by the default-owner row's bound, check_F and the corpus build. `VISIBILITY_ORDER` is CONVENTIONS §1's visibility vocabulary, least restrictive first, and `served_visibilities(root)` resolves `corpus.served_visibilities`, the levels every corpus reader the project serves may show, refusing a level outside that vocabulary or one written twice; `is_served(node, served)` is the one served-or-not decision every such reader makes (a node that states no level is not served); `strictest_visibility` ranks stated levels (a value outside the vocabulary outranks every member), `chain_level` is the level the corpus gives a node from its own and its README chain's stated levels (the strictest, else `internal`), and `is_served_now(node, served, stated_now)` is the decision of a reader that reads a body from disk: the stricter of the node's corpus level and the level its file states now (scripts/corpus_level.py stated_now) must be served, and a file whose level cannot be read is not; and `cut_hidden(node, shown)` drops the ids of nodes outside *shown* from a served node's links, children and parent. It registers itself under both `config_loader` and `scripts.config_loader`, and as the `config_loader` attribute of the `scripts` package that holds it, so either import name, in either order, gives one module, one announced set and one set of exception classes. Never run, stdlib-only and 3.6-safe: child_env and check_structure read through it under the hook interpreter. It reads and writes nothing else, and it caches nothing, so the same file and environment give the same values and lines.
effect: read-only
"""

# NB: stdlib only, no `from __future__ import annotations`, no f-strings, no
# walrus, no dataclass, no `list[str]` or `X | None` annotations: it sits in
# the bottom import layer, which the 3.6 hook interpreter runs
# (tests/integration/test_gate_scope.py `_bottom_import_layer`).

import copy
import datetime
import importlib
import importlib.util
import json
import ntpath
import os
import posixpath
import sys
import threading
import urllib.parse
from types import ModuleType
from typing import (
    IO,
    Any,
    Callable,
    Collection,
    Dict,
    FrozenSet,
    Iterable,
    List,
    Mapping,
    NamedTuple,
    Optional,
    Set,
    Tuple,
)

__all__ = [
    "AUDIT_SEVERITIES",
    "CONFIG_FILE",
    "ENV_TYPES",
    "KEYS",
    "NONE",
    "OWNER_GRAMMAR",
    "PRACTICES_FILE",
    "PROJECT_READS",
    "TYPES",
    "VARIABLE_SOURCES",
    "VISIBILITY_ORDER",
    "ConfigAbsent",
    "ConfigError",
    "ConfigUnreadable",
    "Key",
    "NotSet",
    "WrongValue",
    "chain_level",
    "cut_hidden",
    "declared_variables",
    "env",
    "is_advisory_id",
    "is_null_spelling",
    "is_served",
    "is_served_now",
    "is_owner_token",
    "is_unowned",
    "read",
    "resolve",
    "rows",
    "served_visibilities",
    "strictest_visibility",
]

CONFIG_FILE = os.path.join("config", "project.json")
PRACTICES_FILE = os.path.join("config", "practices.json")
# The fixed project files this module reads, as root-relative literals for
# scripts/jobs/conflict_guard.py, which collects the name by syntax tree: a
# copier job whose imports reach here refuses, naming the file, when an update
# leaves one conflicted.
PROJECT_READS = ("config/project.json", "config/practices.json")
# The merge-conflict grammar, loaded by path only when a file does not parse:
# importing it would put scripts/jobs on every caller's import path.
_GRAMMAR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "jobs", "conflict_guard.py"
)
_FINISH_DOC = "docs/guides/generate-and-upgrade.md, 'Finish an update that stopped'"
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HIDDEN = "<hidden>"
_ENVIRONMENT = "the environment"
_DEFAULT_LINE = "[using default] %s = %s  (not set; to change it, set %s in %s)\n"
_NOT_SET_LINE = "[not set] %s  (required, no default; set %s in %s)"
# (where, path) for each default announced in this process: the line is a
# start-up fact, and a process that resolves a key twice has one fact to tell.
_ANNOUNCED: Set[Tuple[str, Tuple[str, ...]]] = set()


class _NoDefault(object):
    """The marker for a key with no default, distinct from a default of None
    (JSON null), which is a value a key may legitimately default to."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "NONE"


NONE = _NoDefault()


class ConfigError(Exception):
    """A configured value cannot be used. `path` is the config file it names
    (None for a variable) and `lines` the one-line messages, already written
    to the stream when resolve raised it. Not a RuntimeError, so a caller that
    skips an absent backend on RuntimeError cannot skip broken config."""

    def __init__(self, path: Optional[str], lines: List[str]) -> None:
        super(ConfigError, self).__init__("; ".join(lines))
        self.path = path
        self.lines = list(lines)


class ConfigAbsent(ConfigError):
    """The config file does not exist."""


class ConfigUnreadable(ConfigError):
    """The config file exists and cannot be used: unreadable, not UTF-8, not
    JSON, a key twice in one object, or a top level that is not an object.
    `conflict_line` is the first merge-conflict hunk's line, or None;
    `unchecked` is why the markers were not checked, or None."""

    def __init__(
        self,
        path: str,
        lines: List[str],
        conflict_line: Optional[int] = None,
        unchecked: Optional[str] = None,
    ) -> None:
        super(ConfigUnreadable, self).__init__(path, lines)
        self.conflict_line = conflict_line
        self.unchecked = unchecked


class WrongValue(ConfigError):
    """A set key holds a value its row does not accept."""


class NotSet(ConfigError):
    """Required keys are unset; `keys` are their paths, sorted."""

    def __init__(
        self, path: Optional[str], lines: List[str], keys: List[Tuple[str, ...]]
    ) -> None:
        super(NotSet, self).__init__(path, lines)
        self.keys = list(keys)


_KeyFields = NamedTuple(
    "_KeyFields",
    [
        ("path", Tuple[str, ...]),
        ("type", str),
        ("default", object),
        ("secret", bool),
        ("meaning", str),
        ("env", Optional[str]),
        ("file", Optional[str]),
        # (predicate, what it accepts), for a bound the type alone cannot say.
        ("accepts", Optional[Tuple[Callable[[Any], bool], str]]),
    ],
)


class Key(_KeyFields):
    """One declared key: path, type, default (NONE for none), secret, meaning,
    the variable that may set it, its file (None for a variable-only row), and
    an optional (predicate, text) bound."""

    __slots__ = ()

    @property
    def required(self) -> bool:
        """True when the key has no default, so an unset key is refused."""
        return self.default is NONE


def _is_str(value: object) -> bool:
    return isinstance(value, str)


def _is_nonempty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_int(value: object) -> bool:
    # bool is an int to isinstance; a count of `true` is a typo, not 1.
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_bool(value: object) -> bool:
    return isinstance(value, bool)


def _is_list_of_str(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def _is_object(value: object) -> bool:
    return isinstance(value, dict)


def _is_repo_path(value: object) -> bool:
    # Both spellings of absolute, so a Windows `C:/x` or `\\x` written on one
    # host cannot escape the project on another.
    if not _is_nonempty_str(value):
        return False
    text = str(value)
    if posixpath.isabs(text) or ntpath.isabs(text) or ntpath.splitdrive(text)[0]:
        return False
    return ".." not in text.replace("\\", "/").split("/")


_BASE_TYPES = (
    ("str", _is_str, "a string"),
    ("nonempty_str", _is_nonempty_str, "a non-empty string"),
    ("int", _is_int, "an integer"),
    ("number", _is_number, "a number"),
    ("bool", _is_bool, "true or false"),
    ("list_of_str", _is_list_of_str, "a list of strings"),
    ("object", _is_object, "an object"),
    (
        "repo_path",
        _is_repo_path,
        "a non-empty repo-relative path, not absolute and with no `..` part",
    ),
)
_NULLABLE = "_or_null"


def _or_null(check: Callable[[object], bool]) -> Callable[[object], bool]:
    def nullable(value: object) -> bool:
        return value is None or check(value)

    return nullable


def _types() -> Dict[str, Tuple[Callable[[object], bool], str]]:
    out: Dict[str, Tuple[Callable[[object], bool], str]] = {}
    for name, check, text in _BASE_TYPES:
        out[name] = (check, text)
        out[name + _NULLABLE] = (_or_null(check), text + ", or null")
    return out


# The closed set of row types: name -> (check, what it accepts). Each base type
# has a `_or_null` twin, so null is a value only where a row says so.
TYPES = _types()
# A variable's value is a string, so a row a variable may set has a string type.
ENV_TYPES = frozenset(
    name
    for name in TYPES
    if name.replace(_NULLABLE, "") in ("str", "nonempty_str", "repo_path")
)


def _row(
    path: Tuple[str, ...],
    type_: str,
    default: object,
    meaning: str,
    secret: bool = False,
    env: Optional[str] = None,
    file: Optional[str] = CONFIG_FILE,
    accepts: Optional[Tuple[Callable[[Any], bool], str]] = None,
) -> Key:
    return Key(path, type_, default, secret, meaning, env, file, accepts)


def _in_unit_interval(value: Any) -> bool:
    return bool(0 < value <= 1)


def _not_negative(value: Any) -> bool:
    return bool(value >= 0)


def _at_least_one(value: Any) -> bool:
    return bool(value >= 1)


# A week. The slowest full `make verify` measured 3 h 12 min, so a longer
# limit is a mistyped value, not a slow suite; and it keeps the deadline inside
# what time.sleep, select and threading take (10**400 raised OverflowError).
_GATE_TIMEOUT_MAX = 604800
# An hour. The grace only has to outlast a test's own stop of a server it
# started (e2e.server.stop_timeout_s), and a cleanup that needs longer is a
# hang; the same overflow applies.
_GATE_GRACE_MAX = 3600


def _gate_timeout(value: Any) -> bool:
    return bool(1 <= value <= _GATE_TIMEOUT_MAX)


def _gate_grace(value: Any) -> bool:
    return bool(1 <= value <= _GATE_GRACE_MAX)


def _null_or_at_least_one(value: Any) -> bool:
    return value is None or bool(value >= 1)


def _port(value: Any) -> bool:
    return bool(1 <= value <= 65535)


# The most seconds a seconds key may hold: past it a thread wait on the value
# raises OverflowError mid-run instead of refusing it here.
_MOST_SECONDS = threading.TIMEOUT_MAX
_MOST_SECONDS_TEXT = "threading.TIMEOUT_MAX (%d on this platform)" % _MOST_SECONDS


def _at_least_one_second(value: Any) -> bool:
    return bool(1 <= value <= _MOST_SECONDS)


# The most bytes a byte cap may hold: the longest a Python bytes object, and
# so a kept stream, can be. scripts/resource_limits.py run_bounded refuses a
# cap past it too; a refusal here names the key before a child starts.
_MOST_BYTES = sys.maxsize
_MOST_BYTES_TEXT = "sys.maxsize (%d on this platform)" % _MOST_BYTES


def _one_to_most_bytes(value: Any) -> bool:
    return bool(1 <= value <= _MOST_BYTES)


def _zero_to_most_seconds(value: Any) -> bool:
    return bool(0 <= value <= _MOST_SECONDS)


def _seconds_by_adapter(value: Any) -> bool:
    # Empty is refused: every adapter that calls out would then be refused at
    # its first call, a pass over zero entries reported as a valid table. A
    # bool is an int to isinstance, and `true` seconds is a typo, not a limit;
    # `0 < s <= most` also refuses NaN.
    return bool(value) and all(
        isinstance(name, str)
        and name.strip()
        and isinstance(seconds, (int, float))
        and not isinstance(seconds, bool)
        and 0 < seconds <= _MOST_SECONDS
        for name, seconds in value.items()
    )


def _no_parent_part(value: Any) -> bool:
    # Absolute is allowed (a farm job's local disk); `..` never is, so a
    # relative value cannot climb out of the checkout it resolves against.
    return ".." not in str(value).replace("\\", "/").split("/")


# CONVENTIONS §12's owner token: one word of letters, digits and `._@-`.
OWNER_GRAMMAR = "[A-Za-z0-9._@-]+"
_OWNER_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._@-"
)
# The placeholder that counts as unowned, so it cannot be the owner it stands in for.
_UNOWNED = "TBD"


def is_owner_token(value: Any) -> bool:
    """True when *value*, as text, is one token of CONVENTIONS §12's owner
    grammar OWNER_GRAMMAR; the placeholder `TBD` is a token too."""
    text = str(value)
    return bool(text) and set(text) <= _OWNER_CHARS


def is_unowned(value: Any) -> bool:
    """True when *value* is the `TBD` placeholder, in any letter case."""
    return str(value).upper() == _UNOWNED


# How YAML writes null, as a line parser keeps it: `null` (any letter case
# here, as for `TBD`, because no owner is called nUlL), `~`, or nothing.
_NULL_SPELLINGS = frozenset(("", "~", "NULL"))


def is_null_spelling(value: Any) -> bool:
    """True when *value* is None or a way YAML writes null: empty, `~`, or
    `null` in any letter case. Such a value names no owner."""
    return value is None or str(value).upper() in _NULL_SPELLINGS


def _owner_token(value: Any) -> bool:
    # A nullable row hands its bound None too; null is "no default owner".
    if value is None:
        return True
    return (
        is_owner_token(value) and not is_unowned(value) and not is_null_spelling(value)
    )


# CONVENTIONS §1's visibility vocabulary, least restrictive first. It lives
# here because the served-levels row's bound needs it and this module imports
# nothing of the project; scripts/check_structure.py keeps a copy that
# tests/unit/scripts/test_config_loader.py holds equal to this one.
VISIBILITY_ORDER = ("public", "internal", "confidential", "restricted")


def _visibility_members(value: Any) -> bool:
    # Each once: a repeated level is a typo, never a stronger allow.
    return all(v in VISIBILITY_ORDER for v in value) and len(set(value)) == len(value)


_ASCII_DIGITS = "0123456789"
_ISO_DATE = "%Y-%m-%d"


def _iso_date(value: Any) -> bool:
    # strptime takes "2027-1-31"; the round trip holds the value to the one
    # spelling a reader compares, and refuses a day the calendar lacks.
    try:
        parsed = datetime.datetime.strptime(str(value), _ISO_DATE).date()
    except ValueError:
        return False
    return bool(parsed.isoformat() == value)


def _dotted_release(value: Any) -> bool:
    # The grammar setup-python takes for a release: two or three whole numbers.
    # Not str.isdigit, which also accepts `²` and fullwidth digits.
    parts = str(value).split(".")
    return len(parts) in (2, 3) and all(p and not p.strip(_ASCII_DIGITS) for p in parts)


def _pinned_images(value: Any) -> bool:
    # `-latest` is the suffix GitHub gives every label that moves to a new
    # image without an edit here, so a list naming one pins nothing. Judged
    # stripped, so surrounding whitespace cannot hide the suffix.
    return bool(value) and all(
        v.strip() and not v.strip().endswith("-latest") for v in value
    )


def _patterns(value: Any) -> bool:
    # An empty list would judge no file, which reads as a pass over nothing.
    return bool(value) and all(v.strip() for v in value)


def _scanner_exit_code(value: Any) -> bool:
    # 0 is a clean scan, 1 the scanner's own error and 2 a usage error, so a
    # finding must exit with none of them; 126 and up are the shell's and a
    # signal's.
    return bool(3 <= value <= 125)


def _log_options(value: Any) -> bool:
    # The scanner splits its git log options on single spaces, so an option
    # holding whitespace would reach git as two words.
    return bool(value) and all(v and v.split() == [v] for v in value)


def _extra_names(value: Any) -> bool:
    # A pyproject extra is one word, and a gate that installs no extra judges
    # only the core dependencies, which is a narrower gate than any project has.
    return bool(value) and all(_is_nonempty_str(v) and v.split() == [v] for v in value)


def _extra_map(value: Any) -> bool:
    # transport -> the one pyproject extra that installs its packages.
    return all(
        _is_nonempty_str(k) and _is_nonempty_str(v) and v.split() == [v]
        for k, v in value.items()
    )


def _basenames(value: Any) -> bool:
    return bool(value) and all(
        v.strip() == v and v and "/" not in v and "\\" not in v for v in value
    )


def _user_path(value: Any) -> bool:
    # Absolute or under `~`, so the place does not move with the directory a
    # command runs from; `..` never, so the value says where it lands.
    text = str(value)
    return text.startswith(("/", "~/")) and _no_parent_part(text)


def _one_path_part(value: Any) -> bool:
    # The installer joins the value into `<root>/<name>/<rev>/<name>`, so it
    # must name one directory entry: a separator, an absolute value or a
    # leading `.` (`.`, `..`, a hidden name) would move the program elsewhere.
    # No separator also means not absolute, POSIX or Windows.
    text = str(value)
    return (
        bool(text)
        and text.strip() == text
        and not text.startswith(".")
        and not any(c in text for c in "/\\\0")
    )


_ONE_PATH_PART = (
    _one_path_part,
    "one path part: no `/`, `\\` or NUL, not absolute, no leading `.` or "
    "surrounding whitespace",
)

_HEX = "0123456789abcdef"


# Characters a bare URL never needs and a credential or a second parse rides
# in: `@` anywhere (urllib finds no user part in `https:/u:tok@h`, a WHATWG
# parser does), `?` and `#` even with nothing after them, and `\`, which a
# WHATWG parser reads as `/`.
_URL_REFUSED = "@?#\\"


def _bare_url(value: Any) -> Optional[urllib.parse.SplitResult]:
    """*value* split as a URL, or None when it holds whitespace, a control
    character or a `_URL_REFUSED` character, or urllib cannot split it, or
    its port is not one from 1 to 65535."""
    text = str(value)
    if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in text):
        return None
    if any(c in _URL_REFUSED for c in text):
        return None
    try:
        parts = urllib.parse.urlsplit(text)
        # .port raises on a port that is not a number from 0 to 65535, and 0
        # names no port a server listens on.
        if parts.port == 0:
            return None
    except ValueError:
        return None
    return parts


def _release_url(value: Any) -> bool:
    # https, or file for a directory a host already holds; never a user part,
    # query or fragment, so the URL a mirror is given carries no credential and
    # a file name joins it as one more path part.
    parts = _bare_url(value)
    if parts is None:
        return False
    if parts.scheme == "https":
        return bool(parts.hostname)
    return parts.scheme == "file" and not parts.netloc and parts.path.startswith("/")


def _mirror_url(value: Any) -> bool:
    # https with a host, and nothing a credential could ride in, because the
    # Makefile hands the value to npm and pip as one shell word.
    parts = _bare_url(value)
    return parts is not None and parts.scheme == "https" and bool(parts.hostname)


def _null_or_mirror_url(value: Any) -> bool:
    # A bound is judged on null too, and null is the row's "the tool's own".
    return value is None or _mirror_url(value)


_MIRROR_URL = (
    _null_or_mirror_url,
    "an https URL with a host, a valid port if any, and no `@`, `?`, `#`, "
    "backslash, whitespace or control character",
)


def _release_assets(value: Any) -> bool:
    # {platform: {file, sha256}}: at least one, because a table that pins no
    # platform installs nothing on any; a bare .tar.gz name, because the
    # installer joins it to the URL and reads it as one; a full lowercase
    # sha256, the form a vendor's checksums file prints.
    if not value:
        return False
    for key, asset in value.items():
        if not _is_nonempty_str(key) or key != key.lower() or "-" not in key:
            return False
        if not isinstance(asset, dict) or sorted(asset) != ["file", "sha256"]:
            return False
        name, digest = asset["file"], asset["sha256"]
        if not _is_nonempty_str(name) or not name.endswith(".tar.gz"):
            return False
        if "/" in name or "\\" in name or name.startswith("."):
            return False
        if not isinstance(digest, str) or len(digest) != 64 or digest.strip(_HEX):
            return False
    return True


_GLOB_CHARS = "*?["


def _exclusions(value: Any) -> bool:
    # {exact repo-relative path: {rule id: reason}}: a glob or a blank reason
    # would excuse findings nobody named, and a path in any spelling but the
    # scanner's own (POSIX, normalised) could never match one, so it is refused
    # here, where the message names the key.
    for path, rules in value.items():
        if not _is_repo_path(path) or any(c in path for c in _GLOB_CHARS):
            return False
        if "\\" in path or posixpath.normpath(path) != path:
            return False
        if not isinstance(rules, dict) or not rules:
            return False
        for rule, reason in rules.items():
            if not rule.strip() or not _is_nonempty_str(reason):
                return False
    return True


def _suffixes(value: Any) -> bool:
    # A suffix is matched against the end of a file name, so one without its
    # dot (`sh`) would also judge `fresh`, and a `/` would make it a path.
    return bool(value) and all(
        len(v) > 1 and v.startswith(".") and v.split() == [v] and "/" not in v
        for v in value
    )


def _program_names(value: Any) -> bool:
    # Matched against a shebang interpreter's basename, so a path can never
    # match one, and an empty list would make the shebang rule judge nothing.
    return bool(value) and all(
        v and v.split() == [v] and "/" not in v and "\\" not in v for v in value
    )


def _is_reason_map(value: Any) -> bool:
    # At least one entry: an empty policy protects nothing, and a guard over
    # zero items is a vacuous pass, not a pass.
    return _is_any_reason_map(value) and bool(value)


def _is_any_reason_map(value: Any) -> bool:
    # Empty allowed: for a map that only lifts protection, empty is the
    # strictest setting, so the at-least-one bound of a deny map would force
    # a carve-out to exist.
    return isinstance(value, dict) and all(_is_nonempty_str(v) for v in value.values())


def _bare_names(value: Any) -> bool:
    # A bare file name or a glob over one: a `/` would make it a path, and `.`
    # or `..` name a directory, never a file a rule can protect or carve out.
    return all(
        _is_nonempty_str(k) and "/" not in k and k not in (".", "..") for k in value
    )


def _reasoned_names(value: Any) -> bool:
    return _is_reason_map(value) and _bare_names(value)


def _carved_out_names(value: Any) -> bool:
    return _is_any_reason_map(value) and _bare_names(value)


def _relative_posix_keys(value: Any) -> bool:
    # Relative POSIX parts only, each a real name: a leading or trailing `/`,
    # an empty, `.` or `..` part would make two spellings of one entry, or one
    # that climbs out of the root it is judged against.
    return all(
        _is_nonempty_str(k)
        and all(part not in ("", ".", "..") for part in k.split("/"))
        for k in value
    )


def _reasoned_paths(value: Any) -> bool:
    return _is_reason_map(value) and _relative_posix_keys(value)


def _any_reasoned_paths(value: Any) -> bool:
    # Empty allowed: an exclusion list only lifts judgement, so empty is the
    # strictest setting.
    return _is_any_reason_map(value) and _relative_posix_keys(value)


_REASONED_NAMES = (
    _reasoned_names,
    "at least one entry, each a bare file name or a glob over one (no `/`, "
    "not `.` or `..`) mapped to a non-blank reason",
)
_CARVED_OUT_NAMES = (
    _carved_out_names,
    "an object, empty for no carve-out, each key a bare file name or a glob "
    "over one (no `/`, not `.` or `..`) mapped to a non-blank reason",
)
_REASONED_PATHS = (
    _reasoned_paths,
    "at least one entry, each a relative POSIX path (no leading or trailing "
    "`/`, no empty, `.` or `..` part) mapped to a non-blank reason",
)
_ANY_REASONED_PATHS = (
    _any_reasoned_paths,
    "an object, empty for none, each key a relative POSIX path (no leading or "
    "trailing `/`, no empty, `.` or `..` part) mapped to a non-blank reason",
)

# The severities a dependency audit reports, weakest first: the order is what
# `dependency_audit.fail_at` compares against.
AUDIT_SEVERITIES = ("info", "low", "moderate", "high", "critical")
_ADVISORY_PREFIX = "GHSA"
_ADVISORY_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789"
_ACCEPTED_FIELDS = ("package", "reason", "review_by")


def is_advisory_id(value: Any) -> bool:
    """True for a GitHub advisory id as an audit report spells it:
    `GHSA-xxxx-xxxx-xxxx`, each group four lower-case letters or digits."""
    if not isinstance(value, str):
        return False
    parts = value.split("-")
    return (
        len(parts) == 4
        and parts[0] == _ADVISORY_PREFIX
        and all(len(p) == 4 and not p.strip(_ADVISORY_CHARS) for p in parts[1:])
    )


def _is_severity(value: Any) -> bool:
    return value in AUDIT_SEVERITIES


def _accepted_row(row: Any) -> bool:
    # Exactly the three fields: a misspelt `reviewby` would otherwise leave a
    # row with no date, accepted for ever.
    return (
        isinstance(row, dict)
        and sorted(row) == sorted(_ACCEPTED_FIELDS)
        and _is_nonempty_str(row["package"])
        and row["package"].split() == [row["package"]]
        and _is_nonempty_str(row["reason"])
        and _iso_date(row["review_by"])
    )


def _accepted_risks(value: Any) -> bool:
    # Empty allowed: an acceptance only lifts a failure, so none is the
    # strictest setting. An app with no advisory under it is a typo'd
    # leftover, refused rather than read as nothing accepted.
    return isinstance(value, dict) and all(
        _one_path_part(app)
        and isinstance(advisories, dict)
        and bool(advisories)
        and all(
            is_advisory_id(advisory) and _accepted_row(row)
            for advisory, row in advisories.items()
        )
        for app, advisories in value.items()
    )


_ACCEPTED_RISKS = (
    _accepted_risks,
    "an object, empty for none, each key a frontend app's directory name (one "
    "path part) mapped to at least one advisory id written GHSA-xxxx-xxxx-xxxx, "
    'each mapped to exactly {"package": <npm package name, no whitespace>, '
    '"reason": <non-blank>, "review_by": <a calendar date written YYYY-MM-DD>}',
)


# The one table of declared keys, sorted by path. A block a typed validator
# owns (child_env, evidence) is one `object` row, and the validator stays the
# typed view over the value resolved here; an open-keyed map is one row, never
# a row per name.
KEYS = tuple(
    sorted(
        (
            _row(
                ("ANTHROPIC_API_KEY",),
                "nonempty_str_or_null",
                None,
                "the claude-code-headless adapter's API key; set it in the "
                "environment or a git-ignored .env, never a committed file",
                secret=True,
                env="ANTHROPIC_API_KEY",
                file=None,
            ),
            _row(
                ("CLAUDE_CONFIG_DIR",),
                "nonempty_str_or_null",
                None,
                "the claude-code-headless adapter's configuration directory; "
                "secret because models.credential_env lists it, and every name "
                "there is judged a credential",
                secret=True,
                env="CLAUDE_CONFIG_DIR",
                file=None,
            ),
            _row(
                ("KEEL_MCP_MODEL",),
                "nonempty_str_or_null",
                None,
                "the model the MCP Q&A server asks; null: the registry default",
                env="KEEL_MCP_MODEL",
                file=None,
            ),
            _row(
                ("OPENAI_API_KEY",),
                "nonempty_str_or_null",
                None,
                "the openai-compatible adapter's API key; set it in the "
                "environment or a git-ignored .env, never a committed file",
                secret=True,
                env="OPENAI_API_KEY",
                file=None,
            ),
            _row(
                ("accountability", "default_owner"),
                "nonempty_str_or_null",
                None,
                "the owner a kind: tool or agent document whose frontmatter "
                "owner is TBD inherits in scripts/check_structure.py check_F; "
                "null: no default, so each such document is an error",
                accepts=(
                    _owner_token,
                    "one owner token of letters, digits and `._@-`, never TBD or the "
                    "word null in any case",
                ),
            ),
            _row(
                ("agents", "editable_names"),
                "object",
                NONE,
                "each file name or glob scripts/apply_refactor.py lets an agent "
                "edit inside a protected path, mapped to the reason; empty: no "
                "carve-out",
                accepts=_CARVED_OUT_NAMES,
            ),
            _row(
                ("agents", "max_model_calls"),
                "int",
                0,
                "the approved cap on the model calls one agent --execute run, "
                "or one MCP question, may make; 0 approves none",
                accepts=(_not_negative, "a value >= 0"),
            ),
            _row(
                ("agents", "max_session_model_calls"),
                "int",
                0,
                "the approved cap on the model calls one MCP Q&A server process "
                "may make across all its questions, from start to exit; 0 "
                "approves none, since a total keel chose would be a spend no "
                "owner approved",
                accepts=(_not_negative, "a value >= 0"),
            ),
            _row(
                ("agents", "protected_names"),
                "object",
                NONE,
                "each file name or glob scripts/apply_refactor.py refuses an "
                "agent edit to in any directory, mapped to the reason",
                accepts=_REASONED_NAMES,
            ),
            _row(
                ("agents", "protected_paths"),
                "object",
                NONE,
                "each repo-relative path scripts/apply_refactor.py refuses an "
                "agent edit to, itself and everything under it, mapped to the "
                "reason",
                accepts=_REASONED_PATHS,
            ),
            # 64 MiB: the largest output a tool child writes is a gate run's
            # whole make output (scripts/run_make_target.py --json carries it),
            # far under this; both streams together stay a small share of
            # transports.serve.memory_cap_mb (4096).
            _row(
                ("agents", "tool_max_output_bytes"),
                "int",
                67108864,
                "the bytes an agent's tool child, or the MCP action server's "
                "doer, may write to stdout or to stderr before its session is "
                "ended and the call refused",
                accepts=(
                    _one_to_most_bytes,
                    "a value >= 1 and <= %s" % _MOST_BYTES_TEXT,
                ),
            ),
            # 60 s: a margin for the tool child's start, the gated apply's
            # plan_edits and writes before the gate and its rollback after a
            # red one (scripts/apply_refactor.py, run by an agent's _run), and
            # the gate runner's start and its two tree snapshots. Measured: the
            # start and both snapshots took about 0.3 s on a small tree, and
            # two snapshots of a 200,000-file tree on local disk about 7 s;
            # 60 s keeps the large-tree case well inside it.
            _row(
                ("agents", "tool_gate_margin_seconds"),
                "int",
                60,
                "the seconds agents.tool_timeout_seconds must leave, over "
                "make_targets.gate_timeout_seconds plus twice "
                "make_targets.gate_stop_grace_seconds, for the tool child's "
                "start, the gated apply's plan_edits, writes and rollback, and "
                "the gate runner's start and its two tree snapshots",
                accepts=(
                    _at_least_one_second,
                    "a value >= 1 and <= %s less make_targets.gate_timeout_seconds "
                    "and twice make_targets.gate_stop_grace_seconds of the "
                    "same tree (that sum checked by scripts/resource_limits.py "
                    "tool_limits)" % _MOST_SECONDS_TEXT,
                ),
            ),
            # 15000 s: a tool child that runs a gate must outlast the gate
            # runner's timed-out run, its limit and its grace spent twice
            # (make_targets, 14400 + 2 * 15 s), plus the margin above. Ended
            # sooner, the runner's watcher sends make's session SIGKILL at
            # once: make's SIGTERM grace is cut short, the runner's structured
            # result is lost, and apply_refactor's edit is not rolled back.
            _row(
                ("agents", "tool_timeout_seconds"),
                "int",
                15000,
                "the seconds an agent's tool child, or the MCP action server's "
                "doer, may run before its session is ended and the call "
                "refused; it must be at least make_targets.gate_timeout_seconds "
                "plus twice make_targets.gate_stop_grace_seconds plus "
                "agents.tool_gate_margin_seconds",
                accepts=(
                    _at_least_one_second,
                    "a value >= 1 and <= %s" % _MOST_SECONDS_TEXT,
                ),
            ),
            _row(
                ("canary", "answer_sets"),
                "object",
                {
                    "default": {},
                    "skeleton": {
                        "frontend_stack": "none",
                        "showcase": False,
                        "transports": ["grpc"],
                    },
                },
                "the copier answer sets the canary renders, each name mapped "
                "to its answers over copier.yml's defaults",
            ),
            _row(
                ("canary", "scratch_root"),
                "nonempty_str",
                ".canary",
                "where the canary renders its projects: relative to the "
                "checkout, git-ignored, or an absolute path off the system "
                "temporary directory",
                env="KEEL_CANARY_SCRATCH",
                accepts=(_no_parent_part, "a path with no `..` part"),
            ),
            _row(
                ("canary", "step_timeout_minutes"),
                "int",
                90,
                "the minutes one canary step may run before it is killed and failed",
                accepts=(_at_least_one, "a value >= 1"),
            ),
            _row(
                ("canary", "workers"),
                "int",
                1,
                "how many canary projects render and verify at once",
                accepts=(_at_least_one, "a value >= 1"),
            ),
            _row(
                ("child_env",),
                "object",
                NONE,
                "the child-process allowlist scripts/child_env.py validates",
            ),
            _row(
                ("child_env", "login_name_schemes"),
                "list_of_str",
                [],
                "URL schemes whose password-less user part is a login name; "
                "empty: every user part counts as a credential",
            ),
            _row(
                ("corpus", "served_visibilities"),
                "list_of_str",
                ["public", "internal"],
                "the visibility levels a reader the project serves may show a "
                "corpus node at: the showcase API, its llms text, the static "
                "export, the wiki navigator, the practice refactor agent and "
                "scripts/query_corpus.py; a node at any other level is absent "
                "from them",
                accepts=(
                    _visibility_members,
                    "members of %s, each once" % ", ".join(VISIBILITY_ORDER),
                ),
            ),
            _row(
                ("config_reads", "allowed"),
                "object",
                NONE,
                "each file that still reads a config file or a declared "
                "variable directly, mapped to the reason",
            ),
            _row(
                ("config_reads", "roots"),
                "list_of_str",
                NONE,
                "the code roots the config-reads gate test walks",
            ),
            _row(
                ("doc_drift", "gate_target"),
                "nonempty_str",
                NONE,
                "the make target whose scripts the exit-code table lists",
            ),
            _row(
                ("doc_drift", "limits_guide"),
                "repo_path",
                NONE,
                "the guide that holds the generated exit-code table",
            ),
            _row(
                ("evals", "case_schema"),
                "repo_path",
                NONE,
                "the JSON schema every eval case follows",
            ),
            _row(
                ("evals", "dataset_dir"),
                "repo_path",
                NONE,
                "the directory of eval datasets",
            ),
            _row(
                ("evals", "live", "max_calls"),
                "int",
                NONE,
                "the approved cap on live model calls; 0 approves none",
                accepts=(_not_negative, "a value >= 0"),
            ),
            _row(
                ("evals", "live", "model"),
                "nonempty_str_or_null",
                NONE,
                "the model a live eval calls; null refuses make eval-live",
            ),
            _row(
                ("evals", "live", "model_options"),
                "object",
                NONE,
                "options handed to the live model adapter",
            ),
            _row(
                ("evals", "report_dir"),
                "repo_path",
                NONE,
                "where an eval run writes its report",
            ),
            _row(
                ("evals", "report_schema"),
                "repo_path",
                NONE,
                "the JSON schema an eval report follows",
            ),
            _row(
                ("dependency_audit", "accepted"),
                "object",
                {},
                "each frontend app's accepted dependency advisories, each with "
                "the package, the reason and the day it must be reviewed by; "
                "scripts/audit_dependencies.py fails a row past that day or one "
                "whose advisory the audit no longer reports",
                accepts=_ACCEPTED_RISKS,
            ),
            _row(
                ("dependency_audit", "fail_at"),
                "nonempty_str",
                "high",
                "the weakest severity scripts/audit_dependencies.py fails when "
                "no accepted row covers the finding; a weaker one is listed",
                accepts=(_is_severity, "one of " + ", ".join(AUDIT_SEVERITIES)),
            ),
            _row(
                ("dependency_audit", "max_review_days"),
                "int",
                90,
                "the most days after the run's date an accepted row's review_by "
                "may be; scripts/audit_dependencies.py fails a row set further "
                "out, so an acceptance is renewed, not parked",
                accepts=(_at_least_one, "a value >= 1"),
            ),
            _row(
                ("dependency_audit", "max_shown_chars"),
                "int",
                500,
                "the most characters of npm's diagnostic one "
                "scripts/audit_dependencies.py line shows; a longer one is cut "
                "before it is redacted, and the cut is marked",
                accepts=(_at_least_one, "a value >= 1"),
            ),
            _row(
                ("dependency_audit", "timeout_seconds"),
                "int",
                120,
                "the seconds one app's `npm audit --json` may run before "
                "scripts/audit_dependencies.py ends it",
                accepts=(_at_least_one_second, "1 <= value <= " + _MOST_SECONDS_TEXT),
            ),
            _row(
                ("evals", "threshold"),
                "number",
                NONE,
                "the pass fraction a suite needs",
                accepts=(_in_unit_interval, "0 < value <= 1"),
            ),
            _row(
                ("expiring_tier", "baseline"),
                "repo_path",
                NONE,
                "the file of a generated project's recorded findings, each of "
                "which warns until expiring_tier.expires; scripts/"
                "record_gate_baseline.py writes it",
            ),
            _row(
                ("expiring_tier", "expires"),
                "nonempty_str",
                NONE,
                "the day a generated project's recorded findings turn red, no "
                "later than scripts/expiring_tier_data.py CEILING",
                accepts=(_iso_date, "a calendar date written YYYY-MM-DD"),
            ),
            _row(
                ("install_sources", "browser_download_host"),
                "nonempty_str_or_null",
                None,
                "the host `make fe-browsers` downloads the journey's browser "
                "from, as PLAYWRIGHT_DOWNLOAD_HOST; null: the runner's own",
                accepts=_MIRROR_URL,
            ),
            _row(
                ("install_sources", "npm_registry"),
                "nonempty_str_or_null",
                None,
                "the registry `make fe-install` passes npm as --registry; "
                "null: npm's own configuration",
                accepts=_MIRROR_URL,
            ),
            _row(
                ("install_sources", "python_index"),
                "nonempty_str_or_null",
                None,
                "the package index CI's pip install and check-venv's fix "
                "command pass pip as --index-url; null: pip's own configuration",
                accepts=_MIRROR_URL,
            ),
            _row(
                ("evidence",),
                "object",
                NONE,
                "where make verify writes its evidence record",
            ),
            _row(
                ("evidence", "dir"),
                "repo_path",
                NONE,
                "the git-ignored directory of gate evidence records",
            ),
            _row(
                ("evidence", "run_date"),
                "object_or_null",
                None,
                "the one-date channel of a gate run; null: off, every check "
                "reads the clock",
            ),
            _row(
                ("evidence", "schema"),
                "repo_path",
                NONE,
                "the JSON schema a gate evidence record follows",
            ),
            # 4 h: a full `make verify` took 3 h 12 min (11 520 s) on the
            # slowest host keel runs on (2026-10); 4 h leaves a quarter more,
            # so a slow run that is progressing is not ended as a hang.
            _row(
                ("make_targets", "gate_timeout_seconds"),
                "int",
                14400,
                "the seconds scripts/run_make_target.py lets make run before it "
                "ends make's session, every process in it whatever its group "
                "(one that left the session with setsid is not signalled); its "
                "--timeout overrides it",
                accepts=(_gate_timeout, "a value from 1 to %d" % _GATE_TIMEOUT_MAX),
            ),
            # 15 s: on SIGTERM a test's handler stops the uvicorn server it
            # started, outside make's session, with SIGTERM and then SIGKILL
            # after e2e.server.stop_timeout_s (10 s); this grace must outlast
            # that, or the runner's SIGKILL ends pytest first and the server is
            # left running (tests/unit/scripts/test_run_make_target.py holds the
            # two apart). SIGTERM's default action ends pytest, copier and make
            # at once, so only a handler that cleans up uses the grace.
            _row(
                ("make_targets", "gate_stop_grace_seconds"),
                "int",
                15,
                "the seconds scripts/run_make_target.py waits after SIGTERM for "
                "make's session to exit before it sends SIGKILL",
                accepts=(_gate_grace, "a value from 1 to %d" % _GATE_GRACE_MAX),
            ),
            _row(
                ("models", "max_reply_bytes"),
                "int",
                8388608,
                "the bytes one model reply may hold, an HTTP body or a model "
                "child's output stream, before the adapter refuses it unread",
                accepts=(_at_least_one, "a value >= 1"),
            ),
            _row(
                ("models", "timeout_seconds"),
                "object",
                {"claude-code-headless": 600, "openai-compatible": 60},
                "the seconds one call of each model adapter may take, counted "
                "from the call's start, before it is ended and refused, each "
                "adapter name mapped to its limit; an adapter that calls out and "
                "is absent here is refused",
                accepts=(
                    _seconds_by_adapter,
                    "at least one entry, each an adapter name mapped to a number "
                    "of seconds > 0 and <= %s" % _MOST_SECONDS_TEXT,
                ),
            ),
            _row(
                ("practices", "profiles"),
                "object",
                {},
                "which domain practice profiles are on; empty: none",
            ),
            _row(
                ("runtimes", "max_steps"),
                "int",
                10000,
                "the steps one in-process runtime run may take before it is "
                "refused as a plan that never reaches its end",
                accepts=(_at_least_one, "a value >= 1"),
            ),
            _row(
                ("secrets", "dotenv_files"),
                "list_of_str",
                [".env", ".env.*"],
                "the basename patterns of the KEY=VALUE files the committed-"
                "secrets gate judges",
                accepts=(_patterns, "a non-empty list with no blank pattern"),
            ),
            _row(
                ("secrets", "json_files"),
                "list_of_str",
                ["*.json"],
                "the basename patterns of the JSON files the committed-secrets "
                "gate judges",
                accepts=(_patterns, "a non-empty list with no blank pattern"),
            ),
            _row(
                ("secrets", "scanner", "exclusions"),
                "object",
                {},
                "the scanner findings excused, each exact repo-relative path "
                "mapped to {rule id: reason}; empty: none is excused",
                accepts=(
                    _exclusions,
                    "an object mapping an exact repo-relative path (no glob, no "
                    "`..`, not absolute) to a non-empty object of rule id to a "
                    "non-empty reason",
                ),
            ),
            _row(
                ("secrets", "scanner", "history_log_opts"),
                "list_of_str",
                ["--all"],
                "the git log options the history scan passes the scanner",
                accepts=(
                    _log_options,
                    "a non-empty list of options, none blank or holding whitespace",
                ),
            ),
            _row(
                ("secrets", "scanner", "download_max_bytes"),
                "int",
                104857600,
                "the most bytes `make secrets-install` reads of a release archive "
                "before it refuses it",
                accepts=(_at_least_one, "a whole number, 1 or more"),
            ),
            _row(
                ("secrets", "scanner", "download_timeout_seconds"),
                "int",
                60,
                "how long `make secrets-install` waits on the release server "
                "before it gives up",
                accepts=(_at_least_one, "a whole number, 1 or more"),
            ),
            _row(
                ("secrets", "scanner", "install_root"),
                "nonempty_str",
                NONE,
                "the per-user directory, outside the checkout, `make "
                "secrets-install` installs the scanner under",
                accepts=(_user_path, "an absolute path or one under `~/`, no `..`"),
            ),
            _row(
                ("secrets", "scanner", "leak_exit_code"),
                "int",
                77,
                "the status the scanner is told to exit with when it finds a "
                "candidate secret",
                accepts=(_scanner_exit_code, "a value from 3 to 125"),
            ),
            _row(
                ("secrets", "scanner", "name"),
                "nonempty_str",
                "gitleaks",
                "the secret scanner's program name, the release archive member "
                "the installer takes and the record names; scripts/scan_secrets.py "
                "adapts gitleaks only and refuses any other name",
                accepts=_ONE_PATH_PART,
            ),
            _row(
                ("secrets", "scanner", "record_file"),
                "repo_path",
                ".secret-scan/scanner.json",
                "where `make secrets-install` records the scanner's path, rev and "
                "digest; git must ignore it",
            ),
            _row(
                ("secrets", "scanner", "refused_files"),
                "list_of_str",
                [".gitleaks.toml", ".gitleaksignore"],
                "the basenames of the scanner's own config and ignore files, "
                "which a scan refuses to run beside",
                accepts=(_basenames, "a non-empty list of bare file names"),
            ),
            _row(
                ("secrets", "scanner", "release_assets"),
                "object",
                NONE,
                "the scanner's release archive for each platform, its file name "
                "and sha256",
                accepts=(
                    _release_assets,
                    "a non-empty object mapping a lowercase `<system>-<machine>` "
                    "to {file: a bare .tar.gz name, sha256: 64 lowercase hex}",
                ),
            ),
            _row(
                ("secrets", "scanner", "release_url"),
                "nonempty_str",
                NONE,
                "the one URL an asset's file name is joined to; a mirror repoints it",
                accepts=(
                    _release_url,
                    "an https URL with a host, or a file:/// URL, with no user "
                    "part, query or fragment",
                ),
            ),
            _row(
                ("secrets", "scanner", "rev"),
                "nonempty_str",
                "v8.30.1",
                "the scanner release `make secrets-install` installs and the "
                "record must name",
                accepts=_ONE_PATH_PART,
            ),
            _row(
                ("shell", "enabled"),
                "bool",
                True,
                "whether scripts/shell_gate.py judges the project's shell scripts; "
                "the copier question `shell` sets it, and false makes every shell "
                "target say so and run no tool",
            ),
            _row(
                ("shell", "excluded_paths"),
                "object",
                {},
                "each repo-relative path, itself and everything under it, that "
                "scripts/shell_gate.py never judges (a vendored script), mapped "
                "to the reason; an entry that covers no file is refused",
                accepts=_ANY_REASONED_PATHS,
            ),
            _row(
                ("shell", "formatter"),
                "nonempty_str",
                "shfmt",
                "the shell formatter scripts/shell_gate.py runs for `make fmt-sh` "
                "and `make fmt-check-sh`, by adapter name; a name it has no "
                "adapter for is refused",
            ),
            _row(
                ("shell", "linter"),
                "nonempty_str",
                "shellcheck",
                "the shell linter scripts/shell_gate.py runs for `make lint-sh`, "
                "by adapter name; a name it has no adapter for is refused",
            ),
            _row(
                ("shell", "no_scripts"),
                "nonempty_str_or_null",
                None,
                "the reason the project has no shell script and no shell test; "
                "null: zero shell files is NOTHING_JUDGED, and a reason left in "
                "place once a shell file exists is refused",
            ),
            _row(
                ("shell", "script_suffixes"),
                "list_of_str",
                [".sh", ".bash"],
                "the file-name suffixes that make a file a shell script",
                accepts=(
                    _suffixes,
                    "a non-empty list of suffixes, each a dot and at least one "
                    "more character, with no whitespace or `/`",
                ),
            ),
            _row(
                ("shell", "shebang_shells"),
                "list_of_str",
                ["sh", "bash"],
                "the interpreter names whose shebang makes a file with no "
                "script suffix a shell script",
                accepts=(
                    _program_names,
                    "a non-empty list of bare program names, with no whitespace "
                    "or path separator",
                ),
            ),
            _row(
                ("shell", "test_runner"),
                "nonempty_str",
                "bats",
                "the shell test runner scripts/shell_gate.py runs for `make "
                "test-sh`, by adapter name; a name it has no adapter for is "
                "refused",
            ),
            _row(
                ("shell", "test_suffixes"),
                "list_of_str",
                [".bats"],
                "the file-name suffixes that make a file a shell test, which "
                "`make test-sh` runs and the lint and format modes do not judge",
                accepts=(
                    _suffixes,
                    "a non-empty list of suffixes, each a dot and at least one "
                    "more character, with no whitespace or `/`",
                ),
            ),
            _row(
                ("tests", "child_timeout_seconds"),
                "int",
                NONE,
                "the seconds a test of the shipped harness lets a child process "
                "run before it kills it and fails",
                accepts=(
                    _at_least_one_second,
                    "a value >= 1 and <= %s" % _MOST_SECONDS_TEXT,
                ),
            ),
            _row(
                ("tests", "isolation", "exempt"),
                "object",
                {},
                "per axis, the tests that may reach outside their tier on it, "
                "each with its reason; empty: none may",
            ),
            _row(
                ("tests", "isolation", "stores"),
                "list_of_str",
                [],
                "the live stores a test reaches only through the store_copy "
                "fixture; empty: none is listed",
            ),
            _row(
                ("tests", "isolation", "tiers"),
                "object",
                NONE,
                "what a test of each tier marker may reach on the network, "
                "writes and stores axes",
            ),
            _row(
                ("tests", "scratch_root"),
                "nonempty_str",
                NONE,
                "where test scratch lives: an absolute path, `~` allowed, "
                "outside the system temporary directory and the checkout",
                env="KEEL_TEST_SCRATCH",
                accepts=(_no_parent_part, "a path with no `..` part"),
            ),
            _row(
                ("tests", "memory_scratch_root"),
                "nonempty_str_or_null",
                None,
                "where test scratch lives when memory can hold it: an absolute "
                "path in a memory-backed directory, `-<uid>` appended; null "
                "leaves tests.scratch_root",
                accepts=(_no_parent_part, "a path with no `..` part"),
            ),
            _row(
                ("tests", "memory_scratch_min_free_mb"),
                "int",
                NONE,
                "the megabytes the memory root's file system must have free "
                "for a session to choose it",
                accepts=(_not_negative, "a value >= 0"),
            ),
            _row(
                ("tests", "workers"),
                "int",
                0,
                "how many pytest-xdist workers `make test` starts (`-n auto`); "
                "0 runs the suite in one process",
                accepts=(_not_negative, "a value >= 0"),
            ),
            _row(
                ("toolchain", "node_major"),
                "int",
                24,
                "the Node.js major version CI installs and `make fe-install` accepts",
                accepts=(_at_least_one, "a value >= 1"),
            ),
            _row(
                ("toolchain", "python"),
                "nonempty_str",
                "3.11",
                "the Python version CI installs, which must satisfy "
                "layers.backend.python and requires-python",
                accepts=(_dotted_release, "a version written MAJOR.MINOR[.PATCH]"),
            ),
            _row(
                ("toolchain", "runner_images"),
                "list_of_str",
                ["ubuntu-24.04"],
                "the runner images a workflow's runs-on may name",
                accepts=(
                    _pinned_images,
                    "a non-empty list of image names, none blank and none a "
                    "moving `-latest` label",
                ),
            ),
            _row(
                ("transports", "enabled"),
                "list_of_str",
                NONE,
                "the transports this project serves, each a key of "
                "transports.available",
            ),
            _row(
                ("transports", "extras"),
                "object",
                {},
                "an enabled transport mapped to the pyproject.toml extra that "
                "installs its packages; the gate judges that extra and its "
                "tests fail rather than skip without it",
                accepts=(_extra_map, "transport names mapped to one extra name each"),
            ),
            _row(
                ("venv", "extras"),
                "list_of_str",
                ["dev"],
                "the pyproject.toml extras the gate imports, judged installed "
                "by scripts/check_venv.py before `make verify` runs a goal",
                accepts=(_extra_names, "a non-empty list of one-word extra names"),
            ),
            _row(
                ("transports", "grpc", "port"),
                "int",
                50051,
                "the TCP port the gRPC transport's server listens on",
                accepts=(_port, "a value from 1 to 65535"),
            ),
            _row(
                ("transports", "serve", "memory_cap_mb"),
                "int_or_null",
                4096,
                "the megabytes of address space a REST, MCP or gRPC server "
                "process may hold (RLIMIT_AS); null: no cap",
                accepts=(_null_or_at_least_one, "a value >= 1"),
            ),
            _row(
                ("transports", "serve", "shutdown_grace_seconds"),
                "number",
                10,
                "the seconds a REST or gRPC server gives the calls in flight to "
                "finish after a stop signal before it ends them",
                accepts=(
                    _zero_to_most_seconds,
                    "a value >= 0 and <= %s" % _MOST_SECONDS_TEXT,
                ),
            ),
            _row(
                ("transports", "grpc", "workers"),
                "int",
                8,
                "how many threads the gRPC transport's server answers calls on",
                accepts=(_at_least_one, "a value >= 1"),
            ),
        ),
        key=lambda k: k.path,
    )
)

# Where the config declares a variable that carries a value this process may
# read: (path, shape). `name` is one name, `names` a list of names, `values`
# a map whose values are lists of names, `keys` a map whose keys are names,
# and a `*` segment takes every value of the map it stands in. env() and the
# config-reads gate test both derive the declared set from here.
VARIABLE_SOURCES = (
    (("e2e", "mcp_env"), "keys"),
    (("evidence", "run_date", "env"), "name"),
    (("launcher", "farm", "adapters", "*", "inside_env"), "names"),
    (("make_targets", "gate_vars"), "names"),
    (("make_targets", "unattended_vars"), "names"),
    (("models", "credential_env"), "values"),
)


def _dotted(path: Tuple[str, ...]) -> str:
    return ".".join(path)


def _json_type(value: object) -> str:
    """The JSON name of *value*'s type, for a message that must not show it."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _canonical(value: object) -> str:
    # sort_keys, so a dict default prints the same bytes in every run.
    return json.dumps(value, sort_keys=True)


def _refuse_duplicates(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
    seen: Dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(
                "the key `%s` appears twice in one object, so which value counts "
                "is ambiguous; keep one" % key
            )
        seen[key] = value
    return seen


def _refuse_constant(name: str) -> Any:
    raise ValueError("%s is not a JSON value" % name)


def _conflict_line(text: str) -> Optional[int]:
    """The first merge-conflict hunk's line in *text* by conflict_guard's
    grammar, or None; raises whatever loading the grammar raises."""
    spec = importlib.util.spec_from_file_location("_keel_conflict_grammar", _GRAMMAR)
    if spec is None or spec.loader is None:
        raise ImportError("no loader for %s" % _GRAMMAR)
    grammar = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(grammar)
    line = grammar.conflict_line(text)
    return None if line is None else int(line)


def _unparsed(relpath: str, text: str, exc: ValueError) -> ConfigUnreadable:
    unchecked: Optional[str] = None
    try:
        line = _conflict_line(text)
    except Exception as why:  # noqa: BLE001 -- any failure keeps the parse error
        line = None
        unchecked = str(why) or type(why).__name__
    if line is not None:
        return ConfigUnreadable(
            relpath,
            [
                "%s holds a merge-conflict hunk at line %d; resolve it, then "
                "finish the update (%s)" % (relpath, line, _FINISH_DOC)
            ],
            conflict_line=line,
        )
    suffix = (
        "" if unchecked is None else " (conflict markers not checked: %s)" % (unchecked)
    )
    return ConfigUnreadable(
        relpath,
        ["%s cannot be read as JSON (%s)%s" % (relpath, exc, suffix)],
        unchecked=unchecked,
    )


def read(root: str, relpath: str = CONFIG_FILE) -> Dict[str, Any]:
    """The parsed object in *root*/*relpath*: a new dict on every call, read
    from disk each time. Raises ConfigAbsent when the file does not exist and
    ConfigUnreadable for any other reason it cannot be used."""
    path = os.path.join(root, relpath)
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except FileNotFoundError as exc:
        raise ConfigAbsent(relpath, ["%s does not exist" % relpath]) from exc
    except OSError as exc:
        raise ConfigUnreadable(
            relpath, ["%s cannot be read (%s)" % (relpath, exc)]
        ) from exc
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigUnreadable(
            relpath, ["%s is not UTF-8 (%s)" % (relpath, exc)]
        ) from exc
    try:
        loaded = json.loads(
            text,
            object_pairs_hook=_refuse_duplicates,
            parse_constant=_refuse_constant,
        )
    except ValueError as exc:
        raise _unparsed(relpath, text, exc) from exc
    if not isinstance(loaded, dict):
        raise ConfigUnreadable(
            relpath,
            [
                "%s holds a JSON %s at the top level; it must be an object"
                % (relpath, _json_type(loaded))
            ],
        )
    return loaded


def rows(*paths: Tuple[str, ...]) -> Tuple[Key, ...]:
    """The declared rows for *paths*, in the order given. Raises KeyError for
    a path KEYS does not declare: a reader of an undeclared key is a defect."""
    table = {k.path: k for k in KEYS}
    out = []
    for path in paths:
        if path not in table:
            raise KeyError(
                "%s is not declared in scripts/config_loader.py KEYS"
                % _dotted(tuple(path))
            )
        out.append(table[path])
    return tuple(out)


def _check_table(keys: Iterable[Key]) -> List[Key]:
    """*keys* sorted by path, or ValueError for a table resolve cannot judge."""
    ordered = sorted(keys, key=lambda k: k.path)
    files = set()
    for i, key in enumerate(ordered):
        if key.type not in TYPES:
            raise ValueError(
                "%s has type %r, not one of %s"
                % (_dotted(key.path), key.type, ", ".join(sorted(TYPES)))
            )
        if i and ordered[i - 1].path == key.path:
            raise ValueError("%s is declared twice" % _dotted(key.path))
        if key.file is not None:
            files.add(key.file)
    if len(files) > 1:
        raise ValueError(
            "resolve takes the rows of one file, not %s" % ", ".join(sorted(files))
        )
    return ordered


def _lookup(loaded: Mapping[str, Any], path: Tuple[str, ...]) -> Tuple[object, int]:
    """(value or NONE, depth): NONE with depth -1 when unset, NONE with the
    depth of the first segment whose parent is not an object otherwise."""
    node: Any = loaded
    for depth, part in enumerate(path):
        if not isinstance(node, dict):
            return NONE, depth
        if part not in node:
            return NONE, -1
        node = node[part]
    return node, -1


def _holds_at(value: object) -> bool:
    # A user part may be a credential under any key name, and parsers disagree
    # on where one starts (urllib sees none in `https:/u:tok@h`, Node and
    # browsers see user u and password tok), so any `@` in a refused string
    # hides it. That also hides a harmless `a@b.com`: a refusal that names the
    # key without its value costs a look at the file, a printed token costs a
    # rotation.
    return isinstance(value, str) and "@" in value


_LIST_TYPES = ("list_of_str", "list_of_str" + _NULLABLE)


def _refused_members(key: Key, value: List[Any], bound: bool) -> str:
    """The suffix naming what list *value* is refused for: each member the
    row's check refuses on its own, once each in the order written, else
    the members written more than once when the list without them passes,
    else nothing (the list is refused as a whole)."""
    check = TYPES[key.type][0]

    def passes(members: List[Any]) -> bool:
        if not check(members):
            return False
        return not bound or key.accepts is None or bool(key.accepts[0](members))

    def first_seen(members: List[Any]) -> List[Any]:
        # By canonical JSON, so an unhashable member is compared too.
        seen, out = set(), []
        for m in members:
            text = _canonical(m)
            if text not in seen:
                seen.add(text)
                out.append(m)
        return out

    bad = first_seen([m for m in value if not passes([m])])
    if bad:
        return "; refused members: %s" % ", ".join(_canonical(m) for m in bad)
    once = first_seen(value)
    if len(once) < len(value) and passes(once):
        texts = [_canonical(m) for m in value]
        repeated = [m for m in once if texts.count(_canonical(m)) > 1]
        return "; repeated members: %s" % ", ".join(_canonical(m) for m in repeated)
    return ""


def _wrong_line(where: str, name: str, key: Key, value: object, bound: bool) -> str:
    """The one line refusing *value*, read from *where* under *name*."""
    check_text = TYPES[key.type][1]
    shown = ""
    if _holds_at(value):
        shown = " <hidden: it holds an @>"
    # A null is named by its JSON type alone; showing it too reads "null null".
    elif not key.secret and value is not None and not isinstance(value, (dict, list)):
        shown = " " + _canonical(value)
    accepted = check_text
    refused = ""
    if bound and key.accepts is not None:
        accepted = "%s with %s" % (check_text, key.accepts[1])
        if key.type.endswith(_NULLABLE):
            # Null first: "an integer, or null with a value >= 1" reads as a
            # bound on null, which takes none.
            base_text = TYPES[key.type[: -len(_NULLABLE)]][1]
            accepted = "null, or %s with %s" % (base_text, key.accepts[1])
        if isinstance(value, dict) and not key.secret:
            # Each entry is judged alone, so a map with one bad entry among
            # many says which; a bound on the whole map (empty, too few)
            # refuses no single entry and names none.
            names = sorted(k for k in value if not key.accepts[0]({k: value[k]}))
            if names:
                refused = "; refused entries: %s" % ", ".join(
                    _canonical(k) for k in names
                )
    if isinstance(value, list) and not key.secret and key.type in _LIST_TYPES:
        refused = _refused_members(key, value, bound)
    return "%s: %s is %s%s; accepted: %s%s" % (
        where,
        name,
        _json_type(value),
        shown,
        accepted,
        refused,
    )


def resolve(
    loaded: Mapping[str, Any],
    keys: Iterable[Key],
    where: str,
    environ: Optional[Mapping[str, str]] = None,
    stream: Optional[IO[str]] = None,
) -> Dict[Tuple[str, ...], Any]:
    """{path: value} for each of *keys*, read from *loaded* (the parsed file
    named *where* in every line) and *environ* (os.environ when None), with
    the lines written to *stream* (stderr when None). Raises WrongValue or
    NotSet after writing every line; ValueError for a table it cannot judge.
    Mutates neither input and hands out copies, never the table's default."""
    ordered = _check_table(keys)
    environ = os.environ if environ is None else environ
    out_stream = sys.stderr if stream is None else stream
    values: Dict[Tuple[str, ...], Any] = {}
    wrong: List[str] = []
    missing: List[Key] = []
    parents: Set[Tuple[str, ...]] = set()
    for key in ordered:
        row_where = where if key.file is not None else _ENVIRONMENT
        # Where the value was read and under what name, so a refused value is
        # blamed on the place that holds it.
        source, name = where, _dotted(key.path)
        value: object = NONE
        if key.env is not None and environ.get(key.env):
            value = environ[key.env]
            source, name = _ENVIRONMENT, key.env
        elif key.file is not None:
            value, depth = _lookup(loaded, key.path)
            if depth >= 0:
                parent = key.path[:depth]
                if parent not in parents:
                    parents.add(parent)
                    children = [
                        _dotted(k.path)
                        for k in ordered
                        if k.file is not None and k.path[:depth] == parent
                    ]
                    node, _ = _lookup(loaded, parent)
                    wrong.append(
                        "%s: %s is %s; accepted: an object holding %s"
                        % (
                            where,
                            _dotted(parent),
                            _json_type(node),
                            ", ".join(children),
                        )
                    )
                continue
        if value is not NONE:
            if not TYPES[key.type][0](value):
                wrong.append(_wrong_line(source, name, key, value, bound=False))
            elif key.accepts is not None and not key.accepts[0](value):
                wrong.append(_wrong_line(source, name, key, value, bound=True))
            else:
                values[key.path] = copy.deepcopy(value)
            continue
        if key.required:
            missing.append(key)
            continue
        values[key.path] = copy.deepcopy(key.default)
        announced = (row_where, key.path)
        if announced not in _ANNOUNCED:
            _ANNOUNCED.add(announced)
            shown = _HIDDEN if key.secret else _canonical(key.default)
            out_stream.write(
                _DEFAULT_LINE % (_dotted(key.path), shown, _dotted(key.path), row_where)
            )
    not_set = [
        _NOT_SET_LINE
        % (
            _dotted(k.path),
            _dotted(k.path),
            where if k.file is not None else _ENVIRONMENT,
        )
        for k in missing
    ]
    lines = wrong + not_set
    for line in lines:
        out_stream.write(line + "\n")
    if wrong:
        raise WrongValue(where, lines)
    if missing:
        raise NotSet(where, lines, [k.path for k in missing])
    return values


def _names_at(
    node: object, path: Tuple[str, ...], shape: str, where: str, trail: Tuple[str, ...]
) -> List[str]:
    """The variable names one VARIABLE_SOURCES entry declares in *node*."""
    if not path:
        if shape == "name":
            names: List[object] = [node]
        elif shape == "names":
            names = list(node) if isinstance(node, list) else [node]
            if not isinstance(node, list):
                names = [None]
        elif shape == "keys":
            names = sorted(node) if isinstance(node, dict) else [None]
        else:
            if not isinstance(node, dict) or not all(
                isinstance(v, list) for v in node.values()
            ):
                names = [None]
            else:
                names = [n for v in node.values() for n in v]
        bad = [n for n in names if not _is_nonempty_str(n)]
        if bad:
            raise WrongValue(
                where,
                [
                    "%s: %s is %s; accepted: the variable names it declares"
                    % (where, _dotted(trail), _json_type(node))
                ],
            )
        return [str(n) for n in names]
    if not isinstance(node, dict):
        return []
    head, rest = path[0], path[1:]
    if head == "*":
        out: List[str] = []
        for name in sorted(node):
            out += _names_at(node[name], rest, shape, where, trail + (name,))
        return out
    if head not in node:
        return []
    return _names_at(node[head], rest, shape, where, trail + (head,))


def served_visibilities(root: str, stream: Optional[IO[str]] = None) -> FrozenSet[str]:
    """The levels in *root*'s config/project.json `corpus.served_visibilities`,
    the one allowlist every reader the project serves filters corpus nodes
    by. Raises ConfigError (WrongValue for a level outside VISIBILITY_ORDER),
    so a caller serves nothing rather than guess."""
    path = ("corpus", "served_visibilities")
    values = resolve(read(root), rows(path), CONFIG_FILE, stream=stream)
    return frozenset(values[path])


def is_served(node: Mapping[str, Any], served: Collection[str]) -> bool:
    """True when corpus *node* states a `visibility` that is one of *served*,
    the levels served_visibilities resolved. The one served-or-not decision
    every corpus reader the project serves makes. A node with no `visibility`
    field, or one that is not a level string, is not served: fail closed,
    never assumed open."""
    level = node.get("visibility")
    return isinstance(level, str) and level in served


def strictest_visibility(stated: Iterable[Optional[str]]) -> Optional[str]:
    """The most restrictive of the *stated* visibilities, None and empty
    skipped, or None when nothing is stated. A value outside VISIBILITY_ORDER
    outranks every member: it cannot be ranked, so it is kept rather than read
    as a looser level, and check_A and check_corpus refuse it wherever it lands."""
    strictest = None
    rank = -1
    for value in stated:
        if not value:
            continue
        here = (
            VISIBILITY_ORDER.index(value)
            if value in VISIBILITY_ORDER
            else len(VISIBILITY_ORDER)
        )
        if here > rank:
            strictest, rank = value, here
    return strictest


def chain_level(stated: Iterable[Optional[str]]) -> str:
    """The level a corpus node takes from *stated*, its own level and its
    README chain's (scripts/corpus_level.py stated_levels): the most
    restrictive stated, else `internal`, the level CONVENTIONS §1's template
    frontmatter writes, so an unlabelled node is not published. A child
    stating a looser level than an ancestor still comes out at the
    ancestor's, so confidentiality cannot leak through a child."""
    return strictest_visibility(stated) or "internal"


def is_served_now(
    node: Mapping[str, Any],
    served: Collection[str],
    stated_now: Optional[Iterable[Optional[str]]],
) -> bool:
    """True when corpus *node* may be served by a reader that reads its body
    from disk: the stricter of the node's corpus level and the level its file
    states now (*stated_now*, scripts/corpus_level.py stated_now, ranked by
    chain_level) is one of *served*. A file reclassified after the corpus was
    built is therefore served at its new level, never its old one. Fail
    closed: is_served must hold, and *stated_now* None (a file whose level
    cannot be read) or a level outside VISIBILITY_ORDER is not served."""
    if not is_served(node, served) or stated_now is None:
        return False
    now = chain_level(stated_now)
    if now not in VISIBILITY_ORDER:
        return False
    return strictest_visibility([node["visibility"], now]) in served


def cut_hidden(node: Mapping[str, Any], shown: Collection[str]) -> Dict[str, Any]:
    """A copy of corpus *node* whose `links`, `children` and `parent` name only
    the node ids in *shown*, the ids of the nodes a reader serves, so a served
    node never carries a hidden node's id. A link that is not an object with a
    `to` in *shown* is dropped, a hidden parent becomes None, and a field the
    node does not have stays absent."""
    out = dict(node)
    if "links" in out:
        out["links"] = [
            ln
            for ln in out["links"] or []
            if isinstance(ln, Mapping) and ln.get("to") in shown
        ]
    if "children" in out:
        out["children"] = [c for c in out["children"] or [] if c in shown]
    if out.get("parent") is not None and out["parent"] not in shown:
        out["parent"] = None
    return out


def declared_variables(
    loaded: Mapping[str, Any], where: str = CONFIG_FILE
) -> Tuple[str, ...]:
    """Every variable *loaded* declares as carrying a value, sorted, from the
    VARIABLE_SOURCES entries present; an absent entry declares none. Raises
    WrongValue for an entry of the wrong shape."""
    names: Set[str] = set()
    for path, shape in VARIABLE_SOURCES:
        names.update(_names_at(loaded, path, shape, where, ()))
    return tuple(sorted(names))


def env(
    name: str,
    environ: Optional[Mapping[str, str]] = None,
    root: Optional[str] = None,
) -> Optional[str]:
    """The value of declared variable *name*, or None when it is unset or
    empty. A name no KEYS row names is looked up in *root*'s config (the
    project this module ships in when None) through declared_variables; one
    declared nowhere raises ConfigError, never reading its value."""
    if name not in {k.env for k in KEYS if k.env is not None}:
        base = _REPO if root is None else root
        if name not in declared_variables(read(base), CONFIG_FILE):
            raise ConfigError(
                None,
                [
                    "%s is not a variable a scripts/config_loader.py KEYS row or "
                    "config/project.json declares; declare it before reading it" % name
                ],
            )
    value = (os.environ if environ is None else environ).get(name)
    return value or None


# One module object under both import names: scripts/ is a namespace package,
# so `import config_loader` (scripts/ on sys.path) and `scripts.config_loader`
# would otherwise be two modules, with two announced sets and two ConfigError
# classes, and a caller's except clause would miss the other's raise.
_SELF = sys.modules.get(__name__)
if _SELF is None:
    raise ImportError(
        "config_loader was executed without being registered in sys.modules; "
        "import it, or register the module before exec_module"
    )
sys.modules.setdefault("config_loader", _SELF)
sys.modules.setdefault("scripts.config_loader", _SELF)


def _bind_to_package(module: ModuleType) -> None:
    """Set *module* as the `config_loader` attribute of the `scripts`
    package that holds this file. `import scripts.config_loader` finds the
    name in sys.modules and never loads it, so the package never gets the
    attribute and `scripts.config_loader` would raise AttributeError. The
    package is imported here when the name resolves to this file's
    directory; find_spec runs no package code, so a `scripts` elsewhere on
    the path is left alone, and a path where no `scripts` resolves leaves
    nothing to bind."""
    here = os.path.realpath(os.path.dirname(os.path.abspath(__file__)))
    # Any: a namespace package carries no declared attributes to type against.
    package: Any = sys.modules.get("scripts")
    if package is None:
        spec = importlib.util.find_spec("scripts")
        locations = [] if spec is None else spec.submodule_search_locations or []
        if here not in [os.path.realpath(p) for p in locations]:
            return
        package = importlib.import_module("scripts")
    if here in [os.path.realpath(p) for p in getattr(package, "__path__", [])]:
        package.config_loader = module


_bind_to_package(_SELF)
