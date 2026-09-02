#!/usr/bin/env python3
"""
title: review_docs — the deterministic documentation review
kind: script
layer: n/a
summary: Reports documentation facts a rule can decide but check_structure cannot reach without git. Today that is freshness: a governed document's `updated:` is never earlier than the date of its last commit, and a document modified in the working tree carries today's date or later. Report tier (always exit 0) under `make advise`; `--strict` exits 1 on any finding, which is how tests/integration/test_doc_freshness.py turns the same rule into a gate. No model, no network; git is the only tool it shells to, and no git is a stated skip.
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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UPDATED = re.compile(r"^updated:\s*(\S+)", re.MULTILINE)
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _git(root, *args):
    """git's stdout at `root`, or None when git is absent or the call fails."""
    if shutil.which("git") is None:
        return None
    proc = subprocess.run(
        ["git"] + list(args),
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    return proc.stdout if proc.returncode == 0 else None


def _frontmatter_updated(path):
    """The frontmatter `updated:` value of a Markdown file, or None when the file
    has no frontmatter block or no such key (then it is not governed here)."""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, ValueError):
        return None
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    m = _UPDATED.search(text[:end])
    return m.group(1) if m else None


def collect(root):
    """One record per governed Markdown file: (relpath, updated, last_commit,
    modified). Governed = git-tracked, not a symlink, frontmatter carries
    `updated:`. `last_commit` is the ISO date of the file's newest commit
    (None for a file never committed); `modified` says the working tree differs
    from HEAD. Returns None when there is no git repository to ask."""
    listed = _git(root, "ls-files", "-z", "--", "*.md")
    if listed is None:
        return None
    dirty = _git(root, "status", "--porcelain", "-z", "--untracked-files=no") or ""
    modified = {entry[3:] for entry in dirty.split("\0") if len(entry) > 3}
    records = []
    for relpath in sorted(p for p in listed.split("\0") if p):
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
        if not _ISO_DATE.match(updated):
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
                    "without restamping `updated:`" % (last_commit, updated),
                }
            )
        elif modified and updated < today:
            findings.append(
                {
                    "path": relpath,
                    "updated": updated,
                    "expected": today,
                    "reason": "modified in the working tree but stamped %s -- set "
                    "`updated: %s` in the same change" % (updated, today),
                }
            )
    return findings


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
        default=datetime.date.today().isoformat(),
        help="the date a modified file must carry (default: today; tests pin it)",
    )
    args = ap.parse_args(argv)
    records = collect(args.root)
    if records is None:
        # Absent, not broken: no git, or not a repository. Say so, exit 0.
        print("review_docs: no git repository to compare against; freshness unverified")
        return 0
    findings = stale_findings(records, args.today)
    if args.json:
        print(json.dumps({"checked": len(records), "findings": findings}, indent=2))
    else:
        for f in findings:
            print("STALE %s: %s" % (f["path"], f["reason"]))
        print(
            "review_docs: %d governed document(s), %d stale"
            % (len(records), len(findings))
        )
    return 1 if (args.strict and findings) else 0


if __name__ == "__main__":
    sys.exit(main())
