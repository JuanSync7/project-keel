"""
title: Integration — the replayed eval gate, run as a real CLI over a scratch repository
kind: tests
layer: n/a
summary: A scratch git repository carrying keel's evals/, models/, agents/triage, the eval CLI and its script siblings, config/ and .gitignore runs scripts/run_evals.py --mode replay as a child process. Two runs on the same tree exit 0 and write byte-identical reports with result pass under config/project.json `evals.report_dir`, and leave what git lists unchanged (the writer's rerun_proof). The shipped dataset uses every scorer in evals.SCORERS and every doer in evals.DOERS. Each red twin is red with its own exit code: a recorded response that fails its scorer or a prompt that changed is a fail (exit 1); a stale response hash, an empty dataset, no dataset file, an unknown scorer, an id repeated across two suites and a stray file in the dataset directory are refused (exit 2). A report_dir git does not ignore is refused before anything is written, as is one whose first component is a symlink to a directory outside the project (in replay and live mode, with and without git, and when the `evals` block is itself refused) and a report temporary file that is a symlink, each leaving the outside files as they were, a red run replaces an earlier green report, and a refused `evals` block (a bad value or an unknown key) removes the earlier report, twice over, rather than leave it reading pass.
@covers scripts/run_evals.py
"""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "tests"))
sys.path.insert(0, str(_ROOT / "scripts"))

import git_tree  # noqa: E402
from evals import DOERS, SCORERS, load_config, load_suites  # noqa: E402

import hermetic_git  # noqa: E402

pytestmark = pytest.mark.integration

_CONFIG = load_config(_ROOT)
# What the CLI imports when it runs in a project: the harness, the doers and
# backends it drives, the CLI and the stdlib siblings git_tree needs.
_TREES = ("evals", "models", "agents/triage", "config")
_SCRIPTS = ("run_evals.py", "git_tree.py", "child_env.py")
_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc")


def _git(repo, env, *argv):
    out = subprocess.run(
        ("git",) + argv,
        cwd=str(repo),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    assert out.returncode == 0, out.stdout
    return out.stdout


def build_scratch(base):
    """A committed scratch repository holding the eval gate; (repo, env)."""
    work = base / "work"
    work.mkdir()
    env = hermetic_git.git_env(work)
    repo = base / "repo"
    repo.mkdir()
    for tree in _TREES:
        shutil.copytree(str(_ROOT / tree), str(repo / tree), ignore=_IGNORE)
    (repo / "scripts").mkdir()
    for name in _SCRIPTS:
        shutil.copy(str(_ROOT / "scripts" / name), str(repo / "scripts" / name))
    shutil.copy(str(_ROOT / ".gitignore"), str(repo / ".gitignore"))
    _git(repo, env, "init", "-q")
    _git(repo, env, "add", "-A")
    _git(repo, env, "commit", "-q", "-m", "init")
    return repo, env


def run_cli(repo, env, mode="replay"):
    return subprocess.run(
        [
            sys.executable,
            str(repo / "scripts" / "run_evals.py"),
            "--mode",
            mode,
            "--root",
            str(repo),
        ],
        cwd=str(repo),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )


def report_path(repo, mode="replay"):
    return repo / _CONFIG.report_dir / ("%s.json" % mode)


def read_report(repo, mode="replay"):
    return json.loads(report_path(repo, mode).read_text("utf-8"))


def _sha(text):
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _dataset_files(repo):
    return sorted((repo / _CONFIG.dataset_dir).iterdir())


def _cases(path):
    return [json.loads(line) for line in path.read_text("utf-8").splitlines()]


def _write_cases(path, cases):
    path.write_text(
        "".join(
            json.dumps(c, sort_keys=True, separators=(",", ":")) + "\n" for c in cases
        ),
        encoding="utf-8",
    )


def test_replay_over_the_tree_is_green_and_a_fixed_point(tmp_path):
    repo, env = build_scratch(tmp_path)
    before = git_tree.tree_snapshot(str(repo))
    first = run_cli(repo, env)
    assert first.returncode == 0, first.stdout
    text = report_path(repo).read_bytes()
    second = run_cli(repo, env)
    assert second.returncode == 0, second.stdout
    assert report_path(repo).read_bytes() == text
    assert git_tree.tree_snapshot(str(repo)) == before
    report = json.loads(text.decode("utf-8"))
    assert (report["result"], report["reasons"], report["mode"]) == (
        "pass",
        [],
        "replay",
    )
    assert (report["calls"], report["model"]) == (0, None)
    assert report["suites"] and all(s["passed"] == s["total"] for s in report["suites"])
    assert str(tmp_path) not in text.decode("utf-8")


def test_the_shipped_dataset_uses_every_scorer_and_doer():
    suites = load_suites(_CONFIG, _ROOT)
    cases = [c for s in suites for c in s.cases]
    assert cases
    assert {c.scorer_name for c in cases} == set(SCORERS)
    assert {c.doer for c in cases} == set(DOERS)


def _fail_first(repo):
    """Record a response the first case's scorer rejects (hash kept true)."""
    path = _dataset_files(repo)[0]
    cases = _cases(path)
    scorer = SCORERS[cases[0]["scorer"]["name"]]
    assert scorer.score("", cases[0]["scorer"]["params"])[0] is False
    cases[0]["recorded"]["response"] = ""
    cases[0]["recorded"]["sha256"] = _sha("")
    _write_cases(path, cases)
    return cases[0]["id"]


def _stale_prompt(repo):
    path = _dataset_files(repo)[0]
    cases = _cases(path)
    cases[0]["input"]["text"] += " (edited)"
    _write_cases(path, cases)
    return cases[0]["id"]


def _stale_hash(repo):
    path = _dataset_files(repo)[0]
    cases = _cases(path)
    cases[0]["recorded"]["response"] += "!"
    _write_cases(path, cases)


def _empty(repo):
    _dataset_files(repo)[0].write_text("", encoding="utf-8")


def _no_files(repo):
    for path in _dataset_files(repo):
        path.unlink()


def _unknown_scorer(repo):
    path = _dataset_files(repo)[0]
    cases = _cases(path)
    cases[0]["scorer"]["name"] = "judge"
    _write_cases(path, cases)


def _duplicate_across_suites(repo):
    first = _dataset_files(repo)[0]
    shutil.copy(str(first), str(first.parent / "zz-copy.jsonl"))


def _stray_file(repo):
    (repo / _CONFIG.dataset_dir / "README.txt").write_text("notes\n", encoding="utf-8")


@pytest.mark.parametrize(
    "fault, code, result, reasons, case_outcome",
    [
        (_fail_first, 1, "fail", ["below-threshold"], "fail"),
        (_stale_prompt, 1, "fail", ["below-threshold", "stale-recording"], "stale"),
        (_stale_hash, 2, "refused", ["refused"], None),
        (_empty, 2, "refused", ["refused"], None),
        (_no_files, 2, "refused", ["refused"], None),
        (_unknown_scorer, 2, "refused", ["refused"], None),
        (_duplicate_across_suites, 2, "refused", ["refused"], None),
        (_stray_file, 2, "refused", ["refused"], None),
    ],
    ids=lambda v: v.__name__.strip("_") if callable(v) else None,
)
def test_a_failing_recording_reddens_the_gate(
    tmp_path, fault, code, result, reasons, case_outcome
):
    repo, env = build_scratch(tmp_path)
    case_id = fault(repo)
    out = run_cli(repo, env)
    assert out.returncode == code, out.stdout
    report = read_report(repo)
    assert (report["result"], report["reasons"]) == (result, reasons), report
    if case_outcome is not None:
        outcomes = {c["id"]: c["outcome"] for s in report["suites"] for c in s["cases"]}
        assert outcomes[case_id] == case_outcome, outcomes
    else:
        assert report["suites"] == [] and report["detail"], report
    if fault is _duplicate_across_suites:
        assert "zz-copy.jsonl" in report["detail"], report["detail"]
        assert _dataset_files(repo)[0].name in report["detail"], report["detail"]


def test_report_guard_and_stale_green_report(tmp_path):
    repo, env = build_scratch(tmp_path)
    assert run_cli(repo, env).returncode == 0
    assert read_report(repo)["result"] == "pass"
    _fail_first(repo)
    assert run_cli(repo, env).returncode == 1
    assert read_report(repo)["result"] == "fail"

    manifest_path = repo / "config" / "project.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    manifest["evals"]["report_dir"] = "evals/reports"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    out = run_cli(repo, env)
    assert out.returncode == 2, out.stdout
    assert "evals.report_dir" in out.stdout and "ignored" in out.stdout, out.stdout
    assert not (repo / "evals" / "reports").exists()


def _set_manifest(repo, key, value):
    path = repo / "config" / "project.json"
    manifest = json.loads(path.read_text("utf-8"))
    manifest["evals"][key] = value
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


@pytest.mark.parametrize("key, value", [("threshold", 2), ("extra", 1)])
def test_a_refused_eval_config_leaves_no_green_report(tmp_path, key, value):
    repo, env = build_scratch(tmp_path)
    assert run_cli(repo, env).returncode == 0
    assert read_report(repo)["result"] == "pass"
    _set_manifest(repo, key, value)
    for attempt in range(2):
        out = run_cli(repo, env)
        assert out.returncode == 2, out.stdout
        assert "evals." in out.stdout, out.stdout
        assert not report_path(repo).exists(), out.stdout
        assert ("removed" in out.stdout) is (attempt == 0), out.stdout


def test_a_refused_live_config_removes_the_earlier_candidates(tmp_path):
    repo, env = build_scratch(tmp_path)
    live = report_path(repo, "live")
    candidates = live.parent / "live-candidates"
    candidates.mkdir(parents=True)
    (candidates / "old.jsonl").write_text("{}\n", encoding="utf-8")
    live.write_text('{"result": "pass"}\n', encoding="utf-8")
    _set_manifest(repo, "threshold", 0)
    out = run_cli(repo, env, mode="live")
    assert out.returncode == 2, out.stdout
    assert not live.exists() and not candidates.exists(), out.stdout


def test_an_unusable_report_dir_says_the_old_report_may_stand(tmp_path):
    repo, env = build_scratch(tmp_path)
    assert run_cli(repo, env).returncode == 0
    _set_manifest(repo, "report_dir", "../elsewhere")
    out = run_cli(repo, env)
    assert out.returncode == 2, out.stdout
    assert "may still stand" in out.stdout, out.stdout


def _outside(tmp_path):
    """A directory beside the project holding a file the run must not touch."""
    outside = tmp_path / "outside"
    candidates = outside / "evals" / "live-candidates"
    candidates.mkdir(parents=True)
    (candidates / "keep.txt").write_text("precious\n", encoding="utf-8")
    return outside


def _tree(path):
    return sorted(str(p.relative_to(path)) for p in path.rglob("*"))


@pytest.mark.parametrize("git", [True, False], ids=["git", "no-git"])
@pytest.mark.parametrize("mode", ["replay", "live"])
@pytest.mark.parametrize("refused_config", [False, True], ids=["run", "refused-config"])
def test_a_report_dir_through_a_symlink_writes_and_deletes_nothing(
    tmp_path, git, mode, refused_config
):
    """`evals.report_dir` is judged as text by the config and by git's ignore
    rule; a symlinked component points the report, and the live run's delete,
    somewhere neither of them looked."""
    repo, env = build_scratch(tmp_path)
    if not git:
        shutil.rmtree(str(repo / ".git"))
    outside = _outside(tmp_path)
    before = _tree(outside)
    link = repo / Path(_CONFIG.report_dir).parts[0]
    assert not link.exists()
    link.symlink_to(outside, target_is_directory=True)
    if refused_config:
        _set_manifest(repo, "threshold", 0)
    out = run_cli(repo, env, mode=mode)
    assert out.returncode == 2, out.stdout
    assert "evals.report_dir" in out.stdout and "symlink" in out.stdout, out.stdout
    assert _tree(outside) == before, out.stdout
    assert (outside / "evals" / "live-candidates" / "keep.txt").read_text(
        "utf-8"
    ) == "precious\n"


def test_a_report_file_that_is_a_symlink_is_not_written_through(tmp_path):
    repo, env = build_scratch(tmp_path)
    target = tmp_path / "victim.txt"
    target.write_text("precious\n", encoding="utf-8")
    report = report_path(repo)
    report.parent.mkdir(parents=True)
    (report.parent / (report.name + ".tmp")).symlink_to(target)
    out = run_cli(repo, env)
    assert out.returncode == 2, out.stdout
    assert target.read_text("utf-8") == "precious\n"
