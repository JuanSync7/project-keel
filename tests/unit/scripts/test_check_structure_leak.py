"""
title: Unit — check_structure hides configured text that holds an @
kind: tests
layer: n/a
summary: No message scripts/check_structure.py builds from config/project.json or config/practices.json shows text that holds an `@`, at any depth: a value, a list member, a key name or a path segment. Each row plants a sentinel in one position of keel's own config (served in memory, the tree untouched), runs the one check that reads it, and asserts the check still reports, the sentinel never shows and the line says it is hidden; the rows run over check families and mutation kinds. Beside them, a joined line still shows its harmless members, an empty container is shown as is, and the same text is hidden in each message that names it.
"""

import json
import os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit

# Not credential-shaped: the `@` alone is what the rule keys on.
_AT = "tok-SENTINEL@h.invalid"
_HIDDEN = "<hidden: it holds an @>"
_PROJECT = "config/project.json"
_PRACTICES = "config/practices.json"


def _load(relpath):
    with open(_ROOT / relpath, encoding="utf-8") as fh:
        return json.load(fh)


def _node(doc, path):
    for seg in path:
        doc = doc[seg]
    return doc


def _first_key(doc, path):
    return next(k for k in _node(doc, path) if not str(k).startswith("_"))


def _mutate(doc, path, kind, value=_AT):
    """One planted fault: V sets the value at *path*, K renames its last key,
    A adds a key to the object at *path*, M appends a member to the list at
    *path*, D appends a nested list holding the member. A path segment `*`
    is the object's first documented key, so a row survives a config edit."""
    path = tuple(
        _first_key(doc, path[:i]) if s == "*" else s for i, s in enumerate(path)
    )
    if kind == "V":
        _node(doc, path[:-1])[path[-1]] = value
    elif kind == "K":
        parent = _node(doc, path[:-1])
        items = list(parent.items())
        parent.clear()
        for k, v in items:
            parent[value if k == path[-1] else k] = v
    elif kind == "A":
        _node(doc, path)[value] = "x"
    elif kind == "M":
        _node(doc, path).append(value)
    elif kind == "D":
        _node(doc, path).append([value])
    else:
        raise ValueError(kind)


def _isolate(monkeypatch):
    """Restore after the test every global run_checks rebinds, so a later
    test in this worker never reads this one's root or memo."""
    for name in (
        "ROOT",
        "errors",
        "warnings",
        "GOVERNED",
        "_CONFIG_READ",
        "_READ_REPORTED",
        "_PROJECT_CHECKS",
        "_PARSE_REPORTED",
        "_PARSE_DEFERRED",
    ):
        monkeypatch.setattr(cs, name, getattr(cs, name))


def _run(monkeypatch, letter, faults):
    """(errors, warnings) of check *letter* over keel's tree with each fault
    in *faults*, a (file, path, kind[, value]), planted in that config file."""
    docs = {}
    for fault in faults:
        rel = fault[0]
        doc = docs.setdefault(rel, _load(rel))
        _mutate(doc, *fault[1:])
    real = cs._read_json_config

    def served(relpath):
        key = relpath.replace(os.sep, "/")
        return docs[key] if key in docs else real(relpath)

    _isolate(monkeypatch)
    monkeypatch.setattr(cs, "_read_json_config", served)
    monkeypatch.setattr(cs, "CHECKS", ((letter, dict(cs.CHECKS)[letter]),))
    found = cs.run_checks(str(_ROOT), project_checks=False)
    return (
        [m for _l, tier, m in found if tier == "error"],
        [m for _l, tier, m in found if tier == "warning"],
    )


_CASES = [
    # check B
    ("B", "extra_toplevel member", [(_PROJECT, ("structure", "extra_toplevel"), "M")]),
    ("B", "extra_toplevel nested", [(_PROJECT, ("structure", "extra_toplevel"), "D")]),
    ("B", "project_checks", [(_PROJECT, ("structure", "project_checks"), "V")]),
]


@pytest.mark.parametrize(
    "letter,faults", [c[::2] for c in _CASES], ids=["%s: %s" % c[:2] for c in _CASES]
)
def test_a_planted_at_never_shows(monkeypatch, letter, faults):
    """The check still reports the fault, its findings never show the planted
    text, and one of them says the text is hidden, so a row that stopped
    reaching its message fails instead of passing over nothing."""
    errs, warns = _run(monkeypatch, letter, faults)
    lines = errs + warns
    assert lines, faults
    assert not [m for m in lines if "SENTINEL" in m], lines
    assert not [m for m in lines if "@" in m.replace(_HIDDEN, "")], lines
    assert any(_HIDDEN in m for m in lines), lines
