"""
title: Integration — the expiring tier is wired to real gate tests, a real make target and a date no later than the ceiling
kind: tests
layer: n/a
summary: The tree-level half of scripts/expiring_tier.py. config/project.json `expiring_tier` loads, so its `expires` is a calendar date no later than scripts/expiring_tier_data.py `CEILING`. Each `CHECKS` node id names a test function its file defines and whose body calls `expiring_tier.apply` with that check id, so a renamed test or a gate that stops judging through the tier is red here rather than recording nothing. The Makefile defines `gate-baseline` (`RECORD_TARGET`), whose recipe opens with $(WRITE_GUARD) and runs scripts/record_gate_baseline.py. In the template repository, which holds copier.yml, no baseline file exists and a finding handed to the tier is red; in a generated project the baseline names no check `CHECKS` does not register.
@covers scripts/expiring_tier.py
"""

import ast
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import expiring_tier  # noqa: E402
import expiring_tier_data  # noqa: E402

pytestmark = pytest.mark.integration

_IN_TEMPLATE = (_ROOT / expiring_tier.TEMPLATE_MARK).is_file()


def test_the_configured_date_is_no_later_than_the_ceiling():
    policy = expiring_tier.load_policy(str(_ROOT))
    ceiling = expiring_tier_data.CEILING
    assert policy.expires.isoformat() <= ceiling, (policy.expires, ceiling)


def _applies(func, check):
    """True when *func*'s body calls `expiring_tier.apply` with *check* as
    its first argument, a string constant."""
    for node in ast.walk(func):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "apply"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "expiring_tier"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == check
        ):
            return True
    return False


def _judges(tree, name, check):
    """True when test *name* in *tree*, or a module-level function it calls
    with *check* as a constant argument, hands *check* to the tier."""
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    test = funcs.get(name)
    if test is None:
        return False
    if _applies(test, check):
        return True
    module_constants = {
        t.id: n.value.value
        for n in tree.body
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)
        for t in n.targets
        if isinstance(t, ast.Name)
    }
    for call in ast.walk(test):
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)):
            continue
        helper = funcs.get(call.func.id)
        handed = [
            module_constants.get(a.id)
            if isinstance(a, ast.Name)
            else getattr(a, "value", None)
            for a in call.args
        ]
        if helper is not None and check in handed:
            for inner in ast.walk(helper):
                if (
                    isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Attribute)
                    and inner.func.attr == "apply"
                    and isinstance(inner.func.value, ast.Name)
                    and inner.func.value.id == "expiring_tier"
                ):
                    return True
    return False


@pytest.mark.parametrize("check", sorted(expiring_tier_data.CHECKS))
def test_each_check_names_a_gate_test_that_judges_through_the_tier(check):
    relpath, _, name = expiring_tier_data.CHECKS[check].partition("::")
    path = _ROOT / relpath
    assert path.is_file(), "%s: %s does not exist" % (check, relpath)
    tree = ast.parse(path.read_text(encoding="utf-8"), relpath)
    assert _judges(tree, name, check), (
        "%s: %s::%s does not hand its findings to expiring_tier.apply as %r"
        % (check, relpath, name, check)
    )


def test_the_record_target_guards_its_write_and_runs_the_writer():
    lines = (_ROOT / "Makefile").read_text(encoding="utf-8").splitlines()
    head = [
        i
        for i, text in enumerate(lines)
        if text.startswith(expiring_tier.RECORD_TARGET + ":")
    ]
    assert len(head) == 1, "the Makefile defines `%s` %d times" % (
        expiring_tier.RECORD_TARGET,
        len(head),
    )
    assert "## [tree,write] " in lines[head[0]], lines[head[0]]
    recipe = lines[head[0] + 1 : head[0] + 3]
    assert recipe[0] == "\t$(WRITE_GUARD)", recipe
    assert recipe[1] == "\t$(PY) scripts/record_gate_baseline.py", recipe


def test_the_template_has_no_baseline_and_a_project_s_names_only_registered_checks():
    policy = expiring_tier.load_policy(str(_ROOT))
    if _IN_TEMPLATE:
        assert not (_ROOT / policy.baseline).exists(), (
            "%s: the template repository has no tier, so it ships no baseline"
            % policy.baseline
        )
        line = "src/a.py:1: a planted finding — fix it"
        assert expiring_tier.judge(
            sorted(expiring_tier_data.CHECKS)[0], [line], str(_ROOT)
        ).red == [line]
        return
    found = expiring_tier.baseline_findings(str(_ROOT))
    assert not found, "\n".join(found)
