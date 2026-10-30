"""
title: Unit — check_structure hides configured text that holds an @
kind: tests
layer: n/a
summary: No message scripts/check_structure.py builds from config/project.json or config/practices.json shows text that holds an `@`, at any depth: a value, a list member, a key name or a path segment. Each row plants a sentinel in one position of keel's own config (served in memory, the tree untouched), runs the one check that reads it, and asserts the check still reports, the sentinel never shows and the line says it is hidden; the rows run over check families and mutation kinds. Beside them, a joined line still shows its harmless members, an empty container is shown as is, and the same text is hidden in each message that names it.
"""

import json
import os
import re
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
    (
        "B",
        "extra_toplevel hidden",
        [(_PROJECT, ("structure", "extra_toplevel"), "M", ".k@y")],
    ),
    (
        "B",
        "extra_toplevel twice",
        [(_PROJECT, ("structure", "extra_toplevel"), "V", [_AT, _AT])],
    ),
    (
        "B",
        "project_checks nested",
        [(_PROJECT, ("structure", "project_checks"), "V", "x/" + _AT)],
    ),
    (
        "B",
        "project_checks not a name",
        [(_PROJECT, ("structure", "project_checks"), "V", [_AT])],
    ),
    # check H
    ("H", "backend path", [(_PROJECT, ("layers", "backend", "path"), "V")]),
    ("H", "backend python", [(_PROJECT, ("layers", "backend", "python"), "V")]),
    ("H", "app module", [(_PROJECT, ("layers", "app", "module"), "V")]),
    ("H", "app path", [(_PROJECT, ("layers", "app", "path"), "V")]),
    ("H", "frontend stack", [(_PROJECT, ("layers", "frontend", "stack"), "V")]),
    ("H", "frontend root", [(_PROJECT, ("layers", "frontend", "root"), "V")]),
    (
        "H",
        "frontend root under a stack",
        [
            (_PROJECT, ("layers", "frontend", "root"), "V"),
            (_PROJECT, ("layers", "frontend", "stack"), "V", "react-vite"),
        ],
    ),
    (
        "H",
        "frontend stack member",
        [(_PROJECT, ("layers", "frontend", "available"), "M")],
    ),
    ("H", "transports enabled", [(_PROJECT, ("transports", "enabled"), "M")]),
    ("H", "transport dir", [(_PROJECT, ("transports", "available", "*"), "V")]),
    (
        "H",
        "transport name",
        [
            (_PROJECT, ("transports", "enabled"), "M"),
            (_PROJECT, ("transports", "available", _AT), "V", "no-such-dir"),
        ],
    ),
    (
        "H",
        "runtime with no dir",
        [(_PROJECT, ("runtimes", "available", _AT), "V", _AT)],
    ),
    (
        "H",
        "model with no dir",
        [(_PROJECT, ("models", "available", _AT), "V", "no-such-dir")],
    ),
    (
        "H",
        "defined profile name",
        [
            (_PRACTICES, ("profiles",), "A"),
            (_PROJECT, ("practices", "profiles", "zz"), "V", True),
        ],
    ),
    ("H", "runtime name", [(_PROJECT, ("runtimes", "available"), "A")]),
    ("H", "runtime default", [(_PROJECT, ("runtimes", "default"), "V")]),
    ("H", "model dir", [(_PROJECT, ("models", "available", "*"), "V")]),
    ("H", "model default", [(_PROJECT, ("models", "default"), "V")]),
    ("H", "profile flag name", [(_PROJECT, ("practices", "profiles"), "A")]),
    # check M
    ("M", "ruff family", [(_PRACTICES, ("rulesets", "ruff", "extend_select"), "M")]),
    ("M", "mypy flag", [(_PRACTICES, ("rulesets", "mypy", "flags"), "M")]),
    # keel's pyproject selects B, so a family deferred under it is selected.
    (
        "M",
        "deferred family selected",
        [(_PRACTICES, ("rulesets", "ruff", "deferred"), "A", "B1zz@x")],
    ),
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
    (
        "S",
        "roster entry twice",
        [(_PROJECT, ("rosters", "readmes"), "V", ["x@y/README.md", "x@y/README.md"])],
    ),
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
    # check W
    (
        "W",
        "effect_proof_skip key",
        [(_PROJECT, ("make_targets", "effect_proof_skip"), "A")],
    ),
    (
        "W",
        "write_shape_exempt key",
        [(_PROJECT, ("make_targets", "write_shape_exempt"), "A")],
    ),
    # check X
    ("X", "run_date key added", [(_PROJECT, ("evidence", "run_date"), "A")]),
    (
        "X",
        "run_date key renamed",
        [(_PROJECT, ("evidence", "run_date", "max_age_days"), "K")],
    ),
    # check Y
    ("Y", "adr key added", [(_PROJECT, ("adr",), "A")]),
    ("Y", "adr key renamed", [(_PROJECT, ("adr", "template_prefix"), "K")]),
    ("Y", "adr template_dir", [(_PROJECT, ("adr", "template_dir"), "V")]),
    ("Y", "adr project_dir", [(_PROJECT, ("adr", "project_dir"), "V", "/" + _AT)]),
    ("Y", "adr template_prefix", [(_PROJECT, ("adr", "template_prefix"), "V")]),
    ("Y", "adr template_adrs member", [(_PROJECT, ("adr", "template_adrs"), "M")]),
    ("Y", "adr dir outside", [(_PROJECT, ("adr", "template_dir"), "V", "/" + _AT)]),
    (
        "Y",
        "adr template_adrs twice",
        [
            (_PROJECT, ("adr", "template_prefix"), "V", "K@-"),
            (_PROJECT, ("adr", "template_adrs"), "V", ["K@-0001-a.md", "K@-0001-a.md"]),
        ],
    ),
    # check Z
    ("Z", "work key added", [(_PROJECT, ("work_naming",), "A")]),
    ("Z", "work key renamed", [(_PROJECT, ("work_naming", "campaign_id"), "K")]),
    ("Z", "campaign_id", [(_PROJECT, ("work_naming", "campaign_id"), "V")]),
    (
        "Z",
        "campaign_id opens with <n>",
        [(_PROJECT, ("work_naming", "campaign_id"), "V", "<n>@")],
    ),
    ("Z", "slice_id", [(_PROJECT, ("work_naming", "slice_id"), "V")]),
    (
        "Z",
        "slice_id off its campaign_id",
        [
            (_PROJECT, ("work_naming", "campaign_id"), "V", "C@P-<n>"),
            (_PROJECT, ("work_naming", "slice_id"), "V", "X-<n>.S<m>"),
        ],
    ),
    (
        "Z",
        "slice_id suffix",
        [(_PROJECT, ("work_naming", "slice_id"), "V", "CMP-<n>@")],
    ),
    ("Z", "slice_trailer", [(_PROJECT, ("work_naming", "slice_trailer"), "V")]),
    ("Z", "backlog_trailer", [(_PROJECT, ("work_naming", "backlog_trailer"), "V")]),
    (
        "Z",
        "adoption_boundary",
        [(_PROJECT, ("work_naming", "adoption_boundary"), "V", [_AT])],
    ),
    (
        "Z",
        "a valid grammar holding an @",
        [
            (_PROJECT, ("work_naming", "campaign_id"), "V", "C@P-<n>"),
            (_PROJECT, ("work_naming", "slice_id"), "V", "C@P-<n>.S<m>"),
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


def _served_tree(monkeypatch, root, letter, block, value):
    """check *letter*'s findings over the tree at *root*, with keel's
    project.json served and its *block* replaced by *value*."""
    project = _load(_PROJECT)
    project[block] = value
    practices = _load(_PRACTICES)
    _isolate(monkeypatch)
    monkeypatch.setattr(
        cs,
        "_read_json_config",
        lambda rel: practices if "practices" in rel else project,
    )
    monkeypatch.setattr(cs, "CHECKS", ((letter, dict(cs.CHECKS)[letter]),))
    return [m for _l, _t, m in cs.run_checks(str(root), project_checks=False)]


def _write(root, relpath, kind, title="t"):
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\ntitle: %s\nkind: %s\n---\n\n# %s\n" % (title, kind, title))


def test_each_adr_finding_hides_the_configured_spaces_and_prefix(monkeypatch, tmp_path):
    """Both ADR number spaces and the prefix hold an `@`, and the tree breaks
    every rule check_Y holds a file to: each finding still names its file,
    with the configured directory and prefix hidden and the tree's own name
    shown."""
    for rel, kind, title in [
        ("a@d/0001-a.md", "adr", "ADR-0001: a"),
        ("a@d/0001-b.md", "adr", "ADR-0009: b"),
        ("a@d/K@-0002-c.md", "adr", "ADR-0002: c"),
        ("a@d/Bad.md", "adr", "Bad"),
        ("a@d/0003-n.md", "note", "ADR-0003: n"),
        ("a@d/t/K@-0001-x.md", "adr", "ADR-K@-0001: x"),
        ("a@d/t/K@-0001-y.md", "adr", "ADR-0007: y"),
        ("a@d/t/0003-z.md", "adr", "ADR-0003: z"),
        ("a@d/t/K@-0004-w.md", "adr", "ADR-K@-0004: w"),
        ("docs/0001-q.md", "adr", "ADR-0001: q"),
        ("r@0001.md", "adr", "ADR-0001: r"),
    ]:
        _write(tmp_path, rel, kind, title)
    adr = {
        "project_dir": "a@d",
        "template_dir": "a@d/t",
        "template_prefix": "K@-",
        "number_digits": 4,
        "template_adrs": ["K@-0001-x.md", "K@-0001-y.md", "K@-0005-q.md"],
    }
    lines = _served_tree(monkeypatch, tmp_path, "Y", "adr", adr)
    assert len(lines) >= 10, lines
    # r@0001.md lies outside both spaces: its name is the tree's, not config.
    shown = [m for m in lines if "@" in m.replace(_HIDDEN, "")]
    assert [m.split(":", 1)[0] for m in shown] == ["r@0001.md"], shown


_H = _HIDDEN
_ADR_ROWS = [
    # (row id, adr keys over keel's own block, (path, kind, title) written,
    # the line a finding opens with)
    (
        "reported: an @ in a project ADR's slug",
        {},
        [
            ("docs/adr/0001-move-to-git@host.md", "adr", "ADR-0001: a"),
            ("docs/adr/0002-move-to-git@other.md", "adr", "ADR-0002: b"),
        ],
        "docs/adr/0002-move-to-git@other.md: an ADR in docs/adr is named NNNN-",
    ),
    (
        "an @ in the slug under a hidden project space",
        {"project_dir": "a@d", "template_dir": "a@d/t"},
        [("a@d/0001-x@y.md", "adr", "ADR-0001: x")],
        "%s/0001-x@y.md: an ADR in %s is named NNNN-" % (_H, _H),
    ),
    (
        "an @ in the slug behind a hidden prefix in a hidden template space",
        {"template_dir": "t@d", "template_prefix": "K@-"},
        [("t@d/K@-0001-a@b.md", "adr", "ADR-K@-0001: a")],
        "%s/%s0001-a@b.md: the template space %s holds only" % (_H, _H, _H),
    ),
    (
        "a hidden prefix in a project ADR's name",
        {"template_prefix": "K@-"},
        [("docs/adr/K@-0001-a@b.md", "adr", "ADR-0001: a")],
        "docs/adr/%s0001-a@b.md: an ADR named with the template prefix" % _H,
    ),
    (
        "an unshipped template ADR behind a hidden prefix",
        {"template_prefix": "K@-"},
        [("docs/adr/keel/K@-0001-a.md", "adr", "ADR-K@-0001: a")],
        "docs/adr/keel/%s0001-a.md: the template does not ship" % _H,
    ),
    (
        "a kind that is not adr behind a hidden prefix",
        {"template_prefix": "K@-"},
        [("docs/adr/keel/K@-0001-a.md", "note", "ADR-K@-0001: a")],
        "docs/adr/keel/%s0001-a.md: an ADR has frontmatter kind" % _H,
    ),
    (
        "a title that names another file behind a hidden prefix",
        {"template_prefix": "K@-"},
        [("docs/adr/keel/K@-0001-a.md", "adr", "wrong")],
        "docs/adr/keel/%s0001-a.md: an ADR's title begins" % _H,
    ),
    (
        "a nested directory under a hidden project space",
        {"project_dir": "a@d", "template_dir": "a@d/t"},
        [("a@d/s@b/0001-q.md", "adr", "ADR-0001: q")],
        "%s/s@b/0001-q.md: an ADR (kind: adr) lives directly in" % _H,
    ),
    (
        "an @ in a directory outside both spaces",
        {},
        [("n@st/0001-q.md", "adr", "ADR-0001: q")],
        "n@st/0001-q.md: an ADR (kind: adr) lives directly in",
    ),
    (
        "a directory that only begins with a hidden space's name",
        {"project_dir": "a@d", "template_dir": "a@d/t"},
        [("a@dx/0001-q.md", "adr", "ADR-0001: q")],
        "a@dx/0001-q.md: an ADR (kind: adr) lives directly in",
    ),
    (
        "a hidden template space inside a hidden project space",
        {"project_dir": "a@d", "template_dir": "a@d/t@"},
        [("a@d/t@/K-0001-x@y.md", "adr", "ADR-K-0001: x")],
        "%s/K-0001-x@y.md: the template space %s holds only" % (_H, _H),
    ),
    (
        "a number taken twice under a hidden space",
        {"project_dir": "a@d", "template_dir": "a@d/t"},
        [
            ("a@d/0001-a.md", "adr", "ADR-0001: a"),
            ("a@d/0001-b.md", "adr", "ADR-0001: b"),
        ],
        "%s/0001-a.md: ADR number 0001 is also taken by %s/0001-b.md" % (_H, _H),
    ),
    (
        "a hidden space spelled with a `.` segment",
        {"project_dir": "./a@d", "template_dir": "a@d/t"},
        [("a@d/0001-a.md", "adr", "ADR-0001: a")],
        "config/project.json: adr.project_dir must be a relative path inside "
        "the project, with no `.`, `..` or empty segment, got '%s'" % _H,
    ),
]


@pytest.mark.parametrize(
    "adr,files,opening", [r[1:] for r in _ADR_ROWS], ids=[r[0] for r in _ADR_ROWS]
)
def test_an_adr_finding_hides_only_the_configured_part_of_a_path(
    monkeypatch, tmp_path, adr, files, opening
):
    """A path is the configured space directory and prefix, hidden when they
    hold an `@`, around the tree's own directory and name, which show as
    written, so the reader can tell which file to rename."""
    for rel, kind, title in files:
        _write(tmp_path, rel, kind, title)
    block = dict(_load(_PROJECT)["adr"], template_adrs=[], **adr)
    lines = _served_tree(monkeypatch, tmp_path, "Y", "adr", block)
    assert [m for m in lines if m.startswith(opening)], lines


_PLAN = """---
title: p
kind: design
---

# P

| Sl@ce | x |
|---|---|
| C@P-1.S1 | a |

## C@P-1 and C@P-2 — two

| Sl@ce | x |
|---|---|
| C@P-1.S1 | a |

## C@P-3 — three

| Sl@ce | x |
|---|---|
| bogus | a |
| C@P-4.S1 | a |
| C@P-3.S2 | a |
| C@P-3.S1 | a |
| C@P-3.S2 | a |
| C@P-3.S5 | a |

## C@P-6 — six

| Sl@ce | x |
|---|---|
| C@P-6.S1 | a |

## C@P-6 — again

| Sl@ce | x |
|---|---|
| C@P-6.S1 | a |

C@P-9.S1 is named here and declared nowhere.

C@P-1.S0 is not an id.
"""


def test_each_plan_finding_hides_the_configured_grammar(monkeypatch, tmp_path):
    """The slice column and both id templates hold an `@`, and a plan doc
    breaks every rule check_Z holds a slice table to: each finding hides the
    configured column, template and every id built from it."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "p.md").write_text(_PLAN)
    work = dict(_load(_PROJECT)["work_naming"])
    work.update(slice_column="Sl@ce", campaign_id="C@P-<n>", slice_id="C@P-<n>.S<m>")
    lines = _served_tree(monkeypatch, tmp_path, "Z", "work_naming", work)
    assert len(lines) >= 8, lines
    # Five findings quote the document's own text, a row's cell and four
    # mentions, which is not configured text; every other `@` is hidden.
    shown = [m for m in lines if "@" in m.replace(_HIDDEN, "")]
    assert sum(m.replace(_HIDDEN, "").count("@") for m in shown) == 5, shown
    assert {m.split(": ", 1)[1].split()[0] for m in shown} == {
        "C@P-1.S0",
        "C@P-4.S1",
        "C@P-1",
        "C@P-2",
        "C@P-9.S1",
    }, shown


_HIDDEN_IDS = {"campaign_id": "C@P-<n>", "slice_id": "C@P-<n>.S<m>"}
_HIDDEN_SLICE = {"campaign_id": "CMP-<n>", "slice_id": "CMP-<n>.S@<m>"}
_SHOWN_IDS = {"campaign_id": "CMP-<n>", "slice_id": "CMP-<n>.S<m>"}
_ID_ROWS = [
    # (row id, id templates, the finding's text after `docs/p.md:<line>: `)
    (
        "campaigns a heading names",
        _HIDDEN_IDS,
        "the heading at line 12 scoping this Slice table names 2 campaigns "
        "(%s <n>=1, %s <n>=2)" % (_H, _H),
    ),
    (
        "the campaign a row sits under",
        _HIDDEN_IDS,
        "C@P-4.S1 sits under the heading of %s <n>=3 (line 18)" % _H,
    ),
    (
        "a slice out of order",
        _HIDDEN_IDS,
        "%s <n>=3 <m>=1 comes after %s <n>=3 <m>=2" % (_H, _H),
    ),
    (
        "a slice declared twice",
        _HIDDEN_IDS,
        "%s <n>=3 <m>=2 is also declared at line 24" % _H,
    ),
    (
        "the slices a campaign skips",
        _HIDDEN_IDS,
        "%s <n>=3 skips %s <n>=3 <m>=3, %s <n>=3 <m>=4" % (_H, _H, _H),
    ),
    (
        "a campaign declared twice",
        _HIDDEN_IDS,
        "campaign %s <n>=6 is also declared at docs/p.md:29" % _H,
    ),
    (
        "the campaigns a campaign skips",
        _HIDDEN_IDS,
        "%s <n>=3 is declared but %s <n>=1, %s <n>=2 is not; campaigns run "
        "from %s <n>=1" % (_H, _H, _H, _H),
    ),
    (
        "the slice template alone holds an @",
        _HIDDEN_SLICE,
        "CMP-3 skips %s <n>=3 <m>=3, %s <n>=3 <m>=4" % (_H, _H),
    ),
    (
        "no template holds an @",
        _SHOWN_IDS,
        "CMP-3 skips CMP-3.S3, CMP-3.S4; rows run",
    ),
    (
        "no template holds an @, a slice out of order",
        _SHOWN_IDS,
        "CMP-3.S1 comes after CMP-3.S2; rows run",
    ),
]


@pytest.mark.parametrize(
    "ids,finding", [r[1:] for r in _ID_ROWS], ids=[r[0] for r in _ID_ROWS]
)
def test_a_plan_finding_shows_the_numbers_beside_a_hidden_id_template(
    monkeypatch, tmp_path, ids, finding
):
    """An id is the configured template around the document's own numbers:
    when the template holds an `@` it is hidden and the numbers still show,
    so the reader can tell which campaign or slice is meant."""
    plan = _PLAN.replace("Sl@ce", "Slice").replace("C@P", ids["campaign_id"][:3])
    if "S@" in ids["slice_id"]:
        plan = re.sub(r"(CMP-[0-9]+)\.S", r"\1.S@", plan)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "p.md").write_text(plan)
    work = dict(_load(_PROJECT)["work_naming"], **ids)
    lines = _served_tree(monkeypatch, tmp_path, "Z", "work_naming", work)
    assert [m for m in lines if m.split(": ", 1)[1].startswith(finding)], lines


_P = "d@r/f.txt"
_T = _P + ".jinja"


@pytest.mark.parametrize(
    "files,declared",
    [
        ({_T: "", _P: ""}, {_P: "z@"}),
        ({_T: "", _P: ""}, {_P: "generated"}),
        ({_T: ""}, {_P: "parity"}),
        ({_T: "x", _P: "x"}, {_P: "divergence"}),
        ({_T: "stale", _P: "other"}, {_P: "parity"}),
    ],
    ids=[
        "unknown kind",
        "generated with a plain",
        "no plain",
        "no divergence",
        "stale line",
    ],
)
def test_a_twin_finding_hides_the_declared_path(files, declared):
    """Each twin-parity refusal names the declared plain path and its twin;
    a path holding an `@` is hidden in both."""
    lines = cs._twin_parity_findings(files, declared)
    assert lines and all(_HIDDEN in m for m in lines), lines
    assert not [m for m in lines if "@" in m.replace(_HIDDEN, "")], lines


def test_a_roster_readme_without_its_heading_is_hidden():
    """A listed README that exists but lacks the roster heading is named
    with its configured path hidden."""
    lines = cs._roster_registry_findings(["x@y/README.md"], set(), lambda p: True)
    assert lines and all(_HIDDEN in m for m in lines), lines
    assert not [m for m in lines if "@" in m.replace(_HIDDEN, "")], lines


def test_a_doc_mechanism_with_no_such_section_hides_the_path():
    """A `doc:` mechanism whose document exists but lacks the cited section
    names the configured path hidden; the section is digits by then."""
    # Built with %, so check_structure's citation scan of this file does not
    # read a document name followed by a section sign as a citation.
    reason = cs._mechanism_reason(
        "doc:%s §3" % "x@y.md", set(), {"x@y.md"}, set(), lambda p: set()
    )
    assert reason and _HIDDEN in reason, reason
    assert "@" not in reason.replace(_HIDDEN, ""), reason


@pytest.mark.parametrize(
    "files,app",
    [
        (["a@p/__init__.py"], {"path": "a@p", "module": "a@p"}),
        (["a@p/main.py"], {"path": "a@p/main.py", "module": "zz"}),
    ],
    ids=["package without __main__", "module off its path"],
)
def test_a_composition_root_refusal_hides_the_path(tmp_path, files, app):
    """layers.app's refusals, shared with scripts/run_app.py, hide a path
    holding an `@`."""
    for rel in files:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("")
    problems = cs.composition_root(app, str(tmp_path))[0]
    assert problems and all(_HIDDEN in m for m in problems), problems
    assert not [m for m in problems if "@" in m.replace(_HIDDEN, "")], problems


def _project_dir_lines(monkeypatch, root):
    """Every finding check_B and the project checks give over *root*, whose
    structure.project_checks names the declared directory `k@y`."""
    project = _load(_PROJECT)
    project["structure"] = dict(
        project["structure"], extra_toplevel=["k@y"], project_checks="k@y"
    )
    _isolate(monkeypatch)
    monkeypatch.setattr(
        cs, "_read_json_config", lambda rel: project if "project" in rel else {}
    )
    monkeypatch.setattr(cs, "CHECKS", (("B", dict(cs.CHECKS)["B"]),))
    return [m for _l, _t, m in cs.run_checks(str(root), project_checks=True)]


def test_a_project_check_directory_holding_an_at_is_hidden(monkeypatch, tmp_path):
    """The directory's label refusal and each project finding's path hide
    the configured name."""
    (tmp_path / "k@y").mkdir()
    (tmp_path / "k@y" / "c.py").write_text("def check(root):\n    return ['f']\n")
    lines = _project_dir_lines(monkeypatch, tmp_path)
    assert any(m.startswith(_HIDDEN + "/c.py") for m in lines), lines
    assert any("README" in m and _HIDDEN in m for m in lines), lines
    assert not [m for m in lines if "@" in m.replace(_HIDDEN, "")], lines


def test_a_project_check_directory_with_no_module_is_hidden(monkeypatch, tmp_path):
    """A declared project-check directory with no module is named hidden."""
    (tmp_path / "k@y").mkdir()
    lines = _project_dir_lines(monkeypatch, tmp_path)
    assert any("module" in m and _HIDDEN in m for m in lines), lines
    assert not [m for m in lines if "@" in m.replace(_HIDDEN, "")], lines


def test_an_undeclared_stack_under_a_hidden_frontend_root(monkeypatch, tmp_path):
    """A directory under the configured frontend root that no stack declares
    is warned about with the root hidden; the directory's own name shows."""
    (tmp_path / "f@e" / "solid").mkdir(parents=True)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.json").write_text("{}")  # served, not read
    layers = dict(_load(_PROJECT)["layers"])
    layers["frontend"] = dict(layers["frontend"], root="f@e", available=[])
    lines = _served_tree(monkeypatch, tmp_path, "H", "layers", layers)
    assert any(m.startswith(_HIDDEN + "/solid: present") for m in lines), lines
    assert not [m for m in lines if "@" in m.replace(_HIDDEN, "")], lines
