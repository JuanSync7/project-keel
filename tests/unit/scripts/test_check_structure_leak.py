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
    # check H
    ("H", "backend path", [(_PROJECT, ("layers", "backend", "path"), "V")]),
    ("H", "backend python", [(_PROJECT, ("layers", "backend", "python"), "V")]),
    ("H", "app module", [(_PROJECT, ("layers", "app", "module"), "V")]),
    ("H", "app path", [(_PROJECT, ("layers", "app", "path"), "V")]),
    ("H", "frontend stack", [(_PROJECT, ("layers", "frontend", "stack"), "V")]),
    ("H", "frontend root", [(_PROJECT, ("layers", "frontend", "root"), "V")]),
    (
        "H",
        "frontend stack member",
        [(_PROJECT, ("layers", "frontend", "available"), "M")],
    ),
    ("H", "transports enabled", [(_PROJECT, ("transports", "enabled"), "M")]),
    ("H", "transport dir", [(_PROJECT, ("transports", "available", "*"), "V")]),
    ("H", "runtime name", [(_PROJECT, ("runtimes", "available"), "A")]),
    ("H", "runtime default", [(_PROJECT, ("runtimes", "default"), "V")]),
    ("H", "model dir", [(_PROJECT, ("models", "available", "*"), "V")]),
    ("H", "model default", [(_PROJECT, ("models", "default"), "V")]),
    ("H", "profile flag name", [(_PROJECT, ("practices", "profiles"), "A")]),
    # check M
    ("M", "ruff family", [(_PRACTICES, ("rulesets", "ruff", "extend_select"), "M")]),
    ("M", "mypy flag", [(_PRACTICES, ("rulesets", "mypy", "flags"), "M")]),
    (
        "M",
        "per-file-ignore declared",
        [(_PRACTICES, ("rulesets", "ruff", "per_file_ignores", "scripts/**"), "V")],
    ),
    # check N
    ("N", "twin key added", [(_PROJECT, ("template", "twins"), "A")]),
    ("N", "twin key renamed", [(_PROJECT, ("template", "twins", "*"), "K")]),
    ("N", "twin kind", [(_PROJECT, ("template", "twins", "*"), "V")]),
    # check S
    ("S", "roster member", [(_PROJECT, ("rosters", "readmes"), "M")]),
    ("S", "roster nested", [(_PROJECT, ("rosters", "readmes"), "D")]),
    (
        "S",
        "roster README path",
        [(_PROJECT, ("rosters", "readmes"), "M", "x@y/README.md")],
    ),
    # check T
    ("T", "mechanism", [(_PRACTICES, ("practices", 0, "enforced_by"), "M")]),
    ("T", "mechanism nested", [(_PRACTICES, ("practices", 0, "enforced_by"), "D")]),
    (
        "T",
        "script path",
        [(_PRACTICES, ("practices", 0, "enforced_by"), "M", "script:" + _AT)],
    ),
    (
        "T",
        "test path",
        [(_PRACTICES, ("practices", 0, "enforced_by"), "M", "test:" + _AT)],
    ),
    (
        "T",
        "make target",
        [(_PRACTICES, ("practices", 0, "enforced_by"), "M", "make:" + _AT)],
    ),
    (
        "T",
        "check letter",
        [(_PRACTICES, ("practices", 0, "enforced_by"), "M", "check:" + _AT)],
    ),
    (
        "T",
        "doc path",
        [(_PRACTICES, ("practices", 0, "enforced_by"), "M", "doc:" + _AT)],
    ),
    (
        "T",
        "practice id",
        [
            (_PRACTICES, ("practices", 0, "id"), "V"),
            (_PRACTICES, ("practices", 0, "enforced_by"), "M", "check:?"),
        ],
    ),
    (
        "T",
        "practice id, no list",
        [
            (_PRACTICES, ("practices", 0, "id"), "V"),
            (_PRACTICES, ("practices", 0, "enforced_by"), "V", []),
        ],
    ),
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


def _pfi(monkeypatch, declared):
    """check_M's findings when rulesets.ruff.per_file_ignores declares
    *declared* for scripts/**, which pyproject.toml gives T201."""
    rule = (
        _PRACTICES,
        ("rulesets", "ruff", "per_file_ignores", "scripts/**"),
        "V",
        declared,
    )
    errs, _warns = _run(monkeypatch, "M", [rule])
    return [m for m in errs if "per-file-ignore 'scripts/**'" in m]


def test_a_joined_line_hides_only_the_member_holding_the_at(monkeypatch):
    """The declared list is shown member by member: the harmless neighbour
    still shows in its quotes, only the member holding the `@` is hidden."""
    (line,) = _pfi(monkeypatch, ["T999", _AT])
    assert "(declared: ['T999', '%s'])" % _HIDDEN in line, line
    assert "SENTINEL" not in line


def test_an_empty_container_is_shown_as_is(monkeypatch):
    """An empty declared list holds no `@`: it shows as `[]`, nothing hidden."""
    (line,) = _pfi(monkeypatch, [])
    assert line.endswith("(declared: [])"), line
    assert _HIDDEN not in line


def test_a_warning_hides_the_name_and_shows_the_neighbours(monkeypatch):
    """An enabled profile flag naming no defined profile is a warning, not an
    error: its name is hidden there too, and the defined names still show."""
    flag = (_PROJECT, ("practices", "profiles", _AT), "V", True)
    errs, warns = _run(monkeypatch, "H", [flag])
    hits = [m for m in warns if "practices.profiles." in m]
    assert len(hits) == 1, warns
    assert "practices.profiles.%s is enabled" % _HIDDEN in hits[0]
    assert "'ai'" in hits[0] and "SENTINEL" not in hits[0]
    assert not [m for m in errs if "SENTINEL" in m]


def test_the_same_text_is_hidden_in_each_message_naming_it(monkeypatch):
    """One text in two keys yields two findings, and each hides it on its own."""
    errs, _warns = _run(
        monkeypatch,
        "H",
        [
            (_PROJECT, ("runtimes", "default"), "V"),
            (_PROJECT, ("models", "default"), "V"),
        ],
    )
    hits = [m for m in errs if _HIDDEN in m]
    assert any("runtimes.default" in m for m in hits), errs
    assert any("models.default" in m for m in hits), errs
    assert not [m for m in errs if "SENTINEL" in m]


def test_the_frozen_config_marker_is_hidden(monkeypatch, tmp_path):
    """check_K names the declared marker in its refusal; a marker holding an
    `@` is hidden there, over a tree whose one class carries it unfrozen."""
    marker = "practice: " + _AT
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("# %s\nclass A:\n    x = 1\n" % marker)
    practices = _load(_PRACTICES)
    practices.setdefault("tokens", {})["config_marker"] = marker
    monkeypatch.setattr(
        cs, "_read_json_config", lambda rel: practices if "practices" in rel else {}
    )
    _isolate(monkeypatch)
    monkeypatch.setattr(cs, "CHECKS", (("K", dict(cs.CHECKS)["K"]),))
    found = cs.run_checks(str(tmp_path), project_checks=False)
    lines = [m for _l, _t, m in found]
    assert any("class 'A' declares `# %s`" % _HIDDEN in m for m in lines), lines
    assert not [m for m in lines if "SENTINEL" in m]


@pytest.mark.parametrize(
    "pid,path",
    [(_AT, "docs/x.md"), ("P-1", "docs/" + _AT + ".md")],
    ids=["practice id", "doc path segment"],
)
def test_an_unreachable_policy_doc_hides_the_id_and_the_path(pid, path):
    """check_U names the practices citing an unreachable document and the
    document itself; either holding an `@` is hidden."""
    practices = {"practices": [{"id": pid, "enforced_by": ["doc:" + path]}]}
    (line,) = cs._policy_reachability_findings(
        practices, {cs._AGENT_RULES: "", path: ""}
    )
    assert _HIDDEN in line and "SENTINEL" not in line, line


def test_the_deferral_note_hides_the_interpreter_spec(monkeypatch):
    """The one warning a run prints for files it could not parse names
    layers.backend.python; a spec holding an `@` is hidden there."""
    project = _load(_PROJECT)
    project["layers"]["backend"]["python"] = ">=3.11," + _AT
    monkeypatch.setattr(cs, "_read_json_config", lambda rel: project)
    monkeypatch.setattr(cs, "_PARSE_DEFERRED", {"x.py"})
    note = cs._parse_deferral_note()
    assert "asks for %s --" % _HIDDEN in note and "SENTINEL" not in note, note
