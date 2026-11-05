#!/usr/bin/env python3
"""
title: review_docs — the deterministic documentation review
kind: script
layer: n/a
summary: The deterministic documentation review, the doc reviewer's first tool. Reports documentation facts a rule can decide but check_structure does not gate. Freshness (gated elsewhere): a governed document's `updated:` is never earlier than the date of its last commit, and a document modified in the working tree carries today's date or later; this is the judge, and scripts/jobs/restamp_docs.py is the writer that clears a finding, reading the stamp through the same `updated_span` grammar. Report tier (always exit 0) under `make advise`; `--strict` exits 1 on stale stamps, which is how tests/integration/test_doc_freshness.py turns the same rule into a gate. Today is `--today`, else SOURCE_DATE_EPOCH read in UTC, else the date of the gate run this process is part of (the variable config/project.json `evidence.run_date.env` names, set by scripts/gate_evidence.py and checked by scripts/run_date.py against the clock and `evidence.run_date.max_age_days`), else the local clock, through `resolve_today`, the one clock the writer also reads; a malformed or refused source exits 2, a config/project.json the run date cannot use for a reason other than a conflict an update left exits 14 (ExitCode.CONFIG) with the loader's line, and neither is replaced by the clock. Changed paths come from `modified_paths`, which reads `git --no-optional-locks status` and strips the root's prefix: read-only against the repository it judges (`git diff HEAD` and plain `git status` rewrite .git/index, measured), and a root below the repository top is judged on its own documents. Every git call goes through `git_argv`, which switches off each command a repository's own config can make a read run (fsmonitor, every configured clean/smudge/process filter driver, the `log.showSignature` verifier), so judging another project's tree runs none of them; when git will not list the filter drivers the call is not made. Also the advisories that stay advisory: a backticked repository path that resolves to nothing (most are bare basenames used as nouns, hence never a gate), and a thought in a shipped document (any Markdown file or `.md.jinja` twin outside config/project.json `doc_drift.history_paths`: a paragraph, list item, heading, quote, table cell or sentence, fences left out, the period after a step's number quoted or parenthesised in prose, the "2." of `("2. Now run X")`, ends no sentence, and a heading's or a table cell's own number, as in `## 3. Removed checks`, is not its first word) that opens with a `change_comments.phrases` phrase as a whole word, read through scripts/config_loader.py; a past participle or "now" at an opener is as often a present claim as a report, so it is an `OPENER` line `--strict` never fails on, and with no config/project.json in the judged tree it is a stated "unchecked" (JSON null), never a clean count. Every git call takes its allowlist from this checkout's own config/project.json (scripts/child_env.py), so a checkout without a usable one exits 14 (ExitCode.CONFIG) naming that file before any git runs. A manifest or an opener list the loader refuses exits 14 (ExitCode.CONFIG), and one an update left holding a merge-conflict hunk exits 2, with `--today` or without it, by scripts/config_loader.py `is_conflict`. The fence grammar is check_structure's, copied (importing it would put check_structure in the closure of the jobs that import this module) and pinned equal by tests/unit/scripts/test_review_docs.py. And, with --json, every roster row, for the agent to judge. No model, no network; git is the only tool it shells to, and no git is a stated skip.
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
import config_loader  # noqa: E402
import run_date  # noqa: E402
from exit_codes import ExitCode, finish, report  # noqa: E402

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


# What a refused date source is answered with. The run date's variable is not
# named here: config names it, and the refusal's own text carries the name.
_DATE_REMEDY = (
    "pass --today YYYY-MM-DD, or correct SOURCE_DATE_EPOCH, or unset the gate "
    "run's date variable the message names"
)


class DateSourceError(ValueError):
    """A date source (`--today`, SOURCE_DATE_EPOCH, the gate run's date) this
    script refuses to guess about. A ValueError so a caller that only knows the
    stdlib still catches it. *remedy* is the next step a caller reports: a
    fault in config/project.json carries its own, since no other date clears
    it."""

    def __init__(self, message, remedy=_DATE_REMEDY):
        ValueError.__init__(self, message)
        self.remedy = remedy


def resolve_today(argv_today, environ, root=None, clock=datetime.date.today):
    """The date the freshness rule calls today: *argv_today* when given, else
    SOURCE_DATE_EPOCH read in UTC (the reproducible-builds convention, so a
    pinned build agrees with itself on every host), else the date of the gate
    run this process is part of, else the local clock. The run's date is read
    by scripts/run_date.py from the variable <root>/config/project.json
    `evidence.run_date.env` names (*root* defaults to this checkout), so every
    check of one `make verify` judges by the day the run began; it comes after
    the two pins because each is a caller's explicit choice of day and the
    run's date only stands in for the clock. The one clock:
    scripts/jobs/restamp_docs.py calls this too, because a writer and a judge
    on two clocks disagree about what "fresh" means (measured). A malformed or
    refused source raises DateSourceError, never a silent fallback. *clock*
    stands in for datetime.date.today."""
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
    try:
        return run_date.today(environ, run_date.load(root or ROOT), clock)
    except run_date.RunDateConfigError as exc:
        raise DateSourceError(str(exc), exc.remedy) from exc
    except run_date.RunDateError as exc:
        raise DateSourceError(str(exc)) from exc


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
    except GitConfigError:  # noqa: DROP001 -- None when git is absent or fails, as documented
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
    except (OSError, ValueError):  # noqa: DROP001 -- None when there is no readable stamp, as documented
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
            except (OSError, ValueError):  # noqa: DROP001 -- an advisory review: a document it cannot read gives it nothing to judge
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


# check_structure's fence grammar, copied rather than imported: restamp_docs
# and declare_no_app import this module, and conflict_guard refuses a job over
# every read of each module it imports, so importing check_structure would stop
# them over a conflicted Makefile. tests/unit/scripts/test_review_docs.py pins
# the copy equal to check_structure's.
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
INLINE_CODE = re.compile(r"(`+)(.+?)\1")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_TWIN = ".jinja"
_OPENER_KEYS = (("change_comments", "phrases"), ("doc_drift", "history_paths"))
# What opens a block of prose: a list item (a task box included), an ordered
# item, a heading or a quote marker.
_BLOCK_MARK = re.compile(r"^\s*(?:[-*+]\s+(?:\[[ xX]\]\s+)?|\d+[.)]\s+|#{1,6}\s+|>\s*)")
# A line that ends a sentence, closing emphasis, brackets or quotes allowed.
_SENTENCE_END = re.compile(r"[.!?][*_)\"'\u201d]*$")
# A step's number quoted or parenthesised in prose ("2. Now run X") is not a
# sentence end: on this tree every reported opener was the "Now" after one,
# measured. Only that shape: a sentence that ends in a number ("added in
# 2024.", "the count is 2.") still ends there.
_STEP_NUMBER_END = re.compile(r"[(\"'\u201c\u2018]\d+\.$")
# A heading's or a cell's own number ("## 3. Removed checks"), stripped before
# its first word as _BLOCK_MARK strips an ordered item's.
_OWN_NUMBER = re.compile(r"^\d+[.)]\s+")
# Markup a thought may open with before its first word.
_OPENING_MARKUP = "*_[(\"' "
# A code span stands in as a word, so "`x` changed" opens with `x`, not with
# "changed".
_SPAN_WORD = "CODE"


def unfenced_lines(text):
    """*text*'s lines with fenced code blocks and HTML comments blanked,
    numbering kept; a fence closes only on its own character, at least as
    long, and one left open blanks every line after it."""
    out, fence = [], None
    text = HTML_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    for line in text.split("\n"):
        m = FENCE.match(line)
        closes = (
            m
            and fence is not None
            and m.group(1)[0] == fence[0]
            and len(m.group(1)) >= len(fence)
            and not line[m.end() :].strip(" \t")
        )
        opens = (
            m and fence is None and (m.group(1)[0] != "`" or "`" not in line[m.end() :])
        )
        if opens or closes:
            fence = m.group(1) if fence is None else None
            out.append("")
            continue
        out.append("" if fence is not None else line)
    return out


def thought_openers(text):
    """[(line, segment)] for every place a thought opens in *text*'s prose: a
    paragraph's first line, a list item, a heading, a quote, a table cell, a
    line after one that ends a sentence, and a sentence after `.`, `!` or `?`
    in a line; the period after a quoted or parenthesised step's number ends
    none, and a heading's or a cell's own number is not its first word. Fences
    are left out; a code span is read as one word."""
    out = []
    previous = None
    for i, raw in enumerate(unfenced_lines(text), 1):
        line = INLINE_CODE.sub(_SPAN_WORD, raw)
        if not line.strip():
            previous = None
            continue
        if line.lstrip().startswith("|"):
            out.extend(
                (i, _OWN_NUMBER.sub("", c.strip()))
                for c in line.strip().strip("|").split("|")
            )
            previous = None
            continue
        mark = _BLOCK_MARK.match(line)
        body = _OWN_NUMBER.sub("", line[mark.end() :] if mark else line.strip())
        if mark or previous is None or _ends_sentence(previous):
            out.append((i, body))
        sentences = []
        for piece in re.split(r"(?<=[.!?])\s+", body):
            if sentences and _STEP_NUMBER_END.search(sentences[-1]):
                sentences[-1] += " " + piece
            else:
                sentences.append(piece)
        out.extend((i, s) for s in sentences[1:])
        previous = line.rstrip()
    return out


def _ends_sentence(text):
    """Whether *text* ends a sentence: a `.`, `!` or `?` (closing markup
    allowed) that is not the period after a quoted or parenthesised step's
    number."""
    return bool(_SENTENCE_END.search(text)) and not _STEP_NUMBER_END.search(text)


def _opening_phrase(segment, phrases):
    """The phrase of *phrases* (lowercased) *segment* opens with as a whole
    word, else None."""
    body = segment.lstrip(_OPENING_MARKUP).lower()
    for phrase in phrases:
        if body.startswith(phrase):
            rest = body[len(phrase) :]
            if not rest or not rest[0].isalnum():
                return phrase
    return None


def opener_policy(root):
    """(phrases lowercased, history_paths) from *root*'s config/project.json
    `change_comments.phrases` and `doc_drift.history_paths`, read through
    scripts/config_loader.py; None when *root* has no config/project.json.
    Raises config_loader.ConfigError for a manifest or a value it refuses."""
    try:
        loaded = config_loader.read(root)
    except config_loader.ConfigAbsent:  # noqa: DROP001 -- None is the stated unchecked result, reported as null
        return None
    values = config_loader.resolve(
        loaded, config_loader.rows(*_OPENER_KEYS), config_loader.CONFIG_FILE
    )
    phrases = tuple(p.lower() for p in values[_OPENER_KEYS[0]])
    return phrases, tuple(values[_OPENER_KEYS[1]])


def shipped_markdown(root, history_paths):
    """[(relpath, text)] for every Markdown file and `.md.jinja` twin under
    *root* whose path, twin suffix stripped, starts with none of
    *history_paths*, sorted; a symlink and an unreadable file are left out, as
    unresolved_mentions leaves them."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")
        )
        for name in sorted(filenames):
            if not name.endswith((".md", ".md" + _TWIN)):
                continue
            full = os.path.join(dirpath, name)
            relpath = os.path.relpath(full, root).replace(os.sep, "/")
            # A slice, not str.removesuffix: this module stays 3.6-safe.
            untwinned = relpath[: -len(_TWIN)] if name.endswith(_TWIN) else relpath
            if os.path.islink(full) or untwinned.startswith(history_paths):
                continue
            try:
                with open(full, encoding="utf-8") as fh:
                    out.append((relpath, fh.read()))
            except (OSError, ValueError):  # noqa: DROP001 -- an advisory review: a document it cannot read gives it nothing to judge
                continue
    return sorted(out)


def change_openers(docs, phrases):
    """[(relpath, line, phrase)] for each thought in *docs* that opens with a
    phrase of *phrases* as a whole word, sorted. Advisory: "Now runs X"
    reports a change, which the changelog carries, but a past participle or
    "now" at an opener is as often a present claim ("Removed entries are
    reported", "2. Now run `make verify`"), so a reader judges each one."""
    out = []
    for relpath, text in docs:
        for line, segment in thought_openers(text):
            phrase = _opening_phrase(segment, phrases)
            if phrase:
                out.append((relpath, line, phrase))
    return sorted(out)


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
        except (OSError, ValueError):  # noqa: DROP001 -- an advisory review: a README it cannot read gives it nothing to judge
            continue
        relpath = os.path.relpath(full, root).replace(os.sep, "/")
        if _ROSTER_HEADING not in lines:
            continue
        start = lines.index(_ROSTER_HEADING)
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


def _main(argv=None):
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
        "(default: SOURCE_DATE_EPOCH in UTC, else the gate run's date, else "
        "today; tests pin it)",
    )
    args = ap.parse_args(argv)
    try:
        today = resolve_today(args.today, os.environ).isoformat()
    except DateSourceError as exc:
        refusal = config_loader.refusal_cause(exc)
        if refusal is not None and not isinstance(refusal, config_loader.ConfigAbsent):
            return report(
                ExitCode.USAGE
                if config_loader.is_conflict(refusal)
                else ExitCode.CONFIG,
                "review_docs: the manifest cannot be used",
                "; ".join(refusal.lines),
                "repair config/project.json, resolving any hunk, then rerun",
            )
        return report(
            ExitCode.USAGE,
            "review_docs: cannot tell what today is",
            str(exc),
            exc.remedy,
        )
    try:
        policy = opener_policy(args.root)
    except config_loader.ConfigError as exc:
        return report(
            ExitCode.USAGE if config_loader.is_conflict(exc) else ExitCode.CONFIG,
            "review_docs: the change-opener lists cannot be used",
            "; ".join(exc.lines),
            "correct config/project.json `change_comments.phrases` and "
            "`doc_drift.history_paths`",
        )
    records = collect(args.root)
    if records is None:
        # Absent, not broken: no git, or not a repository. Say so, exit 0.
        print("review_docs: no git repository to compare against; freshness unverified")
        return ExitCode.SUCCESS
    findings = stale_findings(records, today)
    mentions = unresolved_mentions(args.root)
    openers = (
        None
        if policy is None
        else change_openers(shipped_markdown(args.root, policy[1]), policy[0])
    )
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
                    # null, not []: no manifest means unchecked, not clean.
                    "change_openers": None
                    if openers is None
                    else [{"path": p, "line": n, "phrase": ph} for p, n, ph in openers],
                },
                indent=2,
            )
        )
    else:
        for f in findings:
            print("STALE %s: %s" % (f["path"], f["reason"]))
        for p, n, m in mentions:
            print("MENTION %s:%d: `%s` resolves to nothing (advisory)" % (p, n, m))
        for p, n, ph in openers or ():
            print(
                "OPENER %s:%d: opens a thought with %r; a change report belongs "
                "in CHANGELOG.md, a present claim stays (advisory)" % (p, n, ph)
            )
        print(
            "review_docs: %d governed document(s), %d stale; %d unresolved mention(s) (advisory); %s"
            % (
                len(records),
                len(findings),
                len(mentions),
                "change openers unchecked: no config/project.json"
                if openers is None
                else "%d change opener(s) (advisory)" % len(openers),
            )
        )
    # --strict gates freshness only; mentions and openers are advisory in
    # every mode.
    if not (args.strict and findings):
        return ExitCode.SUCCESS
    return report(
        ExitCode.FAILURE,
        "review_docs: a governed document changed without its `updated:` stamp",
        "%d stale document(s), each a STALE line above" % len(findings),
        "run `make restamp-docs`",
    )


def main(argv=None):
    """Report a manifest refusal from any read made during this invocation."""
    try:
        return _main(argv)
    except (config_loader.ConfigError, child_env.ChildEnvError) as exc:
        refusal = config_loader.refusal_cause(exc)
        if refusal is None or isinstance(refusal, config_loader.ConfigAbsent):
            raise
        return report(
            ExitCode.USAGE if config_loader.is_conflict(refusal) else ExitCode.CONFIG,
            "review_docs: the manifest cannot be used",
            "; ".join(refusal.lines),
            "repair config/project.json, resolving any hunk, then rerun",
        )


if __name__ == "__main__":
    finish(main())
