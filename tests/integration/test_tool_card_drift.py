"""
title: Integration — a tool card's flags are its script's flags
kind: tests
layer: n/a
summary: The tool-card drift gate. Every `*.tool.md` under agents/ whose frontmatter `public_api` names a Python script holds an `## Args` table with the columns Flag, Required, Default and Meaning, and its rows are exactly the `add_argument` calls of that script (an option by its spelling, a positional by its name case-folded, since a card spells it as its metavar); a flag whose `default=` is a literal string or number states that value as its Default cell's first code span, or as the cell's first word when it has none. The flags are read from the script's syntax tree through tests/integration/test_reference_drift.py `cli_flags`, never typed here, so a card that still documents a removed default, or omits a new flag an agent must pass, is red. A scan over zero cards fails, and each rule has a fault-injection twin that plants one fault and asserts exactly one finding. Not a writer: it reads the tree.
"""

import ast
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402
from test_reference_drift import _first_span, cli_flags  # noqa: E402

pytestmark = pytest.mark.integration

_AGENTS_DIR = "agents"
_CARD_SUFFIX = ".tool.md"
_TOOL_KIND = "tool"
_SCRIPT_SUFFIX = ".py"
_ARGS_HEADING = "Args"
_ARGS_COLUMNS = ("Flag", "Required", "Default", "Meaning")
_OPTION_PREFIX = "-"


def cards(root):
    """{relpath: (public_api, text)} for every `kind: tool` card under agents/
    whose public_api is a Python script, sorted."""
    found = {}
    for path in sorted((Path(root) / _AGENTS_DIR).rglob("*" + _CARD_SUFFIX)):
        fm = cs.parse_frontmatter(str(path))
        if not fm or fm.get("kind") != _TOOL_KIND:
            continue
        api = fm.get("public_api", "")
        if api.endswith(_SCRIPT_SUFFIX):
            rel = path.relative_to(root).as_posix()
            found[rel] = (api, path.read_text(encoding="utf-8"))
    return found


def script_flags(root):
    """{public_api: {flag: default node or None}} from every add_argument call
    in the code roots."""
    flags, findings = cli_flags(root)
    assert not findings, findings
    by_script = {}
    for key, default in flags.items():
        script, flag = key.split(" ", 1)
        by_script.setdefault(script, {})[flag] = default
    return by_script


def _spelling(flag):
    # A positional is documented by its metavar (QUESTION for `question`), so
    # it is matched case-folded; an option is matched as spelt.
    return flag if flag.startswith(_OPTION_PREFIX) else flag.casefold()


def _stated_default(node):
    """The text a Default cell must state for a `default=` node, or None when
    the rule does not judge it (no default, None, a bool, an empty
    collection, or a computed value)."""
    if node is None:
        return None
    try:
        value = ast.literal_eval(node)
    except ValueError:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    return str(value)


def args_rows(card, text):
    """(rows, findings): {spelling: Default cell} for the card's Args table."""
    sections = dict(cs._sections(text))
    if _ARGS_HEADING not in sections:
        return {}, ["%s: has no `## %s` section" % (card, _ARGS_HEADING)]
    table = cs._pipe_table("\n".join(sections[_ARGS_HEADING]), _ARGS_COLUMNS)
    if table is None:
        return {}, [
            "%s: `## %s` holds no table with the columns %s"
            % (card, _ARGS_HEADING, ", ".join(_ARGS_COLUMNS))
        ]
    header, cells = table
    flag_at, default_at = header.index("flag"), header.index("default")
    rows, findings = {}, []
    for raw in cells:
        span = _first_span(raw[flag_at]) if flag_at < len(raw) else None
        if not span:
            findings.append(
                "%s: an `## %s` row names no flag in a code span"
                % (card, _ARGS_HEADING)
            )
            continue
        rows[_spelling(span.split()[0])] = (
            raw[default_at].strip() if default_at < len(raw) else ""
        )
    return rows, findings


def card_findings(card, text, flags):
    """The card's Args rows are the script's flags, and each judged literal
    default is stated."""
    rows, findings = args_rows(card, text)
    want = {_spelling(flag): node for flag, node in flags.items()}
    findings += [
        "%s: `## %s` has no row for `%s`, which the script declares"
        % (card, _ARGS_HEADING, flag)
        for flag in sorted(set(want) - set(rows))
    ]
    findings += [
        "%s: `## %s` row `%s` is a flag the script does not declare"
        % (card, _ARGS_HEADING, flag)
        for flag in sorted(set(rows) - set(want))
    ]
    for flag in sorted(set(rows) & set(want)):
        stated = _stated_default(want[flag])
        if stated is None:
            continue
        cell = rows[flag]
        said = _first_span(cell) or (cell.split() or [""])[0]
        if said != stated:
            findings.append(
                "%s: `## %s` row `%s` states Default %r; the script's is `%s`"
                % (card, _ARGS_HEADING, flag, cell, stated)
            )
    return findings


def test_every_tool_cards_args_table_is_its_scripts_flags():
    found = cards(_ROOT)
    assert found, "no `kind: tool` card under agents/ wraps a script -- zero items"
    flags = script_flags(_ROOT)
    findings = []
    for card, (api, text) in found.items():
        findings += card_findings(card, text, flags.get(api, {}))
    assert not findings, "\n".join(findings)


def _a_card_with_a_default():
    """(card, text, flags, row, stated) for the first card row whose literal
    default the rule judges and the cell states as a code span."""
    flags = script_flags(_ROOT)
    for card, (api, text) in cards(_ROOT).items():
        for line in text.splitlines():
            flag = _first_span(line) if line.startswith("|") else None
            stated = _stated_default(flags.get(api, {}).get(flag or ""))
            if stated is not None and "`%s`" % stated in line.split(flag, 1)[1]:
                return card, text, flags[api], line, stated
    raise AssertionError("no card row states a judged default -- zero items")


@pytest.mark.parametrize("fault", ["missing row", "extra row", "wrong default"])
def test_a_planted_flag_or_default_drift_reds_the_card(fault):
    card, text, flags, row, stated = _a_card_with_a_default()
    assert card_findings(card, text, flags) == [], "the unplanted card must be clean"
    planted = {
        "missing row": lambda: text.replace(row + "\n", ""),
        "extra row": lambda: text.replace(
            row, row + "\n| `--planted-flag` | no | — | planted |"
        ),
        "wrong default": lambda: text.replace(
            row, row.replace("`%s`" % stated, "`planted-%s`" % stated)
        ),
    }[fault]()
    assert planted != text
    findings = card_findings(card, planted, flags)
    assert len(findings) == 1, findings
