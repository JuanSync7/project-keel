"""
title: Integration — each exit code of the gate's two red-fact scripts, reached through the command line
kind: tests
layer: n/a
summary: scripts/gate_evidence.py and scripts/run_evals.py each run as a real child process, started by their command line in a scratch git repository with the allowlisted environment from scripts/child_env.py and never the parent's. Each script is driven to three ends: success, one usage refusal, and the member that names its own red fact (ExitCode.RED_RECORD: every goal passed and the record says fail; ExitCode.BACKEND_ABSENT: the live backend's port has nothing listening). A case asserts the exit status, read from the enum by member name, and for a failure the last stderr line split back into the three parts scripts/exit_codes.py `report` writes: what failed, the input it names, and the next step. The driver is called directly, not through make, because make flattens a failed recipe's status to 2. The two red facts end on different numbers, neither script can return the other's member (scripts/exit_code_table.py `read_script`), and a scratch copy of either script with the two members swapped is reported by the same judge, which is the proof this file can fail. No case reaches a live backend or spends on a model: the absent backend is absent. It does not judge the wording of a record or a report (tests/integration/test_gate_evidence_record.py, tests/integration/test_evals_live_stub.py).
@covers scripts/gate_evidence.py
@covers scripts/run_evals.py
"""

import collections
import json
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "tests"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import child_env  # noqa: E402
import exit_code_table  # noqa: E402
import exit_codes  # noqa: E402
import test_evals_gate as evals_gate  # noqa: E402
import test_gate_evidence_record as gate_record  # noqa: E402

import hermetic_git  # noqa: E402
from live_server import free_port, load_server_config  # noqa: E402

pytestmark = pytest.mark.integration

_SERVER = load_server_config(str(_ROOT))
_GATE_SCRIPT = "gate_evidence.py"
_EVAL_SCRIPT = "run_evals.py"
# The registry name of the adapter whose backend the absent case points at.
_ADAPTER = "openai-compatible"
_GATE = "verify"
# The members that each name one script's own red fact.
_RED_RECORD = "RED_RECORD"
_BACKEND_ABSENT = "BACKEND_ABSENT"
_SUCCESS = "SUCCESS"
_USAGE = "USAGE"

_GATE_USAGE_STEP = "call it as `gate_evidence.py --gate <token> -- <make> <goal>...`"

# One end a script is driven to. *member* is the ExitCode member's name; *what*
# and *next_step* are the first and last part of the stderr line, and *names*
# the fragments its middle part must hold (all three empty for a success,
# which reports nothing).
Case = collections.namedtuple("Case", "script prepare member what names next_step")
Scenario = collections.namedtuple("Scenario", "repo argv extra")
Run = collections.namedtuple("Run", "case scenario proc")


def _pin_the_interpreter(repo, env):
    """Commit this interpreter as the scratch makefile's PY. An outer make
    would hand `PY=` to the driver in MAKEFLAGS, which no child environment
    built by scripts/child_env.py may carry, so a driver started directly
    reads it from the makefile."""
    makefile = repo / "Makefile"
    text = makefile.read_text("utf-8")
    makefile.write_text("PY := %s\n%s" % (sys.executable, text), encoding="utf-8")
    out = gate_record._run(repo, env, "git", "commit", "-q", "-am", "pin PY")
    assert out.returncode == 0, out.stdout


def _gate_scenario(goals, gate=_GATE):
    def prepare(base):
        repo, env = gate_record._build(base)
        _pin_the_interpreter(repo, env)
        argv = ["--gate", gate, "--", "make"] + list(goals)
        return Scenario(repo, argv, dict(hermetic_git.git_env_vars(base / "work")))

    return prepare


def _eval_manifest(repo):
    path = repo / "config" / "project.json"
    return path, json.loads(path.read_text("utf-8"))


def _eval_scenario(mode, absent=False):
    def prepare(base):
        repo, _env = evals_gate.build_scratch(base)
        extra = dict(hermetic_git.git_env_vars(base / "work"))
        # urllib honours proxy variables; a loopback port must not be routed away.
        extra["no_proxy"] = extra["NO_PROXY"] = "*"
        if absent:
            _point_at_a_port_nothing_listens_on(repo)
        argv = ["--mode", mode, "--root", str(repo)]
        return Scenario(repo, argv, extra)

    return prepare


def _point_at_a_port_nothing_listens_on(repo):
    path, manifest = _eval_manifest(repo)
    host = _SERVER["host"]
    endpoint = "%s:%d" % (host, free_port(host))
    cases = [
        line
        for dataset in sorted((repo / manifest["evals"]["dataset_dir"]).iterdir())
        for line in dataset.read_text("utf-8").splitlines()
    ]
    assert cases, "the scratch project ships no eval case -- zero items"
    live = manifest["evals"]["live"]
    live["model"] = _ADAPTER
    live["max_calls"] = len(cases)
    live["model_options"] = {
        "base_url": "http://%s/v1" % endpoint,
        "model": "absent",
        "timeout": _SERVER["request_timeout_s"],
    }
    # The scratch project lists the host it is about to find absent, so the
    # run is not refused for naming an unlisted one before it can be absent.
    manifest["models"].setdefault("allowed_hosts", {})[_ADAPTER] = [endpoint]
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _evidence_dir():
    return gate_record._EVIDENCE["dir"]


def _eval_report(mode):
    return "%s/%s.json" % (evals_gate._CONFIG.report_dir, mode)


_CASES = {
    (_GATE_SCRIPT, "success"): Case(
        _GATE_SCRIPT, _gate_scenario(gate_record._SCRATCH_GOALS), _SUCCESS, "", (), ""
    ),
    # A goal that passes and writes no test report: nothing failed, and the
    # record is red.
    (_GATE_SCRIPT, "red-record"): Case(
        _GATE_SCRIPT,
        _gate_scenario(gate_record._SCRATCH_GOALS[:1]),
        _RED_RECORD,
        "gate_evidence: the evidence record is red though no goal failed",
        ("%s/%s.json" % (_evidence_dir(), _GATE), "no-test-report"),
        "read the record's `reasons`, fix what they name and run the gate again",
    ),
    (_GATE_SCRIPT, "usage"): Case(
        _GATE_SCRIPT,
        _gate_scenario(gate_record._SCRATCH_GOALS[:1], gate="BAD!"),
        _USAGE,
        "gate_evidence: refused before any goal ran",
        ("--gate", "BAD!"),
        _GATE_USAGE_STEP,
    ),
    (_EVAL_SCRIPT, "success"): Case(
        _EVAL_SCRIPT, _eval_scenario("replay"), _SUCCESS, "", (), ""
    ),
    (_EVAL_SCRIPT, "backend-absent"): Case(
        _EVAL_SCRIPT,
        _eval_scenario("live", absent=True),
        _BACKEND_ABSENT,
        "run_evals: the live backend is absent, so nothing was judged",
        (_eval_report("live"), "backend-absent"),
        "configure the model config/project.json `evals` names, then run it again",
    ),
    # The shipped config names no live model.
    (_EVAL_SCRIPT, "usage"): Case(
        _EVAL_SCRIPT,
        _eval_scenario("live"),
        _USAGE,
        "run_evals: the live run was refused",
        ("evals.live.model",),
        "correct config/project.json `evals` and run it again",
    ),
}
_SCRIPTS = (_GATE_SCRIPT, _EVAL_SCRIPT)
# The ends every script is driven to, beside the one that is its own red fact.
_SHARED_ENDS = ("success", "usage")
_OWN_END = {_GATE_SCRIPT: "red-record", _EVAL_SCRIPT: "backend-absent"}


def _start(scenario, script):
    """The script's own command line as a child, with the allowlisted
    environment plus what the scenario names: never the parent's."""
    return subprocess.run(
        [sys.executable, str(scenario.repo / "scripts" / script)] + scenario.argv,
        cwd=str(scenario.repo),
        env=child_env.build_child_env(extra=scenario.extra),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )


def _drive(case, base):
    scenario = case.prepare(base)
    return Run(case, scenario, _start(scenario, case.script))


def _name_of(status):
    try:
        return exit_codes.ExitCode(status).name
    except ValueError:
        return "no member"


def _message_parts(case, stderr):
    """The (what, on, next_step) the last stderr line splits back into, by the
    helper's own line format; None when the line is not the expected one."""
    lines = stderr.splitlines()
    if not lines:
        return None
    last = lines[-1]
    head, tail = case.what + ": ", "; " + case.next_step
    if not (last.startswith(head) and last.endswith(tail)):
        return None
    middle = last[len(head) : len(last) - len(tail)]
    if exit_codes._LINE % (case.what, middle, case.next_step) != last + "\n":
        return None
    return case.what, middle, case.next_step


def judge(run):
    """What is wrong with *run* as a list of findings; empty when the child
    exited with the case's member and reported it in three parts."""
    case, proc = run.case, run.proc
    wanted = exit_codes.ExitCode[case.member]
    where = "%s (%s)" % (case.script, case.member)
    findings = []
    if proc.returncode != int(wanted):
        findings.append(
            "%s: exited %s (%s), expected %d (%s)"
            % (where, proc.returncode, _name_of(proc.returncode), wanted, wanted.name)
        )
    if wanted is exit_codes.ExitCode.SUCCESS:
        return findings
    parts = _message_parts(case, proc.stderr)
    if parts is None:
        findings.append(
            "%s: the last stderr line is not `%s: <input>; %s`: %r"
            % (where, case.what, case.next_step, proc.stderr.splitlines()[-1:])
        )
        return findings
    blank = [part for part in parts if not part.strip()]
    if blank:
        findings.append("%s: a message part is blank: %r" % (where, parts))
    missing = [name for name in case.names if name not in parts[1]]
    if missing:
        findings.append(
            "%s: the input part %r does not name %s" % (where, parts[1], missing)
        )
    return findings


def _detail(run):
    return "stdout:\n%s\nstderr:\n%s" % (run.proc.stdout, run.proc.stderr)


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    """Every case driven once, each in its own scratch repository."""
    return {
        key: _drive(case, tmp_path_factory.mktemp("cli"))
        for key, case in sorted(_CASES.items())
    }


def test_the_cases_cover_every_script_at_every_end():
    wanted = {
        (script, end)
        for script in _SCRIPTS
        for end in _SHARED_ENDS + (_OWN_END[script],)
    }
    assert wanted, "no case -- zero items"
    assert set(_CASES) == wanted
    assert all(case.script == script for (script, _end), case in _CASES.items())
    # A failure case with nothing to compare its line with would pass any line.
    for key, case in _CASES.items():
        if case.member != _SUCCESS:
            assert case.what and case.names and case.next_step, key


@pytest.mark.parametrize("key", sorted(_CASES), ids="-".join)
def test_each_script_reaches_each_code_as_a_child_process(runs, key):
    run = runs[key]
    assert judge(run) == [], _detail(run)


def test_the_two_red_facts_end_on_different_numbers_and_no_script_can_return_the_others(
    runs,
):
    assert len(runs) == len(_CASES) == len(_SCRIPTS) * (len(_SHARED_ENDS) + 1)
    red = runs[(_GATE_SCRIPT, _OWN_END[_GATE_SCRIPT])].proc.returncode
    absent = runs[(_EVAL_SCRIPT, _OWN_END[_EVAL_SCRIPT])].proc.returncode
    assert red == exit_codes.ExitCode[_RED_RECORD]
    assert absent == exit_codes.ExitCode[_BACKEND_ABSENT]
    assert red != absent
    for script in _SCRIPTS:
        statuses = [
            run.proc.returncode for key, run in runs.items() if key[0] == script
        ]
        assert len(set(statuses)) == len(statuses), (script, statuses)

    members = exit_code_table.read_members(str(_ROOT))
    assert members, "the enum has no member -- zero items"
    returnable = {}
    for script in _SCRIPTS:
        reading = exit_code_table.read_script(
            str(_ROOT / "scripts" / script), "scripts/" + script, members
        )
        assert reading.findings == [], reading.findings
        returnable[script] = set(reading.names)
    assert _RED_RECORD in returnable[_GATE_SCRIPT]
    assert _BACKEND_ABSENT in returnable[_EVAL_SCRIPT]
    assert _BACKEND_ABSENT not in returnable[_GATE_SCRIPT]
    assert _RED_RECORD not in returnable[_EVAL_SCRIPT]


@pytest.mark.parametrize(
    "script, own, other",
    [
        (_GATE_SCRIPT, _RED_RECORD, _BACKEND_ABSENT),
        (_EVAL_SCRIPT, _BACKEND_ABSENT, _RED_RECORD),
    ],
    ids=[_GATE_SCRIPT, _EVAL_SCRIPT],
)
def test_swapping_the_two_members_in_one_script_is_seen_by_the_child(
    tmp_path, script, own, other
):
    """Fault injection: the scratch copy of a script returns the other script's
    member for its own red fact, and the judge the cases use says so."""
    case = _CASES[(script, _OWN_END[script])]
    scenario = case.prepare(tmp_path)
    path = scenario.repo / "scripts" / script
    text = path.read_text("utf-8")
    written, planted = "ExitCode." + own, "ExitCode." + other
    assert text.count(written) == 1, text.count(written)
    path.write_text(text.replace(written, planted), encoding="utf-8")
    run = Run(case, scenario, _start(scenario, script))
    findings = judge(run)
    assert len(findings) == 1, (findings, _detail(run))
    assert own in findings[0] and other in findings[0], findings
