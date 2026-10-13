"""
title: Integration — every governed document is stamped no earlier than its last commit
kind: tests
layer: n/a
summary: The freshness rule of scripts/review_docs.py as a gate: `updated:` is never earlier than the file's last commit, and a document modified in the working tree carries today's date. Not a check_* letter on purpose (ADR-K-0009): check_structure.py is stdlib-only and 3.6-safe and does not shell to git. Absent is not broken — no git, or not a repository, is a stated skip. Landed with every stamp normalised in the same commit, so the tree complied on arrival.
"""

import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))
sys.path.insert(0, str(_ROOT / "tests"))

import child_env  # noqa: E402
import exit_codes  # noqa: E402
import review_docs  # noqa: E402

import hermetic_git  # noqa: E402

pytestmark = pytest.mark.integration


def test_every_governed_document_is_fresh():
    """A stale `updated:` is a document lying about itself to every reader and
    to the corpus that ranks by recency (CONVENTIONS §1). The remedy is one
    line: set `updated:` to today in the change that touches the file, which
    `make restamp-docs` (scripts/jobs/restamp_docs.py) does for every finding."""
    records = review_docs.collect(str(_ROOT))
    if records is None:
        pytest.skip("no git repository -- freshness cannot be compared")
    # The judge's own clock, so this gate and `make check-docs` (and the writer,
    # `make restamp-docs`) agree on what today is under a pinned build too.
    today = review_docs.resolve_today(None, os.environ).isoformat()
    stale = review_docs.stale_findings(records, today)
    assert not stale, "%d stale document(s):\n%s" % (
        len(stale),
        "\n".join("  %s: %s" % (f["path"], f["reason"]) for f in stale),
    )


# --- one date for a whole gate run --------------------------------------------

_JUDGE = _ROOT / "scripts" / "jobs" / "review_docs.py"
_RUN_DATE = json.loads((_ROOT / "config" / "project.json").read_text("utf-8"))[
    "evidence"
].get("run_date", {})
_DAY = datetime.timedelta(days=1)
_DOC = "---\ntitle: t\nupdated: %s\n---\n\n# t\n"


def _git(repo, env, *argv):
    out = subprocess.run(
        ["git"] + list(argv),
        cwd=str(repo),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    assert out.returncode == 0, out.stdout
    return out.stdout


def _touched_yesterday(tmp_path, stamp):
    """A repository with one governed document, committed long ago, changed in
    the working tree and stamped *stamp*: the tree a gate run that began on
    *stamp* is still judging after midnight. (repo, the child's environment
    with neither a run date nor a pinned build date)."""
    work = tmp_path / "work"
    work.mkdir(parents=True)
    git = hermetic_git.git_env(work)
    old = "2020-01-01T12:00:00+0000"
    git.update(GIT_AUTHOR_DATE=old, GIT_COMMITTER_DATE=old)
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "docs" / "note.md").write_text(_DOC % "2020-01-01", encoding="utf-8")
    for argv in (("init", "-q"), ("add", "-A"), ("commit", "-q", "-m", "one")):
        _git(repo, git, *argv)
    (repo / "docs" / "note.md").write_text(
        _DOC % stamp.isoformat() + "\nA new paragraph.\n", encoding="utf-8"
    )
    env = child_env.build_child_env(extra=hermetic_git.git_env_vars(work))
    for name in ("SOURCE_DATE_EPOCH", _RUN_DATE.get("env")):
        env.pop(name, None)
    return repo, env


def _judge(repo, env, **extra):
    return subprocess.run(
        [sys.executable, str(_JUDGE), "--root", str(repo), "--strict"],
        cwd=str(repo),
        env=dict(env, **extra),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )


def test_a_doc_stamped_on_the_run_date_stays_fresh_after_the_clock_passes_midnight(
    tmp_path,
):
    """The gate's two late readers of the freshness rule (this file's test above
    and `make check-docs`) each read the clock when they started, so a `make
    verify` begun before midnight on a tree with a touched document turned red
    after it. Here the clock is already a day past the stamp: with the run's
    date handed down the document is fresh, and without it it is stale, which
    is the rule "`updated:` means touched" still standing."""
    assert _RUN_DATE, "config/project.json has no evidence.run_date"
    name = _RUN_DATE["env"]
    assert _RUN_DATE["max_age_days"] >= 1, "a run could not cross midnight at all"
    for _attempt in range(2):
        began = datetime.date.today() - _DAY
        repo, env = _touched_yesterday(tmp_path / ("try%d" % _attempt), began)
        runs = {
            "run-date": _judge(repo, env, **{name: began.isoformat()}),
            "clock": _judge(repo, env),
            "too-old": _judge(
                repo,
                env,
                **{name: (began - _DAY * _RUN_DATE["max_age_days"]).isoformat()},
            ),
            "tomorrow": _judge(repo, env, **{name: (began + 2 * _DAY).isoformat()}),
            "not-a-date": _judge(repo, env, **{name: "yesterday"}),
            # A pinned build date outranks the run's date, as it outranks the
            # clock: it is the caller's explicit pin (ADR K-0010).
            "pinned": _judge(
                repo, env, SOURCE_DATE_EPOCH="4102444800", **{name: began.isoformat()}
            ),
        }
        if datetime.date.today() - _DAY == began:
            break
    codes = {key: (run.returncode, run.stderr) for key, run in runs.items()}
    assert runs["run-date"].returncode == exit_codes.ExitCode.SUCCESS, codes
    assert " 0 stale" in runs["run-date"].stdout, runs["run-date"].stdout
    assert runs["clock"].returncode == exit_codes.ExitCode.FAILURE, codes
    assert "STALE docs/note.md" in runs["clock"].stdout, runs["clock"].stdout
    for refused in ("too-old", "tomorrow", "not-a-date"):
        assert runs[refused].returncode == exit_codes.ExitCode.USAGE, (refused, codes)
        assert name in runs[refused].stderr, (refused, codes)
        assert "STALE" not in runs[refused].stdout, refused
    assert runs["pinned"].returncode == exit_codes.ExitCode.FAILURE, codes


def test_a_tree_the_suite_commits_inside_a_run_begun_yesterday_stays_fresh(
    tmp_path, monkeypatch
):
    """The suite commits the trees it judges: tests/hermetic_git.py
    `clone_including_worktree` commits the working tree, and the copier tests
    commit what they generate. A `make verify` begun before midnight stamped a
    touched document with the run's date and then committed it after midnight,
    so git dated the commit a day past the stamp and the judge called the
    document committed stale (three goals, 17 and 133 documents, measured). The
    suite's git environment dates a commit by the run, so the commit and the
    stamp agree; the run begins on the clock's yesterday, the oldest day
    config/project.json `evidence.run_date.max_age_days` lets it have."""
    assert _RUN_DATE, "config/project.json has no evidence.run_date"
    name = _RUN_DATE["env"]
    assert _RUN_DATE["max_age_days"] >= 1, "a run could not cross midnight at all"
    for _attempt in range(2):
        began = datetime.date.today() - _DAY
        monkeypatch.setenv(name, began.isoformat())
        base = tmp_path / ("try%d" % _attempt)
        work = base / "work"
        work.mkdir(parents=True)
        repo = base / "repo"
        (repo / "docs").mkdir(parents=True)
        (repo / "docs" / "note.md").write_text(
            _DOC % began.isoformat(), encoding="utf-8"
        )
        git = hermetic_git.git_env(work)
        for argv in (("init", "-q"), ("add", "-A"), ("commit", "-q", "-m", "run")):
            _git(repo, git, *argv)
        committed = _git(repo, git, "log", "-1", "--format=%cs").strip()
        env = child_env.build_child_env(extra=hermetic_git.git_env_vars(work))
        env.pop("SOURCE_DATE_EPOCH", None)
        judged = _judge(repo, env)
        if datetime.date.today() - _DAY == began:
            break
    assert env.get(name) == began.isoformat(), "the judge did not get the run date"
    assert committed == began.isoformat(), (committed, began)
    assert judged.returncode == exit_codes.ExitCode.SUCCESS, (
        judged.stdout + judged.stderr
    )
    assert " 0 stale" in judged.stdout, judged.stdout
