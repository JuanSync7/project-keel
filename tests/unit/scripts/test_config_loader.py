"""
title: Unit — the one config loader (declared keys, the default line, the not-set line, a refused value)
kind: tests
layer: n/a
summary: scripts/config_loader.py resolves a parsed config against declared rows. An unset key with a default takes it and writes one `[using default]` line naming the key, its canonical-JSON value and the file, once per (file, key) per process under either import name, and a secret shows `<hidden>` and never its value; a set key of the wrong type or out of its bound is refused in one line naming the key, the file, the value's JSON type and what is accepted, a secret's value never in the exception or the stream; every unset required key is written as one `[not set]` line in sorted key order before one NotSet; a wrong value and a missing one together write every line and raise WrongValue. An environment value wins only for a row that names a variable and only when it is not empty, and `env` refuses a variable nothing declares. resolve neither mutates its input nor hands out the table's own default, and gives the same values and lines twice. A refused map names each entry that is refused on its own. Each seconds key refuses a value past threading.TIMEOUT_MAX, keeps one at it, and models.timeout_seconds refuses an empty map. The key table is well formed against keel's own config, every models.credential_env name has a secret variable-only row, the variables the config declares are derived from it, and the module parses on the oldest hook interpreter.
@covers scripts/config_loader.py
"""

import copy
import importlib
import importlib.util
import io
import json
import sys
import threading
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "tests" / "integration"))

import config_loader  # noqa: E402
import test_gate_scope as gate_scope  # noqa: E402
from config_loader import (  # noqa: E402
    CONFIG_FILE,
    KEYS,
    NONE,
    ConfigError,
    Key,
    NotSet,
    WrongValue,
    env,
    resolve,
)

pytestmark = pytest.mark.unit

_WHERE = "config/project.json"
_SENTINEL = "tok-SENTINEL"


def _key(
    path,
    type_,
    default=NONE,
    secret=False,
    env_name=None,
    file=CONFIG_FILE,
    accepts=None,
):
    return Key(
        tuple(path), type_, default, secret, "a row under test", env_name, file, accepts
    )


@pytest.fixture(autouse=True)
def _fresh_announcements():
    """Each case starts as a fresh process would: no default announced yet.
    Cleared, never reloaded, so every import name keeps one module object."""
    config_loader._ANNOUNCED.clear()
    yield
    config_loader._ANNOUNCED.clear()


def test_an_unset_key_with_a_default_takes_it_and_prints_one_line():
    buf = io.StringIO()
    got = resolve(
        {}, (_key(("a", "b"), "list_of_str", []),), _WHERE, environ={}, stream=buf
    )
    assert got == {("a", "b"): []}
    assert buf.getvalue() == (
        "[using default] a.b = []  (not set; to change it, set a.b in config/project.json)\n"
    )


def test_a_set_key_takes_its_value_and_prints_nothing():
    buf = io.StringIO()
    got = resolve(
        {"a": {"b": ["x"]}},
        (_key(("a", "b"), "list_of_str", []),),
        _WHERE,
        environ={},
        stream=buf,
    )
    assert got == {("a", "b"): ["x"]}
    assert buf.getvalue() == ""


def test_a_default_line_prints_once_per_key_per_process_under_either_import_name():
    scripts_loader = importlib.import_module("scripts.config_loader")
    assert sys.modules["config_loader"] is sys.modules["scripts.config_loader"]
    assert scripts_loader is config_loader
    from scripts import config_loader as from_package

    assert from_package is config_loader
    row = _key(("a",), "object", {"z": 1, "y": [2]})
    buf = io.StringIO()
    config_loader.resolve({}, (row,), _WHERE, environ={}, stream=buf)
    scripts_loader.resolve({}, (row,), _WHERE, environ={}, stream=buf)
    assert buf.getvalue() == (
        '[using default] a = {"y": [2], "z": 1}  (not set; to change it, set a in config/project.json)\n'
    )
    # Another file is another place to set it, so it is announced again.
    scripts_loader.resolve(
        {},
        (row._replace(file="config/practices.json"),),
        "config/practices.json",
        environ={},
        stream=buf,
    )
    assert buf.getvalue().count("[using default]") == 2
    assert buf.getvalue().endswith("set a in config/practices.json)\n")


_IMPORT_NAMES = ("config_loader", "scripts", "scripts.config_loader")


def _load_by_path():
    """The loader loaded as scripts/child_env.py `_config_loader` loads it:
    by path, under the bare name."""
    spec = importlib.util.spec_from_file_location(
        "config_loader", str(_ROOT / "scripts" / "config_loader.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["config_loader"] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "first",
    [
        lambda: importlib.import_module("config_loader"),
        lambda: (
            importlib.import_module("scripts"),
            importlib.import_module("config_loader"),
        )[1],
        _load_by_path,
    ],
    ids=["bare name first", "package imported, then bare name", "loaded by path"],
)
def test_a_dotted_import_after_a_bare_one_reaches_the_same_module(monkeypatch, first):
    """`import scripts.config_loader` then `scripts.config_loader` is the
    module the bare name loaded, in whatever order the names arrive. Run on
    a fresh import state, restored afterwards, so the suite keeps one module."""
    monkeypatch.syspath_prepend(str(_ROOT))
    saved = {n: sys.modules.pop(n) for n in _IMPORT_NAMES if n in sys.modules}
    try:
        bare = first()
        importlib.import_module("scripts.config_loader")
        package = importlib.import_module("scripts")
        assert getattr(package, "config_loader", None) is bare
        assert sys.modules["scripts.config_loader"] is bare
    finally:
        for name in _IMPORT_NAMES:
            sys.modules.pop(name, None)
        sys.modules.update(saved)


def test_a_secret_default_prints_hidden_and_never_its_value():
    buf = io.StringIO()
    got = resolve(
        {},
        (_key(("api", "token"), "nonempty_str", _SENTINEL, secret=True),),
        _WHERE,
        environ={},
        stream=buf,
    )
    assert got == {("api", "token"): _SENTINEL}
    assert buf.getvalue() == (
        "[using default] api.token = <hidden>  (not set; to change it, set api.token in config/project.json)\n"
    )
    assert "SENTINEL" not in buf.getvalue()


_WRONG = (
    ("nonempty_str", 5, "integer", "a non-empty string"),
    ("int", True, "boolean", "an integer"),
    ("repo_path", "/abs/path", "string", "repo-relative"),
    ("repo_path", "a/../b", "string", "repo-relative"),
    ("list_of_str", None, "null", "a list of strings"),
    ("list_of_str", ["a", 1], "array", "a list of strings"),
    ("number", "1", "string", "a number"),
    ("bool", 0, "integer", "true or false"),
    ("object", [], "array", "an object"),
)


@pytest.mark.parametrize("type_,value,type_name,accepted", _WRONG)
def test_a_wrong_value_fails_in_one_line_naming_key_file_type_and_accepted(
    type_, value, type_name, accepted
):
    buf = io.StringIO()
    with pytest.raises(WrongValue) as exc:
        resolve(
            {"k": {"x": value}},
            (_key(("k", "x"), type_, NONE),),
            _WHERE,
            environ={},
            stream=buf,
        )
    assert len(exc.value.lines) == 1, exc.value.lines
    (line,) = exc.value.lines
    assert line.startswith("config/project.json: k.x is %s" % type_name), line
    assert "accepted: " in line and accepted in line, line
    assert buf.getvalue() == line + "\n"
    assert exc.value.path == _WHERE


def test_a_value_out_of_its_bound_is_refused_naming_the_bound():
    bound = (lambda v: 0 < v <= 1, "0 < value <= 1")
    with pytest.raises(WrongValue) as exc:
        resolve(
            {"t": 1.5},
            (_key(("t",), "number", NONE, accepts=bound),),
            _WHERE,
            environ={},
            stream=io.StringIO(),
        )
    (line,) = exc.value.lines
    assert (
        line
        == "config/project.json: t is number 1.5; accepted: a number with 0 < value <= 1"
    ), line
    got = resolve(
        {"t": 1},
        (_key(("t",), "number", NONE, accepts=bound),),
        _WHERE,
        environ={},
        stream=io.StringIO(),
    )
    assert got == {("t",): 1}


def test_a_secret_set_but_wrong_never_shows_its_value():
    buf = io.StringIO()
    rows = (
        _key(("api", "token"), "int", NONE, secret=True),
        _key(("api", "name"), "int", NONE, secret=True),
    )
    with pytest.raises(WrongValue) as exc:
        resolve(
            {"api": {"token": _SENTINEL, "name": 1.5}},
            rows,
            _WHERE,
            environ={},
            stream=buf,
        )
    assert len(exc.value.lines) == 2
    for text in (str(exc.value), buf.getvalue(), "\n".join(exc.value.lines)):
        assert "SENTINEL" not in text and "1.5" not in text, text
    assert "api.token is string; accepted: an integer" in buf.getvalue()


def test_a_parent_that_is_not_an_object_is_one_wrong_line():
    rows = (_key(("e", "dir"), "repo_path"), _key(("e", "schema"), "repo_path"))
    with pytest.raises(WrongValue) as exc:
        resolve({"e": 5}, rows, _WHERE, environ={}, stream=io.StringIO())
    assert exc.value.lines == [
        "config/project.json: e is integer; accepted: an object holding e.dir, e.schema"
    ]


def test_every_missing_required_key_is_listed_sorted_before_it_raises():
    rows = (_key(("z", "a"), "str"), _key(("b",), "int"), _key(("m", "q"), "object"))
    buf = io.StringIO()
    with pytest.raises(NotSet) as exc:
        resolve({}, rows, _WHERE, environ={}, stream=buf)
    assert exc.value.keys == [("b",), ("m", "q"), ("z", "a")]
    assert buf.getvalue() == (
        "[not set] b  (required, no default; set b in config/project.json)\n"
        "[not set] m.q  (required, no default; set m.q in config/project.json)\n"
        "[not set] z.a  (required, no default; set z.a in config/project.json)\n"
    )
    assert exc.value.lines == buf.getvalue().splitlines()


def test_a_wrong_and_a_missing_key_write_every_line_and_raise_wrong_value():
    rows = (_key(("b",), "int"), _key(("a",), "str"))
    buf = io.StringIO()
    with pytest.raises(WrongValue) as exc:
        resolve({"a": 1}, rows, _WHERE, environ={}, stream=buf)
    assert buf.getvalue().splitlines() == [
        "config/project.json: a is integer 1; accepted: a string",
        "[not set] b  (required, no default; set b in config/project.json)",
    ]
    assert exc.value.lines == buf.getvalue().splitlines()
    assert isinstance(exc.value, ConfigError)


def test_null_is_set_and_refused_unless_the_type_admits_it():
    with pytest.raises(WrongValue):
        resolve(
            {"a": None},
            (_key(("a",), "object", {}),),
            _WHERE,
            environ={},
            stream=io.StringIO(),
        )
    buf = io.StringIO()
    got = resolve(
        {"a": None},
        (_key(("a",), "object_or_null", {}),),
        _WHERE,
        environ={},
        stream=buf,
    )
    assert got == {("a",): None} and buf.getvalue() == ""


def test_resolve_is_pure_and_idempotent():
    loaded = {"a": {"b": ["x"]}, "c": 2}
    environ = {"V": "from-env"}
    rows = (
        _key(("a", "b"), "list_of_str", []),
        _key(("d",), "object", {"k": [1]}),
        _key(("e",), "nonempty_str", "file", env_name="V"),
    )
    runs = []
    for _ in range(2):
        config_loader._ANNOUNCED.clear()
        given, env_copy = copy.deepcopy(loaded), dict(environ)
        buf = io.StringIO()
        got = resolve(given, rows, _WHERE, environ=env_copy, stream=buf)
        assert given == loaded and env_copy == environ
        runs.append((got, buf.getvalue()))
    assert runs[0] == runs[1]
    got = runs[0][0]
    got[("d",)]["k"].append(2)
    got[("a", "b")].append("y")
    assert rows[1].default == {"k": [1]}, "resolve handed out the table's own default"
    assert loaded["a"]["b"] == ["x"]


def test_the_environment_wins_only_for_a_row_that_names_a_variable():
    row = _key(("m",), "nonempty_str", NONE, env_name="X")
    quiet = io.StringIO()
    assert resolve({"m": "f"}, (row,), _WHERE, environ={"X": "e"}, stream=quiet) == {
        ("m",): "e"
    }
    # An empty value is not set, as evals/_run.py reads a credential.
    assert resolve({"m": "f"}, (row,), _WHERE, environ={"X": ""}, stream=quiet) == {
        ("m",): "f"
    }
    plain = _key(("m",), "nonempty_str", NONE)
    assert resolve(
        {"m": "f"}, (plain,), _WHERE, environ={"m": "e", "X": "e"}, stream=quiet
    ) == {("m",): "f"}
    assert quiet.getvalue() == ""


def test_a_variable_only_row_names_the_environment_as_where_to_set_it():
    row = _key(
        ("ONLY_VAR",), "nonempty_str_or_null", None, env_name="ONLY_VAR", file=None
    )
    buf = io.StringIO()
    assert resolve({"ONLY_VAR": "ignored"}, (row,), _WHERE, environ={}, stream=buf) == {
        ("ONLY_VAR",): None
    }
    assert buf.getvalue() == (
        "[using default] ONLY_VAR = null  (not set; to change it, set ONLY_VAR in the environment)\n"
    )
    assert resolve({}, (row,), _WHERE, environ={"ONLY_VAR": "v"}, stream=buf) == {
        ("ONLY_VAR",): "v"
    }


def test_a_wrong_value_names_the_place_it_was_read_from():
    """A value read from a variable is blamed on the environment and the
    variable, never on the file, whether or not the row also lives in it."""
    only = _key(
        ("ONLY_VAR",), "nonempty_str_or_null", None, env_name="ONLY_VAR", file=None
    )
    both = _key(("m",), "nonempty_str", NONE, env_name="X")
    cases = (
        (only, {}, {"ONLY_VAR": "   "}, 'the environment: ONLY_VAR is string "   "'),
        (both, {"m": "f"}, {"X": "   "}, 'the environment: X is string "   "'),
        (both, {"m": "   "}, {}, 'config/project.json: m is string "   "'),
    )
    for row, loaded, environ, expected in cases:
        buf = io.StringIO()
        with pytest.raises(WrongValue) as raised:
            resolve(loaded, (row,), _WHERE, environ=environ, stream=buf)
        assert raised.value.lines == [buf.getvalue().rstrip("\n")]
        assert raised.value.lines[0].startswith(expected + "; accepted: "), (
            raised.value.lines
        )


def test_env_reads_a_declared_variable_and_refuses_an_undeclared_one():
    declared = sorted({k.env for k in KEYS if k.env})
    assert declared, "no KEYS row names a variable -- zero items"
    name = declared[0]
    assert env(name, environ={name: "v"}) == "v"
    assert env(name, environ={name: ""}) is None
    assert env(name, environ={}) is None
    manifest = json.loads((_ROOT / CONFIG_FILE).read_text(encoding="utf-8"))
    credential = sorted(manifest["models"]["credential_env"].values())[0][0]
    assert env(credential, environ={credential: "s"}, root=str(_ROOT)) == "s"
    with pytest.raises(ConfigError) as exc:
        env(
            "KEEL_UNDECLARED_FOR_TEST",
            environ={"KEEL_UNDECLARED_FOR_TEST": "undeclared-value-sentinel"},
            root=str(_ROOT),
        )
    assert "KEEL_UNDECLARED_FOR_TEST" in str(exc.value)
    assert "undeclared-value-sentinel" not in str(exc.value)


def test_the_declared_variables_are_derived_from_the_config():
    manifest = json.loads((_ROOT / CONFIG_FILE).read_text(encoding="utf-8"))
    got = config_loader.declared_variables(manifest)
    expected = {manifest["evidence"]["run_date"]["env"]}
    expected |= {
        n for names in manifest["models"]["credential_env"].values() for n in names
    }
    expected |= set(manifest["e2e"]["mcp_env"])
    expected |= set(manifest["make_targets"]["unattended_vars"]) | set(
        manifest["make_targets"]["gate_vars"]
    )
    expected |= {
        n
        for a in manifest["launcher"]["farm"]["adapters"].values()
        for n in a.get("inside_env", [])
    }
    assert expected, "no variable derived -- zero items"
    assert got == tuple(sorted(expected))
    assert config_loader.declared_variables({}) == ()
    with pytest.raises(WrongValue):
        config_loader.declared_variables({"make_targets": {"gate_vars": "PY"}})


def test_rows_returns_the_declared_rows_and_refuses_an_undeclared_path():
    first = KEYS[0]
    assert config_loader.rows(first.path) == (first,)
    with pytest.raises(KeyError):
        config_loader.rows(("no", "such", "key"))


def test_resolve_refuses_a_table_it_cannot_judge():
    with pytest.raises(ValueError):
        resolve(
            {},
            (_key(("a",), "str"), _key(("a",), "str")),
            _WHERE,
            environ={},
            stream=io.StringIO(),
        )
    with pytest.raises(ValueError):
        resolve(
            {},
            (_key(("a",), "no_such_type"),),
            _WHERE,
            environ={},
            stream=io.StringIO(),
        )
    with pytest.raises(ValueError):
        resolve(
            {},
            (_key(("a",), "str"), _key(("b",), "str", file="config/practices.json")),
            _WHERE,
            environ={},
            stream=io.StringIO(),
        )


def _get(mapping, path):
    for part in path:
        if not isinstance(mapping, dict) or part not in mapping:
            return NONE
        mapping = mapping[part]
    return mapping


def test_the_key_table_is_well_formed():
    assert len(KEYS) > 0, "no declared key -- zero items"
    paths = [k.path for k in KEYS]
    assert len(set(paths)) == len(paths), "a key is declared twice"
    assert list(KEYS) == sorted(KEYS, key=lambda k: k.path), (
        "KEYS is not sorted by path"
    )
    manifest = json.loads((_ROOT / CONFIG_FILE).read_text(encoding="utf-8"))
    credential_names = {
        n for names in manifest["models"]["credential_env"].values() for n in names
    }
    for k in KEYS:
        assert (
            isinstance(k.path, tuple)
            and k.path
            and all(isinstance(p, str) and p for p in k.path)
        ), k
        assert k.type in config_loader.TYPES, k
        assert k.meaning.strip(), k
        assert k.required is (k.default is NONE), k
        if k.default is not NONE:
            assert config_loader.TYPES[k.type][0](k.default), k
        if k.env is not None:
            assert k.env not in credential_names or k.secret, k
            assert k.type in config_loader.ENV_TYPES, k
        if k.file is None:
            assert k.env is not None, "%s has no file and no variable to read" % (
                k.path,
            )
        else:
            assert k.file in config_loader.PROJECT_READS, k
        if k.file == CONFIG_FILE and k.required:
            assert _get(manifest, k.path) is not NONE, (
                "%s is required and keel's config lacks it" % (k.path,)
            )


def test_keels_credential_rows_are_secret_variable_only_rows():
    """Every name config/project.json models.credential_env lists is a
    credential, so each has a variable-only row marked secret with no default;
    resolving one that is set never shows its value."""
    manifest = json.loads((_ROOT / CONFIG_FILE).read_text(encoding="utf-8"))
    names = sorted(
        {n for group in manifest["models"]["credential_env"].values() for n in group}
    )
    assert names, "models.credential_env names no variable -- zero items"
    by_env = {k.env: k for k in KEYS if k.env is not None}
    for name in names:
        row = by_env.get(name)
        assert row is not None, "%s has no KEYS row" % name
        assert row.path == (name,) and row.file is None, row
        assert row.secret is True and row.default is None, row
    buf = io.StringIO()
    got = resolve({}, [by_env[names[0]]], _WHERE, environ={}, stream=buf)
    assert got == {(names[0],): None}
    assert buf.getvalue() == (
        "[using default] %s = <hidden>  (not set; to change it, set %s in "
        "the environment)\n" % (names[0], names[0])
    )
    buf = io.StringIO()
    got = resolve(
        {}, [by_env[names[0]]], _WHERE, environ={names[0]: _SENTINEL}, stream=buf
    )
    assert got == {(names[0],): _SENTINEL} and buf.getvalue() == ""


def test_keels_own_config_resolves_every_file_row_silently():
    rows = tuple(k for k in KEYS if k.file == CONFIG_FILE)
    assert rows, "no row reads config/project.json -- zero items"
    manifest = json.loads((_ROOT / CONFIG_FILE).read_text(encoding="utf-8"))
    buf = io.StringIO()
    got = resolve(manifest, rows, CONFIG_FILE, environ={}, stream=buf)
    assert buf.getvalue() == ""
    assert set(got) == {k.path for k in rows}


def test_the_loader_parses_on_the_oldest_hook_interpreter_and_imports_only_the_stdlib():
    path = _ROOT / "scripts" / "config_loader.py"
    assert gate_scope._too_new_syntax(path) == []
    assert gate_scope._old_python_safe(path)


_AGENT_ROWS = (
    ("agents", "editable_names"),
    ("agents", "protected_names"),
    ("agents", "protected_paths"),
)


def _agents_block():
    manifest = json.loads((_ROOT / CONFIG_FILE).read_text(encoding="utf-8"))
    return manifest["agents"]


@pytest.mark.parametrize(
    "path, value",
    [
        (("agents", "protected_paths"), {}),
        (("agents", "protected_paths"), {"scripts": " "}),
        (("agents", "protected_paths"), {"src/../scripts": "a reason"}),
        (("agents", "protected_paths"), {"/scripts": "a reason"}),
        (("agents", "protected_paths"), {"scripts/": "a reason"}),
        (("agents", "protected_paths"), {"scripts": 1}),
        (("agents", "protected_paths"), ["scripts"]),
        (("agents", "protected_names"), {}),
        (("agents", "protected_names"), {"sub/Makefile": "a reason"}),
        (("agents", "protected_names"), {"..": "a reason"}),
        (("agents", "protected_names"), {"Makefile": ""}),
        (("agents", "editable_names"), {"docs/README.md": "a reason"}),
        (("agents", "editable_names"), {"README.md": " "}),
        (("agents", "editable_names"), {".": "a reason"}),
    ],
)
def test_the_agents_policy_rows_refuse_an_empty_or_unreasoned_map(path, value):
    block = _agents_block()
    block[path[1]] = value
    rows = config_loader.rows(*_AGENT_ROWS)
    with pytest.raises(WrongValue) as exc:
        resolve({"agents": block}, rows, _WHERE, environ={}, stream=io.StringIO())
    (line,) = exc.value.lines
    assert line.startswith("%s: %s is " % (_WHERE, ".".join(path))), line


def test_an_empty_carve_out_is_the_strict_setting_and_resolves():
    """editable_names only lifts protection, so an empty map is the setting
    with no carve-out, never a vacuous policy; and a glob over a name is a
    name, so `*.test.*` is accepted where `sub/x` is not."""
    block = _agents_block()
    block["editable_names"] = {}
    block["protected_names"] = dict(block["protected_names"], **{"*.test.*": "r"})
    rows = config_loader.rows(*_AGENT_ROWS)
    got = resolve({"agents": block}, rows, _WHERE, environ={}, stream=io.StringIO())
    assert got[("agents", "editable_names")] == {}
    assert got[("agents", "protected_names")]["*.test.*"] == "r"


def test_the_agents_policy_rows_are_required_and_the_templates_block_resolves():
    rows = config_loader.rows(*_AGENT_ROWS)
    assert all(k.required and k.file == CONFIG_FILE for k in rows), rows
    with pytest.raises(NotSet) as exc:
        resolve({}, rows, _WHERE, environ={}, stream=io.StringIO())
    assert exc.value.keys == list(_AGENT_ROWS)
    block = _agents_block()
    buf = io.StringIO()
    got = resolve({"agents": block}, rows, _WHERE, environ={}, stream=buf)
    assert buf.getvalue() == ""
    assert got[("agents", "protected_paths")] == block["protected_paths"]
    assert all(got[p] for p in _AGENT_ROWS), "an empty policy map -- zero items"


# Past threading.TIMEOUT_MAX a thread wait on the value raises OverflowError,
# so each seconds key stops there.
_SECONDS_KEYS = (
    ("models", "timeout_seconds"),
    ("tests", "child_timeout_seconds"),
    ("transports", "serve", "shutdown_grace_seconds"),
)


def _nested(path, value):
    block = value
    for part in reversed(path):
        block = {part: block}
    return block


@pytest.mark.parametrize(
    "path, value",
    [
        (("models", "timeout_seconds"), {"a": threading.TIMEOUT_MAX * 2}),
        (("models", "timeout_seconds"), {}),
        (("tests", "child_timeout_seconds"), int(threading.TIMEOUT_MAX) + 1),
        (("transports", "serve", "shutdown_grace_seconds"), threading.TIMEOUT_MAX * 2),
    ],
)
def test_a_seconds_limit_no_thread_wait_takes_is_refused_by_its_key(path, value):
    assert path in _SECONDS_KEYS
    with pytest.raises(WrongValue) as exc:
        resolve(
            _nested(path, value),
            config_loader.rows(path),
            _WHERE,
            environ={},
            stream=io.StringIO(),
        )
    (line,) = exc.value.lines
    assert line.startswith("%s: %s is " % (_WHERE, ".".join(path))), line
    assert "TIMEOUT_MAX" in line, line


@pytest.mark.parametrize(
    "path, value",
    [
        (("models", "timeout_seconds"), {"a": threading.TIMEOUT_MAX}),
        (("tests", "child_timeout_seconds"), int(threading.TIMEOUT_MAX)),
        (("transports", "serve", "shutdown_grace_seconds"), threading.TIMEOUT_MAX),
    ],
)
def test_a_seconds_limit_at_timeout_max_is_kept(path, value):
    got = resolve(
        _nested(path, value),
        config_loader.rows(path),
        _WHERE,
        environ={},
        stream=io.StringIO(),
    )
    assert got == {path: value}


def test_a_refused_map_names_each_entry_it_refuses():
    path = ("models", "timeout_seconds")
    with pytest.raises(WrongValue) as exc:
        resolve(
            _nested(path, {"good": 5, "zero": 0, "huge": 1e10 * 1e10}),
            config_loader.rows(path),
            _WHERE,
            environ={},
            stream=io.StringIO(),
        )
    (line,) = exc.value.lines
    assert line.endswith('; refused entries: "huge", "zero"'), line
