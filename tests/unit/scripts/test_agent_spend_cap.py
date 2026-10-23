"""
title: Unit — every agent CLI holds an --execute run to the model-call cap and says which model it chose
kind: tests
layer: n/a
summary: scripts/doc_review.py, scripts/refactor_practice.py, scripts/hooks/on_stop_doc_review.py and scripts/hooks/on_stop_triage.py each check, before the agent runs, that the run's upper bound of model calls (--max-chunks, --max-nodes, or the one call triage makes) is within config/project.json `agents.max_model_calls` (read through scripts/model_budget.py): a bound over the cap, or a negative bound that sets none, returns USAGE with the agent never called, a cap the config cannot give returns CONFIG, and a dry run is never refused, since it calls no model. An approved run hands the agent its bound as `max_model_calls`, the count its counted backend stops at; the agent stopping at that count (models.CallCapReached) returns FAILURE and a saved run the approval does not cover (models.RunNotApproved) returns USAGE, each naming what to do next. With --execute and no --model, each writes to stderr which model the registry default chose and why; with --model it writes no such line. A ConfigError the loader raises once the agent runs (NotSet or WrongValue) returns CONFIG with the loader line on stderr, dry run and --execute alike; two cases run the real chain against this checkout's config, changed as scripts/config_loader.py read returns it: triage on claude-code-headless with no models.timeout_seconds entry for it (PATH empty, so no CLI could start), and a doc_review dry run with runtimes.max_steps 0. Every entry point under scripts/, mcp/ and api/ that ends in finish(main()) and imports agents, evals, models or runtimes, or a scripts/ module that does (model_budget), must be one of these four or named in _HELD_ELSEWHERE with the test that holds it, and that test file must exist and name the entry point, so a new doer is not left out and a row excuses nothing it does not name. An entry point that reaches a package by importlib alone is not seen. Elsewhere the agent function is replaced by a recorder, so no model is built and nothing is written.
"""

import ast
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

pytestmark = pytest.mark.unit

_DOC = DocReviewReport(True, 0, 0, 0, (), (), (), "", False)
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


# Each entry point that builds a model or a runtime, and the test that holds
# it to a CONFIG refusal when the loader refuses a setting it reads.
_HELD_ELSEWHERE = {
    "mcp/qa_server.py": "tests/integration/test_mcp_servers.py",
    "scripts/run_evals.py": "tests/integration/test_evals_live_stub.py",
}
_AGENT_PACKAGES = ("agents", "evals", "models", "runtimes")


def _imported_names(path):
    for node in ast.walk(ast.parse(path.read_text("utf-8"))):
        if isinstance(node, ast.Import):
            yield from (alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module.split(".")[0]


def _agent_reaching_names():
    """The agent packages, and every scripts/ module that imports one, such
    as model_budget: an entry point that reaches models through a helper
    builds a model as surely as one that imports models itself."""
    helpers = {
        path.stem
        for path in (_ROOT / "scripts").glob("*.py")
        if set(_imported_names(path)) & set(_AGENT_PACKAGES)
    }
    return set(_AGENT_PACKAGES) | helpers


def _imports_an_agent_package(path, reaching):
    return bool(set(_imported_names(path)) & reaching)


def test_every_entry_point_that_builds_a_model_or_runtime_is_held():
    """A new doer is not covered by the parametrized cases above until it is
    named here, so the class is held, not the four CLIs that exist today."""
    reaching = _agent_reaching_names()
    entries = {
        str(path.relative_to(_ROOT))
        for top in ("scripts", "mcp", "api")
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
