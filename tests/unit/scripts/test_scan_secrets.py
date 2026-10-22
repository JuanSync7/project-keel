"""
title: Unit — scan_secrets (the secret scanner's adapter, driven through a stub scanner)
kind: tests
layer: n/a
summary: scripts/scan_secrets.py driven against a stub scanner, a small Python program named as config/project.json `secrets.scanner.name` gives and recorded through `write_record`, as the installer records it, which records its argv, environment and the config it was handed, writes the report a plan file tells it to and exits the plan's status. `write_record` records the scanner's absolute path, the configured rev and the program's sha256 in `secrets.scanner.record_file`, and a second write leaves the same bytes and the same modification time, which is the module's fixed point; `record_is_ignored` is false for a record file git would track. Every scan runs only the recorded program: a program named like the scanner first on PATH is never run, and an absent record, one naming another program or rev, a recorded path that is gone, and a program whose digest changed are each BACKEND_ABSENT naming `make secrets-install` before anything runs, in the staged scan and the history scan alike. A finding prints as `file:line rule commit` and the value the stub reports never appears on stdout or stderr. The scanner is handed fixed flags (redaction, the inline allow comments ignored, an empty ignore directory, a config that only extends the default rules, the configured finding status, a JSON report) and the allowlisted environment, so GITLEAKS_CONFIG and the repository context never reach it in the history scan, while the staged scan passes GIT_INDEX_FILE. A staged scan with nothing staged, a deletion alone included, judges nothing (NOTHING_JUDGED), and it reads the staged list from the index GIT_INDEX_FILE names, the one `git commit -a` fills. A scanner that exits 0 with findings, the finding status with none, any other status, or a report that is not a JSON list is BACKEND_ABSENT, never a pass and never FAILURE, which is a finding's alone; a git that ran and failed is USAGE. History options that reach no commit judge nothing (NOTHING_JUDGED). The hook's mode, `--staged-or-history`, scans the staged diff when something is staged and every commit when nothing is, and judges nothing with neither. A `secrets.scanner.name` the module has no adapter for is CONFIG in every mode before anything runs. The asserted name, record path, finding status, rev and log options are read from config/project.json through scripts/config_loader.py, never typed here. An exclusion removes exactly its file and rule; one the history scan does not use is a config fault. The scanner's own config or ignore file in the tree stops the scan before the scanner runs. A repository with no commit, or no repository, judges nothing (NOTHING_JUDGED), and a refused config value is CONFIG before the scanner runs.
"""

import hashlib
import json
import os
import random
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "tests"))

import config_loader  # noqa: E402
import scan_secrets  # noqa: E402
from exit_codes import ExitCode  # noqa: E402

import hermetic_git  # noqa: E402

pytestmark = pytest.mark.unit

_BLOCK = ("secrets", "scanner")


def _scanner_config():
    """keel's secrets.scanner block, which the fixture copies into each
    project, so a test reads every value it asserts and types none."""
    fields = (
        "history_log_opts",
        "leak_exit_code",
        "name",
        "record_file",
        "refused_files",
        "rev",
    )
    keys = config_loader.rows(*[_BLOCK + (f,) for f in fields])
    got = config_loader.resolve(
        config_loader.read(str(_ROOT)), keys, config_loader.CONFIG_FILE
    )
    return {path[-1]: value for path, value in got.items()}


_CFG = _scanner_config()
_NAME = _CFG["name"]
_RECORD = _CFG["record_file"]
_LEAK = _CFG["leak_exit_code"]

# The stub stands in for the scanner: it records what it was handed and does
# what plan.json beside it says, so a test can make the scanner lie.
_STUB = """#!%s
import json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "plan.json")) as fh:
    plan = json.load(fh)
argv = sys.argv[1:]
call = {"argv": argv, "env": dict(os.environ), "cwd": os.getcwd()}
if "--config" in argv:
    with open(argv[argv.index("--config") + 1]) as fh:
        call["config"] = fh.read()
if "--gitleaks-ignore-path" in argv:
    call["ignore_dir"] = sorted(os.listdir(argv[argv.index("--gitleaks-ignore-path") + 1]))
with open(os.path.join(here, "calls.jsonl"), "a") as fh:
    fh.write(json.dumps(call) + "\\n")
if "--report-path" in argv and "report" in plan:
    with open(argv[argv.index("--report-path") + 1], "w") as fh:
        fh.write(plan["report"])
sys.stderr.write(plan.get("stderr", ""))
sys.exit(plan.get("rc", 0))
"""


def _planted_value():
    # Built at run time, so no committed file holds a credential-shaped string.
    rng = random.Random(11)
    return "".join(rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ234567") for _ in range(24))


def _git(repo, env, *argv):
    subprocess.run(
        ["git", *argv], cwd=str(repo), env=env, check=True, capture_output=True
    )


class _Project:
    def __init__(self, root, stub_dir, env):
        self.root = root
        self.stub_dir = stub_dir
        self.env = env

    def plan(self, rc=0, findings=None, report=None, stderr=""):
        plan = {"rc": rc, "stderr": stderr}
        if report is not None:
            plan["report"] = report
        elif findings is not None:
            plan["report"] = json.dumps(findings)
        (self.stub_dir / "plan.json").write_text(json.dumps(plan), encoding="utf-8")

    def calls(self):
        path = self.stub_dir / "calls.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines()]

    def scanner(self, **values):
        path = self.root / "config" / "project.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["secrets"]["scanner"].update(values)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def run(self, *argv):
        return scan_secrets.main(list(argv), root=str(self.root))

    def record(self):
        """Record the stub as the installed scanner, as the installer does."""
        root = str(self.root)
        cfg = scan_secrets.settings(root)
        return scan_secrets.write_record(root, cfg, str(self.stub_dir / _NAME))

    def stage(self, rel="staged.txt", text="staged\n"):
        """Write *rel* and stage it, so the staged diff holds one file."""
        (self.root / rel).write_text(text, encoding="utf-8")
        _git(self.root, self.env, "add", "--", rel)

    def commit_all(self, message="more"):
        _git(self.root, self.env, "add", "-A")
        _git(self.root, self.env, "commit", "-q", "-m", message)

    def head(self):
        return (
            subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(self.root),
                env=self.env,
                check=True,
                capture_output=True,
            )
            .stdout.decode()
            .strip()
        )


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A committed project with keel's config, its record file ignored, and the
    stub scanner recorded, never on PATH. The hermetic git environment is exported,
    because the module's own git calls copy GIT_CONFIG_* from here."""
    work = tmp_path / "work"
    work.mkdir()
    env = hermetic_git.git_env(work)
    for key, value in hermetic_git.git_env_vars(work).items():
        monkeypatch.setenv(key, value)
    root = tmp_path / "proj"
    (root / "config").mkdir(parents=True)
    shutil.copyfile(
        str(_ROOT / "config" / "project.json"), str(root / "config" / "project.json")
    )
    (root / ".gitignore").write_text(_RECORD + "\n", encoding="utf-8")
    (root / "app.txt").write_text("hello\n", encoding="utf-8")
    _git(root, env, "init", "-q")
    _git(root, env, "add", "-A")
    _git(root, env, "commit", "-q", "-m", "init")
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    stub = stub_dir / _NAME
    stub.write_text(_STUB % sys.executable, encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    proj = _Project(root, stub_dir, env)
    proj.plan(rc=0, findings=[])
    assert proj.record()
    return proj


def _finding(file="app.txt", line=3, rule="generic-api-key", commit=None):
    value = _planted_value()
    commit = "c" * 40 if commit is None else commit
    return {
        "RuleID": rule,
        "File": file,
        "StartLine": line,
        "Commit": commit,
        "Secret": value,
        "Match": "token = " + value,
        "Fingerprint": "%s:%s:%s:%d" % (commit, file, rule, line),
    }


# --- the record every scan runs ------------------------------------------


def test_the_record_holds_path_rev_and_digest_and_a_second_write_changes_nothing(
    project,
):
    record = project.root / _RECORD
    stub = project.stub_dir / _NAME
    data = json.loads(record.read_text(encoding="utf-8"))
    assert data == {
        "name": _NAME,
        "path": str(stub),
        "rev": _CFG["rev"],
        "sha256": hashlib.sha256(stub.read_bytes()).hexdigest(),
    }
    first, first_mtime = record.read_bytes(), record.stat().st_mtime_ns
    assert project.record() is False
    assert record.read_bytes() == first
    assert record.stat().st_mtime_ns == first_mtime


def test_a_record_file_git_would_track_is_not_ignored(project):
    cfg = scan_secrets.settings(str(project.root))
    assert scan_secrets.record_is_ignored(str(project.root), cfg)
    (project.root / ".gitignore").write_text("", encoding="utf-8")
    assert not scan_secrets.record_is_ignored(str(project.root), cfg)


def test_a_scanner_on_path_is_never_run_without_a_record(project, monkeypatch, capsys):
    """The commit hook and the history scan run one checked build: a program
    named like the scanner first on PATH is not it."""
    monkeypatch.setenv("PATH", str(project.stub_dir) + os.pathsep + os.environ["PATH"])
    (project.root / _RECORD).unlink()
    project.stage()
    for mode in ("--staged", "--history", "--staged-or-history"):
        assert project.run(mode) == ExitCode.BACKEND_ABSENT, mode
    assert project.calls() == []
    assert "make secrets-install" in capsys.readouterr().err


# --- every scan runs only the recorded program ---------------------------


def _no_record(project):
    (project.root / _RECORD).unlink()


def _other_name(project):
    record = project.root / _RECORD
    data = json.loads(record.read_text())
    data["name"] = _NAME + "-other"
    record.write_text(json.dumps(data))


def _other_rev(project):
    project.scanner(rev=_CFG["rev"] + "-other")


def _path_gone(project):
    record = project.root / _RECORD
    data = json.loads(record.read_text())
    data["path"] = str(project.stub_dir / "gone")
    record.write_text(json.dumps(data))


def _digest_changed(project):
    stub = project.stub_dir / _NAME
    stub.write_text(stub.read_text() + "# changed\n", encoding="utf-8")


@pytest.mark.parametrize(
    "spoil", [_no_record, _other_name, _other_rev, _path_gone, _digest_changed]
)
@pytest.mark.parametrize("mode", ["--history", "--staged"])
def test_a_scan_without_a_matching_record_is_backend_absent(
    project, capsys, spoil, mode
):
    project.stage()
    spoil(project)
    assert project.run(mode) == ExitCode.BACKEND_ABSENT
    assert project.calls() == []
    assert "make secrets-install" in capsys.readouterr().err


# --- what the scanner is handed --------------------------------------------


def test_history_hands_the_scanner_fixed_flags_and_the_allowlisted_env(
    project, monkeypatch
):
    monkeypatch.setenv("GITLEAKS_CONFIG", "/elsewhere/rules.toml")
    monkeypatch.setenv("GITLEAKS_CONFIG_TOML", "[allowlist]")
    monkeypatch.setenv("GIT_INDEX_FILE", str(project.root / ".git" / "index"))
    assert project.run("--history") == ExitCode.SUCCESS
    (call,) = project.calls()
    argv = call["argv"]
    assert argv[0] == "git" and argv[-1] == str(project.root), argv
    assert "--log-opts=" + " ".join(_CFG["history_log_opts"]) in argv, argv
    assert argv[argv.index("--exit-code") + 1] == str(_LEAK)
    assert argv[argv.index("--report-format") + 1] == "json"
    for flag in ("--redact", "--ignore-gitleaks-allow", "--no-banner"):
        assert flag in argv, (flag, argv)
    assert "--staged" not in argv
    assert call["config"] == "[extend]\nuseDefault = true\n"
    assert call["ignore_dir"] == []
    for name in ("GITLEAKS_CONFIG", "GITLEAKS_CONFIG_TOML", "GIT_INDEX_FILE"):
        assert name not in call["env"], name


def test_staged_passes_the_index_and_asks_for_the_staged_diff(project, monkeypatch):
    index = str(project.root / ".git" / "index")
    project.stage()
    monkeypatch.setenv("GIT_INDEX_FILE", index)
    monkeypatch.setenv("GITLEAKS_CONFIG", "/elsewhere/rules.toml")
    assert project.run("--staged") == ExitCode.SUCCESS
    (call,) = project.calls()
    argv = call["argv"]
    assert argv[0] == "git" and "--staged" in argv and "--pre-commit" in argv
    assert not [a for a in argv if a.startswith("--log-opts")], argv
    assert call["env"]["GIT_INDEX_FILE"] == index
    assert "GITLEAKS_CONFIG" not in call["env"]


def test_a_staged_scan_with_nothing_staged_judges_nothing(project, capsys):
    # pre-commit skips a hook when nothing it would scan is staged, so only a
    # hand-run scan meets this; an empty diff is not a clean one.
    assert project.run("--staged") == ExitCode.NOTHING_JUDGED
    assert project.calls() == []
    assert "git add" in capsys.readouterr().err
    _git(project.root, project.env, "rm", "-q", "app.txt")
    assert project.run("--staged") == ExitCode.NOTHING_JUDGED, "a deletion only"
    assert project.calls() == []


def test_the_staged_scan_judges_the_index_git_hands_the_hook(project, monkeypatch):
    # `git commit -a` and `git commit <path>` stage into a temporary index that
    # GIT_INDEX_FILE names, and leave the default index as it was.
    temporary = project.root / ".git" / "next-index"
    shutil.copyfile(str(project.root / ".git" / "index"), str(temporary))
    (project.root / "app.txt").write_text("changed\n", encoding="utf-8")
    env = dict(project.env, GIT_INDEX_FILE=str(temporary))
    _git(project.root, env, "add", "app.txt")
    assert project.run("--staged") == ExitCode.NOTHING_JUDGED, "the default index"
    monkeypatch.setenv("GIT_INDEX_FILE", str(temporary))
    assert project.run("--staged") == ExitCode.SUCCESS
    (call,) = project.calls()
    assert call["env"]["GIT_INDEX_FILE"] == str(temporary)


# --- findings -----------------------------------------------------------------


def test_a_finding_prints_file_line_rule_and_commit_never_the_value(project, capsys):
    commit = project.head()
    project.plan(rc=_LEAK, findings=[_finding(commit=commit)])
    assert project.run("--history") == ExitCode.FAILURE
    out, err = capsys.readouterr()
    assert out.splitlines() == ["app.txt:3 generic-api-key %s" % commit[:12]]
    value = _planted_value()
    assert value not in out and value not in err


def test_a_staged_finding_prints_without_a_commit(project, capsys):
    project.stage()
    project.plan(rc=_LEAK, findings=[_finding(commit="")])
    assert project.run("--staged") == ExitCode.FAILURE
    out, err = capsys.readouterr()
    assert out.splitlines() == ["app.txt:3 generic-api-key"]
    assert _planted_value() not in out + err


@pytest.mark.parametrize(
    "rc, report",
    [
        (0, json.dumps([_finding()])),
        (_LEAK, "[]"),
        (_LEAK, None),
        (1, None),
        (1, "[]"),
        (0, "{}"),
        (0, "not json"),
        (0, None),
    ],
    ids=[
        "clean-status-with-findings",
        "finding-status-with-none",
        "finding-status-without-a-report",
        "scanner-error-without-a-report",
        "scanner-error-with-an-empty-report",
        "report-not-a-list",
        "report-not-json",
        "clean-status-without-a-report",
    ],
)
def test_a_scanner_that_contradicts_itself_is_backend_absent(
    project, capsys, rc, report
):
    # Not FAILURE, which is a finding: a caller must tell "rotate a
    # credential" from "fix the scanner".
    project.plan(rc=rc, report=report, stderr="scanner said something\n")
    assert project.run("--history") == ExitCode.BACKEND_ABSENT
    out, err = capsys.readouterr()
    assert _planted_value() not in out + err
    # Named as the scanner's own fault, with its stderr, never as a plain
    # finding: a report the status contradicts is not a verdict.
    assert "scanner said something" in err and "candidate secret" not in err, err


# --- exclusions -----------------------------------------------------------------


def test_an_exclusion_removes_exactly_its_file_and_rule(project, capsys):
    project.scanner(
        exclusions={"tests/fixture.txt": {"generic-api-key": "a fake key on purpose"}}
    )
    project.plan(
        rc=_LEAK,
        findings=[
            _finding(file="tests/fixture.txt"),
            _finding(file="tests/fixture.txt", rule="aws-access-token"),
            _finding(file="app.txt"),
        ],
    )
    assert project.run("--history") == ExitCode.FAILURE
    out = capsys.readouterr().out.splitlines()
    assert [line.rsplit(" ", 1)[0] for line in out] == [
        "app.txt:3 generic-api-key",
        "tests/fixture.txt:3 aws-access-token",
    ]


def test_a_used_exclusion_leaves_a_clean_scan(project):
    project.scanner(
        exclusions={"tests/fixture.txt": {"generic-api-key": "a fake key on purpose"}}
    )
    project.plan(rc=_LEAK, findings=[_finding(file="tests/fixture.txt")])
    assert project.run("--history") == ExitCode.SUCCESS


def test_an_exclusion_the_history_scan_does_not_use_is_a_config_fault(project, capsys):
    project.scanner(exclusions={"gone.txt": {"generic-api-key": "was a fixture"}})
    project.plan(rc=0, findings=[])
    assert project.run("--history") == ExitCode.CONFIG
    assert "gone.txt" in capsys.readouterr().err


def test_an_unused_exclusion_does_not_fail_a_staged_scan(project):
    # A staged diff carries a few files; an exclusion for another is not stale.
    project.scanner(exclusions={"gone.txt": {"generic-api-key": "was a fixture"}})
    project.stage()
    assert project.run("--staged") == ExitCode.SUCCESS


# --- what stops a scan before it runs ---------------------------------------------


@pytest.mark.parametrize("name", _CFG["refused_files"])
@pytest.mark.parametrize("where", ["tracked-deep", "ignored-at-root"])
def test_the_scanners_own_config_or_ignore_file_stops_the_scan(
    project, capsys, name, where
):
    if where == "tracked-deep":
        (project.root / "sub").mkdir()
        (project.root / "sub" / name).write_text("x\n", encoding="utf-8")
        project.commit_all()
    else:
        with open(str(project.root / ".gitignore"), "a") as fh:
            fh.write(name + "\n")
        (project.root / name).write_text("x\n", encoding="utf-8")
    for mode in ("--history", "--staged"):
        assert project.run(mode) == ExitCode.CONFIG, mode
    assert project.calls() == []
    assert name in capsys.readouterr().err


@pytest.mark.parametrize(
    "values",
    [
        {"leak_exit_code": 1},
        {"leak_exit_code": 0},
        {"history_log_opts": ["--all --full-history"]},
        {"history_log_opts": []},
        {"exclusions": {"tests/*.txt": {"generic-api-key": "glob"}}},
        {"exclusions": {"./app.txt": {"generic-api-key": "unnormalised"}}},
        {"exclusions": {"../app.txt": {"generic-api-key": "outside"}}},
        {"exclusions": {"app.txt": {"generic-api-key": " "}}},
        {"exclusions": {"app.txt": {}}},
        {"refused_files": []},
        {"refused_files": ["sub/" + _CFG["refused_files"][0]]},
    ],
    ids=lambda values: json.dumps(values, sort_keys=True),
)
def test_a_refused_scanner_setting_is_config_before_the_scanner_runs(
    project, capsys, values
):
    project.scanner(**values)
    assert project.run("--history") == ExitCode.CONFIG
    assert project.calls() == []
    assert "secrets.scanner" in capsys.readouterr().err


@pytest.mark.parametrize("options", [["--max-count=0"], ["--author=nobody-wrote-this"]])
def test_history_options_that_reach_no_commit_judge_nothing(project, capsys, options):
    project.scanner(history_log_opts=options)
    assert project.run("--history") == ExitCode.NOTHING_JUDGED
    assert project.calls() == []
    assert "history_log_opts" in capsys.readouterr().err


def test_a_git_that_ran_and_failed_is_usage_never_a_finding(project, capsys):
    (project.root / ".git" / "HEAD").write_text("garbage\n", encoding="utf-8")
    for mode in ("--history", "--staged"):
        assert project.run(mode) == ExitCode.USAGE, mode
    assert project.calls() == []
    assert "git failed" in capsys.readouterr().err


@pytest.mark.parametrize("mode", ["--staged", "--history", "--staged-or-history"])
def test_a_scanner_name_with_no_adapter_is_config(project, capsys, mode):
    """This module holds one scanner's flags, so config naming another is a
    refusal before anything runs, not a scan that cannot be read."""
    other = _NAME + "-other"
    shutil.copyfile(str(project.stub_dir / _NAME), str(project.stub_dir / other))
    (project.stub_dir / other).chmod(0o755)
    project.scanner(name=other)
    project.stage()
    assert project.run(mode) == ExitCode.CONFIG
    assert project.calls() == []
    err = capsys.readouterr().err
    assert "secrets.scanner.name" in err and other in err, err


def test_the_hook_scans_the_history_when_nothing_is_staged(project, capsys):
    """`pre-commit run --all-files` runs the hook with nothing staged; the
    hook then judges every commit, with the recorded build, never zero files."""
    assert project.run("--staged-or-history") == ExitCode.SUCCESS
    (call,) = project.calls()
    assert "--staged" not in call["argv"], call["argv"]
    assert [a for a in call["argv"] if a.startswith("--log-opts=")], call["argv"]
    assert "nothing is staged" in capsys.readouterr().out
    project.stage()
    assert project.run("--staged-or-history") == ExitCode.SUCCESS
    assert "--staged" in project.calls()[-1]["argv"]


def test_the_hook_with_no_commit_and_nothing_staged_judges_nothing(project):
    shutil.rmtree(str(project.root / ".git"))
    _git(project.root, project.env, "init", "-q")
    assert project.run("--staged-or-history") == ExitCode.NOTHING_JUDGED
    assert project.calls() == []


def test_a_repository_with_no_commit_judges_nothing(project, tmp_path, capsys):
    shutil.rmtree(str(project.root / ".git"))
    _git(project.root, project.env, "init", "-q")
    assert project.run("--history") == ExitCode.NOTHING_JUDGED
    assert project.calls() == []
    assert "commit" in capsys.readouterr().err


def test_no_repository_judges_nothing(project, monkeypatch):
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(project.root.parent))
    shutil.rmtree(str(project.root / ".git"))
    for mode in ("--history", "--staged"):
        assert project.run(mode) == ExitCode.NOTHING_JUDGED, mode
    assert project.calls() == []


def test_no_mode_or_two_modes_is_usage(project):
    assert project.run() == ExitCode.USAGE
    assert project.run("--history", "--staged") == ExitCode.USAGE
    assert project.run("--staged", "--staged-or-history") == ExitCode.USAGE
