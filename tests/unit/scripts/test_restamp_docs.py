"""
title: Unit — restamp_docs (the writer that keeps `updated:` true)
kind: tests
layer: n/a
summary: The pure half of scripts/jobs/restamp_docs.py, pinned: only the ten date bytes of the `updated:` value change, BOM and CRLF and a trailing comment survive, a stamp is never moved backwards, a non-date stamp is a loud error that leaves the file alone while the other documents are still restamped, the date comes from --today then SOURCE_DATE_EPOCH (UTC) then the local clock, `--check` writes nothing, and the no-git walk skips exactly check_structure's IGNORE_DIRS. Measured before it existed: a project generated from keel and committed the same day had 112 of 112 governed documents stale.
"""

import datetime
import difflib
import os
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure  # noqa: E402
import restamp_docs  # noqa: E402
import review_docs  # noqa: E402

import hermetic_git  # noqa: E402

pytestmark = pytest.mark.unit

TODAY = datetime.date(2026, 9, 2)


def _doc(stamp, newline="\n", tail=""):
    lines = [
        "---",
        "title: A document",
        "updated: %s%s" % (stamp, tail),
        "---",
        "",
        "# A document",
        "",
        "Body text with `updated: 1999-01-01` quoted in prose.",
        "",
    ]
    return newline.join(lines)


def test_an_older_stamp_becomes_today_and_no_other_byte_changes():
    """The whole contract of a writer that edits someone else's prose: the value
    span, and nothing else — not the line ending, not the comment after it."""
    before = _doc("2026-01-01", newline="\r\n", tail="  # note")
    after = restamp_docs.restamp_text(before, TODAY)
    assert after == before.replace("2026-01-01", "2026-09-02", 1)
    changed = [
        ln
        for ln in difflib.ndiff(before.splitlines(True), after.splitlines(True))
        if ln.startswith(("- ", "+ "))
    ]
    assert changed == [
        "- updated: 2026-01-01  # note\r\n",
        "+ updated: 2026-09-02  # note\r\n",
    ]


def test_a_stamp_on_or_after_today_is_never_moved():
    assert restamp_docs.restamp_text(_doc("2026-09-02"), TODAY) is None
    assert restamp_docs.restamp_text(_doc("2027-01-01"), TODAY) is None


def test_a_bom_prefixed_doc_is_restamped_and_keeps_its_bom():
    after = restamp_docs.restamp_text("\ufeff" + _doc("2026-01-01"), TODAY)
    assert after is not None and after.startswith("\ufeff---")
    assert "updated: 2026-09-02\n" in after


def test_a_non_date_stamp_is_a_loud_error_not_a_rewrite(tmp_path, capsys):
    with pytest.raises(restamp_docs.RestampError) as err:
        restamp_docs.restamp_text(_doc("soon"), TODAY)
    assert "soon" in str(err.value)
    # A quoted date is not a date either: the judge (review_docs) says so too,
    # and the writer must agree with the judge rather than guess.
    with pytest.raises(restamp_docs.RestampError):
        restamp_docs.restamp_text(_doc('"2026-01-01"'), TODAY)

    bad, good = tmp_path / "bad.md", tmp_path / "good.md"
    bad.write_text(_doc("soon"), encoding="utf-8")
    good.write_text(_doc("2026-01-01"), encoding="utf-8")
    bad_before = bad.read_bytes()
    rc = restamp_docs.main(["--root", str(tmp_path), "--today", "2026-09-02"])
    assert rc == 1
    assert bad.read_bytes() == bad_before
    assert "updated: 2026-09-02" in good.read_text(encoding="utf-8")
    assert "bad.md" in capsys.readouterr().err


def test_docs_without_frontmatter_or_without_updated_are_left_alone():
    assert restamp_docs.restamp_text("# Plain\n\nupdated: 2026-01-01\n", TODAY) is None
    assert restamp_docs.restamp_text("---\ntitle: x\n---\n# x\n", TODAY) is None
    body_only = "---\ntitle: x\n---\n\nupdated: 2026-01-01\n"
    assert restamp_docs.restamp_text(body_only, TODAY) is None
    nested = "---\nmeta:\n  updated: 2026-01-01\n---\n"
    assert restamp_docs.restamp_text(nested, TODAY) is None
    # An empty value must not borrow the next line's token as its date.
    empty = "---\nupdated:\ntitle: 2026-01-01\n---\n"
    assert restamp_docs.restamp_text(empty, TODAY) is None


def test_today_resolution_order():
    env = {"SOURCE_DATE_EPOCH": "86400"}
    assert restamp_docs.resolve_today("2030-05-06", env) == datetime.date(2030, 5, 6)
    assert restamp_docs.resolve_today(None, env) == datetime.date(1970, 1, 2)
    # UTC, not local: one second before midnight UTC is still the first day.
    assert restamp_docs.resolve_today(None, {"SOURCE_DATE_EPOCH": "86399"}) == (
        datetime.date(1970, 1, 1)
    )
    assert restamp_docs.resolve_today(None, {}) == datetime.date.today()
    # "99999999999999" is digits past datetime's year 9999: it used to escape
    # as a ValueError traceback (exit 1, which `--check` uses for "would restamp").
    for bad in ("tomorrow", "", "1.5", "99999999999999"):
        with pytest.raises(restamp_docs.RestampError):
            restamp_docs.resolve_today(None, {"SOURCE_DATE_EPOCH": bad})
    with pytest.raises(restamp_docs.RestampError):
        restamp_docs.resolve_today("2026-9-2", {})


def test_a_bad_date_source_exits_2(tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "not-a-number")
    assert restamp_docs.main(["--root", str(tmp_path)]) == 2
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "99999999999999")
    assert restamp_docs.main(["--root", str(tmp_path), "--check"]) == 2
    monkeypatch.delenv("SOURCE_DATE_EPOCH")
    assert restamp_docs.main(["--root", str(tmp_path), "--today", "soon"]) == 2


def test_check_mode_lists_and_writes_nothing(tmp_path, capsys):
    doc = tmp_path / "docs" / "a.md"
    doc.parent.mkdir()
    doc.write_text(_doc("2026-01-01"), encoding="utf-8")
    before = doc.read_bytes()
    argv = ["--root", str(tmp_path), "--today", "2026-09-02"]

    assert restamp_docs.main(argv + ["--check"]) == 1
    assert "docs/a.md" in capsys.readouterr().out
    assert doc.read_bytes() == before

    assert restamp_docs.main(argv) == 0
    assert doc.read_bytes() != before
    capsys.readouterr()
    assert restamp_docs.main(argv + ["--check"]) == 0
    assert capsys.readouterr().out == ""


def test_the_no_git_walk_includes_wiki_and_dot_dirs_and_skips_ignore_dirs(
    tmp_path, monkeypatch
):
    """review_docs' own walk drops `wiki/` and every dot-dir; three of keel's
    governed documents live there, so the writer walks check_structure's
    IGNORE_DIRS instead — imported, so the two lists cannot drift apart."""
    assert restamp_docs.WALK_SKIP_DIRS == check_structure.IGNORE_DIRS
    monkeypatch.setattr(restamp_docs, "_inside_work_tree", lambda root: False)
    kept = ["wiki/README.md", ".claude/README.md", "README.md"]
    skipped = ["node_modules/pkg/README.md", ".venv/lib/README.md"]
    for rel in kept + skipped:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(_doc("2026-01-01"), encoding="utf-8")
    link = tmp_path / "linked.md"
    link.symlink_to(tmp_path / "README.md")

    assert restamp_docs.main(["--root", str(tmp_path), "--today", "2026-09-02"]) == 0
    for rel in kept:
        assert "2026-09-02" in (tmp_path / rel).read_text(encoding="utf-8"), rel
    for rel in skipped:
        assert "2026-01-01" in (tmp_path / rel).read_text(encoding="utf-8"), rel
    assert link.is_symlink(), "the writer replaced a symlink with a regular file"


def test_the_writer_and_the_judge_read_the_same_bytes():
    """One grammar: the span the writer rewrites is the value the judge reads."""
    text = "\ufeff" + _doc("2026-01-01", newline="\r\n", tail="  # c")
    start, end = review_docs.updated_span(text)
    assert text[start:end] == "2026-01-01"
    after = restamp_docs.restamp_text(text, TODAY)
    start, end = review_docs.updated_span(after)
    assert after[start:end] == "2026-09-02"


def test_a_write_keeps_the_file_mode(tmp_path):
    doc = tmp_path / "a.md"
    doc.write_text(_doc("2026-01-01"), encoding="utf-8")
    doc.chmod(0o640)
    assert restamp_docs.main(["--root", str(tmp_path), "--today", "2026-09-02"]) == 0
    assert doc.stat().st_mode & 0o777 == 0o640
    assert not [p.name for p in tmp_path.iterdir() if p.name != "a.md"], (
        "the atomic write left its temporary file behind"
    )


def test_a_template_twin_moves_with_its_document(tmp_path, monkeypatch, capsys):
    """check_N requires every non-templated line of a parity twin to appear in
    its plain file, and `updated:` is such a line. A writer that moved only the
    plain stamp turned keel's own gate red on its first dogfood run (measured),
    so the twin, found by the gate's own suffix, moves in the same run."""
    monkeypatch.setattr(restamp_docs, "_inside_work_tree", lambda root: False)
    plain = tmp_path / "README.md"
    twin = tmp_path / ("README.md" + restamp_docs.TWIN_SUFFIX)
    plain.write_text(_doc("2026-01-01"), encoding="utf-8")
    twin.write_text(
        _doc("2026-01-01", tail="").replace("A document", "{{ t }}"), "utf-8"
    )
    argv = ["--root", str(tmp_path), "--today", "2026-09-02"]

    assert restamp_docs.main(argv + ["--check"]) == 1
    listed = capsys.readouterr().out.split()
    assert listed == ["README.md", "README.md" + restamp_docs.TWIN_SUFFIX]

    assert restamp_docs.main(argv) == 0
    for path in (plain, twin):
        assert "updated: 2026-09-02\n" in path.read_text(encoding="utf-8"), path
    assert "{{ t }}" in twin.read_text(encoding="utf-8")
    capsys.readouterr()
    assert restamp_docs.main(argv + ["--check"]) == 0


def test_the_twin_suffix_is_the_parity_gates_own():
    assert restamp_docs.TWIN_SUFFIX == check_structure._TWIN_SUFFIX


def test_the_writer_and_the_judge_share_one_clock():
    """Two resolvers drifted once: the writer read SOURCE_DATE_EPOCH and the
    judge did not, so `make restamp-docs` wrote nothing while the judge it
    answers to stayed red (measured)."""
    for env in ({}, {"SOURCE_DATE_EPOCH": "86400"}):
        assert restamp_docs.resolve_today(None, env) == review_docs.resolve_today(
            None, env
        )


def test_the_target_is_never_earlier_than_the_last_commit():
    """The judge's first rule is `updated:` >= the date of the file's last
    commit, read from git, not from the writer's clock. A writer that stamped
    only its own today left a committed-stale document stale whenever that
    today was behind the commit (a pinned SOURCE_DATE_EPOCH, or a committer
    timezone ahead of UTC), and `--check` then passed a red gate (measured)."""
    today = datetime.date(2026, 1, 1)
    assert restamp_docs.target_date(today, None) == today
    assert restamp_docs.target_date(today, "2025-12-31") == today
    assert restamp_docs.target_date(today, "2026-10-06") == datetime.date(2026, 10, 6)
    with pytest.raises(restamp_docs.RestampError):
        restamp_docs.target_date(today, "last tuesday")


# --- read-only git: --check and pending() must not rewrite .git/index ----------
#
# `git diff HEAD` rewrites .git/index whenever a stat refresh is due (measured on
# git 2.43.5, GIT_OPTIONAL_LOCKS=0 included); the worklist reads changed paths
# through review_docs.modified_paths instead, so `--check` is read-only against
# another project's repository too.


def _git(cwd, *argv):
    proc = subprocess.run(
        ["git"] + list(argv),
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        env=dict(
            os.environ,
            GIT_AUTHOR_DATE="2026-01-01T12:00:00+0000",
            GIT_COMMITTER_DATE="2026-01-01T12:00:00+0000",
        ),
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_check_mode_leaves_the_git_index_untouched(tmp_path, monkeypatch, capsys):
    work = tmp_path / "gitwork"
    work.mkdir()
    for key, value in hermetic_git.git_env_vars(work).items():
        monkeypatch.setenv(key, value)
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    stale = repo / "docs" / "a.md"
    stale.write_text(_doc("2026-01-01"), encoding="utf-8")
    other = repo / "docs" / "b.md"
    other.write_text(_doc("2026-01-01"), encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    stale.write_text(_doc("2026-01-01", tail="  # edited"), encoding="utf-8")
    # An unmodified tracked file with a moved mtime: a stat refresh is due, so
    # any index-refreshing git command would rewrite .git/index here.
    later = other.stat().st_mtime + 120
    os.utime(str(other), (later, later))
    index = repo / ".git" / "index"
    before = (index.read_bytes(), index.stat().st_mtime_ns, stale.read_bytes())

    argv = ["--check", "--root", str(repo), "--today", "2026-09-02"]
    assert restamp_docs.main(argv) == 1
    assert capsys.readouterr().out.splitlines() == ["docs/a.md"]
    assert (index.read_bytes(), index.stat().st_mtime_ns, stale.read_bytes()) == before
    assert restamp_docs.pending(str(repo), TODAY) == [
        ("docs/a.md", "2026-01-01", "2026-09-02")
    ]

    assert (index.read_bytes(), index.stat().st_mtime_ns, stale.read_bytes()) == before


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root reads mode-000 files"
)
def test_an_unreadable_document_is_named_and_the_rest_still_listed_or_written(
    tmp_path, capsys
):
    """A governed doc the reader cannot open is an error the run names, as a
    non-date stamp is, never a traceback that hides the rest of the worklist:
    `pending` records it and lists the others, `--check` and a write run name it
    on stderr and exit 1 while the readable document is still listed or written."""
    (tmp_path / "docs").mkdir()
    locked = tmp_path / "docs" / "a.md"
    locked.write_text(_doc("2026-01-01"), encoding="utf-8")
    stale = tmp_path / "docs" / "b.md"
    stale.write_text(_doc("2026-01-01"), encoding="utf-8")
    locked.chmod(0)
    try:
        errors = []
        rows = restamp_docs.pending(str(tmp_path), TODAY, errors)
        argv = ["--root", str(tmp_path), "--today", TODAY.isoformat()]
        check = restamp_docs.main(argv + ["--check"])
        check_out = capsys.readouterr()
        run = restamp_docs.main(argv)
        run_out = capsys.readouterr()
    finally:
        locked.chmod(0o644)
    assert rows == [("docs/b.md", "2026-01-01", "2026-09-02")]
    assert [path for path, _reason in errors] == ["docs/a.md"]
    assert "cannot read" in errors[0][1]
    assert check == 1 and check_out.out.splitlines() == ["docs/b.md"]
    assert "docs/a.md: cannot read" in check_out.err
    assert run == 1 and run_out.out.splitlines() == ["docs/b.md"]
    assert "docs/a.md: cannot read" in run_out.err
    assert "updated: 2026-09-02" in stale.read_text(encoding="utf-8")
    assert "updated: 2026-01-01" in locked.read_text(encoding="utf-8")


def test_pending_reports_a_twin_and_skips_what_is_current(tmp_path):
    """pending() is the public read of what `--check` would list: the document,
    its template twin, and nothing already on or after the target."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text(_doc("2026-01-01"), encoding="utf-8")
    (tmp_path / "docs" / "a.md.jinja").write_text(_doc("2026-01-01"), encoding="utf-8")
    (tmp_path / "docs" / "c.md").write_text(_doc("2026-09-02"), encoding="utf-8")
    assert restamp_docs.pending(str(tmp_path), TODAY) == [
        ("docs/a.md", "2026-01-01", "2026-09-02"),
        ("docs/a.md.jinja", "2026-01-01", "2026-09-02"),
    ]
