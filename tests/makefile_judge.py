"""
title: Makefile judge — derive full pytest invocations without executing recipes
summary: Guards Makefile syntax before expanding recipes as data and following recursive make hops; refuses unjudged make or pytest forms with the input, cause and fix.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
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
# pytest's reference/environment-variables and how-to/tmp_path document these
# inputs: https://docs.pytest.org/en/stable/reference/reference.html#environment-variables
# CI/BUILD_NUMBER also select CI output. PYTEST_CURRENT_TEST is output, not input.
# xdist reads PYTEST_XDIST_AUTO_NUM_WORKERS for -n auto. TERM and COLUMNS only
# affect terminal presentation; PYTHONWARNINGS is Python's warning policy, not
# a pytest option/plugin/worker input. These three are deliberately left out.
_PYTEST_INPUT_VARIABLES = (
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
)
_MAKE_CONTROL_VARIABLES = frozenset(
    {"MAKE", "MAKEFILES", "MAKEFLAGS", "GNUMAKEFLAGS", "SHELL"}
)


def _require(condition: object, cause: str, source: object, fix: str) -> None:
    assert condition, f"{cause} on {source!r}. Fix: {fix}."


def _guard_pytest_environment(
    text: str, source: str, *, check_references: bool = True
) -> None:
    # Refuse assignments/exports conservatively: their state can cross
    # statement, recipe and recursive-make boundaries without a local prefix.
    # References also import caller state that our empty expansion env loses.
    # Literal help prose may name an input; @echo naming it with $$ is refused
    # because even a quoted reference imports state our empty env cannot judge.
    for name in _PYTEST_INPUT_VARIABLES:
        _require(
            not re.search(rf"\b{name}[ \t]*[:?+]?=", text)
            and not (
                check_references
                and re.search(rf"\$\$?(?:\({name}\)|\{{{name}\}}|{name}\b)", text)
            )
            and not re.search(
                rf"\b(?:export|declare[ \t]+-x)\b[^;\n&|]*\b{name}\b", text
            ),
            f"Unjudged pytest environment {name}",
            source,
            f"remove {name} and pass only _PYTEST_ARGUMENTS explicitly",
        )


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
        lazy = re.match(r"^([\w.-]+)[ \t]*\??=", line)
        _guard_pytest_environment(line, where, check_references=not lazy)
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
    _guard_recipe_references(root, rule)
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
        _guard_pytest_environment(command, f"{root}/Makefile: {rule.target}: {command}")
        _guard_shell_environment(command, f"{root}/Makefile: {rule.target}: {command}")
        commands.append(command)
    return commands


def _guard_recipe_references(root: Path, rule: cs.MakeRule) -> None:
    # Unexported recursive data is inert until a reached recipe uses it. Follow
    # raw aliases/macros before make can erase caller values under an empty env.
    # Keep every definition so reassignment cannot hide a caller reference.
    text = (root / "Makefile").read_text(encoding="utf-8")
    deferred: dict[str, list[str]] = {}
    macro = ""
    for line in re.sub(r"\\\n[ \t]*", " ", text).splitlines():
        definition = re.fullmatch(r"define ([A-Z_][A-Z0-9_]*)[ \t]*", line)
        if definition:
            macro = definition[1]
        elif line == "endef":
            macro = ""
        elif macro:
            deferred.setdefault(macro, []).append(line)
        else:
            data = re.match(r"^([\w.-]+)[ \t]*\??=[ \t]*(.*)$", line)
            if data:
                deferred.setdefault(data[1], []).append(data[2])
    pending, seen = list(rule.recipe), set()
    while pending:
        value = pending.pop()
        _guard_pytest_environment(value, f"{root}/Makefile: {rule.target}: {value}")
        names = re.findall(r"\$[({](?:call[ \t]+)?([\w.-]+)(?=[)}, \t])", value)
        for name in names:
            if name in deferred and name not in seen:
                seen.add(name)
                pending.extend(deferred[name])


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


@dataclass(frozen=True)
class _ShellToken:
    value: str
    raw: str
    operator: bool = False
    stdin: str | None = None
    descriptor: bool = False


def _shell_tokens(command: str) -> list[_ShellToken]:
    # Retain quoting on operators: find's escaped semicolon and quoted script
    # punctuation are argv data, whereas a shell separator starts a statement.
    tokens = []
    position = 0
    operators = re.compile(r"&&|\|\||;;|<<<|<<-?|>>|>&|<&|<>|[;&|()<>\n]")
    while position < len(command):
        if command[position] in " \t\r":
            position += 1
            continue
        operator = operators.match(command, position)
        if operator:
            raw = operator[0]
            tokens.append(_ShellToken(raw, raw, operator=True))
            position = operator.end()
            continue
        start, quote, depth = position, "", 0
        while position < len(command):
            char = command[position]
            if char == "\\" and quote != "'":
                position += 2
                continue
            if char in "'\"`" and (not quote or quote == char):
                quote = "" if quote else char
            elif quote != "'" and command.startswith("$(", position):
                depth += 1
                position += 2
                continue
            elif depth and char == ")":
                depth -= 1
            elif (
                not quote
                and not depth
                and (char.isspace() or operators.match(command, position))
            ):
                break
            position += 1
        raw = command[start:position]
        try:
            value = " ".join(shlex.split(raw))
        except ValueError as error:
            raise AssertionError(
                f"Unjudged shell quoting on {command!r}. Fix: use balanced simple quoting."
            ) from error
        stdin = None
        if len(tokens) and tokens[-1].value in {"<<", "<<-"}:
            newline = command.find("\n", position)
            terminator = (
                re.search(
                    r"^[\t]*" + re.escape(value) + r"[\r]?(?:\n|$)",
                    command[newline + 1 :],
                    re.MULTILINE,
                )
                if newline >= 0
                else None
            )
            _require(
                terminator,
                "Cannot judge stdin environment",
                command,
                "close the literal heredoc",
            )
            assert terminator is not None
            stdin = command[newline + 1 : newline + 1 + terminator.start()]
            if tokens[-1].value == "<<-":
                stdin = re.sub(r"^\t+", "", stdin, flags=re.MULTILINE)
            command = command[: newline + 1] + command[newline + 1 + terminator.end() :]
        tokens.append(
            _ShellToken(
                value,
                raw,
                stdin=stdin,
                descriptor=value.isdigit()
                and position < len(command)
                and command[position] in "<>",
            )
        )
    return tokens


# An option's operand is data even when it looks like an executable. Attached
# operands and --option=value consume no following word. Unknown options fail
# closed rather than guessing whether they conceal a command.
_WRAPPER_OPTIONS = {
    "env": (
        {"-u", "--unset", "-C", "--chdir"},
        {"-i", "--ignore-environment", "-0", "--null"},
    ),
    "command": (set(), {"-p", "-v", "-V"}),
    "builtin": (set(), set()),
    "exec": ({"-a"}, {"-c", "-l"}),
    "nice": ({"-n", "--adjustment"}, set()),
    "ionice": (
        {
            "-c",
            "--class",
            "-n",
            "--classdata",
            "-p",
            "--pid",
            "-P",
            "--pgid",
            "-u",
            "--uid",
        },
        {"-t", "--ignore"},
    ),
    "timeout": (
        {"-s", "--signal", "-k", "--kill-after"},
        {"--foreground", "--preserve-status", "-v", "--verbose"},
    ),
    "nohup": (set(), set()),
    "setsid": (set(), {"-c", "--ctty", "-f", "--fork", "-w", "--wait"}),
    "stdbuf": ({"-i", "--input", "-o", "--output", "-e", "--error"}, set()),
    "xargs": (
        {
            "-a",
            "--arg-file",
            "-d",
            "--delimiter",
            "-E",
            "-I",
            "-L",
            "--max-lines",
            "-n",
            "--max-args",
            "-P",
            "--max-procs",
            "--process-slot-var",
            "-s",
            "--max-chars",
        },
        {
            "-0",
            "--null",
            "-r",
            "--no-run-if-empty",
            "-t",
            "--verbose",
            "-p",
            "--interactive",
            "-x",
            "--exit",
        },
    ),
    "time": (
        {"-f", "--format", "-o", "--output"},
        {"-p", "--portability", "-a", "--append", "-v", "--verbose"},
    ),
}


def _substitution_texts(raw: str) -> Iterator[str]:
    if raw.startswith("'") and raw.endswith("'"):
        return
    for match in re.finditer(r"\$\((.*)\)|`([^`]*)`", raw):
        yield match[1] or match[2]


def _printf_escapes(text: str, source: str) -> str:
    escapes = {
        "a": "\a",
        "b": "\b",
        "f": "\f",
        "n": "\n",
        "r": "\r",
        "t": "\t",
        "v": "\v",
        "\\": "\\",
    }
    result = []
    for match in re.finditer(
        r"\\(?:0[0-7]{1,3}|[0-7]{1,3}|x[0-9A-Fa-f]{1,2}|.|$)|[^\\]+", text
    ):
        piece = match[0]
        if not piece.startswith("\\"):
            result.append(piece)
            continue
        code = piece[1:]
        _require(
            code in escapes or re.fullmatch(r"0?[0-7]{1,3}|x[0-9A-Fa-f]{1,2}", code),
            "Cannot judge encoded stdin environment",
            source,
            "use literal script text or supported printf escapes",
        )
        if code in escapes:
            result.append(escapes[code])
        else:
            result.append(
                chr(int(code[1:], 16) if code.startswith("x") else int(code, 8))
            )
    return "".join(result)


def _printed_script(entry: _ShellCommand, source: str) -> str:
    arguments = list(entry.arguments)
    if entry.word.rsplit("/", 1)[-1] == "echo":
        decode = True
        while arguments and arguments[0] in {"-n", "-e", "-E"}:
            option = arguments.pop(0)
            if option in {"-e", "-E"}:
                decode = option == "-e"
        text = " ".join(arguments)
        return _printf_escapes(text, source) if decode else text
    _require(
        arguments,
        "Cannot judge stdin environment",
        source,
        "print a literal shell script",
    )
    format_string, *values = arguments
    pieces = re.findall(r"%[%sb]|[^%]+", format_string)
    _require(
        "".join(pieces) == format_string,
        "Cannot judge stdin environment",
        source,
        "use literal printf %s or %b script input",
    )
    result = []
    position = 0
    while True:
        for piece in pieces:
            if piece in {"%s", "%b"}:
                value = values[position] if position < len(values) else ""
                position += 1
                result.append(
                    _printf_escapes(value, source) if piece == "%b" else value
                )
            else:
                result.append("%" if piece == "%%" else _printf_escapes(piece, source))
        if position >= len(values) or not any(
            piece in {"%s", "%b"} for piece in pieces
        ):
            return "".join(result)


def _after_options(words: list[str], start: int, wrapper: str, source: str) -> int:
    operands, flags = _WRAPPER_OPTIONS[wrapper]
    while start < len(words) and words[start].startswith("-"):
        option = words[start]
        start += 1
        if option == "--":
            break
        if option in operands:
            _require(
                start < len(words),
                "Missing wrapper option operand",
                source,
                "supply a literal operand",
            )
            _require(
                not re.search(r"[$`]", words[start]),
                "Cannot judge computed wrapper environment",
                source,
                "write wrapper operands literally so splitting cannot choose the executable",
            )
            start += 1
            continue
        attached = any(
            option.startswith(name + "=")
            if name.startswith("--")
            else option.startswith(name) and len(option) > len(name)
            for name in operands
        )
        _require(
            option in flags
            or attached
            or (
                option.startswith("-")
                and not option.startswith("--")
                and all("-" + char in flags for char in option[1:])
            )
            or (wrapper == "nice" and re.fullmatch(r"-\d+", option)),
            "Cannot judge wrapper environment",
            source,
            "use explicit supported wrapper options and literal operands",
        )
    return start


@dataclass(frozen=True)
class _ShellCommand:
    word: str
    arguments: tuple[str, ...]
    prefix: tuple[str, ...] = ()
    before: tuple[str, ...] = ()
    wrapped: bool = False
    script: str | None = None
    redirected: bool = False
    compound: bool = False


def _command_words(command: str, source: str | None = None) -> Iterator[_ShellCommand]:
    # Literal environment names require one command-position rule for every
    # guard: follow argv runners, time, compound bodies and shell input strings;
    # refuse computed executables because their environment effects are unknown.
    source = command if source is None else source
    tokens = _shell_tokens(command.replace("\\\n", "").lstrip("@-"))
    position, boundary = 0, 0
    producer: _ShellCommand | None = None
    while position < len(tokens):
        token = tokens[position]
        if (
            token.operator
            and token.value in {";", ";;", "&", "&&", "|", "||", "(", ")", "\n"}
        ) or token.value in {
            "{",
            "}",
            "if",
            "then",
            "elif",
            "else",
            "while",
            "until",
            "do",
            "done",
            "fi",
            "!",
        }:
            position += 1
            boundary = position
            continue
        if token.value == "function":
            position += 2
            boundary = position
            continue
        if position + 1 < len(tokens) and tokens[position + 1].value == "(":
            position += 1
            continue
        if re.match(r"^[A-Za-z_]\w*=", token.value):
            for substitution_text in _substitution_texts(token.raw):
                yield from _command_words(substitution_text, source)
            position += 1
            continue
        end = position
        while end < len(tokens) and not (
            tokens[end].operator
            and tokens[end].value in {";", ";;", "&", "&&", "|", "||", "(", ")", "\n"}
        ):
            end += 1
        # Redirections may precede the executable or appear between its args.
        # Their descriptors and operands never occupy command position.
        argv = []
        script_input: str | None = None
        cursor = position
        while cursor < end:
            item = tokens[cursor]
            if item.descriptor:
                cursor += 1
                continue
            if item.operator:
                _require(
                    cursor + 1 < end,
                    "Unjudged shell redirection",
                    source,
                    "supply literal input",
                )
                operand = tokens[cursor + 1]
                if item.value == "<<<":
                    script_input = operand.value
                elif item.value in {"<<", "<<-"}:
                    script_input = operand.stdin
                cursor += 2
                continue
            argv.append(item)
            cursor += 1
        words = [item.value for item in argv]
        # Substitutions execute in arguments too, independently of argv runners.
        for item in argv:
            for substitution_text in _substitution_texts(item.raw):
                yield from _command_words(substitution_text, source)
        index = 0
        wrapped = False
        prefix = tuple(item.value for item in tokens[boundary:position])
        while index < len(words) and re.match(r"^[A-Za-z_]\w*=", words[index]):
            prefix += (words[index],)
            index += 1
        while index < len(words):
            word = words[index]
            _require(
                not re.search(r"[$`*?]|\[[^]]+\]", word),
                "Cannot judge computed command environment for pytest",
                source,
                "write the command word literally",
            )
            name = word.rsplit("/", 1)[-1]
            arguments = words[index + 1 :]
            script: str | None = None
            if name.endswith("sh") or re.fullmatch(r"ksh[0-9]+", name):
                offset = 0
                reads_stdin = False
                while offset < len(arguments) and arguments[offset].startswith(
                    ("-", "+")
                ):
                    option = arguments[offset]
                    offset += 1
                    if option in {"--", "-"}:
                        break
                    if option in {"-o", "+o", "-O", "+O"}:
                        offset += 1
                        continue
                    reads_stdin = reads_stdin or bool(
                        re.fullmatch(r"-[A-Za-z]*s[A-Za-z]*", option)
                    )
                    if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", option):
                        if arguments[offset : offset + 1] == ["--"]:
                            offset += 1
                        _require(
                            offset < len(arguments),
                            "Cannot judge shell string environment",
                            source,
                            "supply a literal shell script",
                        )
                        script = arguments[offset]
                        break
                if script is None and (
                    reads_stdin
                    or offset == len(arguments)
                    or arguments[offset:] == ["-"]
                ):
                    script = script_input
                    if position and tokens[position - 1].value == "|":
                        _require(
                            producer is not None
                            and producer.word.rsplit("/", 1)[-1] in {"echo", "printf"},
                            "Cannot judge stdin environment",
                            source,
                            "pipe a literal script from echo or printf",
                        )
                        assert producer is not None
                        script = _printed_script(producer, source)
                    _require(
                        script is not None,
                        "Cannot judge stdin environment",
                        source,
                        "supply a literal shell script",
                    )
            entry = _ShellCommand(
                word,
                tuple(arguments),
                prefix,
                tuple(item.value for item in tokens[:boundary]),
                wrapped,
                script,
                redirected=any(item.operator for item in tokens[position:end]),
                compound=bool(boundary or end < len(tokens)),
            )
            yield entry
            if script is not None:
                yield from _command_words(script, source)
            if name in _WRAPPER_OPTIONS:
                next_index = _after_options(words, index + 1, name, source)
                if name == "command" and any(
                    re.fullmatch(r"-[pVv]*[Vv][pVv]*", argument)
                    for argument in words[index + 1 : next_index]
                ):
                    break
                index = next_index
                if name == "timeout":
                    _require(
                        index < len(words) and not re.search(r"[$`]", words[index]),
                        "Cannot judge computed wrapper environment",
                        source,
                        "write the timeout duration literally",
                    )
                    index += 1
                if name == "xargs":
                    replacement = None
                    for offset in range(1, index):
                        option = words[offset]
                        if option == "-I" and offset + 1 < index:
                            replacement = words[offset + 1]
                        elif option.startswith("-I"):
                            replacement = option[2:]
                    if replacement is None:
                        words.append("$xargs_input")
                    else:
                        words[index:] = [
                            value.replace(replacement, "$xargs_input")
                            for value in words[index:]
                        ]
                if name in {"env", "time"}:
                    while index < len(words) and "=" in words[index]:
                        if name == "time":
                            prefix += (words[index],)
                        index += 1
                wrapped = True
                continue
            if name == "find":
                for offset, argument in enumerate(arguments):
                    if argument in {"-exec", "-execdir", "-ok", "-okdir"}:
                        stop = offset + 1
                        while stop < len(arguments) and arguments[stop] not in {
                            ";",
                            "+",
                        }:
                            stop += 1
                        yield from _command_words(
                            shlex.join(
                                [
                                    value.replace("{}", "$find_path")
                                    for value in arguments[offset + 1 : stop]
                                ]
                            ),
                            source,
                        )
            if "--" in arguments and arguments[arguments.index("--") + 1 :][:1] == [
                "__keel_make__"
            ]:
                yield from _command_words(
                    shlex.join(arguments[arguments.index("--") + 1 :]), source
                )
            producer = entry
            break
        position = end
        boundary = position


def _guard_shell_environment(command: str, source: str) -> None:
    # Shell quoting can split a literal name in the original text.
    _guard_pytest_environment(" ".join(_shell_words(command)), source)
    for entry in _command_words(command, source):
        word = entry.word.rsplit("/", 1)[-1]
        arguments = list(entry.arguments)
        _require(
            word not in {"eval", ".", "source"}
            and not (
                word == "set"
                and (
                    any(re.fullmatch(r"-[A-Za-z]*a[A-Za-z]*", arg) for arg in arguments)
                    or any(
                        arguments[j : j + 2] == ["-o", "allexport"]
                        for j in range(len(arguments))
                    )
                )
            ),
            "Cannot judge implicit shell environment",
            source,
            "replace eval, sourcing and allexport with literal environment names",
        )
        if entry.script is not None:
            _require(
                not re.search(
                    r"[$`]|\b(?:export|declare|typeset|local|env|eval|source|allexport)\b"
                    r"|(?:^|[;&|])[ \t]*\.[ \t]",
                    entry.script,
                ),
                "Cannot judge indirect shell environment",
                source,
                "replace shell script environment construction with literal names",
            )
        if word not in {"export", "declare", "typeset", "local", "env"}:
            continue
        options = []
        if word == "env":
            offset = _after_options(arguments, 0, "env", source)
            for option_index, option in enumerate(arguments[:offset]):
                if option in {"-u", "--unset"}:
                    name = arguments[option_index + 1]
                elif option.startswith("--unset="):
                    name = option.partition("=")[2]
                elif option.startswith("-u"):
                    name = option[2:]
                else:
                    continue
                _require(
                    re.fullmatch(r"[A-Za-z_]\w*", name),
                    "Cannot judge computed environment name",
                    source,
                    "write the unset environment name literally",
                )
            arguments = arguments[offset:]
        else:
            while arguments and arguments[0].startswith("-"):
                options.append(arguments.pop(0))
        if word in {"declare", "typeset", "local"} and not any(
            re.fullmatch(r"-[A-Za-z]*x[A-Za-z]*", option) for option in options
        ):
            continue
        for argument in arguments:
            if word == "env" and "=" not in argument and not argument.startswith("-"):
                break
            name = argument.split("=", 1)[0]
            _require(
                re.fullmatch(r"[A-Za-z_]\w*", name),
                "Cannot judge a computed environment name without a shell",
                source,
                "write the exported or env variable name literally",
            )
            _guard_pytest_environment(f"{name}=", source)


def make_hop(command: str) -> tuple[list[str], list[str]]:
    """Return literal goals and assignments from one expanded make command."""
    calls = []
    for entry in _command_words(command):
        markers = entry.arguments.count("__keel_make__")
        if entry.word == "__keel_make__":
            _require(
                not markers, "Ambiguous make hop", command, "use one make call per line"
            )
        elif markers:
            _require(
                markers == 1
                and not entry.compound
                and not entry.redirected
                and "--" in entry.arguments
                and entry.arguments[entry.arguments.index("--") + 1 :][:1]
                == ("__keel_make__",),
                "Unjudged make wrapper",
                command,
                "invoke make directly or after the gate wrapper's --",
            )
        if entry.word in {"__keel_make__", "make"}:
            calls.append(entry)
    if not calls:
        return [], []
    _require(
        len(calls) == 1, "Ambiguous make hop", command, "use one make call per line"
    )
    (call,) = calls
    _require(
        not call.wrapped
        and not call.prefix
        and not call.redirected
        and not call.compound,
        "Unjudged make wrapper",
        command,
        "invoke make directly or after the gate wrapper's --",
    )
    goals, assignments = [], []
    for word in call.arguments:
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
            entry.word.rsplit("/", 1)[-1] == "pytest"
            or any(
                argument.rsplit("/", 1)[-1] == "pytest" for argument in entry.arguments
            )
            for command in commands
            for entry in _command_words(command)
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
    count = 0
    for entry in _command_words(command):
        if entry.word.rsplit("/", 1)[-1] == "pytest":
            args = list(entry.arguments)
        elif entry.arguments[:2] == ("-m", "pytest"):
            _require(
                entry.word == sys.executable,
                "Unjudged pytest interpreter",
                command,
                "invoke pytest through $(PY) -m pytest",
            )
            args = list(entry.arguments[2:])
        else:
            _require(
                not any(
                    argument.rsplit("/", 1)[-1] == "pytest"
                    for argument in entry.arguments
                ),
                "Unjudged pytest invocation prefix",
                command,
                "invoke pytest through $(PY) -m pytest without opaque prefixes",
            )
            continue
        _require(
            not entry.wrapped
            and not entry.redirected
            and all(
                re.fullmatch(r"[A-Za-z_]\w*=[^$`]*", value)
                and value.split("=", 1)[0] in _PYTEST_ENVIRONMENT
                for value in entry.prefix
            ),
            "Unjudged pytest invocation prefix",
            command,
            "use a direct pytest invocation with literal _PYTEST_ENVIRONMENT assignments",
        )
        count += 1
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
                    valid = valid and entry.before[-2:] == (binding, "&&")
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
    _require(
        count,
        "Unjudged pytest invocation prefix",
        command,
        "invoke pytest as a command",
    )
    return count
