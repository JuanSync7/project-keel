"""
title: Integration — restamp_docs picks the right documents in a real git tree
kind: tests
layer: n/a
summary: The git half of scripts/jobs/restamp_docs.py, driven as a process against real repositories under a hermetic git config. The worklist is what git would commit: in a committed repository the documents changed against HEAD, the untracked ones and the ones already committed stale, never an untouched or ignored one (ignored by the enclosing repository included); in a repository with history the arriving documents and not the repository's own; in a tree with no committed history everything (no git, a fresh `git init`, a new directory inside someone else's repository); and below the repository top its own modified documents, for the writer and the judge alike. The judge's remedy clears the judge under any SOURCE_DATE_EPOCH, including one behind the last commit, and `--check` agrees with the judge before it runs.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from hermetic_git import git_env

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "scripts" / "jobs" / "restamp_docs.py"
_JUDGE = _ROOT / "scripts" / "jobs" / "review_docs.py"
sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))

import review_docs  # noqa: E402

pytestmark = pytest.mark.integration

TODAY = "2026-09-02"


def _doc(stamp):
    return "---\ntitle: t\nupdated: %s\n---\n\n# t\n" % stamp


def _stamp(path):
    text = path.read_text(encoding="utf-8")
    start, end = review_docs.updated_span(text)
    return text[start:end]


def _git(cwd, env, *argv, date=None):
    env = dict(env)
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = "%sT12:00:00+0000" % date
    proc = subprocess.run(
        ["git"] + list(argv), cwd=str(cwd), env=env, capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def _restamp(root, env, *args):
    return subprocess.run(
        [sys.executable, str(_SCRIPT), "--root", str(root), "--today", TODAY]
        + list(args),
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.fixture()
def env(tmp_path):
    work = tmp_path / "gitwork"
    work.mkdir()
    return git_env(work)


def test_a_committed_repo_restamps_exactly_new_changed_and_committed_stale(
    tmp_path, env
):
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    _git(repo, env, "init", "-q")
    (repo / ".gitignore").write_text("scratch/\n", encoding="utf-8")
    (repo / "docs" / "untouched.md").write_text(_doc("2026-01-01"), encoding="utf-8")
    (repo / "docs" / "changed.md").write_text(_doc("2026-01-01"), encoding="utf-8")
    _git(repo, env, "add", "-A")
    _git(repo, env, "commit", "-qm", "one", date="2026-01-01")
    # A commit that changed a document without restamping it: committed stale.
    (repo / "docs" / "behind.md").write_text(_doc("2026-01-01"), encoding="utf-8")
    _git(repo, env, "add", "-A")
    _git(repo, env, "commit", "-qm", "two", date="2026-03-01")

    with (repo / "docs" / "changed.md").open("a", encoding="utf-8") as fh:
        fh.write("\nA new paragraph.\n")
    (repo / "docs" / "new.md").write_text(_doc("2026-01-01"), encoding="utf-8")
    (repo / "scratch").mkdir()
    (repo / "scratch" / "ignored.md").write_text(_doc("2026-01-01"), encoding="utf-8")

    proc = _restamp(repo, env)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.split() == ["docs/behind.md", "docs/changed.md", "docs/new.md"]
    for name in ("behind", "changed", "new"):
        assert _stamp(repo / "docs" / ("%s.md" % name)) == TODAY, name
    assert _stamp(repo / "docs" / "untouched.md") == "2026-01-01"
    assert _stamp(repo / "scratch" / "ignored.md") == "2026-01-01"
    assert review_docs.stale_findings(review_docs.collect(str(repo)), TODAY) == []

    again = _restamp(repo, env, "--check")
    assert (again.returncode, again.stdout) == (0, ""), again.stdout


def test_a_repo_with_history_stamps_what_arrives_and_nothing_it_already_had(
    tmp_path, env
):
    """`copier copy` into a repository that already has commits (measured: 105
    of 113 governed documents stale after the first commit). Every arriving
    document is untracked, so it is stamped; the repository's own committed,
    unchanged document is not touched."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, env, "init", "-q")
    (repo / "NOTES.txt").write_text("mine\n", encoding="utf-8")
    (repo / "own.md").write_text(_doc("2026-01-01"), encoding="utf-8")
    _git(repo, env, "add", "-A")
    _git(repo, env, "commit", "-qm", "history", date="2026-01-01")
    for rel in ("README.md", "docs/a.md", ".claude/b.md"):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(_doc("2025-06-01"), encoding="utf-8")

    proc = _restamp(repo, env, "--quiet")
    assert (proc.returncode, proc.stdout) == (0, ""), proc.stdout + proc.stderr
    for rel in ("README.md", "docs/a.md", ".claude/b.md"):
        assert _stamp(repo / rel) == TODAY, rel
    assert _stamp(repo / "own.md") == "2026-01-01"
    _git(repo, env, "add", "-A")
    _git(repo, env, "commit", "-qm", "arrive", date=TODAY)
    assert review_docs.stale_findings(review_docs.collect(str(repo)), TODAY) == []


@pytest.mark.parametrize("shape", ["no-git", "init-no-commit", "inside-a-parent-repo"])
def test_a_tree_with_no_committed_history_is_stamped_whole(tmp_path, env, shape):
    outer = tmp_path / "outer"
    root = outer / "proj" if shape == "inside-a-parent-repo" else outer
    (root / "docs").mkdir(parents=True)
    if shape == "init-no-commit":
        _git(root, env, "init", "-q")
    if shape == "inside-a-parent-repo":
        _git(outer, env, "init", "-q")
        (outer / "README.md").write_text(_doc("2026-01-01"), encoding="utf-8")
        _git(outer, env, "add", "-A")
        _git(outer, env, "commit", "-qm", "parent", date="2026-01-01")
    for rel in ("README.md", "docs/a.md", ".claude/b.md"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(_doc("2026-01-01"), encoding="utf-8")
    if shape == "init-no-commit":
        _git(root, env, "add", "README.md")

    proc = _restamp(root, env, "--quiet")
    assert (proc.returncode, proc.stdout) == (0, ""), proc.stdout + proc.stderr
    for rel in ("README.md", "docs/a.md", ".claude/b.md"):
        assert _stamp(root / rel) == TODAY, rel
    if shape == "inside-a-parent-repo":
        assert _stamp(outer / "README.md") == "2026-01-01", "escaped --root"


def test_a_document_an_enclosing_repo_ignores_is_left_alone(tmp_path, env):
    """The worklist is what git would commit. A document the enclosing
    repository ignores is never committed there, so the judge never reads it,
    and stamping it would be a write nobody asked for."""
    outer = tmp_path / "outer"
    root = outer / "proj"
    (root / "docs").mkdir(parents=True)
    _git(outer, env, "init", "-q")
    (outer / ".gitignore").write_text("docs/\n", encoding="utf-8")
    _git(outer, env, "add", "-A")
    _git(outer, env, "commit", "-qm", "parent", date="2026-01-01")
    (root / "README.md").write_text(_doc("2026-01-01"), encoding="utf-8")
    (root / "docs" / "a.md").write_text(_doc("2026-01-01"), encoding="utf-8")

    proc = _restamp(root, env)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.split() == ["README.md"]
    assert _stamp(root / "docs" / "a.md") == "2026-01-01"


def test_a_project_inside_a_larger_repo_finds_its_modified_documents(tmp_path, env):
    """`--root` below the repository top: git reports a changed path relative
    to the top (`sub/docs/a.md`) unless asked for `--relative`, and the
    root-relative name the writer expects (`docs/a.md`) would never match. The
    document is stamped fresh at its commit, so only the diff can find it."""
    top = tmp_path / "mono"
    doc = top / "sub" / "docs" / "a.md"
    doc.parent.mkdir(parents=True)
    _git(top, env, "init", "-q")
    doc.write_text(_doc("2026-01-01"), encoding="utf-8")
    _git(top, env, "add", "-A")
    _git(top, env, "commit", "-qm", "one", date="2026-01-01")
    with doc.open("a", encoding="utf-8") as fh:
        fh.write("\nA new paragraph.\n")

    proc = _restamp(top / "sub", env, "--check")
    assert (proc.returncode, proc.stdout.split()) == (1, ["docs/a.md"]), proc.stderr
    # The judge has the same blind spot to close: `git status --porcelain`
    # names paths from the repository top whatever the working directory, so a
    # project below the top never saw its own modified documents (measured).
    judged = _judge(top / "sub", dict(env, SOURCE_DATE_EPOCH="1788307200"))
    assert judged.returncode == 1, judged.stdout
    assert "STALE docs/a.md" in judged.stdout


# --- one clock: whatever the writer writes, the judge accepts -------------------


def _judge(root, env):
    """The judge as `make check-docs` runs it: strict, today from its default."""
    return subprocess.run(
        [sys.executable, str(_JUDGE), "--root", str(root), "--strict"],
        env=env,
        capture_output=True,
        text=True,
    )


def _writer(root, env, *args):
    """The writer as `make restamp-docs` runs it: today from its default."""
    return subprocess.run(
        [sys.executable, str(_SCRIPT), "--root", str(root)] + list(args),
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize(
    "epoch",
    [
        # Nix's default SOURCE_DATE_EPOCH (1980-01-01): behind every commit.
        "315532800",
        # 2026-01-01: the day the document was stamped, months before its commit.
        "1767225600",
        None,
    ],
)
def test_the_remedy_the_judge_names_clears_the_judge(tmp_path, env, epoch):
    """The contract the judge's message makes ("run `make restamp-docs`"): after
    the writer runs, the judge finds nothing, and `--check` agrees with the
    judge before it does. Before the shared clock and the commit-date floor, a
    pinned SOURCE_DATE_EPOCH made the writer a silent no-op and `--check` pass
    while the judge stayed red (measured)."""
    run_env = dict(env)
    run_env.pop("SOURCE_DATE_EPOCH", None)
    if epoch is not None:
        run_env["SOURCE_DATE_EPOCH"] = epoch
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    _git(repo, env, "init", "-q")
    (repo / "docs" / "behind.md").write_text(_doc("2026-01-01"), encoding="utf-8")
    (repo / "docs" / "edited.md").write_text(_doc("2026-01-01"), encoding="utf-8")
    # A commit dated after both stamps, as any commit made today is.
    _git(repo, env, "add", "-A")
    _git(repo, env, "commit", "-qm", "one", date="2026-03-01")
    with (repo / "docs" / "edited.md").open("a", encoding="utf-8") as fh:
        fh.write("\nA new paragraph.\n")

    assert _judge(repo, run_env).returncode == 1
    check = _writer(repo, run_env, "--check")
    assert check.returncode == 1, "--check passed while the judge is red"
    assert "docs/behind.md" in check.stdout.split()

    wrote = _writer(repo, run_env)
    assert wrote.returncode == 0, wrote.stderr
    judged = _judge(repo, run_env)
    assert judged.returncode == 0, judged.stdout + judged.stderr
    again = _writer(repo, run_env, "--check")
    assert (again.returncode, again.stdout) == (0, ""), again.stdout


def test_a_fresh_init_with_no_commit_restamps_tracked_and_untracked(tmp_path, env):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, env, "init", "-q")
    for name in ("staged.md", "loose.md"):
        (repo / name).write_text(_doc("2026-01-01"), encoding="utf-8")
    _git(repo, env, "add", "staged.md")

    proc = _restamp(repo, env)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.split() == ["loose.md", "staged.md"]


def test_the_date_defaults_to_source_date_epoch_in_utc(tmp_path, env):
    (tmp_path / "a.md").write_text(_doc("1969-01-01"), encoding="utf-8")
    run_env = dict(env, SOURCE_DATE_EPOCH="86400")
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--root", str(tmp_path)],
        env=run_env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert _stamp(tmp_path / "a.md") == "1970-01-02"
    assert sorted(os.listdir(str(tmp_path))) == ["a.md", "gitwork"], "temp file left"
