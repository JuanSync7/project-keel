#!/usr/bin/env python3
"""
title: review_docs — the deterministic documentation review
kind: script
layer: n/a
summary: The deterministic documentation review, the doc reviewer's first tool. Reports documentation facts a rule can decide but check_structure does not gate. Freshness (gated elsewhere): a governed document's `updated:` is never earlier than the date of its last commit, and a document modified in the working tree carries today's date or later; this is the judge, and scripts/jobs/restamp_docs.py is the writer that clears a finding, reading the stamp through the same `updated_span` grammar. Report tier (always exit 0) under `make advise`; `--strict` exits 1 on any finding, which is how tests/integration/test_doc_freshness.py turns the same rule into a gate. Today is `--today`, else SOURCE_DATE_EPOCH read in UTC, else the local clock, through `resolve_today`, the one clock the writer also reads; a malformed source exits 2. Changed paths come from `modified_paths`, which reads `git --no-optional-locks status` and strips the root's prefix: read-only against the repository it judges (`git diff HEAD` and plain `git status` rewrite .git/index, measured), and a root below the repository top is judged on its own documents. Every git call goes through `git_argv`, which switches off each command a repository's own config can make a read run (fsmonitor, every configured clean/smudge/process filter driver, the `log.showSignature` verifier), so judging another project's tree runs none of them; when git will not list the filter drivers the call is not made. Also the advisory that stays advisory: a backticked repository path that resolves to nothing (most are bare basenames used as nouns, hence never a gate). And, with --json, every roster row, for the agent to judge. No model, no network; git is the only tool it shells to, and no git is a stated skip.
"""

# 3.6-safe on purpose: `make advise` runs this under $(PY), but the rule it
# states is one a pre-commit hook may one day want, and the cost is nil.
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

_SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import child_env  # noqa: E402

ROOT = os.path.dirname(_SCRIPTS)
# Every file this judge reads is found at run time (the Markdown walk); the
# one path literal is a basename it looks for in each directory.
PROJECT_PATHS_NOT_READ = (("README.md", "a worklist basename, not a fixed read"),)
# `[ \t]*`, not `\s*`: `\s` spans the newline, so an empty `updated:` read the
# NEXT line's first token as its date.
_UPDATED = re.compile(r"^updated:[ \t]*(\S+)", re.MULTILINE)
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_BOM = "\ufeff"
_EPOCH = re.compile(r"^[0-9]+$")


class DateSourceError(ValueError):
    """A date source (`--today`, SOURCE_DATE_EPOCH) this script refuses to guess
    about. A ValueError so a caller that only knows the stdlib still catches it."""


def resolve_today(argv_today, environ):
    """The date the freshness rule calls today: *argv_today* when given, else
    SOURCE_DATE_EPOCH read in UTC (the reproducible-builds convention, so a
    pinned build agrees with itself on every host), else the local clock. The
    one clock: scripts/jobs/restamp_docs.py calls this too, because a writer and
    a judge on two clocks disagree about what "fresh" means (measured). A
    malformed source raises DateSourceError, never a silent fallback."""
    if argv_today is not None:
        if not ISO_DATE.match(argv_today):
            raise DateSourceError("--today %r is not an ISO date" % argv_today)
        try:
            return datetime.datetime.strptime(argv_today, "%Y-%m-%d").date()
        except ValueError as exc:
            raise DateSourceError(
                "--today %r is not a calendar date" % argv_today
            ) from exc
    if "SOURCE_DATE_EPOCH" in environ:
        raw = environ["SOURCE_DATE_EPOCH"]
        if not _EPOCH.match(raw):
            raise DateSourceError(
                "SOURCE_DATE_EPOCH=%r is not a whole number of seconds" % raw
            )
        try:
            moment = datetime.datetime.fromtimestamp(int(raw), datetime.timezone.utc)
        except (ValueError, OverflowError, OSError) as exc:
            # Digits past datetime's year 9999 (or the platform's time_t).
            raise DateSourceError(
                "SOURCE_DATE_EPOCH=%r is not a representable date" % raw
            ) from exc
        return moment.date()
    return datetime.date.today()


# Prepended to every git call. `--no-optional-locks`: a status that may not
# take the index lock does not write the refreshed index back (measured on git
# 2.43.5; GIT_OPTIONAL_LOCKS=0 does not stop `git diff HEAD` doing so). The
# rest stop a command the judged repository's own config names from running:
# `core.fsmonitor` on status, and the signature verifier (`gpg.program`) that
# `log.showSignature` makes `git log` run. Filter drivers have no wildcard
# switch, so `git_argv` adds one override per configured driver.
GIT_READ_ONLY = (
    "--no-optional-locks",
    "-c",
    "core.fsmonitor=false",
    "-c",
    "log.showSignature=false",
)
_FILTER_KEY = re.compile(r"^filter\.(.+)\.(?:clean|smudge|process)$")


class GitConfigError(RuntimeError):
    """git would not list the filter drivers its config names at a root, so a
    call there could run one: the caller treats the root as one git refused."""


def _filter_drivers(root):
    """Every filter driver name git's config (all levels, includes followed)
    gives a clean, smudge or process command at *root*. `git config` reads and
    runs nothing. Exit 1 is git's "no key matched"; any other failure raises."""
    proc = subprocess.run(
        ["git"]
        + list(GIT_READ_ONLY)
        + ["config", "-z", "--get-regexp", r"^filter\..*\.(clean|smudge|process)$"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        env=child_env.build_child_env(),
    )
    if proc.returncode == 1 and not proc.stdout:
        return []
    if proc.returncode != 0:
        raise GitConfigError(proc.stderr.strip() or "git config failed")
    names = set()
    for entry in proc.stdout.split("\0"):
        m = _FILTER_KEY.match(entry.split("\n", 1)[0])
        if m:
            names.add(m.group(1))
    return sorted(names)


def git_argv(root, *args):
    """The argv of a read-only git call at *root*: GIT_READ_ONLY, then an empty
    clean, smudge and process command and `required=false` for every filter
    driver the config names there (git runs no command for an empty one,
    measured on git 2.43.5), then *args*. Status re-hashes a stat-dirty file
    through its clean filter, so without these a judge pointed at another
    project's tree would run that project's filter (measured: 366 runs in one
    audit). The cost: a filtered file whose stat data is stale is compared by
    its raw bytes. Raises GitConfigError when the drivers cannot be listed."""
    argv = ["git"] + list(GIT_READ_ONLY)
    for name in _filter_drivers(root):
        for key, value in (
            ("clean", ""),
            ("smudge", ""),
            ("process", ""),
            ("required", "false"),
        ):
            argv += ["-c", "filter.%s.%s=%s" % (name, key, value)]
    return argv + list(args)


def _git(root, *args):
    """git's stdout at `root`, or None when git is absent or the call fails."""
    if shutil.which("git") is None:
        return None
    try:
        argv = git_argv(root, *args)
    except GitConfigError:
        return None
    proc = subprocess.run(
        argv,
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        env=child_env.build_child_env(),
    )
    return proc.stdout if proc.returncode == 0 else None


def updated_span(text):
    """The (start, end) offsets of the frontmatter `updated:` value in *text*, or
    None when there is no frontmatter block or no top-level `updated:` with a
    value in it (then the document is not governed here).

    The one grammar the judge (this module) and the writer
    (scripts/jobs/restamp_docs.py) share: the writer replaces exactly
    `text[start:end]`, so what it rewrites is by construction what is judged.
    A leading U+FEFF is allowed, because a BOM document is still a document."""
    offset = len(_BOM) if text.startswith(_BOM) else 0
    if not text.startswith("---", offset):
        return None
    end = text.find("\n---", offset + 3)
    if end < 0:
        return None
    m = _UPDATED.search(text, offset, end)
    return m.span(1) if m else None


def _frontmatter_updated(path):
    """The frontmatter `updated:` value of a Markdown file, or None when it is
    not governed (see `updated_span`)."""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, ValueError):
        return None
    span = updated_span(text)
    return text[span[0] : span[1]] if span else None


def modified_paths(root):
    """The root-relative paths whose index or working-tree copy differs from
    HEAD (untracked files excluded), or None when *root* is in no git work tree.

    Read through `git --no-optional-locks status`, which never rewrites
    .git/index; `git diff HEAD` refreshes and rewrites it. Porcelain names
    every path from the repository top, so the root's own prefix (`rev-parse
    --show-prefix`) is kept and stripped: a project below the top (`--root
    sub`) matches its own documents (measured)."""
    prefix = _git(root, "rev-parse", "--show-prefix")
    if prefix is None:
        return None
    prefix = prefix.strip()
    out = _git(
        root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=no",
        "--no-renames",
        # A submodule's status runs in its own repository, whose filter drivers
        # git_argv did not list; a gitlink is never a governed document.
        "--ignore-submodules=all",
        "--",
        ".",
    )
    if out is None:
        return None
    found = set()
    for entry in out.split("\0"):
        # `XY path`: two status letters and a space, then the top-relative path.
        path = entry[3:]
        if entry and path.startswith(prefix):
            found.add(path[len(prefix) :])
    return found


def collect(root):
    """One record per governed Markdown file: (relpath, updated, last_commit,
    modified). Governed = git-tracked, not a symlink, frontmatter carries
    `updated:`. `last_commit` is the ISO date of the file's newest commit
    (None for a file never committed); `modified` says the working tree differs
    from HEAD. Returns None when there is no git repository to ask."""
    listed = _git(root, "ls-files", "-z", "--", "*.md")
    if listed is None:
        return None
    tracked = [p for p in listed.split("\0") if p]
    if _git(root, "rev-parse", "--verify", "-q", "HEAD") is None:
        # Before the first commit every tracked file is a change being made.
        modified = set(tracked)
    else:
        modified = modified_paths(root)
        if modified is None:
            return None  # git listed the files but would not say what changed
    records = []
    for relpath in sorted(tracked):
        full = os.path.join(root, relpath)
        if os.path.islink(full):
            continue  # CLAUDE.md -> AGENT.md: the target carries the date
        updated = _frontmatter_updated(full)
        if updated is None:
            continue
        stamp = _git(root, "log", "-1", "--format=%cs", "--", relpath)
        last_commit = stamp.strip() if stamp and stamp.strip() else None
        records.append((relpath, updated, last_commit, relpath in modified))
    return records


def stale_findings(records, today):
    """The freshness rule over collected records. Pure.

    A document's `updated:` must be an ISO date; it must not be earlier than its
    last commit (a file changed by a commit that did not restamp it); and a file
    modified in the working tree must carry `today` or later (the change being
    made is a touch). `today` is an ISO date string, injected so the rule is
    testable and the report reproducible."""
    findings = []
    for relpath, updated, last_commit, modified in records:
        if not ISO_DATE.match(updated):
            findings.append(
                {
                    "path": relpath,
                    "updated": updated,
                    "expected": "an ISO date (YYYY-MM-DD)",
                    "reason": "`updated:` is not a date",
                }
            )
            continue
        if last_commit and updated < last_commit:
            findings.append(
                {
                    "path": relpath,
                    "updated": updated,
                    "expected": last_commit,
                    "reason": "last committed %s but stamped %s -- a change landed "
                    "without restamping `updated:`; run `make restamp-docs`"
                    % (last_commit, updated),
                }
            )
        elif modified and updated < today:
            findings.append(
                {
                    "path": relpath,
                    "updated": updated,
                    "expected": today,
                    "reason": "modified in the working tree but stamped %s -- set "
                    "`updated: %s` in the same change (`make restamp-docs` "
                    "does it)" % (updated, today),
                }
            )
    return findings


_MENTION = re.compile(r"`([A-Za-z0-9_][A-Za-z0-9_./-]*)`")
_SKIP_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".astro",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    ".eggs",
    "htmlcov",
    "wiki",
}


def unresolved_mentions(root):
    """[(relpath, lineno, mention)] for every backticked span in a Markdown file
    that looks like a repository path (a slash, or a .py/.md suffix) yet names no
    file or directory, root-relative or beside the citing file. Advisory: a bare
    basename used as a noun (`check_structure.py`) is prose the graph cannot
    follow, not an error."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")
        )
        for name in sorted(filenames):
            if not name.endswith(".md"):
                continue
            full = os.path.join(dirpath, name)
            if os.path.islink(full):
                continue
            try:
                with open(full, encoding="utf-8") as fh:
                    lines = fh.read().split("\n")
            except (OSError, ValueError):
                continue
            relpath = os.path.relpath(full, root).replace(os.sep, "/")
            base = os.path.dirname(full)
            for lineno, line in enumerate(lines, 1):
                for m in _MENTION.finditer(line):
                    span = m.group(1)
                    if not ("/" in span or span.endswith((".py", ".md"))):
                        continue
                    candidate = span.rstrip("/")
                    if os.path.exists(os.path.join(root, candidate)) or os.path.exists(
                        os.path.join(base, candidate)
                    ):
                        continue
                    out.append((relpath, lineno, span))
    return out


_ROSTER_HEADING = "## What ships here"


def roster_rows(root):
    """[{path, member, line, not_for}] for every row of every `## What ships here`
    table: the facts the doc reviewer judges (is the `Not for` cell true?). The
    table is the first pipe table under the heading, before the next `## `."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")
        )
        if "README.md" not in filenames:
            continue
        full = os.path.join(dirpath, "README.md")
        try:
            with open(full, encoding="utf-8") as fh:
                lines = fh.read().split("\n")
        except (OSError, ValueError):
            continue
        relpath = os.path.relpath(full, root).replace(os.sep, "/")
        try:
            start = lines.index(_ROSTER_HEADING)
        except ValueError:
            continue
        header, not_for = None, None
        for i in range(start + 1, len(lines)):
            line = lines[i]
            if line.startswith("## "):
                break
            if not line.startswith("|"):
                if header is not None and line.strip() == "":
                    break
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if header is None:
                header = [c.lower() for c in cells]
                not_for = header.index("not for") if "not for" in header else None
                continue
            if set(line.replace("|", "").strip()) <= set("-: "):
                continue  # the rule line
            member = cells[0].strip("`").rstrip("/") if cells else ""
            out.append(
                {
                    "path": relpath,
                    "member": member,
                    "line": i + 1,
                    "not_for": cells[not_for]
                    if not_for is not None and len(cells) > not_for
                    else "",
                }
            )
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[-1])
    ap.add_argument(
        "--root", default=ROOT, help="repository root (default: this checkout)"
    )
    ap.add_argument("--json", action="store_true", help="emit findings as JSON")
    ap.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 when there is any finding (gate mode)",
    )
    ap.add_argument(
        "--today",
        default=None,
        help="the date a modified file must carry "
        "(default: SOURCE_DATE_EPOCH in UTC, else today; tests pin it)",
    )
    args = ap.parse_args(argv)
    try:
        today = resolve_today(args.today, os.environ).isoformat()
    except DateSourceError as exc:
        print("review_docs: %s" % exc, file=sys.stderr)
        return 2
    records = collect(args.root)
    if records is None:
        # Absent, not broken: no git, or not a repository. Say so, exit 0.
        print("review_docs: no git repository to compare against; freshness unverified")
        return 0
    findings = stale_findings(records, today)
    mentions = unresolved_mentions(args.root)
    if args.json:
        print(
            json.dumps(
                {
                    "checked": len(records),
                    "findings": findings,
                    "unresolved_mentions": [
                        {"path": p, "line": n, "mention": m} for p, n, m in mentions
                    ],
                    "rosters": roster_rows(args.root),
                },
                indent=2,
            )
        )
    else:
        for f in findings:
            print("STALE %s: %s" % (f["path"], f["reason"]))
        for p, n, m in mentions:
            print("MENTION %s:%d: `%s` resolves to nothing (advisory)" % (p, n, m))
        print(
            "review_docs: %d governed document(s), %d stale; %d unresolved mention(s) (advisory)"
            % (len(records), len(findings), len(mentions))
        )
    # --strict gates freshness only; mentions are advisory in every mode.
    return 1 if (args.strict and findings) else 0


if __name__ == "__main__":
    sys.exit(main())
