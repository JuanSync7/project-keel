"""
title: Integration — the replayed eval gate, run as a real CLI over a scratch repository
kind: tests
layer: n/a
summary: A scratch git repository carrying keel's evals/, models/, agents/, runtimes/, the eval CLI and its script siblings, config/ and .gitignore runs scripts/run_evals.py --mode replay as a child process. Two runs on the same tree exit 0 and write byte-identical reports with result pass under config/project.json `evals.report_dir`, and leave what git lists unchanged (the writer's rerun_proof). The shipped dataset uses every scorer in evals.SCORERS and every doer in evals.DOERS, every agent package under agents/ has a doer of its own name that a shipped case drives, and every shipped case's scorer rejects each of a fixed set of generic wrong replies (empty, a one-sentence shrug such as "I don't know.", a bare yes or no, an empty JSON object, and three shrugs as three lines), so no case passes whatever the model says. Each red twin is red with its own exit code: a recorded response that fails its scorer or a prompt that changed is a fail (exit 1); a stale response hash, an empty dataset, no dataset file, an unknown scorer, an id repeated across two suites and a stray file in the dataset directory are refused (exit 2). A report_dir git does not ignore is refused before anything is written, as is one whose first component is a symlink to a directory outside the project (in replay and live mode, with and without git, and when the `evals` block is itself refused) and a report temporary file that is a symlink, each leaving the outside files as they were, a red run replaces an earlier green report, and a refused `evals` block (a bad value or an unknown key) removes the earlier report, twice over, rather than leave it reading pass.
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
# backends it drives, the CLI and the stdlib siblings git_tree needs,
# corpus_level.py, which the agents read a file's level on disk through, and
# resource_limits.py, which models starts its CLI child through.
_TREES = ("evals", "models", "agents", "runtimes", "config")
_SCRIPTS = (
    "run_evals.py",
    "git_tree.py",
    "child_env.py",
    "config_loader.py",
    "corpus_level.py",
    "exit_codes.py",
    "resource_limits.py",
)
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


def _example(repo):
    """The suite whose first case takes plain text, so an edit to its text
    stays a valid input and changes only the prompt."""
    return repo / _CONFIG.dataset_dir / "example.jsonl"


def _agents():
    """Every agent package under agents/: a directory holding an __init__.py."""
    return sorted(
        d.name for d in (_ROOT / "agents").iterdir() if (d / "__init__.py").is_file()
    )


def test_every_agent_has_a_doer_and_a_shipped_case():
    """An agent with no doer has no eval, and a doer with no case judges
    nothing; the doer takes the agent's package name."""
    agents = _agents()
    assert agents, "no agent package found under agents/"
    named = {c.doer for s in load_suites(_CONFIG, _ROOT) for c in s.cases}
    assert [a for a in agents if a not in DOERS] == []
    assert [a for a in agents if a not in named] == []


# Replies that answer no case: empty, a shrug in one sentence, a bare
# yes/no, an empty JSON object, and the same shrugs as three lines, the
# shape the triage prompt asks for.
_GENERIC_WRONG = (
    "",
    "I don't know.",
    "Nothing to add.",
    "N/A.",
    "Yes.",
    "No.",
    "OK",
    "{}",
    "I don't know.\nNothing to add.\nN/A.",
)


def test_every_shipped_case_can_fail():
    """A case its scorer passes whatever the model says proves nothing: each
    shipped case's scorer must reject every generic wrong reply."""
    cases = [c for s in load_suites(_CONFIG, _ROOT) for c in s.cases]
    assert cases
    vacuous = [
        (c.id, reply)
        for c in cases
        for reply in _GENERIC_WRONG
        if SCORERS[c.scorer_name].score(reply, c.params)[0]
    ]
    assert vacuous == []


def _fail_first(repo):
    """Record a response the first case's scorer rejects (hash kept true)."""
    path = _example(repo)
    cases = _cases(path)
    scorer = SCORERS[cases[0]["scorer"]["name"]]
    assert scorer.score("", cases[0]["scorer"]["params"])[0] is False
    cases[0]["recorded"]["response"] = ""
    cases[0]["recorded"]["sha256"] = _sha("")
    _write_cases(path, cases)
    return cases[0]["id"]


def _stale_prompt(repo):
    path = _example(repo)
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
        assert out.returncode == 14, out.stdout
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
    assert out.returncode == 14, out.stdout
    assert not live.exists() and not candidates.exists(), out.stdout


def test_an_unusable_report_dir_says_the_old_report_may_stand(tmp_path):
    repo, env = build_scratch(tmp_path)
    assert run_cli(repo, env).returncode == 0
    _set_manifest(repo, "report_dir", "../elsewhere")
    out = run_cli(repo, env)
    assert out.returncode == 14, out.stdout
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
    # A refused block is a config fault (CONFIG); a valid one reaching its
    # files through a symlink is a refused call (USAGE).
    assert out.returncode == (14 if refused_config else 2), out.stdout
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


# --- three answers from git: not installed, no repository, ran and failed ------


def _run_apart(repo, env, mode="replay"):
    """run_cli with stderr kept apart, so the helper's one line can be read."""
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
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )


def _head_names_nothing(repo):
    (repo / ".git" / "HEAD").write_text("garbage\n", encoding="utf-8")


def _gitdir_is_gone(repo):
    shutil.rmtree(str(repo / ".git"))
    (repo / ".git").write_text("gitdir: %s\n" % (repo / "gone"), encoding="utf-8")


@pytest.mark.parametrize("mode", ["replay", "live"])
@pytest.mark.parametrize(
    "break_it", [_head_names_nothing, _gitdir_is_gone], ids=["head", "gitdir"]
)
@pytest.mark.parametrize("stale", [False, True], ids=["first-run", "stale-green"])
def test_a_git_that_ran_and_failed_is_refused_and_names_its_status(
    tmp_path, break_it, mode, stale
):
    """A repository git cannot read is not "no git": whether the report path is
    ignored is unknown, so the run writes nothing. git exits 128 for this and
    for "not a repository" alike; the `.git` entry on disk tells them apart."""
    repo, env = build_scratch(tmp_path)
    env = dict(env, GIT_CEILING_DIRECTORIES=str(tmp_path))
    if stale:
        assert run_cli(repo, env).returncode == 0
    before = _tree(repo / _CONFIG.report_dir) if stale else None
    green = report_path(repo).read_bytes() if stale else None
    break_it(repo)
    out = _run_apart(repo, env, mode)
    assert out.returncode == 2, out.stderr
    line = out.stderr.strip().splitlines()[-1]
    assert line.startswith("run_evals: git "), line
    assert "evals.report_dir" in line and "git exited 128" in line, line
    assert "Traceback" not in out.stderr, out.stderr
    if stale:
        assert _tree(repo / _CONFIG.report_dir) == before
        assert report_path(repo).read_bytes() == green
    else:
        assert not (repo / Path(_CONFIG.report_dir).parts[0]).exists()


def test_a_git_that_fails_under_a_refused_config_removes_nothing(tmp_path):
    """The refused-config path deletes the earlier report only where git says
    the path is ignored; a git that cannot say is not a yes."""
    repo, env = build_scratch(tmp_path)
    env = dict(env, GIT_CEILING_DIRECTORIES=str(tmp_path))
    assert run_cli(repo, env).returncode == 0
    _set_manifest(repo, "threshold", 2)
    _head_names_nothing(repo)
    out = _run_apart(repo, env)
    assert out.returncode == 14, out.stderr
    assert "git exited 128" in out.stderr and "may still stand" in out.stderr
    assert "Traceback" not in out.stderr, out.stderr
    assert report_path(repo).exists()


def _no_git_on_path(tmp_path, env):
    bare = tmp_path / "no-tools"
    bare.mkdir()
    return dict(env, PATH=str(bare))


@pytest.mark.parametrize("absent", ["no-repository", "git-not-installed", "both"])
def test_no_git_and_no_repository_still_run_and_write_the_report(tmp_path, absent):
    """The two "no git" answers keep their path: with nothing tracked there is
    no tree to dirty, so the ignore rule has nothing to protect."""
    repo, env = build_scratch(tmp_path)
    env = dict(env, GIT_CEILING_DIRECTORIES=str(tmp_path))
    if absent in ("no-repository", "both"):
        shutil.rmtree(str(repo / ".git"))
    if absent in ("git-not-installed", "both"):
        env = _no_git_on_path(tmp_path, env)
    out = _run_apart(repo, env)
    assert out.returncode == 0, out.stderr
    assert read_report(repo)["result"] == "pass"
