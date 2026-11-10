"""
title: Unit — Makefile judge refuses unmodelled make and pytest forms
summary: Small fixture Makefiles exercise guarded parsing, recipe expansion, make hops and full pytest argument derivation; unsupported forms fail with the input, cause and fix.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import makefile_judge as judge

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "makefile",
    [
        'FLAGS = -m "not slow"\n'
        "HOP = test EXTRA='$(FLAGS)'\n"
        "verify:\n\t$(PY) gate.py -- $(MAKE) $(HOP) test\n"
        "test:\n\t$(PY) -m pytest --durations 10 $(EXTRA)\n",
        "verify:\n\t$(PY) gate.py -- $(MAKE) fast test\n"
        'fast:\n\t$(PY) -m pytest --durations 10 -m "not slow"\n'
        "test:\n\t$(PY) -m pytest --durations 10\n",
        "verify:\n\t$(PY) gate.py -- $(MAKE) test\ntest:\n\t@echo no tests\n",
    ],
    ids=["variable-hop", "different-target", "zero-pytest"],
)
def test_verify_rejects_incomplete_test_chains(tmp_path: Path, makefile: str) -> None:
    (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    with pytest.raises(AssertionError, match="pytest"):
        judge.assert_verify_keeps_slow(tmp_path)


@pytest.mark.parametrize(
    "args",
    [
        '--durations 10 -m "not slow"',
        "--durations=10 -mnot\\ slow",
        "--durations 10 -k quick",
        "--durations 10 -kquick",
        "--durations 10 --deselect tests/test_sample.py::test_slow",
        "--durations 10 --deselect=tests/test_sample.py::test_slow",
        "--durations 10 --ignore=tests/test_slow.py",
        "--durations 10 --lf",
        "",
        "--durations",
    ],
)
def test_verify_checks_every_pytest_and_its_durations(
    tmp_path: Path, args: str
) -> None:
    (tmp_path / "Makefile").write_text(
        "NEXT = middle\n"
        "verify:\n\t$(MAKE) $(NEXT)\n"
        "middle:\n\t$(PY) gate.py -- $(MAKE) test\n"
        "test:\n\t$(PY) -m pytest --durations 10\n"
        f"\t$(PY) -m pytest {args}\n",
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="pytest"):
        judge.assert_verify_keeps_slow(tmp_path)


def test_verify_follows_later_hops_and_distinct_variable_values(tmp_path: Path) -> None:
    (tmp_path / "Makefile").write_text(
        "HOP = middle EXTRA='--durations=7'\n"
        "verify:\n\t$(MAKE) $(HOP)\n"
        "middle:\n\t$(PY) -m pytest --durations 10\n"
        "\t$(MAKE) test\n"
        "test:\n\t$(PY) -m pytest $(EXTRA)\n",
        encoding="utf-8",
    )
    judge.assert_verify_keeps_slow(tmp_path)
    with (tmp_path / "Makefile").open("a", encoding="utf-8") as stream:
        stream.write("\t$(MAKE) later\nlater:\n\t$(PY) -m pytest -k quick\n")
    with pytest.raises(AssertionError, match="pytest"):
        judge.assert_verify_keeps_slow(tmp_path)


_FULL_CHAIN = "verify:\n\t$(MAKE) test\ntest:\n\t$(PY) -m pytest --durations 10\n"


@pytest.mark.parametrize(
    "runner",
    [
        "script -qc",
        "script --command",
        "su -c",
        "sg grp -c",
        "busybox sh -c",
        "runuser -c",
        "flock f -c",
    ],
)
@pytest.mark.parametrize("body", ["pytest --durations 10 -k quick", "export $$n=x"])
def test_string_runners_judge_each_executed_command(
    tmp_path: Path, runner: str, body: str
) -> None:
    path = tmp_path / "Makefile"
    path.write_text(_FULL_CHAIN + f"\tn=OTHER; {runner} '{body}'\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="Fix:"):
        judge.assert_verify_keeps_slow(tmp_path)


@pytest.mark.parametrize("shell", ["csh", "tcsh", "fish"])
def test_non_posix_strings_are_refused(tmp_path: Path, shell: str) -> None:
    body = "set -gx OTHER x" if shell == "fish" else "setenv OTHER x"
    path = tmp_path / "Makefile"
    path.write_text(_FULL_CHAIN + f"\t{shell} -c '{body}'\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="Fix:"):
        judge.assert_verify_keeps_slow(tmp_path)


@pytest.mark.parametrize("name", ["BASH_ENV", "ENV"])
@pytest.mark.parametrize(
    "shape", ["{name}=startup", "export {name}", "sh -c 'export {name}=startup'"]
)
def test_shell_startup_inputs_are_refused(
    tmp_path: Path, name: str, shape: str
) -> None:
    path = tmp_path / "Makefile"
    path.write_text(
        _FULL_CHAIN + "\t" + shape.format(name=name) + "\n", encoding="utf-8"
    )
    with pytest.raises(AssertionError, match=name) as failure:
        judge.assert_verify_keeps_slow(tmp_path)
    assert str(path) in str(failure.value)
    assert "Fix:" in str(failure.value)


@pytest.mark.parametrize(
    "shape",
    [
        '$(PY) -c \'import os,pytest; os.environ["PYTEST_"+"ADDOPTS"]="-k quick"; pytest.main()\'',
        "perl -e 'system(\"pytest --durations 10 -k quick\")'",
        "ruby -e 'system(\"pytest --durations 10 -k quick\")'",
    ],
    ids=["python-environment", "perl-system", "ruby-system-extra-shape"],
)
def test_interpreter_strings_naming_pytest_are_refused(
    tmp_path: Path, shape: str
) -> None:
    path = tmp_path / "Makefile"
    path.write_text(_FULL_CHAIN + f"\t{shape}\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="Fix:"):
        judge.assert_verify_keeps_slow(tmp_path)


@pytest.mark.parametrize(
    "shape",
    [
        "runuser -c 'pytest -k x' bob",
        "flock f -c 'pytest -k x'",
    ],
)
def test_added_shell_runners_judge_pytest(tmp_path: Path, shape: str) -> None:
    (tmp_path / "Makefile").write_text(_FULL_CHAIN + f"\t{shape}\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="pytest.*Fix:"):
        judge.assert_verify_keeps_slow(tmp_path)


@pytest.mark.parametrize(
    "shape",
    [
        "doas sh -c 'pytest -k x'",
        "sudo sh -c 'pytest -k x'",
        "watch -n1 'pytest -k x'",
        "ssh host 'pytest -k x'",
        "parallel sh -c 'pytest -k x'",
        "perl -le 'system(\"pytest -k x\")'",
        "python3 -Bc 'import pytest'",
        "Rscript -e 'system(\"pytest -k x\")'",
        "awk 'BEGIN{system(\"pytest -k x\")}'",
        "tclsh -c 'exec pytest -k x'",
        "tclsh <<< 'exec pytest -k x'",
        "unlisted --payload='pytest -k x'",
        "unlisted 'before;pytest.main()'",
        "sh -c 'true' ignored 'pytest -k x'",
        "sh -c 'true' ignored 'true' 'pytest -k x'",
        "sh --pytest=x -c x",
    ],
)
def test_unwalked_arguments_naming_pytest_are_refused(
    tmp_path: Path, shape: str
) -> None:
    path = tmp_path / "Makefile"
    path.write_text(_FULL_CHAIN + f"\t{shape}\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="pytest.*Fix:") as failure:
        judge.assert_verify_keeps_slow(tmp_path)
    message = str(failure.value)
    assert shape.split()[0] in message
    assert "pytest" in message
    assert "string " in message
    assert str(path) in message


@pytest.mark.parametrize(
    "shape",
    [
        "$(PY) -c 'print(1)'",
        "unlisted 'notpytest pytest_helper pytest2'",
        "sh -c 'pytest --durations 10'",
        "runuser -c 'pytest --durations 10' bob",
        "flock f -c 'pytest --durations 10'",
        "nice sh -c 'pytest --durations 10'",
        r"find . -exec sh -c 'pytest --durations 10' \;",
        "printf '%s' 'pytest --durations 10' | sh",
        "printf '%s' 'pytest --durations 10' | nice sh",
    ],
)
def test_judged_strings_and_unrelated_words_are_accepted(
    tmp_path: Path, shape: str
) -> None:
    (tmp_path / "Makefile").write_text(_FULL_CHAIN + f"\t{shape}\n", encoding="utf-8")
    judge.assert_verify_keeps_slow(tmp_path)


@pytest.mark.parametrize("body", ["echo $$HOME", "export FOO=1; true"])
def test_walked_literal_shell_strings_are_accepted(tmp_path: Path, body: str) -> None:
    (tmp_path / "Makefile").write_text(
        _FULL_CHAIN + f"\tsh -c '{body}'\n", encoding="utf-8"
    )
    judge.assert_verify_keeps_slow(tmp_path)


@pytest.mark.parametrize(
    "shape",
    [
        "nice env $$n=x true",
        "nice -n 5 env $$n=x true",
        "timeout 5 env $$n=x true",
        "nohup env $$n=x true",
        "setsid env $$n=x true",
        "stdbuf -o0 env $$n=x true",
        "xargs env $$n=x true",
        r"find . -exec env $$n=x true \;",
        "dash -c 'export $$n=x'",
        "zsh -c 'export $$n=x'",
        "ksh -c 'export $$n=x'",
        "/bin/sh -c 'export $$n=x'",
        "bash -c -- 'export $$n=x'",
        "bash <<< 'export $$n=x'",
        "echo 'export $$n=x' | sh",
        "time export $$n=x",
        "f() { export $$n=x; }; f",
        "{ export $$n=x; }",
        "e=export; $$e $$n=x",
        "timeout --signal TERM 5 nice --adjustment 3 env $$n=x true",
        r"find . -execdir env $$n=x true +",
        "function f { export $$n=x; }; f",
        "printf '%s' 'export $$n=x' | dash -s --",
        "env -u OTHER command -- exec env $$n=x true",
        "xargs -I {} env $$n=x true",
    ],
    ids=[
        "nice",
        "nice-option",
        "timeout",
        "nohup",
        "setsid",
        "stdbuf",
        "xargs",
        "find-exec",
        "dash",
        "zsh",
        "ksh",
        "absolute-sh",
        "shell-c-double-dash",
        "here-string",
        "stdin-pipe",
        "time",
        "function",
        "brace-group",
        "computed-command",
        "nested-wrapper-options",
        "find-execdir",
        "function-keyword",
        "printf-stdin",
        "env-options",
        "xargs-option-operand",
    ],
)
def test_every_command_position_refuses_shell_chosen_names(
    tmp_path: Path, shape: str
) -> None:
    path = tmp_path / "Makefile"
    path.write_text(
        _FULL_CHAIN.replace("\t$(PY)", f"\tn=PYTEST_PLUGINS; {shape}; $(PY)"),
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="Cannot judge.*environment") as failure:
        judge.assert_verify_keeps_slow(tmp_path)
    assert str(path) in str(failure.value)
    assert "Fix:" in str(failure.value)


def test_help_prose_refuses_a_doubled_dollar_pytest_reference(tmp_path: Path) -> None:
    path = tmp_path / "Makefile"
    path.write_text(
        _FULL_CHAIN + "\t@echo '$$PYTEST_PLUGINS configures plugins'\n",
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="pytest environment PYTEST_PLUGINS"):
        judge.assert_verify_keeps_slow(tmp_path)


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("printf '%s\\n' 'pytest --durations 10' | dash", ["printf", "dash", "pytest"]),
        ("sh <<'END'\npytest --durations 10\nEND\n", ["sh", "pytest"]),
        ("value=$(env OTHER=value true)", ["env", "true"]),
        ('echo "$(env OTHER=value true)"', ["env", "true", "echo"]),
        ("sh <<< 'pytest --durations 10' -s", ["sh", "pytest"]),
        ("2>/dev/null time -p env OTHER=value true", ["time", "env", "true"]),
    ],
    ids=[
        "printf-script",
        "heredoc-script",
        "assignment-substitution",
        "argument-substitution",
        "redirect-before-options",
        "leading-redirection",
    ],
)
def test_command_iterator_follows_executed_text(
    command: str, expected: list[str]
) -> None:
    assert [entry.word for entry in judge._command_words(command)] == expected


@pytest.mark.parametrize(
    "shape",
    [
        "env -u $$n true",
        "echo value | xargs env",
        "echo value | xargs -I NAME env NAME=x true",
        r"find . -exec {} $$n=x true \;",
        "v=$$(env $$n=x true)",
        "posh -c 'export $$n=x'",
        "echo 'export $$n=x' | sh -s argument",
        "dash -o errexit -c 'export $$n=x'",
        "command env -v $$n=x true",
        "ionice -c 3 env $$n=x true",
        "time OTHER=value export $$n=x",
        r"printf '%b' '\0145nv \0044n=x true' | sh",
        r"echo -e '\0145nv \0044n=x true' | sh",
        "opts='5 env'; nice -n $$opts true",
        "opts='5 env'; timeout $$opts true",
    ],
    ids=[
        "computed-unset",
        "xargs-appended-names",
        "xargs-replaced-names",
        "find-computed-command",
        "substitution-environment",
        "another-posix-shell",
        "stdin-shell-arguments",
        "shell-option-operand",
        "command-query-argument",
        "ionice-wrapper",
        "time-assignment-prefix",
        "printf-encoded-script",
        "echo-encoded-script",
        "computed-wrapper-option",
        "computed-wrapper-positional-operand",
    ],
)
def test_command_runner_inputs_cannot_choose_environment_names(
    tmp_path: Path, shape: str
) -> None:
    path = tmp_path / "Makefile"
    path.write_text(
        _FULL_CHAIN.replace("\t$(PY)", f"\tn=PYTEST_PLUGINS; {shape}; $(PY)"),
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="Cannot judge.*environment") as failure:
        judge.assert_verify_keeps_slow(tmp_path)
    assert str(path) in str(failure.value)
    assert "Fix:" in str(failure.value)


@pytest.mark.parametrize(
    "command",
    [
        "pytest --durations 10; echo pytest",
        "pytest --durations 10; python -B -m pytest -k quick",
        "pytest --durations 10 > report",
    ],
    ids=["data-mention", "interpreter-options", "redirected-pytest"],
)
def test_pytest_guard_keeps_earlier_conservative_refusals(command: str) -> None:
    with pytest.raises(AssertionError, match="pytest.*Fix:"):
        judge.assert_full_pytests(command)


@pytest.mark.parametrize(
    "command",
    [
        "make test; true",
        "true; make test",
        "make test > report",
        "python gate.py -- __keel_make__ test; true",
    ],
)
def test_make_guard_keeps_earlier_conservative_refusals(command: str) -> None:
    with pytest.raises(AssertionError, match="make.*Fix:"):
        judge.make_hop(command)


@pytest.mark.parametrize(
    "name",
    [
        "PYTEST_ADDOPTS",
        "PYTEST_PLUGINS",
        "PYTEST_XDIST_AUTO_NUM_WORKERS",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
        "PYTEST_DEBUG",
        "PYTEST_DEBUG_TEMPROOT",
        "PYTEST_THEME",
        "PYTEST_THEME_MODE",
        "PY_COLORS",
        "NO_COLOR",
        "FORCE_COLOR",
        "CI",
        "BUILD_NUMBER",
    ],
)
@pytest.mark.parametrize(
    ("prefix", "recipe"),
    [
        ("", "export {name}=literal\n\t$(PY) -m pytest --durations 10"),
        ("", "export {name}=literal; $(PY) -m pytest --durations 10"),
        ("", "export {name}=literal && $(PY) -m pytest --durations 10"),
        ("", "env {name}=literal $(PY) -m pytest --durations 10"),
        ("export {name}=literal\n", "$(PY) -m pytest --durations 10"),
        ("export {name}\n", "$(PY) -m pytest --durations 10"),
        ("{name} = literal\nexport\n", "$(PY) -m pytest --durations 10"),
        ("test: {name} = literal\n", "$(PY) -m pytest --durations 10"),
        ("", "{name}=literal\n\t$(PY) -m pytest --durations 10"),
        ("", "declare -x {name}=literal; $(PY) -m pytest --durations 10"),
    ],
    ids=[
        "earlier-export",
        "semicolon-export",
        "and-export",
        "env-prefix",
        "make-export-value",
        "make-export-name",
        "make-export-all",
        "target-variable",
        "earlier-assignment",
        "declare-export",
    ],
)
def test_pytest_inputs_are_refused_in_every_placement(
    tmp_path: Path, name: str, prefix: str, recipe: str
) -> None:
    text = (
        prefix.format(name=name)
        + "verify:\n\t$(MAKE) test\ntest:\n\t"
        + recipe.format(name=name)
        + "\n"
    )
    path = tmp_path / "Makefile"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(
        AssertionError, match=f"Unjudged pytest environment {name}"
    ) as failure:
        judge.assert_verify_keeps_slow(tmp_path)
    assert str(path) in str(failure.value)
    assert "Fix:" in str(failure.value)


@pytest.mark.parametrize("operation", ["export", "declare -x", "env"])
@pytest.mark.parametrize(
    "name",
    ["$$name", "$${name}", "PYTEST_`printf PLUGINS`"],
    ids=["shell-variable", "braced-variable", "backquote"],
)
def test_shell_computed_export_names_are_refused(
    tmp_path: Path, operation: str, name: str
) -> None:
    path = tmp_path / "Makefile"
    path.write_text(
        "verify:\n\t$(MAKE) test\ntest:\n"
        f"\tname=PYTEST_PLUGINS; {operation} {name}=literal\n"
        "\t$(PY) -m pytest --durations 10\n",
        encoding="utf-8",
    )
    with pytest.raises(
        AssertionError, match="Cannot judge a computed.*name"
    ) as failure:
        judge.assert_verify_keeps_slow(tmp_path)
    message = str(failure.value)
    assert str(path) in message
    assert "Fix:" in message and "literal" in message


@pytest.mark.parametrize("operation", ["export", "declare -x", "env"])
def test_quoted_pytest_input_names_are_refused(tmp_path: Path, operation: str) -> None:
    path = tmp_path / "Makefile"
    path.write_text(
        "verify:\n\t$(MAKE) test\ntest:\n"
        f"\t{operation} PYTEST_'PLUGINS'=literal; $(PY) -m pytest --durations 10\n",
        encoding="utf-8",
    )
    with pytest.raises(
        AssertionError, match="pytest environment PYTEST_PLUGINS"
    ) as failure:
        judge.assert_verify_keeps_slow(tmp_path)
    assert str(path) in str(failure.value)
    assert "Fix:" in str(failure.value)


@pytest.mark.parametrize("builtin", ["declare", "typeset", "local"])
@pytest.mark.parametrize("options", ["-gx", "-xg", "-g -x"])
@pytest.mark.parametrize("name", ["$$n", "$${n}", "PYTEST_'PLUGINS'"])
def test_export_option_clusters_are_refused(
    tmp_path: Path, builtin: str, options: str, name: str
) -> None:
    path = tmp_path / "Makefile"
    path.write_text(
        _FULL_CHAIN.replace(
            "\t$(PY)", f"\tn=PYTEST_PLUGINS; {builtin} {options} {name}; $(PY)"
        ),
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="environment|computed.*name") as failure:
        judge.assert_verify_keeps_slow(tmp_path)
    assert str(path) in str(failure.value)
    assert "Fix:" in str(failure.value)


@pytest.mark.parametrize(
    "shape",
    ["eval 'true'"]
    + [
        f"{path}{shell} -c '{body}'"
        for path in ("", "/bin/", "/custom/")
        for shell in ("sh", "bash")
        for body in ("$$n", "`printf true`")
    ],
)
def test_indirect_shell_environment_is_refused(tmp_path: Path, shape: str) -> None:
    path = tmp_path / "Makefile"
    path.write_text(
        _FULL_CHAIN.replace("\t$(PY)", f"\tn=PYTEST_PLUGINS; {shape}; $(PY)"),
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="Cannot judge.*environment") as failure:
        judge.assert_verify_keeps_slow(tmp_path)
    assert str(path) in str(failure.value)
    assert "Fix:" in str(failure.value)


@pytest.mark.parametrize(
    "shape",
    [
        f"{path}{shell} -c '{body}'"
        for path in ("", "/bin/", "/custom/")
        for shell in ("sh", "bash")
        for body in (
            "export OTHER=value",
            "declare -x OTHER=value",
            "typeset -x OTHER=value",
            "local -x OTHER=value",
            "env OTHER=value true",
        )
    ],
)
def test_indirect_shell_environment_is_accepted(tmp_path: Path, shape: str) -> None:
    (tmp_path / "Makefile").write_text(
        _FULL_CHAIN.replace("\t$(PY)", f"\tn=PYTEST_PLUGINS; {shape}; $(PY)"),
        encoding="utf-8",
    )
    judge.assert_verify_keeps_slow(tmp_path)


@pytest.mark.parametrize("name", judge._PYTEST_INPUT_VARIABLES)
@pytest.mark.parametrize("reference", ["$({})", "${{{}}}", "$${}", "$${{{}}}"])
@pytest.mark.parametrize("expanded", [False, True], ids=["raw", "expanded"])
def test_pytest_input_references_are_refused(
    tmp_path: Path, name: str, reference: str, *, expanded: bool
) -> None:
    reference = reference.format(name)
    if expanded:
        reference = reference.replace("$", "$(D)")
    text = ("D = $$\n" if expanded else "") + _FULL_CHAIN
    path = tmp_path / "Makefile"
    path.write_text(text + f"\t@echo {reference}\n", encoding="utf-8")
    with pytest.raises(AssertionError, match=f"pytest environment {name}") as failure:
        judge.assert_verify_keeps_slow(tmp_path)
    assert str(path) in str(failure.value)
    assert "Fix:" in str(failure.value)


@pytest.mark.parametrize(
    "shape", ["set -a", "set -o allexport", ". file", "source file"]
)
def test_implicit_shell_exports_are_refused(tmp_path: Path, shape: str) -> None:
    path = tmp_path / "Makefile"
    path.write_text(
        _FULL_CHAIN.replace("\t$(PY)", f"\tn=PYTEST_PLUGINS; {shape}; $(PY)"),
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="Cannot judge.*environment") as failure:
        judge.assert_verify_keeps_slow(tmp_path)
    assert str(path) in str(failure.value)
    assert "Fix:" in str(failure.value)


def test_make_variable_override_is_refused_before_make_hop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected_hop(command: str) -> tuple[list[str], list[str]]:
        pytest.fail(f"override reached make_hop: {command}")

    monkeypatch.setattr(judge, "make_hop", unexpected_hop)
    path = tmp_path / "Makefile"
    path.write_text(
        "OVR = CI=1\n" + _FULL_CHAIN.replace("$(MAKE) test", "$(MAKE) test $(OVR)"),
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="pytest environment CI") as failure:
        judge.assert_verify_keeps_slow(tmp_path)
    assert "OVR = CI=1" in str(failure.value)
    assert str(path) in str(failure.value)
    assert "Fix:" in str(failure.value)


def test_pytest_variable_help_prose_is_accepted(tmp_path: Path) -> None:
    (tmp_path / "Makefile").write_text(
        _FULL_CHAIN + "\t@echo 'PYTEST_PLUGINS configures plugins'\n", encoding="utf-8"
    )
    judge.assert_verify_keeps_slow(tmp_path)


def test_unused_deferred_data_does_not_import_pytest_inputs(tmp_path: Path) -> None:
    (tmp_path / "Makefile").write_text(
        "UNUSED = $(CI)\n" + _FULL_CHAIN, encoding="utf-8"
    )
    judge.assert_verify_keeps_slow(tmp_path)


@pytest.mark.parametrize("reference", ["$(CI)", "${CI}", "$$CI", "$${CI}"])
def test_used_deferred_data_refuses_pytest_input_references(
    tmp_path: Path, reference: str
) -> None:
    path = tmp_path / "Makefile"
    path.write_text(
        f"DATA = {reference}\nALIAS = $(DATA)\n"
        + _FULL_CHAIN.replace("--durations 10", "--durations 10 $(ALIAS)"),
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="pytest environment CI") as failure:
        judge.assert_verify_keeps_slow(tmp_path)
    assert str(path) in str(failure.value)
    assert "Fix:" in str(failure.value)


@pytest.mark.parametrize(
    ("prefix", "reason"),
    [
        ("-include missing.mk\nmissing.mk:\n\t@touch missing.mk\n", "include"),
        ("include missing.mk\nmissing.mk:\n\t@touch missing.mk\n", "include"),
        ("X := $(call shell,printf harmless)\n", "expansion"),
        ("X := $(shell printf harmless)\n", "expansion"),
        ("FN = shell\nX := $($(FN) printf harmless)\n", "expansion"),
        ("ifeq (1,1)\nX = yes\nendif\n", "conditional"),
        ("X != printf harmless\n", "shell assignment"),
        ("export PYTEST_ADDOPTS = -m slow\n", "PYTEST_ADDOPTS"),
        ("test: export PYTEST_ADDOPTS = -m slow\n", "PYTEST_ADDOPTS"),
        ("test: PYTEST_ADDOPTS = -m slow\n", "PYTEST_ADDOPTS"),
        ("other::\n\t@echo harmless\n", "double-colon"),
        ("other: FLAG = value\n", "target-specific"),
        ("other:\n\t+echo harmless\n", "forced recipe"),
    ],
    ids=[
        "absent-optional-include",
        "absent-required-include",
        "call-shell",
        "direct-shell",
        "computed-shell",
        "ifeq",
        "non-tab-shell-assignment",
        "export-addopts",
        "export-target-addopts",
        "target-addopts",
        "double-colon",
        "target-variable",
        "forced-recipe",
    ],
)
def test_guard_refuses_unsupported_make_forms_with_a_fix(
    prefix: str, reason: str
) -> None:
    with pytest.raises(AssertionError, match=reason) as failure:
        judge.guard_makefile(prefix + _FULL_CHAIN, "fixture.mk")
    assert "Fix:" in str(failure.value)
    assert "fixture.mk" in str(failure.value)


@pytest.mark.parametrize(
    "args",
    [
        "tests/integration",
        "--collect-only",
        "$$FLAGS",
        '-xm "not slow"',
        "--desel=tests/test_sample.py::test_slow",
        "--unknown",
        "--durations nope",
        "--durations 0",
        "--durations $$OTHER",
        "--durations $(printf 10)",
    ],
    ids=[
        "positional",
        "collect-only",
        "shell-flags",
        "combined-short",
        "abbreviation",
        "unknown-option",
        "bad-duration",
        "zero-duration",
        "unknown-duration-variable",
        "duration-substitution",
    ],
)
def test_pytest_grammar_refuses_unknown_arguments_with_a_fix(
    tmp_path: Path, args: str
) -> None:
    (tmp_path / "Makefile").write_text(
        _FULL_CHAIN + f"\t$(PY) -m pytest --durations 10 {args}\n",
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="pytest|expansion") as failure:
        judge.assert_verify_keeps_slow(tmp_path)
    assert "Fix:" in str(failure.value)


@pytest.mark.parametrize(
    "line",
    ["\tPYTEST_ADDOPTS='-m slow'\n", "\texport PYTEST_ADDOPTS='-m slow'\n"],
    ids=["later-addopts", "later-export-addopts"],
)
def test_later_recipe_addopts_is_refused(tmp_path: Path, line: str) -> None:
    (tmp_path / "Makefile").write_text(_FULL_CHAIN + line, encoding="utf-8")
    with pytest.raises(AssertionError, match="PYTEST_ADDOPTS") as failure:
        judge.assert_verify_keeps_slow(tmp_path)
    assert "Fix:" in str(failure.value)


@pytest.mark.parametrize("test_hop", ["", " test"], ids=["missing-test", "empty-test"])
def test_unfiltered_pytest_cannot_hide_a_dropped_test_hop(
    tmp_path: Path, test_hop: str
) -> None:
    (tmp_path / "Makefile").write_text(
        f"verify:\n\t$(MAKE) other{test_hop}\n"
        "other:\n\t$(PY) -m pytest --durations 10\n"
        "test:\n\t@echo no tests\n",
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="test hop") as failure:
        judge.assert_verify_keeps_slow(tmp_path)
    assert "Fix:" in str(failure.value)


def test_file_prerequisite_is_refused_with_a_fix(tmp_path: Path) -> None:
    (tmp_path / "Makefile").write_text(
        _FULL_CHAIN.replace("test:\n", "test: input.txt\n"), encoding="utf-8"
    )
    (tmp_path / "input.txt").write_text("present\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="input.txt") as failure:
        judge.assert_verify_keeps_slow(tmp_path)
    assert "Fix:" in str(failure.value)


@pytest.mark.parametrize(
    "recipe",
    [
        "\tCOUNT=10; $(PY) -m pytest --durations 10\n",
        "\t@echo make\n\t$(PY) -m pytest --durations 10\n",
    ],
    ids=["first-recipe-assignment", "echo-make"],
)
def test_unambiguous_recipe_lines_are_accepted(tmp_path: Path, recipe: str) -> None:
    (tmp_path / "Makefile").write_text(
        "verify:\n\t$(MAKE) test\ntest:\n" + recipe, encoding="utf-8"
    )
    judge.assert_verify_keeps_slow(tmp_path)


@pytest.mark.parametrize(
    "prefix",
    [
        "sinclude missing.mk\n",
        "-include present.mk\n",
        "X := $(file >sentinel,unsafe)\n",
        "X := $(eval unsafe)\n",
        "X := $(guile unsafe)\n",
        "load unsafe.so\n",
        "define BAD\n$(call shell,printf harmless)\nendef\n",
        "define BAD\n$(shell printf harmless)\nendef\n",
        "define BAD\n$(call $(FN),printf harmless)\nendef\n",
        "Makefile:\n\t@touch Makefile\n",
        ".RECIPEPREFIX = >\n",
        "MAKEFLAGS = unsafe\n",
    ],
    ids=[
        "sinclude",
        "present-include",
        "file-function",
        "eval-function",
        "guile-function",
        "load-directive",
        "macro-builtin-call",
        "macro-shell",
        "macro-computed-call",
        "main-makefile-remake",
        "recipe-prefix",
        "makeflags",
    ],
)
def test_guard_refuses_the_parse_side_effect_class(tmp_path: Path, prefix: str) -> None:
    (tmp_path / "Makefile").write_text(prefix + _FULL_CHAIN, encoding="utf-8")
    (tmp_path / "present.mk").write_text("# inert\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="Fix:"):
        judge.read_rules(tmp_path)


@pytest.mark.parametrize(
    "recipe",
    [
        "\t$(PY) -m pytest --durations $$durations\n",
        "\t$$FLAGS $(PY) -m pytest --durations 10\n",
        "\t@echo pytest --durations 10\n",
    ],
    ids=["unbound-duration", "prefix-expansion", "echo-pytest"],
)
def test_only_a_known_pytest_invocation_counts(tmp_path: Path, recipe: str) -> None:
    (tmp_path / "Makefile").write_text(
        "verify:\n\t$(MAKE) test\ntest:\n" + recipe, encoding="utf-8"
    )
    with pytest.raises(AssertionError, match="pytest.*Fix:"):
        judge.assert_verify_keeps_slow(tmp_path)


def test_checked_macro_and_shared_test_prerequisite_are_accepted(
    tmp_path: Path,
) -> None:
    (tmp_path / "Makefile").write_text(
        "define FULL_PYTEST\n$(PY) -m pytest --durations $(1)\nendef\n"
        "verify:\n\t$(MAKE) other test\n"
        "other: suite\ntest: suite\nsuite:\n\t$(call FULL_PYTEST,7)\n",
        encoding="utf-8",
    )
    judge.assert_verify_keeps_slow(tmp_path)


@pytest.mark.parametrize(
    "prefix",
    [
        ".SECONDEXPANSION:\n.PHONY: $$(shell printf harmless)\n",
        "define MAKEFILES\nmissing.mk\nendef\n",
    ],
    ids=["secondary-expansion", "control-macro"],
)
def test_guard_refuses_special_expansion_contexts(tmp_path: Path, prefix: str) -> None:
    (tmp_path / "Makefile").write_text(prefix + _FULL_CHAIN, encoding="utf-8")
    with pytest.raises(AssertionError, match="Fix:"):
        judge.read_rules(tmp_path)


@pytest.mark.parametrize(
    "recipe",
    [
        "\t$(ENV) $(PY) -m pytest --durations 10\n",
        "\t$(PY) -m pytest --durations 10\n\texport PYTEST_$(A)='-m \"not slow\"'\n",
    ],
    ids=["computed-prefix", "computed-export-line"],
)
def test_expanded_recipe_refuses_computed_addopts(tmp_path: Path, recipe: str) -> None:
    (tmp_path / "Makefile").write_text(
        "A = ADDOPTS\n"
        "ENV = PYTEST_$(A)='-m \"not slow\"'\n"
        "verify:\n\t$(MAKE) test\ntest:\n" + recipe,
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="PYTEST_ADDOPTS") as failure:
        judge.assert_verify_keeps_slow(tmp_path)
    message = str(failure.value)
    assert "Fix:" in message
    assert str(tmp_path / "Makefile") in message
    assert "test:" in message


@pytest.mark.parametrize("name", ["PYTEST_PLUGINS", "PYTHONHOME", "OTHER"])
def test_pytest_environment_refuses_unlisted_assignments(name: str) -> None:
    command = f"{name}=literal pytest --durations 10"
    with pytest.raises(AssertionError, match="pytest.*Fix:") as failure:
        judge.assert_full_pytests(command)
    assert command in str(failure.value)


def test_pytest_environment_accepts_pythonpath() -> None:
    assert judge.assert_full_pytests("PYTHONPATH=src:. pytest --durations 10") == 1


@pytest.mark.parametrize("option", ["-n=3", "-n=auto", "-p=no:cacheprovider"])
def test_short_pytest_options_refuse_equals(option: str) -> None:
    command = f"pytest --durations 10 {option}"
    with pytest.raises(AssertionError, match="pytest.*Fix:") as failure:
        judge.assert_full_pytests(command)
    assert option in str(failure.value)


@pytest.mark.parametrize(
    "args",
    [
        "--durations=10 --junitxml=report.xml -n 3 -p no:cacheprovider",
        "--durations 7 --junitxml report.xml -n auto --keel-full-gate",
    ],
)
def test_long_value_options_accept_equals_and_separate_values(args: str) -> None:
    assert judge.assert_full_pytests(f"pytest {args}") == 1


@pytest.mark.parametrize(
    ("text", "cause"),
    [
        ("define OUTER\ndefine INNER\nendef\nendef\n", "Nested make definition"),
        ("endef\n", "Unmatched endef"),
        ("define OPEN\nliteral\n", "Unclosed make definition"),
        ("define SHELL\n/bin/sh\nendef\n", "make control macro"),
        ("SHELL = /bin/sh\n", "make control variable"),
        (".NOTPARALLEL:\n", "make special rule"),
        ("not a rule\n", "make syntax"),
    ],
)
def test_guard_refusal_kinds_name_the_text_source(text: str, cause: str) -> None:
    with pytest.raises(AssertionError, match=cause) as failure:
        judge.guard_makefile(text, "fixture.mk")
    assert "fixture.mk" in str(failure.value)
    assert "Fix:" in str(failure.value)


@pytest.mark.parametrize(
    ("command", "cause"),
    [
        ("__keel_make__ test __keel_make__ later", "Ambiguous make hop"),
        ("wrapper __keel_make__ test", "make wrapper"),
        ("__keel_make__ MAKEFLAGS=x test", "make assignment"),
        ("__keel_make__ PYTEST_ADDOPTS=x test", "make assignment"),
        ("__keel_make__ EXTRA=$FLAGS test", "make assignment"),
        ("__keel_make__ test/path", "make goal"),
        ("__keel_make__", "Missing make goal"),
        ("__keel_make__ 'test", "shell quoting"),
    ],
)
def test_make_hop_refusal_kinds_name_the_command(command: str, cause: str) -> None:
    with pytest.raises(AssertionError, match=cause) as failure:
        judge.make_hop(command)
    assert repr(command) in str(failure.value)
    assert "Fix:" in str(failure.value)


def test_make_hop_accepts_wrapper_and_literal_assignments() -> None:
    assert judge.make_hop("python gate.py -- __keel_make__ test EXTRA=literal") == (
        ["test"],
        ["EXTRA=literal"],
    )
    assert judge.make_hop("echo make") == ([], [])


@pytest.mark.parametrize(
    ("text", "cause"),
    [
        ("test:\ntest:\n", "Duplicate target"),
        ("test: $(OTHER)\n", "variable prerequisites"),
        ("Makefile:\n", "makefile or probe remake"),
        ("__keel_slowtest_probe:\n", "makefile or probe remake"),
    ],
)
def test_rule_refusal_kinds_name_the_makefile(
    tmp_path: Path, text: str, cause: str
) -> None:
    path = tmp_path / "Makefile"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(AssertionError, match=cause) as failure:
        judge.read_rules(tmp_path)
    assert str(path) in str(failure.value)
    assert "Fix:" in str(failure.value)


def test_missing_makefile_names_the_input(tmp_path: Path) -> None:
    with pytest.raises(AssertionError, match="Missing Makefile") as failure:
        judge.read_rules(tmp_path)
    assert str(tmp_path / "Makefile") in str(failure.value)
    assert "Fix:" in str(failure.value)


@pytest.mark.parametrize(
    ("command", "cause", "source"),
    [
        ("python -m pytest --durations 10", "pytest interpreter", "python"),
        ("echo pytest --durations 10", "pytest invocation prefix", "echo"),
        ("pytest --unknown", "pytest argument", "--unknown"),
        ("pytest --durations 0", "pytest option value", "--durations=0"),
        (
            "pytest --durations 10 --durations 7",
            "Repeated pytest option",
            "--durations",
        ),
        ("pytest -n 2", "pytest loses --durations", "-n"),
        (
            "pytest --durations 10 --keel-full-gate=yes",
            "pytest option value",
            "--keel-full-gate=yes",
        ),
    ],
)
def test_pytest_refusal_kinds_name_the_input(
    command: str, cause: str, source: str
) -> None:
    with pytest.raises(AssertionError, match=cause) as failure:
        judge.assert_full_pytests(command)
    assert source in str(failure.value)
    assert "Fix:" in str(failure.value)


@pytest.mark.parametrize(
    ("text", "cause"),
    [
        ("test:\n\t$(MAKE) other\nother:\n", "Unsafe recursive dry run"),
        (
            "NEXT = __keel_make__ other\ntest:\n\t$(NEXT)\nother:\n",
            "Unsafe recursive dry run",
        ),
        ("PREFIX = +\ntest:\n\t$(PREFIX)echo inert\n", "Unsafe expanded forced recipe"),
        ("test:\n\t$(MAKE) $(NEXT)\n", "Unjudged recipe references"),
        ("test:\n\t$(error fixture error)\n", "Make recipe expansion failed"),
        (
            "test:\n\t$(info __keel_slowtest_probe_0:duplicate)echo inert\n",
            "Ambiguous make expansion output",
        ),
    ],
)
def test_leaf_refusal_kinds_name_the_input(
    tmp_path: Path, text: str, cause: str
) -> None:
    (tmp_path / "Makefile").write_text(text, encoding="utf-8")
    with pytest.raises(AssertionError, match=cause) as failure:
        judge.dry_run("test", root=tmp_path)
    assert any(source in str(failure.value) for source in ("test", "+echo inert"))
    assert "Fix:" in str(failure.value)
