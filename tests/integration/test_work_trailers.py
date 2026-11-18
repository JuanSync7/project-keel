"""
title: Integration — every Slice: trailer names a slice the plan declares
kind: tests
layer: n/a
summary: The git half of the work-naming rule (CONVENTIONS §20) as a gate. A commit's trailer block carries at most one `Slice:` trailer, and its value is one of this repository's own slice ids that a plan doc in the tree declares, never a prefixed cross-repository id; an optional `Backlog:` trailer matches config/project.json `work_naming.backlog_id`; the keys are spelled as configured; and a `Slice:` or `Backlog:` line outside the trailer block is a finding, because git does not read it as a trailer. Commits reachable from `work_naming.adoption_boundary` are not judged, and a boundary that does not resolve to an ancestor of HEAD fails closed. Not a check_* letter on purpose (ADR-K-0009): check_structure.py does not shell to git. Absent is not broken for the trailer gate: no git, no repository, no commit, or no trailer in the judged range is a stated skip that names the count. The independent subject gate imports scripts/commit_subject.py, judges every non-merge subject after commit_subject.adoption_boundary even without trailers, counts merges separately, and refuses a zero-commit range. The installed shipped commit-msg hook refuses bad subjects, accepts git merge and autosquash messages, and keeps history strict.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, cast

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))

import check_structure as cs  # noqa: E402
import child_env  # noqa: E402
import commit_subject  # noqa: E402
import config_loader  # noqa: E402
import review_docs  # noqa: E402
from scripts.bounded_match import match_values  # noqa: E402

from hermetic_git import git_env  # noqa: E402

pytestmark = pytest.mark.integration

# A commit's fields and records are split on bytes git never writes into a
# message: NUL between fields, the record separator after each commit.
_FIELD = "\x00"
_RECORD = "\x1e"
_LOG_FORMAT = "%H%x00%(trailers:only,unfold)%x00%B%x1e"
_TRAILER_LINE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9-]*)\s*:\s*(.*)$")


class TrailerGateError(AssertionError):
    """The gate cannot judge: a boundary that does not resolve, or a git call
    that fails where it should not. Raised, never skipped."""


def _git(root, env, *args):
    proc = subprocess.run(
        review_docs.git_argv(str(root), *args),
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        env=env,
    )
    return proc.returncode, proc.stdout, proc.stderr


def trailer_findings(root, env=None):
    """Judge the work trailers of the commits at *root*.

    Returns {"skip": reason or None, "commits": n, "trailers": n, "findings":
    ["<sha12>: message", ...]}. Raises TrailerGateError when the configured
    adoption boundary is not an ancestor of HEAD."""
    env = child_env.build_child_env() if env is None else env
    out = {"skip": None, "commits": 0, "trailers": 0, "findings": []}
    if shutil.which("git") is None:
        out["skip"] = "no git on PATH -- trailers cannot be read"
        return out
    with open(
        os.path.join(str(root), "config", "project.json"), encoding="utf-8"
    ) as fh:
        manifest = json.load(fh)
    policy, perrs = cs.work_naming_policy(manifest)
    if policy is None:
        raise TrailerGateError("config/project.json: " + "; ".join(perrs))
    rc, inside, _e = _git(root, env, "rev-parse", "--is-inside-work-tree")
    if rc != 0 or inside.strip() != "true":
        out["skip"] = "not a git work tree -- trailers cannot be read"
        return out
    rc, _o, _e = _git(root, env, "rev-parse", "--verify", "-q", "HEAD")
    if rc != 0:
        out["skip"] = "no commit yet -- no trailer to judge"
        return out
    span = "HEAD"
    boundary = policy["adoption_boundary"]
    if boundary is not None:
        rc, _o, err = _git(
            root, env, "rev-parse", "--verify", "-q", boundary + "^{commit}"
        )
        if rc != 0:
            raise TrailerGateError(
                "work_naming.adoption_boundary %r does not resolve to a commit"
                % boundary
            )
        rc, _o, err = _git(root, env, "merge-base", "--is-ancestor", boundary, "HEAD")
        if rc != 0:
            raise TrailerGateError(
                "work_naming.adoption_boundary %r is not an ancestor of HEAD: "
                "the range it opens would judge nothing it means to" % boundary
            )
        span = boundary + "..HEAD"
    rc, log, err = _git(root, env, "log", "--format=" + _LOG_FORMAT, span)
    if rc != 0:
        raise TrailerGateError("git log %s failed: %s" % (span, err.strip()))
    grammar = cs.id_grammar(policy)
    declared = set(
        cs.plan_inventory(str(root), policy, cs.work_owner(manifest))["slices"]
    )
    keys = {
        policy["slice_trailer"].lower(): policy["slice_trailer"],
        policy["backlog_trailer"].lower(): policy["backlog_trailer"],
    }
    body_key = re.compile(
        r"^\s*(%s)\s*:\s*(.*?)\s*$" % "|".join(re.escape(k) for k in sorted(keys)),
        re.IGNORECASE,
    )
    records = [
        record.lstrip("\n") for record in log.split(_RECORD) if record.lstrip("\n")
    ]
    backlog_values = []
    for record in records:
        _sha, trailers, body = record.split(_FIELD, 2)
        for line in trailers.splitlines():
            m = _TRAILER_LINE.match(line)
            if m and m.group(1).lower() == policy["backlog_trailer"].lower():
                backlog_values.append(m.group(2).strip())
        for line in body.splitlines():
            m = body_key.match(line)
            if m and keys[m.group(1).lower()] == policy["backlog_trailer"]:
                backlog_values.append(m.group(2))
    backlog_matches = dict(
        zip(
            backlog_values,
            match_values(
                policy["backlog_id"],
                "work_naming.backlog_id",
                backlog_values,
                "search",
                root=str(root),
            ),
            strict=True,
        )
    )
    # A line is a misplaced trailer only when its value has the shape its key
    # carries; "slice: split the parser" in an old history is prose.
    shaped: dict[str, Callable[[str], bool]] = {
        policy["slice_trailer"]: lambda v: grammar["mention"].fullmatch(v) is not None,
        policy["backlog_trailer"]: lambda v: backlog_matches[v],
    }
    for record in records:
        sha, trailers, body = record.split(_FIELD, 2)
        out["commits"] += 1
        tag = sha[:12] + ": "
        parsed = {}
        for line in trailers.splitlines():
            m = _TRAILER_LINE.match(line)
            if not m or m.group(1).lower() not in keys:
                continue
            key, value = m.group(1), m.group(2).strip()
            out["trailers"] += 1
            want = keys[key.lower()]
            parsed.setdefault(want, []).append(value)
            if key != want:
                out["findings"].append(
                    tag + "trailer key %r is spelled %r (work_naming)" % (key, want)
                )
        slices = parsed.get(policy["slice_trailer"], [])
        if len(slices) > 1:
            out["findings"].append(
                tag
                + "more than one %s: trailer (%s); a commit delivers one slice"
                % (policy["slice_trailer"], ", ".join(slices))
            )
        for value in slices:
            mention = grammar["mention"].fullmatch(value)
            if mention and mention.group("prefix"):
                out["findings"].append(
                    tag + "%s: %s carries a repository prefix; a commit names a "
                    "slice of its own repository, bare"
                    % (policy["slice_trailer"], value)
                )
            elif not grammar["slice"].fullmatch(value):
                out["findings"].append(
                    tag
                    + "%s: %r is not a %s id"
                    % (policy["slice_trailer"], value, policy["slice_id"])
                )
            elif value not in declared:
                out["findings"].append(
                    tag
                    + "%s: %s names no slice a plan doc in the tree declares"
                    % (policy["slice_trailer"], value)
                )
        for value in parsed.get(policy["backlog_trailer"], []):
            if not backlog_matches[value]:
                out["findings"].append(
                    tag
                    + "%s: %r does not match work_naming.backlog_id"
                    % (policy["backlog_trailer"], value)
                )
        seen = {}
        for line in body.splitlines():
            m = body_key.match(line)
            if m:
                want = keys[m.group(1).lower()]
                if shaped[want](m.group(2)):
                    seen[want] = seen.get(want, 0) + 1
        for want in sorted(seen):
            read = [v for v in parsed.get(want, []) if shaped[want](v)]
            stray = seen[want] - len(read)
            if stray > 0:
                out["findings"].append(
                    tag + "%d %s: line(s) outside the trailer block; git reads a "
                    "trailer only in the message's last paragraph" % (stray, want)
                )
    if out["commits"] == 0:
        out["skip"] = "no commit after work_naming.adoption_boundary %s" % boundary
    elif out["trailers"] == 0 and not out["findings"]:
        out["skip"] = "no %s: or %s: trailer in %d commit(s)" % (
            policy["slice_trailer"],
            policy["backlog_trailer"],
            out["commits"],
        )
    return out


def subject_findings(root, env=None):
    """Judge non-merge subjects, counting merges separately and refusing zero."""
    env = child_env.build_child_env() if env is None else env
    out = {"skip": None, "refusal": None, "commits": 0, "merges": 0, "findings": []}
    if shutil.which("git") is None:
        out["skip"] = "no git on PATH -- subjects cannot be read"
        return out
    try:
        policy = commit_subject.load_policy(str(root))
    except config_loader.ConfigError as exc:
        raise TrailerGateError(str(exc)) from exc
    rc, inside, _e = _git(root, env, "rev-parse", "--is-inside-work-tree")
    if rc != 0 or inside.strip() != "true":
        out["skip"] = "not a git work tree -- subjects cannot be read"
        return out
    rc, _o, _e = _git(root, env, "rev-parse", "--verify", "-q", "HEAD")
    if rc != 0:
        out["refusal"] = "no commit yet -- 0 commit(s) judged"
        return out
    span = "HEAD"
    boundary = policy["adoption_boundary"]
    if boundary is not None:
        rc, resolved, _e = _git(
            root, env, "rev-parse", "--verify", "-q", boundary + "^{commit}"
        )
        if rc != 0:
            raise TrailerGateError(
                "commit_subject.adoption_boundary %r does not resolve to a commit"
                % boundary
            )
        resolved = resolved.strip()
        rc, _o, _e = _git(root, env, "merge-base", "--is-ancestor", resolved, "HEAD")
        if rc != 0:
            raise TrailerGateError(
                "commit_subject.adoption_boundary %r is not an ancestor of HEAD: "
                "the range it opens would judge nothing it means to" % boundary
            )
        span = resolved + "..HEAD"
    rc, log, err = _git(root, env, "log", "--format=%H%x00%P%x00%s%x1e", span)
    if rc != 0:
        raise TrailerGateError("git log %s failed: %s" % (span, err.strip()))
    for record in log.split(_RECORD):
        record = record.lstrip("\n")
        if not record:
            continue
        sha, parents, subject = record.split(_FIELD, 2)
        if len(parents.split()) > 1:
            out["merges"] += 1
            continue
        out["commits"] += 1
        out["findings"].extend(
            sha[:12] + ": " + finding
            for finding in commit_subject.subject_findings(subject, policy)
        )
    if out["commits"] == 0:
        out["refusal"] = (
            "no commit after commit_subject.adoption_boundary %s; 0 commit(s) judged"
            % boundary
        )
    return out


def test_every_commit_subject_matches_policy():
    """The real history uses the same matcher as the message-file CLI."""
    result = subject_findings(_ROOT)
    if result["skip"]:
        pytest.skip(result["skip"])
    assert result["refusal"] is None, result
    assert not result["findings"], (
        "%d finding(s) in %d commit(s), %d merge(s) not judged:\n%s"
        % (
            len(result["findings"]),
            result["commits"],
            result["merges"],
            "\n".join(result["findings"]),
        )
    )


def test_every_work_trailer_names_a_declared_slice():
    """The real repository. A commit that delivers a slice says which, so the
    ledger, the plan row and the commit name the same unit of work."""
    result = trailer_findings(_ROOT)
    if result["skip"]:
        pytest.skip(result["skip"])
    assert not result["findings"], "%d finding(s) in %d commit(s):\n%s" % (
        len(result["findings"]),
        result["commits"],
        "\n".join(result["findings"]),
    )


# --- the rule, pinned on throwaway repositories -------------------------------

_PLAN = (
    "---\ntitle: t\nkind: design\nid: x-plan\n---\n\n# Plan\n\n"
    "## CMP-1 — first\n\n| Slice | Subject |\n|---|---|\n| CMP-1.S1 | a |\n"
    "| CMP-1.S2 | b |\n"
)


def _run(repo, env, *argv):
    r = subprocess.run(
        ("git",) + argv,
        cwd=str(repo),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    assert r.returncode == 0, "git %s: %s" % (" ".join(argv), r.stderr)
    return r.stdout.strip()


@pytest.fixture
def toy(tmp_path):
    """A repository with the default block, a plan of CMP-1.S1..S2 and one
    trailer-free commit; returns (root, env, commit)."""
    if shutil.which("git") is None:
        pytest.skip("no git on PATH")
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    (root / "docs" / "design").mkdir(parents=True)
    with open(str(_ROOT / "config" / "project.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    data = {
        "name": "demo",
        "work_naming": manifest["work_naming"],
        "tests": manifest["tests"],
    }
    (root / "config" / "project.json").write_text(json.dumps(data), encoding="utf-8")
    (root / "docs" / "design" / "plan.md").write_text(_PLAN, encoding="utf-8")
    env = git_env(tmp_path)
    _run(root, env, "init", "-q")
    _run(root, env, "add", "-A")
    _run(root, env, "commit", "-q", "-m", "init")

    def commit(message):
        _run(root, env, "commit", "-q", "--allow-empty", "-m", message)
        return _run(root, env, "rev-parse", "HEAD")

    return root, env, commit


def _set_boundary(root, boundary):
    path = root / "config" / "project.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["work_naming"]["adoption_boundary"] = boundary
    path.write_text(json.dumps(data), encoding="utf-8")


def test_a_well_formed_trailer_block_is_clean(toy):
    root, env, commit = toy
    commit(
        "feat: x\n\nWhy.\n\nSlice: CMP-1.S2\nBacklog: KEEL-12\n"
        "Co-Authored-By: A <a@example.invalid>"
    )
    result = trailer_findings(root, env)
    assert result == {"skip": None, "commits": 2, "trailers": 2, "findings": []}


@pytest.mark.parametrize(
    "message, says",
    [
        ("x\n\nSlice: CMP-1.S1\nSlice: CMP-1.S2", "more than one"),
        ("x\n\nSlice: jarvis:CMP-1.S1", "repository prefix"),
        ("x\n\nSlice: demo:CMP-1.S1", "repository prefix"),
        ("x\n\nSlice: CMP-1-S1", "is not a"),
        ("x\n\nSlice: C2-4", "is not a"),
        ("x\n\nSlice: CMP-1.S9", "names no slice"),
        ("x\n\nSlice: CMP-1.S1\nBacklog: keel-12", "backlog_id"),
        ("x\n\nslice: CMP-1.S1", "is spelled 'Slice'"),
        ("x\n\nSlice: CMP-1.S1\n\nMore prose after it.", "outside the trailer block"),
    ],
    ids=[
        "two",
        "foreign-prefix",
        "own-prefix",
        "hyphen",
        "retired",
        "undeclared",
        "backlog",
        "case",
        "misplaced",
    ],
)
def test_a_bad_trailer_is_a_finding(toy, message, says):
    root, env, commit = toy
    sha = commit(message)
    result = trailer_findings(root, env)
    assert result["skip"] is None, result
    assert len(result["findings"]) == 1, result
    assert result["findings"][0].startswith(sha[:12] + ": "), result
    assert says in result["findings"][0], result


def test_a_campaign_heading_with_the_own_prefix_declares_its_slices(toy):
    """check_Z reads `## demo:CMP-1` as this repository's campaign; the
    trailer gate reads the same plan the same way, so the two agree."""
    root, env, commit = toy
    plan = root / "docs" / "design" / "plan.md"
    plan.write_text(_PLAN.replace("## CMP-1", "## demo:CMP-1"), encoding="utf-8")
    commit("x\n\nSlice: CMP-1.S1")
    result = trailer_findings(root, env)
    assert result == {"skip": None, "commits": 2, "trailers": 1, "findings": []}


@pytest.mark.parametrize(
    "message",
    [
        "slice: split the parser into two passes",
        "x\n\nBacklog: nothing left after the sweep, see notes.\n\nMore.",
        "x\n\nSlice: the second half waits.\n\nMore.",
    ],
    ids=["subject", "backlog-prose", "slice-prose"],
)
def test_prose_that_opens_with_a_trailer_key_is_not_a_trailer(toy, message):
    """A history written before adoption may start a line with `slice:` or
    `Backlog:` in prose. Only a line whose value is shaped like the id the
    key carries is a misplaced trailer; anything else is prose and the
    trailer-free history stays a stated skip."""
    root, env, commit = toy
    commit(message)
    result = trailer_findings(root, env)
    assert result["findings"] == [], result
    assert result["skip"] == "no Slice: or Backlog: trailer in 2 commit(s)", result


@pytest.mark.parametrize(
    "message, key",
    [
        ("x\n\nSlice: CMP-1.S1\n\nMore prose after it.", "Slice"),
        ("x\n\nBacklog: KEEL-12\n\nMore prose after it.", "Backlog"),
        ("Slice: CMP-1.S1", "Slice"),
    ],
    ids=["slice", "backlog", "as-subject"],
)
def test_an_id_shaped_line_outside_the_trailer_block_is_a_finding(toy, message, key):
    root, env, commit = toy
    sha = commit(message)
    result = trailer_findings(root, env)
    assert result["findings"] == [
        sha[:12] + ": 1 %s: line(s) outside the trailer block; git reads a "
        "trailer only in the message's last paragraph" % key
    ], result


def test_commits_before_the_adoption_boundary_are_not_judged(toy):
    root, env, commit = toy
    boundary = commit("old\n\nSlice: CMP-9.S9")
    commit("new\n\nSlice: CMP-1.S1")
    _set_boundary(root, boundary)
    result = trailer_findings(root, env)
    assert result == {"skip": None, "commits": 1, "trailers": 1, "findings": []}
    _set_boundary(root, None)
    assert len(trailer_findings(root, env)["findings"]) == 1


def test_a_boundary_off_the_history_fails_closed(toy):
    root, env, commit = toy
    _set_boundary(root, "no-such-ref")
    with pytest.raises(TrailerGateError, match="does not resolve"):
        trailer_findings(root, env)
    orphan = _run(root, env, "commit-tree", "HEAD^{tree}", "-m", "orphan")
    _set_boundary(root, orphan)
    with pytest.raises(TrailerGateError, match="not an ancestor"):
        trailer_findings(root, env)


def test_a_missing_block_fails_closed_and_says_only_what_is_known(toy):
    """With no grammar there is nothing to judge a trailer against, so the gate
    refuses; and a project without a plan doc is not told it has one."""
    root, env, _commit = toy
    (root / "docs" / "design" / "plan.md").unlink()
    (root / "config" / "project.json").write_text('{"name": "demo"}', encoding="utf-8")
    with pytest.raises(TrailerGateError) as caught:
        trailer_findings(root, env)
    message = str(caught.value)
    assert "work_naming is missing" in message
    assert "plan doc" not in message


def test_nothing_to_judge_is_a_stated_skip_with_its_count(toy):
    root, env, commit = toy
    commit("plain\n\nCo-Authored-By: A <a@example.invalid>")
    result = trailer_findings(root, env)
    assert result["skip"] == "no Slice: or Backlog: trailer in 2 commit(s)", result
    _set_boundary(root, "HEAD")
    result = trailer_findings(root, env)
    assert result["commits"] == 0 and result["skip"].startswith("no commit after"), (
        result
    )


def test_the_gate_is_a_fixed_point(toy):
    """Reading twice gives one answer: the judge writes nothing."""
    root, env, commit = toy
    commit("x\n\nSlice: CMP-1.S9")
    assert trailer_findings(root, env) == trailer_findings(root, env)


@pytest.mark.parametrize("in_block", [True, False], ids=["trailer", "body"])
def test_backtracking_backlog_pattern_is_refused(toy: Any, *, in_block: bool) -> None:
    root, env, commit = toy
    pattern, value = "^(a+)+$", "a" * 100 + "!"
    path = root / "config" / "project.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["work_naming"]["backlog_id"] = pattern
    data["tests"] = {"child_timeout_seconds": 2}
    path.write_text(json.dumps(data), encoding="utf-8")
    commit("x\n\nBacklog: " + value + ("" if in_block else "\n\nMore prose."))
    judge = cast(Callable[..., Any], trailer_findings)
    with pytest.raises(AssertionError) as caught:
        judge(root, env)
    message = str(caught.value)
    assert "work_naming.backlog_id" in message
    assert "tests.child_timeout_seconds" in message
    assert "timeout" in message and "repair" in message
    assert pattern not in message and value not in message


# Subject checks have their own boundary: trailer adoption does not waive them.
def _subject_boundary(root, boundary):
    path = root / "config" / "project.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["commit_subject"] = {
        "types": [
            "feat",
            "fix",
            "docs",
            "test",
            "refactor",
            "ci",
            "chore",
            "style",
            "perf",
            "release",
        ],
        "scope_chars": "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_./,-",
        "adoption_boundary": boundary,
    }
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.mark.parametrize("subject", ["wip", "Update file"])
def test_subject_unstructured_after_valid_commit(toy, subject):
    root, env, commit = toy
    boundary = commit("old bad subject")
    commit("feat: valid")
    sha = commit(subject)
    _subject_boundary(root, boundary)
    result = subject_findings(root, env)
    assert result["commits"] == 2 and result["skip"] is None
    assert len(result["findings"]) == 1
    assert sha[:12] in result["findings"][0]
    assert subject in result["findings"][0]


def test_subject_bad_with_valid_slice(toy):
    root, env, commit = toy
    boundary = _run(root, env, "rev-parse", "HEAD")
    sha = commit("stuff\n\nSlice: CMP-1.S1")
    _subject_boundary(root, boundary)
    result = subject_findings(root, env)
    assert len(result["findings"]) == 1
    assert sha[:12] in result["findings"][0] and "stuff" in result["findings"][0]
    assert not trailer_findings(root, env)["findings"]


def test_subject_trailer_free_range_is_judged(toy):
    root, env, commit = toy
    boundary = _run(root, env, "rev-parse", "HEAD")
    commit("docs: valid without trailers")
    _subject_boundary(root, boundary)
    result = subject_findings(root, env)
    assert result["skip"] is None and result["commits"] == 1
    assert not result["findings"]


def test_subject_zero_range_is_refused(toy):
    root, env, _commit = toy
    _subject_boundary(root, "HEAD")
    result = subject_findings(root, env)
    assert result["commits"] == 0
    assert (
        result["refusal"]
        == "no commit after commit_subject.adoption_boundary HEAD; 0 commit(s) judged"
    )


def test_subject_boundary_fails_closed(toy):
    root, env, _commit = toy
    _subject_boundary(root, "no-such-ref")
    with pytest.raises(
        TrailerGateError, match="commit_subject.adoption_boundary.*does not resolve"
    ):
        subject_findings(root, env)
    orphan = _run(root, env, "commit-tree", "HEAD^{tree}", "-m", "orphan")
    _subject_boundary(root, orphan)
    with pytest.raises(
        TrailerGateError, match="commit_subject.adoption_boundary.*not an ancestor"
    ):
        subject_findings(root, env)


def test_subject_null_boundary_judges_initial_commit(toy):
    root, env, _commit = toy
    _subject_boundary(root, None)
    result = subject_findings(root, env)
    assert result["commits"] == 1 and "init" in result["findings"][0]


def test_subject_merge_is_counted_without_judging(toy):
    root, env, commit = toy
    boundary = _run(root, env, "rev-parse", "HEAD")
    other = commit("feat: side")
    _run(root, env, "checkout", "--detach", boundary)
    commit("fix: main")
    _run(root, env, "merge", "--no-ff", other, "-m", "tool merge subject")
    _subject_boundary(root, boundary)
    result = subject_findings(root, env)
    assert result["commits"] == 2 and result["merges"] == 1
    assert not result["findings"] and result["refusal"] is None


@pytest.mark.parametrize("interpreter", [sys.executable, "/usr/bin/python3"])
@pytest.mark.parametrize(
    "message, expected",
    [
        ("\n# comment\n\nfeat(Core/a,b)!: valid\n\nbody", 0),
        ("wip\n\nSlice: CMP-1.S1", 1),
        (None, 2),
    ],
)
def test_subject_cli(toy, interpreter, message, expected):
    root, _env, _commit = toy
    _subject_boundary(root, None)
    path = root / "message"
    if message is not None:
        path.write_text(message, encoding="utf-8")
    proc = subprocess.run(
        [
            interpreter,
            "-B",
            str(_ROOT / "scripts" / "commit_subject.py"),
            "--message-file",
            str(path),
        ],
        cwd=root,
        env=child_env.build_child_env(),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == expected, proc.stderr
    if expected == 1:
        assert "commit_subject" in proc.stderr and "wip" in proc.stderr
    if expected == 2:
        assert "cannot read message" in proc.stderr


@pytest.mark.parametrize("interpreter", [sys.executable, "/usr/bin/python3"])
@pytest.mark.parametrize(
    "key, value",
    [
        ("types", []),
        ("types", ["feat", "feat"]),
        ("types", ["Feat"]),
        ("types", ["2fix"]),
        ("types", "feat"),
        ("scope_chars", ""),
        ("scope_chars", "a(b"),
        ("scope_chars", "a b"),
        ("adoption_boundary", 7),
    ],
)
def test_subject_cli_malformed_policy(toy, interpreter, key, value):
    root, _env, _commit = toy
    _subject_boundary(root, None)
    path = root / "config" / "project.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["commit_subject"][key] = value
    path.write_text(json.dumps(data), encoding="utf-8")
    message = root / "message"
    message.write_text("feat: valid", encoding="utf-8")
    proc = subprocess.run(
        [
            interpreter,
            "-B",
            str(_ROOT / "scripts" / "commit_subject.py"),
            "--message-file",
            str(message),
        ],
        cwd=root,
        env=child_env.build_child_env(),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 14, proc.stderr
    assert "commit_subject." + key in proc.stderr


@pytest.mark.parametrize(
    "subject",
    [
        "feat: x",
        "fix(core): x",
        "docs!: x",
        "refactor(Core/a_b.c,d-e)!: x",
        "test: x",
        "ci: x",
        "chore: x",
        "style: x",
        "perf: x",
        "release: x",
    ],
)
def test_subject_matcher_accepts_declared_shapes(toy, subject):
    import commit_subject

    root, _env, _commit = toy
    _subject_boundary(root, None)
    assert (
        commit_subject.subject_findings(subject, commit_subject.load_policy(str(root)))
        == []
    )


@pytest.mark.parametrize(
    "subject",
    [
        "",
        "wip",
        "feature: x",
        "feat(): x",
        "feat(bad scope): x",
        "feat: ",
        "feat:  x",
        "feat: x ",
        "feat:x",
        "feat(core)!!: x",
        "feat: x\ny",
        " feat: x",
    ],
)
def test_subject_matcher_refuses_invalid_shapes(toy, subject):
    import commit_subject

    root, _env, _commit = toy
    _subject_boundary(root, None)
    assert commit_subject.subject_findings(
        subject, commit_subject.load_policy(str(root))
    )


@pytest.mark.parametrize("block", [None, {}, {"types": ["feat"]}])
def test_subject_missing_policy_fails_closed(toy, block):
    root, env, _commit = toy
    path = root / "config" / "project.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["commit_subject"] = block
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(TrailerGateError, match="commit_subject"):
        subject_findings(root, env)


def test_subject_matcher_obeys_loaded_vocabulary_and_scope(toy):
    root, _env, _commit = toy
    _subject_boundary(root, None)
    policy = commit_subject.load_policy(str(root))
    policy["types"] = ["feat"]
    policy["scope_chars"] = "abc"
    before = json.dumps(policy)
    assert commit_subject.subject_findings("feat(abc): valid", policy) == []
    assert commit_subject.subject_findings("feat(Z): invalid", policy)
    assert commit_subject.subject_findings("fix: invalid", policy)
    assert json.dumps(policy) == before


def test_subject_types_come_from_config_alone(toy):
    """A project's own type list is the whole vocabulary: an added type
    passes, and a type the list leaves out is refused."""
    root, env, commit = toy
    boundary = _run(root, env, "rev-parse", "HEAD")
    commit("build(deps): pin the toolchain")
    sha = commit("feat: not in this project's list")
    _subject_boundary(root, boundary)
    path = root / "config" / "project.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["commit_subject"]["types"] = ["build", "fix"]
    path.write_text(json.dumps(data), encoding="utf-8")
    result = subject_findings(root, env)
    assert result["commits"] == 2
    assert len(result["findings"]) == 1 and sha[:12] in result["findings"][0]


@pytest.mark.parametrize("prefix", ["fixup! ", "squash! ", "amend! "])
def test_subject_hook_autosquash_is_still_judged_in_history(toy, prefix):
    from test_scratch_root_gate import child_timeout

    root, env, commit = toy
    boundary = _run(root, env, "rev-parse", "HEAD")
    _subject_boundary(root, boundary)
    message = prefix + "feat: original"
    commit(message)
    path = root / "message"
    path.write_text(message, encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            "-B",
            str(_ROOT / "scripts/commit_subject.py"),
            "--message-file",
            str(path),
        ],
        cwd=root,
        env=child_env.build_child_env(),
        capture_output=True,
        text=True,
        timeout=child_timeout(),
    )
    assert proc.returncode == 0, proc.stderr
    assert message in subject_findings(root, env)["findings"][0]


@pytest.mark.parametrize("merging, expected", [(True, 0), (False, 1)])
def test_subject_hook_merge_marker_is_beside_message(toy, merging, expected):
    from test_scratch_root_gate import child_timeout

    root, _env, _commit = toy
    _subject_boundary(root, None)
    gitdir = root / ".git"
    # A different git directory models a linked worktree without consulting git.
    message_dir = root / "worktree-gitdir"
    message_dir.mkdir()
    (gitdir / "MERGE_HEAD").write_text("unrelated", encoding="utf-8")
    if merging:
        (message_dir / "MERGE_HEAD").write_text("side", encoding="utf-8")
    message = message_dir / "COMMIT_EDITMSG"
    message.write_text('Revert "feat: original"', encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            "-B",
            str(_ROOT / "scripts/commit_subject.py"),
            "--message-file",
            str(message),
        ],
        cwd=root,
        env=child_env.build_child_env(),
        capture_output=True,
        text=True,
        timeout=child_timeout(),
    )
    assert proc.returncode == expected, proc.stderr
    if expected:
        assert "commit_subject" in proc.stderr and "Revert" in proc.stderr


@pytest.mark.parametrize("linked", [False, True], ids=["repository", "worktree"])
def test_subject_installed_hook_refuses_bad_and_allows_git_messages(tmp_path, linked):
    from test_scratch_root_gate import child_timeout

    import optional_deps
    import script_copy
    from hermetic_git import git_env_vars

    optional_deps.importorskip("pre_commit", extra="dev")
    yaml = optional_deps.importorskip("yaml", extra="dev")
    pre_commit = Path(sys.executable).with_name("pre-commit")
    optional_deps.require_or_skip(
        pre_commit.is_file(),
        "dev",
        "pre-commit executable from the dev extra is absent",
    )
    shipped = yaml.safe_load((_ROOT / ".pre-commit-config.yaml").read_text("utf-8"))
    hooks = [
        hook
        for repo in shipped["repos"]
        for hook in repo["hooks"]
        if hook["id"] == "commit-subject"
    ]
    assert len(hooks) == 1, "shipped config must carry the commit-subject hook"
    assert shipped["default_install_hook_types"] == ["pre-commit", "commit-msg"]
    assert shipped["default_stages"] == ["pre-commit"]
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    (root / "config").mkdir()
    # Follow transitive imports so the host hook can start in its isolated copy.
    script_copy.copy_with_imports(
        root, _ROOT, ("scripts/commit_subject.py", "config/project.json")
    )
    config = {
        key: shipped[key] for key in ("default_install_hook_types", "default_stages")
    }
    config["repos"] = [{"repo": "local", "hooks": hooks}]
    (root / ".pre-commit-config.yaml").write_text(
        yaml.safe_dump(config), encoding="utf-8"
    )
    env = child_env.build_child_env(
        extra={
            **git_env_vars(tmp_path),
            "PRE_COMMIT_HOME": str(tmp_path / "pre-commit"),
            "PATH": str(pre_commit.parent) + os.pathsep + os.defpath,
            "GIT_MERGE_AUTOEDIT": "no",
        }
    )

    def run(*argv):
        return subprocess.run(
            argv,
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=child_timeout(),
        )

    def git(*argv):
        proc = run("git", *argv)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        return proc.stdout.strip()

    git("init", "-q")
    git("add", "-A")
    git("commit", "-qm", "chore: initial")
    if linked:
        worktree = tmp_path / "linked"
        git("worktree", "add", "-qb", "linked", str(worktree))
        root = worktree
    base_branch = git("symbolic-ref", "--short", "HEAD")
    before = git("rev-parse", "HEAD")
    installed = run(str(pre_commit), "install")
    assert installed.returncode == 0, installed.stdout + installed.stderr
    hooks_dir = root / git("rev-parse", "--git-common-dir") / "hooks"
    assert (hooks_dir / "pre-commit").is_file()
    assert (hooks_dir / "commit-msg").is_file()
    (root / "main").write_text("main", encoding="utf-8")
    git("add", "main")
    refused = run("git", "commit", "-m", "wip")
    assert refused.returncode != 0, refused.stdout + refused.stderr
    assert "does not match <type>" in refused.stdout + refused.stderr
    assert git("rev-parse", "HEAD") == before
    git("commit", "-m", "feat: ok")
    assert git("rev-parse", "HEAD") != before
    (root / "main").write_text("fixup", encoding="utf-8")
    git("add", "main")
    git("commit", "--fixup", "HEAD")
    assert git("log", "-1", "--format=%s") == "fixup! feat: ok"
    git("checkout", "-qb", "side")
    (root / "side").write_text("side", encoding="utf-8")
    git("add", "side")
    git("commit", "-qm", "feat: side")
    git("checkout", base_branch)
    # --no-commit exposes git's own marker and default message before the hook runs.
    git("merge", "--no-ff", "--no-commit", "side")
    gitdir = root / git("rev-parse", "--git-dir")
    assert (gitdir / "MERGE_HEAD").is_file()
    assert (gitdir / "MERGE_MSG").read_text("utf-8").startswith("Merge ")
    assert (gitdir / "COMMIT_EDITMSG").is_file()
    git("merge", "--abort")
    git("merge", "--no-ff", "side")
    assert git("log", "-1", "--format=%s").startswith("Merge ")
    assert len(git("rev-list", "--parents", "-1", "HEAD").split()) == 3
