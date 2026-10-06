"""
title: Unit — make_help (`make help`, labelled by effect)
kind: tests
layer: n/a
summary: make_help groups the help recipe's `file:target: ## [label] text` lines by area header or, without one, by makefile, and shows each target's effect label; `EFFECT=<word>` keeps the targets whose label contains that word, `AREA=` with no area headers and any unknown filter value exit 2 naming the valid values, and an unlabelled row shows `[?]` rather than vanishing. The real `make help` in keel lists every annotated target once, and `make help EFFECT=tree` lists exactly the targets the labels say rewrite the tree.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402
import make_help as mh  # noqa: E402

pytestmark = pytest.mark.unit

_LINES = [
    "Makefile:check: ## [local] Validate\n",
    "Makefile:fmt: ## [tree] Format\n",
    "Makefile:fe-install: ## [tree,read] Install deps\n",
    "Makefile:mystery: ## Undeclared\n",
]
_HEADERS = [("Makefile", "check: ## [local] Validate\n")]


def _rows(groups):
    return [(t["target"], t["effect"]) for g in groups for t in g["targets"]]


def test_without_area_headers_targets_group_by_makefile():
    groups = mh.group(_LINES, _HEADERS, "", "")
    assert [g["area"] for g in groups] == ["Makefile"]
    assert _rows(groups) == [
        ("check", "local"),
        ("fmt", "tree"),
        ("fe-install", "tree,read"),
        ("mystery", "?"),
    ]


def test_an_effect_filter_keeps_every_label_containing_the_word():
    assert _rows(mh.group(_LINES, _HEADERS, "", "tree")) == [
        ("fmt", "tree"),
        ("fe-install", "tree,read"),
    ]
    assert _rows(mh.group(_LINES, _HEADERS, "", "read")) == [
        ("fe-install", "tree,read")
    ]


@pytest.mark.parametrize("word", ["bogus", "?", "tree,read"])
def test_an_unknown_effect_is_refused_naming_the_vocabulary(word):
    with pytest.raises(ValueError) as exc:
        mh.group(_LINES, _HEADERS, "", word)
    for label in cs.EFFECT_LABELS:
        assert label in str(exc.value)


def test_an_area_filter_without_area_headers_says_there_are_no_areas():
    with pytest.raises(ValueError) as exc:
        mh.group(_LINES, _HEADERS, "repo", "")
    assert "no areas" in str(exc.value)


def test_area_headers_name_the_groups_and_filter():
    headers = [
        ("Makefile", "##@ repo  gates\n"),
        ("mk/gateway.mk", "##@ gateway  the gateway\n"),
    ]
    lines = _LINES[:1] + ["mk/gateway.mk:gateway-plan: ## [read] Plan\n"]
    groups = mh.group(lines, headers, "", "")
    assert [(g["area"], g["about"]) for g in groups] == [
        ("repo", "gates"),
        ("gateway", "the gateway"),
    ]
    assert _rows(mh.group(lines, headers, "gateway", "")) == [("gateway-plan", "read")]
    with pytest.raises(ValueError) as exc:
        mh.group(lines, headers, "nope", "")
    assert "gateway" in str(exc.value) and "repo" in str(exc.value)


def test_render_aligns_target_effect_and_text_and_shows_the_legend():
    out = mh.render(mh.group(_LINES, _HEADERS, "", ""))
    assert "  %-22s %-12s %s" % ("fe-install", "[tree,read]", "Install deps") in out
    assert "  %-22s %-12s %s" % ("mystery", "[?]", "Undeclared") in out
    for word, meaning in cs.EFFECT_MEANINGS:
        assert "[%s] %s" % (word, meaning) in out, word
    assert "EFFECT=" in out


def test_main_exits_2_on_an_unknown_filter(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", _Stdin(_LINES))
    assert mh.main(["--effect", "bogus", str(_ROOT / "Makefile")]) == 2
    assert "bogus" in capsys.readouterr().err


class _Stdin:
    def __init__(self, lines):
        self._lines = lines

    def readlines(self):
        return list(self._lines)


# --- the real `make help` over keel's own Makefile --------------------------------


def _make_help(*args):
    env = {k: v for k, v in os.environ.items() if k not in ("EFFECT", "AREA")}
    return subprocess.run(
        ["make", "-s", "--no-print-directory", "help", "PY=" + sys.executable]
        + list(args),
        cwd=str(_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )


def _listed(stdout):
    return [
        line.split()[0]
        for line in stdout.splitlines()
        if line.startswith("  ")
        and len(line.split()) > 1
        and line.split()[1].startswith("[")
    ]


def _annotated():
    rules = []
    for _relpath, text in cs.walk_makefiles(str(_ROOT), lambda _m: None):
        rules.extend(r for r in cs.make_target_rules(text) if r.help is not None)
    return rules


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
def test_make_help_lists_every_annotated_target_once():
    r = _make_help()
    assert r.returncode == 0, r.stderr
    expected = sorted(r_.target for r_ in _annotated())
    assert expected, "keel's Makefile has no annotated targets -- this proves nothing"
    assert sorted(_listed(r.stdout)) == expected
    assert "[?]" not in r.stdout


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
def test_make_help_effect_tree_lists_what_the_labels_say_rewrites_the_tree():
    r = _make_help("EFFECT=tree")
    assert r.returncode == 0, r.stderr
    expected = sorted(
        rule.target
        for rule in _annotated()
        if "tree" in (cs.parse_effect_labels(rule.help)[0] or ())
    )
    assert expected, "no target is labelled [tree] -- this proves nothing"
    assert sorted(_listed(r.stdout)) == expected


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
def test_make_help_refuses_an_unknown_effect():
    r = _make_help("EFFECT=bogus")
    assert r.returncode != 0 and "bogus" in r.stderr, (r.stdout, r.stderr)
