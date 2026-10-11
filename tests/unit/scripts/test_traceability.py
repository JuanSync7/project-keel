"""
title: Unit — traceability (the requirement-id grammar, the spec reader, the verdicts and the matrix)
kind: tests
layer: n/a
summary: parse_id accepts `<prefix><digits>` and `<prefix><digits>#AC-<n>` only under the config/project.json `traceability.id_prefixes` registry and refuses a trailing newline, a leading zero, a wrong digit count, a non-ASCII digit, an unlisted prefix and a goal id; the longest listed prefix wins with no fallback, and dropping a registry row refuses every id of that prefix. load_policy refuses a missing, unknown or mistyped key by its dotted name, derived by deleting each key of the shipped block. read_specs defines a requirement from a heading and a criterion from a `- AC-<n>: <text>` line in a `kind: spec` document, skipping fenced blocks, comments and frontmatter, and refuses a malformed heading or criterion, a criterion written as any other list item, an id on an indented, underlined or wrapped heading or anywhere but a heading's first word, a fenced block never closed, a document of another kind that reads as a spec, a duplicate, a missing frontmatter block and a symlink that leaves the specs root. scan_tests reads no file below a directory pytest does not enter. judge gives every unit exactly one verdict: a bare id never discharges a numbered criterion, a gap row excuses only an unnamed unit, dropping a gap row is exactly one more uncovered finding, and zero requirements is a finding unless declared. The matrix is canonical JSON holding no criterion text, and its vocabularies equal the schema's.
"""

import json
import random
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "tests"))
sys.path.insert(0, str(_ROOT / "scripts"))

import traceability as tr  # noqa: E402

import optional_deps  # noqa: E402

pytestmark = pytest.mark.unit

_GAPS_WHERE = "%s %s" % (tr.MANIFEST, tr.GAPS_KEY)


def _shipped():
    manifest = json.loads((_ROOT / tr.MANIFEST).read_text(encoding="utf-8"))
    return manifest[tr.BLOCK]


def _row(prefix, digits, family="requirement", source="self"):
    return {"prefix": prefix, "family": family, "digits": digits, "source": source}


def _policy(rows=None, **changes):
    block = dict(_shipped(), **changes)
    if rows is not None:
        block["id_prefixes"] = rows
    return tr.load_policy({tr.BLOCK: block})


_ROWS = [_row("REQ-", 4), _row("GOAL-", 4, family="goal")]
_TWO = [_row("REQ-", 4), _row("REQ-X-", 3)]


def _prefixes(rows=_ROWS):
    return _policy(rows).prefixes


# ----------------------------------------------------------------- the parser

_ACCEPTED = ["REQ-0001", "REQ-9999", "REQ-0001#AC-1", "REQ-0001#AC-12"]
_REJECTED = [
    "REQ-0001\n",
    "REQ-0001\r",
    "REQ-0001#AC-1\n",
    "REQ-0001#AC-01",
    "REQ-0001#AC-0",
    "REQ-0001#AC-",
    "REQ-0001#AC-1 ",
    "REQ-0001#AC--1",
    "REQ-0001#ac-1",
    "REQ-001",
    "REQ-00001",
    "REQ-000a",
    " REQ-0001",
    "req-0001",
    "FOO-0001",
    "REQ-0001#AC-1#AC-2",
    "REQ-000١",
    "REQ-0001#AC-١",
    "REQ-0001:",
    "",
    "GOAL-0001",
]


@pytest.mark.parametrize("text", _ACCEPTED)
def test_an_id_parses_only_under_the_registry(text):
    parsed = tr.parse_id(text, _prefixes())
    assert str(parsed) == text
    assert parsed.req == text.split(tr.AC_SEP)[0]
    assert (parsed.ac is None) is (tr.AC_SEP not in text)


@pytest.mark.parametrize("text", _REJECTED, ids=ascii)
def test_an_id_outside_the_grammar_is_refused(text):
    with pytest.raises(tr.TraceError):
        tr.parse_id(text, _prefixes())


def test_the_criterion_number_is_an_integer():
    assert tr.parse_id("REQ-0001#AC-12", _prefixes()) == tr.TraceId("REQ-0001", 12)
    assert tr.parse_id("REQ-0001", _prefixes()) == tr.TraceId("REQ-0001", None)


def test_the_longest_listed_prefix_wins_and_never_falls_back():
    for rows in (_TWO, list(reversed(_TWO))):
        prefixes = _prefixes(rows)
        assert tr.parse_id("REQ-X-001", prefixes).req == "REQ-X-001"
        assert tr.parse_id("REQ-0001", prefixes).req == "REQ-0001"
        # Four digits would parse under `REQ-` only by dropping the longer match.
        with pytest.raises(tr.TraceError):
            tr.parse_id("REQ-X-0001", prefixes)


def test_dropping_a_registry_row_refuses_every_id_of_that_prefix():
    ids = {"REQ-": ["REQ-0001", "REQ-0002#AC-3"], "REQ-X-": ["REQ-X-001"]}
    full = _prefixes(_TWO)
    for texts in ids.values():
        for text in texts:
            assert str(tr.parse_id(text, full)) == text
    for dropped in _TWO:
        kept = [row for row in _TWO if row is not dropped]
        prefixes = _prefixes(kept)
        for text in ids[dropped["prefix"]]:
            with pytest.raises(tr.TraceError):
                tr.parse_id(text, prefixes)
        for row in kept:
            for text in ids[row["prefix"]]:
                assert str(tr.parse_id(text, prefixes)) == text
    with pytest.raises(tr.TraceError, match=r"traceability\.id_prefixes"):
        _policy([])


@pytest.mark.parametrize(
    "text, shaped",
    [
        ("REQ-", True),
        ("REQ-SELF-", True),
        ("R2-D2-", True),
        ("REQ", False),
        ("req-", False),
        ("REQ--", False),
        ("-REQ-", False),
        ("2R-", False),
        ("REQ-\n", False),
        ("RÉQ-", False),
        ("", False),
    ],
    ids=ascii,
)
def test_a_prefix_is_upper_case_ascii_words_ending_in_a_dash(text, shaped):
    assert tr.is_prefix_shape(text) is shaped


# ------------------------------------------------------------------ the policy


def test_the_shipped_block_loads():
    policy = tr.load_policy({tr.BLOCK: _shipped()})
    assert [p.prefix for p in policy.prefixes] == [
        row["prefix"] for row in _shipped()["id_prefixes"]
    ]
    assert policy.specs_root == _shipped()["specs_root"]
    assert "kind_evidence" not in _shipped()


def _refused(block, key):
    with pytest.raises(tr.TraceError) as caught:
        tr.load_policy({tr.BLOCK: block})
    assert "%s.%s" % (tr.BLOCK, key) in str(caught.value), caught.value


def test_a_malformed_traceability_block_fails_closed():
    shipped = _shipped()
    for manifest in ({}, {tr.BLOCK: None}, {tr.BLOCK: []}, []):
        with pytest.raises(tr.TraceError, match=tr.BLOCK):
            tr.load_policy(manifest)
    keys = [k for k in shipped if k != "_comment"]
    assert len(keys) >= 8, keys
    for key in keys:
        _refused({k: v for k, v in shipped.items() if k != key}, key)
    _refused(dict(shipped, kind_evidence={}), "kind_evidence")

    row = shipped["id_prefixes"][0]
    for bad_row in (
        {k: v for k, v in row.items() if k != "digits"},
        dict(row, extra=1),
        dict(row, family="epic"),
        dict(row, source="ledger"),
        dict(row, digits=0),
        dict(row, digits=-1),
        dict(row, digits=True),
        dict(row, digits="4"),
        dict(row, prefix="REQ"),
        dict(row, prefix="req-"),
        dict(row, prefix="REQ-\n"),
        "REQ-",
    ):
        _refused(dict(shipped, id_prefixes=[bad_row]), "id_prefixes[0]")
    _refused(dict(shipped, id_prefixes=[row, dict(row)]), "id_prefixes")
    _refused(dict(shipped, id_prefixes={}), "id_prefixes")

    for key in ("specs_root", "tests_root", "matrix_path", "matrix_schema"):
        for bad in ("/abs/path", "../out", "a/../../b", "", 3, None) + (
            "docs/specs ",
            " docs/specs",
            "docs/ specs",
            "docs/\tspecs",
        ):
            _refused(dict(shipped, **{key: bad}), key)
    for bad in ("not-a-name", "1x", "", "class", None):
        _refused(dict(shipped, marker=bad), "marker")
    for bad in ("", "  ", 3, None):
        _refused(dict(shipped, gaps={"REQ-0001": bad}), "gaps")
    _refused(dict(shipped, gaps=[]), "gaps")
    for bad in ("", " \n", 0, False):
        _refused(dict(shipped, no_requirements=bad), "no_requirements")


def test_a_goal_or_spine_row_is_a_valid_registry_row():
    """The row shape is shared with a project that lists other families, so
    the loader accepts them; only what an id may then name is narrower."""
    policy = _policy(
        [_row("REQ-", 3, source="spine"), _row("GOAL-SELF-", 4, family="goal")]
    )
    assert [(p.family, p.source) for p in policy.prefixes] == [
        ("requirement", "spine"),
        ("goal", "self"),
    ]


# ------------------------------------------------------------ the spec reader

_FRONT = "---\ntitle: T\nkind: %s\n---\n"


def _spec(root, name, body, kind="spec"):
    path = root / "docs" / "specs" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_FRONT % kind + body, encoding="utf-8")
    return path


_GOOD = (
    "# Feature\n"
    "\n"
    "## REQ-0001 A thing is made\n"
    "\n"
    "- AC-1: first.\n"
    "- AC-2: second.\n"
    "\n"
    "### Notes\n"
    "\n"
    "- AC-10: still inside the requirement.\n"
    "\n"
    "## REQ-0002\n"
    "\n"
    "No criteria here.\n"
    "\n"
    "## Appendix\n"
    "\n"
    "```\n"
    "## REQ-0003 fenced\n"
    "- AC-1: fenced\n"
    "```\n"
    "<!-- ## REQ-0004 commented\n"
    "- AC-1: commented -->\n"
    "- ACME is not a criterion, and neither is AC-3 in a sentence.\n"
)


def test_a_spec_defines_requirements_and_criteria_by_structure(tmp_path):
    _spec(tmp_path, "feature.md", _GOOD)
    _spec(
        tmp_path,
        "notes.md",
        "```\n## REQ-0009 an example in a document of another kind\n- AC-1: x\n```\n"
        "| REQ-0001 | a table row mentions an id and defines nothing |\n"
        "\nREQ-0001 opens a paragraph and defines nothing.\n",
        kind="doc",
    )
    _spec(tmp_path, "sub/deeper.md", "## REQ-0005 nested file\n")
    (tmp_path / "docs" / "specs" / "plain.txt").write_text("## REQ-0007 x\n")
    catalogue = tr.read_specs(str(tmp_path), _policy(_ROWS))
    reqs = catalogue.requirements
    assert sorted(reqs) == ["REQ-0001", "REQ-0002", "REQ-0005"]
    assert reqs["REQ-0001"].where == "docs/specs/feature.md:7"
    assert reqs["REQ-0001"].criteria == {
        1: "docs/specs/feature.md:9",
        2: "docs/specs/feature.md:10",
        10: "docs/specs/feature.md:14",
    }
    assert reqs["REQ-0002"].criteria == {}
    assert reqs["REQ-0005"].where == "docs/specs/sub/deeper.md:5"
    assert catalogue.units() == [
        "REQ-0001#AC-1",
        "REQ-0001#AC-2",
        "REQ-0001#AC-10",
        "REQ-0002",
        "REQ-0005",
    ]


def test_frontmatter_lines_define_nothing(tmp_path):
    path = tmp_path / "docs" / "specs" / "a.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        "---\ntitle: T\nkind: spec\n# REQ-0009 a yaml comment\nnotes:\n"
        "- AC-1: a yaml list item\n---\n\n## REQ-0001 real\n",
        encoding="utf-8",
    )
    reqs = tr.read_specs(str(tmp_path), _policy(_ROWS)).requirements
    assert sorted(reqs) == ["REQ-0001"]
    assert reqs["REQ-0001"].where == "docs/specs/a.md:9"
    assert reqs["REQ-0001"].criteria == {}


@pytest.mark.parametrize(
    "body",
    [
        "## X-ray *notes* and `code`\n",
        "## REQ-0002 Supersedes REQ-0001\n",
        "## GOAL-0001 An outcome that REQ-0001 serves\n",
        "| REQ-0003 | a table row |\n| --- | --- |\n",
        "REQ-0003 opens a paragraph.\n",
        "A paragraph that ends a section.\n\n---\n",
        "Title\n=====\n\nSub title\n---------\n",
        "1. A first step\n2) A second\n- [ ] a task\n- **bold** item\n> - quoted\n",
        "- AC/DC is not a criterion\n- an AC-1 inside an item\n",
        "    ## REQ-0003 four spaces is a code block\n",
        "```\n## REQ-0003 fenced\n```\n~~~~\n```\n~~~~\n",
    ],
    ids=lambda v: ascii(v)[:40],
)
def test_text_that_only_mentions_an_id_defines_nothing_and_is_not_refused(
    tmp_path, body
):
    _spec(tmp_path, "ok.md", "## REQ-0001 x\n\n" + body)
    found = sorted(tr.read_specs(str(tmp_path), _policy(_ROWS)).requirements)
    assert "REQ-0001" in found and "REQ-0003" not in found, found


@pytest.mark.parametrize(
    "body, said",
    [
        ("## REQ-0009 a requirement\n", "REQ-0009"),
        ("## REQ-0009 a requirement\n- AC-1: x\n", "REQ-0009"),
        ("- AC-1: a criterion with no requirement\n", "criterion"),
        ("## REQ-09 a malformed id\n", "REQ-09"),
        ("## **REQ-0009** wrapped\n", "REQ-0009"),
    ],
    ids=lambda v: ascii(v)[:40],
)
def test_a_document_of_another_kind_that_reads_as_a_spec_is_refused(
    tmp_path, body, said
):
    """Left alone it would define a requirement no run ever judges."""
    _spec(tmp_path, "real.md", "## REQ-0001 x\n")
    _spec(tmp_path, "notes.md", body, kind="doc")
    with pytest.raises(tr.TraceError) as caught:
        tr.read_specs(str(tmp_path), _policy(_ROWS))
    message = str(caught.value)
    assert "docs/specs/notes.md:5" in message, message
    assert said in message and "kind 'doc'" in message, message
    assert "kind: spec" in message, message


def test_a_goal_heading_defines_no_requirement(tmp_path):
    _spec(tmp_path, "g.md", "## GOAL-0001 An outcome\n\n## REQ-0001 A thing\n")
    assert sorted(tr.read_specs(str(tmp_path), _policy(_ROWS)).requirements) == [
        "REQ-0001"
    ]


@pytest.mark.parametrize(
    "body, line",
    [
        ("## REQ-0001: Title\n", 5),
        ("## REQ-01 short\n", 5),
        ("## REQ-00001 long\n", 5),
        ("## FOO-0001 unlisted\n", 5),
        ("## UTF-8 handling\n", 5),
        ("## REQ-0001#AC-1 a criterion as a heading\n", 5),
        ("## REQ-0001 x\n- AC-01: leading zero\n", 6),
        ("## REQ-0001 x\n- AC-0: zero\n", 6),
        ("## REQ-0001 x\n- AC-1 no colon\n", 6),
        ("## REQ-0001 x\n- AC-1:no space\n", 6),
        ("## REQ-0001 x\n- AC-1: \n", 6),
        ("## REQ-0001 x\n- AC-1:\n", 6),
        ("## REQ-0001 x\n- AC-x: text\n", 6),
        ("## REQ-0001 x\n  - AC-1: indented\n", 6),
        ("## REQ-0001 x\n* AC-1: another bullet\n", 6),
        ("## REQ-0001 x\n+ AC-1: another bullet\n", 6),
        ("## REQ-0001 x\n- AC-\u0661: text\n", 6),
        ("## REQ-0001 x\n-  AC-1: two spaces\n", 6),
        ("## REQ-0001 x\n-\tAC-1: a tab\n", 6),
        ("## REQ-0001 x\n1. AC-1: ordered\n", 6),
        ("## REQ-0001 x\n12) AC-1: ordered\n", 6),
        ("## REQ-0001 x\n- [ ] AC-1: a task\n", 6),
        ("## REQ-0001 x\n- [x] AC-1: a done task\n", 6),
        ("## REQ-0001 x\n- **AC-1**: bold\n", 6),
        ("## REQ-0001 x\n- _AC-1_: emphasis\n", 6),
        ("## REQ-0001 x\n- `AC-1`: code\n", 6),
        ("## REQ-0001 x\n> - AC-1: quoted\n", 6),
        ("## REQ-0001 x\n>- AC-1: quoted\n", 6),
        ("## REQ-0001 x\n- AC-1: a\n---\n\n- AC-1: again\n", 9),
        (" ## REQ-0003 one space\n", 5),
        ("   ## REQ-0003 three spaces\n", 5),
        ("REQ-0003 underlined\n-------\n", 5),
        ("REQ-0003 underlined\n=======\n", 5),
        ("**REQ-0003** underlined\n---\n", 5),
        ("## **REQ-0003** bold\n", 5),
        ("## `REQ-0003` code\n", 5),
        ("## [REQ-0003] bracketed\n", 5),
        ("## _REQ-0003_ emphasis\n", 5),
        ("## Requirement REQ-0003 worded\n", 5),
        ("## 3. REQ-0003 numbered\n", 5),
        ("## About `REQ-0003`:\n", 5),
        ("```text\nnever closed\n\n## REQ-0003 below it\n", 5),
        ("````\nfour\n```\n## REQ-0003 below it\n", 5),
        ("~~~\n```\n## REQ-0003 below it\n", 5),
        ("## REQ-0001 x\n- AC-1: a\n- AC-1: again\n", 7),
        ("- AC-1: before any requirement\n", 5),
        ("## REQ-0001 x\n## Other\n- AC-1: after the section closed\n", 7),
        ("## REQ-0001 x\n## REQ-0001 twice\n", 6),
        ("## REQ-0001 x\n### REQ-0002 nested\n", 6),
    ],
    ids=lambda v: ascii(v)[:40] if isinstance(v, str) else None,
)
def test_a_malformed_spec_is_refused_by_line(tmp_path, body, line):
    _spec(tmp_path, "bad.md", body)
    with pytest.raises(tr.TraceError) as caught:
        tr.read_specs(str(tmp_path), _policy(_ROWS))
    assert "docs/specs/bad.md:%d" % line in str(caught.value), caught.value


def test_a_spine_sourced_prefix_cannot_be_defined_here(tmp_path):
    _spec(tmp_path, "s.md", "## REQ-001 from elsewhere\n")
    with pytest.raises(tr.TraceError, match="source"):
        tr.read_specs(str(tmp_path), _policy([_row("REQ-", 3, source="spine")]))


def test_an_unreadable_specs_tree_is_refused(tmp_path):
    policy = _policy(_ROWS)
    with pytest.raises(tr.TraceError, match=r"traceability\.specs_root"):
        tr.read_specs(str(tmp_path), policy)
    _spec(tmp_path, "a.md", "## REQ-0001 x\n")
    _spec(tmp_path, "b.md", "## REQ-0001 same id, other file\n")
    with pytest.raises(tr.TraceError, match="REQ-0001"):
        tr.read_specs(str(tmp_path), policy)
    (tmp_path / "docs" / "specs" / "b.md").write_text("# no frontmatter\n")
    with pytest.raises(tr.TraceError, match="frontmatter"):
        tr.read_specs(str(tmp_path), policy)
    (tmp_path / "docs" / "specs" / "b.md").write_text("---\nkind: spec\n# open\n")
    with pytest.raises(tr.TraceError, match="frontmatter"):
        tr.read_specs(str(tmp_path), policy)
    (tmp_path / "docs" / "specs" / "b.md").write_bytes(b"---\nkind: spec\n---\n\xff\n")
    with pytest.raises(tr.TraceError, match="b.md"):
        tr.read_specs(str(tmp_path), policy)


def test_a_symlink_out_of_the_specs_root_is_refused(tmp_path):
    policy = _policy(_ROWS)
    root = tmp_path / "proj"
    _spec(root, "a.md", "## REQ-0001 x\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "o.md").write_text(_FRONT % "spec" + "## REQ-0002 outside\n")
    specs = root / "docs" / "specs"

    # An alias of a file the walk already reads is the directory's own
    # agent-rules link; it defines nothing twice.
    (specs / "alias.md").symlink_to("a.md")
    assert sorted(tr.read_specs(str(root), policy).requirements) == ["REQ-0001"]

    (specs / "link.md").symlink_to(outside / "o.md")
    with pytest.raises(tr.TraceError, match="link.md"):
        tr.read_specs(str(root), policy)
    (specs / "link.md").unlink()
    (specs / "linked-dir").symlink_to(outside, target_is_directory=True)
    with pytest.raises(tr.TraceError, match="linked-dir"):
        tr.read_specs(str(root), policy)


# ---------------------------------------------------------------- the verdicts


def _catalogue():
    """One requirement with three criteria, one with none."""
    return tr.Catalogue(
        {
            "REQ-0001": tr.Requirement(
                "REQ-0001", "s.md:5", {1: "s.md:6", 2: "s.md:7", 3: "s.md:8"}
            ),
            "REQ-0002": tr.Requirement("REQ-0002", "s.md:10", {}),
        }
    )


def _cite(*ids, test="tests/test_x.py::test_a", where="tests/test_x.py:3"):
    return tr.Citation(tuple(ids), (test,), where)


_ALL = _cite("REQ-0001#AC-1", "REQ-0001#AC-2", "REQ-0001#AC-3", "REQ-0002")


def _judge(citations, **changes):
    changes.setdefault("gaps", {})
    return tr.judge(_catalogue(), citations, _policy(_ROWS, **changes))


def _kinds(judgement):
    return sorted((f["kind"], f["id"]) for f in judgement.findings)


def _verdicts(judgement):
    return {u.id: u.verdict for u in judgement.units}


def test_each_unit_gets_exactly_one_verdict():
    green = _judge([_ALL])
    assert [u.id for u in green.units] == _catalogue().units()
    assert set(_verdicts(green).values()) == {"covered"}
    assert green.findings == [] and green.result == "pass"
    assert green.counts == {"covered": 4, "gap": 0, "uncovered": 0}
    assert all(u.verdict in tr.VERDICTS for u in green.units)

    two = _judge([_cite("REQ-0001#AC-1", "REQ-0001#AC-3", "REQ-0002")])
    assert _kinds(two) == [("uncovered", "REQ-0001#AC-2")]
    assert two.findings[0]["where"] == "s.md:7"
    assert _verdicts(two)["REQ-0001#AC-2"] == "uncovered" and two.result == "fail"

    gapped = _judge(
        [_cite("REQ-0001#AC-1", "REQ-0001#AC-3", "REQ-0002")],
        gaps={"REQ-0001#AC-2": "waits for the store"},
    )
    assert gapped.findings == []
    unit = {u.id: u for u in gapped.units}["REQ-0001#AC-2"]
    assert (unit.verdict, unit.gap, unit.tests) == ("gap", "waits for the store", ())
    assert gapped.counts == {"covered": 3, "gap": 1, "uncovered": 0}


def test_a_bare_id_never_discharges_a_numbered_criterion():
    judged = _judge([_cite("REQ-0001", "REQ-0002")])
    assert _kinds(judged) == [
        ("uncovered", "REQ-0001#AC-1"),
        ("uncovered", "REQ-0001#AC-2"),
        ("uncovered", "REQ-0001#AC-3"),
    ]
    assert _verdicts(judged)["REQ-0002"] == "covered"
    # The bare citation is reported beside the requirement, not dropped.
    assert judged.whole == {"REQ-0001": ("tests/test_x.py::test_a",)}


def test_a_test_wins_over_a_gap_and_the_gap_is_then_redundant():
    judged = _judge([_ALL], gaps={"REQ-0002": "r", "REQ-0001#AC-1": "r"})
    assert _kinds(judged) == [
        ("gap-redundant", "REQ-0001#AC-1"),
        ("gap-redundant", "REQ-0002"),
    ]
    assert set(_verdicts(judged).values()) == {"covered"}
    assert all(f["where"] == _GAPS_WHERE for f in judged.findings)
    assert all(u.gap is None for u in judged.units)


@pytest.mark.parametrize(
    "cited, kind",
    [
        ("REQ-0002#AC-1", "marker-undefined-id"),
        ("REQ-0001#AC-9", "marker-undefined-id"),
        ("REQ-0404", "marker-undefined-id"),
        ("REQ-0404#AC-1", "marker-undefined-id"),
        ("FOO-0001", "marker-malformed-id"),
        ("REQ-0001#AC-01", "marker-malformed-id"),
        ("GOAL-0001", "marker-malformed-id"),
    ],
)
def test_a_marker_naming_no_unit_is_a_finding(cited, kind):
    judged = _judge([_ALL, _cite(cited, where="tests/test_y.py:9")])
    assert judged.findings == [
        {"kind": kind, "where": "tests/test_y.py:9", "id": cited}
    ]


@pytest.mark.parametrize(
    "gap, kind",
    [
        ("REQ-0001", "gap-undefined-id"),
        ("REQ-0002#AC-1", "gap-undefined-id"),
        ("REQ-0001#AC-9", "gap-undefined-id"),
        ("REQ-0404", "gap-undefined-id"),
        ("FOO-0001", "gap-malformed-id"),
        ("REQ-0001#AC-01", "gap-malformed-id"),
    ],
)
def test_a_gap_naming_no_unit_excuses_nothing(gap, kind):
    judged = _judge([_ALL], gaps={gap: "a reason"})
    assert judged.findings == [{"kind": kind, "where": _GAPS_WHERE, "id": gap}]
    bare = _judge([_cite("REQ-0002")], gaps={"REQ-0001": "all of it"})
    assert ("gap-undefined-id", "REQ-0001") in _kinds(bare)
    assert [v for k, v in _verdicts(bare).items() if k.startswith("REQ-0001")] == [
        "uncovered"
    ] * 3


def test_dropping_any_one_gap_row_is_exactly_one_more_uncovered_finding():
    gaps = {unit: "reason for %s" % unit for unit in _catalogue().units()}
    assert len(gaps) == 4
    green = _judge([], gaps=gaps)
    assert green.findings == []
    assert green.counts == {"covered": 0, "gap": 4, "uncovered": 0}
    for dropped in gaps:
        kept = {k: v for k, v in gaps.items() if k != dropped}
        assert _kinds(_judge([], gaps=kept)) == [("uncovered", dropped)]


def test_the_same_test_named_twice_is_listed_once():
    judged = _judge(
        [_ALL, _cite("REQ-0002", "REQ-0002"), _cite("REQ-0002", test="t::b")]
    )
    unit = {u.id: u for u in judged.units}["REQ-0002"]
    assert unit.tests == ("t::b", "tests/test_x.py::test_a")


def test_findings_from_the_scan_are_kept_and_sorted():
    scan = [{"kind": "marker-unattached", "where": "tests/t.py:4", "id": "REQ-0002"}]
    judged = tr.judge(
        _catalogue(),
        [_cite("REQ-0001#AC-1", "REQ-0001#AC-2", "REQ-0001#AC-3")],
        _policy(_ROWS, gaps={}),
        scan,
    )
    assert _kinds(judged) == [
        ("marker-unattached", "REQ-0002"),
        ("uncovered", "REQ-0002"),
    ]


def test_zero_requirements_is_a_stated_state_never_a_pass():
    empty = tr.Catalogue({})
    where = "%s %s" % (tr.MANIFEST, tr.EMPTY_KEY)
    undeclared = tr.judge(empty, [], _policy(_ROWS, gaps={}))
    assert undeclared.findings == [
        {"kind": "no-requirements", "where": where, "id": None}
    ]
    assert undeclared.state == "no-requirements" and undeclared.result == "fail"
    assert undeclared.counts == {"covered": None, "gap": None, "uncovered": None}

    declared = _policy(_ROWS, gaps={}, no_requirements="nothing specified yet")
    stated = tr.judge(empty, [], declared)
    assert stated.findings == [] and stated.result == "pass"
    assert stated.state == "no-requirements"
    assert stated.counts == {"covered": None, "gap": None, "uncovered": None}

    with_marker = tr.judge(empty, [_cite("REQ-0002")], declared)
    assert ("stale-no-requirements", None) in _kinds(with_marker)
    with_requirement = tr.judge(_catalogue(), [_ALL], declared)
    assert _kinds(with_requirement) == [("stale-no-requirements", None)]
    assert with_requirement.state == "traced" and with_requirement.result == "fail"


# ------------------------------------------------------------------ the matrix


def _schema():
    path = _ROOT / _shipped()["matrix_schema"]
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_vocabularies_equal_the_schemas():
    schema = _schema()
    props = schema["properties"]
    unit = props["requirements"]["items"]["properties"]["units"]["items"]
    assert unit["properties"]["verdict"]["enum"] == list(tr.VERDICTS)
    finding = props["findings"]["items"]["properties"]
    assert finding["kind"]["enum"] == list(tr.FINDING_KINDS)
    assert props["state"]["enum"] == list(tr.STATES)
    assert props["result"]["enum"] == list(tr.RESULTS)
    bounds = tr.read_bounds(schema)
    assert bounds.schema_version == props["schema_version"]["const"]
    assert bounds.reason_max > 0 and bounds.id_max > 0


@pytest.mark.parametrize(
    "damage",
    [
        lambda s: s["properties"].pop("schema_version"),
        lambda s: s["properties"]["schema_version"].update(const="1"),
        lambda s: s["properties"]["schema_version"].update(const=True),
        lambda s: s["properties"]["schema_version"].update(const=0),
        lambda s: s["$defs"]["reason"].pop("maxLength"),
        lambda s: s["$defs"]["cited_id"].update(maxLength=0),
        lambda s: s.pop("$defs"),
    ],
)
def test_a_schema_that_states_no_version_or_bound_is_refused(damage):
    schema = _schema()
    damage(schema)
    with pytest.raises(tr.TraceError):
        tr.read_bounds(schema)
    with pytest.raises(tr.TraceError):
        tr.read_bounds([])


def test_the_matrix_is_canonical_and_holds_no_outside_text():
    bounds = tr.read_bounds(_schema())
    long_reason = "r" * (bounds.reason_max + 50)
    long_id = "FOO-" + "9" * (bounds.id_max + 50)
    citations = [
        _cite("REQ-0001#AC-1", "REQ-0001#AC-3", test="tests/b.py::test_b"),
        _cite("REQ-0001#AC-1", "REQ-0001", test="tests/a.py::test_a"),
        _cite(long_id, where="tests/z.py:1"),
        _cite("FOO-1", where="tests/a.py:1"),
    ]
    gaps = {"REQ-0002": long_reason, "REQ-0001#AC-2": "short"}
    policy = _policy(_ROWS, gaps=gaps)
    texts = set()
    for seed in range(5):
        shuffled = list(citations)
        random.Random(seed).shuffle(shuffled)
        reqs = list(_catalogue().requirements.items())
        random.Random(seed).shuffle(reqs)
        catalogue = tr.Catalogue(dict(reqs))
        judged = tr.judge(catalogue, shuffled, policy)
        texts.add(tr.render(tr.build_matrix(policy, bounds, catalogue, judged)))
    assert len(texts) == 1
    (text,) = texts
    assert text.endswith("}\n") and not text.endswith("\n\n")
    matrix = json.loads(text)
    assert text == json.dumps(matrix, indent=2, sort_keys=True) + "\n"

    assert matrix["schema"] == policy.matrix_schema
    assert matrix["schema_version"] == bounds.schema_version
    assert (matrix["state"], matrix["result"]) == ("traced", "fail")
    assert matrix["counts"] == {"covered": 2, "gap": 2, "uncovered": 0}
    assert [r["id"] for r in matrix["requirements"]] == ["REQ-0001", "REQ-0002"]
    first = matrix["requirements"][0]
    assert first["spec"] == "s.md:5"
    assert first["whole_requirement_tests"] == ["tests/a.py::test_a"]
    assert [(u["id"], u["criterion"], u["verdict"]) for u in first["units"]] == [
        ("REQ-0001#AC-1", 1, "covered"),
        ("REQ-0001#AC-2", 2, "gap"),
        ("REQ-0001#AC-3", 3, "covered"),
    ]
    assert first["units"][0]["tests"] == ["tests/a.py::test_a", "tests/b.py::test_b"]
    second = matrix["requirements"][1]["units"][0]
    assert (second["id"], second["criterion"]) == ("REQ-0002", None)
    assert second["gap"] == long_reason[: bounds.reason_max]
    assert matrix["findings"] == [
        {"kind": "marker-malformed-id", "where": "tests/a.py:1", "id": "FOO-1"},
        {
            "kind": "marker-malformed-id",
            "where": "tests/z.py:1",
            "id": long_id[: bounds.id_max],
        },
    ]
    assert str(_ROOT) not in text


def test_a_stopped_run_writes_a_red_matrix_with_unknown_counts():
    bounds = tr.read_bounds(_schema())
    policy = _policy(_ROWS, gaps={}, no_requirements=None)
    for state in ("incomplete", "refused"):
        matrix = tr.stopped_matrix(policy, bounds, state)
        assert (matrix["state"], matrix["result"]) == (state, state)
        assert matrix["counts"] == {"covered": None, "gap": None, "uncovered": None}
        assert matrix["requirements"] == [] and matrix["findings"] == []
    with pytest.raises(ValueError, match="traced"):
        tr.stopped_matrix(policy, bounds, "traced")


def test_every_matrix_shape_validates_against_the_schema():
    jsonschema = optional_deps.importorskip("jsonschema", extra="dev")
    schema = _schema()
    validator = jsonschema.Draft202012Validator(schema)
    jsonschema.Draft202012Validator.check_schema(schema)
    bounds = tr.read_bounds(schema)
    policy = _policy(_ROWS, gaps={"REQ-0002": "later"})
    judged = tr.judge(_catalogue(), [_cite("REQ-0001#AC-1", "REQ-0001", "X")], policy)
    validator.validate(tr.build_matrix(policy, bounds, _catalogue(), judged))
    declared = _policy(_ROWS, gaps={}, no_requirements="none yet")
    empty = tr.Catalogue({})
    validator.validate(
        tr.build_matrix(declared, bounds, empty, tr.judge(empty, [], declared))
    )
    validator.validate(tr.stopped_matrix(policy, bounds, "refused"))
    broken = tr.stopped_matrix(policy, bounds, "incomplete")
    broken["host"] = "somewhere"
    assert list(validator.iter_errors(broken))


# -------------------------------------------------------------- the test scan


def _tests(root, files):
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


_RULE = (("test",), ("Test",), ("test_*.py",), ("build", ".*"))
_MARKED = (
    "import pytest\n"
    "\n"
    "@pytest.mark.req('REQ-0001#AC-1', 'REQ-0002')\n"
    "def test_a():\n"
    "    pass\n"
    "\n"
    "@pytest.mark.req('REQ-0002')\n"
    "def helper():\n"
    "    pass\n"
    "\n"
    "@pytest.mark.req(name)\n"
    "def test_b():\n"
    "    pass\n"
    "\n"
    "@pytest.mark.req\n"
    "def test_c():\n"
    "    pass\n"
    "\n"
    "@pytest.mark.other('REQ-0002')\n"
    "def test_d():\n"
    "    pass\n"
)


def test_the_scan_reads_markers_only_from_files_pytest_collects(tmp_path):
    _tests(
        tmp_path,
        {
            "tests/unit/test_one.py": _MARKED,
            "tests/helpers.py": "import pytest\n@pytest.mark.req('REQ-0002')\ndef test_x(): pass\n",
            "tests/fixtures/broken.py": "def (:\n",
            "tests/conftest.py": "",
            # pytest enters none of these, so a marker below them names
            # nothing that runs: a file that does not parse proves it is unread.
            "tests/build/test_built.py": "def (:\n",
            "tests/unit/.cache/test_hidden.py": "def (:\n",
            "tests/env/pyvenv.cfg": "",
            "tests/env/lib/test_vendored.py": "def (:\n",
            "tests/unit/__pycache__/test_cached.py": "def (:\n",
        },
    )
    citations, findings = tr.scan_tests(str(tmp_path), _policy(_ROWS), _RULE)
    assert citations == [
        tr.Citation(
            ("REQ-0001#AC-1", "REQ-0002"),
            ("tests/unit/test_one.py::test_a",),
            "tests/unit/test_one.py:3",
        )
    ]
    assert findings == [
        {
            "kind": "marker-unattached",
            "where": "tests/unit/test_one.py:7",
            "id": "REQ-0002",
        },
        {"kind": "marker-unreadable", "where": "tests/unit/test_one.py:11", "id": None},
        {"kind": "marker-unreadable", "where": "tests/unit/test_one.py:15", "id": None},
    ]


def test_a_test_file_that_does_not_parse_is_refused_not_skipped(tmp_path):
    _tests(tmp_path, {"tests/test_bad.py": "def (:\n"})
    with pytest.raises(tr.TraceError, match=r"tests/test_bad\.py"):
        tr.scan_tests(str(tmp_path), _policy(_ROWS), _RULE)
    with pytest.raises(tr.TraceError, match=r"traceability\.tests_root"):
        tr.scan_tests(str(tmp_path / "absent"), _policy(_ROWS), _RULE)
