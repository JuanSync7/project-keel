"""
title: config_loader — the one way a configured value enters a process
kind: script
layer: n/a
summary: Every configured value comes through here: a key of config/project.json or config/practices.json, or an environment variable the config declares. KEYS is the one table of declared keys, each row a Key giving its path (a tuple of segments, since a segment may hold a dot), its type from the closed set TYPES, its default or NONE (required exactly when the default is NONE, so a default of null stays distinct from no default), whether it is a secret, a one-line meaning, the variable that may set it, the file it lives in (None for a variable-only row) and an optional bound. `read(root, relpath)` is the one open and parse of a config file: a missing file is ConfigAbsent, and an OSError, bytes that are not UTF-8, text that is not JSON (a NaN constant, a byte-order mark and a key written twice in one object included), or a top level that is not an object is ConfigUnreadable, naming a merge-conflict hunk an update left by its line through scripts/jobs/conflict_guard.py's grammar, loaded by path (when it cannot load, the parse error says the markers were not checked). `resolve(loaded, rows, where)` walks the rows in sorted path order. Precedence: a row that names a variable takes that variable when it is set and not empty, else the file's value; a row with no variable reads the file only; a variable-only row reads its variable only; an empty variable is not set. A set value of the wrong type or out of its bound is one line `<where>: <key> is <JSON type>[ <value>]; accepted: <what>`, naming the environment and the variable instead when the value came from a variable, the value never shown for a secret. An unset key with a default takes it and writes `[using default] <key> = <canonical JSON value>  (not set; to change it, set <key> in <where>)` to stderr once per (where, key) per process, a secret's value written `<hidden>`. Each unset required key is `[not set] <key>  (required, no default; set <key> in <where>)`; every wrong and every not-set line is written before one raise, WrongValue when any value is wrong, else NotSet carrying the sorted keys. It never ends the process: the entry point that called it returns report(ExitCode.CONFIG, ...). `env(name)` is the one literal-name read of a declared variable and refuses a name neither a row nor the config declares (declared_variables). It registers itself under both `config_loader` and `scripts.config_loader`, and as the `config_loader` attribute of the `scripts` package that holds it, so either import name, in either order, gives one module, one announced set and one set of exception classes. Never run, stdlib-only and 3.6-safe: child_env and check_structure read through it under the hook interpreter. It reads and writes nothing else, and it caches nothing, so the same file and environment give the same values and lines.
effect: read-only
"""

# NB: stdlib only, no `from __future__ import annotations`, no f-strings, no
# walrus, no dataclass, no `list[str]` or `X | None` annotations: it sits in
# the bottom import layer, which the 3.6 hook interpreter runs
# (tests/integration/test_gate_scope.py `_bottom_import_layer`).

import copy
import importlib
import importlib.util
import json
import ntpath
import os
import posixpath
import sys
from types import ModuleType
from typing import (
    IO,
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    NamedTuple,
    Optional,
    Set,
    Tuple,
)

__all__ = [
    "CONFIG_FILE",
    "ENV_TYPES",
    "KEYS",
    "NONE",
    "PRACTICES_FILE",
    "PROJECT_READS",
    "TYPES",
    "VARIABLE_SOURCES",
    "ConfigAbsent",
    "ConfigError",
    "ConfigUnreadable",
    "Key",
    "NotSet",
    "WrongValue",
    "declared_variables",
    "env",
    "read",
    "resolve",
    "rows",
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


def _no_parent_part(value: Any) -> bool:
    # Absolute is allowed (a farm job's local disk); `..` never is, so a
    # relative value cannot climb out of the checkout it resolves against.
    return ".." not in str(value).replace("\\", "/").split("/")


_ASCII_DIGITS = "0123456789"


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


# The one table of declared keys, sorted by path. A block a typed validator
# owns (child_env, evidence) is one `object` row, and the validator stays the
# typed view over the value resolved here; an open-keyed map is one row, never
# a row per name.
KEYS = tuple(
    sorted(
        (
            _row(
                ("KEEL_MCP_MODEL",),
                "nonempty_str_or_null",
                None,
                "the model the MCP Q&A server asks; null: the registry default",
                env="KEEL_MCP_MODEL",
                file=None,
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
                ("evals", "threshold"),
                "number",
                NONE,
                "the pass fraction a suite needs",
                accepts=(_in_unit_interval, "0 < value <= 1"),
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
            _row(
                ("practices", "profiles"),
                "object",
                {},
                "which domain practice profiles are on; empty: none",
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


def _wrong_line(where: str, name: str, key: Key, value: object, bound: bool) -> str:
    """The one line refusing *value*, read from *where* under *name*."""
    check_text = TYPES[key.type][1]
    shown = ""
    if not key.secret and not isinstance(value, (dict, list)):
        shown = " " + _canonical(value)
    accepted = check_text
    if bound and key.accepts is not None:
        accepted = "%s with %s" % (check_text, key.accepts[1])
    return "%s: %s is %s%s; accepted: %s" % (
        where,
        name,
        _json_type(value),
        shown,
        accepted,
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
