"""
title: Makefile judge — derive full pytest invocations without executing recipes
summary: Guards Makefile syntax before expanding recipes as data and following recursive make hops; refuses unjudged make or pytest forms with the input, cause and fix.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402
import config_loader  # noqa: E402
from child_env import build_child_env  # noqa: E402

__all__ = [
    "assert_full_pytests",
    "assert_verify_keeps_slow",
    "dry_run",
    "guard_makefile",
    "make_hop",
    "read_rules",
]


def _timeout() -> float:
    return cast(
        float,
        config_loader.resolve(
            config_loader.read(str(_ROOT), "config/project.json"),
            [
                row
                for row in config_loader.KEYS
                if row.path == ("tests", "child_timeout_seconds")
            ],
            "config/project.json",
        )[("tests", "child_timeout_seconds")],
    )


# These functions only compute text or report diagnostics. Calls may name only
# declared uppercase macros whose bodies pass the same guard (GNU builtins are
# lowercase). Computed names, builtin calls and unknown expansions are refused
# before make runs, so no indirect path can reach shell/file/eval/guile.
_PURE_MAKE_FUNCTIONS = frozenset(
    [
        "if",
        "or",
        "and",
        "wildcard",
        "dir",
        "findstring",
        "firstword",
        "error",
        "info",
        "warning",
        "subst",
        "patsubst",
        "strip",
        "sort",
        "filter",
        "filter-out",
        "words",
        "word",
        "wordlist",
        "lastword",
        "notdir",
        "suffix",
        "basename",
        "addsuffix",
        "addprefix",
        "join",
        "origin",
        "flavor",
        "abspath",
        "realpath",
    ]
)
_PYTEST_ARGUMENTS = {
    "--keel-full-gate": None,
    "-p": r"no:cacheprovider",
    "-n": r"auto|[0-9]+",
    "--durations": r"[1-9][0-9]*|\$durations|\$\{durations\}",
    "--junitxml": r"[A-Za-z0-9_./-]+",
}
_PYTEST_ENVIRONMENT = frozenset({"PYTHONPATH"})
_MAKE_CONTROL_VARIABLES = frozenset(
    {"MAKE", "MAKEFILES", "MAKEFLAGS", "GNUMAKEFLAGS", "SHELL"}
)


def _require(condition: object, cause: str, source: object, fix: str) -> None:
    assert condition, f"{cause} on {source!r}. Fix: {fix}."


def _guard_expansions(text: str, source: str, macros: set[str]) -> None:
    for match in re.finditer(r"\$(\$|[({]|.)", text):
        if match[1] not in ("(", "{"):
            continue
        tail = text[match.end() :]
        head = re.match(r"([A-Za-z0-9_][A-Za-z0-9_-]*)([)}]|[ \t,])", tail)
        call = re.match(r"call[ \t]+([A-Z_][A-Z0-9_]*)[ \t]*[,)}]", tail)
        safe = head and (
            head[2] in ")}"
            or head[1] in _PURE_MAKE_FUNCTIONS
            or (head[1] == "call" and call and call[1] in macros)
        )
        _require(
            safe,
            "Unjudged make expansion",
            source,
            "use static variable references and _PURE_MAKE_FUNCTIONS only",
        )


def guard_makefile(text: str, source: str | Path) -> None:
    """Refuse make syntax whose expansion or execution cannot be judged."""
    # Only static assignments and explicit single-colon rules are modelled.
    # Includes are refused even when absent: make may remake them under -q/-n.
    # Match each logical line separately; whitespace must never eat a newline.
    logical = re.sub(r"\\\n[ \t]*", " ", text)
    macros = set(
        re.findall(r"^define ([A-Z_][A-Z0-9_]*)[ \t]*$", logical, re.MULTILINE)
    )
    in_define = False
    for number, line in enumerate(logical.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        where = f"{source}:{number}: {line}"
        _guard_expansions(line, where, macros)
        _require(
            not re.search(r"\bPYTEST_ADDOPTS\b", line),
            "Unjudged PYTEST_ADDOPTS",
            where,
            "remove PYTEST_ADDOPTS and pass only _PYTEST_ARGUMENTS explicitly",
        )
        definition = re.fullmatch(r"define ([A-Z_][A-Z0-9_]*)[ \t]*", line)
        if definition:
            _require(not in_define, "Nested make definition", where, "use flat macros")
            _require(
                definition[1] not in _MAKE_CONTROL_VARIABLES,
                "Unjudged make control macro",
                where,
                "use ordinary data macros without changing make execution",
            )
            in_define = True
            continue
        if line == "endef":
            _require(in_define, "Unmatched endef", where, "pair define and endef")
            in_define = False
            continue
        if in_define:
            continue
        if line.startswith("\t"):
            _require(
                not re.match(r"[ \t@-]*\+", line),
                "Unjudged forced recipe",
                where,
                "remove the + recipe prefix",
            )
            continue
        stripped = line.split("#", 1)[0].strip()
        _require(
            not re.match(r"(?:-?include|sinclude)\b", stripped),
            "Unjudged include remake",
            where,
            "inline the included makefile",
        )
        _require(
            not re.match(r"(?:ifdef|ifndef|ifeq|ifneq|else|endif)\b", stripped),
            "Unjudged conditional",
            where,
            "use unconditional explicit rules",
        )
        _require(
            "!=" not in line,
            "Unjudged shell assignment",
            where,
            "replace != with an inert literal assignment",
        )
        assignment = re.match(
            r"(?:(?:export|override|private) +)*([\w.-]+)[ \t]*[:?+]?=", stripped
        )
        if assignment:
            _require(
                assignment[1] not in _MAKE_CONTROL_VARIABLES
                and (
                    not assignment[1].startswith(".")
                    or assignment[1] == ".DEFAULT_GOAL"
                ),
                "Unjudged make control variable",
                where,
                "use ordinary data variables without changing make execution",
            )
            continue
        _require(
            not re.match(r"[^:]+::", stripped),
            "Unjudged double-colon rule",
            where,
            "merge the recipes into one single-colon rule",
        )
        _require(
            not re.match(
                r"[^:]+:[ \t]*(?:(?:export|override|private) +)*[\w.-]+[ \t]*[:?+]?=",
                stripped,
            ),
            "Unjudged target-specific variable",
            where,
            "pass ordinary assignments explicitly through the recursive make hop",
        )
        _require(
            re.fullmatch(r"[A-Za-z0-9_. -]+:[^;]*", stripped)
            and not stripped.startswith(("define ", "load ")),
            "Unjudged make syntax",
            where,
            "use explicit single-colon targets and separate tab recipes",
        )
        targets, prerequisites = stripped.split(":", 1)
        if any(target.startswith(".") for target in targets.split()):
            _require(
                targets == ".PHONY"
                and re.fullmatch(r"[A-Za-z0-9_. \t-]*", prerequisites),
                "Unjudged make special rule",
                where,
                "use only .PHONY with literal target names",
            )
    _require(
        not in_define, "Unclosed make definition", source, "close the macro with endef"
    )


def read_rules(root: Path) -> dict[str, cs.MakeRule]:
    """Return guarded explicit rules from root/Makefile or fail with a fix."""
    path = root / "Makefile"
    _require(path.is_file(), "Missing Makefile", path, "supply a readable Makefile")
    text = path.read_text(encoding="utf-8")
    guard_makefile(text, path)
    rules: dict[str, cs.MakeRule] = {}
    parse_rules = cast(Callable[[str], list[cs.MakeRule]], cs.make_target_rules)
    for rule in parse_rules(text):
        _require(
            rule.target not in rules,
            "Duplicate target",
            f"{path}: {rule.target}",
            "merge the target into one rule",
        )
        recipe_only = parse_rules(
            "probe:\n" + "".join("\t" + command + "\n" for command in rule.recipe)
        )[0]
        _require(
            rule.unresolved == recipe_only.unresolved,
            "Unjudged variable prerequisites",
            f"{path}: {rule.target}",
            "name prerequisite targets literally",
        )
        _require(
            rule.target not in {"Makefile", "__keel_slowtest_probe", "-"},
            "Unjudged makefile or probe remake",
            f"{path}: {rule.target}",
            "remove rules that remake makefiles or reserved probe targets",
        )
        rules[rule.target] = rule
    return rules


def _rule(rules: Mapping[str, cs.MakeRule], name: str, root: Path) -> cs.MakeRule:
    _require(
        name in rules,
        "Unjudged file prerequisite or missing target",
        f"{root}/Makefile: {name}",
        "declare an explicit target instead of a file or implicit prerequisite",
    )
    return rules[name]


def _expanded_recipes(
    root: Path, rule: cs.MakeRule, assignments: tuple[str, ...]
) -> list[str]:
    # The selected goal has no prerequisites and an empty recipe. -q never
    # reaches an original recipe, even one containing $(MAKE). info expands
    # recipe text as data after loading the real variables; it runs no shell.
    probe = "__keel_slowtest_probe"
    source = [f"{probe}: ;"]
    for i, command in enumerate(rule.recipe):
        source.extend(
            [
                f"define {probe}_{i}",
                command.replace("$@", rule.target),
                "endef",
                f"$(info {probe}_{i}:$({probe}_{i}))",
            ]
        )
    proc = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "-rR",
            "-q",
            "-o",
            "Makefile",
            "-o",
            "-",
            "-f",
            "Makefile",
            "-f",
            "-",
            probe,
            "PY=" + sys.executable,
            "MAKE=__keel_make__",
            *assignments,
        ],
        input="\n".join(source) + "\n",
        cwd=root,
        env=build_child_env(),
        capture_output=True,
        text=True,
        timeout=_timeout(),
    )
    _require(
        proc.returncode in (0, 1) and not proc.stderr,
        "Make recipe expansion failed",
        f"{root}/Makefile: {rule.target}: {proc.stdout + proc.stderr}",
        "repair the make syntax and keep expansion free of side effects",
    )
    lines = proc.stdout.splitlines()
    commands = []
    for i in range(len(rule.recipe)):
        prefix = f"{probe}_{i}:"
        matches = [line for line in lines if line.startswith(prefix)]
        _require(
            len(matches) == 1,
            "Ambiguous make expansion output",
            f"{root}/Makefile: {rule.target}: {prefix}",
            "remove multiline or diagnostic-producing recipe expansions",
        )
        (line,) = matches
        command = line.removeprefix(prefix)
        _require(
            not re.search(r"\bPYTEST_ADDOPTS\b", command),
            "Unjudged expanded PYTEST_ADDOPTS",
            f"{root}/Makefile: {rule.target}: {command}",
            "remove PYTEST_ADDOPTS and pass only _PYTEST_ARGUMENTS explicitly",
        )
        commands.append(command)
    return commands


def _shell_words(command: str) -> list[str]:
    try:
        lexer = shlex.shlex(
            command.replace("\\\n", ""), posix=True, punctuation_chars=";&|()\n"
        )
        lexer.whitespace = " \t\r"
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError as error:
        raise AssertionError(
            f"Unjudged shell quoting on {command!r}. Fix: use balanced simple quoting."
        ) from error


def make_hop(command: str) -> tuple[list[str], list[str]]:
    """Return literal goals and assignments from one expanded make command."""
    words = _shell_words(command)
    calls = [
        i
        for i, word in enumerate(words)
        if word == "__keel_make__"
        or (word == "make" and (i == 0 or words[i - 1] in ("--", ";", "&&")))
    ]
    if not calls:
        return [], []
    _require(
        len(calls) == 1, "Ambiguous make hop", command, "use one make call per line"
    )
    (start,) = calls
    _require(
        start == 0 or words[start - 1] == "--",
        "Unjudged make wrapper",
        command,
        "invoke make directly or after the gate wrapper's --",
    )
    goals, assignments = [], []
    for word in words[start + 1 :]:
        if re.match(r"^[A-Za-z_]\w*=", word):
            _require(
                word.split("=", 1)[0]
                not in _MAKE_CONTROL_VARIABLES | {"PYTEST_ADDOPTS"}
                and "$" not in word,
                "Unjudged make assignment",
                command,
                "pass literal data assignments without make controls or PYTEST_ADDOPTS",
            )
            assignments.append(word)
        else:
            _require(
                re.fullmatch(r"[A-Za-z0-9_-]+", word),
                "Unjudged make goal",
                command,
                "name each target literally without shell operators or flags",
            )
            goals.append(word)
    _require(goals, "Missing make goal", command, "name an explicit target")
    return goals, assignments


def dry_run(
    target: str, *, root: Path | None = None, assignments: tuple[str, ...] = ()
) -> str:
    """Return a guarded leaf dry run without executing its recipes."""
    root = _ROOT if root is None else root
    rules = read_rules(root)
    stack, seen = [target], set()
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        rule = _rule(rules, name, root)
        _require(
            not rule.unresolved,
            "Unjudged recipe references",
            rule,
            "use literal prerequisite targets and explicit make hops",
        )
        # GNU make executes a line with a literal MAKE reference under -n
        # even when that reference is in a branch that expands to nothing.
        _require(
            not any(re.search(r"\$[({]MAKE[)}]", command) for command in rule.recipe),
            "Unsafe recursive dry run",
            rule,
            "follow the make hop as data instead of dry-running it",
        )
        stack.extend(rule.prereqs)
        for command in _expanded_recipes(root, rule, assignments):
            _require(
                not re.match(r"[ \t@-]*\+", command),
                "Unsafe expanded forced recipe",
                command,
                "remove the expanded + prefix before dry-running the leaf",
            )
            goals, _ = make_hop(command)
            _require(
                not goals,
                "Unsafe recursive dry run",
                f"{name}: {command}",
                "follow the make hop as data instead of dry-running it",
            )
    proc = subprocess.run(
        [
            "make",
            "-rR",
            "-f",
            "Makefile",
            "-n",
            target,
            "PY=" + sys.executable,
            *assignments,
        ],
        cwd=root,
        env=build_child_env(),
        capture_output=True,
        text=True,
        timeout=_timeout(),
    )
    _require(
        proc.returncode == 0,
        "Make leaf dry run failed",
        f"{root}/Makefile: {target}: {proc.stdout + proc.stderr}",
        "repair the leaf rule and its explicit prerequisites",
    )
    return proc.stdout


def assert_verify_keeps_slow(root: Path) -> None:
    """Prove verify reaches full pytest commands through its test hop."""
    rules = read_rules(root)
    stack: list[tuple[str, tuple[str, ...], bool]] = [("verify", (), False)]
    seen: set[tuple[str, tuple[str, ...], bool]] = set()
    count, test_count = 0, 0
    while stack:
        target, assignments, through_test = stack.pop()
        through_test = through_test or target == "test"
        key = (target, assignments, through_test)
        if key in seen:
            continue
        seen.add(key)
        rule = _rule(rules, target, root)
        stack.extend((name, assignments, through_test) for name in rule.prereqs)
        commands = _expanded_recipes(root, rule, assignments)
        recursive = False
        for command in commands:
            goals, overrides = make_hop(command)
            recursive = recursive or bool(goals)
            inherited = dict(item.split("=", 1) for item in assignments)
            for override in overrides:
                name, value = override.split("=", 1)
                inherited[name] = value
            child = tuple(f"{key}={value}" for key, value in sorted(inherited.items()))
            stack.extend((name, child, through_test) for name in goals)
        if any(
            word == "pytest" or word.endswith("/pytest")
            for command in commands
            for word in _shell_words(command)
        ):
            # A recipe may run pytest and then recurse. Never dry-run such a
            # target; its expanded commands are already available as data.
            output = (
                "\n".join(commands)
                if recursive
                else dry_run(target, root=root, assignments=assignments)
            )
            reached = assert_full_pytests(output)
            count += reached
            if through_test:
                test_count += reached
    _require(
        count,
        "verify reaches zero pytest commands",
        root,
        "restore a full pytest invocation with --durations",
    )
    _require(
        test_count,
        "verify's test hop reaches zero full pytest commands",
        root,
        "restore the test hop and its full pytest invocation",
    )


def assert_full_pytests(command: str) -> int:
    """Judge executable pytest invocations and return their count."""
    words = _shell_words(command)
    count = 0
    for i, word in enumerate(words):
        if word != "pytest" and not word.endswith("/pytest"):
            continue
        # Only an executable invocation counts; an echo mentioning pytest
        # cannot prove that the test hop runs any tests.
        start = i
        if i >= 2 and words[i - 1] == "-m":
            start = i - 2
            _require(
                words[start] == sys.executable,
                "Unjudged pytest interpreter",
                command,
                "invoke pytest through $(PY) -m pytest",
            )
        boundary = start
        while boundary and not all(char in ";&|()\n" for char in words[boundary - 1]):
            boundary -= 1
        _require(
            all(
                re.fullmatch(r"[A-Za-z_]\w*=[^$`]*", value)
                and value.split("=", 1)[0] in _PYTEST_ENVIRONMENT
                for value in words[boundary:start]
            ),
            "Unjudged pytest invocation prefix",
            command,
            "use a direct pytest invocation with literal _PYTEST_ENVIRONMENT assignments",
        )
        count += 1
        args = []
        for arg in words[i + 1 :]:
            if arg and all(char in ";&|()\n" for char in arg):
                break
            args.append(arg)
        options, position = set(), 0
        while position < len(args):
            option, equals, value = args[position].partition("=")
            _require(
                option in _PYTEST_ARGUMENTS,
                "Unjudged pytest argument",
                args[position],
                "use only _PYTEST_ARGUMENTS without test selections",
            )
            grammar = _PYTEST_ARGUMENTS[option]
            valid: bool | re.Match[str] | None
            if grammar is None:
                valid = not equals
            else:
                if not equals:
                    position += 1
                    value = args[position] if position < len(args) else ""
                valid = re.fullmatch(grammar, value) and (
                    not equals or option.startswith("--")
                )
                if option == "--durations" and "$" in value:
                    binding = f"durations=$({sys.executable} scripts/config_get.py tests.durations)"
                    valid = (
                        valid
                        and boundary >= 2
                        and words[boundary - 2 : boundary] == [binding, "&&"]
                    )
            _require(
                valid,
                "Unjudged pytest option value",
                f"{option}={value}",
                "use the literal value grammar in _PYTEST_ARGUMENTS",
            )
            _require(
                option not in options,
                "Repeated pytest option",
                option,
                "pass each allowlisted option once",
            )
            options.add(option)
            position += 1
        _require(
            "--durations" in options,
            "pytest loses --durations",
            args,
            "pass --durations with a positive count from config",
        )
    return count
