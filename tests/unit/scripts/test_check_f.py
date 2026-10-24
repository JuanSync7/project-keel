"""
title: Unit — check_structure check_F (tool spec body contract and owner roll-up)
kind: tests
layer: n/a
summary: check_F pinned. The owner half: config/project.json `accountability.default_owner` is read through scripts/config_loader.py's KEYS row (null, or a string that is one owner token never TBD or the word null in any case; null by default, and its refusal line puts that bound on the string, not on null) on every run, so a refused value is an error with no TBD document in the tree; a `kind: tool` or `agent` document whose frontmatter owner is `TBD` in any letter case inherits it, and with no default, or a refused one, is an error naming the document and the key; an owner outside the CONVENTIONS §12 grammar (a quoted or commented placeholder) is an error naming the document and the grammar; a written null (`null` in any letter case, or `~`) is an error the default does not cover, where an empty or missing owner stays a warning; build_corpus takes neither TBD nor a null spelling as a real owner; any other owner is never judged. The body half: a `kind: tool` spec's body is the seven sections CONVENTIONS §10 names, in that order; its `## Side effects` opens with the word that matches `tool_effect` (READ-ONLY / WRITES / MODEL-CALL); and its `## When to use` carries at least one `- NOT` bullet — the negative-scope line that says what the tool is not for and names the sibling that is. Seven specs complied by discipline (six carried the NOT line); this makes the discipline a rule so the eighth cannot quietly skip it.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit

_BODY = """# query_corpus

## Command

`python scripts/query_corpus.py <q>`

## Purpose

Find nodes.

## When to use

- When an agent needs a node.
- NOT to build or mutate the corpus (that is `build_corpus`).

## Args

- `q` — the query.

## Output

JSON.

## Side effects

READ-ONLY. Reads the corpus; writes nothing.

## Used by

- agents/wiki_navigator
"""


def _find(text=_BODY, effect="read-only", path="agents/tools/query_corpus.tool.md"):
    return cs._tool_spec_body_findings(path, text, effect)


def test_a_conforming_spec_passes():
    assert _find() == []


@pytest.mark.parametrize(
    "section",
    ["Command", "Purpose", "When to use", "Args", "Output", "Side effects", "Used by"],
)
def test_a_missing_section_is_named(section):
    text = _BODY.replace("## %s\n" % section, "## Something else\n")
    errs = _find(text)
    assert len(errs) >= 1 and any(section in e for e in errs), errs


def test_sections_out_of_order_error():
    text = _BODY.replace(
        "## Purpose\n\nFind nodes.\n\n## When to use", "## When to use"
    ).replace("## Args", "## Purpose\n\nFind nodes.\n\n## Args")
    errs = _find(text)
    assert len(errs) == 1 and "order" in errs[0], errs


def test_an_extra_section_between_required_ones_is_allowed():
    text = _BODY.replace("## Args", "## Examples\n\nnone\n\n## Args")
    assert _find(text) == []


@pytest.mark.parametrize(
    "effect, word",
    [("read-only", "READ-ONLY"), ("writes", "WRITES"), ("model-call", "MODEL-CALL")],
)
def test_side_effects_must_open_with_the_word_for_the_declared_effect(effect, word):
    text = _BODY.replace("READ-ONLY. Reads", "%s. Reads" % word)
    assert _find(text, effect) == []


def test_side_effects_disagreeing_with_tool_effect_errors():
    """Frontmatter says writes, the body says READ-ONLY: an agent trusting either
    one is wrong half the time."""
    errs = _find(effect="writes")
    assert len(errs) == 1 and "WRITES" in errs[0] and "READ-ONLY" in errs[0], errs


def test_side_effects_opening_with_prose_errors():
    text = _BODY.replace("READ-ONLY. Reads the corpus", "It reads the corpus")
    errs = _find(text)
    assert len(errs) == 1 and "Side effects" in errs[0], errs


def test_a_when_to_use_without_a_not_line_errors():
    """The negative-scope line is the discriminator between siblings — the
    answer to 'why are these two separate tools?'. accountability_report was
    the one spec without it."""
    text = _BODY.replace(
        "- NOT to build or mutate the corpus (that is `build_corpus`).\n", ""
    )
    errs = _find(text)
    assert len(errs) == 1 and "NOT" in errs[0] and "When to use" in errs[0], errs


def test_a_not_line_in_another_section_does_not_count():
    text = _BODY.replace(
        "- NOT to build or mutate the corpus (that is `build_corpus`).\n", ""
    ).replace("JSON.\n", "JSON.\n\n- NOT a table.\n")
    errs = _find(text)
    assert len(errs) == 1 and "When to use" in errs[0], errs


def test_headings_inside_fenced_code_are_not_sections():
    text = _BODY.replace(
        "`python scripts/query_corpus.py <q>`", "```\n## Fake\npython x\n```"
    )
    assert _find(text) == []


# --- the owner roll-up: a TBD owner inherits accountability.default_owner ----

_KEY = ("accountability", "default_owner")
_DOTTED = "accountability.default_owner"


def _rollup(governed, default, refused=False):
    return cs._owner_rollup(governed, default, refused)


def test_the_default_owner_row_is_an_optional_owner_token_defaulting_to_null():
    """Null is "no default configured": absent, a TBD owner has nothing to
    inherit, so it is red rather than quietly owned by a name nobody chose."""
    (row,) = cs.config_loader.rows(_KEY)
    assert row.type == "nonempty_str_or_null"
    assert row.default is None and not row.required
    assert row.file == cs.config_loader.CONFIG_FILE
    assert row.env is None and not row.secret
    assert "TBD" in row.meaning and "null" in row.meaning
    check, _text = row.accepts
    assert check(None) and check("platform-team") and check("ops@example.org")
    for bad in ("TBD", "tbd", "Tbd", "two words", "a/b", "", "null", "NULL", "~"):
        assert not check(bad), bad


def test_the_refusal_puts_the_bound_on_the_string_and_null_apart():
    """The bound judges the string: null is accepted on its own, so the line
    must not read as if null had to be an owner token."""
    _value, (line,) = cs._default_owner({"accountability": {"default_owner": "TBD"}})
    assert line.endswith(
        "; accepted: null, or a non-empty string with one owner token of "
        "letters, digits and `._@-`, never TBD or the word null in any case"
    ), line


# Spellings of the placeholder: TBD in any case is TBD.
_TBD_CASES = ["TBD", "tbd", "Tbd"]
# Owners outside CONVENTIONS section 12's grammar: a quoted or commented
# placeholder is neither TBD nor an owner, so it is red, never owned.
_OFF_GRAMMAR = ['"TBD"', "'TBD'", "TBD # later", "two words", '"ops"']


@pytest.mark.parametrize("owner", _TBD_CASES)
@pytest.mark.parametrize("kind", ["tool", "agent"])
def test_tbd_in_any_case_inherits_the_default(owner, kind):
    assert _rollup([("agents/x/README.md", kind, owner)], "ops") == ([], [])
    assert cs._effective_owner(owner, "ops") == "ops"


@pytest.mark.parametrize("owner", _TBD_CASES)
def test_tbd_in_any_case_with_no_default_is_an_error(owner):
    errs, warns = _rollup([("agents/x/README.md", "agent", owner)], None)
    assert warns == [] and len(errs) == 1, (errs, warns)
    assert "agents/x/README.md" in errs[0] and _DOTTED in errs[0], errs


@pytest.mark.parametrize("default", [None, "ops"])
@pytest.mark.parametrize("owner", _OFF_GRAMMAR)
def test_an_owner_outside_the_grammar_is_an_error_naming_doc_and_grammar(
    owner, default
):
    errs, warns = _rollup([("agents/tools/q.tool.md", "tool", owner)], default)
    assert warns == [] and len(errs) == 1, (errs, warns)
    assert "agents/tools/q.tool.md" in errs[0], errs
    assert "[A-Za-z0-9._@-]+" in errs[0] and "§12" in errs[0], errs


# The ways YAML writes null that the line parser keeps as text. An empty value
# reaches the roll-up as "", the missing-owner case, and stays a warning.
_NULL_SPELLINGS = ["null", "Null", "NULL", "nUlL", "~"]


@pytest.mark.parametrize("default", [None, "ops"])
@pytest.mark.parametrize("owner", _NULL_SPELLINGS)
@pytest.mark.parametrize("kind", ["tool", "agent"])
def test_a_null_owner_is_an_error_the_default_does_not_cover(owner, kind, default):
    """`owner: null` is an owner nobody is called, not the placeholder: it
    is refused as `~` always was, and never inherits the default."""
    errs, warns = _rollup([("agents/x/README.md", kind, owner)], default)
    assert warns == [] and len(errs) == 1, (errs, warns)
    assert "agents/x/README.md" in errs[0] and "null" in errs[0], errs
    assert "TBD" in errs[0] and _DOTTED in errs[0], errs
    assert cs._effective_owner(owner, default) is None


@pytest.mark.parametrize("default", [None, "ops"])
@pytest.mark.parametrize("owner", [None, ""])
def test_an_absent_or_empty_owner_still_warns(owner, default):
    errs, warns = _rollup([("agents/x/README.md", "agent", owner)], default)
    assert errs == [] and len(warns) == 1, (errs, warns)


def test_a_tbd_owner_under_a_refused_default_says_the_value_was_refused():
    errs, _warns = _rollup([("agents/x/README.md", "agent", "TBD")], None, True)
    assert len(errs) == 1 and "refused" in errs[0], errs
    assert "gives no" not in errs[0], errs


@pytest.mark.parametrize("owner", _TBD_CASES + _NULL_SPELLINGS + [""])
def test_the_corpus_takes_neither_tbd_nor_null_as_a_real_owner(owner):
    """build_corpus and check_F agree on what names nobody: the placeholder,
    which the corpus fills from the default, and every null spelling."""
    import build_corpus as bc

    assert bc._real_owner(owner) is None
    assert bc._real_owner("ops") == "ops"


@pytest.mark.parametrize("kind", ["tool", "agent"])
def test_a_tbd_owner_with_a_default_inherits_it_and_says_nothing(kind):
    governed = [("agents/x/README.md", kind, "TBD")]
    assert _rollup(governed, "platform-team") == ([], [])


@pytest.mark.parametrize("kind", ["tool", "agent"])
def test_a_tbd_owner_with_no_default_is_an_error_naming_the_doc_and_the_key(kind):
    governed = [
        ("agents/x/README.md", kind, "TBD"),
        ("agents/y/README.md", kind, "TBD"),
    ]
    errs, warns = _rollup(governed, None)
    assert warns == []
    assert len(errs) == 2, errs
    for path, message in zip(
        ("agents/x/README.md", "agents/y/README.md"), errs, strict=True
    ):
        assert path in message and _DOTTED in message, message
        assert "config/project.json" in message, message


def test_the_effective_owner_is_the_default_for_tbd_and_the_doc_s_own_otherwise():
    assert cs._effective_owner("TBD", "platform-team") == "platform-team"
    assert cs._effective_owner("TBD", None) is None
    assert cs._effective_owner("docs-team", "platform-team") == "docs-team"
    assert cs._effective_owner("docs-team", None) == "docs-team"
    assert cs._effective_owner(None, "platform-team") is None


@pytest.mark.parametrize("default", [None, "platform-team"])
def test_a_real_owner_is_unaffected_by_the_default(default):
    governed = [("agents/tools/q.tool.md", "tool", "docs-team")]
    assert _rollup(governed, default) == ([], [])


@pytest.mark.parametrize("default", [None, "platform-team"])
def test_a_missing_owner_still_warns_whatever_the_default(default):
    """A missing owner is a frontmatter fault, not the placeholder: the default
    stands in for `TBD` only."""
    errs, warns = _rollup([("agents/x/README.md", "agent", None)], default)
    assert errs == []
    assert len(warns) == 1 and "agents/x/README.md" in warns[0], warns


def test_other_kinds_are_outside_the_roll_up():
    assert _rollup([("docs/guides/a.md", "guide", "TBD")], None) == ([], [])


# Kinds the roll-up does not hold to an owner, each a governed document whose
# owner the corpus still reads. None is a document whose `kind` is missing.
_OTHER_KINDS = ["readme", "guide", "rules", "design", "spec", None]


@pytest.mark.parametrize("default", [None, "ops"])
@pytest.mark.parametrize("kind", _OTHER_KINDS)
@pytest.mark.parametrize("owner", _OFF_GRAMMAR)
def test_an_owner_outside_the_grammar_in_any_kind_is_an_error_naming_the_grammar(
    owner, kind, default
):
    """KEEL-OWNER-3: a quoted `"alice"` on a README read as no owner in the
    corpus and no gate named the grammar, because only tools and agents were
    judged. The grammar holds for every governed document."""
    errs, warns = _rollup([("docs/x/README.md", kind, owner)], default)
    assert warns == [] and len(errs) == 1, (errs, warns)
    assert "docs/x/README.md" in errs[0] and owner in errs[0], errs
    assert "[A-Za-z0-9._@-]+" in errs[0] and "§12" in errs[0], errs


@pytest.mark.parametrize("default", [None, "ops"])
@pytest.mark.parametrize("kind", _OTHER_KINDS)
@pytest.mark.parametrize(
    "owner", [None, "", "alice", "docs-team", "a.b@c"] + _TBD_CASES + _NULL_SPELLINGS
)
def test_other_kinds_with_no_owner_a_real_owner_tbd_or_null_say_nothing(
    owner, kind, default
):
    """Only the grammar reaches past tools and agents: an owner is not required
    there, so an absent, null or placeholder owner is no finding."""
    assert _rollup([("docs/x/README.md", kind, owner)], default) == ([], [])


def test_the_default_owner_is_read_through_the_loader():
    manifest = {"accountability": {"default_owner": "platform-team"}}
    assert cs._default_owner(manifest) == ("platform-team", [])


def test_an_absent_default_owner_is_the_keys_default_and_prints_nothing(capsys):
    assert cs._default_owner({}) == (None, [])
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("bad", ["", "TBD", "two words", 7, [], "null", "Null", "~"])
def test_a_refused_default_owner_is_an_error_naming_the_key(bad):
    value, errs = cs._default_owner({"accountability": {"default_owner": bad}})
    assert value is None
    assert len(errs) == 1 and _DOTTED in errs[0], errs


def test_an_unreadable_manifest_leaves_no_default():
    value, errs = cs._default_owner(cs._NO_DATA)
    assert value is None and errs == []


# --- end to end: run_checks over a tree with a TBD agent README -------------

_AGENT_FM = (
    "---\ntitle: %s\nkind: %s\nlayer: n/a\nstatus: stable\nsummary: s\nid: %s\n"
    "created: 2026-01-01\nupdated: 2026-01-01\nvisibility: internal\n"
    "canonical: true\nowner: %s\n---\n\n# t\n"
)


def _labelled(root, name, kind, owner="me"):
    import os

    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    slug = name.replace("/", "-")
    (d / "README.md").write_text(_AGENT_FM % (name, kind, slug + "-readme", owner))
    (d / "AGENT.md").write_text(_AGENT_FM % (name, "rules", slug + "-rules", "me"))
    os.symlink("AGENT.md", str(d / "CLAUDE.md"))


def _agent_tree(root, manifest, agents_owner="TBD"):
    import json

    for name in ("src", "tests", "docs", "config"):
        _labelled(root, name, "readme")
    _labelled(root, "agents", "agent", owner=agents_owner)
    (root / "config" / "project.json").write_text(json.dumps(manifest))
    return str(root)


@pytest.fixture
def _isolated(monkeypatch):
    for name in ("ROOT", "errors", "warnings", "GOVERNED"):
        monkeypatch.setattr(cs, name, getattr(cs, name))
    monkeypatch.setattr(cs, "_CONFIG_READ", dict(cs._CONFIG_READ))
    monkeypatch.setattr(cs, "_READ_REPORTED", set(cs._READ_REPORTED))


def test_a_tree_whose_tbd_agent_inherits_the_default_is_clean(tmp_path, _isolated):
    root = _agent_tree(tmp_path, {"accountability": {"default_owner": "ops"}})
    assert [f for f in cs.run_checks(root) if f[0] == "F"] == []


def test_a_tree_with_a_tbd_agent_and_no_default_errs_in_f(tmp_path, _isolated):
    root = _agent_tree(tmp_path, {})
    found = [f for f in cs.run_checks(root) if f[0] == "F"]
    assert len(found) == 1, found
    letter, tier, message = found[0]
    assert tier == "error" and "agents/README.md" in message, found
    assert _DOTTED in message, found


@pytest.mark.parametrize("bad", ["TBD", "not a token!", 42, ""])
def test_a_refused_default_is_an_error_with_no_tbd_document(tmp_path, _isolated, bad):
    """The key is judged on every run, not only when a TBD document needs it:
    the loader's own refusal line reaches the findings."""
    root = _agent_tree(tmp_path, {"accountability": {"default_owner": bad}}, "me")
    found = [f for f in cs.run_checks(root) if f[0] == "F"]
    assert len(found) == 1, found
    _letter, tier, message = found[0]
    assert tier == "error" and _DOTTED in message, found
    assert "accepted:" in message, found


def test_a_tbd_agent_under_a_refused_default_names_both(tmp_path, _isolated):
    root = _agent_tree(tmp_path, {"accountability": {"default_owner": "TBD"}})
    found = sorted(f[2] for f in cs.run_checks(root) if f[0] == "F")
    assert len(found) == 2, found
    assert any("accepted:" in m for m in found), found
    assert any("agents/README.md" in m and "refused" in m for m in found), found


@pytest.mark.parametrize("owner", ['"alice"', "'alice'", "alice # later"])
def test_a_quoted_owner_on_a_plain_readme_errs_in_f(tmp_path, _isolated, owner):
    root = _agent_tree(tmp_path, {"accountability": {"default_owner": "ops"}}, "me")
    _labelled(tmp_path, "docs/guides", "readme", owner=owner)
    found = [f for f in cs.run_checks(root) if f[0] == "F"]
    assert len(found) == 1, found
    _letter, tier, message = found[0]
    assert tier == "error" and "docs/guides/README.md" in message, found
    assert "[A-Za-z0-9._@-]+" in message, found


@pytest.mark.parametrize("owner", ['"TBD"', "TBD # later", "null", "NULL", "~"])
def test_a_quoted_or_commented_owner_in_frontmatter_errs(tmp_path, _isolated, owner):
    root = _agent_tree(tmp_path, {"accountability": {"default_owner": "ops"}}, owner)
    found = [f for f in cs.run_checks(root) if f[0] == "F"]
    assert len(found) == 1, found
    assert found[0][1] == "error" and "agents/README.md" in found[0][2], found
