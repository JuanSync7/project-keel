"""
title: Test helper — a generation date no template stamp can outrun
kind: tests
layer: n/a
summary: `pinned_day` makes one pinned epoch the day for the stamper and for git alike, so a commit a copier test makes is dated the day its documents were stamped and not the clock's, which restamp_docs would otherwise raise every stamp to. The SOURCE_DATE_EPOCH a copier test pins so every governed document's `updated:` is moved, derived from the template's own newest stamp rather than written down. restamp_docs never moves a stamp backwards, so a pinned date older than some stamp in the template would leave that document alone and make "every stamp equals the generation date" false for a reason that has nothing to do with the code under test. Shared by test_copier_generation.py and test_copier_update.py so the two cannot drift.
"""

import contextlib
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


def day_env(epoch):
    """The variables that make *epoch* the day: SOURCE_DATE_EPOCH for the
    stamper, GIT_AUTHOR_DATE and GIT_COMMITTER_DATE for every commit."""
    moment = "@%d +0000" % epoch
    return {
        "SOURCE_DATE_EPOCH": str(epoch),
        "GIT_AUTHOR_DATE": moment,
        "GIT_COMMITTER_DATE": moment,
    }


@contextlib.contextmanager
def pinned_day(epoch):
    """Run the block on the day of *epoch*: `day_env` in os.environ and in
    plumbum's environment, restored on exit.

    Both, because a test's own `git commit` inherits os.environ while copier
    runs git and its tasks through plumbum, whose environment is a copy taken
    at import. A commit left on the clock's date is a later day than the
    pinned one as soon as the clock passes it, and restamp_docs raises a
    stamp to its document's last commit date: every document is then
    restamped and "the update touched only what changed" fails."""
    # Imported here: plumbum comes with the optional `template` extra, and a
    # caller that only reads stamps must not need it.
    import plumbum

    env = day_env(epoch)
    saved = {name: os.environ.get(name) for name in env}
    os.environ.update(env)
    try:
        with plumbum.local.env(**env):
            yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
