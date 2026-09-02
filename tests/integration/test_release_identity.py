"""
title: Integration — a version heading names a tag that exists
kind: tests
layer: n/a
summary: CHANGELOG.md carried a `## [0.1.0] — 2026-08-04` heading for a release nobody ever cut, and nothing noticed because no check reads the changelog — while five shipped references told users to `copier copy --vcs-ref v0.1.0`, which resolved to nothing. This pins the pair: every dated version heading must have a matching git tag. Not a check_* letter on purpose (ADR-0009): check_structure.py is stdlib-only and 3.6-safe and has no business shelling to git in a pre-commit hook. Absent is not broken — no git, no repository, or a repository with no tags AND no version headings are all real states that pass loudly.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.integration

# `## [1.2.3] — 2026-09-02`. `## [Unreleased]` is exempt by definition: it is the
# section that exists precisely because its contents have NOT been released.
_VERSION_HEADING = re.compile(r"^## \[(\d+\.\d+\.\d+)\]", re.MULTILINE)


def _git(*args):
    """Run git at the repo root; return (ok, stdout). Never raises."""
    if shutil.which("git") is None:
        return False, ""
    result = subprocess.run(
        ["git"] + list(args), cwd=str(_ROOT), capture_output=True, text=True
    )
    return result.returncode == 0, result.stdout


def test_every_released_version_heading_has_a_matching_tag():
    """A changelog that names a version nobody can check out is a promise the
    repository cannot keep.

    The failure it exists to prevent is not hypothetical: this repository shipped
    a `[0.1.0]` heading, five documented commands that assumed the tag resolved,
    and no tag, for the better part of a month.
    """
    changelog = _ROOT / "CHANGELOG.md"
    if not changelog.is_file():
        pytest.skip("no CHANGELOG.md in this project")

    declared = _VERSION_HEADING.findall(changelog.read_text(encoding="utf-8"))
    if not declared:
        # A generated project starts its own changelog with nothing released yet.
        # A skip with a stated reason, not a silent pass: pytest reports it, and
        # `print` is banned outside entrypoints (ruff T20).
        pytest.skip("no released version headings yet — nothing to pin")

    ok, _ = _git("rev-parse", "--is-inside-work-tree")
    if not ok:
        # Not a git checkout (a tarball, or a generated project before `git init`).
        # Nothing is KNOWN about tags here, which is absent, not broken.
        pytest.skip(
            "not a git repository — cannot verify %d version heading(s) against tags"
            % len(declared)
        )

    _, tag_out = _git("tag", "--list")
    tags = set(tag_out.split())
    missing = [v for v in declared if "v%s" % v not in tags and v not in tags]
    assert not missing, (
        "CHANGELOG.md documents %s but no matching tag exists (tags: %s). Either "
        "cut and push the tag, or move the section back under [Unreleased] — a "
        "version heading is a claim that a named ref is checkable out (ADR-0009)."
        % (", ".join(missing), sorted(tags) or "none")
    )


def test_the_newest_tag_is_not_behind_the_default_branch_tip():
    """The tag-ordering rule of ADR-0009, asserted rather than trusted.

    copier resolves an untagged template through dunamai, so a descendant
    generated from a commit AHEAD of the newest tag records a version like
    `0.1.0.postN.devM` — which PEP 440 orders ABOVE `0.1.0`. copier refuses to
    update downwards, so a tag left behind the tip turns every such descendant's
    `copier update` into a hard error. Cutting at the tip is what keeps the
    upgrade channel the template advertises actually usable.

    Warns rather than fails while commits accumulate after a release — that is
    normal development, not a defect. It fails only for the shape that breaks
    users: a tag that exists but names no ancestor of HEAD at all.
    """
    ok, _ = _git("rev-parse", "--is-inside-work-tree")
    if not ok:
        pytest.skip("not a git repository")
    _, tag_out = _git("tag", "--list")
    if not tag_out.split():
        pytest.skip("no tags yet — the ordering rule is vacuous")

    described_ok, described = _git("describe", "--tags", "--abbrev=0")
    assert described_ok, "tags exist but `git describe` found none reachable from HEAD"
    newest = described.strip()
    reachable, _ = _git("merge-base", "--is-ancestor", newest, "HEAD")
    assert reachable, (
        "the newest reachable tag %s is not an ancestor of HEAD — a tag must name "
        "a commit no descendant is ahead of (ADR-0009)" % newest
    )
