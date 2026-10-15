"""
title: Integration — a comment explains the code, it does not report a change
kind: tests
layer: n/a
summary: A tree-wide heuristic gate over every Python file tests/source_tree.py `python_files` lists. It reads the comments that open a thought (`comment_starts`: through tokenize, so a `#` inside a string is never one; a trailing comment, the first line of a run, or a line after one that ends a sentence) and fails one whose text, lowercased, starts with a phrase in config/project.json `change_comments.phrases` followed by a character that is not a letter or digit, or by its end: `# now uses X` and `# Fixed the off-by-one` report what changed, which the commit message carries, and leave the reader without the reason the code is so (docs/guides/python-style.md section 2). The match is by whole words, so `# nowhere else` is no finding. A comment opening with one of `change_comments.directives` is an instruction to a tool and is skipped. The lists are read from the config, never typed here; an empty or malformed list, a walk with no Python file, and a walk with no comment are each a failure, never a pass. It cannot see a phrase in mid-sentence or a change reported in other words. Not a check_* letter: the letters A to Z are taken.
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "tests"))

import source_tree as st  # noqa: E402

pytestmark = pytest.mark.integration

_BLOCK = "change_comments"
_LISTS = ("phrases", "directives")


def read_lists(root):
    """(phrases, directives) from config/project.json `change_comments`,
    lowercased. Raises SourceTreeError naming the block when either is not a
    non-empty list of non-blank strings: a gate with nothing to match passes
    everything."""
    path = Path(str(root)) / st.CONFIG
    try:
        block = json.loads(path.read_text(encoding="utf-8")).get(_BLOCK)
    except (OSError, ValueError) as exc:
        raise st.SourceTreeError("%s: cannot be read (%s)" % (st.CONFIG, exc)) from exc
    if not isinstance(block, dict):
        raise st.SourceTreeError("%s: no `%s` block" % (st.CONFIG, _BLOCK))
    out = []
    for key in _LISTS:
        values = block.get(key)
        if (
            not isinstance(values, list)
            or not values
            or not all(isinstance(v, str) and v.strip() for v in values)
        ):
            raise st.SourceTreeError(
                "%s: %s.%s is not a non-empty list of non-blank strings"
                % (st.CONFIG, _BLOCK, key)
            )
        out.append(tuple(v.lower() for v in values))
    return out[0], out[1]


def opening_phrase(text, phrases, directives):
    """The phrase *text*, a comment, opens with as a whole word, else None.
    A comment that opens with a directive is never matched."""
    body = text.lstrip("#").lstrip().lower()
    if body.startswith(directives):
        return None
    for phrase in phrases:
        if body.startswith(phrase):
            rest = body[len(phrase) :]
            if not rest or not rest[0].isalnum():
                return phrase
    return None


def change_findings(root):
    """{files, comments, findings}: one finding per comment that opens with
    a change phrase."""
    phrases, directives = read_lists(root)
    files = st.python_files(root)
    if not files:
        raise st.SourceTreeError("%s: no Python file to judge -- zero items" % root)
    comments, findings = 0, []
    for relpath in files:
        for lineno, text in st.comment_starts(root, relpath):
            comments += 1
            phrase = opening_phrase(text, phrases, directives)
            if phrase is not None:
                findings.append(
                    "%s:%d: the comment opens with `%s`, which reports a change; "
                    "say why the code is as it is, and leave the change to the "
                    "commit message" % (relpath, lineno, phrase)
                )
    if not comments:
        raise st.SourceTreeError("%s: no comment to judge -- zero items" % root)
    return {"files": len(files), "comments": comments, "findings": sorted(findings)}


# --- the tree itself -------------------------------------------------------------


def test_no_comment_in_the_tree_reports_a_change():
    result = change_findings(_ROOT)
    assert not result["findings"], "\n".join(result["findings"])


# --- fixtures: each rule can fail ---------------------------------------------------

_LISTS_FIXTURE = {
    "phrases": ["now", "fixed", "new:"],
    "directives": ["!", "type:", "noqa"],
}


def _project(tmp_path, text, lists=None):
    root = tmp_path / "proj"
    (root / "config").mkdir(parents=True)
    (root / "src").mkdir()
    block = _LISTS_FIXTURE if lists is None else lists
    (root / st.CONFIG).write_text(json.dumps({_BLOCK: block}), encoding="utf-8")
    (root / "src" / "mod.py").write_text(text, encoding="utf-8")
    return root


@pytest.mark.parametrize(
    "text, line, phrase",
    [
        ("# now uses X\nx = 1\n", 1, "now"),
        ("x = 1  # Fixed the off-by-one\n", 1, "fixed"),
        ("x = 1\n#    NOW, the cache\n", 2, "now"),
        ("# New: a second reader\n", 1, "new:"),
        ("# now\n", 1, "now"),
        ("# The reader is shared.\n# Now the cache holds it.\n", 2, "now"),
    ],
    ids=[
        "own line",
        "trailing",
        "indented and upper case",
        "phrase with punctuation",
        "phrase alone",
        "after a sentence ends",
    ],
)
def test_a_comment_that_opens_with_a_change_phrase_is_a_finding(
    tmp_path, text, line, phrase
):
    findings = change_findings(_project(tmp_path, text))["findings"]
    assert findings == [
        "src/mod.py:%d: the comment opens with `%s`, which reports a change; say "
        "why the code is as it is, and leave the change to the commit message"
        % (line, phrase)
    ], findings


@pytest.mark.parametrize(
    "text",
    [
        "# nowhere else holds the cache\n",
        "# The cache is read once, and\n# now the reader holds it\n",
        "x = '# now uses X'\n# the string above is no comment\n",
        "#!/usr/bin/env python3\n# the entry\n",
        "x = []  # type: list\n",
        "# fixedpoint: a second run changes nothing\n",
    ],
    ids=[
        "not a whole word",
        "a continuation line",
        "inside a string",
        "a shebang",
        "a type comment",
        "longer word",
    ],
)
def test_a_comment_that_explains_is_no_finding(tmp_path, text):
    result = change_findings(_project(tmp_path, text))
    assert result["findings"] == [] and result["comments"] > 0, result


@pytest.mark.parametrize(
    "lists",
    [
        None,
        {"phrases": [], "directives": ["!"]},
        {"phrases": ["now", " "], "directives": ["!"]},
        {"phrases": ["now"]},
        {"phrases": "now", "directives": ["!"]},
    ],
)
def test_a_malformed_block_is_an_error_not_a_pass(tmp_path, lists):
    root = _project(tmp_path, "# a comment\n")
    manifest = {} if lists is None else {_BLOCK: lists}
    (root / st.CONFIG).write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(st.SourceTreeError, match=_BLOCK):
        change_findings(root)


def test_a_tree_with_no_comment_is_an_error_not_a_pass(tmp_path):
    with pytest.raises(st.SourceTreeError, match="zero items"):
        change_findings(_project(tmp_path, "x = 1\n"))


def test_a_tree_with_no_python_file_is_an_error_not_a_pass(tmp_path):
    root = _project(tmp_path, "")
    (root / "src" / "mod.py").unlink()
    with pytest.raises(st.SourceTreeError, match="zero items"):
        change_findings(root)
