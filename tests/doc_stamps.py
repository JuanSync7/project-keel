"""
title: Test helper — a generation date no template stamp can outrun
kind: tests
layer: n/a
summary: The SOURCE_DATE_EPOCH a copier test pins so every governed document's `updated:` is moved, derived from the template's own newest stamp rather than written down. restamp_docs never moves a stamp backwards, so a pinned date older than some stamp in the template would leave that document alone and make "every stamp equals the generation date" false for a reason that has nothing to do with the code under test. Shared by test_copier_generation.py and test_copier_update.py so the two cannot drift.
"""

import datetime
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "scripts"))
sys.path.insert(0, os.path.join(_ROOT, "scripts", "jobs"))

import check_structure  # noqa: E402
import review_docs  # noqa: E402


def newest_stamp(root):
    """The latest ISO `updated:` of any Markdown file under *root*, as a date.
    Raises when there is none: a template with no stamps cannot test stamping."""
    newest = None
    for dirpath, dirnames, filenames in os.walk(str(root)):
        dirnames[:] = [d for d in dirnames if d not in check_structure.IGNORE_DIRS]
        for name in filenames:
            if not name.endswith(".md"):
                continue
            path = os.path.join(dirpath, name)
            if os.path.islink(path):
                continue
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            span = review_docs.updated_span(text)
            value = text[span[0] : span[1]] if span else None
            if value and review_docs.ISO_DATE.match(value):
                day = datetime.datetime.strptime(value, "%Y-%m-%d").date()
                newest = day if newest is None or day > newest else newest
    assert newest is not None, "no stamped document under %s" % root
    return newest


def epoch_of(day):
    """Midnight UTC of *day*, as the integer SOURCE_DATE_EPOCH wants."""
    start = datetime.datetime(
        day.year, day.month, day.day, tzinfo=datetime.timezone.utc
    )
    return int(start.timestamp())


def epoch_after_newest_stamp(root, days=1):
    """SOURCE_DATE_EPOCH for *days* after the newest stamp under *root*, with the
    date it resolves to."""
    day = newest_stamp(root) + datetime.timedelta(days=days)
    return epoch_of(day), day
