"""
title: Unit — check_structure check_W (every make target declares its effect)
kind: tests
layer: n/a
summary: check_W's rule, pinned: an annotated make target opens its help with an effect label from the closed EFFECT_LABELS vocabulary, written as comma-separated words in canonical order, the same label on every rule that annotates one target; a composite target's label covers what its prerequisites and `$(MAKE)` recursions reach; a [write] target, and any target named with a configured write shape, opens its recipe with `$(WRITE_GUARD)` behind no `-` prefix unless config names it in `write_shape_exempt` with a reason (an exemption that matches nothing, an unshaped, unlabelled or [write] target is stale), a labelled recipe that calls the guard anywhere in any line (a `$$`-escaped reference is text) must be [write], and the guard, read as make stores it (a `#` comment cut off), tests exactly the configured unattended variables, carries no `-` prefix and exits 1. The policy is read from config/project.json `make_targets` and validated before it is used. Area makefiles are held to their header, prefix and include only when the policy names an area directory. Keel's own Makefile passes, and so does the bedrock-platform shape that the rule was ported from.
"""

import copy
import json
import re
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit

_POLICY = {
    "unattended_vars": ["CI", "RALPH"],
    "gate_runner_var": "RALPH",
    "gate_effects": ["local", "read"],
    "write_shapes": [],
    "area_dir": None,
    "effect_proof_skip": {},
    "write_shape_exempt": {},
    "empty_test_selections": {},
    "gate_vars": ["PY"],
}
_GUARD = (
    'WRITE_GUARD = @if [ -n "$(CI)$(RALPH)" ]; then echo "refusing $@" >&2; '
    "exit 1; fi\n"
)


def _policy(**over):
    p = copy.deepcopy(_POLICY)
    p.update(over)
    return p


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """An empty root with the gate's module state isolated (as test_check_b)."""
    (tmp_path / "config").mkdir()
    monkeypatch.setattr(cs, "ROOT", str(tmp_path))
    monkeypatch.setattr(cs, "errors", [])
    monkeypatch.setattr(cs, "warnings", [])
    monkeypatch.setattr(cs, "_CONFIG_READ", {})
    monkeypatch.setattr(cs, "_READ_REPORTED", set())
    return tmp_path


def _write(root, makefile, policy=None, manifest=None, **more):
    """Makefile text, a make_targets policy (default: keel's shape), extra files."""
    (root / "Makefile").write_text(makefile, encoding="utf-8")
    if manifest is None:
        manifest = {"make_targets": policy if policy is not None else _policy()}
    (root / "config" / "project.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    for relpath, text in more.items():
        path = root / re.sub(r"_mk$", ".mk", relpath.replace("__", "/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _run(root, makefile, policy=None, **more):
    _write(root, makefile, policy, **more)
    cs.check_W()
    return cs.errors, cs.warnings


# --- the vacuity control ------------------------------------------------------


def test_a_labelled_makefile_passes(repo):
    errs, warns = _run(
        repo,
        _GUARD
        + "check: ## [local] Validate\n\tpython3 check.py\n"
        + "fmt: ## [tree] Format\n\truff format\n"
        + "deploy: ## [write] Ship it\n\t$(WRITE_GUARD)\n\tship\n",
    )
    assert errs == [] and warns == []


def test_no_makefile_is_silent_even_without_a_policy(repo):
    cs.check_W()
    assert cs.errors == [] and cs.warnings == []


# --- the label grammar ---------------------------------------------------------


def test_an_annotated_target_without_a_label_errors_naming_the_vocabulary(repo):
    errs, _ = _run(repo, "check: ## Validate structure\n\tx\n")
    assert len(errs) == 1, errs
    assert errs[0].startswith("Makefile:1: `check`"), errs
    assert "no effect label" in errs[0]
    for label in cs.EFFECT_LABELS:
        assert label in errs[0], errs


def test_an_unannotated_target_is_not_this_checks_business(repo):
    assert _run(repo, "check:\n\tx\n") == ([], [])


@pytest.mark.parametrize(
    "help_, labels, text",
    [
        ("[local] Validate", ("local",), "Validate"),
        ("[tree] Format", ("tree",), "Format"),
        ("[tree,read] Install deps", ("tree", "read"), "Install deps"),
        ("[read,cost,write] Everything", ("read", "cost", "write"), "Everything"),
        ("[local] [see docs] text", ("local",), "[see docs] text"),
        ("[local]", ("local",), ""),
    ],
)
def test_a_well_formed_label_parses_to_its_words_and_text(help_, labels, text):
    assert cs.parse_effect_labels(help_) == (labels, text, None)


@pytest.mark.parametrize(
    "help_, problem",
    [
        ("Validate", "no effect label"),
        ("[local Validate", "no effect label"),
        ("[] Validate", "empty"),
        ("[remote] Validate", "'remote' is not an effect label"),
        ("[Local] Validate", "'Local' is not an effect label"),
        ("[read,tree] Validate", "canonical order"),
        ("[tree,tree] Validate", "twice"),
        ("[local,tree] Validate", "`local` stands alone"),
        ("[tree, read] Validate", "' read' is not an effect label"),
        ("[local] [tree] Validate", "second effect label"),
        ("[tree] [cost,write] Validate", "second effect label"),
    ],
    ids=[
        "unlabelled",
        "unclosed",
        "empty",
        "unknown",
        "case",
        "order",
        "duplicate",
        "local-not-alone",
        "space",
        "second-bracket",
        "second-bracket-multi",
    ],
)
def test_a_malformed_label_is_one_error_naming_its_problem(repo, help_, problem):
    labels, _, why = cs.parse_effect_labels(help_)
    assert labels is None and problem in why, why
    errs, _ = _run(repo, "check: ## %s\n\tx\n" % help_)
    assert len(errs) == 1 and problem in errs[0], errs


def test_every_vocabulary_word_has_a_meaning_and_no_meaning_lacks_a_word():
    """make_help's legend and check_W's messages read one owner."""
    assert tuple(word for word, _ in cs.EFFECT_MEANINGS) == cs.EFFECT_LABELS
    assert all(meaning for _, meaning in cs.EFFECT_MEANINGS)


# --- composite targets ----------------------------------------------------------


def test_a_composite_whose_label_misses_a_prerequisites_effect_errors(repo):
    errs, _ = _run(
        repo,
        "verify: check fmt ## [local] All gates\n"
        "check: ## [local] c\n\tc\n"
        "fmt: ## [tree] f\n\tf\n",
    )
    assert len(errs) == 1, errs
    assert "`verify`" in errs[0] and "`fmt`" in errs[0] and "[tree]" in errs[0], errs


def test_a_composite_that_covers_its_prerequisites_passes(repo):
    assert _run(
        repo,
        "all: check fmt ## [tree] Everything\n"
        "check: ## [local] c\n\tc\n"
        "fmt: ## [tree] f\n\tf\n",
    ) == ([], [])


def test_a_recursion_counts_as_a_child(repo):
    errs, _ = _run(
        repo,
        "ci: ## [local] CI\n\t$(MAKE) -s --no-print-directory fmt V=1\n"
        "fmt: ## [tree] f\n\tf\n",
    )
    assert len(errs) == 1 and "`ci`" in errs[0] and "`fmt`" in errs[0], errs


def test_an_effect_reached_through_an_unlabelled_middle_still_counts(repo):
    errs, _ = _run(
        repo,
        "verify: middle ## [local] v\nmiddle: fmt\nfmt: ## [tree] f\n\tf\n",
    )
    assert len(errs) == 1 and "`verify`" in errs[0] and "`fmt`" in errs[0], errs


def test_an_unlabelled_child_with_a_recipe_warns(repo):
    errs, warns = _run(repo, "verify: helper ## [local] v\nhelper:\n\tdo-it\n")
    assert errs == []
    assert len(warns) == 1 and "`helper`" in warns[0] and "`verify`" in warns[0]


def test_a_recursion_this_check_cannot_resolve_warns(repo):
    errs, warns = _run(
        repo, "sub: ## [local] s\n\t$(MAKE) -C api all\n\t$(MAKE) $(NEXT)\n"
    )
    assert errs == []
    assert len(warns) == 2 and all("`sub`" in w for w in warns), warns


def test_a_prerequisite_cycle_terminates(repo):
    assert _run(repo, "a: b ## [local] a\nb: a ## [local] b\n") == ([], [])


# --- the write guard -----------------------------------------------------------


def test_a_write_target_without_the_guard_errors(repo):
    errs, _ = _run(repo, _GUARD + "deploy: ## [write] Ship\n\tship\n")
    assert len(errs) == 1 and "$(WRITE_GUARD)" in errs[0], errs


def test_the_guard_must_open_the_recipe(repo):
    errs, _ = _run(
        repo, _GUARD + "deploy: ## [write] Ship\n\techo go\n\t$(WRITE_GUARD)\n"
    )
    assert len(errs) == 1 and "opens" in errs[0], errs


def test_a_write_target_with_no_guard_defined_errors(repo):
    errs, _ = _run(repo, "deploy: ## [write] Ship\n\t$(WRITE_GUARD)\n\tship\n")
    assert len(errs) == 1 and "never defined" in errs[0], errs


def test_a_shaped_target_must_be_labelled_write(repo):
    errs, _ = _run(
        repo,
        _GUARD + "db-apply: ## [tree] Apply\n\t$(WRITE_GUARD)\n\tx\n",
        _policy(write_shapes=["-apply"]),
    )
    assert len(errs) == 1 and "`db-apply`" in errs[0] and "-apply" in errs[0], errs


def test_a_shaped_target_must_open_with_the_guard_even_unlabelled(repo):
    errs, _ = _run(repo, _GUARD + "db-apply:\n\tx\n", _policy(write_shapes=["-apply"]))
    assert any("`db-apply`" in e and "[write]" in e for e in errs), errs
    assert any("`db-apply`" in e and "$(WRITE_GUARD)" in e for e in errs), errs


def test_with_shapes_configured_a_write_target_must_be_shaped(repo):
    errs, _ = _run(
        repo,
        _GUARD + "deploy: ## [write] Ship\n\t$(WRITE_GUARD)\n\tship\n",
        _policy(write_shapes=["-apply", "-destroy"]),
    )
    assert len(errs) == 1 and "-apply" in errs[0] and "-destroy" in errs[0], errs


# --- the converse: a recipe that calls the guard is a write ------------------------


@pytest.mark.parametrize(
    "recipe",
    [
        "\t$(WRITE_GUARD)\n\tlook\n",
        "\techo first\n\t@$(WRITE_GUARD)\n",
        "\t${WRITE_GUARD}\n\tlook\n",
        "\t$(WRITE_GUARD) && look\n",
        "\t$(WRITE_GUARD); look\n",
        "\t$(WRITE_GUARD) \n\tlook\n",
        "\tlook && ${WRITE_GUARD}\n",
        "\t$$$(WRITE_GUARD)\n",
    ],
    ids=[
        "first-line",
        "later-line",
        "brace-spelling",
        "and-chained",
        "semicolon-chained",
        "trailing-blank",
        "after-a-command",
        "escaped-dollar-then-call",
    ],
)
def test_a_guarded_recipe_must_be_labelled_write(repo, recipe):
    """The guard refuses CI and gate runs, so a [read] target that calls it is a
    target the gate runner admits and the guard then kills: the label lies."""
    errs, _ = _run(repo, _GUARD + "platform-look: ## [read] Look\n" + recipe)
    assert len(errs) == 1, errs
    assert errs[0].startswith("Makefile:2: `platform-look` runs $(WRITE_GUARD)")
    assert "labelled [read]" in errs[0] and "[write]" in errs[0], errs


@pytest.mark.parametrize(
    "recipe",
    ["\t@echo '$$(WRITE_GUARD)'\n", "\t@echo $$$$(WRITE_GUARD)\n"],
    ids=["escaped", "twice-escaped"],
)
def test_an_escaped_guard_reference_is_text_not_a_call(repo, recipe):
    """make turns `$$` into a literal `$`, so `$$(WRITE_GUARD)` reaches the shell
    as text and the guard never runs: no write to label."""
    assert _run(repo, _GUARD + "platform-look: ## [read] Look\n" + recipe) == ([], [])


def test_an_unlabelled_guarded_recipe_is_this_checks_label_rule_not_the_converse(repo):
    """With no annotation there is no label to contradict."""
    assert _run(repo, _GUARD + "look:\n\t$(WRITE_GUARD)\n\tlook\n") == ([], [])


# --- write_shape_exempt: a write-shaped target that is not a write -----------------

_EXEMPT_REASON = "rewrites the working tree from a paid review, never shared state"


def test_without_an_exemption_a_shaped_non_write_target_errors(repo):
    errs, _ = _run(
        repo,
        _GUARD + "doc-review-apply: ## [tree,cost] Apply the review\n\tx\n",
        _policy(write_shapes=["-apply"]),
    )
    assert any("named like a write" in e for e in errs), errs


def test_an_exemption_lets_a_named_target_keep_its_label(repo):
    errs, warns = _run(
        repo,
        _GUARD + "doc-review-apply: ## [tree,cost] Apply the review\n\tx\n",
        _policy(
            write_shapes=["-apply"],
            write_shape_exempt={"doc-review-apply": _EXEMPT_REASON},
        ),
    )
    assert errs == [] and warns == []


def test_an_exemption_is_per_target_not_per_shape(repo):
    errs, _ = _run(
        repo,
        _GUARD
        + "doc-review-apply: ## [tree,cost] Apply the review\n\tx\n"
        + "db-apply: ## [tree] Apply\n\tx\n",
        _policy(
            write_shapes=["-apply"],
            write_shape_exempt={"doc-review-apply": _EXEMPT_REASON},
        ),
    )
    assert errs and all("`db-apply`" in e for e in errs), errs


def test_a_guarded_exempt_target_is_still_an_error(repo):
    """An exemption says the target is not a write; a guard says it is."""
    errs, _ = _run(
        repo,
        _GUARD + "doc-review-apply: ## [tree,cost] Apply\n\t$(WRITE_GUARD)\n\tx\n",
        _policy(
            write_shapes=["-apply"],
            write_shape_exempt={"doc-review-apply": _EXEMPT_REASON},
        ),
    )
    assert len(errs) == 1 and "runs $(WRITE_GUARD)" in errs[0], errs
    assert "labelled [tree,cost]" in errs[0], errs


@pytest.mark.parametrize(
    "makefile, name, tail",
    [
        ("check: ## [local] c\n\tc\n", "gone-apply", "which no makefile defines"),
        (
            "check: ## [local] c\n\tc\n",
            "check",
            "which no write_shapes suffix matches",
        ),
        ("db-apply:\n\tx\n", "db-apply", "which carries no effect label"),
        (
            "db-apply: ## [write] Apply\n\t$(WRITE_GUARD)\n\tx\n",
            "db-apply",
            "which is already [write]",
        ),
    ],
    ids=["undefined", "unshaped", "unlabelled", "already-write"],
)
def test_a_stale_exemption_is_an_error(repo, makefile, name, tail):
    errs, _ = _run(
        repo,
        _GUARD + makefile,
        _policy(write_shapes=["-apply"], write_shape_exempt={name: _EXEMPT_REASON}),
    )
    head = "config/project.json: make_targets.write_shape_exempt names `%s`" % name
    stale = [e for e in errs if e.startswith(head)]
    assert len(stale) == 1 and tail in stale[0], errs


def test_stale_exemptions_are_reported_sorted_by_name(repo):
    errs, _ = _run(
        repo,
        _GUARD + "check: ## [local] c\n\tc\n",
        _policy(
            write_shapes=["-apply"],
            write_shape_exempt={"zz-apply": "r", "check": "r", "aa-apply": "r"},
        ),
    )
    named = [
        re.search(r"write_shape_exempt names `([^`]+)`", e).group(1)
        for e in errs
        if "write_shape_exempt names" in e
    ]
    assert named == ["aa-apply", "check", "zz-apply"], errs


@pytest.mark.parametrize(
    "guard, missing",
    [
        ('WRITE_GUARD = @if [ -n "$(CI)" ]; then exit 1; fi\n', "RALPH"),
        ('WRITE_GUARD = @if [ -n "$(RALPH)" ]; then exit 1; fi\n', "CI"),
        ('WRITE_GUARD = @if [ -n "$(CI)$(RALPH)" ]; then false; fi\n', "exit 1"),
    ],
)
def test_a_guard_that_misses_a_configured_refusal_errors(repo, guard, missing):
    errs, _ = _run(repo, guard + "check: ## [local] c\n\tc\n")
    assert len(errs) == 1 and "WRITE_GUARD" in errs[0] and missing in errs[0], errs


@pytest.mark.parametrize(
    "guard",
    [
        'WRITE_GUARD = @if [ -n "$$CI$${RALPH}" ]; then exit 1; fi\n',
        'WRITE_GUARD = @if [ -n "${CI}" ] || [ -n "$(RALPH)" ]; then \\\n\texit 1; fi\n',
    ],
    ids=["shell-vars", "continued"],
)
def test_every_spelling_of_a_variable_counts(repo, guard):
    assert _run(repo, guard + "check: ## [local] c\n\tc\n") == ([], [])


@pytest.mark.parametrize(
    "line",
    ["\t-$(WRITE_GUARD)\n", "\t@-$(WRITE_GUARD)\n", "\t- $(WRITE_GUARD)\n"],
    ids=["dash", "at-dash", "dash-space"],
)
def test_a_guard_whose_failure_make_ignores_errors(repo, line):
    """`-` tells make to carry on past the guard's `exit 1`, so the [write]
    recipe runs under CI anyway (measured: `Error 1 (ignored)`, rc 0)."""
    errs, _ = _run(repo, _GUARD + "deploy: ## [write] Ship\n" + line + "\tship\n")
    assert len(errs) == 1 and "`-`" in errs[0] and "`deploy`" in errs[0], errs


@pytest.mark.parametrize("line", ["\t@$(WRITE_GUARD)\n", "\t+${WRITE_GUARD}\n"])
def test_a_guard_line_with_a_harmless_prefix_passes(repo, line):
    assert _run(repo, _GUARD + "deploy: ## [write] Ship\n" + line + "\tship\n") == (
        [],
        [],
    )


def test_a_guard_definition_that_ignores_its_own_failure_errors(repo):
    guard = _GUARD.replace("WRITE_GUARD = @if", "WRITE_GUARD = -@if")
    errs, _ = _run(repo, guard + "check: ## [local] c\n\tc\n")
    assert len(errs) == 1 and "WRITE_GUARD" in errs[0] and "`-`" in errs[0], errs


def test_a_guard_whose_refusal_is_a_make_comment_errors(repo):
    """Everything after an unescaped `#` in a make assignment is a comment, so
    this guard is `@true` and never refuses."""
    errs, _ = _run(
        repo,
        "WRITE_GUARD = @true # $(CI) $(RALPH) exit 1\n"
        "d-apply: ## [write] x\n\t$(WRITE_GUARD)\n\techo hi\n",
    )
    assert len(errs) == 1 and "CI" in errs[0] and "exit 1" in errs[0], errs


def test_a_guard_testing_a_variable_config_omits_errors(repo):
    """The names live in two places (Makefile, config); check_W holds them equal
    in both directions, so a variable only the Makefile tests is never untested."""
    errs, _ = _run(
        repo,
        'WRITE_GUARD = @if [ -n "$(CI)$(RALPH)$(NIGHTLY)" ]; then echo "$(MSG)"; '
        "exit 1; fi\ncheck: ## [local] c\n\tc\n",
    )
    assert len(errs) == 1 and "NIGHTLY" in errs[0] and "MSG" not in errs[0], errs


def test_the_guards_variables_come_from_config_not_from_the_check(repo):
    errs, _ = _run(
        repo,
        _GUARD + "check: ## [local] c\n\tc\n",
        _policy(unattended_vars=["CI", "RALPH", "BUILD_BOT"]),
    )
    assert len(errs) == 1 and "BUILD_BOT" in errs[0], errs


# --- one target, one label ------------------------------------------------------


def test_a_target_annotated_twice_with_different_labels_errors(repo):
    """make merges the two rules into one target; keeping only the first label
    would hide the wider effect (measured: [local] then [write] passed)."""
    errs, _ = _run(
        repo,
        _GUARD + "publish: ## [local] checks\npublish: ## [write] pushes\n\techo P\n",
    )
    assert any("`publish`" in e and "[local]" in e and "[write]" in e for e in errs), (
        errs
    )


def test_a_target_annotated_twice_with_one_label_passes(repo):
    assert _run(repo, "a: ## [local] one\na: ## [local] two\n\tx\n") == ([], [])


# --- the policy -------------------------------------------------------------------


def _policy_errors(value):
    _, errs = cs.make_targets_policy({"make_targets": value})
    return errs


def test_keels_policy_shape_is_valid():
    policy, errs = cs.make_targets_policy({"make_targets": _policy()})
    assert errs == [] and policy["gate_runner_var"] == "RALPH"


def test_a_missing_policy_block_is_an_error_when_a_makefile_exists(repo):
    _write(repo, "check: ## [local] c\n\tc\n", manifest={"name": "x"})
    cs.check_W()
    assert len(cs.errors) == 1 and "make_targets" in cs.errors[0], cs.errors


@pytest.mark.parametrize("key", sorted(_POLICY))
def test_every_policy_key_is_required(key):
    p = _policy()
    del p[key]
    errs = _policy_errors(p)
    assert len(errs) == 1 and key in errs[0], errs


@pytest.mark.parametrize(
    "over, expect",
    [
        ({"unknown": 1}, "unknown"),
        ({"gate_effects": ["read"]}, "local"),
        ({"gate_effects": ["local", "tree"]}, "tree"),
        ({"gate_effects": ["local", "write"]}, "write"),
        ({"gate_effects": ["local", "remote"]}, "remote"),
        ({"gate_runner_var": "LOOP"}, "LOOP"),
        ({"unattended_vars": []}, "unattended_vars"),
        ({"unattended_vars": ["CI", "bad name"]}, "bad name"),
        ({"write_shapes": ["apply"]}, "apply"),
        ({"area_dir": "mk/areas"}, "mk/areas"),
        ({"area_dir": 3}, "area_dir"),
        ({"effect_proof_skip": ["run"]}, "effect_proof_skip"),
        ({"effect_proof_skip": {"run": ""}}, "run"),
        ({"write_shape_exempt": ["doc-review-apply"]}, "write_shape_exempt"),
        ({"write_shape_exempt": {"doc-review-apply": "  "}}, "doc-review-apply"),
        ({"write_shape_exempt": {"doc-review-apply": 3}}, "doc-review-apply"),
        ({"empty_test_selections": ["smoke"]}, "empty_test_selections"),
        ({"empty_test_selections": {"smoke": ""}}, "empty_test_selections.smoke"),
        ({"empty_test_selections": {"smoke": 3}}, "empty_test_selections.smoke"),
        ({"empty_test_selections": {"smoke test": "r"}}, "smoke test"),
        ({"empty_test_selections": {"smoke-test": "r"}}, "smoke-test"),
        ({"gate_vars": "PY"}, "gate_vars"),
        ({"gate_vars": ["PY", "bad name"]}, "bad name"),
        ({"gate_vars": ["MAKEFILES"]}, "MAKEFILES"),
        ({"gate_vars": ["MAKEFLAGS"]}, "MAKEFLAGS"),
        ({"gate_vars": ["SHELL"]}, "SHELL"),
        ({"gate_vars": ["WRITE_GUARD"]}, "WRITE_GUARD"),
        ({"gate_vars": ["CI"]}, "CI"),
    ],
)
def test_a_malformed_policy_value_is_an_error(over, expect):
    errs = _policy_errors(_policy(**over))
    assert len(errs) == 1 and expect in errs[0], errs


@pytest.mark.parametrize("value", ["x", [], None])
def test_a_policy_that_is_not_an_object_is_an_error(value):
    errs = _policy_errors(value)
    assert len(errs) == 1 and "object" in errs[0], errs


def test_a_broken_policy_reds_the_gate(repo):
    errs, _ = _run(repo, "check: ## [local] c\n\tc\n", _policy(gate_effects=["read"]))
    assert len(errs) == 1 and errs[0].startswith("config/project.json"), errs


def test_a_skip_entry_naming_no_target_is_stale(repo):
    errs, _ = _run(
        repo,
        "check: ## [local] c\n\tc\n",
        _policy(effect_proof_skip={"gone": "was a dev server"}),
    )
    assert len(errs) == 1 and "gone" in errs[0] and "effect_proof_skip" in errs[0]


# --- empty_test_selections: a declared-empty marker names a pytest -m recipe -------

_TIERS = (
    "test: ## [local] t\n\tPYTHONPATH=$(PYTHONPATH) $(PY) -m pytest\n"
    "smoke: ## [local] s\n\tPYTHONPATH=$(PYTHONPATH) $(PY) -m pytest -m smoke\n"
)


def test_a_declared_empty_selection_naming_a_pytest_marker_is_clean(repo):
    errs, warns = _run(
        repo, _TIERS, _policy(empty_test_selections={"smoke": "no smoke surface yet"})
    )
    assert errs == [] and warns == [], (errs, warns)


def test_a_declared_empty_selection_naming_no_pytest_marker_is_stale(repo):
    errs, _ = _run(
        repo, _TIERS, _policy(empty_test_selections={"nightly": "not written yet"})
    )
    assert len(errs) == 1, errs
    assert "stale: make_targets.empty_test_selections.nightly" in errs[0], errs


def test_a_non_pytest_dash_m_is_not_a_marker(repo):
    """`$(PY) -m pytest` is itself a `-m`: only a `-m` after the pytest word
    selects a marker, so `pytest` cannot be declared as one."""
    errs, _ = _run(repo, _TIERS, _policy(empty_test_selections={"pytest": "x"}))
    assert len(errs) == 1 and "empty_test_selections.pytest" in errs[0], errs


def test_the_pytest_selections_are_read_from_the_recipes_not_a_list():
    """target -> the `-m` expression after the pytest word (None: no `-m`); a
    recipe that never runs pytest is not a selection, and nothing is listed."""
    text = (
        _TIERS
        + "quoted: ## [local] q\n\t$(PY) -m pytest -q -m 'nightly' tests\n"
        + 'compound: ## [local] c\n\t$(PY) -m pytest -m "smoke and not slow"\n'
        + "lint: ## [local] l\n\t$(PY) -m ruff check -m x\n"
    )
    assert cs.pytest_selections([("Makefile", "")]) == {}
    assert cs.pytest_selections([("Makefile", text)]) == {
        "test": None,
        "smoke": "smoke",
        "quoted": "nightly",
        "compound": "smoke and not slow",
    }


def test_a_compound_selection_cannot_be_declared_empty(repo):
    """Only a bare marker is declarable: `smoke and not slow` is not `smoke`."""
    errs, _ = _run(
        repo,
        'part: ## [local] p\n\t$(PY) -m pytest -m "smoke and not slow"\n',
        _policy(empty_test_selections={"smoke": "r"}),
    )
    assert len(errs) == 1 and "empty_test_selections.smoke" in errs[0], errs


# --- areas --------------------------------------------------------------------------


def test_an_area_header_with_areas_off_is_an_error(repo):
    errs, _ = _run(repo, "##@ repo  gates\ncheck: ## [local] c\n\tc\n")
    assert len(errs) == 1 and "##@" in errs[0] and "area_dir" in errs[0], errs


_AREA_ROOT = _GUARD + "check: ## [local] c\n\tc\n"


def test_an_included_well_formed_area_passes(repo):
    assert _run(
        repo,
        "##@ repo  gates\n" + _AREA_ROOT + "include mk/gateway.mk\n",
        _policy(area_dir="mk"),
        mk__gateway_mk="##@ gateway  the gateway\n"
        "gateway-plan: ## [read] Plan\n\tplan\n"
        "_gateway-helper:\n\thelp\n",
    ) == ([], [])


@pytest.mark.parametrize(
    "area_text, expect",
    [
        ("gateway-plan: ## [read] p\n\tp\n", "##@ gateway"),
        ("##@ other  x\ngateway-plan: ## [read] p\n\tp\n", "##@ gateway"),
        ("##@ gateway  x\nplan: ## [read] p\n\tp\n", "gateway-"),
        ("##@ gateway  x\ngateway-plan:\n\tp\n", "annotation"),
    ],
    ids=["no-header", "wrong-header", "unprefixed", "unannotated"],
)
def test_an_area_makefile_breaking_a_rule_errors(repo, area_text, expect):
    errs, _ = _run(
        repo,
        _AREA_ROOT + "include mk/gateway.mk\n",
        _policy(area_dir="mk"),
        mk__gateway_mk=area_text,
    )
    assert len(errs) == 1 and expect in errs[0], errs


def test_an_area_makefile_nothing_includes_is_an_error(repo):
    errs, _ = _run(
        repo,
        _AREA_ROOT,
        _policy(area_dir="mk"),
        mk__gateway_mk="##@ gateway  x\ngateway-plan: ## [read] p\n\tp\n",
    )
    assert len(errs) == 1 and "mk/gateway.mk" in errs[0] and "include" in errs[0]


def test_a_misnamed_area_makefile_is_an_error(repo):
    errs, _ = _run(
        repo,
        _AREA_ROOT + "include mk/Gate_way.mk\n",
        _policy(area_dir="mk"),
        mk__Gate_way_mk="##@ Gate_way  x\n",
    )
    assert any("mk/Gate_way.mk" in e and "kebab" in e for e in errs), errs


def test_a_declared_area_directory_that_is_absent_is_stale(repo):
    errs, _ = _run(repo, _AREA_ROOT, _policy(area_dir="mk"))
    assert len(errs) == 1 and "area_dir" in errs[0] and "mk" in errs[0], errs


def test_two_area_headers_in_one_makefile_is_an_error(repo):
    errs, _ = _run(repo, "##@ a  x\n##@ b  y\n" + _AREA_ROOT, _policy(area_dir="mk"))
    errs = [e for e in errs if "area_dir" not in e]
    assert len(errs) == 1 and "##@" in errs[0], errs


# --- the shape bedrock-platform ships, and keel's own -------------------------------


def test_the_bedrock_platform_shape_passes(repo):
    """The shape check_W was ported from (bedrock-platform docs/adr/0010-areas-and-
    effect-labels.md): a root `##@` group, a guard, explicit area includes, shaped
    [write] targets that open with the guard, and a composite gate."""
    errs, warns = _run(
        repo,
        "##@ repo  gates\n"
        "help: ## [local] List tasks\n\t@echo\n" + _GUARD + "include mk/guardrail.mk\n"
        "lint: guardrail-lint ## [local] Lint\n\truff check\n"
        "doc-review-apply: ## [cost] Apply a paid doc review\n\tapply\n",
        _policy(
            write_shapes=["-apply", "-drill", "-destroy"],
            area_dir="mk",
            write_shape_exempt={"doc-review-apply": _EXEMPT_REASON},
        ),
        mk__guardrail_mk="##@ guardrail  who may call what\n"
        "guardrail-lint: ## [local] Lint guardrail\n\tlint\n"
        "guardrail-caps-plan: ## [read] Plan\n\tplan\n"
        "guardrail-caps-apply: ## [write] Apply\n\t$(WRITE_GUARD)\n\tapply\n",
    )
    assert errs == [] and warns == []


def test_keels_own_makefile_passes(monkeypatch):
    monkeypatch.setattr(cs, "ROOT", str(_ROOT))
    monkeypatch.setattr(cs, "errors", [])
    monkeypatch.setattr(cs, "warnings", [])
    monkeypatch.setattr(cs, "_CONFIG_READ", {})
    monkeypatch.setattr(cs, "_READ_REPORTED", set())
    cs.check_W()
    assert cs.errors == [] and cs.warnings == []
    effects = cs.target_effects(str(_ROOT))
    assert effects, "keel's Makefile yielded no targets -- this proves nothing"
    unlabelled = sorted(t for t, (labels, _) in effects.items() if labels is None)
    assert unlabelled == [], unlabelled


# --- the parser and the runner's view ------------------------------------------------


def test_the_rule_parser_reads_what_make_reads():
    rules = cs.make_target_rules(
        "X := a:b\n"
        "t: VAR = 1\n"
        "%.o: %.c\n\tcc\n"
        ".PHONY: a\n"
        "define BODY\nfake: ## [write] no\nendef\n"
        "a b: c $(D) ## [local] Two at once\n"
        "\t# a shell comment\n"
        "\t@first \\\n\t  continued\n"
        "\n"
        "c:\n\t$(MAKE) d\n"
    )
    by = {r.target: r for r in rules}
    assert sorted(by) == ["a", "b", "c"], sorted(by)
    assert by["a"].help == "[local] Two at once" and by["b"].help == by["a"].help
    assert by["a"].prereqs == ["c"] and by["a"].unresolved == ["$(D)"]
    assert by["a"].first_recipe == "first continued", by["a"].first_recipe
    assert by["a"].lineno == 9
    assert by["c"].recursions == ["d"] and by["c"].help is None


def test_target_effects_closes_over_prerequisites_and_refuses_the_unprovable(tmp_path):
    (tmp_path / "Makefile").write_text(
        "check: ## [local] c\n\tc\n"
        "fmt: ## [tree] f\n\tf\n"
        "cloud: ## [read] r\n\tr\n"
        "verify: check cloud ## [read] v\n"
        "lying: fmt ## [local] says local\n"
        "helper:\n\th\n"
        "uses-helper: helper ## [local] u\n"
        "opaque: ## [local] o\n\t$(MAKE) -C sub all\n"
        "bad: ## [nonsense] b\n\tb\n",
        encoding="utf-8",
    )
    eff = cs.target_effects(str(tmp_path))
    assert eff["check"] == (("local",), None)
    assert eff["verify"] == (("read",), None)
    assert eff["lying"][0] == ("tree",), eff["lying"]
    for name in ("helper", "uses-helper", "opaque", "bad"):
        labels, why = eff[name]
        assert labels is None and why, (name, eff[name])
    assert "helper" in eff["uses-helper"][1]


def test_target_effects_refuses_a_target_annotated_twice_with_different_labels(
    tmp_path,
):
    (tmp_path / "Makefile").write_text(
        "publish: ## [local] checks\npublish: ## [write] pushes\n\tp\n"
        "outer: publish ## [local] o\n",
        encoding="utf-8",
    )
    eff = cs.target_effects(str(tmp_path))
    labels, why = eff["publish"]
    assert labels is None and "[local]" in why and "[write]" in why, eff["publish"]
    assert eff["outer"][0] is None, eff["outer"]


# --- check_P rides the same walk ------------------------------------------------------


def test_walk_makefiles_follows_includes_in_order_and_reports_what_it_cannot(tmp_path):
    (tmp_path / "Makefile").write_text(
        "include a.mk\ninclude $(X)\n-include gone.mk\n", encoding="utf-8"
    )
    (tmp_path / "a.mk").write_text("include b.mk\n", encoding="utf-8")
    (tmp_path / "b.mk").write_text("x:\n", encoding="utf-8")
    said = []
    walked = cs.walk_makefiles(str(tmp_path), said.append)
    assert [p for p, _ in walked] == ["Makefile", "a.mk", "b.mk"]
    assert len(said) == 1 and "$(X)" in said[0], said


def test_check_p_still_passes_on_keels_makefile(monkeypatch):
    monkeypatch.setattr(cs, "ROOT", str(_ROOT))
    monkeypatch.setattr(cs, "errors", [])
    monkeypatch.setattr(cs, "warnings", [])
    monkeypatch.setattr(cs, "_READ_REPORTED", set())
    cs.check_P()
    assert cs.errors == [] and cs.warnings == []
