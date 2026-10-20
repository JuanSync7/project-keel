"""
title: Unit — canary (each answer set rendered fresh and as an update, then its own make verify)
kind: tests
layer: n/a
summary: scripts/canary.py driven through its injected runner, so no test spawns copier, git or make, and through a fake snapshot, so none clones a tree. A template root in pytest's tmp_path holds the config and CHANGELOG.md each case needs. The previous release is the newest dated CHANGELOG heading whose tag exists and is a strict ancestor of HEAD (the tag HEAD itself carries is skipped, so the release step updates from the release before), and with none the update path is refused with USAGE before anything renders, while `--path fresh` judges normally. Each answer set and path prints one line naming the last step reached, the verdict, the log and the elapsed seconds; a red step names that step, a conflict the update leaves fails the `update` step and nothing after it runs, every set runs after a red one, and the run exits FAILURE naming each kept project. A passing project is removed through the injected remove, a failing one, or one whose step raised, is kept. Zero answer sets, or a `--set` filter leaving none, judge nothing (NOTHING_JUDGED); an unknown `--set` name is USAGE. The pool never runs more pairs at once than canary.workers, 1 when the key is unset. A scratch root under the system temporary directory, or inside the template and tracked or not ignored by git, is a config fault (CONFIG) naming canary.scratch_root, and the same root once git ignores it is accepted. A set key copier.yml does not ask is a config fault naming `<set>.<key>` before any render, and the update step hands copier the set's answers file again. A second run with the same arguments prints the same verdicts and leaves the same scratch tree, its own run directory replaced, which is the module's fixed point. Excluded from generated projects with the doer.
"""

import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import canary  # noqa: E402
from exit_codes import ExitCode  # noqa: E402

pytestmark = pytest.mark.unit

_CHANGELOG = (
    "# Changelog\n\n"
    "Generated projects record `--vcs-ref v0.3.0` (a mention, not a heading).\n\n"
    "## [Unreleased]\n\n- next\n\n"
    "## [0.3.0] — 2026-10-15\n\n- three\n\n"
    "## [0.2.2] — 2026-10-09\n\n- two two\n\n"
    "## [0.2.1] — 2026-10-09\n\n- two one\n\n"
    "## Template foundations (pre-0.1.0)\n"
)
_TWO_SETS = {"alpha": {}, "beta": {"frontend_stack": "none"}}
_QUESTIONS = ("frontend_stack", "showcase", "transports")


class FakeGit(object):
    """git as a table: *tags* maps a tag to its commit, *head* is HEAD's
    commit, *ancestors* the (older, newer) commit pairs that hold; every call
    is recorded, and `ls-files -u` writes *unmerged* into the log it is given.
    `check-ignore` answers yes only for a path *ignored* names, as git does
    for the repository's own `.gitignore`."""

    def __init__(
        self,
        tags=None,
        head="h",
        ancestors=(),
        unmerged="",
        tracked=(),
        ignored=(".canary/",),
    ):
        self.tags = dict(tags or {})
        self.head = head
        self.ancestors = set(ancestors)
        self.unmerged = unmerged
        self.tracked = set(tracked)
        self.ignored = set(ignored)
        self.calls = []

    def _commit(self, ref):
        return self.head if ref == "HEAD" else self.tags.get(ref)

    def __call__(self, args, cwd, log):
        self.calls.append(list(args))
        if args[:2] == ["rev-parse", "--verify"]:
            ref = args[-1].replace("^{commit}", "")
            return (0 if ref in self.tags else 1), log
        if args[:2] == ["merge-base", "--is-ancestor"]:
            older, newer = self._commit(args[2]), self._commit(args[3])
            return (0 if older == newer or (older, newer) in self.ancestors else 1), log
        if args[:2] == ["ls-files", "--error-unmatch"]:
            return (0 if args[-1] in self.tracked else 1), log
        if args[:2] == ["check-ignore", "-q"]:
            return (0 if args[-1] in self.ignored else 1), log
        if args[:2] == ["ls-files", "-u"]:
            with open(log, "a", encoding="utf-8") as fh:
                fh.write(self.unmerged)
            return 0, log
        return 0, log


class FakeTool(object):
    """copier or make: status 0 unless *red* maps (dest basename, first
    argument) to a status; records each call, with the peak concurrency."""

    def __init__(self, red=None, sleep=0.0, raise_on=None):
        self.red = dict(red or {})
        self.sleep = sleep
        self.raise_on = raise_on
        self.calls = []
        self.running = 0
        self.peak = 0
        self._lock = threading.Lock()

    def __call__(self, args, cwd, log):
        dest = (
            os.path.basename(args[-1])
            if args[0] in ("copy", "update")
            else (os.path.basename(cwd))
        )
        with self._lock:
            self.calls.append((dest, args[0]))
            self.running += 1
            self.peak = max(self.peak, self.running)
        try:
            if self.sleep:
                time.sleep(self.sleep)
            if self.raise_on == (dest, args[0]):
                raise RuntimeError("the fake broke mid-step")
            if args[0] == "copy":
                os.makedirs(args[-1], exist_ok=True)
            return self.red.get((dest, args[0]), 0), log
        finally:
            with self._lock:
                self.running -= 1


@pytest.fixture
def root(tmp_path, monkeypatch):
    """A template root holding CHANGELOG.md, with the system temporary
    directory moved off pytest's tmp_path so a scratch root there is legal,
    and the snapshot faked: a directory, no clone."""
    repo = tmp_path / "template"
    (repo / "config").mkdir(parents=True)
    (repo / "CHANGELOG.md").write_text(_CHANGELOG, encoding="utf-8")
    monkeypatch.setattr(canary, "ROOT", str(repo))
    monkeypatch.delenv("KEEL_CANARY_SCRATCH", raising=False)
    systemp = tmp_path / "systemp"
    systemp.mkdir()
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(systemp))

    def fake_snapshot(template, scratch, extra, skip=(), label="snapshot"):
        snap = os.path.join(scratch, "template")
        os.makedirs(snap)
        return snap, []

    monkeypatch.setattr(canary, "snapshot_working_tree", fake_snapshot)
    # copier.yml's questions, without the YAML parser the template extra brings.
    monkeypatch.setattr(canary, "asked_questions", lambda _root: set(_QUESTIONS))
    return repo


def _config(root, **canary_block):
    block = {"answer_sets": _TWO_SETS, "scratch_root": ".canary"}
    block.update(canary_block)
    block = {k: v for k, v in block.items() if v is not None}
    (root / "config" / "project.json").write_text(
        json.dumps({"canary": block}), encoding="utf-8"
    )


def _released_git():
    """HEAD one commit past v0.3.0, every tag an ancestor of the next."""
    return FakeGit(
        tags={"v0.3.0": "c3", "v0.2.2": "c22", "v0.2.1": "c21"},
        head="h",
        ancestors={
            ("c3", "h"),
            ("c22", "h"),
            ("c21", "h"),
            ("c22", "c3"),
            ("c21", "c3"),
        },
    )


def _runner(git=None, copier=None, make=None, removed=None):
    removed = [] if removed is None else removed

    def remove(path):
        removed.append(path)
        import shutil

        shutil.rmtree(path)

    return canary.Runner(
        copier=copier or FakeTool(),
        git=git or _released_git(),
        make=make or FakeTool(),
        remove=remove,
    )


def _lines(out):
    return [line for line in out.splitlines() if line.strip()]


# --- the previous release ----------------------------------------------------


def test_previous_tag_is_the_newest_released_heading_that_is_a_strict_ancestor_of_head():
    past = _released_git()
    assert canary.previous_tag(_CHANGELOG, past, "here") == "v0.3.0"

    at_release = _released_git()
    at_release.head = "c3"
    assert canary.previous_tag(_CHANGELOG, at_release, "here") == "v0.2.2"

    missing = _released_git()
    del missing.tags["v0.3.0"]
    assert canary.previous_tag(_CHANGELOG, missing, "here") == "v0.2.2"

    diverged = _released_git()
    diverged.ancestors.discard(("c3", "h"))
    assert canary.previous_tag(_CHANGELOG, diverged, "here") == "v0.2.2"

    # A heading with no date, a mention in prose and [Unreleased] name no
    # release: with every dated tag gone nothing qualifies.
    none = FakeGit(tags={"vUnreleased": "x", "v0.3.0-rc": "y"}, head="h")
    assert canary.previous_tag(_CHANGELOG, none, "here") is None


def test_the_release_heading_grammar_takes_only_dated_version_headings():
    text = (
        "## [1.2.3] — 2026-01-02\n"
        "## [1.2.4]\n"
        "## [1.2.5] — not a date\n"
        "### [1.2.6] — 2026-01-02\n"
        " ## [1.2.7] — 2026-01-02\n"
        "## [1.2.8] — 2026-13-40\n"
        "## [Unreleased]\n"
        "## [0.9.0] — 2025-12-31\n"
    )
    assert canary.released_versions(text) == ["1.2.3", "0.9.0"]


def test_no_qualifying_tag_refuses_with_usage_before_any_render(root, capsys):
    _config(root)
    copier = FakeTool()
    git = FakeGit(tags={}, head="h")
    rc = canary.main([], runner=_runner(git=git, copier=copier))
    err = capsys.readouterr().err
    assert rc == ExitCode.USAGE
    assert "no previous release to update from" in err
    assert "CHANGELOG.md" in err and "git tag --list" in err
    assert copier.calls == []

    copier = FakeTool()
    rc = canary.main(["--path", "fresh"], runner=_runner(git=git, copier=copier))
    assert rc == ExitCode.SUCCESS
    assert {call[1] for call in copier.calls} == {"copy"}


# --- the verdict lines -------------------------------------------------------


def test_each_set_and_path_prints_one_line_with_step_and_verdict(root, capsys):
    _config(root)
    rc = canary.main([], runner=_runner())
    lines = _lines(capsys.readouterr().out)
    assert rc == ExitCode.SUCCESS
    assert len(lines) == 4, lines
    seen = set()
    for line in lines:
        name, path, step, verdict, log, elapsed = line.split(" ")
        assert (step, verdict) == ("verify", "pass"), line
        assert os.path.isfile(log), line
        assert elapsed.endswith("s") and elapsed[:-1].isdigit(), line
        seen.add((name, path))
    assert seen == {(s, p) for s in _TWO_SETS for p in ("fresh", "update")}

    make = FakeTool(red={("alpha-fresh", "fe-install"): 2})
    rc = canary.main([], runner=_runner(make=make))
    lines = _lines(capsys.readouterr().out)
    assert rc == ExitCode.FAILURE
    assert [ln for ln in lines if ln.startswith("alpha fresh ")][0].split(" ")[2:4] == [
        "fe-install",
        "fail",
    ]
    # The frontend steps run in every project, with or without an app: the
    # Makefile's FE_APPS decides what they install, so the canary keeps no
    # second copy of the app layout.
    beta = [target for dest, target in make.calls if dest == "beta-fresh"]
    assert beta == ["fe-install", "fe-browsers", "secrets-install", "verify"], beta


def test_a_pass_deletes_the_project_and_a_fail_keeps_and_names_it(root, capsys):
    _config(root)
    removed = []
    make = FakeTool(red={("beta-update", "verify"): 1})
    rc = canary.main([], runner=_runner(make=make, removed=removed))
    err = capsys.readouterr().err
    assert rc == ExitCode.FAILURE
    names = sorted(os.path.basename(p) for p in removed)
    assert names == ["alpha-fresh", "alpha-update", "beta-fresh"], names
    kept = list(Path(str(root), ".canary").glob("*/beta-update"))
    assert len(kept) == 1 and kept[0].is_dir()
    assert str(kept[0]) in err

    removed = []
    copier = FakeTool(raise_on=("alpha-fresh", "copy"))
    rc = canary.main(
        ["--set", "alpha", "--path", "fresh"],
        runner=_runner(copier=copier, removed=removed),
    )
    captured = capsys.readouterr()
    assert rc == ExitCode.FAILURE
    assert removed == []
    line = _lines(captured.out)[0]
    assert line.split(" ")[:4] == ["alpha", "fresh", "copy", "fail"], line
    log = line.split(" ")[4]
    assert "the fake broke mid-step" in Path(log).read_text(encoding="utf-8")
    assert "alpha-fresh" in captured.err


def test_every_set_runs_after_a_red_one_and_the_run_exits_failure(root, capsys):
    _config(root)
    make = FakeTool(red={("alpha-fresh", "verify"): 1, ("alpha-update", "verify"): 1})
    rc = canary.main([], runner=_runner(make=make))
    lines = _lines(capsys.readouterr().out)
    assert rc == ExitCode.FAILURE
    assert ("beta-fresh", "verify") in make.calls
    assert ("beta-update", "verify") in make.calls
    # Every pair is reported too, not only the ones before the first red.
    verdicts = sorted(tuple(ln.split(" ")[:4]) for ln in lines)
    assert verdicts == [
        ("alpha", "fresh", "verify", "fail"),
        ("alpha", "update", "verify", "fail"),
        ("beta", "fresh", "verify", "pass"),
        ("beta", "update", "verify", "pass"),
    ], lines


def test_zero_answer_sets_judge_nothing(root, capsys):
    _config(root, answer_sets={})
    assert canary.main([], runner=_runner()) == ExitCode.NOTHING_JUDGED
    _config(root)
    assert canary.main(["--set", "nope"], runner=_runner()) == ExitCode.USAGE
    err = capsys.readouterr().err
    assert "nope" in err and "alpha" in err


def test_an_update_that_leaves_conflicts_fails_at_the_update_step(root, capsys):
    _config(root, answer_sets={"alpha": {}})
    git = _released_git()
    git.unmerged = "100644 abc 1\tMakefile\x00"
    make = FakeTool()
    rc = canary.main([], runner=_runner(git=git, make=make))
    lines = _lines(capsys.readouterr().out)
    assert rc == ExitCode.FAILURE
    update = [ln for ln in lines if ln.startswith("alpha update ")][0]
    assert update.split(" ")[2:4] == ["update", "fail"], update
    assert ("alpha-update", "verify") not in make.calls
    assert ("alpha-fresh", "verify") in make.calls


def test_a_conflict_marker_left_in_a_file_fails_at_the_update_step(root, capsys):
    _config(root, answer_sets={"alpha": {}})

    class MarkingCopier(FakeTool):
        def __call__(self, args, cwd, log):
            status, log = FakeTool.__call__(self, args, cwd, log)
            if args[0] == "update":
                hunk = "\n".join(
                    ["<" * 7 + " before", "a", "=" * 7, "b", ">" * 7 + " after"]
                )
                with open(os.path.join(args[-1], "Makefile"), "w") as fh:
                    fh.write(hunk + "\n")
            return status, log

    make = FakeTool()
    rc = canary.main(
        ["--path", "update"], runner=_runner(copier=MarkingCopier(), make=make)
    )
    lines = _lines(capsys.readouterr().out)
    assert rc == ExitCode.FAILURE
    assert lines[0].split(" ")[:4] == ["alpha", "update", "update", "fail"], lines
    assert make.calls == []


def test_the_pool_never_runs_more_children_than_canary_workers(root, capsys):
    for workers in (1, 2):
        _config(root, workers=workers)
        make = FakeTool(sleep=0.3)
        assert canary.main([], runner=_runner(make=make)) == ExitCode.SUCCESS
        assert make.peak == workers, (workers, make.peak)
    _config(root, workers=None)
    make = FakeTool(sleep=0.3)
    assert canary.main([], runner=_runner(make=make)) == ExitCode.SUCCESS
    assert make.peak == 1
    capsys.readouterr()


def test_a_scratch_root_in_system_temp_or_a_tracked_or_unignored_path_is_a_config_fault(
    root, capsys, monkeypatch
):
    _config(root, scratch_root=os.path.join(tempfile.gettempdir(), "canary"))
    copier = FakeTool()
    assert canary.main([], runner=_runner(copier=copier)) == ExitCode.CONFIG
    assert "canary.scratch_root" in capsys.readouterr().err

    _config(root, scratch_root="docs")
    git = _released_git()
    git.tracked = {"docs"}
    assert canary.main([], runner=_runner(git=git, copier=copier)) == ExitCode.CONFIG
    assert "canary.scratch_root" in capsys.readouterr().err

    # Untracked but not ignored: the projects would be files git offers to commit.
    _config(root, scratch_root="docs/x")
    assert canary.main([], runner=_runner(copier=copier)) == ExitCode.CONFIG
    err = capsys.readouterr().err
    assert "git does not ignore it" in err and "canary.scratch_root" in err
    # The same root once git ignores it is accepted: the refusal above is the
    # ignore rule, not the path.
    git = _released_git()
    git.ignored = {"docs/x/"}
    assert canary.main(["--path", "fresh"], runner=_runner(git=git)) == ExitCode.SUCCESS
    capsys.readouterr()

    # The variable is the same key: a farm job's value is judged the same way.
    _config(root)
    monkeypatch.setenv("KEEL_CANARY_SCRATCH", os.path.join(tempfile.gettempdir(), "x"))
    assert canary.main([], runner=_runner(copier=copier)) == ExitCode.CONFIG
    assert "KEEL_CANARY_SCRATCH" in capsys.readouterr().err
    assert copier.calls == []


def test_a_rerun_replaces_its_own_run_directory_and_prints_the_same_verdicts(
    root, capsys
):
    _config(root)
    make = FakeTool(red={("beta-fresh", "verify"): 1})

    def verdicts():
        rc = canary.main([], runner=_runner(make=make))
        lines = _lines(capsys.readouterr().out)
        tree = sorted(
            str(p.relative_to(root / ".canary"))
            for p in (root / ".canary").rglob("*")
            if p.parent.name != "tmp"
        )
        return rc, [ln.rsplit(" ", 1)[0] for ln in lines], tree

    first, second = verdicts(), verdicts()
    assert first[0] == ExitCode.FAILURE
    assert first[1] == second[1]
    assert first[2] == second[2]


class RecordingCopier(FakeTool):
    """copier that also keeps each call's whole argument list."""

    def __init__(self):
        FakeTool.__init__(self)
        self.argv = []

    def __call__(self, args, cwd, log):
        self.argv.append(list(args))
        return FakeTool.__call__(self, args, cwd, log)


def test_an_answer_naming_no_copier_question_is_refused_before_any_render(root, capsys):
    # copier ignores a data key that is not a question and renders the
    # default, so a typo would verify a project the set never asked for.
    _config(root, answer_sets={"alpha": {}, "beta": {"frontend_stak": "none"}})
    copier = RecordingCopier()
    assert canary.main([], runner=_runner(copier=copier)) == ExitCode.CONFIG
    err = capsys.readouterr().err
    assert "beta.frontend_stak" in err and "copier.yml" in err, err
    assert copier.argv == []
    # The same set spelled right renders.
    _config(root, answer_sets={"beta": {"frontend_stack": "none"}})
    assert canary.main([], runner=_runner(copier=copier)) == ExitCode.SUCCESS
    capsys.readouterr()


def test_the_update_step_carries_the_sets_answers(root, capsys):
    # A question added after the previous tag is ignored by the copy from that
    # tag; only answers handed to the update reach the project it verifies.
    answers = {"frontend_stack": "none", "showcase": False}
    _config(root, answer_sets={"alpha": answers})
    copier = RecordingCopier()
    assert canary.main(["--path", "update"], runner=_runner(copier=copier)) == (
        ExitCode.SUCCESS
    )
    capsys.readouterr()
    updates = [argv for argv in copier.argv if argv[0] == "update"]
    assert len(updates) == 1, copier.argv
    given = updates[0][updates[0].index("--data-file") + 1]
    with open(given, encoding="utf-8") as fh:
        assert json.load(fh) == answers
