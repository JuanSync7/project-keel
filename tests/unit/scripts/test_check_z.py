"""
title: Unit — check_structure check_Z (campaigns and slices carry one checked name)
kind: tests
layer: n/a
summary: check_Z's rule, pinned. config/project.json `work_naming` names the plan-doc kinds, the slice column, the campaign and slice id templates, the backlog pattern, the two trailer keys and the adoption boundary; a missing block is silent until a plan doc exists and then an error naming that doc, and a malformed block fails closed with one error naming the key and judges nothing more. In a plan doc every Slice cell is a well-formed id (a bare number, the retired C2-4 form, a backticked id, a leading zero, S0, a lower-case s and a hyphen separator each fail, naming the doc, the line and the shape); a Slice table sits under exactly one campaign heading, its rows name that campaign and run S1..Sk in document order (a duplicate names both lines, a gap names the missing S); a campaign is declared once across every plan doc and campaigns run from 1 with no gap. A prose mention, bare or with the project's own name as prefix, that resolves to nothing declared is an error in any Markdown document, and so is an id-shaped token outside the grammar (CMP-1.S9a, CMP-1.S02, CMP-1.S0, CMP-01), read whole rather than as the campaign it starts with, while a foreign prefix, inline code and fenced code are ignored. The grammar is read from config, not assumed. Non-plan documents and Phase/Pass tables are not judged; a plan doc with no slice is a warning; two runs agree. The tree the suite runs in is Z-clean and check_Z declares exactly the slice rows a plain line scan of its plan docs finds; a tree with no plan doc (a newly generated project) is a stated skip, and keel's own tree is held to having one by tests/integration/test_copier_generation.py.
"""

import json
import re
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit

_BLOCK = {
    "plan_kinds": ["design"],
    "slice_column": "Slice",
    "campaign_id": "CMP-<n>",
    "slice_id": "CMP-<n>.S<m>",
    "backlog_id": "^[A-Z][A-Z0-9]*(?:-[A-Z][A-Z0-9]*)*-[1-9][0-9]*$",
    "slice_trailer": "Slice",
    "backlog_trailer": "Backlog",
    "adoption_boundary": None,
}

_TWO_CAMPAIGNS = (
    "## CMP-1 — first\n\n"
    "| Slice | Subject | Status |\n|---|---|---|\n"
    "| CMP-1.S1 | a | done |\n| CMP-1.S2 | b | done |\n\n"
    "## CMP-2 — second\n\n"
    "| Slice | Subject | Status |\n|---|---|---|\n"
    "| CMP-2.S1 | c | planned |\n\n"
    "CMP-1.S2 led to CMP-2.S1, and CMP-2 follows CMP-1.\n"
)


def _doc(path, body, kind="design"):
    """A Markdown document with the frontmatter check_Z reads (kind)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\ntitle: t\nkind: %s\nid: x-%s\n---\n\n# Plan\n\n%s"
        % (kind, path.stem, body),
        encoding="utf-8",
    )
    return path


def _manifest(root, block, name="demo"):
    data = {"name": name}
    if block is not None:
        data["work_naming"] = block
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "project.json").write_text(json.dumps(data), encoding="utf-8")


def _isolate(monkeypatch, root):
    monkeypatch.setattr(cs, "ROOT", str(root))
    monkeypatch.setattr(cs, "errors", [])
    monkeypatch.setattr(cs, "warnings", [])
    monkeypatch.setattr(cs, "_CONFIG_READ", {})
    monkeypatch.setattr(cs, "_READ_REPORTED", set())


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A tree with the default block and one plan doc of two campaigns."""
    root = tmp_path / "repo"
    _manifest(root, _BLOCK)
    _doc(root / "docs/design/plan.md", _TWO_CAMPAIGNS)
    _isolate(monkeypatch, root)
    return root


def _zs():
    cs.check_Z()
    return list(cs.errors), list(cs.warnings)


def _rerun(monkeypatch, root):
    _isolate(monkeypatch, root)
    return _zs()


def _keel_policy():
    with open(str(_ROOT / "config" / "project.json"), encoding="utf-8") as fh:
        policy, perrs = cs.work_naming_policy(json.load(fh))
    assert perrs == [], perrs
    return policy


def _line_scan_slices(root, policy):
    """The slice ids in the first cell of a table row of any Markdown file whose
    frontmatter kind is a plan kind: a plain line scan, independent of
    check_Z's table and heading parser, so the two can be compared."""
    slice_re = cs.id_grammar(policy)["slice"]
    kind_re = re.compile(
        r"^kind:\s*(%s)\s*$" % "|".join(re.escape(k) for k in policy["plan_kinds"]),
        re.MULTILINE,
    )
    found = set()
    for dirpath, _dirs, files in cs.walk(str(root)):
        for name in sorted(files):
            if not name.endswith(".md"):
                continue
            text = (Path(dirpath) / name).read_text(encoding="utf-8", errors="replace")
            if not text.startswith("---") or not kind_re.search(
                text.split("\n---", 1)[0]
            ):
                continue
            for line in text.splitlines():
                m = re.match(r"^\|\s*([^|`]*?)\s*\|", line)
                if m and slice_re.match(m.group(1)):
                    found.add(m.group(1))
    return found


def test_this_tree_is_z_clean_and_declares_what_a_line_scan_finds(monkeypatch):
    """The real tree: zero Z findings, and the slices check_Z declares are
    exactly the slice-id rows a plain line scan of the plan docs finds. A tree
    with no plan doc (a newly generated project) is a stated skip, not a pass
    over zero slices; keel's own tree is held to having some by
    tests/integration/test_copier_generation.py."""
    _isolate(monkeypatch, _ROOT)
    errs, warns = _zs()
    assert errs == [] and warns == [], (errs, warns)
    policy = _keel_policy()
    scanned = _line_scan_slices(_ROOT, policy)
    if not scanned:
        pytest.skip(
            "no plan doc in this tree declares a slice -- the rule is "
            "pinned by the fixture trees below"
        )
    inventory = cs.plan_inventory(str(_ROOT), policy)
    assert set(inventory["slices"]) == scanned
    campaign_of = {
        s: cs.id_grammar(policy)["slice"].match(s).group("n") for s in scanned
    }
    assert len(inventory["campaigns"]) == len(set(campaign_of.values()))


def test_the_fixture_tree_is_clean(repo):
    assert _zs() == ([], [])


@pytest.mark.parametrize(
    "cell",
    ["1", "C2-4", "`CMP-1.S3`", "CMP-01.S3", "CMP-1.S0", "CMP-1.s3", "CMP-1-S3"],
    ids=["bare", "retired", "backticked", "leading-zero", "s0", "lower-s", "hyphen"],
)
def test_z_rejects_a_malformed_slice_cell(repo, monkeypatch, cell):
    body = _TWO_CAMPAIGNS.replace(
        "| CMP-1.S2 | b | done |\n",
        "| CMP-1.S2 | b | done |\n| %s | x | done |\n" % cell,
    )
    _doc(repo / "docs/design/plan.md", body)
    errs, _w = _rerun(monkeypatch, repo)
    lineno = (repo / "docs/design/plan.md").read_text(encoding="utf-8").split(
        "\n"
    ).index("| %s | x | done |" % cell) + 1
    assert len(errs) == 1, errs
    assert errs[0].startswith("docs/design/plan.md:%d:" % lineno), errs
    assert "CMP-<n>.S<m>" in errs[0] and cell in errs[0], errs


def test_z_names_a_gap_by_its_missing_slice(repo, monkeypatch):
    _doc(
        repo / "docs/design/plan.md",
        _TWO_CAMPAIGNS.replace("| CMP-1.S2 |", "| CMP-1.S4 |").replace(
            "CMP-1.S2 led", "CMP-1.S4 led"
        ),
    )
    errs, _w = _rerun(monkeypatch, repo)
    assert len(errs) == 1, errs
    assert "CMP-1" in errs[0] and "S2" in errs[0] and "S3" in errs[0], errs
    assert errs[0].startswith("docs/design/plan.md"), errs


def test_z_names_both_lines_of_a_duplicate_slice(repo, monkeypatch):
    _doc(
        repo / "docs/design/plan.md",
        _TWO_CAMPAIGNS.replace(
            "| CMP-1.S2 | b | done |\n",
            "| CMP-1.S2 | b | done |\n| CMP-1.S2 | d | done |\n",
        ),
    )
    errs, _w = _rerun(monkeypatch, repo)
    lines = (repo / "docs/design/plan.md").read_text(encoding="utf-8").split("\n")
    first = lines.index("| CMP-1.S2 | b | done |") + 1
    second = lines.index("| CMP-1.S2 | d | done |") + 1
    assert len(errs) == 1, errs
    assert errs[0].startswith("docs/design/plan.md:%d:" % second), errs
    assert "line %d" % first in errs[0], errs


def test_z_rejects_rows_out_of_document_order(repo, monkeypatch):
    _doc(
        repo / "docs/design/plan.md",
        _TWO_CAMPAIGNS.replace(
            "| CMP-1.S1 | a | done |\n| CMP-1.S2 | b | done |\n",
            "| CMP-1.S2 | b | done |\n| CMP-1.S1 | a | done |\n",
        ),
    )
    errs, _w = _rerun(monkeypatch, repo)
    assert len(errs) == 1 and "document order" in errs[0], errs


def test_z_rejects_a_row_of_another_campaign(repo, monkeypatch):
    _doc(
        repo / "docs/design/plan.md",
        _TWO_CAMPAIGNS.replace(
            "| CMP-1.S2 | b | done |\n",
            "| CMP-1.S2 | b | done |\n| CMP-2.S2 | e | done |\n",
        ),
    )
    errs, _w = _rerun(monkeypatch, repo)
    assert len(errs) == 1, errs
    assert "CMP-2.S2" in errs[0] and "CMP-1" in errs[0], errs


def test_z_rejects_a_table_under_no_campaign_heading(repo, monkeypatch):
    body = (
        "## Status\n\n| Slice | Subject |\n|---|---|\n| CMP-3.S1 | z |\n\n"
        + _TWO_CAMPAIGNS
    )
    _doc(repo / "docs/design/plan.md", body)
    errs, _w = _rerun(monkeypatch, repo)
    assert len(errs) == 1 and "no campaign heading" in errs[0], errs


def test_z_rejects_a_table_under_a_heading_naming_two_campaigns(repo, monkeypatch):
    body = _TWO_CAMPAIGNS + (
        "\n## CMP-3 and CMP-4 together\n\n| Slice | Subject |\n|---|---|\n"
        "| CMP-3.S1 | z |\n"
    )
    _doc(repo / "docs/design/plan.md", body)
    errs, _w = _rerun(monkeypatch, repo)
    assert any("2 campaigns" in e for e in errs), errs


def test_a_slice_subheading_keeps_its_campaign_scope(repo, monkeypatch):
    """`### Slice CMP-2.S1` names a slice, not a campaign: a table under it
    still belongs to the CMP-2 heading above."""
    body = _TWO_CAMPAIGNS + (
        "\n### Slice CMP-2.S1 — detail\n\n| Slice | Note |\n|---|---|\n"
        "| CMP-2.S2 | more |\n"
    )
    _doc(repo / "docs/design/plan.md", body)
    assert _rerun(monkeypatch, repo) == ([], [])


def test_z_rejects_a_campaign_declared_twice_across_docs(repo, monkeypatch):
    _doc(
        repo / "docs/design/other.md",
        "## CMP-2 — again\n\n| Slice | Subject |\n|---|---|\n| CMP-2.S1 | z |\n",
    )
    errs, _w = _rerun(monkeypatch, repo)
    assert len(errs) == 1, errs
    assert "docs/design/other.md" in errs[0] and "docs/design/plan.md" in errs[0], errs


def test_z_rejects_a_gap_between_campaigns(repo, monkeypatch):
    _doc(
        repo / "docs/design/other.md",
        "## CMP-4 — later\n\n| Slice | Subject |\n|---|---|\n| CMP-4.S1 | z |\n",
    )
    errs, _w = _rerun(monkeypatch, repo)
    assert len(errs) == 1 and "CMP-3" in errs[0], errs


@pytest.mark.parametrize(
    "prose, bad",
    [
        ("See CMP-1.S9.\n", "CMP-1.S9"),
        ("See CMP-7.\n", "CMP-7"),
        ("See demo:CMP-2.S5 for it.\n", "demo:CMP-2.S5"),
        ("| CMP-1 | CMP-2.S8 |\n", "CMP-2.S8"),
    ],
    ids=["slice", "campaign", "own-prefix", "table-cell"],
)
def test_z_rejects_a_mention_that_resolves_to_nothing(repo, monkeypatch, prose, bad):
    _doc(repo / "docs/design/plan.md", _TWO_CAMPAIGNS + "\n" + prose)
    errs, _w = _rerun(monkeypatch, repo)
    assert len(errs) == 1 and bad in errs[0], errs
    assert errs[0].startswith("docs/design/plan.md:"), errs


@pytest.mark.parametrize(
    "token",
    ["CMP-1.S9a", "CMP-1.S7x", "CMP-1.S02", "CMP-1.S0", "CMP-01.S1", "CMP-01"],
    ids=["letter-9a", "letter-7x", "leading-zero", "s0", "campaign-zero", "bare-zero"],
)
def test_z_rejects_a_malformed_id_in_prose(repo, monkeypatch, token):
    """A token shaped like an id but outside the grammar is not read as the
    campaign it starts with: it names nothing, so it is a finding."""
    _doc(repo / "docs/design/plan.md", _TWO_CAMPAIGNS + "\nDone in %s.\n" % token)
    errs, _w = _rerun(monkeypatch, repo)
    assert len(errs) == 1, errs
    assert token in errs[0] and "is not a" in errs[0], errs


def test_z_judges_mentions_in_any_markdown_document(repo, monkeypatch):
    _doc(repo / "docs/guides/howto.md", "Shipped in CMP-9.S1.\n", kind="doc")
    errs, _w = _rerun(monkeypatch, repo)
    assert len(errs) == 1 and errs[0].startswith("docs/guides/howto.md:"), errs


def test_z_ignores_foreign_refs_and_code(repo, monkeypatch):
    prose = (
        "jarvis:CMP-9.S9 is theirs, and project-jarvis:CMP-8 too.\n"
        "Inline `CMP-9.S9` is code.\n\n```\nSlice: CMP-9.S9\n```\n\n"
        "A shape is CMP-<n>.S<m>; XCMP-9 is another word.\n"
    )
    _doc(repo / "docs/design/plan.md", _TWO_CAMPAIGNS + "\n" + prose)
    assert _rerun(monkeypatch, repo) == ([], [])


def test_z_reads_its_grammar_from_config(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    block = dict(
        _BLOCK,
        plan_kinds=["roadmap"],
        slice_column="Task",
        campaign_id="WP-<n>",
        slice_id="WP-<n>/T<m>",
    )
    _manifest(root, block)
    _doc(
        root / "docs/plan.md",
        "## WP-1 — work package\n\n| Task | What |\n|---|---|\n| WP-1/T1 | a |\n"
        "| WP-1/T2 | b |\n\nWP-1/T2 follows WP-1/T1; CMP-1.S1 is not our grammar.\n",
        kind="roadmap",
    )
    # A design doc is not a plan doc under this block: its Slice table is prose.
    _doc(root / "docs/design/x.md", "| Slice | x |\n|---|---|\n| 1 | y |\n")
    _isolate(monkeypatch, root)
    assert _zs() == ([], [])
    assert sorted(
        cs.plan_inventory(str(root), cs.work_naming_policy({"work_naming": block})[0])[
            "slices"
        ]
    ) == ["WP-1/T1", "WP-1/T2"]
    _doc(
        root / "docs/plan.md",
        "## WP-1 — work package\n\n| Task | What |\n|---|---|\n| CMP-1.S1 | a |\n",
        kind="roadmap",
    )
    errs, _w = _rerun(monkeypatch, root)
    assert len(errs) == 1 and "WP-<n>/T<m>" in errs[0], errs


@pytest.mark.parametrize(
    "block, key",
    [
        ({k: v for k, v in _BLOCK.items() if k != "slice_id"}, "slice_id"),
        (dict(_BLOCK, slice_colum="Slice"), "slice_colum"),
        (dict(_BLOCK, plan_kinds=[]), "work_naming.plan_kinds"),
        (dict(_BLOCK, plan_kinds="design"), "work_naming.plan_kinds"),
        (dict(_BLOCK, slice_column=""), "work_naming.slice_column"),
        (dict(_BLOCK, campaign_id="CMP-<n>-<n>"), "work_naming.campaign_id"),
        (dict(_BLOCK, campaign_id="CMP-"), "work_naming.campaign_id"),
        (dict(_BLOCK, campaign_id="<n>"), "work_naming.campaign_id"),
        (dict(_BLOCK, slice_id="WP-<n>.S<m>"), "work_naming.slice_id"),
        (dict(_BLOCK, slice_id="CMP-<n><m>"), "work_naming.slice_id"),
        (dict(_BLOCK, slice_id="CMP-<n>.S"), "work_naming.slice_id"),
        (dict(_BLOCK, slice_id="CMP-<n>.S<m>.<m>"), "work_naming.slice_id"),
        (dict(_BLOCK, slice_id="CMP-<n>.S<x>"), "work_naming.slice_id"),
        (dict(_BLOCK, backlog_id="^[A-Z"), "work_naming.backlog_id"),
        (dict(_BLOCK, slice_trailer="Slice id"), "work_naming.slice_trailer"),
        (dict(_BLOCK, backlog_trailer="slice"), "work_naming.backlog_trailer"),
        (dict(_BLOCK, adoption_boundary=True), "work_naming.adoption_boundary"),
        (dict(_BLOCK, adoption_boundary=""), "work_naming.adoption_boundary"),
        ("CMP", "work_naming must be an object"),
    ],
    ids=[
        "missing-key",
        "unknown-key",
        "empty-kinds",
        "kinds-not-a-list",
        "empty-column",
        "two-n",
        "no-n",
        "no-literal",
        "slice-not-campaign",
        "no-separator",
        "no-m",
        "two-m",
        "unknown-placeholder",
        "bad-backlog-regex",
        "trailer-with-space",
        "trailers-collide",
        "bool-boundary",
        "empty-boundary",
        "not-an-object",
    ],
)
def test_z_fails_closed_on_a_malformed_block(repo, monkeypatch, block, key):
    """One error naming the key, and nothing judged: the malformed row below
    would be its own error under a good block."""
    _manifest(repo, block)
    _doc(repo / "docs/design/plan.md", _TWO_CAMPAIGNS + "\n| Slice |\n|---|\n| 1 |\n")
    errs, _w = _rerun(monkeypatch, repo)
    assert len(errs) == 1, errs
    assert errs[0].startswith("config/project.json:"), errs
    assert key in errs[0], errs


def test_z_is_silent_without_a_block_or_a_plan_doc(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    _manifest(root, None)
    _doc(
        root / "docs/guides/x.md",
        "CMP-9.S9 is not judged without a block.\n",
        kind="doc",
    )
    _isolate(monkeypatch, root)
    assert _zs() == ([], [])


def test_z_names_the_plan_doc_when_the_block_is_missing(repo, monkeypatch):
    _manifest(repo, None)
    errs, _w = _rerun(monkeypatch, repo)
    assert len(errs) == 1, errs
    assert "work_naming" in errs[0] and "docs/design/plan.md" in errs[0], errs


def test_z_ignores_non_plan_docs_and_phase_or_pass_tables(repo, monkeypatch):
    _doc(repo / "docs/guides/x.md", "| Slice | x |\n|---|---|\n| 1 | y |\n", kind="doc")
    _doc(
        repo / "docs/design/plan.md",
        _TWO_CAMPAIGNS
        + "\n| Phase | Subject |\n|---|---|\n| 1 | a |\n\n| Pass | Subject |\n|---|---|\n"
        "| 2 | b |\n\n| Subject | Slice |\n|---|---|\n| c | 3 |\n",
    )
    assert _rerun(monkeypatch, repo) == ([], [])


def test_z_warns_on_a_plan_doc_with_no_slice(repo, monkeypatch):
    _doc(
        repo / "docs/design/empty.md",
        "## CMP-3 — not started\n\n| Slice | Subject |\n|---|---|\n",
    )
    errs, warns = _rerun(monkeypatch, repo)
    assert errs == [], errs
    assert len(warns) == 1 and "docs/design/empty.md" in warns[0], warns


def test_z_is_a_fixed_point(repo, monkeypatch):
    """Two runs over one tree give the same findings: the check derives, it
    never accumulates."""
    _doc(repo / "docs/design/plan.md", _TWO_CAMPAIGNS + "\nSee CMP-1.S9 and CMP-8.\n")
    first = _rerun(monkeypatch, repo)
    assert len(first[0]) == 2, first
    assert _rerun(monkeypatch, repo) == first


def test_the_missing_block_fallback_is_the_shipped_default():
    """A tree without the block still finds its plan docs by the template's
    default kinds and column; the two constants are that default, not a
    second opinion."""
    policy = _keel_policy()
    assert list(cs._WORK_PLAN_KINDS_FALLBACK) == policy["plan_kinds"]
    assert policy["slice_column"] == cs._WORK_SLICE_COLUMN_FALLBACK


def test_id_grammar_compiles_the_templates():
    policy, perrs = cs.work_naming_policy({"work_naming": _BLOCK})
    assert perrs == [], perrs
    grammar = cs.id_grammar(policy)
    assert grammar["slice"].match("CMP-12.S3").groups() == ("12", "3")
    assert grammar["campaign"].match("CMP-12").groups() == ("12",)
    for bad in ("CMP-0.S1", "CMP-1.S01", "cmp-1.S1", "CMP-1.S1x"):
        assert grammar["slice"].match(bad) is None, bad
    found = [
        m.group(0)
        for m in grammar["mention"].finditer(
            "x:CMP-1.S2, CMP-3. CMP-4.S5x XCMP-6 CMP-7.S8"
        )
    ]
    # CMP-4.S5x is read whole, so it is judged malformed, never as CMP-4.
    assert found == ["x:CMP-1.S2", "CMP-3", "CMP-4.S5x", "CMP-7.S8"], found
    assert grammar["slice"].match("CMP-4.S5x") is None
