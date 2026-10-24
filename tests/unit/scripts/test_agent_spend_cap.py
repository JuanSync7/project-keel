"""
title: Unit — every agent CLI holds an --execute run to the model-call cap and says which model it chose
kind: tests
layer: n/a
summary: scripts/doc_review.py, scripts/refactor_practice.py, scripts/hooks/on_stop_doc_review.py and scripts/hooks/on_stop_triage.py each check, before the agent runs, that the run's upper bound of model calls (--max-chunks, --max-nodes, or the one call triage makes) is within config/project.json `agents.max_model_calls` (read through scripts/model_budget.py): a bound over the cap, or a negative bound that sets none, returns USAGE with the agent never called, a cap the config cannot give returns CONFIG, and a dry run is never refused, since it calls no model. An approved run hands the agent its bound as `max_model_calls`, the count its counted backend stops at; the agent stopping at that count (models.CallCapReached) returns FAILURE and a saved run the approval does not cover (models.RunNotApproved) returns USAGE, each naming what to do next. With --execute and no --model, each writes to stderr which model the registry default chose and why; with --model it writes no such line. A ConfigError the loader raises once the agent runs (NotSet or WrongValue) returns CONFIG with the loader line on stderr, dry run and --execute alike; two cases run the real chain against this checkout's config, changed as scripts/config_loader.py read returns it: triage on claude-code-headless with no models.timeout_seconds entry for it (PATH empty, so no CLI could start), and a doc_review dry run with runtimes.max_steps 0. A tool child the agent starts that scripts/resource_limits.py ends at config/project.json `agents.tool_timeout_seconds` or `agents.tool_max_output_bytes` (ChildTimedOut, ChildOutputTooLarge) returns FAILURE with the message naming the key and no traceback, for each CLI whose agent runs tools, dry run and --execute alike; a third real-chain case runs a doc_review dry run whose agents.tool_timeout_seconds is no longer than make_targets.gate_timeout_seconds, which run_tool refuses as CONFIG before its first child starts; a fourth runs a doc_review and a refactor_practice dry run under a --root whose make_targets.gate_timeout_seconds outlasts the shipped tool limit, which run_tool, reading that root's config as the gate runner does, refuses as CONFIG the same way. Every entry point under scripts/, mcp/ and api/ that ends in finish(main()) and reaches agents, evals, models or runtimes through any chain of imports among the modules and packages under those three directories (model_budget is one such helper; a sibling under scripts/jobs/, a helper's helper, a package and a `from scripts import` each count, and a case for each fails if the scan stops seeing it) must be one of these four or named in _HELD_ELSEWHERE with the test that holds it, and that test file must exist and name the entry point, so a new doer is not left out and a row excuses nothing it does not name. A module importlib or runpy loads by a name spelled whole in literals (a `+` of literals, an f-string with no field, a module-level name assigned one), or from a `.py` path whose every part after an anchor on the doer's own `__file__` is such a literal, is an import like any other, and every directory on that path is named too, so running models/__init__.py by its path reaches models. A load whose name or path holds any part the scan cannot read (a literal prefix beside sys.argv included), an `__import__` from-list it cannot read, a loader named other than as the callee of a call (assigned to a name or passed as a value), a loader fetched by getattr from importlib or runpy by a loader's name or a name the scan cannot read, and an exec or eval of text it cannot read each count as reaching unless _DYNAMIC_LOADS names the file with the reason; an `import_module as load` alias is followed to its call, and a row whose file no longer has such a load fails. Elsewhere the agent function is replaced by a recorder, so no model is built and nothing is written.
"""

import ast
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "hooks"))

import config_loader  # noqa: E402
import doc_review  # noqa: E402
import model_budget  # noqa: E402
import on_stop_doc_review  # noqa: E402
import on_stop_triage  # noqa: E402
import refactor_practice  # noqa: E402
from agents.doc_reviewer import DocReviewReport  # noqa: E402
from agents.practice_refactor import RefactorReport  # noqa: E402
from exit_codes import ExitCode  # noqa: E402
from models import CallCapReached, RunNotApproved  # noqa: E402
from models.registry import DEFAULT_MODEL  # noqa: E402
from scripts import resource_limits  # noqa: E402

pytestmark = pytest.mark.unit

_DOC = DocReviewReport(True, 0, 0, 0, (), (), (), (), "", False)
_REF = RefactorReport("p", True, (), (), (), "", False)

# name -> (module, agent attribute, argv before flags, bound flag, what it returns)
_CLIS = {
    "doc_review": (doc_review, "review", [], "--max-chunks", _DOC),
    "refactor_practice": (refactor_practice, "refactor", ["p"], "--max-nodes", _REF),
    "on_stop_doc_review": (on_stop_doc_review, "review", ["x"], "--max-chunks", _DOC),
    "on_stop_triage": (on_stop_triage, "triage", ["x"], None, "answer"),
}


def _wire(monkeypatch, name, approved):
    module, attr, argv, flag, result = _CLIS[name]
    calls = []

    def agent(*args, **kwargs):
        calls.append(kwargs)
        return result

    monkeypatch.setattr(module, attr, agent)
    monkeypatch.setattr(model_budget, "cap", lambda root: approved)
    return module, argv, flag, calls


@pytest.mark.parametrize("name", sorted(_CLIS))
def test_a_cap_of_zero_refuses_an_execute_run_before_the_agent_runs(
    name, monkeypatch, capsys
):
    module, argv, flag, calls = _wire(monkeypatch, name, 0)
    assert module.main(argv + ["--execute"]) is ExitCode.USAGE
    assert calls == []
    err = capsys.readouterr().err
    assert "agents.max_model_calls" in err
    # The next step names the bound's flag only where the run has one.
    assert ("or lower %s" % flag in err) if flag else ("or lower" not in err)


@pytest.mark.parametrize("name", sorted(_CLIS))
def test_a_dry_run_is_never_refused_and_names_no_model(name, monkeypatch, capsys):
    module, argv, _flag, calls = _wire(monkeypatch, name, 0)
    assert module.main(argv) is ExitCode.SUCCESS
    assert len(calls) == 1 and not calls[0].get("execute")
    assert "registry default" not in capsys.readouterr().err


@pytest.mark.parametrize("name", sorted(_CLIS))
def test_an_approved_run_without_model_says_which_model_and_why(
    name, monkeypatch, capsys
):
    module, argv, _flag, calls = _wire(monkeypatch, name, 8)
    assert module.main(argv + ["--execute"]) is ExitCode.SUCCESS
    assert len(calls) == 1 and calls[0]["execute"] is True
    err = capsys.readouterr().err
    assert repr(DEFAULT_MODEL) in err and "registry default" in err


@pytest.mark.parametrize("name", sorted(_CLIS))
def test_a_named_model_is_not_announced(name, monkeypatch, capsys):
    module, argv, _flag, calls = _wire(monkeypatch, name, 8)
    assert module.main(argv + ["--execute", "--model", "fake"]) is ExitCode.SUCCESS
    assert calls[0]["model"] == "fake"
    assert "registry default" not in capsys.readouterr().err


@pytest.mark.parametrize("name", sorted(n for n in _CLIS if _CLIS[n][3]))
def test_a_bound_over_the_cap_is_refused_and_the_bound_is_what_runs(
    name, monkeypatch, capsys
):
    module, argv, flag, calls = _wire(monkeypatch, name, 3)
    assert module.main(argv + ["--execute", flag, "4"]) is ExitCode.USAGE
    assert calls == [] and flag in capsys.readouterr().err
    assert module.main(argv + ["--execute", flag, "3"]) is ExitCode.SUCCESS
    bound = {"--max-chunks": "max_chunks", "--max-nodes": "max_nodes"}[flag]
    assert calls[0][bound] == 3 and calls[0]["max_model_calls"] == 3


def test_triage_is_approved_its_one_call(monkeypatch):
    module, argv, _flag, calls = _wire(monkeypatch, "on_stop_triage", 8)
    assert module.main(argv + ["--execute"]) is ExitCode.SUCCESS
    assert calls[0]["max_model_calls"] == 1


def _raising(monkeypatch, name, exc):
    module, argv, _flag, _calls = _wire(monkeypatch, name, 8)
    _module, attr = _CLIS[name][:2]

    def agent(*args, **kwargs):
        raise exc

    monkeypatch.setattr(module, attr, agent)
    return module, argv


@pytest.mark.parametrize("name", sorted(_CLIS))
def test_a_run_stopped_at_its_count_is_a_failure_naming_the_count(
    name, monkeypatch, capsys
):
    module, argv = _raising(monkeypatch, name, CallCapReached(3, 3))
    assert module.main(argv + ["--execute"]) is ExitCode.FAILURE
    err = capsys.readouterr().err
    assert "approved 3 model call(s)" in err and "agents.max_model_calls" in err


@pytest.mark.parametrize("name", sorted(n for n in _CLIS if _CLIS[n][3]))
def test_a_saved_run_the_approval_does_not_cover_is_refused(name, monkeypatch, capsys):
    refusal = RunNotApproved("the saved run differs", "s.json", "remove s.json")
    module, argv = _raising(monkeypatch, name, refusal)
    assert module.main(argv + ["--execute"]) is ExitCode.USAGE
    err = capsys.readouterr().err
    assert "the saved run differs" in err and "remove s.json" in err


@pytest.mark.parametrize("name", sorted(n for n in _CLIS if _CLIS[n][3]))
def test_a_negative_bound_cannot_be_estimated_and_is_refused(name, monkeypatch, capsys):
    module, argv, flag, calls = _wire(monkeypatch, name, 10**6)
    assert module.main(argv + ["--execute", flag, "-1"]) is ExitCode.USAGE
    assert calls == [] and "cannot be estimated" in capsys.readouterr().err


@pytest.mark.parametrize("name", sorted(_CLIS))
def test_a_cap_the_config_cannot_give_is_a_config_refusal(name, monkeypatch, capsys):
    module, argv, _flag, calls = _wire(monkeypatch, name, 8)

    def broken(root):
        raise config_loader.WrongValue(
            "config/project.json", ["agents.max_model_calls is -1"]
        )

    monkeypatch.setattr(model_budget, "cap", broken)
    assert module.main(argv + ["--execute"]) is ExitCode.CONFIG
    assert calls == []


# --- a setting the model or the runtime reads is refused -----------------------

# A refusal from each kind the loader raises once the agent runs: a key missing
# (models/limits.py timeout_seconds) and a value out of its bound (a model
# limit, or runtimes.max_steps when the runtime is built).
_FAULTS = {
    "not-set": config_loader.NotSet(
        "config/project.json",
        ["config/project.json: models.timeout_seconds has no entry for 'x'"],
        [("models", "timeout_seconds", "x")],
    ),
    "wrong-value": config_loader.WrongValue(
        "config/project.json", ["config/project.json: runtimes.max_steps is 0"]
    ),
}


@pytest.mark.parametrize("fault", sorted(_FAULTS))
@pytest.mark.parametrize("execute", [False, True], ids=["dry-run", "execute"])
@pytest.mark.parametrize("name", sorted(_CLIS))
def test_a_setting_the_agent_reads_and_the_loader_refuses_is_a_config_refusal(
    name, execute, fault, monkeypatch, capsys
):
    """A dry run builds the runtime too, so both modes are held."""
    module, argv = _raising(monkeypatch, name, _FAULTS[fault])
    assert module.main(argv + (["--execute"] if execute else [])) is ExitCode.CONFIG
    err = capsys.readouterr().err
    assert _FAULTS[fault].lines[0] in err and name in err, err


# The CLIs whose agent starts tool children (triage runs none).
_TOOL_CLIS = sorted(n for n in _CLIS if n != "on_stop_triage")
_TOOL_ENDS = {
    "timed-out": resource_limits.ChildTimedOut(
        "run_make_target.py did not finish within 15000 seconds, so its session "
        "was ended; the limit is config/project.json "
        "agents.tool_timeout_seconds"
    ),
    "flooded": resource_limits.ChildOutputTooLarge(
        "query_corpus.py wrote more than 64 bytes to stdout, so its session "
        "was ended; the limit is config/project.json "
        "agents.tool_max_output_bytes"
    ),
}


@pytest.mark.parametrize("end", sorted(_TOOL_ENDS))
@pytest.mark.parametrize("execute", [False, True], ids=["dry-run", "execute"])
@pytest.mark.parametrize("name", _TOOL_CLIS)
def test_a_tool_child_ended_at_its_limit_is_a_failure_naming_the_key(
    name, execute, end, monkeypatch, capsys
):
    module, argv = _raising(monkeypatch, name, _TOOL_ENDS[end])
    assert module.main(argv + (["--execute"] if execute else [])) is ExitCode.FAILURE
    err = capsys.readouterr().err
    assert str(_TOOL_ENDS[end]) in err and name in err, err
    assert "Traceback" not in err


def _config_read_as(monkeypatch, edit):
    """Every config read through scripts/config_loader.py returns this
    checkout's config/project.json changed by *edit*; the file is untouched.
    The loader's public reader is the one seam both the model limits and the
    runtime's step cap read through."""
    real = config_loader.read

    def read(root, *args, **kwargs):
        loaded = real(root, *args, **kwargs)
        edit(loaded)
        return loaded

    monkeypatch.setattr(config_loader, "read", read)


def test_a_model_time_limit_the_config_omits_stops_triage_as_config(
    monkeypatch, capsys
):
    """The reviewer's repro, in process: the real triage agent and the real
    claude-code-headless adapter, whose limit models/limits.py reads at the
    call, from a config that names no limit for it."""

    def omit(manifest):
        manifest["models"]["timeout_seconds"] = {"openai-compatible": 60}

    _config_read_as(monkeypatch, omit)
    monkeypatch.setattr(model_budget, "cap", lambda root: 1)
    # No CLI can start: the refusal comes before the spawn, and nothing is paid.
    monkeypatch.setenv("PATH", "/nonexistent")
    result = on_stop_triage.main(["x", "--execute", "--model", "claude-code-headless"])
    assert result is ExitCode.CONFIG
    err = capsys.readouterr().err
    assert "models.timeout_seconds" in err and "claude-code-headless" in err, err


def test_a_step_cap_the_loader_refuses_stops_a_dry_run_as_config(monkeypatch, capsys):
    """The runtime reads runtimes.max_steps when it is built, which a dry run
    does too, so no --execute is needed to reach the refusal."""

    def zero(manifest):
        manifest["runtimes"]["max_steps"] = 0

    _config_read_as(monkeypatch, zero)
    assert doc_review.main([]) is ExitCode.CONFIG
    assert "runtimes.max_steps" in capsys.readouterr().err


def test_a_tool_limit_that_does_not_outlast_the_gate_stops_a_dry_run_as_config(
    monkeypatch, capsys
):
    """The real chain: the doc reviewer's first tool child reads
    agents.tool_timeout_seconds through scripts/resource_limits.py run_tool,
    which refuses a value no longer than the gate runner's limit and grace
    before the child starts."""

    def short(manifest):
        manifest["agents"]["tool_timeout_seconds"] = manifest["make_targets"][
            "gate_timeout_seconds"
        ]

    _config_read_as(monkeypatch, short)
    assert doc_review.main([]) is ExitCode.CONFIG
    err = capsys.readouterr().err
    assert "agents.tool_timeout_seconds" in err
    assert "make_targets.gate_stop_grace_seconds" in err


def _practice_name():
    loaded = config_loader.read(str(_ROOT), "config/practices.json")
    return sorted(row["id"] for row in loaded["practices"])[0]


@pytest.mark.parametrize("name", ["doc_review", "refactor_practice"])
def test_a_root_whose_gate_outlasts_the_tool_limit_stops_a_dry_run_as_config(
    name, tmp_path, capsys
):
    """The gate runner a reviewer or refactorer starts reads its limit from
    the --root tree, so the tool limit is held against that tree's gate keys:
    a root whose make_targets.gate_timeout_seconds is 20000, past this
    checkout's shipped tool limit, is refused before the first child starts,
    though this checkout's own config passes the same check."""
    resource_limits.tool_limits()
    (tmp_path / "config").mkdir()
    manifest = config_loader.read(str(_ROOT))
    manifest["make_targets"]["gate_timeout_seconds"] = 20000
    (tmp_path / "config" / "project.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    practices = (_ROOT / "config" / "practices.json").read_text(encoding="utf-8")
    (tmp_path / "config" / "practices.json").write_text(practices, encoding="utf-8")
    if name == "doc_review":
        result = doc_review.main(["--root", str(tmp_path)])
    else:
        result = refactor_practice.main([_practice_name(), "--root", str(tmp_path)])
    assert result is ExitCode.CONFIG
    err = capsys.readouterr().err
    assert "agents.tool_timeout_seconds" in err and "at least 20090" in err, err


# Each entry point that builds a model or a runtime, and the test that holds
# it to a CONFIG refusal when the loader refuses a setting it reads.
_HELD_ELSEWHERE = {
    "mcp/qa_server.py": "tests/integration/test_mcp_servers.py",
    "scripts/run_evals.py": "tests/integration/test_evals_live_stub.py",
}
_AGENT_PACKAGES = ("agents", "evals", "models", "runtimes")
_ENTRY_TOPS = ("scripts", "mcp", "api")
# A load the scan cannot name stands for this, and it reaches every package
# the scan guards: a module it cannot read is counted, not skipped.
_DYNAMIC = "<a load the scan cannot name>"
# Each file whose unresolvable load is known not to reach an agent package,
# and why; a row whose file has no such load fails, so it excuses nothing.
_DYNAMIC_LOADS = {
    "scripts/check_structure.py": (
        "loads the project's own checks from config/project.json "
        "structure.project_checks, a directory outside scripts/, mcp/ and api/"
    ),
    "scripts/run_app.py": (
        "runs config/project.json layers.app.module, the app under app/, "
        "which is outside scripts/, mcp/ and api/"
    ),
}
# Calls that load a module by its dotted name, and calls that load one from a
# file path, with the position and keyword of the path argument; each is
# matched on its last attribute, so `importlib.util.` and a bare imported name
# both count.
_BY_NAME = ("import_module", "__import__", "find_spec", "run_module")
_BY_FILE = {
    "spec_from_file_location": (1, "location"),
    "run_path": (0, "path_name"),
    "SourceFileLoader": (1, "path"),
}
_LOADERS = (*_BY_NAME, *_BY_FILE)
_RUNS_TEXT = ("exec", "eval")
# The modules the loaders live in: a getattr on one of them may fetch a loader.
_LOADER_MODULES = ("importlib", "importlib.util", "importlib.machinery", "runpy")
# The only names a file path's anchor may use, so the anchor is the doer's own
# file and the literal parts after it say where the loaded module is.
_ANCHOR_NAMES = {"__file__", "os", "path", "Path", "pathlib"}


def _literal(node, assigned):
    """The whole text *node* spells in literals, or None when any part of it is
    not one: a string, a module-level name bound to one, a `+` of two, or an
    f-string with no field. A literal fragment beside a name the scan cannot
    read is not the module's name."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name) and node.id in assigned:
        return _literal(assigned.pop(node.id), assigned)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _literal(node.left, assigned)
        right = _literal(node.right, assigned)
        return None if left is None or right is None else left + right
    if isinstance(node, ast.JoinedStr):
        parts = [_literal(value, assigned) for value in node.values]
        return None if None in parts else "".join(parts)
    return None


def _anchored(node, assigned):
    """Whether *node* is a directory derived from the doer's own `__file__`
    and nothing else, so a path built on it is known up to its literal tail."""
    if isinstance(node, ast.Name) and node.id in assigned:
        return _anchored(assigned.pop(node.id), assigned)
    ids = {part.id for part in ast.walk(node) if isinstance(part, ast.Name)}
    return "__file__" in ids and ids <= _ANCHOR_NAMES


def _path_parts(node, assigned):
    """The literal path components *node* names, or None when the path holds
    a part the scan cannot read; an anchor on `__file__` may open the path."""
    if isinstance(node, ast.Name) and node.id in assigned:
        return _path_parts(assigned.pop(node.id), assigned)
    text = _literal(node, assigned)
    if text is not None:
        return [text]
    if isinstance(node, ast.Call) and _called(node) in ("join", "Path") and node.args:
        first, *rest = node.args
        head = _path_parts(first, assigned)
        if head is None and not _anchored(first, assigned):
            return None
        tail = [_literal(arg, assigned) for arg in rest]
        return None if None in tail else (head or []) + tail
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        right = _literal(node.right, assigned)
        head = _path_parts(node.left, assigned)
        if right is None or (head is None and not _anchored(node.left, assigned)):
            return None
        return (head or []) + [right]
    return None


def _argument(node, position, keyword):
    if len(node.args) > position:
        return node.args[position]
    return next((kw.value for kw in node.keywords if kw.arg == keyword), None)


def _called(node, aliases=None):
    """The loader *node* calls, by its last attribute, or by the name an
    `import ... as` gave it."""
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if not isinstance(func, ast.Name):
        return None
    return (aliases or {}).get(func.id, func.id)


def _by_name(node, called, assigned):
    """The module names a load by dotted name reads: the name, any package it
    is relative to, and an `__import__` from-list, each whole in literals."""
    name = _argument(node, 0, "name")
    if name is None:
        return [_DYNAMIC]
    named = [name]
    package = _argument(node, 1, "package")
    if called in ("import_module", "find_spec") and package is not None:
        named.append(package)
    fromlist = _argument(node, 3, "fromlist")
    if fromlist is not None:
        if not isinstance(fromlist, (ast.List, ast.Tuple)):
            return [_DYNAMIC]
        named.extend(fromlist.elts)
    texts = [_literal(arg, dict(assigned)) for arg in named]
    if None in texts:
        return [_DYNAMIC]
    names = [part for text in texts for part in text.split(".") if part]
    return names or [_DYNAMIC]


def _dynamic_names(node, assigned, aliases=None):
    """The module names one importlib, runpy or exec call loads, or _DYNAMIC
    when its argument is not a literal the scan can read."""
    called = _called(node, aliases)
    if called in _BY_NAME:
        return _by_name(node, called, assigned)
    if called in _BY_FILE:
        where = _argument(node, *_BY_FILE[called])
        parts = None if where is None else _path_parts(where, dict(assigned))
        if parts is None:
            return [_DYNAMIC]
        # Every directory on the path is named too: running models/__init__.py
        # by its path loads the models package.
        names = [
            part.removesuffix(".py")
            for text in parts
            for part in text.split("/")
            if part not in ("", ".", "..")
        ]
        return names or [_DYNAMIC]
    if called in _RUNS_TEXT and node.args:
        first = node.args[0]
        literal = isinstance(first, ast.Constant) and isinstance(first.value, str)
        return [] if literal and "import" not in first.value else [_DYNAMIC]
    return []


def _loader_aliases(tree):
    """Each local name an import binds to a loader (`from importlib import
    import_module as load` binds load), and each local name bound to a module
    the loaders live in."""
    aliases, modules = {}, set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0:
            for alias in node.names:
                full = "%s.%s" % (node.module, alias.name)
                if node.module in _LOADER_MODULES and alias.name in _LOADERS:
                    aliases[alias.asname or alias.name] = alias.name
                elif full in _LOADER_MODULES:
                    modules.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _LOADER_MODULES:
                    modules.add(alias.asname or alias.name.split(".")[0])
    return aliases, modules


def _names_a_loader(node, aliases):
    if isinstance(node, ast.Attribute):
        return node.attr in _LOADERS
    return isinstance(node, ast.Name) and (node.id in aliases or node.id in _LOADERS)


def _escaped_loaders(tree, aliases, modules):
    """A _DYNAMIC for each loader the scan cannot follow to its call: one
    named other than as the callee of a call (assigned, passed as a value), and
    one fetched by getattr from a loader's module by a loader's name or by a
    name the scan cannot read."""
    callees = {id(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
    for node in ast.walk(tree):
        if id(node) in callees or not isinstance(getattr(node, "ctx", None), ast.Load):
            continue
        if _names_a_loader(node, aliases):
            yield _DYNAMIC
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
        ):
            continue
        owner = node.args[0]
        while isinstance(owner, ast.Attribute):
            owner = owner.value
        if isinstance(owner, ast.Name) and owner.id in modules:
            attr = _literal(node.args[1], {})
            if attr is None or attr in _LOADERS:
                yield _DYNAMIC


def _imported_names(path):
    """Every module name *path* imports, each dotted part on its own, and the
    names a `from` import takes, so `from scripts import model_budget` names
    model_budget; a module importlib or runpy loads by a name or a `.py` path
    spelled whole in literals is named the same way, and a load the scan
    cannot read, or a loader it cannot follow to its call, yields _DYNAMIC."""
    tree = ast.parse(path.read_text("utf-8"))
    assigned = {
        target.id: node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    aliases, modules = _loader_aliases(tree)
    yield from _escaped_loaders(tree, aliases, modules)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield from alias.name.split(".")
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield from node.module.split(".")
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.Call):
            yield from _dynamic_names(node, assigned, aliases)


def _names(path, root):
    """*path*'s imported names, with _DYNAMIC dropped when a _DYNAMIC_LOADS
    row excuses the file."""
    names = set(_imported_names(path))
    if path.relative_to(root).as_posix() in _DYNAMIC_LOADS:
        names.discard(_DYNAMIC)
    return names


def _module_name(path):
    return path.parent.name if path.name == "__init__.py" else path.stem


def _agent_reaching_names(root=None):
    """The agent packages, and every module or package under scripts/, mcp/
    and api/ that reaches one through any chain of imports: an entry point
    that reaches models through a helper, a helper's helper or a package
    builds a model as surely as one that imports models itself. The set
    grows until no module joins it. A load the scan cannot name counts as
    reaching unless a _DYNAMIC_LOADS row excuses its file."""
    root = _ROOT if root is None else root
    modules = [
        (_module_name(path), _names(path, root))
        for top in _ENTRY_TOPS
        for path in sorted((root / top).rglob("*.py"))
    ]
    reaching = set(_AGENT_PACKAGES) | {_DYNAMIC}
    grew = True
    while grew:
        joined = {name for name, imports in modules if imports & reaching}
        grew = not joined <= reaching
        reaching |= joined
    return reaching


def _imports_an_agent_package(path, reaching, root=None):
    return bool(_names(path, _ROOT if root is None else root) & reaching)


# Each shape a doer can reach models through, as the files that build it: the
# doer is the last file, and the scan must count it as reaching.
_REACH_SHAPES = {
    "a sibling under scripts/jobs/": {
        "scripts/jobs/probe_helper.py": "import models\n",
        "scripts/jobs/probe_doer.py": "import probe_helper\n",
    },
    "a helper's helper": {
        "scripts/probe_low.py": "from models import get_model\n",
        "scripts/probe_mid.py": "import probe_low\n",
        "scripts/probe_doer.py": "import probe_mid\n",
    },
    "a package": {
        "scripts/probe_pkg/__init__.py": "import models\n",
        "scripts/probe_doer.py": "from probe_pkg import thing\n",
    },
    "a from-import of a helper": {
        "scripts/probe_helper.py": "import runtimes\n",
        "scripts/probe_doer.py": "from scripts import probe_helper\n",
    },
    "importlib.import_module of a helper": {
        "scripts/probe_helper.py": "import evals\n",
        "scripts/probe_doer.py": (
            "import importlib\nhelper = importlib.import_module('scripts.probe_helper')\n"
        ),
    },
    "__import__ of a package": {
        "scripts/probe_doer.py": "models = __import__('models')\n",
    },
    "a helper loaded by its file path": {
        "scripts/probe_helper.py": "import agents\n",
        "scripts/probe_doer.py": (
            "import importlib.util, os\n"
            "_HELPER = os.path.join(os.path.dirname(__file__), 'probe_helper.py')\n"
            "spec = importlib.util.spec_from_file_location('helper', _HELPER)\n"
        ),
    },
    "a load whose module the scan cannot name": {
        "scripts/probe_doer.py": (
            "import importlib, sys\nimportlib.import_module(sys.argv[1])\n"
        ),
    },
    "a literal prefix joined to a name the scan cannot read": {
        "scripts/probe_doer.py": (
            "import importlib, sys\nimportlib.import_module('scripts.' + sys.argv[1])\n"
        ),
    },
    "an f-string around a name the scan cannot read": {
        "scripts/probe_doer.py": (
            "import importlib, sys\nimportlib.import_module(f'{sys.argv[1]}.backend')\n"
        ),
    },
    "a from-list the scan cannot read": {
        "scripts/probe_doer.py": (
            "import sys\n__import__('scripts', fromlist=[sys.argv[1]])\n"
        ),
    },
    "a from-list that is not a literal list": {
        "scripts/probe_doer.py": (
            "import sys\n__import__('scripts', fromlist=sys.argv[1:])\n"
        ),
    },
    "a directory the scan cannot read inside a literal path": {
        "scripts/probe_doer.py": (
            "import os, runpy, sys\nrunpy.run_path(os.path.join(os.path.dirname("
            "__file__), sys.argv[1], 'run.py'))\n"
        ),
    },
    "import_module under another name": {
        "scripts/probe_doer.py": (
            "import sys\nfrom importlib import import_module as load\n"
            "load(sys.argv[1])\n"
        ),
    },
    "import_module assigned to a name": {
        "scripts/probe_doer.py": (
            "import importlib, sys\nload = importlib.import_module\nload(sys.argv[1])\n"
        ),
    },
    "import_module fetched by getattr": {
        "scripts/probe_doer.py": (
            "import importlib, sys\ngetattr(importlib, 'import_module')(sys.argv[1])\n"
        ),
    },
    "an imported import_module passed as a value": {
        "scripts/probe_doer.py": (
            "import sys\nfrom importlib import import_module\n"
            "list(map(import_module, sys.argv[1:]))\n"
        ),
    },
    "a loader fetched by a getattr the scan cannot read": {
        "scripts/probe_doer.py": (
            "import runpy, sys\ngetattr(runpy, sys.argv[1])(sys.argv[2])\n"
        ),
    },
    "import_module passed as a value": {
        "scripts/probe_doer.py": (
            "import importlib, sys\nlist(map(importlib.import_module, sys.argv[1:]))\n"
        ),
    },
    "an agent package's __init__ run by its file path": {
        "scripts/probe_doer.py": (
            "import os, runpy\nrunpy.run_path(os.path.join(os.path.dirname(__file__),"
            " '..', 'models', '__init__.py'))\n"
        ),
    },
    "a literal file name under a directory the scan cannot read": {
        "scripts/probe_doer.py": (
            "import os, runpy, sys\nrunpy.run_path(os.path.join(sys.argv[1], 'x.py'))\n"
        ),
    },
    "a file path the scan cannot read": {
        "scripts/probe_doer.py": (
            "import os, runpy, sys\nrunpy.run_path(os.path.join(os.path.dirname("
            "__file__), sys.argv[1] + '.py'))\n"
        ),
    },
}


@pytest.mark.parametrize("shape", sorted(_REACH_SHAPES))
def test_a_doer_reaching_models_through_any_import_chain_is_seen(tmp_path, shape):
    files = _REACH_SHAPES[shape]
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, "utf-8")
    doer = tmp_path / list(files)[-1]
    reaching = _agent_reaching_names(tmp_path)
    assert _imports_an_agent_package(doer, reaching, tmp_path), shape


# Each way a doer can load a helper that reaches no agent package, written
# whole in literals, so the scan names the helper instead of counting the load
# as one it cannot read.
_QUIET_SHAPES = {
    "a plain import": "import probe_helper\n",
    "a name joined from two literals": (
        "import importlib\nimportlib.import_module('scripts.' + 'probe_helper')\n"
    ),
    "a module-level name bound to a literal": (
        "import importlib\n_NAME = 'scripts.probe_helper'\n"
        "importlib.import_module(_NAME)\n"
    ),
    "a literal file path under the doer's directory": (
        "import os, runpy\nrunpy.run_path(os.path.join(os.path.dirname(__file__),"
        " 'probe_helper.py'))\n"
    ),
}


@pytest.mark.parametrize("shape", sorted(_QUIET_SHAPES))
def test_a_doer_reaching_no_agent_package_is_not_seen(tmp_path, shape):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/probe_helper.py").write_text("import json\n", "utf-8")
    doer = tmp_path / "scripts/probe_doer.py"
    doer.write_text(_QUIET_SHAPES[shape], "utf-8")
    assert not _imports_an_agent_package(
        doer, _agent_reaching_names(tmp_path), tmp_path
    )


def test_every_entry_point_that_builds_a_model_or_runtime_is_held():
    """A new doer is not covered by the parametrized cases above until it is
    named here, so the class is held, not the four CLIs that exist today."""
    reaching = _agent_reaching_names()
    entries = {
        str(path.relative_to(_ROOT))
        for top in _ENTRY_TOPS
        for path in (_ROOT / top).rglob("*.py")
        if "finish(main(" in path.read_text("utf-8")
        and _imports_an_agent_package(path, reaching)
    }
    held = {
        str(Path(module.__file__).resolve().relative_to(_ROOT))
        for module, *_rest in _CLIS.values()
    } | set(_HELD_ELSEWHERE)
    assert entries, "the scan found no entry point, so it checked nothing"
    assert entries == held, (sorted(entries - held), sorted(held - entries))


@pytest.mark.parametrize("entry", sorted(_HELD_ELSEWHERE))
def test_each_entry_held_elsewhere_is_named_by_the_test_said_to_hold_it(entry):
    """A _HELD_ELSEWHERE row is a claim; the test file it names must exist and
    name the entry point's module, or the row excuses nothing."""
    holder = _ROOT / _HELD_ELSEWHERE[entry]
    assert holder.is_file(), holder
    assert Path(entry).stem in holder.read_text("utf-8"), (entry, holder)


@pytest.mark.parametrize("excused", sorted(_DYNAMIC_LOADS))
def test_each_excused_dynamic_load_is_still_one_the_scan_cannot_name(excused):
    """A _DYNAMIC_LOADS row is a claim; once its file no longer has a load the
    scan cannot name, the row excuses nothing and must go."""
    assert _DYNAMIC in set(_imported_names(_ROOT / excused)), excused


def test_a_load_by_literal_name_or_path_is_named_not_counted_as_unknown():
    """config_loader and child_env load a module by a literal path; the scan
    names it, so neither needs a _DYNAMIC_LOADS row."""
    for rel in ("scripts/config_loader.py", "scripts/child_env.py"):
        names = set(_imported_names(_ROOT / rel))
        assert _DYNAMIC not in names, rel
    assert "config_loader" in set(_imported_names(_ROOT / "scripts/child_env.py"))
