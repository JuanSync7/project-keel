"""
title: Unit — launch (where a long script runs, decided from what is true now)
kind: tests
layer: n/a
summary: The launcher's decision core as pure functions, with every fact injected and no disk, process or network. Each row of the decision table decides and explains itself in one exact line that names no host and no absolute path. The host kind fails closed to shared for an absent, unreadable, malformed, empty or unmatched own-hosts file, and a farm job wins over a match. An unknown script length stays distinct from a short one, and only a run that succeeded can prove a script short. The launch key drops variable assignments and absolute paths. An unknown load or cpu count is not spare. After a farm submission a status passes through, falls back here when spare, or stops. Placeholder rendering takes only the closed set. The config loader refuses each malformed key by its path and loads keel's own block. The farm interface builds an argv adapter's submit words and environment from config alone and reads its reserved statuses; the none adapter is never asked to submit. A run record is made and read by one rule: a signal is spelled the shell's way, only a measured outcome carries seconds, an attempt that measured nothing keeps a measured record over the threshold, the durations text is whole canonical JSON with one entry per key, and a credential the environment holds reaches a launch only when config names it for that key. The launcher and long_scripts.py parse on the oldest supported interpreter and import only the standard library and their scripts/ siblings.
"""

import ast
import copy
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "tests"))
sys.path.insert(0, str(_ROOT / "tests" / "integration"))

import launch  # noqa: E402
import test_gate_scope as gate_scope  # noqa: E402

pytestmark = pytest.mark.unit

_LAUNCHER = _ROOT / "scripts" / "launch.py"
# The bare-name siblings the launcher may import: each is stdlib-only and
# 3.6-safe, which _old_python_safe walks into and checks for itself.
_SIBLINGS = {"child_env", "exit_codes", "git_tree"}
# A planted host name: placeholder only, never a real host.
_HOST = "h1.example.com"
_OWN = json.dumps({"own_hosts": ["*.example.com"]})
_ROOT_DIR = "/work/project"


def _manifest():
    """keel's own config/project.json, read once per test, so the tests judge
    the block that ships."""
    return json.loads((_ROOT / "config" / "project.json").read_text(encoding="utf-8"))


def _cfg(adapter=None, local_only=None, manifest=None):
    manifest = copy.deepcopy(manifest or _manifest())
    block = manifest["launcher"]
    if adapter is not None:
        block["farm"]["adapter"] = adapter
    if local_only is not None:
        block["local_only"] = local_only
    return launch.load_launcher_config(manifest)


def _argv_adapter(cfg):
    """The name of one shipped adapter of kind argv, read from config so the
    test names no vendor."""
    names = [n for n, a in sorted(cfg.adapters.items()) if a.kind == "argv"]
    assert names, "the shipped config has no argv adapter -- zero items"
    return names[0]


def _record(outcome, seconds, status=0, where="shared-host"):
    return {"outcome": outcome, "seconds": seconds, "status": status, "where": where}


# --- the decision table ---------------------------------------------------

_LISTED = "make verify"
_UNKNOWN = "make check-all"
_RECORDED = "pytest -m slow"
_SHORT = "make lint"


def _facts(host_case, length_case, cfg):
    """(host, length) as the pure functions derive them from planted facts."""
    host = {
        "in-farm-job": launch.host_kind(_HOST, None, True),
        "own": launch.host_kind(_HOST, _OWN, False),
        "shared": launch.host_kind(_HOST, None, False),
    }[host_case]
    seconds = cfg.long_after_seconds
    durations = {
        _RECORDED: _record("succeeded", seconds + 1),
        _SHORT: _record("succeeded", seconds),
    }
    key = {
        "long-listed": _LISTED,
        "long-recorded": _RECORDED,
        "unknown": _UNKNOWN,
        "short": _SHORT,
    }[length_case]
    return key, host, launch.script_length(key, cfg, durations)


# (host, length, local-only?, adapter kind) -> (where, the exact line). The
# line's farm part is filled in per adapter name, read from config.
_TABLE = [
    (
        "in-farm-job",
        "unknown",
        False,
        "argv",
        "here",
        "launch: run here: host in-farm-job (already inside a farm job); script "
        '"make check-all" unknown (never recorded); farm {adapter} (not used)',
    ),
    (
        "in-farm-job",
        "long-listed",
        False,
        "none",
        "here",
        "launch: run here: host in-farm-job (already inside a farm job); script "
        '"make verify" long-listed (listed in launcher.long_scripts); farm none '
        "(no farm configured)",
    ),
    (
        "own",
        "long-listed",
        False,
        "argv",
        "here",
        "launch: run here: host own (an own_hosts pattern matches this host); "
        'script "make verify" long-listed (listed in launcher.long_scripts); farm '
        "{adapter} (not used)",
    ),
    (
        "own",
        "unknown",
        False,
        "none",
        "here",
        "launch: run here: host own (an own_hosts pattern matches this host); "
        'script "make check-all" unknown (never recorded); farm none (no farm '
        "configured)",
    ),
    (
        "shared",
        "short",
        False,
        "argv",
        "here",
        'launch: run here: host shared (no own-hosts file); script "make lint" '
        "short (last run succeeded in 600 s <= 600 s); farm {adapter} (not used)",
    ),
    (
        "shared",
        "long-listed",
        True,
        "argv",
        "here-limited",
        "launch: run here limited (nice 10): host shared (no own-hosts file); "
        'script "make verify" long-listed (listed in launcher.long_scripts); farm '
        "{adapter} (not used: local-only, needs the license server)",
    ),
    (
        "shared",
        "unknown",
        False,
        "none",
        "here-limited",
        "launch: run here limited (nice 10): host shared (no own-hosts file); "
        'script "make check-all" unknown (never recorded); farm none (no farm '
        "configured)",
    ),
    (
        "shared",
        "long-recorded",
        False,
        "argv",
        "farm",
        "launch: submit to farm {adapter}: host shared (no own-hosts file); script "
        '"pytest -m slow" long-recorded (last run took 601 s > 600 s); farm '
        "{adapter} (submitting, wait up to 900 s)",
    ),
]


def test_each_branch_of_the_decision_table_decides_and_explains_itself():
    assert len(_TABLE) >= 6, "the decision table has too few rows -- zero items"
    seen = set()
    for host_case, length_case, local, kind, where, line in _TABLE:
        probe = _cfg()
        adapter = _argv_adapter(probe) if kind == "argv" else "none"
        local_only = {_LISTED: "needs the license server"} if local else {}
        cfg = _cfg(adapter=adapter, local_only=local_only)
        key, host, length = _facts(host_case, length_case, cfg)
        assert host[0] == host_case and length[0] == length_case, (host, length)
        decision = launch.decide(host, length, cfg, key)
        assert decision.where == where, (host_case, length_case, local, kind)
        said = launch.explain(decision, host, length)
        assert said == line.format(adapter=adapter), said
        assert "\n" not in said and _HOST not in said and _ROOT_DIR not in said
        seen.add(where)
    assert seen == {"here", "here-limited", "farm"}, seen


def test_explain_keeps_one_line_for_a_key_with_a_newline_or_a_quote():
    cfg = _cfg()
    key = launch.script_key(["python3", "-c", 'print("a")\nprint(1)'], _ROOT_DIR)
    host = launch.host_kind(_HOST, None, False)
    length = launch.script_length(key, cfg, {})
    said = launch.explain(launch.decide(host, length, cfg, key), host, length)
    assert "\n" not in said and "\r" not in said, said
    assert json.dumps(key) in said, said


def test_an_explicit_farm_state_replaces_the_derived_one():
    cfg = _cfg()
    host = launch.host_kind(_HOST, None, False)
    length = launch.script_length(_UNKNOWN, cfg, {})
    decision = launch.decide(host, length, cfg, _UNKNOWN)
    said = launch.explain(decision, host, length, "did not allocate within 900 s")
    assert said.endswith("farm none (did not allocate within 900 s)"), said


# --- after the farm ---------------------------------------------------------


class _NeverAllocates:
    """A farm that never allocates: every submission ends with the status the
    adapter reserves for "not allocated within the wait"."""

    def __init__(self, adapter):
        self.adapter = adapter

    def submit(self):
        return self.adapter.not_allocated_status


def test_after_the_farm_status_passes_through_falls_back_when_spare_or_stops():
    cfg = _cfg()
    adapter = cfg.adapters[_argv_adapter(cfg)]
    reserved = {adapter.not_allocated_status, adapter.farm_error_status}
    spare = launch.spare((0.1, 0.1, 0.1), 8, cfg.max_load_per_cpu)
    busy = launch.spare((7.0, 7.0, 7.0), 8, cfg.max_load_per_cpu)
    assert spare[0] is True and busy[0] is False
    statuses = [s for s in (0, 1, 2, 3, 130, 137, 250, 253) if s not in reserved]
    assert statuses, "no ordinary status to pass through -- zero items"
    for status in statuses:
        for measured in (spare, busy):
            assert launch.after_farm(status, adapter, measured) == "passthrough"
    status = _NeverAllocates(adapter).submit()
    assert launch.after_farm(status, adapter, spare) == "here-limited"
    assert launch.after_farm(status, adapter, busy) == "stop-no-capacity"
    unknown = launch.spare(None, 8, cfg.max_load_per_cpu)
    assert launch.after_farm(status, adapter, unknown) == "stop-no-capacity"
    for measured in (spare, busy):
        refused = launch.after_farm(adapter.farm_error_status, adapter, measured)
        assert refused == "farm-refused"


# --- host kind --------------------------------------------------------------

_SHARED_CASES = [
    (None, {}),
    ("{", {}),
    ("[]", {}),
    (json.dumps({"own_hosts": []}), {}),
    (json.dumps({"own_hosts": [1]}), {}),
    (json.dumps({"own_hosts": "*.example.com"}), {}),
    (json.dumps({"own_hosts": ["other.example.org"]}), {}),
    (_OWN, {"unreadable": True}),
]


def test_host_kind_fails_closed_to_shared():
    reasons = []
    for text, kwargs in _SHARED_CASES:
        kind, reason = launch.host_kind(_HOST, text, False, **kwargs)
        assert kind == "shared", (text, kwargs, reason)
        assert _HOST not in reason and "example" not in reason, reason
        reasons.append(reason)
    assert len(set(reasons)) >= 6, reasons
    assert launch.host_kind("", _OWN, False)[0] == "shared"
    assert launch.host_kind("H1.Example.COM", _OWN, False)[0] == "own"
    assert launch.host_kind("h1.example.com.", _OWN, False)[0] == "own"
    upper = json.dumps({"own_hosts": ["*.EXAMPLE.com"]})
    assert launch.host_kind(_HOST, upper, False)[0] == "own"
    assert launch.host_kind(_HOST, _OWN, True)[0] == "in-farm-job"
    assert launch.host_kind(_HOST, None, True)[0] == "in-farm-job"
    # A pattern language, chosen on purpose: `?` and `[...]` mean what fnmatch
    # says, and a pattern is never a substring search.
    assert (
        launch.host_kind(
            "box7.example.com", '{"own_hosts": ["box?.example.com"]}', False
        )[0]
        == "own"
    )
    assert (
        launch.host_kind("xbox7.example.com", '{"own_hosts": ["box7"]}', False)[0]
        == "shared"
    )


# --- script length ----------------------------------------------------------


def test_script_length_keeps_unknown_distinct_from_short():
    cfg = _cfg()
    limit = cfg.long_after_seconds
    listed = sorted(cfg.long_scripts)
    assert listed, "no listed script -- zero items"
    over = {"k": _record("succeeded", limit + 1)}
    assert launch.script_length(listed[0], cfg, {})[0] == "long-listed"
    assert launch.script_length("k", cfg, over)[0] == "long-recorded"
    at = launch.script_length("k", cfg, {"k": _record("succeeded", limit)})
    assert at[0] == "short", at
    assert launch.script_length("k", cfg, {})[0] == "unknown"
    incomplete = {"k": _record("incomplete", None, None)}
    assert launch.script_length("k", cfg, incomplete)[0] == "unknown"
    zero = launch.script_length("k", cfg, {"k": _record("succeeded", 0)})
    assert zero[0] == "short", zero
    # A run that did not succeed only bounds the duration from below: under the
    # threshold it proves nothing, over it the script is long.
    for outcome in ("failed", "interrupted"):
        quick = launch.script_length("k", cfg, {"k": _record(outcome, 5, 3)})
        assert quick[0] == "unknown", quick
        slow = launch.script_length("k", cfg, {"k": _record(outcome, limit + 1, 3)})
        assert slow[0] == "long-recorded", slow
    waited = {"k": _record("no-capacity", limit + 1, None, "farm")}
    assert launch.script_length("k", cfg, waited)[0] == "unknown"
    for bad in (
        "x",
        {"outcome": "succeeded"},
        _record("succeeded", -1),
        _record("succeeded", True),
        _record("won", 1),
    ):
        assert launch.script_length("k", cfg, {"k": bad})[0] == "unknown", bad
    malformed = launch.script_length("k", cfg, None)
    assert malformed[0] == "unknown" and malformed[1] != "never recorded", malformed


# --- the launch key ---------------------------------------------------------


def test_script_key_drops_assignments_and_absolute_paths():
    key = launch.script_key
    assert (
        key(["make", "PY=.venv/bin/python", "check-all"], _ROOT_DIR) == "make check-all"
    )
    assert key(["/usr/bin/make", "verify"], _ROOT_DIR) == "make verify"
    assert "s3cret" not in key(["make", "TOKEN=s3cret", "x"], _ROOT_DIR)
    assert (
        key(["pytest", "--basetemp=/tmp/x", "-m", "unit"], _ROOT_DIR)
        == "pytest --basetemp -m unit"
    )
    assert (
        key(["python3", _ROOT_DIR + "/scripts/x.py"], _ROOT_DIR)
        == "python3 scripts/x.py"
    )
    assert key(["python3", "/elsewhere/tool.py", "a"], _ROOT_DIR) == "python3 tool.py a"
    assert key(["python3", _ROOT_DIR + "x/y.py"], _ROOT_DIR) == "python3 y.py"
    # An assignment-shaped first word is the program, not a variable.
    assert key(["A=1"], _ROOT_DIR) == "A=1"


# --- spare compute ----------------------------------------------------------


def test_spare_treats_unknown_load_as_not_spare():
    spare = launch.spare
    for load, ncpu in (
        (None, 8),
        ((0.1, 0.1, 0.1), None),
        ((0.1, 0.1, 0.1), 0),
        ((0.1,), 8),
    ):
        verdict = spare(load, ncpu, 0.25)
        assert verdict == (False, "load unknown"), (load, ncpu, verdict)
    at, reason = spare((0.5, 2.0, 0), 8, 0.25)
    assert at is True, reason
    assert "0.25" in reason and "<=" in reason, reason
    over, reason = spare((0.5, 2.1, 0), 8, 0.25)
    assert over is False and "0.26" in reason and "0.25" in reason, reason


# --- placeholders -----------------------------------------------------------


def test_render_substitutes_only_the_closed_placeholder_set():
    values = {"cpus": 8}
    assert launch.render("--cpus-per-task={cpus}", values) == "--cpus-per-task=8"
    assert launch.render("--", values) == "--"
    for bad in ("{cpu}", "{0}", "{cpus.__class__}", "{}", "{cpus", "cpus}"):
        with pytest.raises(launch.LauncherConfigError) as refused:
            launch.render(bad, values)
        assert bad.strip("{}") in str(refused.value) or "brace" in str(refused.value), (
            refused.value
        )
    # The set is closed even when the caller holds a value for another name, so
    # a value passed by mistake cannot open a new placeholder.
    with pytest.raises(launch.LauncherConfigError, match="not one of"):
        launch.render("{home}", {"cpus": 8, "home": "/somewhere"})
    with pytest.raises(launch.LauncherConfigError, match="no value"):
        launch.render("{minutes}", values)


# --- the config loader ------------------------------------------------------


def _set(path, value):
    def edit(block):
        node = block
        for part in path[:-1]:
            node = node[part]
        node[path[-1]] = value

    return edit


def _drop(path):
    def edit(block):
        node = block
        for part in path[:-1]:
            node = node[part]
        del node[path[-1]]

    return edit


def _slurm(field, value):
    def edit(block):
        name = [
            n
            for n, a in sorted(block["farm"]["adapters"].items())
            if a["kind"] == "argv"
        ][0]
        block["farm"]["adapters"][name][field] = value

    return edit


_REFUSALS = [
    ("niceness 0", _set(("limited", "niceness"), 0), "limited.niceness"),
    ("niceness 20", _set(("limited", "niceness"), 20), "limited.niceness"),
    ("threshold 0", _set(("spare", "max_load_per_cpu"), 0), "spare.max_load_per_cpu"),
    (
        "threshold 65",
        _set(("spare", "max_load_per_cpu"), 65.0),
        "spare.max_load_per_cpu",
    ),
    ("wait 0", _set(("farm", "wait_seconds"), 0), "farm.wait_seconds"),
    ("long_after bool", _set(("long_after_seconds",), True), "long_after_seconds"),
    ("adapter not listed", _set(("farm", "adapter"), "nowhere"), "farm.adapter"),
    (
        "unknown kind",
        _set(("farm", "adapters", "none", "kind"), "poll"),
        "farm.adapters.none.kind",
    ),
    ("empty submit", _slurm("submit", []), "submit"),
    ("non-str submit", _slurm("submit", ["srun", 3]), "submit"),
    ("unknown placeholder", _slurm("submit", ["srun", "--x={user}"]), "submit"),
    ("unknown env placeholder", _slurm("env", {"X": "{home}"}), "env"),
    ("reserved statuses equal", _slurm("farm_error_status", 251), "farm_error_status"),
    (
        "reserved status 130",
        _slurm("not_allocated_status", 130),
        "not_allocated_status",
    ),
    ("reserved status 255", _slurm("farm_error_status", 255), "farm_error_status"),
    ("inside_env not a name", _slurm("inside_env", ["JOB ID"]), "inside_env"),
    (
        "size missing cpus",
        _drop(("long_scripts", "make verify", "cpus")),
        "long_scripts.make verify",
    ),
    ("size zero", _set(("default_size", "minutes"), 0), "default_size"),
    (
        "unknown model_adapter",
        _set(("credentials",), {"make eval": {"model_adapter": "nope", "names": []}}),
        "credentials.make eval.model_adapter",
    ),
    (
        "credential name shape",
        _set(
            ("credentials",), {"make eval": {"model_adapter": None, "names": ["A-B"]}}
        ),
        "credentials.make eval.names",
    ),
    (
        "blank local_only reason",
        _set(("local_only",), {"make eval": "  "}),
        "local_only.make eval",
    ),
    (
        "local_only reason on two lines",
        _set(("local_only",), {"make eval": "a\nb"}),
        "local_only.make eval",
    ),
    ("state path climbs out", _set(("durations_file",), "../d.json"), "durations_file"),
    (
        "state path absolute",
        _set(("own_hosts_file",), "/etc/hosts.json"),
        "own_hosts_file",
    ),
    ("missing key", _drop(("spare",)), "spare"),
    ("unknown key", _set(("spares",), {}), "spares"),
]


@pytest.mark.parametrize("name, edit, where", _REFUSALS, ids=[r[0] for r in _REFUSALS])
def test_load_launcher_config_refuses_each_malformed_key(name, edit, where):
    manifest = _manifest()
    edit(manifest["launcher"])
    with pytest.raises(launch.LauncherConfigError) as refused:
        launch.load_launcher_config(manifest)
    assert where in str(refused.value), (name, str(refused.value))


def test_the_shipped_block_loads_and_an_absent_block_is_refused():
    cfg = launch.load_launcher_config(_manifest())
    block = _manifest()["launcher"]
    assert cfg.farm_adapter == block["farm"]["adapter"] == "none"
    assert cfg.niceness == block["limited"]["niceness"]
    assert set(cfg.adapters) == set(block["farm"]["adapters"])
    manifest = _manifest()
    del manifest["launcher"]
    with pytest.raises(launch.LauncherConfigError) as refused:
        launch.load_launcher_config(manifest)
    assert "launcher" in str(refused.value)
    for bad in (None, [], "x"):
        with pytest.raises(launch.LauncherConfigError):
            launch.load_launcher_config(bad)


# --- the farm interface and the run record ----------------------------------


def _rendered(word, values):
    """*word* with each `{name}` replaced from *values*: the expectation, built
    from the config dict so no adapter value is repeated here as a literal."""
    for name, value in values.items():
        word = word.replace("{%s}" % name, str(value))
    return word


def test_the_slurm_adapter_builds_its_argv_and_env_from_config_only():
    name = _argv_adapter(_cfg())
    cfg = _cfg(adapter=name)
    farm = launch.make_farm(cfg)
    assert isinstance(farm, launch.Farm) and isinstance(farm, launch.ArgvFarm)
    assert farm.name == name
    raw = _manifest()["launcher"]["farm"]["adapters"][name]
    size = launch.size_for("make verify", cfg)
    assert size == cfg.long_scripts["make verify"]
    values = dict(size._asdict(), wait_seconds=cfg.wait_seconds)
    values.update(
        not_allocated_status=raw["not_allocated_status"],
        farm_error_status=raw["farm_error_status"],
    )
    argv = farm.submit_argv(size, cfg)
    assert type(argv) is list and all(isinstance(w, str) for w in argv), argv
    assert argv == [_rendered(w, values) for w in raw["submit"]]
    env = farm.submit_env_extra(size, cfg)
    assert env == {k: _rendered(v, values) for k, v in raw["env"].items()}
    # The one golden example, written out: the shipped entry at the size
    # launcher.long_scripts gives `make verify`.
    if name == "slurm":
        assert argv == [
            "srun",
            "--export=ALL",
            "--immediate=900",
            "--cpus-per-task=8",
            "--mem=16G",
            "--time=180",
            "--",
        ]
        assert env == {"SLURM_EXIT_IMMEDIATE": "251", "SLURM_EXIT_ERROR": "252"}

    # What a runner is handed: one list, the submit words then the command, and
    # never a shell string.
    host = launch.host_kind(_HOST, None, False)
    length = launch.script_length(_LISTED, cfg, {})
    decision = launch.decide(host, length, cfg, _LISTED)
    assert decision.where == "farm"
    handed = launch.command_for(decision, farm, cfg, ["make", "verify"])
    assert type(handed) is list and handed == argv + ["make", "verify"]
    here = decision._replace(where="here-limited")
    assert launch.command_for(here, farm, cfg, ["make", "verify"]) == [
        "make",
        "verify",
    ]
    assert launch.size_for(_UNKNOWN, cfg) == cfg.default_size

    adapter = cfg.adapters[name]
    assert farm.classify(0) == "ran" and farm.classify(-9) == "ran"
    assert farm.classify(adapter.not_allocated_status) == "not-allocated"
    assert farm.classify(adapter.farm_error_status) == "refused"
    assert set(launch.FARM_STATES) == {"ran", "not-allocated", "refused"}

    none = launch.make_farm(_cfg())
    assert isinstance(none, launch.NoFarm) and none.name == "none"
    for ask in (
        lambda: none.submit_argv(size, cfg),
        lambda: none.submit_env_extra(size, cfg),
        lambda: none.classify(0),
    ):
        with pytest.raises(ValueError):
            ask()


def test_a_run_record_is_made_and_read_by_one_rule():
    assert launch.run_outcome(0) == ("succeeded", 0)
    assert launch.run_outcome(3) == ("failed", 3)
    # A child killed by SIGINT reports -2, which the shell spells 130.
    assert launch.run_outcome(-2) == ("interrupted", 130)
    assert launch.run_outcome(130) == ("interrupted", 130)
    assert launch.run_outcome(-9) == ("failed", 137)
    for outcome in ("succeeded", "failed", "interrupted"):
        assert launch.recorded_seconds(_record(outcome, 0)) == 0
        assert launch.recorded_seconds(_record(outcome, 701)) == 701
    for unmeasured in (
        _record("incomplete", None, status=None),
        _record("no-capacity", None, status=None),
        _record("succeeded", None),
        {"outcome": "succeeded", "seconds": 5},
        _record("succeeded", -1),
        _record("succeeded", 1.5),
        None,
    ):
        assert launch.recorded_seconds(unmeasured) is None, unmeasured
    assert launch.run_where("here", "own") == "own-host"
    assert launch.run_where("here", "shared") == "shared-host"
    assert launch.run_where("here-limited", "shared") == "shared-host"
    assert launch.run_where("farm", "shared") == "farm"
    assert launch.run_where("here", "in-farm-job") == "farm"


def test_the_durations_text_is_whole_canonical_and_one_entry_per_key():
    old = {"make lint": _record("succeeded", 3), "make odd": {"x": 1}}
    new = _record("failed", 700, status=3)
    text = launch.durations_text(old, "make lint", new)
    data = json.loads(text)
    # The unreadable entry is dropped and the key's entry replaced, not appended.
    assert data == {"make lint": new}, data
    assert text == json.dumps(data, indent=2, sort_keys=True) + "\n"
    assert launch.durations_text(data, "make lint", new) == text
    both = json.loads(launch.durations_text(data, _UNKNOWN, _record("succeeded", 1)))
    assert sorted(both) == [_UNKNOWN, "make lint"]
    # A malformed file is rewritten whole with this run's entry only.
    assert json.loads(launch.durations_text(None, _UNKNOWN, new)) == {_UNKNOWN: new}
    # None drops the key: what restoring "no previous record" writes.
    assert json.loads(launch.durations_text(both, _UNKNOWN, None)) == data
    with pytest.raises(ValueError):
        launch.durations_text({}, _UNKNOWN, {"outcome": "won"})


def test_an_attempt_that_measured_nothing_keeps_a_record_that_proves_the_script_long():
    cfg = _cfg()
    limit = cfg.long_after_seconds
    proving = [
        _record("succeeded", limit + 1),
        _record("failed", limit + 1, status=3, where="farm"),
        _record("interrupted", limit + 1, status=130),
    ]
    not_proving = [
        None,
        _record("succeeded", limit),
        _record("failed", 5, status=3),
        _record("incomplete", None, status=None),
        _record("no-capacity", None, status=None, where="farm"),
        _record("succeeded", None),
        {"outcome": "succeeded", "seconds": limit + 1},
    ]
    for outcome in ("incomplete", "no-capacity"):
        for previous in proving:
            kept = launch.unmeasured_record(previous, cfg, outcome, "farm")
            # Kept as it was, so the measured duration still makes the script
            # long for the launcher and still reaches long_scripts.py.
            assert kept == previous, (outcome, previous, kept)
            assert launch.recorded_seconds(kept) == limit + 1
            assert launch.script_length("k", cfg, {"k": kept})[0] == "long-recorded"
        for previous in not_proving:
            made = launch.unmeasured_record(previous, cfg, outcome, "farm")
            assert made == _record(outcome, None, status=None, where="farm"), (
                outcome,
                previous,
                made,
            )
            assert launch.script_length("k", cfg, {"k": made})[0] == "unknown"
    for measured in ("succeeded", "failed", "interrupted", "won"):
        with pytest.raises(ValueError):
            launch.unmeasured_record(None, cfg, measured, "farm")


def test_a_credential_reaches_a_launch_only_when_config_names_it_for_that_key():
    known = {"OPENAI_API_KEY", "PROXY_URL"}
    env = ["HOME", "OPENAI_API_KEY", "PATH", "PROXY_URL"]
    assert launch.unlisted_credentials(env, known, ()) == [
        "OPENAI_API_KEY",
        "PROXY_URL",
    ]
    assert launch.unlisted_credentials(env, known, ("OPENAI_API_KEY",)) == ["PROXY_URL"]
    assert launch.unlisted_credentials(env, known, tuple(known)) == []
    assert launch.unlisted_credentials(["HOME", "PATH"], known, ()) == []


# --- the interpreter floor --------------------------------------------------


_LONG = _ROOT / "scripts" / "long_scripts.py"


@pytest.mark.parametrize(
    "path, siblings",
    [(_LAUNCHER, _SIBLINGS), (_LONG, _SIBLINGS | {"launch"})],
    ids=["launch", "long_scripts"],
)
def test_the_launcher_parses_on_the_oldest_supported_python_and_imports_only_the_stdlib(
    path, siblings
):
    assert path.is_file(), path
    assert gate_scope._too_new_syntax(path) == []
    assert gate_scope._old_python_safe(path)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.JoinedStr)]
    local = {
        name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for name in (
            [a.name for a in node.names]
            if isinstance(node, ast.Import)
            else [node.module]
        )
        if (_ROOT / "scripts" / (name + ".py")).is_file()
    }
    assert local and local <= siblings, local
    assert launch.__all__ and all(hasattr(launch, n) for n in launch.__all__)
