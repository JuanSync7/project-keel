"""
title: Integration — the target that regenerates what a check judges turns that check green
kind: tests
layer: n/a
summary: A check target runs writers with `--check` (`$(PY) <script>.py ... --check`), and a `[tree]` target that runs one of those writers without `--check` is that check's remedy. When a check judges more than one artifact, some one `[tree]` target must run every writer the check runs, so the target a user is told to run after a change (such as `make exit-codes` after adding an ExitCode member) leaves the check green rather than red on the artifact it skipped. A check none of whose writers any `[tree]` target runs is not judged here, and a pass that judges no check is a failure. Read from the Makefile with scripts/check_structure.py `make_target_rules` and `target_effects`; it runs nothing.
@covers Makefile
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.integration

_CHECK = " --check"


def _writers(rule):
    """The commands *rule* runs as `$(PY) <script>.py ... --check`, each
    with its `--check` removed."""
    found = []
    for command in rule.recipe:
        words = command.split()
        if (
            len(words) >= 3
            and words[0] == "$(PY)"
            and words[1].endswith(".py")
            and words[-1] == _CHECK.strip()
        ):
            found.append(" ".join(words[:-1]))
    return found


def _unrestored(text, tree_targets):
    """(judged, findings): each check target with writers some target of
    *tree_targets* runs is judged, and a finding names one whose writers no
    single such target runs all of."""
    rules = cs.make_target_rules(text)
    recipes = {
        r.target: {" ".join(c.split()) for c in r.recipe}
        for r in rules
        if r.target in tree_targets
    }
    judged, findings = 0, []
    for rule in rules:
        writers = _writers(rule)
        if not writers:
            continue
        runs_some = [t for t, cmds in sorted(recipes.items()) if cmds & set(writers)]
        if not runs_some:
            continue
        judged += 1
        if not any(set(writers) <= recipes[t] for t in runs_some):
            findings.append(
                "%s: no one [tree] target runs every writer it checks (%s); "
                "%s each run only some"
                % (rule.target, "; ".join(writers), ", ".join(runs_some))
            )
    return judged, findings


def _tree_targets(root):
    return {
        target
        for target, (labels, _reason) in cs.target_effects(str(root)).items()
        if labels and "tree" in labels
    }


_SPLIT = """\
check-x: ## [local] x
\t$(PY) scripts/gen.py --check
\t$(PY) scripts/gen.py --shell --check
x: ## [tree] x
\t$(PY) scripts/gen.py
x-sh: ## [tree] x
\t$(PY) scripts/gen.py --shell
"""
_ONE_TARGET = _SPLIT.replace(
    "x: ## [tree] x\n\t$(PY) scripts/gen.py\n",
    "x: ## [tree] x\n\t$(PY) scripts/gen.py\n\t$(PY) scripts/gen.py --shell\n",
)
_NO_REMEDY = """\
check-y: ## [local] y
\t$(PY) scripts/gen.py --check
"""


@pytest.mark.parametrize(
    "text, judged, red",
    [(_SPLIT, 1, True), (_ONE_TARGET, 1, False), (_NO_REMEDY, 0, False)],
    ids=["split-across-targets", "one-target-runs-all", "no-remedy-target"],
)
def test_a_check_is_restored_by_one_target_that_runs_every_writer(text, judged, red):
    count, findings = _unrestored(text, {"x", "x-sh"})
    assert count == judged
    assert bool(findings) is red, findings


def test_each_check_s_regenerate_target_runs_every_writer_it_checks():
    judged, findings = _unrestored(
        (_ROOT / "Makefile").read_text(encoding="utf-8"), _tree_targets(_ROOT)
    )
    assert judged > 0, "no check target has a [tree] remedy -- zero items"
    assert not findings, "\n".join(findings)
