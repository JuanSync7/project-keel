"""
title: Unit — review_docs (the freshness rule and its advisories)
kind: tests
layer: n/a
summary: The pure half of scripts/jobs/review_docs.py, pinned: `updated:` must be an ISO date, never earlier than the file's last commit, and a file modified in the working tree must carry today's date or later. Measured before the rule landed: 135 of 153 governed documents were stamped earlier than their last commit — including AGENT.md and CONVENTIONS.md — and nothing said so. The change-opener advisory, pinned too: each kind of thought opener is read, a phrase counts only as a whole word ("Nowhere" and "Nowadays" are not "now"), the period after a quoted or parenthesised step's number ends no sentence (the shapes of the three lines the real tree reported), while a heading's or a cell's own number and a sentence that ends in a number (`## 3. Removed checks`, "added in 2024.", "1,000.", a line ending "2.") hide no opener after them, a present claim at one ("2. Now run X", a `fixed-point` cell) is reported while `--strict` still exits 0, no manifest is a stated "unchecked", a refused opener list exits 14 with the loader's reason (which key, and why) on the refusal line, and the copied fence grammar equals check_structure's, down to a fence that closes only on its own character (a `~~~` line inside a backtick fence is content, and the reverse) and only when followed by spaces or tabs.
"""

import ast
import datetime
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))

import review_docs  # noqa: E402
from exit_codes import ExitCode  # noqa: E402

import hermetic_git  # noqa: E402

pytestmark = pytest.mark.unit

TODAY = "2026-09-02"


def _find(*records):
    return review_docs.stale_findings(list(records), TODAY)


def test_a_document_stamped_on_or_after_its_last_commit_passes():
    assert _find(("a.md", "2026-08-18", "2026-08-18", False)) == []
    assert _find(("a.md", "2026-09-01", "2026-08-18", False)) == []


def test_a_document_committed_after_its_stamp_is_stale_naming_both_dates():
    """The measured shape: a commit changed the file, the stamp stayed behind."""
    out = _find(("CONVENTIONS.md", "2026-06-24", "2026-08-18", False))
    assert len(out) == 1
    assert out[0]["path"] == "CONVENTIONS.md" and out[0]["expected"] == "2026-08-18"
    assert "2026-06-24" in out[0]["reason"] and "2026-08-18" in out[0]["reason"]


def test_a_modified_document_must_carry_today():
    out = _find(("a.md", "2026-08-18", "2026-08-18", True))
    assert (
        len(out) == 1
        and out[0]["expected"] == TODAY
        and "today" not in out[0]["expected"]
    )
    assert _find(("a.md", TODAY, "2026-08-18", True)) == []


def test_a_never_committed_document_is_held_only_to_today_when_modified():
    assert _find(("new.md", "2026-01-01", None, False)) == []
    assert len(_find(("new.md", "2026-01-01", None, True))) == 1


def test_a_stamp_that_is_not_a_date_is_a_finding():
    out = _find(("a.md", "yesterday", "2026-08-18", False))
    assert len(out) == 1 and "not a date" in out[0]["reason"]


def test_a_committed_stale_stamp_is_reported_once_even_when_also_modified():
    out = _find(("a.md", "2026-06-24", "2026-08-18", True))
    assert len(out) == 1 and out[0]["expected"] == "2026-08-18"


def test_no_records_no_findings():
    assert review_docs.stale_findings([], TODAY) == []


def test_a_stale_reason_names_the_remedy():
    """A finding that does not say how to clear it is a chore with no handle.
    The dates stay in the reason; the command that fixes it is added."""
    committed = _find(("a.md", "2026-06-24", "2026-08-18", False))[0]["reason"]
    modified = _find(("a.md", "2026-08-18", "2026-08-18", True))[0]["reason"]
    for reason in (committed, modified):
        assert "make restamp-docs" in reason, reason
    assert "2026-06-24" in committed and "2026-08-18" in committed
    assert "`updated: %s`" % TODAY in modified


def test_a_bom_prefixed_doc_is_governed(tmp_path):
    """`text.startswith('---')` is False after a U+FEFF, so a BOM document used
    to be silently ungoverned. The span helper is the one grammar the judge and
    the writer (restamp_docs) share."""
    doc = tmp_path / "bom.md"
    text = "\ufeff---\ntitle: x\nupdated: 2026-01-01\n---\n# x\n"
    doc.write_text(text, encoding="utf-8")
    assert review_docs._frontmatter_updated(str(doc)) == "2026-01-01"
    start, end = review_docs.updated_span(text)
    assert text[start:end] == "2026-01-01"


def test_an_empty_updated_never_borrows_the_next_line():
    """`updated:\\s*` used to span the newline and read the NEXT line's token as
    the date; the value is horizontal-whitespace-delimited now."""
    assert review_docs.updated_span("---\nupdated:\ntitle: 2026-01-01\n---\n") is None
    assert review_docs.updated_span("---\ntitle: x\n---\nupdated: 2026-01-01\n") is None


# --- the advisory that stays advisory: unresolved mentions ---------------------


def test_a_backticked_path_that_resolves_to_nothing_is_listed(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "real.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "docs" / "a.md").write_text(
        "See `scripts/real.py`, `scripts/gone.py`, `docs/a.md`, `a.md` and `not a path`.\n"
        "Also `check_structure.py` as a noun.\n",
        encoding="utf-8",
    )
    found = review_docs.unresolved_mentions(str(tmp_path))
    assert found == [
        ("docs/a.md", 1, "scripts/gone.py"),
        ("docs/a.md", 2, "check_structure.py"),
    ]


def test_mentions_never_make_strict_fail(tmp_path, monkeypatch, capsys):
    """Advisory in every mode: `--strict` gates freshness only."""
    (tmp_path / "a.md").write_text("`nowhere/x.py`\n", encoding="utf-8")
    monkeypatch.setattr(review_docs, "collect", lambda root: [])
    assert review_docs.main(["--root", str(tmp_path), "--strict"]) == 0
    assert "unresolved mention" in capsys.readouterr().out


# --- change openers: advisory, since a participle or "now" is as often a present claim

_PHRASES = [
    "now",
    "no longer",
    "previously",
    "added",
    "changed",
    "removed",
    "moved",
    "fixed",
]


def _opener_root(tmp_path, phrases=_PHRASES, history=("CHANGELOG.md", "docs/adr/")):
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "config" / "project.json").write_text(
        json.dumps(
            {
                "change_comments": {"phrases": list(phrases)},
                "doc_drift": {"history_paths": list(history)},
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def _openers(root, name, text):
    (root / name).write_text(text, encoding="utf-8")
    phrases, history = review_docs.opener_policy(str(root))
    return review_docs.change_openers(
        review_docs.shipped_markdown(str(root), history), phrases
    )


def test_the_fence_grammar_has_the_same_syntax_tree():
    """Conflict guards require a copy; syntax equality pins every grammar path."""
    sys.path.insert(0, str(_ROOT / "scripts"))
    import check_structure as cs

    original = ast.parse(inspect.getsource(cs._fence_scan)).body[0]
    wrapper = ast.parse(inspect.getsource(review_docs.unfenced_lines))
    copied = next(
        node
        for node in ast.walk(wrapper)
        if isinstance(node, ast.FunctionDef) and node.name == "scan"
    )
    # Only the entry name differs: tolerating any other rewrite could hide drift.
    copied.name = "_fence_scan"
    assert ast.dump(original) == ast.dump(copied)
    assert review_docs.INLINE_CODE.pattern == cs._INLINE_CODE.pattern


def test_the_fence_grammar_has_the_same_output():
    """Pin the wrapper too, on tracked Markdown and every regression string."""
    sys.path.insert(0, str(_ROOT / "scripts"))
    import check_structure as cs
    import git_tree

    paths = []
    for directory, _dirs, names in cs.sorted_walk(str(_ROOT)):
        for name in names:
            if name.endswith((".md", ".md.jinja")):
                path = Path(directory) / name
                paths.append(path.relative_to(_ROOT).as_posix())
    tree_texts = [
        (rel, (_ROOT / rel).read_text(encoding="utf-8"))
        for rel in sorted(git_tree.tracked(str(_ROOT), paths))
    ]
    assert tree_texts, "a pin over zero tree documents"
    regression = _ROOT / "tests/unit/scripts/test_check_structure_fences.py"
    regression_texts = [
        ("fence regression line %s" % node.lineno, node.value)
        for node in ast.walk(ast.parse(regression.read_text(encoding="utf-8")))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    assert regression_texts, "a pin over zero regression texts"
    for label, text in tree_texts + regression_texts:
        assert review_docs.unfenced_lines(text) == cs._unfenced_lines(text), label


@pytest.mark.parametrize(
    "planted, exempt",
    [
        (
            "A line with no stop\n\nNow the gate runs twice.",
            "A line with no stop\nnow the gate runs twice.",
        ),
        ("`x` reads it. Changed: `y`.", "`x` reads it. `y` changed."),
        ("- **Added** a second pass.", "- A second pass, `added` by the gate."),
        ("| Row | Changed to read the manifest. |", "| Row | Reads the manifest. |"),
        (
            "It reads one file. No longer slow.",
            "It reads one file, no longer slow.",
        ),
        (
            "It reads one file\nand two more.\nNow fast.",
            "It reads one\nnow fast file.",
        ),
        ("## Removed checks", "```\nRemoved checks\n```"),
    ],
    ids=[
        "paragraph",
        "code-span",
        "list-item",
        "table-cell",
        "sentence",
        "next-line",
        "heading",
    ],
)
def test_a_change_phrase_at_each_kind_of_opener_is_reported_once(
    tmp_path, planted, exempt
):
    root = _opener_root(tmp_path)
    assert _openers(root, "a.md", "# Guide\n\nIt reads.\n") == []
    found = _openers(root, "a.md", "# Guide\n\n" + planted + "\n")
    assert len(found) == 1 and found[0][0] == "a.md", found
    assert _openers(root, "a.md", "# Guide\n\n" + exempt + "\n") == []


@pytest.mark.parametrize(
    "text, expected",
    [
        ("| Rule | It reads. Now it reads twice. |", [("a.md", 1, "now")]),
        (
            "| Rule | It reads. |\n|---|---|\n| 2 | One. Removed two. |",
            [("a.md", 3, "removed")],
        ),
        ('| Rule | It is a step ("2. Now run X"). |', []),
        ("| Rule | Reads a \\| Now b. |", []),
        ("| Rule | Reads a \\\\| Now b. |", [("a.md", 1, "now")]),
        ("| Rule | It reads it, e.g. now twice. |", []),
        ("| Rule | It reads **once.** Now twice. |", [("a.md", 1, "now")]),
    ],
    ids=[
        "cell-sentence",
        "body-row-sentence",
        "cell-step-number",
        "escaped-pipe",
        "escaped-backslash-pipe",
        "cell-abbreviation",
        "cell-closing-emphasis",
    ],
)
def test_a_sentence_inside_a_table_cell_opens_a_thought(tmp_path, text, expected):
    """A cell is prose like a paragraph: a sentence after `.`, `!` or `?` in
    it opens a thought, and a quoted step's number ends none."""
    root = _opener_root(tmp_path)
    assert _openers(root, "a.md", text + "\n") == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("It reads it, e.g. now twice.", []),
        ("It reads it, i.e.\nnow twice.", []),
        ("It takes 2.5 s. Now it reads twice.", [("a.md", 1, "now")]),
        ("It reads **once.** Now twice.", [("a.md", 1, "now")]),
        ('It reads "once." Now twice.', [("a.md", 1, "now")]),
    ],
    ids=[
        "abbreviation",
        "abbreviation-at-line-end",
        "decimal",
        "closing-emphasis",
        "closing-quote",
    ],
)
def test_a_sentence_ends_where_the_next_one_opens(tmp_path, text, expected):
    """A period ends a sentence only when the next word does not open in
    lower case, so "e.g." ends none; closing emphasis or a closing quote
    after the stop still ends one, in a line and at its end alike."""
    root = _opener_root(tmp_path)
    assert _openers(root, "a.md", text + "\n") == expected


def test_a_change_phrase_at_a_sentence_opener_is_an_advisory_line(
    tmp_path, monkeypatch, capsys
):
    root = _opener_root(tmp_path)
    (root / "guide.md").write_text("It reads one file. Now it reads two.\n")
    monkeypatch.setattr(review_docs, "collect", lambda root: [])
    assert review_docs.main(["--root", str(root)]) == 0
    lines = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("OPENER ")
    ]
    assert len(lines) == 1 and lines[0].startswith("OPENER guide.md:1:")
    assert "'now'" in lines[0] and "(advisory)" in lines[0]


@pytest.mark.parametrize("mode", [[], ["--strict"], ["--json"], ["--strict", "--json"]])
def test_an_opener_advisory_fails_no_mode(tmp_path, monkeypatch, capsys, mode):
    root = _opener_root(tmp_path)
    (root / "guide.md.jinja").write_text("Now it reads two.\n")
    monkeypatch.setattr(review_docs, "collect", lambda root: [])
    assert review_docs.main(["--root", str(root)] + mode) == 0
    out = capsys.readouterr().out
    if "--json" in mode:
        assert json.loads(out)["change_openers"] == [
            {"path": "guide.md.jinja", "line": 1, "phrase": "now"}
        ]
    else:
        assert "OPENER guide.md.jinja:1:" in out


@pytest.mark.parametrize(
    "text, phrase",
    [
        ("2. Now run `make verify`, then commit.", "now"),
        ("| Mode | Rerun |\n|---|---|\n| writer | fixed-point |", "fixed"),
        ("Removed entries are reported by the audit.", "removed"),
        ("Added keys need a `KEYS` row.", "added"),
        ("Moved files keep their history.", "moved"),
    ],
    ids=["ordered-step", "table-cell", "removed", "added", "moved"],
)
def test_a_present_claim_at_an_opener_is_reported_and_strict_still_passes(
    tmp_path, monkeypatch, capsys, text, phrase
):
    """The reason the rule is advisory: each of these is true prose a reader
    keeps, so it is reported for judgement and fails nothing."""
    root = _opener_root(tmp_path)
    assert [f[2] for f in _openers(root, "guide.md", text + "\n")] == [phrase]
    monkeypatch.setattr(review_docs, "collect", lambda root: [])
    assert review_docs.main(["--root", str(root), "--strict"]) == 0
    out = capsys.readouterr().out
    assert "OPENER guide.md:" in out and "1 change opener(s) (advisory)" in out


@pytest.mark.parametrize(
    "text",
    [
        "Nowhere does the gate read it.",
        "Nowadays the gate reads it.",
        "Fixedness is not a word the gate reads.",
        "Movedown is a flag the gate reads.",
    ],
    ids=["nowhere", "nowadays", "fixedness", "movedown"],
)
def test_a_phrase_inside_a_longer_word_is_not_an_opener(tmp_path, text):
    """A phrase counts only as a whole word: "Nowhere" and "Nowadays" are not
    "now", and a word that merely starts with "fixed" or "moved" is not either."""
    root = _opener_root(tmp_path)
    assert _openers(root, "a.md", text + "\n") == []
    assert _openers(root, "a.md", "Now, " + text[0].lower() + text[1:] + "\n") == [
        ("a.md", 1, "now")
    ]


@pytest.mark.parametrize(
    "text",
    [
        # agents/doc_reviewer/prompt.md
        "   If it reports a change, rewrite that\n"
        '   sentence only to say what is true; if it is a present claim ("2. Now run\n'
        '   X", a cell), return nothing.',
        # agents/tools/review_docs.tool.md
        'that opens with a phrase ("Now\n'
        'runs X" reports a change; "2. Now run X" is a step, so a reader judges it).',
        # docs/guides/deterministic-checks.md
        'participle or "now" at an opener is as often a present claim ("2. Now run `make\n'
        'verify`", a cell) as a report.',
        # the same step number at a line's end
        'It is as often a present claim ("2.\nNow run X") as a report.',
    ],
    ids=["prompt", "tool-spec", "guide", "line-end"],
)
def test_a_step_number_does_not_end_a_sentence(tmp_path, text):
    """A digit run after an opening quote or bracket is a step's number, not
    a sentence end, so the "Now" after a quoted "2." opens nothing. Shapes of the three lines
    the real tree reported before the rule."""
    root = _opener_root(tmp_path)
    assert _openers(root, "a.md", text + "\n") == []


@pytest.mark.parametrize(
    "text, line, phrase",
    [
        ("## 3. Removed checks", 1, "removed"),
        ("### 12. Now the gate runs twice", 1, "now"),
        ("## 3) Removed checks", 1, "removed"),
        ("| Step | What |\n|---|---|\n| 4 | 4) Added a row |", 3, "added"),
        ("It was added in 2024. Now it runs twice.", 1, "now"),
        ("The count is 2. Now it is three.", 1, "now"),
        ("It cost 1,000. Previously it cost less.", 1, "previously"),
        ("The count is 2.\nNow it is three.", 2, "now"),
    ],
    ids=[
        "numbered-heading",
        "numbered-heading-now",
        "parenthesised-heading",
        "numbered-cell",
        "year",
        "count",
        "thousands",
        "count-at-line-end",
    ],
)
def test_a_number_that_is_no_quoted_step_still_ends_a_sentence(
    tmp_path, text, line, phrase
):
    """The step-number rule is for a quoted or parenthesised step ("2. Now run
    X"); a heading's or a cell's own number and a sentence that ends in a
    number hide no opener after them."""
    root = _opener_root(tmp_path)
    assert _openers(root, "a.md", text + "\n") == [("a.md", line, phrase)]


def test_a_word_before_the_period_still_ends_a_sentence(tmp_path):
    root = _opener_root(tmp_path)
    assert _openers(root, "a.md", 'It is a claim ("two. Now run X").\n') == [
        ("a.md", 1, "now")
    ]
    assert _openers(root, "a.md", "It reads v2.\nNow it runs.\n") == [
        ("a.md", 2, "now")
    ]


def test_a_twin_is_read_and_history_and_symlinks_are_not(tmp_path):
    root = _opener_root(tmp_path)
    (root / "docs" / "adr").mkdir(parents=True)
    (root / "docs" / "adr" / "a.md").write_text("Now history.\n", encoding="utf-8")
    (root / "CHANGELOG.md.jinja").write_text("Now history.\n", encoding="utf-8")
    (root / "linked.md").symlink_to(root / "docs" / "adr" / "a.md")
    assert _openers(root, "README.md.jinja", "{{ name }}\n\nNow it runs.\n") == [
        ("README.md.jinja", 3, "now")
    ]


def test_openers_appear_in_the_json_report(tmp_path, monkeypatch, capsys):
    root = _opener_root(tmp_path)
    (root / "a.md").write_text("Now it runs.\n", encoding="utf-8")
    monkeypatch.setattr(review_docs, "collect", lambda root: [])
    assert review_docs.main(["--root", str(root), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["change_openers"] == [{"path": "a.md", "line": 1, "phrase": "now"}]


def test_no_manifest_is_unchecked_never_clean(tmp_path, monkeypatch, capsys):
    (tmp_path / "a.md").write_text("Now it runs.\n", encoding="utf-8")
    monkeypatch.setattr(review_docs, "collect", lambda root: [])
    assert review_docs.main(["--root", str(tmp_path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["change_openers"] is None
    assert review_docs.main(["--root", str(tmp_path)]) == 0
    assert "change openers unchecked: no config/project.json" in capsys.readouterr().out


@pytest.mark.parametrize(
    "manifest, reason",
    [
        (
            '{"change_comments": {"phrases": ["now"]}, "change_comments": {}, '
            '"doc_drift": {"history_paths": ["CHANGELOG.md"]}}',
            'the key "change_comments" appears twice',
        ),
        (
            '{"change_comments": {"phrases": []}, '
            '"doc_drift": {"history_paths": ["CHANGELOG.md"]}}',
            "change_comments.phrases is array; accepted: a list of strings with "
            "a non-empty list",
        ),
        (
            '{"change_comments": {"phrases": ["now"]}, "doc_drift": {}}',
            "[not set] doc_drift.history_paths  (required, no default",
        ),
    ],
    ids=["key-twice", "empty-phrases", "no-history-paths"],
)
def test_a_refused_opener_list_is_a_config_fault(
    tmp_path, monkeypatch, capsys, manifest, reason
):
    """The refusal carries the loader's reason: which key, and why. The key
    names alone are no evidence, since the remedy always holds them."""
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.json").write_text(manifest, encoding="utf-8")
    monkeypatch.setattr(review_docs, "collect", lambda root: [])
    assert review_docs.main(["--root", str(tmp_path)]) == ExitCode.CONFIG
    err = capsys.readouterr().err
    # The loader prints its own line too; the reason must reach the refusal.
    refusal = [line for line in err.splitlines() if line.startswith("review_docs: ")]
    assert len(refusal) == 1 and reason in refusal[0], err


# --- roster rows: the facts the doc reviewer judges -----------------------------


def test_every_roster_row_is_reported_with_its_not_for_cell(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "README.md").write_text(
        "# S\n\n## What ships here\n\n| Member | Purpose | Not for |\n|---|---|---|\n"
        "| `a.py` | does a | b (that is `b.py`) |\n| `b.py` | does b | n/a |\n\n## Later\n\n| Member | Not for |\n|---|---|\n| `z` | no |\n",
        encoding="utf-8",
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "plain.md").write_text("# no roster\n", encoding="utf-8")
    rows = review_docs.roster_rows(str(tmp_path))
    assert rows == [
        {
            "path": "scripts/README.md",
            "member": "a.py",
            "line": 7,
            "not_for": "b (that is `b.py`)",
        },
        {"path": "scripts/README.md", "member": "b.py", "line": 8, "not_for": "n/a"},
    ]


# --- one clock: the judge and the writer read "today" from the same source -----


def test_the_judge_resolves_today_from_source_date_epoch_then_the_clock():
    """The writer (restamp_docs) stamps with SOURCE_DATE_EPOCH when it is set. A
    judge that ignored it held a modified document to a different day than the
    writer stamped, so the remedy it names wrote nothing and the gate stayed red
    (measured with SOURCE_DATE_EPOCH=1767225600). One resolver, owned here."""
    assert review_docs.resolve_today("2030-05-06", {}) == datetime.date(2030, 5, 6)
    env = {"SOURCE_DATE_EPOCH": "86399"}  # one second before midnight UTC
    assert review_docs.resolve_today(None, env) == datetime.date(1970, 1, 1)
    assert review_docs.resolve_today(None, {}) == datetime.date.today()


_RUN_DATE = "A_RUN_DATE"
_CLOCK = datetime.date(2031, 3, 1)


def _run_date_root(tmp_path, max_age_days=1):
    """A project root whose config names a run-date variable and allowlists it."""
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.json").write_text(
        json.dumps(
            {
                "evidence": {
                    "run_date": {"env": _RUN_DATE, "max_age_days": max_age_days}
                },
                "child_env": {"names": [_RUN_DATE]},
            }
        ),
        encoding="utf-8",
    )
    return str(tmp_path)


def test_today_is_the_gate_runs_date_before_the_clock_and_after_the_pins(tmp_path):
    """A gate run that crosses midnight read two days from the clock: a document
    stamped when the run began turned stale before the run ended. The driver's
    one date sits between the two explicit pins and the clock."""
    root = _run_date_root(tmp_path)
    yesterday = _CLOCK - datetime.timedelta(days=1)

    def today(argv_today, env):
        return review_docs.resolve_today(argv_today, env, root, lambda: _CLOCK)

    run = {_RUN_DATE: yesterday.isoformat()}
    assert today(None, {}) == _CLOCK
    assert today(None, run) == yesterday
    pinned = dict(run, SOURCE_DATE_EPOCH="86399")
    assert today(None, pinned) == datetime.date(1970, 1, 1)
    assert today("2030-05-06", pinned) == datetime.date(2030, 5, 6)
    # An explicit pin is never judged by the run date's rule, even a bad one.
    assert today("2030-05-06", {_RUN_DATE: "not-a-date"}) == datetime.date(2030, 5, 6)


@pytest.mark.parametrize(
    "days_from_the_clock, names",
    [(-2, "evidence.run_date.max_age_days"), (1, "later"), (None, "YYYY-MM-DD")],
    ids=["too-old", "tomorrow", "not-a-date"],
)
def test_a_run_date_the_run_could_not_have_is_a_named_error(
    tmp_path, days_from_the_clock, names
):
    """A caller cannot hold the freshness rule to a day of its choosing: the
    variable is accepted only as far from the clock as a run can last."""
    root = _run_date_root(tmp_path)
    raw = "not-a-date"
    if days_from_the_clock is not None:
        raw = (_CLOCK + datetime.timedelta(days=days_from_the_clock)).isoformat()
    with pytest.raises(review_docs.DateSourceError) as caught:
        review_docs.resolve_today(None, {_RUN_DATE: raw}, root, lambda: _CLOCK)
    assert _RUN_DATE in str(caught.value) and names in str(caught.value)


def test_a_root_without_the_block_reads_the_clock(tmp_path):
    env = {_RUN_DATE: "not-a-date"}
    assert review_docs.resolve_today(None, env, str(tmp_path), lambda: _CLOCK) == _CLOCK
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.json").write_text("{ not json", encoding="utf-8")
    with pytest.raises(review_docs.DateSourceError) as caught:
        review_docs.resolve_today(None, env, str(tmp_path), lambda: _CLOCK)
    assert "config/project.json" in str(caught.value)


def test_the_judge_exits_2_naming_a_refused_run_date(monkeypatch, capsys, tmp_path):
    """Through the command: the checkout's own config names the variable."""
    import run_date

    name = run_date.load(review_docs.ROOT).env
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    monkeypatch.setenv(name, "not-a-date")
    assert review_docs.main(["--root", str(tmp_path)]) is review_docs.ExitCode.USAGE
    line = capsys.readouterr().err.strip().splitlines()[-1]
    assert line.startswith("review_docs: cannot tell what today is: "), line
    assert name in line and "YYYY-MM-DD" in line, line
    assert "unset the gate run's date variable" in line.rsplit("; ", 1)[1], line


def test_a_run_date_config_fault_is_answered_with_the_config_fix(
    monkeypatch, capsys, tmp_path
):
    """A variable `child_env.names` does not list is a config fault: passing
    --today or unsetting the variable would not clear it, so the next step
    names the two edits that do."""
    root = tmp_path / "project"
    root.mkdir()
    _run_date_root(root)
    manifest = json.loads((root / "config" / "project.json").read_text("utf-8"))
    manifest["child_env"]["names"] = ["PATH"]
    (root / "config" / "project.json").write_text(json.dumps(manifest), "utf-8")
    monkeypatch.setattr(review_docs, "ROOT", str(root))
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    assert review_docs.main(["--root", str(root)]) is review_docs.ExitCode.USAGE
    line = capsys.readouterr().err.strip().splitlines()[-1]
    next_step = line.rsplit("; ", 1)[1]
    assert "child_env.names" in next_step and _RUN_DATE in next_step, line
    assert "--today" not in next_step, line


@pytest.mark.parametrize(
    "argv_today, epoch",
    [
        (None, "tomorrow"),
        (None, ""),
        (None, "1.5"),
        # Digits, but past datetime's year 9999: fromtimestamp raises, and an
        # uncaught raise exits 1, which in `--check` means "would restamp".
        (None, "99999999999999"),
        ("2026-9-2", None),
        ("2026-02-30", None),
    ],
)
def test_a_malformed_date_source_is_a_named_error_never_a_crash(argv_today, epoch):
    env = {} if epoch is None else {"SOURCE_DATE_EPOCH": epoch}
    with pytest.raises(review_docs.DateSourceError):
        review_docs.resolve_today(argv_today, env)


def test_the_judge_exits_2_on_a_malformed_date_source(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "99999999999999")
    assert review_docs.main(["--root", str(tmp_path)]) == 2
    assert "SOURCE_DATE_EPOCH" in capsys.readouterr().err


# --- read-only git: the judge must not rewrite .git/index ----------------------
#
# Measured on git 2.43.5 (docs/design/downstream-feedback.md CMP-1.S5): `git diff
# HEAD` and plain `git status` refresh stat data and rewrite .git/index, even with
# GIT_OPTIONAL_LOCKS=0; `git --no-optional-locks status`, ls-files, log and
# rev-parse do not. A "read-only" judge pointed at another project's tree must
# leave that index alone, so the changed-path source is pinned here.

_DOC = "---\ntitle: %s\nupdated: 2026-01-01\n---\n\n# %s\n"


def _git(cwd, *argv):
    proc = subprocess.run(
        ["git"] + list(argv),
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        env=dict(
            os.environ,
            GIT_AUTHOR_DATE="2026-01-01T12:00:00+0000",
            GIT_COMMITTER_DATE="2026-01-01T12:00:00+0000",
        ),
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    """A committed repo with governed docs in `sub/docs/` and one outside it.
    The hermetic git config reaches review_docs' own git calls through
    child_env's GIT_CONFIG_* allowlist entries."""
    work = tmp_path / "gitwork"
    work.mkdir()
    for key, value in hermetic_git.git_env_vars(work).items():
        monkeypatch.setenv(key, value)
    top = tmp_path / "repo"
    for rel in ("sub/docs/a.md", "sub/docs/b.md", "outside.md"):
        path = top / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_DOC % (rel, rel), encoding="utf-8")
    _git(top, "init", "-q")
    _git(top, "add", "-A")
    _git(top, "commit", "-q", "-m", "init")
    return top


def _index_state(top):
    index = top / ".git" / "index"
    return index.read_bytes(), index.stat().st_mtime_ns


def test_collect_leaves_the_git_index_untouched(repo):
    (repo / "sub" / "docs" / "a.md").write_text(
        _DOC % ("edited", "edited"), encoding="utf-8"
    )
    # An unmodified tracked file whose mtime moved: its stat data is now stale
    # in the index, so any command that refreshes the index will rewrite it.
    unmodified = repo / "sub" / "docs" / "b.md"
    later = unmodified.stat().st_mtime + 120
    os.utime(str(unmodified), (later, later))
    before = _index_state(repo)

    records = review_docs.collect(str(repo))

    assert _index_state(repo) == before
    modified = {relpath for relpath, _u, _c, is_modified in records if is_modified}
    assert modified == {"sub/docs/a.md"}


def test_modified_paths_below_the_repository_top_are_root_relative(repo):
    (repo / "sub" / "docs" / "a.md").write_text(
        _DOC % ("edited", "edited"), encoding="utf-8"
    )
    (repo / "outside.md").write_text(_DOC % ("edited", "edited"), encoding="utf-8")
    sub = repo / "sub"

    assert review_docs.modified_paths(str(sub)) == {"docs/a.md"}
    assert review_docs.modified_paths(str(repo)) == {"sub/docs/a.md", "outside.md"}
    records = review_docs.collect(str(sub))
    assert {r[0] for r in records if r[3]} == {"docs/a.md"}


def test_modified_paths_is_none_outside_a_repository(tmp_path):
    assert review_docs.modified_paths(str(tmp_path)) is None


def _probe(tmp_path, name):
    """An executable that records it ran (in `<name>.ran`) and passes stdin
    through, so a filter it stands in for would otherwise succeed."""
    script = tmp_path / ("%s.sh" % name)
    script.write_text(
        "#!/bin/sh\necho ran >> %s\ncat\n" % (tmp_path / ("%s.ran" % name))
    )
    script.chmod(0o755)
    return script


def _signed_head(top):
    """Point HEAD at a copy of itself carrying a (fake) PGP signature header, so
    `log.showSignature` makes git run `gpg.program` to verify it."""
    raw = _git(top, "cat-file", "commit", "HEAD")
    head, _blank, body = raw.partition("\n\n")
    sig = (
        "gpgsig -----BEGIN PGP SIGNATURE-----\n \n iQ==\n -----END PGP SIGNATURE-----\n"
    )
    obj = top / "signed.commit"
    obj.write_text(head + "\n" + sig + "\n" + body)
    sha = _git(top, "hash-object", "-t", "commit", "-w", str(obj)).strip()
    obj.unlink()
    _git(top, "update-ref", "HEAD", sha)


def test_judging_a_repository_runs_none_of_its_configured_commands(repo, tmp_path):
    """The repository judged is data. Its own config may name a clean or smudge
    filter (selected by a committed .gitattributes or .git/info/attributes), a
    long-running filter process, or a signature verifier that `git log` runs
    under log.showSignature; status re-hashes a stat-dirty file through the
    clean filter, so each would run inside the judge (measured: 366 runs in
    one audit before the fix)."""
    clean, process, gpg = (_probe(tmp_path, n) for n in ("clean", "process", "gpg"))
    for key, value in (
        ("filter.probe.clean", str(clean)),
        ("filter.probe.smudge", str(clean)),
        ("filter.probe.required", "true"),
        ("filter.lfs-like.process", str(process)),
        ("filter.lfs-like.required", "true"),
        ("log.showSignature", "true"),
        ("gpg.program", str(gpg)),
    ):
        _git(repo, "config", key, value)
    (repo / ".git" / "info").mkdir(exist_ok=True)
    (repo / ".git" / "info" / "attributes").write_text("sub/docs/*.md filter=probe\n")
    (repo / ".gitattributes").write_text("outside.md filter=lfs-like\n")
    _signed_head(repo)
    for rel in ("sub/docs/a.md", "sub/docs/b.md", "outside.md"):
        path = repo / rel
        later = path.stat().st_mtime + 120
        os.utime(str(path), (later, later))

    records = review_docs.collect(str(repo))

    assert records is not None
    ran = sorted(p.name for p in tmp_path.glob("*.ran"))
    assert ran == [], ran


def test_a_root_whose_filter_drivers_cannot_be_listed_is_refused(monkeypatch):
    """Fail closed: when `git config` fails (anything but exit 1, "no match"),
    the call that might have run a driver is not made."""
    calls = []

    class _Proc:
        returncode, stdout, stderr = 3, "", "bad config line 7"

    def fake_run(argv, **_kw):
        calls.append(argv)
        return _Proc()

    monkeypatch.setattr(review_docs.subprocess, "run", fake_run)
    with pytest.raises(review_docs.GitConfigError) as exc:
        review_docs.git_argv("/nowhere", "status")
    assert "bad config line 7" in str(exc.value)
    del calls[:]
    assert review_docs._git("/nowhere", "status") is None
    assert len(calls) == 1 and "config" in calls[0], calls


def test_the_judge_ignores_the_repository_the_parent_was_pointed_at(
    tmp_path, monkeypatch, capsys
):
    """A git hook exports GIT_DIR/GIT_INDEX_FILE for the repository being
    committed. Measured before the fix: under them, `--strict` on another
    repository judged 0 documents and exited 0, because every git call the
    judge made answered for the hook's repository."""
    env = hermetic_git.git_env(tmp_path)
    decoy, other = tmp_path / "decoy", tmp_path / "other"
    decoy.mkdir()
    (decoy / "a").write_text("a\n", encoding="utf-8")
    (other / "docs").mkdir(parents=True)
    (other / "docs" / "x.md").write_text(
        "---\ntitle: x\nupdated: 2020-01-01\n---\n\n# x\n", encoding="utf-8"
    )
    dated = dict(env, GIT_COMMITTER_DATE="@1790000000", GIT_AUTHOR_DATE="@1790000000")
    for top in (decoy, other):
        for argv in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "init"]):
            r = subprocess.run(
                ["git"] + argv, cwd=str(top), env=dated, capture_output=True
            )
            assert r.returncode == 0, r.stderr
    index = decoy / ".git" / "index"
    before = index.read_bytes(), index.stat().st_mtime_ns
    monkeypatch.setenv("GIT_DIR", str(decoy / ".git"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(index))

    rc = review_docs.main(["--root", str(other), "--strict", "--today", "2026-10-06"])
    out = capsys.readouterr().out
    assert rc == 1, out
    assert "STALE docs/x.md" in out and "1 governed document(s)" in out, out
    found = review_docs._git(str(other), "rev-parse", "--absolute-git-dir")
    assert Path(found.strip()).resolve() == (other / ".git").resolve(), found
    assert (index.read_bytes(), index.stat().st_mtime_ns) == before
