"""
title: Unit — review_docs (the freshness rule)
kind: tests
layer: n/a
summary: The pure half of scripts/review_docs.py, pinned: `updated:` must be an ISO date, never earlier than the file's last commit, and a file modified in the working tree must carry today's date or later. Measured before the rule landed: 135 of 153 governed documents were stamped earlier than their last commit — including AGENT.md and CONVENTIONS.md — and nothing said so.
"""

import datetime
import os
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))

import review_docs  # noqa: E402

import hermetic_git  # noqa: E402

pytestmark = pytest.mark.unit

TODAY = "2026-09-02"


def _find(*records):
    return review_docs.stale_findings(list(records), TODAY)


def test_a_document_stamped_on_or_after_its_last_commit_passes():
    assert _find(("a.md", "2026-08-18", "2026-08-18", False)) == []
    assert _find(("a.md", "2026-09-01", "2026-08-18", False)) == []


def test_a_document_committed_after_its_stamp_is_stale_naming_both_dates():
    """The measured shape: a commit changed the file, the stamp stayed behind."""
    out = _find(("CONVENTIONS.md", "2026-06-24", "2026-08-18", False))
    assert len(out) == 1
    assert out[0]["path"] == "CONVENTIONS.md" and out[0]["expected"] == "2026-08-18"
    assert "2026-06-24" in out[0]["reason"] and "2026-08-18" in out[0]["reason"]


def test_a_modified_document_must_carry_today():
    out = _find(("a.md", "2026-08-18", "2026-08-18", True))
    assert (
        len(out) == 1
        and out[0]["expected"] == TODAY
        and "today" not in out[0]["expected"]
    )
    assert _find(("a.md", TODAY, "2026-08-18", True)) == []


def test_a_never_committed_document_is_held_only_to_today_when_modified():
    assert _find(("new.md", "2026-01-01", None, False)) == []
    assert len(_find(("new.md", "2026-01-01", None, True))) == 1


def test_a_stamp_that_is_not_a_date_is_a_finding():
    out = _find(("a.md", "yesterday", "2026-08-18", False))
    assert len(out) == 1 and "not a date" in out[0]["reason"]


def test_a_committed_stale_stamp_is_reported_once_even_when_also_modified():
    out = _find(("a.md", "2026-06-24", "2026-08-18", True))
    assert len(out) == 1 and out[0]["expected"] == "2026-08-18"


def test_no_records_no_findings():
    assert review_docs.stale_findings([], TODAY) == []


def test_a_stale_reason_names_the_remedy():
    """A finding that does not say how to clear it is a chore with no handle.
    The dates stay in the reason; the command that fixes it is added."""
    committed = _find(("a.md", "2026-06-24", "2026-08-18", False))[0]["reason"]
    modified = _find(("a.md", "2026-08-18", "2026-08-18", True))[0]["reason"]
    for reason in (committed, modified):
        assert "make restamp-docs" in reason, reason
    assert "2026-06-24" in committed and "2026-08-18" in committed
    assert "`updated: %s`" % TODAY in modified


def test_a_bom_prefixed_doc_is_governed(tmp_path):
    """`text.startswith('---')` is False after a U+FEFF, so a BOM document used
    to be silently ungoverned. The span helper is the one grammar the judge and
    the writer (restamp_docs) share."""
    doc = tmp_path / "bom.md"
    text = "\ufeff---\ntitle: x\nupdated: 2026-01-01\n---\n# x\n"
    doc.write_text(text, encoding="utf-8")
    assert review_docs._frontmatter_updated(str(doc)) == "2026-01-01"
    start, end = review_docs.updated_span(text)
    assert text[start:end] == "2026-01-01"


def test_an_empty_updated_never_borrows_the_next_line():
    """`updated:\\s*` used to span the newline and read the NEXT line's token as
    the date; the value is horizontal-whitespace-delimited now."""
    assert review_docs.updated_span("---\nupdated:\ntitle: 2026-01-01\n---\n") is None
    assert review_docs.updated_span("---\ntitle: x\n---\nupdated: 2026-01-01\n") is None


# --- the advisory that stays advisory: unresolved mentions ---------------------


def test_a_backticked_path_that_resolves_to_nothing_is_listed(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "real.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "docs" / "a.md").write_text(
        "See `scripts/real.py`, `scripts/gone.py`, `docs/a.md`, `a.md` and `not a path`.\n"
        "Also `check_structure.py` as a noun.\n",
        encoding="utf-8",
    )
    found = review_docs.unresolved_mentions(str(tmp_path))
    assert found == [
        ("docs/a.md", 1, "scripts/gone.py"),
        ("docs/a.md", 2, "check_structure.py"),
    ]


def test_mentions_never_make_strict_fail(tmp_path, monkeypatch, capsys):
    """Advisory in every mode: `--strict` gates freshness only."""
    (tmp_path / "a.md").write_text("`nowhere/x.py`\n", encoding="utf-8")
    monkeypatch.setattr(review_docs, "collect", lambda root: [])
    assert review_docs.main(["--root", str(tmp_path), "--strict"]) == 0
    assert "unresolved mention" in capsys.readouterr().out


# --- roster rows: the facts the doc reviewer judges -----------------------------


def test_every_roster_row_is_reported_with_its_not_for_cell(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "README.md").write_text(
        "# S\n\n## What ships here\n\n| Member | Purpose | Not for |\n|---|---|---|\n"
        "| `a.py` | does a | b (that is `b.py`) |\n| `b.py` | does b | n/a |\n\n## Later\n\n| Member | Not for |\n|---|---|\n| `z` | no |\n",
        encoding="utf-8",
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "plain.md").write_text("# no roster\n", encoding="utf-8")
    rows = review_docs.roster_rows(str(tmp_path))
    assert rows == [
        {
            "path": "scripts/README.md",
            "member": "a.py",
            "line": 7,
            "not_for": "b (that is `b.py`)",
        },
        {"path": "scripts/README.md", "member": "b.py", "line": 8, "not_for": "n/a"},
    ]


# --- one clock: the judge and the writer read "today" from the same source -----


def test_the_judge_resolves_today_from_source_date_epoch_then_the_clock():
    """The writer (restamp_docs) stamps with SOURCE_DATE_EPOCH when it is set. A
    judge that ignored it held a modified document to a different day than the
    writer stamped, so the remedy it names wrote nothing and the gate stayed red
    (measured with SOURCE_DATE_EPOCH=1767225600). One resolver, owned here."""
    assert review_docs.resolve_today("2030-05-06", {}) == datetime.date(2030, 5, 6)
    env = {"SOURCE_DATE_EPOCH": "86399"}  # one second before midnight UTC
    assert review_docs.resolve_today(None, env) == datetime.date(1970, 1, 1)
    assert review_docs.resolve_today(None, {}) == datetime.date.today()


@pytest.mark.parametrize(
    "argv_today, epoch",
    [
        (None, "tomorrow"),
        (None, ""),
        (None, "1.5"),
        # Digits, but past datetime's year 9999: fromtimestamp raises, and an
        # uncaught raise exits 1, which in `--check` means "would restamp".
        (None, "99999999999999"),
        ("2026-9-2", None),
        ("2026-02-30", None),
    ],
)
def test_a_malformed_date_source_is_a_named_error_never_a_crash(argv_today, epoch):
    env = {} if epoch is None else {"SOURCE_DATE_EPOCH": epoch}
    with pytest.raises(review_docs.DateSourceError):
        review_docs.resolve_today(argv_today, env)


def test_the_judge_exits_2_on_a_malformed_date_source(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "99999999999999")
    assert review_docs.main(["--root", str(tmp_path)]) == 2
    assert "SOURCE_DATE_EPOCH" in capsys.readouterr().err


# --- read-only git: the judge must not rewrite .git/index ----------------------
#
# Measured on git 2.43.5 (docs/design/downstream-feedback.md slice 5): `git diff
# HEAD` and plain `git status` refresh stat data and rewrite .git/index, even with
# GIT_OPTIONAL_LOCKS=0; `git --no-optional-locks status`, ls-files, log and
# rev-parse do not. A "read-only" judge pointed at another project's tree must
# leave that index alone, so the changed-path source is pinned here.

_DOC = "---\ntitle: %s\nupdated: 2026-01-01\n---\n\n# %s\n"


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


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    """A committed repo with governed docs in `sub/docs/` and one outside it.
    The hermetic git config reaches review_docs' own git calls through
    child_env's GIT_CONFIG_* allowlist entries."""
    work = tmp_path / "gitwork"
    work.mkdir()
    for key, value in hermetic_git.git_env_vars(work).items():
        monkeypatch.setenv(key, value)
    top = tmp_path / "repo"
    for rel in ("sub/docs/a.md", "sub/docs/b.md", "outside.md"):
        path = top / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_DOC % (rel, rel), encoding="utf-8")
    _git(top, "init", "-q")
    _git(top, "add", "-A")
    _git(top, "commit", "-q", "-m", "init")
    return top


def _index_state(top):
    index = top / ".git" / "index"
    return index.read_bytes(), index.stat().st_mtime_ns


def test_collect_leaves_the_git_index_untouched(repo):
    (repo / "sub" / "docs" / "a.md").write_text(
        _DOC % ("edited", "edited"), encoding="utf-8"
    )
    # An unmodified tracked file whose mtime moved: its stat data is now stale
    # in the index, so any command that refreshes the index will rewrite it.
    unmodified = repo / "sub" / "docs" / "b.md"
    later = unmodified.stat().st_mtime + 120
    os.utime(str(unmodified), (later, later))
    before = _index_state(repo)

    records = review_docs.collect(str(repo))

    assert _index_state(repo) == before
    modified = {relpath for relpath, _u, _c, is_modified in records if is_modified}
    assert modified == {"sub/docs/a.md"}


def test_modified_paths_below_the_repository_top_are_root_relative(repo):
    (repo / "sub" / "docs" / "a.md").write_text(
        _DOC % ("edited", "edited"), encoding="utf-8"
    )
    (repo / "outside.md").write_text(_DOC % ("edited", "edited"), encoding="utf-8")
    sub = repo / "sub"

    assert review_docs.modified_paths(str(sub)) == {"docs/a.md"}
    assert review_docs.modified_paths(str(repo)) == {"sub/docs/a.md", "outside.md"}
    records = review_docs.collect(str(sub))
    assert {r[0] for r in records if r[3]} == {"docs/a.md"}


def test_modified_paths_is_none_outside_a_repository(tmp_path):
    assert review_docs.modified_paths(str(tmp_path)) is None


def _probe(tmp_path, name):
    """An executable that records it ran (in `<name>.ran`) and passes stdin
    through, so a filter it stands in for would otherwise succeed."""
    script = tmp_path / ("%s.sh" % name)
    script.write_text(
        "#!/bin/sh\necho ran >> %s\ncat\n" % (tmp_path / ("%s.ran" % name))
    )
    script.chmod(0o755)
    return script


def _signed_head(top):
    """Point HEAD at a copy of itself carrying a (fake) PGP signature header, so
    `log.showSignature` makes git run `gpg.program` to verify it."""
    raw = _git(top, "cat-file", "commit", "HEAD")
    head, _blank, body = raw.partition("\n\n")
    sig = (
        "gpgsig -----BEGIN PGP SIGNATURE-----\n \n iQ==\n -----END PGP SIGNATURE-----\n"
    )
    obj = top / "signed.commit"
    obj.write_text(head + "\n" + sig + "\n" + body)
    sha = _git(top, "hash-object", "-t", "commit", "-w", str(obj)).strip()
    obj.unlink()
    _git(top, "update-ref", "HEAD", sha)


def test_judging_a_repository_runs_none_of_its_configured_commands(repo, tmp_path):
    """The repository judged is data. Its own config may name a clean or smudge
    filter (selected by a committed .gitattributes or .git/info/attributes), a
    long-running filter process, or a signature verifier that `git log` runs
    under log.showSignature; status re-hashes a stat-dirty file through the
    clean filter, so each would run inside the judge (measured: 366 runs in
    one audit before the fix)."""
    clean, process, gpg = (_probe(tmp_path, n) for n in ("clean", "process", "gpg"))
    for key, value in (
        ("filter.probe.clean", str(clean)),
        ("filter.probe.smudge", str(clean)),
        ("filter.probe.required", "true"),
        ("filter.lfs-like.process", str(process)),
        ("filter.lfs-like.required", "true"),
        ("log.showSignature", "true"),
        ("gpg.program", str(gpg)),
    ):
        _git(repo, "config", key, value)
    (repo / ".git" / "info").mkdir(exist_ok=True)
    (repo / ".git" / "info" / "attributes").write_text("sub/docs/*.md filter=probe\n")
    (repo / ".gitattributes").write_text("outside.md filter=lfs-like\n")
    _signed_head(repo)
    for rel in ("sub/docs/a.md", "sub/docs/b.md", "outside.md"):
        path = repo / rel
        later = path.stat().st_mtime + 120
        os.utime(str(path), (later, later))

    records = review_docs.collect(str(repo))

    assert records is not None
    ran = sorted(p.name for p in tmp_path.glob("*.ran"))
    assert ran == [], ran


def test_a_root_whose_filter_drivers_cannot_be_listed_is_refused(monkeypatch):
    """Fail closed: when `git config` fails (anything but exit 1, "no match"),
    the call that might have run a driver is not made."""
    calls = []

    class _Proc:
        returncode, stdout, stderr = 3, "", "bad config line 7"

    def fake_run(argv, **_kw):
        calls.append(argv)
        return _Proc()

    monkeypatch.setattr(review_docs.subprocess, "run", fake_run)
    with pytest.raises(review_docs.GitConfigError) as exc:
        review_docs.git_argv("/nowhere", "status")
    assert "bad config line 7" in str(exc.value)
    del calls[:]
    assert review_docs._git("/nowhere", "status") is None
    assert len(calls) == 1 and "config" in calls[0], calls


def test_the_judge_ignores_the_repository_the_parent_was_pointed_at(
    tmp_path, monkeypatch, capsys
):
    """A git hook exports GIT_DIR/GIT_INDEX_FILE for the repository being
    committed. Measured before the fix: under them, `--strict` on another
    repository judged 0 documents and exited 0, because every git call the
    judge made answered for the hook's repository."""
    env = hermetic_git.git_env(tmp_path)
    decoy, other = tmp_path / "decoy", tmp_path / "other"
    decoy.mkdir()
    (decoy / "a").write_text("a\n", encoding="utf-8")
    (other / "docs").mkdir(parents=True)
    (other / "docs" / "x.md").write_text(
        "---\ntitle: x\nupdated: 2020-01-01\n---\n\n# x\n", encoding="utf-8"
    )
    dated = dict(env, GIT_COMMITTER_DATE="@1790000000", GIT_AUTHOR_DATE="@1790000000")
    for top in (decoy, other):
        for argv in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "init"]):
            r = subprocess.run(
                ["git"] + argv, cwd=str(top), env=dated, capture_output=True
            )
            assert r.returncode == 0, r.stderr
    index = decoy / ".git" / "index"
    before = index.read_bytes(), index.stat().st_mtime_ns
    monkeypatch.setenv("GIT_DIR", str(decoy / ".git"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(index))

    rc = review_docs.main(["--root", str(other), "--strict", "--today", "2026-10-06"])
    out = capsys.readouterr().out
    assert rc == 1, out
    assert "STALE docs/x.md" in out and "1 governed document(s)" in out, out
    found = review_docs._git(str(other), "rev-parse", "--absolute-git-dir")
    assert Path(found.strip()).resolve() == (other / ".git").resolve(), found
    assert (index.read_bytes(), index.stat().st_mtime_ns) == before
