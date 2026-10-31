"""
title: Integration — a process ends only through the exit helper, and the exit-code table is the enum
kind: tests
layer: n/a
summary: Three tree-wide gates over every Python file tests/source_tree.py `python_files` lists, and the first over every shell script too (the walk `check_structure.walk` uses), read from the syntax tree. The first fails an exit written anywhere but scripts/exit_codes.py (`sys.exit`, `os._exit`, any `.exit(...)` attribute such as argparse's, `raise SystemExit`, a SystemExit subclass, the builtins `exit` and `quit`, each of those as an attribute of `builtins` or `__builtins__`, and an import that renames any of them), an entry block that hands `finish` nothing while its module imports the helper, or that calls a function of its module and drops the value it returns, a return scripts/exit_code_table.py `read_script` cannot follow to an ExitCode member (a returned name bound by anything but a plain assignment included), a `report` or `fail` call missing one of its three message parts or holding a blank literal one, or handed a code that is not a failure member, a `passthrough` handed the script's own status (the entry function's result, directly or through a name, an int literal, a member, or a function of the module whose every return is one of those, also under a sign, in an arithmetic or `and`/`or` of them, or through a builtin such as `int`), an entry line `finish(passthrough(...))`, and an import of the helper under a second name. The second fails an ExitCode member the generated table in the limits guide does not name and a table row no member backs (scripts/exit_code_table.py `table_findings`). The third fails a `fail` or `finish` call outside the entry block of a module another project module imports (an import from tests/ does not count, and scripts/exit_codes.py is the helper), because a shared module raises or returns and only an entry point ends the process; `passthrough` is no ending, it marks a status and returns it. config/project.json `import_layers.may_end_the_process` names a module that may, with a non-blank reason, and an entry naming no such module is a finding. A walk that finds no Python file, or no entry block, is a failure, never a pass. It does not judge whether a message part is useful, and it cannot see an exit reached through `getattr`, `os.abort`, `os.kill`, an uncaught exception, argparse's own `--help` and usage exits, a `python -c` line in a makefile, or a status dropped by another callable (`asyncio.run(main())`); and it does not check a `passthrough` over a helper that returns another process's status (scripts/run_app.py `_app_status`), which passes by design, nor one over a function some of whose returns are the script's own literals and others a tool's status. The first also reads every file scripts/shell_gate.py `classify` calls a shell script (with no repository yet, every one the structure walk reaches), less scripts/exit_codes.sh itself: a script must source that helper by a path ending in `/exit_codes.sh` and end through it, as `exit "$EXIT_<NAME>"`, `exit_fail "$EXIT_<NAME>" WHAT ON NEXT` with a member other than SUCCESS and no blank part, or `exit_passthrough "$?"` for a wrapped tool's status, or of a name assigned as `name=$?` and otherwise only read as `$name` or `${name}` outside comments and quoted here-document bodies (any other occurrence, `let`, `(( ))`, `${name:=...}`, `printf -v`, `read`, `mapfile`, `for`, a word that only names it, is a finding at its own line), never a number or a member; a bare `exit 3`, `exit $?` or `exit` is a finding at its file and line, in a subshell, `$(...)`, backquotes or a process substitution `<(...)` or `>(...)` too, inside double quotes or a `${...}` as well (a quoted `}` closes no `${...}`), and so is a status the script renames: an `exit_passthrough` or `return` of anything else (`$((...))`, a positional, a name never assigned), and a `return` of a number or of nothing. A command name with no expansion has its quotes and backslashes removed and a `$'...'` decoded as bash decodes it, so `"exit"`, `\\exit`, `$'exit'`, `command exit` and `builtin exit` are `exit`; a command named by an expansion (`$x 3`, `"$cmd" 3`) and an `eval` are findings where the command could end the script (not inside `$(...)`, backquotes, a process substitution or `( ... )`, nor before a single `|` or `&`), because the gate cannot judge them; and an ending that needs the helper on a line before the one that sources it is a finding. Comments, quoted words, here-document bodies and a `case` subject or pattern are not commands, inside `$(...)` too, while a command in a clause body is judged; a file it cannot read to its end, such as one with an open quote or nested past `_SH_MAX_DEPTH` levels, is a finding, and a CRLF line end is the file's one finding, naming the carriage return. No shell script is a finding unless config/project.json `shell.no_scripts` gives the reason or `shell.enabled` (the copier answer `shell`) is false; every other finding holds whatever `shell.enabled` says, because it switches the shell tools only. It cannot see `set -e`, `trap`, `exec`, `kill`, an `sh -c` string, a pathname or brace expansion in a command name, or a script that falls off its end after some other ending. The first and third hand their findings to scripts/expiring_tier.py as the checks `exit-helper` and `exit-shared-module`: in the template repository, which holds copier.yml, every finding is red; in a generated project a finding its `expiring_tier.baseline` records warns until `expiring_tier.expires`, and any other is red. The first's held-status findings are the exception: they go as `exit-held-status`, which scripts/expiring_tier_data.py `WARN_ONLY` lists, and warn and never fail, in the template too, because the rule still flags ordinary scripts. Catching SystemExit is not an exit and is not a finding: the exception itself, or a tuple holding it, as the type of an `except` clause or an argument of pytest's `raises`; anywhere deeper in those expressions, and in a `raises` that is not pytest's, it is one. Not a check_* letter: the letters A to Z are taken.
"""

import ast
import collections
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "tests"))

import check_structure as cs  # noqa: E402
import config_loader  # noqa: E402
import exit_code_table as et  # noqa: E402
import expiring_tier  # noqa: E402
import git_tree  # noqa: E402
import shell_gate  # noqa: E402

import hermetic_git  # noqa: E402
import source_tree as st  # noqa: E402

pytestmark = pytest.mark.integration

# The attribute names that end a process when called: `sys.exit`, `os._exit`,
# and an argparse parser's own `exit`.
_EXIT_ATTRIBUTES = ("exit", "_exit")
# The builtins the `site` module adds for the interactive prompt.
_EXIT_BUILTINS = ("exit", "quit")
_EXIT_EXCEPTION = "SystemExit"
# {module: names} whose import under any name is an exit the walk would not
# otherwise recognise at its call.
_EXIT_IMPORTS = {
    "sys": ("exit",),
    "os": ("_exit",),
    "builtins": (*_EXIT_BUILTINS, _EXIT_EXCEPTION),
}
# The module whose attributes are the builtins, and the name every module
# already holds it under without importing it.
_BUILTINS_MODULE = "builtins"
_BUILTINS_GLOBAL = "__builtins__"
# (module, function): the one call that, handed SystemExit, asserts on an exit
# instead of causing one.
_EXPECTING_CALL = ("pytest", "raises")
# `report(code, what, on, next_step)` and `fail(...)`: the parts after the code.
_MESSAGE_PARTS = ("what", "on", "next_step")
_MESSAGE_CALLS = ("report", "fail")
_FINISH = "finish"
# The helper is one module under one import name; this is the other spelling.
_SECOND_NAME = "scripts." + et.HELPER_MODULE


def _builtins_names(tree):
    """The names under which *tree* can reach the builtins module."""
    names = {_BUILTINS_GLOBAL}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name == _BUILTINS_MODULE
            )
    return names


def _is_exit_exception(node, builtins_names):
    """True when *node* is `SystemExit`, bare or as an attribute of builtins."""
    if isinstance(node, ast.Name):
        return node.id == _EXIT_EXCEPTION
    return (
        isinstance(node, ast.Attribute)
        and node.attr == _EXIT_EXCEPTION
        and isinstance(node.value, ast.Name)
        and node.value.id in builtins_names
    )


def _expecting_call(tree):
    """A predicate: is this call the test library's `raises`? It is when the
    callee is `<name>.raises` and `<name>` is that library imported, or a bare
    name that `from <library> import raises` binds. A function a module
    defines under the same name is not."""
    library, function = _EXPECTING_CALL
    modules, names = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name == library
            )
        elif (
            isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module == library
        ):
            names.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name == function
            )

    def expecting(func):
        if isinstance(func, ast.Name):
            return func.id in names
        return (
            isinstance(func, ast.Attribute)
            and func.attr == function
            and isinstance(func.value, ast.Name)
            and func.value.id in modules
        )

    return expecting


def _caught_or_expected(tree, builtins_names):
    """The ids of the SystemExit references that catch or expect an exit: the
    type of an `except` clause, or an argument of the test library's `raises`,
    in either place the exception itself or a tuple that holds it. A
    SystemExit any deeper in such an expression is being called or raised
    there, and is not allowed."""
    allowed = set()
    expecting = _expecting_call(tree)
    for node in ast.walk(tree):
        holders = []
        if isinstance(node, ast.ExceptHandler) and node.type is not None:
            holders.append(node.type)
        elif isinstance(node, ast.Call) and expecting(node.func):
            holders.extend(node.args)
            holders.extend(kw.value for kw in node.keywords)
        for holder in holders:
            items = holder.elts if isinstance(holder, ast.Tuple) else [holder]
            for item in items:
                if _is_exit_exception(item, builtins_names):
                    allowed.add(id(item))
                    # The `builtins` in `builtins.SystemExit` is no exit.
                    allowed.update(id(n) for n in ast.walk(item))
    return allowed


def exit_form_findings(tree, relpath):
    """Each place *tree* ends the process, or names the means to, without the
    helper: `relpath:line: what`."""
    out = []
    builtins_names = _builtins_names(tree)
    allowed = _caught_or_expected(tree, builtins_names)

    def finding(node, what):
        out.append(
            "%s:%d: %s -- end the process through `finish(main())` (%s)"
            % (relpath, node.lineno, what, et.HELPER)
        )

    for node in ast.walk(tree):
        if id(node) in allowed:
            continue
        if isinstance(node, ast.Attribute) and node.attr in _EXIT_ATTRIBUTES:
            finding(node, "`.%s` ends the process here" % node.attr)
        elif (
            isinstance(node, ast.Attribute)
            and node.attr in _EXIT_IMPORTS[_BUILTINS_MODULE]
            and isinstance(node.value, ast.Name)
            and node.value.id in builtins_names
        ):
            finding(node, "`%s.%s` ends the process here" % (node.value.id, node.attr))
        elif isinstance(node, ast.Name) and node.id in _EXIT_BUILTINS:
            finding(node, "the builtin `%s` ends the process here" % node.id)
        elif isinstance(node, ast.Name) and node.id == _EXIT_EXCEPTION:
            finding(node, "`%s` is raised or named here" % _EXIT_EXCEPTION)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            for alias in node.names:
                if alias.name in _EXIT_IMPORTS.get(node.module or "", ()):
                    finding(node, "imports `%s.%s`" % (node.module, alias.name))
                if "%s.%s" % (node.module, alias.name) == _SECOND_NAME:
                    finding(node, "imports the helper as `%s`" % _SECOND_NAME)
            if node.module == _SECOND_NAME:
                finding(node, "imports the helper as `%s`" % _SECOND_NAME)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == _SECOND_NAME:
                    finding(node, "imports the helper as `%s`" % _SECOND_NAME)
    return sorted(out)


def _blank_literal(node):
    """True when *node* is a string literal with nothing in it but space."""
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and not node.value.strip()
    )


def message_findings(tree, relpath):
    """Each `report` or `fail` call of the helper in *tree* that does not carry
    its three message parts, or carries a blank literal one. A starred or
    `**` argument is a finding: the parts could not be counted."""
    out = []
    bindings = et.helper_bindings(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        symbol = et.helper_symbol(node.func, bindings)
        if symbol not in _MESSAGE_CALLS:
            continue
        where = "%s:%d: `%s`" % (relpath, node.lineno, symbol)
        if any(isinstance(a, ast.Starred) for a in node.args) or any(
            kw.arg is None for kw in node.keywords
        ):
            out.append(
                "%s is called with a starred argument, so its message parts "
                "cannot be counted -- name each part" % where
            )
            continue
        given = dict(zip(_MESSAGE_PARTS, node.args[1:], strict=False))
        given.update({kw.arg: kw.value for kw in node.keywords})
        for part in _MESSAGE_PARTS:
            if part not in given:
                out.append(
                    "%s has no `%s` part -- say what failed, on which input "
                    "and what to do next" % (where, part)
                )
            elif _blank_literal(given[part]) or _is_none(given[part]):
                out.append("%s has a blank `%s` part" % (where, part))
    return sorted(out)


def _is_none(node):
    return isinstance(node, ast.Constant) and node.value is None


def entry_findings(tree, relpath, quiet_names, exercises_helper=False):
    """Each way *tree*'s entry block fails to end through the helper: a
    `finish` call outside the block, every return `read_tree` cannot follow to
    a member, and an entry block that hands `finish` nothing while the module
    binds the helper or the block drops what a function of the module returns.
    *exercises_helper* is the helper's own unit test, which calls `finish` to
    assert on it."""
    out = []
    bindings = et.helper_bindings(tree)
    blocks = et.entry_blocks(tree)
    handed = et.finish_calls(tree, bindings)
    in_block = {id(call) for call in handed}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and et.helper_symbol(node.func, bindings) == _FINISH
            and id(node) not in in_block
            and not exercises_helper
        ):
            out.append(  # noqa: PERF401 -- one finding per line reads plainer
                '%s:%d: `finish` is called outside the `if __name__ == "__main__":` '
                "block -- return the member to `main`'s caller, or call `fail`"
                % (relpath, node.lineno)
            )
    if handed:
        out.extend(et.read_tree(tree, relpath, quiet_names).findings)
    elif blocks and (bindings[0] or bindings[1]):
        out.append(
            "%s:%d: the entry block hands nothing to `finish`, so the status "
            "`main` returns is dropped -- write `finish(main())` (%s)"
            % (relpath, blocks[0].lineno, et.HELPER)
        )
    else:
        out.extend(
            "%s:%d: the entry block drops what `%s` returns, so the process "
            "exits 0 whatever it found -- write `finish(%s())` with `%s` "
            "returning members (%s), or return nothing from it"
            % (relpath, node.lineno, name, name, name, et.HELPER)
            for node, name in et.dropped_results(tree)
        )
    return sorted(out)


def _mirror_test(relpath):
    """The unit test that mirrors the script at *relpath* (tests/AGENT.md)."""
    directory, name = os.path.split(relpath)
    return "tests/unit/%s/test_%s" % (directory, name)


def helper_findings(root):
    """Every finding of the first gate over the tree at *root*, with the count
    of files walked and of entry blocks judged. Raises st.SourceTreeError when there
    is nothing to walk."""
    files = st.python_files(root)
    if not files:
        raise st.SourceTreeError("%s: no Python file to judge -- zero items" % root)
    members = et.read_members(str(root))
    quiet = frozenset(m.name for m in members if m.value == 0)
    known = {m.name for m in members}
    findings, entries = [], 0
    for relpath in files:
        tree = st.parse(root, relpath)
        if relpath != et.HELPER:
            findings.extend(exit_form_findings(tree, relpath))
        # The helper's mirror unit test calls it with bad arguments on purpose.
        exercises = relpath == _mirror_test(et.HELPER)
        if not exercises:
            findings.extend(message_findings(tree, relpath))
            findings.extend(et.code_findings(tree, relpath, quiet))
        findings.extend(entry_findings(tree, relpath, quiet, exercises))
        entries += len(et.entry_blocks(tree))
        bindings = et.helper_bindings(tree)
        findings.extend(
            "%s:%d: names %s.%s, which %s does not define"
            % (relpath, node.lineno, et.ENUM, node.attr, et.HELPER)
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and et.helper_symbol(node.value, bindings) == et.ENUM
            and node.attr not in known
            # `ExitCode.__members__` reads the class, it names no member.
            and not node.attr.startswith("__")
        )
    # `read_tree` and `code_findings` both judge the code of a call an entry
    # function reaches; one line per defect.
    findings = sorted(set(findings))
    return {"files": len(files), "entries": entries, "findings": findings}


# The helper calls that end the process. `passthrough` only marks a wrapped
# tool's status for `finish` and returns it, so a module may call it anywhere.
_ENDING_CALLS = ("fail", "finish")
_TESTS = "tests/"


def library_findings(root):
    """Every call that ends the process in a module another project module
    imports, outside that module's entry block, with the count of such
    modules judged. Tests importing a module do not make it shared: a test
    imports scripts to drive their `main`. config/project.json
    `import_layers.may_end_the_process` names a module that may, with its
    reason; an entry that names no shared module calling the helper is
    stale and a finding."""
    files = st.python_files(root)
    if not files:
        raise st.SourceTreeError("%s: no Python file to judge -- zero items" % root)
    policy = st.import_layers(root)
    exempt = policy["may_end_the_process"]
    importers = {}
    for importer, _lineno, imported in st.import_edges(
        root, files, policy["search_roots"]
    ):
        if not importer.startswith(_TESTS) and imported != et.HELPER:
            importers.setdefault(imported, importer)
    findings, enders = [], set()
    for relpath in sorted(importers):
        tree = st.parse(root, relpath)
        bindings = et.helper_bindings(tree)
        entry = {id(n) for block in et.entry_blocks(tree) for n in ast.walk(block)}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or id(node) in entry:
                continue
            name = et.helper_symbol(node.func, bindings)
            if name not in _ENDING_CALLS:
                continue
            enders.add(relpath)
            if relpath in exempt:
                continue
            findings.append(
                "%s:%d: %s is imported by %s, so it must raise or return, never end "
                "the process; return to the entry point and let it call finish"
                % (relpath, node.lineno, name, importers[relpath])
            )
    findings.extend(
        "config/project.json: import_layers.may_end_the_process names `%s`, which "
        "is no shared module that ends the process; delete the entry" % relpath
        for relpath in sorted(exempt)
        if relpath not in enders
    )
    return {"modules": len(importers), "findings": sorted(findings)}


# --- shell scripts -----------------------------------------------------------------

# The words that open or close a compound command and never name a command.
_SH_RESERVED = frozenset(
    ("!", "{", "}", "if", "then", "else", "elif", "fi", "do", "done", "while")
    + ("until", "case", "esac", "time")
)
# Where the reader is in a `case`: after `case`, after its subject, among
# the patterns of a clause, and in a clause's body.
_SH_CASE_SUBJECT, _SH_CASE_IN = "subject", "in"
_SH_CASE_PATTERN, _SH_CASE_BODY = "pattern", "body"
_SH_EXIT, _SH_FAIL, _SH_PASS = "exit", "exit_fail", "exit_passthrough"
_SH_ENDINGS = (_SH_EXIT, _SH_FAIL, _SH_PASS)
_SH_RETURN = "return"
_SH_EVAL = "eval"
# The escapes bash decodes inside `$'...'`: a letter or quote, an octal,
# `\xHH`, `\uHHHH`, `\UHHHHHHHH` and `\cX`.
_SH_ANSI_C_ESCAPE = re.compile(
    r"\\(?:([abeEfnrtv\\'\"?])|([0-7]{1,3})|x([0-9A-Fa-f]{1,2})"
    r"|u([0-9A-Fa-f]{1,4})|U([0-9A-Fa-f]{1,8})|c(.))",
    re.DOTALL,
)
_SH_ANSI_C_SIMPLE = {
    "a": "\a",
    "b": "\b",
    "e": "\x1b",
    "E": "\x1b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "v": "\v",
    "\\": "\\",
    "'": "'",
    '"': '"',
    "?": "?",
}
_SH_SOURCE = (".", "source")
# Words that run the command after them as it is, so `command exit 3` is an
# exit; `command -v` and `-V` only describe it.
_SH_PREFIXES = ("command", "builtin")
_SH_DESCRIBE = ("-v", "-V")
# The commands whose `name=value` arguments assign as a plain assignment does.
_SH_DECLARE = ("local", "export", "readonly", "declare", "typeset")
_SH_HELPER_NAME = os.path.basename(et.HELPER_SH)
# An assignment word, `name=value` or the append `name+=value`.
_SH_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\+?=")
# A word so far that a `(` turns into an array assignment, `a=(...)` or
# `a+=(...)`.
_SH_ARRAY_START = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\+?=\Z")
# `$EXIT_NAME` or `${EXIT_NAME}`, bare or inside one pair of double quotes.
_SH_MEMBER = re.compile(r'(")?\$(?:EXIT_([A-Z0-9_]+)|\{EXIT_([A-Z0-9_]+)\})(?(1)")\Z')
_SH_NUMBER = re.compile(r"""(["']?)[0-9]+\1\Z""")
# `$?` or `${?}`, bare or inside one pair of double quotes.
_SH_LAST_STATUS = re.compile(r'(")?\$(?:\?|\{\?\})(?(1)")\Z')
# `$name` or `${name}`, bare or inside one pair of double quotes.
_SH_NAME_REF = re.compile(
    r'(")?\$(?:([A-Za-z_][A-Za-z0-9_]*)|\{([A-Za-z_][A-Za-z0-9_]*)\})(?(1)")\Z'
)
# A carriage return that ends a line, as a CRLF file writes every one.
_SH_CRLF = re.compile(r"\r(?=\n|\Z)")
# The places _ShellReader records, where a carriage return is no part of a
# word; a span of commands, inside `$(...)` or backquotes, is place None.
_SH_IN_COMMENT, _SH_IN_QUOTE = "comment", "quote"
_SH_IN_BODY, _SH_IN_COMMANDS = "body", None
# What a carriage return that ends a line does where it sits, and what to do.
_SH_LF = "save the file with LF line endings"
_SH_CR_WHERE = {
    _SH_IN_COMMANDS: ", which the shell reads as part of its last word; " + _SH_LF,
    _SH_IN_COMMENT: " inside a comment; " + _SH_LF,
    _SH_IN_QUOTE: (
        " inside a quoted string, which keeps it as a character of the string; "
        + _SH_LF
    ),
    _SH_IN_BODY: (
        " inside a here-document body, which writes it out with the text; "
        + _SH_LF
        + ", and if the document must carry CRLF, add the carriage returns as "
        + """it is written: awk '{ printf "%s\\r\\n", $0 }' <<'EOF'"""
    ),
}
_SH_BLANK = re.compile(r"""(["'])\s*\1\Z""")
# The characters that end a here-document's delimiter word.
_SH_DELIMITER_ENDS = " \t\n;&|<>()"
_SH_ENDS_WELL = 'exit "$EXIT_<NAME>" from %s' % et.HELPER_SH
# How deep `$(...)`, `${...}`, double quotes and backquotes may nest. A script
# a person writes nests a handful deep; the reader spends up to three Python
# frames a level, so 100 levels stay far under the default recursion limit of
# 1000 with pytest's own frames on the stack.
_SH_MAX_DEPTH = 100
_SH_HANDS_ON = (
    'hand it "$?", or a name a bare name=$? statement binds before it and that '
    'is read only as "$name"'
)
# Which uses of a name an `exit_passthrough` or `return` hands on keep it the
# wrapped tool's status. Only a bare assignment statement binds it: the word
# `name=$?` (`"$?"` or `${?}` too), alone or after `local` and its kin, as a
# whole simple command in the main shell, earlier in the text than the ending.
# Every other mention of the name, by _SH_NAMING's rule, outside a comment
# and a quoted here-document body, must be the plain read `$name` or
# `${name}`; any other is a finding at its line, because the gate cannot show
# it leaves the status alone, and so is a `name=$?` that binds nothing.
_SH_BINDING = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)=(")?\$(?:\?|\{\?\})(?(2)")\Z')
# A mention is a word that names the variable, so where a held name sits
# decides it. Each word of a command whose arguments can name a variable it
# writes or tests is a mention: the commands below, `printf -v`, a command
# named by an expansion and a function the script defines. So is a command
# name, unless it is a path, and the name part of an assignment word. An
# argument of any other command, a redirection target, a `case` word, an
# assigned value and the text of an unquoted here-document body are none.
# A `${...}`, `$((...))`, `((...))`, `$[...]` and `{name}>` holds a mention
# wherever it sits, and so does an unquoted here-document body with a
# substitution or an expansion other than `${name}` in it. Text no word
# holds is a mention: what the reader cannot place fails closed.
_SH_NAMING = frozenset(
    ("read", "mapfile", "readarray", "unset", "let", "getopts", "wait", "eval")
    + ("for", "select", "coproc", "[[", "trap", "function")
    + _SH_DECLARE
)
_SH_PRINTF, _SH_PRINTF_VAR = "printf", "-v"
_SH_FD_NAME = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}\Z")
_SH_FUNCTION = re.compile(
    r"(?:^|[\s;&|(){}])(?:function[ \t]+([^\s(){};&|<>]+)"
    r"|([A-Za-z_][A-Za-z0-9_.:-]*)[ \t]*\([ \t]*\))"
)
_SH_BODY_EXPANDS = re.compile(r"\$\(|`|\$\[|\$\{(?![A-Za-z_][A-Za-z0-9_]*\})")


class ShellScanError(Exception):
    """A shell file the reader cannot read to its end, at *line*."""

    def __init__(self, line, reason):
        super().__init__(reason)
        self.line, self.reason = line, reason


class _ShellReader:
    """Splits POSIX shell text into its simple commands, each (line, words,
    main), main false where the command cannot end the script: inside
    `$(...)`, backquotes, a process substitution or `( ... )`, or ended by a
    `|` or `|&` that pipes it on or a `&` that runs it in the background.
    `&&`, `||`, `;`, `;&`, `;;&` and the redirections `&>`, `&>>`, `>&` and
    `<&` leave a command in the main shell.

    A word keeps its quotes, so `"$EXIT_USAGE"` and `exit` stay tellable
    apart. A comment, a quoted span and a here-document body are no command;
    the inside of `$(...)` and of backquotes is read as commands too, inside
    double quotes as well, because the shell runs it there, and so is the
    inside of a process substitution `<(...)` or `>(...)`. A
    redirection and its target are no word, and neither is a `case` header
    or pattern, which never names a command; the elements of an array
    assignment `a=(...)` are part of its word. A `$'...'` is read to its
    closing quote, a backslash escaping the next character, as bash reads
    it. It does not read a command a string later runs (`trap`, `eval`,
    `sh -c`)."""

    def __init__(self, text, line=1, depth=0, offset=0, sub=0):
        self.text, self.i, self.line, self.depth = text, 0, line, depth
        # How many substitutions and `( ... )` subshells enclose i.
        self.sub, self.paren = sub, 0
        self.commands, self._heredocs = [], []
        # (start, end) in the whole file's text of each comment and quoted
        # here-document body: text no command reads.
        self.offset, self.unread = offset, []
        # (start, end, place) in the whole file's text of each comment, quoted
        # string, here-document body and span of commands.
        self.places = []
        # [state, line it opened on] of each open `case`, innermost last; the
        # state is _SH_CASE_SUBJECT, _SH_CASE_IN, _SH_CASE_PATTERN or
        # _SH_CASE_BODY. pattern_open says a pattern has begun since the last
        # clause ended, so an `esac` there is a pattern word, not the end.
        self.cases, self.pattern_open = [], False
        self.words, self.word, self.word_line = [], None, line
        # The offsets in the whole file's text where each of words starts and
        # ends, and where the word being read starts.
        self.starts, self.ends, self.word_at = [], [], offset
        # (start, end, red_before, zone) in the whole file's text of each
        # word whose role the reader alone settles and each span that holds
        # a mention wherever it sits; _sh_name_uses reads them.
        self.marks = []
        self.start, self.skip = line, False

    def _add(self, chars):
        if self.word is None:
            self.word, self.word_line = [], self.line
            self.word_at = self.offset + self.i
        self.word.append(chars)

    def _end_word(self):
        if self.word is None:
            return
        word, self.word = "".join(self.word), None
        at, end = self.word_at, self.offset + self.i
        if "$[" in word:
            self.marks.append((at, end, end, True))
        if self.skip:
            self.skip = False
            self.marks.append((at, end, at, False))
        elif self._case_word(word):
            self.marks.append((at, end, at, False))
        else:
            if not self.words:
                self.start = self.word_line
            self.words.append(word)
            self.starts.append(at)
            self.ends.append(end)
            # `function f` is a whole definition head: the `{` after it on
            # the same line opens the body, whose commands are read as such.
            if self.words[-2:-1] == ["function"] and all(
                w in _SH_RESERVED for w in self.words[:-2]
            ):
                self._end_command()

    def _case_state(self):
        return self.cases[-1][0] if self.cases else None

    def _case_word(self, word):
        """Whether *word* belongs to a `case` header or pattern, which names
        no command; reading it moves the case state on."""
        state = self._case_state()
        at_command = all(w in _SH_RESERVED for w in self.words)
        if state == _SH_CASE_SUBJECT:
            self.cases[-1][0] = _SH_CASE_IN
        elif state == _SH_CASE_IN:
            if word != "in":
                raise ShellScanError(self.line, "a `case` names no `in`")
            self.cases[-1][0], self.pattern_open = _SH_CASE_PATTERN, False
        elif state == _SH_CASE_PATTERN:
            if word == "esac" and not self.pattern_open:
                self.cases.pop()
            self.pattern_open = True
        elif word == "case" and at_command:
            self.cases.append([_SH_CASE_SUBJECT, self.word_line])
        elif word == "esac" and at_command and state == _SH_CASE_BODY:
            self.cases.pop()
        else:
            return False
        return True

    def _case_mark(self, c):
        """Read the mark *c* at i if it belongs to a `case` clause: a `(` or
        `|` inside a pattern, the `)` that ends one, or the `;;`, `;&` or
        `;;&` that ends a clause body. Returns whether it did."""
        self._end_word()
        state, t = self._case_state(), self.text
        if state == _SH_CASE_PATTERN and c in "(|":
            self.pattern_open = True
            self.i += 1
        elif state == _SH_CASE_PATTERN and c == ")":
            self.cases[-1][0] = _SH_CASE_BODY
            self.i += 1
        elif state == _SH_CASE_BODY and t.startswith((";;", ";&"), self.i):
            self._end_command()
            self.i += 3 if t.startswith(";;&", self.i) else 2
            self.cases[-1][0], self.pattern_open = _SH_CASE_PATTERN, False
        else:
            return False
        return True

    def _open_case(self):
        """Fail on a `case` still open where the text being read ends."""
        if self.cases:
            raise ShellScanError(
                self.cases[-1][1], "a `case` is never closed by `esac`"
            )

    def _end_command(self, alone=True):
        """End the command being read; *alone* is false when a `|`, `|&`
        or background `&` ends it, which runs it in a subshell."""
        self._end_word()
        if self.skip:
            raise ShellScanError(self.line, "a redirection names no target")
        if self.words:
            main = alone and not self.sub and not self.paren
            self.commands.append((self.start, self.words, main, self.starts, self.ends))
        self.words, self.starts, self.ends = [], [], []

    def _span(self, end, what):
        """Add text[i:end+1] to the word, counting its lines."""
        if end < 0:
            raise ShellScanError(self.line, "%s is never closed" % what)
        chunk = self.text[self.i : end + 1]
        self._add(chunk)
        self.line += chunk.count("\n")
        self.i = end + 1

    def _arithmetic(self):
        """`$((...))`: one part of a word, a span that holds a mention."""
        begin = self.offset + self.i
        self._span(self._matching(self.i + 1, "(", ")"), "a `$((`")
        end = self.offset + self.i
        self.marks.append((begin, end, end, True))

    def _quote_span(self, end, what):
        """A single-quoted or `$'...'` span to *end*, recorded as a place."""
        begin = self.offset + self.i
        self._span(end, what)
        self.places.append((begin, self.offset + self.i, _SH_IN_QUOTE))

    def _comment(self):
        """A comment, from the `#` at i to the end of its line: text no
        command reads."""
        newline = self.text.find("\n", self.i)
        end = len(self.text) if newline < 0 else newline
        span = (self.offset + self.i, self.offset + end)
        self.unread.append(span)
        self.places.append(span + (_SH_IN_COMMENT,))
        self.i = end

    def _closing(self, j, quote):
        """The index of the *quote* that closes the span from j, a backslash
        escaping the next character, or -1."""
        t = self.text
        while j < len(t) and t[j] != quote:
            j += 2 if t[j] == "\\" else 1
        return j if j < len(t) else -1

    def _matching(self, j, opener, closer):
        """The index of the *closer* that balances the *opener* at j, or -1."""
        depth = 0
        for k in range(j, len(self.text)):
            if self.text[k] == opener:
                depth += 1
            elif self.text[k] == closer:
                depth -= 1
                if depth == 0:
                    return k
        return -1

    @contextlib.contextmanager
    def _level(self):
        """One more level of nesting for the span read inside it; past
        _SH_MAX_DEPTH the read stops with a finding, never a RecursionError."""
        self.depth += 1
        if self.depth > _SH_MAX_DEPTH:
            raise ShellScanError(
                self.line, "it nests deeper than %d levels" % _SH_MAX_DEPTH
            )
        try:
            yield
        finally:
            self.depth -= 1

    def _double_quote(self):
        """A double-quoted span: one part of a word, to the `"` that closes
        it. A `$(...)` or backquote inside it is read as commands, because
        the shell runs it there too."""
        with self._level():
            t, opened, begin = self.text, self.line, self.offset + self.i
            self._add('"')
            self.i += 1
            while self.i < len(t):
                c = t[self.i]
                if c == '"':
                    self._add(c)
                    self.i += 1
                    self.places.append((begin, self.offset + self.i, _SH_IN_QUOTE))
                    return
                if c == "\\":
                    self._span(self.i + 1, "a double quote")
                elif c == "`":
                    self._backquote()
                elif t.startswith("$((", self.i):
                    self._arithmetic()
                elif t.startswith("$(", self.i):
                    self._substitution()
                elif t.startswith("${", self.i):
                    self._expansion(quoted=True)
                else:
                    self._span(self.i, "a double quote")
            raise ShellScanError(opened, "a double quote is never closed")

    def _expansion(self, quoted):
        """`${...}`: one part of a word, to the unquoted `}` that closes it.
        A quote, a nested expansion or a substitution inside is read as the
        shell reads it, so a quoted `}` closes nothing. Inside double quotes
        a `'` is literal, as POSIX reads it (`bash --posix` agrees; plain
        bash does not)."""
        with self._level():
            t, opened, begin = self.text, self.line, self.offset + self.i
            self._add("${")
            self.i += 2
            while self.i < len(t):
                c = t[self.i]
                if c == "}":
                    self._add(c)
                    self.i += 1
                    end = self.offset + self.i
                    self.marks.append((begin, end, end, True))
                    return
                if c == "\\":
                    self._span(self.i + 1, "a `${`")
                elif c == "'" and not quoted:
                    self._quote_span(t.find("'", self.i + 1), "a single quote")
                elif t.startswith("$'", self.i) and not quoted:
                    self._quote_span(self._closing(self.i + 2, "'"), "an ANSI-C quote")
                elif c == '"':
                    self._double_quote()
                elif c == "`":
                    self._backquote()
                elif t.startswith("$((", self.i):
                    self._arithmetic()
                elif t.startswith("$(", self.i):
                    self._substitution()
                elif t.startswith("${", self.i):
                    self._expansion(quoted)
                else:
                    self._span(self.i, "a `${`")
            raise ShellScanError(opened, "a `${` is never closed")

    def _substitution(self):
        """`$(...)`, or the process substitution `<(...)` or `>(...)`: its
        commands are read; the whole is one part of a word."""
        with self._level():
            begin, line = self.i, self.line
            saved = (self.words, self.word, self.word_line, self.start, self.skip)
            nested = (self.cases, self.pattern_open, self.paren)
            starts = (self.starts, self.ends, self.word_at)
            self.words, self.word, self.skip = [], None, False
            self.starts, self.ends = [], []
            self.cases, self.paren = [], 0
            self.sub += 1
            self.i += 2
            self.run(closer=")")
            self.sub -= 1
            raw = self.text[begin : self.i]
            span = (self.offset + begin, self.offset + self.i, _SH_IN_COMMANDS)
            self.places.append(span)
            self.words, self.word, self.word_line, self.start, self.skip = saved
            self.cases, self.pattern_open, self.paren = nested
            self.starts, self.ends, self.word_at = starts
            if self.word is None:
                self.word, self.word_line = [], line
                self.word_at = self.offset + begin
            self.word.append(raw)

    def _backquote(self):
        with self._level():
            end = self._closing(self.i + 1, "`")
            if end < 0:
                raise ShellScanError(self.line, "a backquote is never closed")
            inner = _ShellReader(
                self.text[self.i + 1 : end],
                self.line,
                self.depth,
                self.offset + self.i + 1,
                self.sub + 1,
            )
            inner.run()
            self.commands.extend(inner.commands)
            self.unread.extend(inner.unread)
            self.places.extend(inner.places)
            self.marks.extend(inner.marks)
            span = (self.offset + self.i, self.offset + end + 1, _SH_IN_COMMANDS)
            self.places.append(span)
            self._span(end, "a backquote")

    def _array(self):
        """`name=( ... )`: the elements of an array assignment, one part of
        the assignment word, to the unquoted `)` that closes them. No element
        is a command; a substitution inside one is read as commands, and a
        `#` that opens an element opens a comment, as bash reads them."""
        with self._level():
            t, opened = self.text, self.line
            self._add("(")
            self.i += 1
            while self.i < len(t):
                c = t[self.i]
                if c == ")":
                    self._add(c)
                    self.i += 1
                    return
                if c == "#" and t[self.i - 1] in " \t\n(":
                    self._comment()
                elif c == "\\":
                    self._span(self.i + 1, "an array")
                elif c == "'":
                    self._quote_span(t.find("'", self.i + 1), "a single quote")
                elif t.startswith("$'", self.i):
                    self._quote_span(self._closing(self.i + 2, "'"), "an ANSI-C quote")
                elif c == '"':
                    self._double_quote()
                elif c == "`":
                    self._backquote()
                elif t.startswith("$((", self.i):
                    self._arithmetic()
                elif t.startswith("$(", self.i):
                    self._substitution()
                elif t.startswith("${", self.i):
                    self._expansion(quoted=False)
                else:
                    self._span(self.i, "an array")
            raise ShellScanError(opened, "an array is never closed")

    def _redirect(self):
        t = self.text
        # A descriptor number written against the operator belongs to it;
        # `&>` and `&>>` take none, so `echo 1&>f` echoes 1.
        word = None if self.word is None else "".join(self.word)
        if t[self.i] != "&" and word is not None and word.isdigit():
            self.word = None
        else:
            if word is not None and _SH_FD_NAME.match(word):
                # `{name}>` stores the descriptor it opens in name.
                end = self.offset + self.i
                self.marks.append((self.word_at, end, end, True))
            self._end_word()
        if t.startswith("<<", self.i) and not t.startswith("<<<", self.i):
            self.i += 2
            strip = t.startswith("-", self.i)
            self.i += strip
            self._heredoc_delimiter(strip)
            return
        while self.i < len(t) and t[self.i] in "<>&|":
            self.i += 1
        if t.startswith("-", self.i):
            # `>&-` closes a descriptor and names no target.
            self.i += 1
            return
        self.skip = True

    def _heredoc_delimiter(self, strip):
        t = self.text
        while self.i < len(t) and t[self.i] in " \t":
            self.i += 1
        parts, quoted = [], False
        while self.i < len(t) and t[self.i] not in _SH_DELIMITER_ENDS:
            c = t[self.i]
            quoted = quoted or c in "'\"\\"
            if c in "'\"":
                end = t.find(c, self.i + 1)
                if end < 0:
                    raise ShellScanError(self.line, "a quote is never closed")
                parts.append(t[self.i + 1 : end])
                self.i = end + 1
            elif c == "\\":
                parts.append(t[self.i + 1 : self.i + 2])
                self.i += 2
            else:
                parts.append(c)
                self.i += 1
        if not parts:
            raise ShellScanError(self.line, "a here-document names no delimiter")
        self._heredocs.append(("".join(parts), strip, self.line, quoted))

    def _heredoc_bodies(self):
        t = self.text
        while self._heredocs:
            delimiter, strip, opened, quoted = self._heredocs.pop(0)
            begin = self.offset + self.i
            while True:
                if self.i >= len(t):
                    raise ShellScanError(
                        opened, "a here-document is never closed by %s" % delimiter
                    )
                newline = t.find("\n", self.i)
                end = len(t) if newline < 0 else newline
                body = t[self.i : end]
                self.i, self.line = end + 1, self.line + 1
                if (body.lstrip("\t") if strip else body) == delimiter:
                    break
            end = self.offset + self.i
            if quoted:
                self.unread.append((begin, end))
            else:
                expands = _SH_BODY_EXPANDS.search(
                    self.text, begin - self.offset, self.i
                )
                self.marks.append((begin, end, end if expands else begin, False))
            self.places.append((begin, end, _SH_IN_BODY))

    def run(self, closer=None):
        """Read from i to the end, or to the unbalanced *closer*."""
        t = self.text
        while self.i < len(t):
            c = t[self.i]
            if c == "#" and self.word is None:
                self._comment()
            elif c == "\\" and t.startswith("\\\n", self.i):
                self.i, self.line = self.i + 2, self.line + 1
            elif c == "\\":
                self._add(t[self.i : self.i + 2])
                self.i += 2
            elif c == "'":
                self._quote_span(t.find("'", self.i + 1), "a single quote")
            elif t.startswith("$'", self.i):
                self._quote_span(self._closing(self.i + 2, "'"), "an ANSI-C quote")
            elif c == '"':
                self._double_quote()
            elif c == "`":
                self._backquote()
            elif t.startswith("$((", self.i):
                self._arithmetic()
            elif t.startswith("$(", self.i):
                self._substitution()
            elif t.startswith("${", self.i):
                self._expansion(quoted=False)
            elif c == "\n":
                self._end_command()
                self.i, self.line = self.i + 1, self.line + 1
                self._heredoc_bodies()
            elif c == "(" and _SH_ARRAY_START.match("".join(self.word or ())):
                self._array()
            elif t.startswith("&>", self.i):
                # `&>` and `&>>` redirect both outputs; no background `&`.
                self._redirect()
            elif c in ";&|()":
                if self._case_mark(c):
                    continue
                # A doubled `||` or `&&` runs its left side in this shell.
                pair = (t[self.i - 1 : self.i], t[self.i + 1 : self.i + 2])
                if c == "(" and pair[1] == "(" and pair[0] != "(":
                    # `((...))` is arithmetic: a span that holds a mention.
                    close = self._matching(self.i, "(", ")")
                    if close >= 0:
                        end = self.offset + close + 1
                        self.marks.append((self.offset + self.i, end, end, True))
                self._end_command(c not in "|&" or c in pair)
                self.i += 1
                if c == "(":
                    self.paren += 1
                elif c == ")" and self.paren:
                    self.paren -= 1
                elif c == ")" and closer:
                    self._open_case()
                    return
            elif t.startswith(("<(", ">("), self.i):
                self._substitution()
            elif c in "<>":
                self._redirect()
            elif c in " \t":
                self._end_word()
                self.i += 1
            else:
                self._add(c)
                self.i += 1
        if closer:
            raise ShellScanError(self.line, "a `$(` is never closed")
        self._end_command()
        self._open_case()
        if self._heredocs:
            _delimiter, _strip, opened, _quoted = self._heredocs[0]
            raise ShellScanError(opened, "a here-document has no body")


def _sh_ansi_c(body):
    """The text bash makes of *body*, the inside of `$'...'`: each escape
    _SH_ANSI_C_ESCAPE matches decoded, any other backslash kept as written."""

    def decode(match):
        simple, octal, byte, short, long, control = match.groups()
        if simple is not None:
            return _SH_ANSI_C_SIMPLE[simple]
        if control is not None:
            return chr(ord(control) & 0x1F)
        number = int(octal, 8) if octal else int(byte or short or long, 16)
        return chr(number) if number <= sys.maxunicode else match.group(0)

    return _SH_ANSI_C_ESCAPE.sub(decode, body)


def _sh_unquoted(word):
    """*word* as the shell reads a command name: its quotes and backslashes
    removed and `$'...'` decoded as bash decodes it, or None when it holds an
    expansion, whose name is known only when the script runs."""
    out, i = [], 0
    while i < len(word):
        c = word[i]
        if word.startswith("$'", i):
            end = i + 2
            while word[end] != "'":
                end += 2 if word[end] == "\\" else 1
            out.append(_sh_ansi_c(word[i + 2 : end]))
            i = end + 1
        elif c in "$`":
            return None
        elif c == "\\":
            out.append(word[i + 1 : i + 2])
            i += 2
        elif c == "'":
            end = word.index("'", i + 1)
            out.append(word[i + 1 : end])
            i = end + 1
        elif c == '"':
            i += 1
            while word[i] != '"':
                if word[i] in "$`":
                    return None
                if word[i] == "\\" and word[i + 1 : i + 2] in ('"', "\\", "$", "`"):
                    i += 1
                out.append(word[i])
                i += 1
            i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _sh_run_words(words):
    """(dynamic, [command name, argument words...]) as the shell runs *words*:
    `command` / `builtin` stepped over and the name unquoted, or kept as
    written and dynamic true when it holds an expansion; None for a
    `command -v` / `-V` that only describes the command."""
    raw, rest = words[0], words[1:]
    name = _sh_unquoted(raw)
    while name in _SH_PREFIXES and rest:
        while name == "command" and len(rest) > 1 and rest[0].startswith("-"):
            if rest[0] in _SH_DESCRIBE:
                return None
            rest = rest[1:]
        raw, rest = rest[0], rest[1:]
        name = _sh_unquoted(raw)
    return name is None, [raw if name is None else name] + rest


def _sh_word_marks(words, starts, ends, functions):
    """The (start, end, red_before, zone) mark of each of one command's
    *words*, by the roles _SH_NAMING states: a held name that starts before
    red_before in a word is a mention."""
    k = 0
    while k < len(words) and words[k] in _SH_RESERVED:
        k += 1
    j = k
    while j < len(words) and _SH_ASSIGNMENT.match(words[j]):
        j += 1
    read = _sh_run_words(words[j:]) if j < len(words) else None
    naming = read is not None and (
        read[0]
        or read[1][0] in _SH_NAMING
        or read[1][0] in functions
        or (
            read[1][0] == _SH_PRINTF
            and any(w.startswith(_SH_PRINTF_VAR) for w in read[1][1:])
        )
    )
    marks = []
    for n, (word, at, end) in enumerate(zip(words, starts, ends, strict=True)):
        if naming:
            red_before = end
        elif k <= n < j:
            red_before = at + word.index("=")
        elif n == j and "/" not in word:
            red_before = end
        else:
            red_before = at
        marks.append((at, end, red_before, False))
    return marks


def shell_commands(text):
    """([(line, [command name, argument words...], dynamic, main, at)],
    [(start, end)], {at: name}, [(start, end, red_before, zone)]) for
    *text*: each simple command, the assignments and reserved words before
    it stepped over and its name read by _sh_run_words, whether that name
    holds an expansion, whether the command could end the script
    (_ShellReader's main) and the offset its name starts at; the span of
    each comment and quoted here-document body, in text order; the offset of
    each `name=$?` word a bare assignment statement binds, by _SH_BINDING's
    rule; and each word's and span's mark by _SH_NAMING's rule, ordered so
    an enclosing mark comes before the marks it holds. Raises ShellScanError
    when the text cannot be read to its end."""
    reader = _ShellReader(text)
    reader.run()
    functions = {a or b for a, b in _SH_FUNCTION.findall(text)}
    commands, bindings, marks = [], {}, list(reader.marks)
    for line, words, main, starts, ends in sorted(reader.commands, key=lambda c: c[0]):
        marks.extend(_sh_word_marks(words, starts, ends, functions))
        k = 0
        while k < len(words) and words[k] in _SH_RESERVED:
            k += 1
        statement = words[k:]
        binding = _SH_BINDING.match(statement[-1]) if statement else None
        bare = len(statement) == 1 or (
            len(statement) == 2 and statement[0] in _SH_DECLARE
        )
        if main and binding and bare:
            bindings[starts[-1]] = binding.group(1)
        while k < len(words) and _SH_ASSIGNMENT.match(words[k]):
            k += 1
        read = _sh_run_words(words[k:]) if k < len(words) else None
        if read is not None:
            dynamic, run = read
            commands.append((line, run, dynamic, main, starts[k]))
    marks.sort(key=lambda m: (m[0], -m[1]))
    return commands, sorted(reader.unread), bindings, marks


def _sh_name_uses(text, unread, name, bindings, marks):
    """([offset of each `name=$?` in *bindings*], [line of each mention of
    *name* that is no plain read]) in *text*, outside the *unread* spans, by
    the rules _SH_BINDING and _SH_NAMING state; *unread* and *marks* are in
    shell_commands' order."""
    bound, other = [], []
    pattern = re.compile(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % re.escape(name))
    # The matches come in text order, so one pass over the spans, the marks
    # and the newlines between matches keeps the scan linear: a script with
    # 25k comments and 25k reads took 31 s when each match walked every span.
    # The marks nest, so the open ones form a stack whose top is the
    # innermost, and zones counts the open marks that are zones.
    k, m, line, counted, stack, zones = 0, 0, 1, 0, [], 0
    for match in pattern.finditer(text):
        start, end = match.span()
        while k < len(unread) and unread[k][1] <= start:
            k += 1
        if k < len(unread) and unread[k][0] <= start:
            continue
        line, counted = line + text.count("\n", counted, start), start
        before = text[start - 1 : start]
        braced = text[start - 2 : start] == "${" and text[end : end + 1] == "}"
        if before == "$" or braced:
            continue
        if bindings.get(start) == name:
            bound.append(start)
            continue
        while m < len(marks) and marks[m][0] <= start:
            mark = marks[m]
            m += 1
            while stack and stack[-1][1] <= mark[0]:
                zones -= stack.pop()[3]
            stack.append(mark)
            zones += mark[3]
        while stack and stack[-1][1] <= start:
            zones -= stack.pop()[3]
        if zones or not stack or stack[-1][0] > start or start < stack[-1][2]:
            other.append(line)
    return bound, other


def _sh_handed_name(word):
    """The name *word* reads as `$name` or `${name}`, bare or inside one pair
    of double quotes, or None."""
    match = _SH_NAME_REF.match(word)
    return None if match is None else (match.group(2) or match.group(3))


def _sh_hands_on(word, held):
    """Whether *word* is the last command's status: `$?`, or, when *held*
    says the ending's name is bound before it or its every other use is
    judged at its own line, `$name` or `${name}`."""
    if _SH_LAST_STATUS.match(word):
        return True
    return held and _sh_handed_name(word) is not None


def _sh_member(word):
    """The member name `$EXIT_<NAME>` in *word* names, or None."""
    match = _SH_MEMBER.match(word)
    return None if match is None else (match.group(2) or match.group(3))


def _sh_ending_findings(head, args, known, quiet, held):
    """What is wrong with one `exit`, `exit_fail`, `exit_passthrough` or
    `return`; *held* is _sh_hands_on's."""
    said = " ".join([head] + args)
    member = _sh_member(args[0]) if args else None
    if member is not None and member not in known:
        return [
            "`%s` names EXIT_%s, which %s does not set" % (said, member, et.HELPER_SH)
        ]
    if head == _SH_RETURN:
        return _sh_return_findings(said, args, member, held)
    if head == _SH_EXIT:
        if not args:
            return [
                "`exit` with no status ends on the last command's; end with %s, "
                'or exit_passthrough "$?" for a wrapped tool\'s status' % _SH_ENDS_WELL
            ]
        if len(args) == 1 and member is not None:
            return []
        if len(args) == 1 and _SH_NUMBER.match(args[0]):
            return ["`%s` writes a number; end with %s" % (said, _SH_ENDS_WELL)]
        return [
            '`%s` is not a member; end with %s, or exit_passthrough "$?" for a '
            "wrapped tool's status" % (said, _SH_ENDS_WELL)
        ]
    if head == _SH_FAIL:
        if len(args) != 4:
            return ["`%s` takes CODE WHAT ON NEXT, four arguments" % said]
        out = []
        if member is None or member in quiet:
            out.append(
                '`%s` takes "$EXIT_<NAME>" of a member other than SUCCESS first' % said
            )
        if any(_SH_BLANK.match(part) for part in args[1:]):
            out.append(
                "`%s` has a blank message part; say what failed, on which input and "
                "what to do next" % said
            )
        return out
    if len(args) != 1:
        return ["`%s` takes one argument, the wrapped tool's status" % said]
    if member is not None or _SH_NUMBER.match(args[0]):
        return [
            "`%s` hands the script's own status, not a wrapped tool's; end with %s"
            % (said, _SH_ENDS_WELL)
        ]
    if not _sh_hands_on(args[0], held):
        return ["`%s` renames a wrapped tool's status; %s" % (said, _SH_HANDS_ON)]
    return []


def _sh_return_findings(said, args, member, held):
    """What is wrong with one `return`: it carries a member, as `exit` does,
    or hands on the last command's status, as `exit_passthrough` does."""
    if not args:
        return [
            '`return` with no status returns the last command\'s; write return "$?" '
            'to hand it on, or return "$EXIT_<NAME>"'
        ]
    if len(args) == 1 and (member is not None or _sh_hands_on(args[0], held)):
        return []
    if len(args) == 1 and _SH_NAME_REF.match(args[0]):
        return ["`%s` renames a status; %s" % (said, _SH_HANDS_ON)]
    return [
        '`%s` is not a member; return "$EXIT_<NAME>" from %s, or %s'
        % (said, et.HELPER_SH, _SH_HANDS_ON)
    ]


def _sh_unjudged(head, args, dynamic):
    """The finding at a command that could end the script but whose ending
    the gate cannot see: one named by an expansion, or an `eval`."""
    said = " ".join([head] + args)
    if dynamic:
        return (
            "`%s` runs a command named by %s, which is known only when the script "
            "runs, so the gate cannot judge whether it ends the script; name the "
            "command, or run it in a subshell `( ... )` and hand on its status "
            'with exit_passthrough "$?"' % (said, head)
        )
    return (
        "`%s` runs a string the gate cannot read, so it cannot judge whether it "
        "ends the script; run the command itself" % said
    )


def _sh_held_status_findings(text, unread, bindings, marks, commands, relpath):
    """([finding], held) for the names an `exit_passthrough` or `return` of
    *commands* hands on: a finding at each line that uses one other than as
    _SH_BINDING allows, and the offsets of the endings whose name is held:
    bound before the ending, or used other than so, which those findings
    judge instead."""
    handed = {}
    for line, (head, *args), _dynamic, _main, offset in commands:
        name = _sh_handed_name(args[0]) if len(args) == 1 else None
        if head in (_SH_PASS, _SH_RETURN) and name is not None:
            handed.setdefault(name, []).append((offset, line, " ".join([head] + args)))
    findings, held = [], set()
    for name, endings in sorted(handed.items()):
        bound, other = _sh_name_uses(text, unread, name, bindings, marks)
        held.update(
            offset
            for offset, _line, _said in endings
            if other or any(b < offset for b in bound)
        )
        _offset, at, said = endings[0]
        findings.extend(
            "%s:%d: line %d hands `%s` on as a wrapped tool's status (`%s`), and "
            "this line uses `%s` other than as %s=$?, $%s or ${%s}, so the gate "
            "cannot show it still holds that status; assign it only as %s=$? and "
            'read it only as "$%s"' % ((relpath, line, at, name, said) + (name,) * 6)
            for line in sorted(set(other))
        )
    return findings, held


def _sh_carriage_return_finding(text, relpath):
    """The finding at the first line of *text* that ends with a carriage
    return, saying where the CR sits, or None when no line does."""
    crlf = _SH_CRLF.search(text)
    if crlf is None:
        return None
    at = crlf.start()
    line = text.count("\n", 0, at) + 1
    said = "%s:%d: the line ends with a carriage return (CRLF)" % (relpath, line)
    if line == 1 and text.startswith("#!"):
        return (
            "%s in the `#!` line, which the system reads as part of the "
            "interpreter's name; %s" % (said, _SH_LF)
        )
    reader = _ShellReader(text)
    try:
        reader.run()
    except ShellScanError:
        # The CR is the file's one finding either way; where the text cannot
        # be read, the finding claims no place for it.
        return "%s; %s" % (said, _SH_LF)
    around = [span for span in reader.places if span[0] <= at < span[1]]
    place = min(around, key=lambda span: span[1] - span[0])[2] if around else None
    return said + _SH_CR_WHERE[place]


def shell_file_findings(text, relpath, known, quiet):
    """Every finding of the exit gate over one shell script: an ending not
    through the helper, a script that does not source the helper, and one
    that sources it but never ends through it. A CRLF line end is the one
    finding, because every other would follow from it."""
    return shell_file_tiers(text, relpath, known, quiet)[0]


def shell_file_tiers(text, relpath, known, quiet):
    """(shell_file_findings, the held-status findings among them), so the
    gate can hand the second to the warn-only check `exit-held-status`."""
    crlf = _sh_carriage_return_finding(text, relpath)
    if crlf is not None:
        return [crlf], []
    try:
        commands, unread, bindings, marks = shell_commands(text)
    except ShellScanError as exc:
        return [
            "%s:%d: cannot be read to its end: %s; close it so the exit gate can "
            "judge the script" % (relpath, exc.line, exc.reason)
        ], []
    held_status, held = _sh_held_status_findings(
        text, unread, bindings, marks, commands, relpath
    )
    findings = list(held_status)
    sourced, ends, needs = None, 0, []
    for line, (head, *args), dynamic, main, offset in commands:
        if main and (dynamic or head == _SH_EVAL):
            findings.append(
                "%s:%d: %s" % (relpath, line, _sh_unjudged(head, args, dynamic))
            )
        if head in _SH_SOURCE and args and sourced is None:
            target = args[0].replace('"', "").replace("'", "")
            if target.endswith("/" + _SH_HELPER_NAME):
                sourced = line
        if head in _SH_ENDINGS or head == _SH_RETURN:
            ends += head != _SH_RETURN
            if head != _SH_RETURN or (args and _sh_member(args[0])):
                needs.append((line, " ".join([head] + args)))
            findings.extend(
                "%s:%d: %s" % (relpath, line, finding)
                for finding in _sh_ending_findings(
                    head, args, known, quiet, offset in held
                )
            )
    # The helper's names are set only from the line that sources it on, and
    # the text order is the one this reader can see.
    findings.extend(
        "%s:%d: `%s` comes before line %d, which sources %s, so its names are "
        "unset there; source the helper first"
        % (relpath, line, said, sourced, et.HELPER_SH)
        for line, said in needs
        if sourced is not None and line < sourced
    )
    if sourced is None:
        findings.append(
            "%s:1: does not source %s, so it cannot end through it; add "
            '`. "$(dirname "$0")/%s"` before its first command'
            % (relpath, et.HELPER_SH, _SH_HELPER_NAME)
        )
    elif not ends:
        findings.append(
            "%s:1: never ends through %s, so it exits on its last command's "
            "status; end it with %s" % (relpath, et.HELPER_SH, _SH_ENDS_WELL)
        )
    return findings, held_status


def _walked_shell_scripts(root, cfg):
    """The shell scripts under *root* by scripts/shell_gate.py's rule, from
    the structure walk rather than git, as
    tests/integration/test_committed_secrets_gate.py `candidates` falls back:
    regular files, not symlinks, never shell_gate.HELPER_SH, none
    `shell.excluded_paths` covers."""
    excluded = sorted(cfg["excluded_paths"])
    out = []
    for dirpath, _dirs, files in cs.walk(str(root)):
        for name in files:
            full = os.path.join(dirpath, name)
            relpath = os.path.relpath(full, str(root)).replace(os.sep, "/")
            if os.path.islink(full) or not os.path.isfile(full):
                continue
            if relpath == shell_gate.HELPER_SH:
                continue
            if shell_gate.excluded_by(relpath, excluded) is not None:
                continue
            if shell_gate.kind(relpath, full, cfg) == shell_gate.SCRIPT:
                out.append(relpath)
    return sorted(out)


def shell_findings(root):
    """Every finding of the exit gate over the shell scripts of *root*: the
    files scripts/shell_gate.py `classify` calls scripts, so the shell tools
    and this gate judge the same files, which never include the helper. `shell.enabled`
    switches the shell tools only, so every script is judged whatever it
    says; a tree with none is a finding unless config/project.json
    `shell.no_scripts` gives the reason or `shell.enabled` is false. With no
    repository, as in a project generated a moment ago, it judges every
    shell script the structure walk reaches instead. Raises
    config_loader.ConfigError, git_tree.GitFailedError and OSError rather
    than judging nothing."""
    cfg = shell_gate.settings(str(root), stream=io.StringIO())
    try:
        scripts = shell_gate.classify(str(root), cfg).scripts
    except git_tree.NoGitError:
        scripts = _walked_shell_scripts(root, cfg)
    members = et.read_members(str(root))
    known = {m.name for m in members}
    quiet = {m.name for m in members if m.value == 0}
    findings, held_status = [], []
    for relpath in scripts:
        # newline="" keeps a CR the shell would read, which universal newlines
        # would drop.
        with open(Path(root) / relpath, encoding="utf-8", newline="") as handle:
            text = handle.read()
        every, held = shell_file_tiers(text, relpath, known, quiet)
        findings.extend(every)
        held_status.extend(held)
    # Off, a project with no shell script is the expected case, so the
    # switch is the reason; it never excuses a script that exists.
    stated = (cfg["no_scripts"] or "") if cfg["enabled"] else "shell.enabled is false"
    if not scripts and not stated.strip():
        findings.append(
            "config/project.json:1: no shell script to judge and shell.no_scripts "
            "gives no reason -- zero items; add a script or state the reason"
        )
    return {
        "files": len(scripts),
        "findings": sorted(findings),
        "held_status": sorted(held_status),
    }


def exit_helper_red(python_findings, shell, root):
    """The red lines of the exit gate's first check over *python_findings*
    and *shell* (shell_findings' result) in the tree at *root*. The
    held-status findings go to scripts/expiring_tier.py as `exit-held-status`,
    which warns and never fails (scripts/expiring_tier_data.py `WARN_ONLY`);
    every other finding goes as `exit-helper`, in its own tier."""
    held = collections.Counter(shell["held_status"])
    rest = sorted((collections.Counter(shell["findings"]) - held).elements())
    red = expiring_tier.apply("exit-held-status", shell["held_status"], root)
    return red + expiring_tier.apply("exit-helper", python_findings + rest, root)


# --- the tree itself -------------------------------------------------------------


def test_no_process_in_the_tree_ends_outside_the_helper():
    result = helper_findings(_ROOT)
    assert result["entries"] > 0, "no entry block was judged -- zero items"
    # A shell script is held by the same check, so one baseline covers both.
    shell = shell_findings(_ROOT)
    red = exit_helper_red(result["findings"], shell, str(_ROOT))
    assert not red, "\n".join(red)


def test_the_exit_code_table_is_what_the_enum_and_the_gate_scripts_say():
    assert et.read_members(str(_ROOT)), "the enum has no member -- zero items"
    assert not et.table_findings(str(_ROOT)), "\n".join(et.table_findings(str(_ROOT)))


def test_every_member_is_named_by_a_row_and_every_row_by_a_member():
    """The two directions, read from the guide by the repo's table reader and
    not by comparing against what the generator would write."""
    guide, _target = et.load_policy(str(_ROOT))
    text = (_ROOT / guide).read_text(encoding="utf-8")
    region = et.split_region(text, guide)[1]
    table = cs._pipe_table(region, et.MEMBER_COLUMNS)
    assert table is not None, "%s: no member table in the region" % guide
    named = {(row[0], row[1].strip("`")) for row in table[1]}
    backed = {(str(m.value), m.name) for m in et.read_members(str(_ROOT))}
    assert backed, "zero members"
    assert named == backed


def test_a_shared_module_never_ends_the_process():
    result = library_findings(_ROOT)
    assert result["modules"] > 0, "no shared module was judged -- zero items"
    red = expiring_tier.apply("exit-shared-module", result["findings"], str(_ROOT))
    assert not red, "\n".join(red)


# --- fixtures: each check can fail -------------------------------------------------

_GOOD = (
    "import sys\n"
    "from exit_codes import ExitCode, finish, report\n"
    "\n"
    "def main():\n"
    "    if len(sys.argv) > 1:\n"
    "        return report(ExitCode.USAGE, 'tool: no', sys.argv[1], 'drop it')\n"
    "    return ExitCode.SUCCESS\n"
    "\n"
    "if __name__ == '__main__':\n"
    "    finish(main())\n"
)
_GUIDE = "docs/guides/limits.md"
_MAKEFILE = "verify:\n\tpython scripts/tool.py\n"


def _tree(tmp_path, tool=_GOOD, extra=None):
    """A project with the real helper, one gate script, and a current table."""
    root = tmp_path / "proj"
    (root / "scripts").mkdir(parents=True)
    (root / "config").mkdir()
    (root / "docs" / "guides").mkdir(parents=True)
    shutil.copy(str(_ROOT / et.HELPER), str(root / et.HELPER))
    (root / "scripts" / "tool.py").write_text(tool, encoding="utf-8")
    for relpath, text in (extra or {}).items():
        (root / relpath).parent.mkdir(parents=True, exist_ok=True)
        (root / relpath).write_text(text, encoding="utf-8")
    (root / "Makefile").write_text(_MAKEFILE, encoding="utf-8")
    (root / "config" / "project.json").write_text(
        json.dumps(
            {et.BLOCK: {et.GUIDE_KEY: _GUIDE, et.TARGET_KEY: "verify"}}, sort_keys=True
        ),
        encoding="utf-8",
    )
    (root / _GUIDE).write_text(
        "# Limits\n\n%s\n%s\n\nprose\n" % (et.BEGIN, et.END), encoding="utf-8"
    )
    return root


def _generate(root):
    assert et.main([], root=str(root)) == 0


def test_a_tree_that_ends_through_the_helper_has_no_finding(tmp_path):
    root = _tree(tmp_path)
    _generate(root)
    result = helper_findings(root)
    assert result == {"files": 2, "entries": 1, "findings": []}
    assert et.table_findings(str(root)) == []


_EXIT_FORMS = {
    "sys.exit": "import sys\nsys.exit(1)\n",
    "sys.exit(main())": (
        "import sys\n\ndef main():\n    return 1\n\n"
        "if __name__ == '__main__':\n    sys.exit(main())\n"
    ),
    "aliased sys": "import sys as s\ns.exit(1)\n",
    "from sys import exit": "from sys import exit as leave\nleave(1)\n",
    "raise SystemExit": "raise SystemExit(2)\n",
    "raise SystemExit bare": "def f():\n    raise SystemExit\n",
    "SystemExit subclass": "class Stop(SystemExit):\n    pass\n",
    "SystemExit renamed": "Stop = SystemExit\n",
    "os._exit": "import os\nos._exit(3)\n",
    "from os import _exit": "from os import _exit\n",
    "exit builtin": "exit(1)\n",
    "quit builtin": "quit()\n",
    "argparse exit": "import argparse\nargparse.ArgumentParser().exit(2, 'no')\n",
    "builtins.SystemExit": "import builtins\nraise builtins.SystemExit(7)\n",
    "builtins aliased": "import builtins as b\nraise b.SystemExit(7)\n",
    "builtins.quit": "import builtins\nbuiltins.quit(7)\n",
    "__builtins__.SystemExit": "raise __builtins__.SystemExit(7)\n",
    "from builtins import SystemExit": (
        "from builtins import SystemExit as Stop\nraise Stop(7)\n"
    ),
    "from builtins import quit": "from builtins import quit as leave\nleave(7)\n",
    "a local raises": "def raises(exc):\n    raise exc\n\nraises(SystemExit)\n",
    "raised inside pytest.raises": (
        "import pytest\n\ndef f():\n    pytest.raises(ValueError, SystemExit(7))\n"
    ),
    "raised in an except type": (
        "def f(exc):\n    raise exc\n\n"
        "try:\n    pass\nexcept f(SystemExit(7)):\n    pass\n"
    ),
    "second import name": "from scripts.exit_codes import finish\n",
    "second import name 2": "import scripts.exit_codes\n",
    "second import name 3": "from scripts import exit_codes\n",
}


@pytest.mark.parametrize("form", sorted(_EXIT_FORMS))
def test_each_exit_form_outside_the_helper_is_a_finding(tmp_path, form):
    root = _tree(tmp_path, extra={"src/pkg/mod.py": _EXIT_FORMS[form]})
    findings = helper_findings(root)["findings"]
    assert findings, form
    assert all(f.startswith("src/pkg/mod.py:") for f in findings), findings
    # Green again once the exit is gone: the finding was the exit's, not the file's.
    (root / "src" / "pkg" / "mod.py").write_text("X = 1\n", encoding="utf-8")
    assert helper_findings(root)["findings"] == []


@pytest.mark.parametrize(
    "source",
    [
        "try:\n    pass\nexcept SystemExit:\n    pass\n",
        "try:\n    pass\nexcept (ValueError, SystemExit) as e:\n    print(e.code)\n",
        "import pytest\n\ndef test_x():\n    with pytest.raises(SystemExit):\n        pass\n",
        "import pytest as pt\n\ndef test_x():\n    with pt.raises(SystemExit):\n        pass\n",
        "from pytest import raises\n\ndef test_x():\n"
        "    with raises((ValueError, SystemExit)):\n        pass\n",
        "import pytest\n\ndef test_x():\n"
        "    with pytest.raises(expected_exception=SystemExit):\n        pass\n",
        "import builtins\n\ntry:\n    pass\nexcept builtins.SystemExit:\n    pass\n",
        "x = 'sys.exit(1)'\nexit_code = 3\n",
    ],
)
def test_catching_or_expecting_an_exit_is_not_a_finding(tmp_path, source):
    root = _tree(tmp_path, extra={"tests/test_mod.py": source})
    assert helper_findings(root)["findings"] == []


_BAD_ENTRIES = {
    "int return": _GOOD.replace("return ExitCode.SUCCESS", "return 0"),
    "bare failure member": _GOOD.replace(
        "return ExitCode.SUCCESS", "return ExitCode.FAILURE"
    ),
    "falls off the end": _GOOD.replace("    return ExitCode.SUCCESS\n", ""),
    "status dropped": _GOOD.replace("finish(main())", "main()"),
    "unknown member": _GOOD.replace("ExitCode.USAGE", "ExitCode.NOPE"),
    "another module's call": _GOOD.replace(
        "return ExitCode.SUCCESS", "return sys.getrecursionlimit()"
    ),
    "finish outside the block": _GOOD.replace(
        "def main():\n", "def stop():\n    finish(ExitCode.SUCCESS)\n\ndef main():\n"
    ),
    "finish of a literal": _GOOD.replace("finish(main())", "finish(1)"),
    "report of the success member": _GOOD.replace(
        "return ExitCode.SUCCESS", "return report(ExitCode.SUCCESS, 'a', 'b', 'c')"
    ),
    "status dropped, helper not imported": (
        "import sys\n\ndef main():\n    sys.stderr.write('check failed\\n')\n"
        "    return 1\n\nif __name__ == '__main__':\n    main()\n"
    ),
    "status dropped in a nested statement": (
        "def main():\n    return 1\n\n"
        "if __name__ == '__main__':\n    try:\n        main()\n"
        "    finally:\n        print('done')\n"
    ),
}
# Each line rebinds `rc` after `rc = ExitCode.SUCCESS` in a way the reader of
# returns does not follow, so the name can hold a status that is no member.
_REBINDINGS = {
    "tuple unpacking": "    rc, out = divmod(7, 8)\n",
    "starred unpacking": "    [rc, *rest] = [7, 8]\n",
    "for loop": "    for rc in (7,):\n        pass\n",
    "augmented assign": "    rc += 5\n",
    "walrus": "    if (rc := 9):\n        pass\n",
    "with as": "    with open(sys.argv[0]) as rc:\n        pass\n",
    "except as": "    try:\n        pass\n    except ValueError as rc:\n        pass\n",
    "import as": "    import os as rc\n",
    "global": "    global rc\n",
    "delete": "    del rc\n",
    "nested def": "    def rc():\n        return 7\n",
}
_REBOUND = _GOOD.replace(
    "    return ExitCode.SUCCESS\n", "    rc = ExitCode.SUCCESS\n%s    return rc\n"
)
_BAD_ENTRIES.update({"rebound by " + k: _REBOUND % v for k, v in _REBINDINGS.items()})
_BAD_ENTRIES["rebound by a parameter default"] = (
    "from exit_codes import ExitCode, finish\n\nrc = ExitCode.SUCCESS\n\n"
    "def main(rc=7):\n    return rc\n\nif __name__ == '__main__':\n    finish(main())\n"
)
_BAD_ENTRIES["rebound by another function's global"] = (
    "from exit_codes import ExitCode, finish\n\nrc = ExitCode.SUCCESS\n\n"
    "def spoil():\n    global rc\n    rc = 7\n\n"
    "def main():\n    spoil()\n    return rc\n\n"
    "if __name__ == '__main__':\n    finish(main())\n"
)
_BAD_ENTRIES["rebound in a module-level branch"] = (
    "import sys\nfrom exit_codes import ExitCode, finish\n\nrc = ExitCode.SUCCESS\n"
    "if sys.argv:\n    rc, _ = 7, 8\n\n"
    "def main():\n    return rc\n\nif __name__ == '__main__':\n    finish(main())\n"
)

# `passthrough` marks a wrapped tool's status. Handed main's own result, or a
# status this script wrote itself, it would label the script's choice as a
# tool's and let a main returning integers past the gate.
_INT_MAIN = _GOOD.replace("return ExitCode.SUCCESS", "return 0").replace(
    "return report(ExitCode.USAGE, 'tool: no', sys.argv[1], 'drop it')", "return 2"
)
_BAD_ENTRIES["finish of passthrough of main"] = _INT_MAIN.replace(
    "finish(main())", "finish(passthrough(main()))"
).replace("finish, report", "finish, passthrough, report")
_BAD_ENTRIES["finish of passthrough of a name bound to main"] = _INT_MAIN.replace(
    "    finish(main())\n", "    rc = main()\n    finish(passthrough(rc))\n"
).replace("finish, report", "finish, passthrough, report")
_BAD_ENTRIES["passthrough of a module function returning integers"] = (
    "import sys\n"
    "from exit_codes import ExitCode, finish, passthrough\n"
    "\n"
    "def main2():\n"
    "    return 1 if len(sys.argv) > 1 else 0\n"
    "\n"
    "def main():\n"
    "    return passthrough(main2())\n"
    "\n"
    "if __name__ == '__main__':\n"
    "    finish(main())\n"
)
# The same status dressed as a computed one: a builtin, an `or`, a sign.
for _label, _dressed in (
    ("through a builtin", "int(main2())"),
    ("or a literal", "main2() or 0"),
):
    _BAD_ENTRIES["passthrough of a module function returning integers " + _label] = (
        _BAD_ENTRIES["passthrough of a module function returning integers"].replace(
            "passthrough(main2())", "passthrough(%s)" % _dressed
        )
    )
_BAD_ENTRIES["passthrough of a negative literal"] = _BAD_ENTRIES[
    "passthrough of a module function returning integers"
].replace("passthrough(main2())", "passthrough(-1)")


def test_a_name_bound_only_by_plain_assignments_is_followed(tmp_path):
    """The control for the rebinding fixtures: the same script without the
    rebinding line has no finding, annotated or not."""
    for line in ("", "    rc: ExitCode = ExitCode.SUCCESS\n", "    other, x = 1, 2\n"):
        root = _tree(tmp_path / str(len(line)), tool=_REBOUND % line)
        assert helper_findings(root)["findings"] == [], line


def test_a_passthrough_of_a_wrapped_status_is_no_finding(tmp_path):
    """The control for the passthrough fixtures: a status read from the child
    the script ran, where it ran it, passes through."""
    tool = (
        "import subprocess\n"
        "from exit_codes import finish, passthrough\n"
        "\n"
        "def main():\n"
        "    return passthrough(subprocess.run(['true']).returncode)\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    finish(main())\n"
    )
    root = _tree(tmp_path, tool=tool)
    assert helper_findings(root)["findings"] == []


@pytest.mark.parametrize(
    "block",
    [
        "    main()\n",
        "    print(helper())\n",
        "    text = helper()\n    print(text)\n",
        "    import asyncio\n    asyncio.run(serve())\n",
    ],
)
def test_an_entry_block_that_drops_no_value_needs_no_finish(tmp_path, block):
    """An entry block with no status to hand over (a server, a demo): it calls
    a function that returns nothing, or it uses the value a function returns."""
    source = (
        "def main():\n    print('served')\n\n"
        "def helper():\n    return 'text'\n\n"
        "async def serve():\n    return None\n\n"
        "if __name__ == '__main__':\n" + block
    )
    root = _tree(tmp_path, extra={"src/pkg/__main__.py": source})
    assert helper_findings(root)["findings"] == []


@pytest.mark.parametrize("case", sorted(_BAD_ENTRIES))
def test_an_entry_that_does_not_return_members_through_finish_is_a_finding(
    tmp_path, case
):
    assert _BAD_ENTRIES[case] != _GOOD, case
    root = _tree(tmp_path, tool=_BAD_ENTRIES[case])
    findings = helper_findings(root)["findings"]
    assert findings, case
    assert all(f.startswith("scripts/tool.py") for f in findings), findings


_BLANK_PARTS = {
    "blank what": "report(ExitCode.USAGE, '', sys.argv[1], 'drop it')",
    "blank on": "report(ExitCode.USAGE, 'tool: no', '  ', 'drop it')",
    "blank next": "report(ExitCode.USAGE, 'tool: no', sys.argv[1], '')",
    "none part": "report(ExitCode.USAGE, 'tool: no', None, 'drop it')",
    "missing part": "report(ExitCode.USAGE, 'tool: no', sys.argv[1])",
    "blank keyword": "report(ExitCode.USAGE, 'tool: no', sys.argv[1], next_step='')",
    "starred": "report(ExitCode.USAGE, *sys.argv[1:4])",
}


@pytest.mark.parametrize("case", sorted(_BLANK_PARTS))
def test_a_blank_or_missing_message_part_is_a_finding(tmp_path, case):
    good = "report(ExitCode.USAGE, 'tool: no', sys.argv[1], 'drop it')"
    assert good in _GOOD
    root = _tree(tmp_path, tool=_GOOD.replace(good, _BLANK_PARTS[case]))
    findings = helper_findings(root)["findings"]
    assert len(findings) == 1 and "scripts/tool.py:6: `report`" in findings[0], findings


def test_a_blank_part_of_fail_is_a_finding(tmp_path):
    source = (
        "import exit_codes\n\ndef stop(path):\n"
        "    exit_codes.fail(exit_codes.ExitCode.USAGE, 'no', path, ' ')\n"
    )
    root = _tree(tmp_path, extra={"scripts/lib.py": source})
    findings = helper_findings(root)["findings"]
    assert len(findings) == 1 and "`fail` has a blank `next_step`" in findings[0]


@pytest.mark.parametrize(
    "call",
    [
        "exit_codes.fail(7, 'a', path, 'c')",
        "exit_codes.report(7, 'a', path, 'c')",
        "exit_codes.fail(exit_codes.ExitCode.SUCCESS, 'a', path, 'c')",
        "exit_codes.report(code=path, what='a', on=path, next_step='c')",
        "exit_codes.fail(what='a', on=path, next_step='c')",
    ],
)
def test_a_code_the_helper_would_refuse_is_a_finding_in_any_module(tmp_path, call):
    """`report` raises on a code that is not a failure member, so the call
    would end on a traceback; a module with no entry block is read too."""
    source = "import exit_codes\n\ndef stop(path):\n    return %s\n" % call
    root = _tree(tmp_path, extra={"scripts/lib.py": source})
    findings = helper_findings(root)["findings"]
    assert len(findings) == 1 and findings[0].startswith("scripts/lib.py:4:"), findings


def _add_member(root, annotation=""):
    """Append to *root*'s enum a member its list does not hold yet, and return
    its name: one past the highest value, so the fixture holds whatever
    members a project has added. The line goes in at the class's last line,
    found in the syntax tree, so it does not depend on how the members before
    it are laid out. *annotation* is written between the name and the `=`."""
    path = root / et.HELPER
    text = path.read_text(encoding="utf-8")
    members = et.read_members(str(root))
    enum = next(
        node
        for node in ast.parse(text).body
        if isinstance(node, ast.ClassDef) and node.name == et.ENUM
    )
    name = "PLANTED_%d" % len(members)
    assert name not in {m.name for m in members}
    lines = text.splitlines(True)
    lines.insert(
        enum.end_lineno,
        "    %s%s = (%d, 'it was planted', 'nothing')\n"
        % (name, annotation, members[-1].value + 1),
    )
    path.write_text("".join(lines), encoding="utf-8")
    return name


def test_a_member_added_without_regenerating_is_a_finding(tmp_path):
    root = _tree(tmp_path)
    _generate(root)
    assert et.table_findings(str(root)) == []
    name = _add_member(root)
    findings = et.table_findings(str(root))
    assert findings == ["%s: the exit-code table names no member `%s`" % (_GUIDE, name)]
    assert et.main(["--check"], root=str(root)) == 1
    _generate(root)
    assert et.table_findings(str(root)) == []


def test_an_annotated_member_is_refused_not_skipped(tmp_path):
    """`NAME: tuple = (...)` is a member at run time; a reader that skipped it
    would call a table without its row current."""
    root = _tree(tmp_path)
    _generate(root)
    _add_member(root, annotation=": tuple")
    findings = et.table_findings(str(root))
    assert len(findings) == 1 and "%s:" % et.HELPER in findings[0], findings
    assert et.main(["--check"], root=str(root)) == 2


def test_a_table_row_no_member_backs_is_a_finding(tmp_path):
    root = _tree(tmp_path)
    _generate(root)
    guide = root / _GUIDE
    text = guide.read_text(encoding="utf-8")
    last = et.read_members(str(root))[-1]
    row = "| %d | `%s` |" % (last.value, last.name)
    assert text.count(row) == 1
    guide.write_text(
        text.replace(
            row, "| %d | `GHOST` | nothing | nothing |\n" % (last.value + 1) + row
        ),
        encoding="utf-8",
    )
    findings = et.table_findings(str(root))
    assert len(findings) == 1 and "`GHOST`, which nothing backs" in findings[0]
    assert et.main(["--check"], root=str(root)) == 1


def test_a_script_row_that_says_another_code_is_a_finding(tmp_path):
    root = _tree(tmp_path)
    _generate(root)
    guide = root / _GUIDE
    text = guide.read_text(encoding="utf-8")
    row = "| `scripts/tool.py` | 0, 2 |"
    assert text.count(row) == 1
    guide.write_text(text.replace(row, "| `scripts/tool.py` | 0 |"), encoding="utf-8")
    findings = et.table_findings(str(root))
    assert len(findings) == 1 and "script `scripts/tool.py`" in findings[0]


def test_a_tree_with_no_python_file_is_an_error_not_a_pass(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(st.SourceTreeError, match="zero items"):
        helper_findings(tmp_path / "empty")


def test_a_file_that_does_not_parse_is_an_error_not_a_skip(tmp_path):
    root = _tree(tmp_path, extra={"src/bad.py": "def (:\n"})
    with pytest.raises(st.SourceTreeError, match="src/bad.py"):
        helper_findings(root)


# --- fixtures: a shared module never ends the process -----------------------------

_LAYERS = {"search_roots": ["", "scripts/"], "order": [["scripts"]]}
_USER = "import lib\n\nlib.check()\n"


def _shared(tmp_path, lib, exempt=None, user=_USER):
    """A project whose scripts/user.py imports scripts/lib.py."""
    layers = dict(_LAYERS)
    if exempt is not None:
        layers["may_end_the_process"] = exempt
    root = _tree(tmp_path, extra={"scripts/lib.py": lib, "scripts/user.py": user})
    (root / "config" / "project.json").write_text(
        json.dumps({"import_layers": layers}), encoding="utf-8"
    )
    return root


_FAIL_IN_A_FUNCTION = (
    "from exit_codes import ExitCode, fail\n"
    "\n"
    "def check():\n"
    "    fail(ExitCode.USAGE, 'lib: bad', 'input', 'fix it')\n"
)


@pytest.mark.parametrize(
    "lib, line, name",
    [
        (_FAIL_IN_A_FUNCTION, 4, "fail"),
        (
            "import exit_codes\n"
            "exit_codes.fail(exit_codes.ExitCode.USAGE, 'lib: bad', 'in', 'fix')\n",
            2,
            "fail",
        ),
        (
            "from exit_codes import ExitCode, finish\n"
            "\n"
            "def check():\n"
            "    finish(ExitCode.SUCCESS)\n",
            4,
            "finish",
        ),
        (
            "import exit_codes\n"
            "_f = exit_codes.fail\n"
            "\n"
            "def check():\n"
            "    _f(exit_codes.ExitCode.USAGE, 'lib: bad', 'input', 'fix it')\n",
            5,
            "fail",
        ),
        (
            "from exit_codes import ExitCode, fail\n"
            "die = fail\n"
            "stop = die\n"
            "\n"
            "def check():\n"
            "    stop(ExitCode.USAGE, 'lib: bad', 'input', 'fix it')\n",
            6,
            "fail",
        ),
        (
            "import exit_codes\n"
            "helper = exit_codes\n"
            "\n"
            "def check():\n"
            "    helper.fail(helper.ExitCode.USAGE, 'lib: bad', 'input', 'fix it')\n",
            5,
            "fail",
        ),
    ],
    ids=[
        "fail in a function",
        "fail at module level",
        "finish in a function",
        "fail rebound to a name",
        "fail rebound twice",
        "the helper module rebound to a name",
    ],
)
def test_a_shared_module_that_ends_the_process_is_a_finding(tmp_path, lib, line, name):
    result = library_findings(_shared(tmp_path, lib))
    assert result["findings"] == [
        "scripts/lib.py:%d: %s is imported by scripts/user.py, so it must raise or "
        "return, never end the process; return to the entry point and let it call "
        "finish" % (line, name)
    ], result


def test_an_entry_block_or_passthrough_in_a_shared_module_is_no_finding(tmp_path):
    lib = (
        "from exit_codes import ExitCode, finish, passthrough\n"
        "\n"
        "def check():\n"
        "    return passthrough(3)\n"
        "\n"
        "def main():\n"
        "    return ExitCode.SUCCESS\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    finish(main())\n"
    )
    result = library_findings(_shared(tmp_path, lib))
    assert result == {"modules": 1, "findings": []}, result


def test_a_module_only_tests_import_is_not_shared(tmp_path):
    root = _shared(tmp_path, _FAIL_IN_A_FUNCTION, user="")
    (root / "tests").mkdir()
    (root / "tests" / "test_lib.py").write_text("import lib\n", encoding="utf-8")
    result = library_findings(root)
    assert result == {"modules": 0, "findings": []}, result


def test_an_exempt_module_is_no_finding(tmp_path):
    exempt = {"scripts/lib.py": "it runs before its importer can hold a main"}
    result = library_findings(_shared(tmp_path, _FAIL_IN_A_FUNCTION, exempt))
    assert result["findings"] == [], result


def test_a_stale_exemption_is_a_finding(tmp_path):
    exempt = {"scripts/lib.py": "it once ended the process"}
    result = library_findings(_shared(tmp_path, "def check():\n    return 1\n", exempt))
    assert result["findings"] == [
        "config/project.json: import_layers.may_end_the_process names "
        "`scripts/lib.py`, which is no shared module that ends the process; "
        "delete the entry"
    ], result


def test_an_exemption_with_a_blank_reason_is_an_error_not_a_pass(tmp_path):
    root = _shared(tmp_path, _FAIL_IN_A_FUNCTION, {"scripts/lib.py": " -- "})
    with pytest.raises(st.SourceTreeError, match="may_end_the_process"):
        library_findings(root)


# --- fixtures: a shell script ends only through the helper ------------------------

_SH_HEAD = '#!/bin/sh\n. "$(dirname "$0")/exit_codes.sh"\n'
_SH_TAIL = 'exit "$EXIT_SUCCESS"\n'
_SH_GOOD = (
    _SH_HEAD
    + '[ "$#" -eq 0 ] || exit_fail "$EXIT_USAGE" "tool: no argument" "$1" "drop it"\n'
    + "shellcheck tool.sh\n"
    + "status=$?\n"
    + '[ "$status" -eq 0 ] || exit_passthrough "$status"\n'
    + _SH_TAIL
)


def _sh_tree(
    tmp_path,
    monkeypatch,
    scripts,
    no_scripts=None,
    excluded=None,
    enabled=True,
    git=True,
):
    """A git work tree holding the real Python helper, a shell block and
    *scripts* {relpath: text}; nothing is committed, and git lists untracked
    files, as a commit could carry them."""
    work = tmp_path / "work"
    work.mkdir()
    for key, value in hermetic_git.git_env_vars(work).items():
        monkeypatch.setenv(key, value)
    root = tmp_path / "proj"
    (root / "scripts").mkdir(parents=True)
    (root / "config").mkdir()
    shutil.copy(str(_ROOT / et.HELPER), str(root / et.HELPER))
    shell = {
        "enabled": enabled,
        "no_scripts": no_scripts,
        "excluded_paths": excluded or {},
    }
    (root / "config" / "project.json").write_text(
        json.dumps({"shell": shell}, sort_keys=True), encoding="utf-8"
    )
    for relpath, text in scripts.items():
        (root / relpath).parent.mkdir(parents=True, exist_ok=True)
        (root / relpath).write_text(text, encoding="utf-8")
    if not git:
        return root
    subprocess.run(
        ["git", "init", "-q"],
        cwd=str(root),
        env=hermetic_git.git_env(work),
        check=True,
        capture_output=True,
    )
    return root


_SH_PASSES = {
    "the good script": "",
    "a braced member": 'exit "${EXIT_USAGE}"\n',
    "an unquoted member": "exit $EXIT_USAGE\n",
    "a wrapped status": 'shellcheck x.sh || exit_passthrough "$?"\n',
    "a comment": "# exit 3\n",
    "a double-quoted word": 'echo "exit 3; exit $?"\n',
    "a single-quoted word": "echo 'exit 3'\n",
    "a here-document body": "cat <<EOF\nexit 3\nEOF\n",
    "a quoted here-document": "cat <<-'END'\n\texit 3\n\tEND\n",
    "a member under a keyword": 'if true; then exit "$EXIT_FAILURE"; fi\n',
    "a descriptor redirection": 'echo x >&2 2>/dev/null\nexit "$EXIT_USAGE" 2>&1\n',
    "a quoted command name": '"exit" "$EXIT_USAGE"\n',
    "a query of the exit builtin": "command -v exit >/dev/null\n",
    "a status held by local": 'f() {\n    false\n    local rc="$?"\n    exit_passthrough "$rc"\n}\n',
    "a braced status name": 'false\nrc=${?}\nexit_passthrough "${rc}"\n',
    "a return of a member": 'f() { return "$EXIT_USAGE"; }\n',
    "a return of the last status": 'f() { false; return "$?"; }\n',
    "a return of a held status": 'f() { false; rc=$?; return "$rc"; }\n',
    "a quote inside a quoted substitution": 'echo "$(printf \'"\')"\n',
    "a quoted brace in an expansion": 'echo ${y:-"}"}\n',
    "a single-quoted brace in an expansion": "echo ${y:-'{'}\n",
    "a quoted brace in a quoted expansion": 'echo "${y:-"}"}"\n',
    "a literal single quote in a quoted expansion": 'echo "${y:-\'}"\n',
    "a nested expansion": "echo ${y:-${z:-a}}\n",
    "a continued failure": 'exit_fail "$EXIT_USAGE" \\\n  "tool: no input" none "pass one"\n',
    "plain reads of a held status": (
        'false\nrc=$?\necho "$rc" ${rc} $rc "${rc}"\n'
        '[ "$rc" -eq 0 ] || exit_passthrough "$rc"\n'
    ),
    "a status held by local in two functions": (
        'f() { false; local rc=$?; return "$rc"; }\n'
        'g() { false; local rc="${?}"; exit_passthrough "$rc"; }\n'
    ),
    "a held status named in a comment": (
        'false\nrc=$? # rc=3 here would rename it\nexit_passthrough "$rc"\n'
    ),
    "case patterns named exit and quit": 'case "$1" in exit|quit) echo stop ;; esac\n',
    "a case pattern named return": (
        'case "$1" in\n  return) : ;;\n  "exit") : ;;\n  (\'quit\') : ;;\n'
        "  *) : ;;\nesac\n"
    ),
    "a case pattern inside a substitution": (
        'x=$(case "$1" in exit) echo a ;; return) echo b ;; esac)\n'
    ),
    "a last case clause with no terminator": 'case "$1" in exit) :\nesac\n',
    "case clauses that fall through": (
        'case "$1" in exit) : ;& return) : ;;& *) : ;; esac\n'
    ),
    "a case nested in a case body": (
        'case "$1" in a) case "$2" in exit) : ;; esac ;; return) : ;; esac\n'
    ),
    "a case subject on the next line": 'case "$1"\nin exit) : ;; esac\n',
    "process substitutions as arguments": "diff <(sort a) <(sort b)\n",
    "a redirection from a process substitution": (
        "while read -r l; do :; done < <(ls)\n"
    ),
    "a redirection to a process substitution": "echo x > >(cat) 2> >(cat >&2)\n",
    "a process substitution inside a word": "echo a<(ls)b\n",
    "an expansion named command in a substitution": 'v=$("$cmd" --version)\n',
    "an expansion named command in a subshell": '( "$cmd" 3 )\nexit_passthrough "$?"\n',
    "an expansion named command piped on": '"$cmd" 3 | cat\n"$@" |& cat\n',
    "an expansion named command in the background": '"$cmd" 3 &\nwait\n',
    "an eval piped on with |&": 'eval "$x" |& cat\n',
    "an eval in the background before a redirection": 'eval "$x" & >log\nwait\n',
    "an eval in a process substitution": 'cat <(eval "$x")\n',
    "an eval in a backquote": 'v=`eval "$x"`\n',
    "an ANSI-C quoted word": "echo $'it\\'s'\n",
    "an array append of an expansion": 'args+=("$a")\n',
    "an array append of an option and an expansion": 'args+=(-v "$f")\n',
    "a string append to PATH": 'PATH+=":$HOME/bin"\n',
    "a string append holding an expansion": 'opts+=" --x=$v"\n',
    "an append before a command": 'opts+=" -q" true\n',
    "an ANSI-C quoted brace in an expansion": "echo ${y:-$'}'}\n",
    "an ANSI-C quoted name that is not exit": "$'exit 3'\n",
    "an array assignment": "a=(exit quit)\n",
    "an appended array": "a+=(exit)\n",
    "an array after declare": "declare -a a=(exit)\n",
    "an array with a quoted parenthesis": "a=(\")\" exit '(')\n",
    "an array over two lines with a comment": "a=(exit # one\n  return)\n",
    "a status bound by export": 'false\nexport rc=$?\nexit_passthrough "$rc"\n',
    "a status bound by declare": 'false\ndeclare rc="$?"\nexit_passthrough "$rc"\n',
    "a status bound in an else branch": (
        'if true; then :; else rc=$?; fi\nexit_passthrough "$rc"\n'
    ),
    "a status bound and handed on in one line": 'false; rc=$?; exit_passthrough "$rc"\n',
    "a held status named in a quoted here-document": (
        "false\nrc=$?\ncat <<'EOF'\nrc=3\nEOF\nexit_passthrough \"$rc\"\n"
    ),
}


@pytest.mark.parametrize("body", list(_SH_PASSES.values()), ids=list(_SH_PASSES))
def test_a_shell_script_that_ends_through_the_helper_has_no_finding(
    tmp_path, monkeypatch, body
):
    script = _SH_GOOD.replace(_SH_TAIL, body + _SH_TAIL)
    root = _sh_tree(tmp_path, monkeypatch, {"scripts/tool.sh": script})
    assert shell_findings(root) == {"files": 1, "findings": [], "held_status": []}


# The fragments of the findings at a command whose name holds an expansion and
# at an `eval`, where either could end the script.
_SH_UNJUDGED_NAME = "the gate cannot judge whether it ends the script"
_SH_UNREAD_STRING = "runs a string the gate cannot read"
# The fragment of the finding at a use of a handed-on name that is no plain read.
_SH_CANNOT_SHOW = "so the gate cannot show it still holds that status"
# (body placed on line 3, its finding's line, a fragment of the finding)
_SH_FINDINGS = {
    "a number": ("exit 3\n", 3, "`exit 3` writes a number"),
    "a quoted number": ('exit "3"\n', 3, "writes a number"),
    "the last status": ("exit $?\n", 3, "`exit $?` is not a member"),
    "no status": ("exit\n", 3, "`exit` with no status"),
    "an unknown member": ('exit "$EXIT_NOPE"\n', 3, "names EXIT_NOPE"),
    "two words": ('exit "$EXIT_USAGE" 2\n', 3, "is not a member"),
    "a failure that is SUCCESS": (
        'exit_fail "$EXIT_SUCCESS" a b c\n',
        3,
        "a member other than SUCCESS",
    ),
    "a failure that is a number": ("exit_fail 3 a b c\n", 3, "other than SUCCESS"),
    "a failure of three parts": ('exit_fail "$EXIT_USAGE" a b\n', 3, "four"),
    "a blank part": ('exit_fail "$EXIT_USAGE" a "" c\n', 3, "blank message part"),
    "a space part": ("exit_fail \"$EXIT_USAGE\" a ' ' c\n", 3, "blank message part"),
    "a passthrough of a number": ("exit_passthrough 3\n", 3, "own status"),
    "a passthrough of a member": (
        'exit_passthrough "$EXIT_FAILURE"\n',
        3,
        "own status",
    ),
    "a passthrough of nothing": ("exit_passthrough\n", 3, "takes one argument"),
    "under a keyword": ("if true; then exit 1; fi\n", 3, "`exit 1`"),
    "after an and": ("true && exit 1\n", 3, "`exit 1`"),
    "after an or": ("false || exit 1\n", 3, "`exit 1`"),
    "in a subshell": ("(exit 1)\n", 3, "`exit 1`"),
    "in a substitution": ("x=$(exit 1)\n", 3, "`exit 1`"),
    "in a backquote": ("x=`exit 1`\n", 3, "`exit 1`"),
    "in a substitution inside an expansion": (
        "echo ${y:-$(exit 3)}\n",
        3,
        "`exit 3`",
    ),
    "after an expansion holding a quoted brace": (
        'echo ${y:-"}"}\nexit 1\n',
        4,
        "`exit 1`",
    ),
    "in a quoted substitution": ('x="$(exit 3)"\n', 3, "`exit 3`"),
    "in a quoted backquote": ('x="`exit 3`"\n', 3, "`exit 3`"),
    "in a substitution inside a quoted word": (
        'echo "a $(exit 3) b"\n',
        3,
        "`exit 3`",
    ),
    "in a quoted substitution after a quoted newline": (
        'echo "a\n$(exit 3)"\n',
        4,
        "`exit 3`",
    ),
    "after an assignment": ("x=1 exit 1\n", 3, "`exit 1`"),
    "before a comment": ("exit 1 # done\n", 3, "`exit 1`"),
    "after a here-document": ("cat <<EOF\nx\nEOF\nexit 1\n", 6, "`exit 1`"),
    "after a continued line": ("echo a \\\n  b\nexit 1\n", 5, "`exit 1`"),
    "after a quoted newline": ('echo "a\nb"\nexit 1\n', 5, "`exit 1`"),
    "a descriptor taken for a status": ("exit 1>&2\n", 3, "`exit` with no status"),
    "an open quote": ("echo 'a\n", 3, "a single quote is never closed"),
    "an open here-document": ("cat <<EOF\nx\n", 3, "never closed by EOF"),
    "an arithmetic exit": ("exit $((1 + 2))\n", 3, "is not a member"),
    "a quoted exit": ('"exit" 3\n', 3, "writes a number"),
    "an escaped exit": ("\\exit 3\n", 3, "writes a number"),
    "a split quoted exit": ("e'xi't 3\n", 3, "writes a number"),
    "command exit": ("command exit 3\n", 3, "writes a number"),
    "command -p exit": ("command -p exit 3\n", 3, "writes a number"),
    "builtin exit": ("builtin exit 3\n", 3, "writes a number"),
    "a passthrough of a name never assigned": (
        'exit_passthrough "$status"\n',
        3,
        "renames",
    ),
    "a passthrough of a renamed status": (
        'status=3\nexit_passthrough "$status"\n',
        3,
        _SH_CANNOT_SHOW,
    ),
    "a passthrough of a status assigned twice": (
        'false\nstatus=$?\nstatus=1\nexit_passthrough "$status"\n',
        5,
        _SH_CANNOT_SHOW,
    ),
    "a passthrough of a loop variable": (
        'for s in 1; do exit_passthrough "$s"; done\n',
        3,
        _SH_CANNOT_SHOW,
    ),
    "a passthrough of a read variable": (
        'read -r s\nexit_passthrough "$s"\n',
        3,
        _SH_CANNOT_SHOW,
    ),
    "a passthrough of a positional": ('exit_passthrough "$1"\n', 3, "renames"),
    "a passthrough of arithmetic": (
        'exit_passthrough "$((1 + 2))"\n',
        3,
        "renames",
    ),
    "a return of a number": ("f() {\n    return 3\n}\n", 4, "`return 3`"),
    "a return of zero": ("f() { return 0; }\n", 3, "`return 0`"),
    "a bare return": ("f() { true; return; }\n", 3, "`return` with no status"),
    "a return of arithmetic": ("f() { return $((2)); }\n", 3, "`return $((2))`"),
    "a held status written in an unquoted here-document": (
        'false\nrc=$?\ncat <<EOF\n${rc:=3}\nEOF\nexit_passthrough "$rc"\n',
        6,
        _SH_CANNOT_SHOW,
    ),
    "an exit in a case body": ('case "$1" in exit) exit 3 ;; esac\n', 3, "`exit 3`"),
    "an exit in a case body on its own line": (
        'case "$1" in\n  exit)\n    exit 3\n    ;;\nesac\n',
        5,
        "`exit 3`",
    ),
    "an exit in a case body inside a substitution": (
        'x=$(case "$1" in exit) exit 3 ;; esac)\n',
        3,
        "`exit 3`",
    ),
    "an exit in a case subject": (
        'case "$(exit 3)" in *) : ;; esac\n',
        3,
        "`exit 3`",
    ),
    "an exit after a case": ("case x in exit) : ;; esac\nexit 3\n", 4, "`exit 3`"),
    "an exit in a last clause with no terminator": (
        "case x in a) exit 3\nesac\n",
        3,
        "`exit 3`",
    ),
    "a case never closed": ("case x in a) : ;;\n", 3, "a `case` is never closed"),
    "a case with no in": ("case x a) : ;; esac\n", 3, "a `case` names no `in`"),
    "in a process substitution": ("diff <(exit 3) b\n", 3, "`exit 3`"),
    "in an output process substitution": ("tee >(exit 3)\n", 3, "`exit 3`"),
    "in a process substitution redirected from": (
        "while :; do :; done < <(exit 3)\n",
        3,
        "`exit 3`",
    ),
    "a redirection with no target": (
        "echo x >\n",
        3,
        "cannot be read to its end: a redirection names no target",
    ),
    "a redirection before a separator": (
        "cat < ; :\n",
        3,
        "a redirection names no target",
    ),
    "a redirection before a parenthesis": (
        "echo x >>(cat)\n",
        3,
        "a redirection names no target",
    ),
    "a command named by an expansion": ("x=exit; $x 3\n", 3, _SH_UNJUDGED_NAME),
    "a command named by a braced expansion": ("${x} 3\n", 3, _SH_UNJUDGED_NAME),
    "a command named by a quoted expansion": ('"$cmd" 3\n', 3, _SH_UNJUDGED_NAME),
    "a command named by a backquote": ("`echo exit` 3\n", 3, _SH_UNJUDGED_NAME),
    "a command named by an expansion after command": (
        'command "$x" 3\n',
        3,
        _SH_UNJUDGED_NAME,
    ),
    "a command named by an expansion after an or": (
        'true || "$x" 3\n',
        3,
        _SH_UNJUDGED_NAME,
    ),
    "a command named by an expansion last in a pipeline": (
        'cat | "$x" 3\n',
        3,
        _SH_UNJUDGED_NAME,
    ),
    "a command named by an expansion before &>": (
        "x=exit; $x 3 &>/dev/null\n",
        3,
        _SH_UNJUDGED_NAME,
    ),
    "an eval before &>": ('eval "exit 3" &>/dev/null\n', 3, _SH_UNREAD_STRING),
    "an eval before &>>": ('eval "exit 3" &>>log\n', 3, _SH_UNREAD_STRING),
    "an eval before >&": ('eval "exit 3" >&2\n', 3, _SH_UNREAD_STRING),
    "an eval before <&": ('eval "exit 3" <&0\n', 3, _SH_UNREAD_STRING),
    "an eval after &&": ('true && eval "exit 3"\n', 3, _SH_UNREAD_STRING),
    "an eval in a case clause ended by ;&": (
        'case x in a) eval "exit 3" ;& b) : ;; esac\n',
        3,
        _SH_UNREAD_STRING,
    ),
    "an eval in a case clause ended by ;;&": (
        'case x in a) eval "exit 3" ;;& b) : ;; esac\n',
        3,
        _SH_UNREAD_STRING,
    ),
    "all arguments run in a function": ('f() { "$@"; }\n', 3, _SH_UNJUDGED_NAME),
    "an eval": ('eval "exit 3"\n', 3, _SH_UNREAD_STRING),
    "an eval after command": ('command eval "exit 3"\n', 3, _SH_UNREAD_STRING),
    "an ANSI-C quoted exit": ("$'exit' 3\n", 3, "writes a number"),
    "an ANSI-C escaped exit": ("$'\\x65xit' 3\n", 3, "writes a number"),
    "an octal escaped exit": ("$'\\145xit' 3\n", 3, "writes a number"),
    "an exit after an ANSI-C quoted quote": (
        "echo $'it\\'s'; exit 3\n",
        3,
        "`exit 3`",
    ),
    "an exit in an array's substitution": ("a=($(exit 3))\n", 3, "`exit 3`"),
    "an exit after an array": ("a=(x\n  y)\nexit 3\n", 5, "`exit 3`"),
    "an array never closed": ("a=(x\n", 3, "an array is never closed"),
    "an exit in a function defined with the keyword": (
        "function f { exit 3; }\n",
        3,
        "`exit 3`",
    ),
    "an exit in a keyword function with its brace below": (
        "if true; then function f\n{\n  exit 3\n}\nfi\n",
        5,
        "`exit 3`",
    ),
    "a return of a renamed status": (
        'f() { s=2; return "$s"; }\n',
        3,
        _SH_CANNOT_SHOW,
    ),
    "a continued failure of three parts": (
        'exit_fail "$EXIT_USAGE" \\\n  "tool: no input" none\n',
        3,
        "four",
    ),
    "a return of an unknown member": (
        'f() { return "$EXIT_NOPE"; }\n',
        3,
        "names EXIT_NOPE",
    ),
}


@pytest.mark.parametrize("case", list(_SH_FINDINGS.values()), ids=list(_SH_FINDINGS))
def test_each_shell_ending_outside_the_helper_is_a_finding_at_its_line(
    tmp_path, monkeypatch, case
):
    body, line, fragment = case
    script = _SH_HEAD + body + _SH_TAIL
    root = _sh_tree(tmp_path, monkeypatch, {"scripts/tool.sh": script})
    result = shell_findings(root)
    assert result["files"] == 1
    assert len(result["findings"]) == 1, result
    (finding,) = result["findings"]
    assert finding.startswith("scripts/tool.sh:%d: " % line), finding
    assert fragment in finding, finding


# Each line writes `rc`, or uses it in a way the gate cannot show is a plain
# read, after `rc=$?` and before `exit_passthrough "$rc"` hands it on.
_SH_STATUS_WRITES = {
    "let": "let rc=3",
    "a quoted let": 'let "rc = 3"',
    "an arithmetic assignment": "(( rc = 3 ))",
    "an arithmetic increment": "(( rc++ ))",
    "an arithmetic expansion": "echo $((rc = 3))",
    "a default assignment": ': "${rc:=3}"',
    "an unset-only assignment": ": ${rc=3}",
    "printf -v": "printf -v rc 3",
    "read": "read rc",
    "mapfile": "mapfile rc",
    "readarray": "readarray -t rc",
    "an append": "rc+=1",
    "an array append of an expansion": 'rc+=("$a")',
    "a string append of an expansion": 'rc+=" $v"',
    "an element": "rc[0]=3",
    "a plain assignment": "rc=1",
    "an assignment of more than the status": "rc=$?1",
    "unset": "unset rc",
    "a nameref": "declare -n ref=rc",
    "a loop": "for rc in 1; do :; done",
    "getopts": "getopts ab rc",
    "a local with no value": "f() { local rc; }",
    "a length": 'echo "${#rc}"',
    "an indirect expansion": 'echo "${!rc}"',
    "a test that it is set": "[[ -v rc ]]",
    "wait -p": "wait -n -p rc",
    "a descriptor it names": "exec {rc}>&-",
    "an old arithmetic expansion": "echo $[rc = 3]",
    "an argument of a function the script defines": "f() { :; }; f rc",
    "a function it names": "function rc { :; }",
    "a read inside a word": 'echo "$(read rc)"',
    "a word only an expansion reads": "echo ${x:-rc}",
}
# The line of an unquoted here-document body that holds the name, for each
# expansion of it that could write a held status.
_SH_BODY_WRITES = {
    "an arithmetic expansion": "$((rc = 3))",
    "a substitution": "$(read rc)",
    "a default assignment": "${rc:=3}",
    "a backquote": "`read rc`",
}


@pytest.mark.parametrize(
    "write", list(_SH_STATUS_WRITES.values()), ids=list(_SH_STATUS_WRITES)
)
def test_any_use_of_a_held_status_but_a_plain_read_is_a_finding_at_its_line(
    tmp_path, monkeypatch, write
):
    """A name `exit_passthrough` or `return` hands on is held only if every
    mention of it outside a comment is its binding or the plain read `$name`
    or `${name}`; any other is one finding at its own line, and the ending
    that hands it on is none."""
    body = 'false\nrc=$?\n%s\nexit_passthrough "$rc"\n' % write
    root = _sh_tree(
        tmp_path, monkeypatch, {"scripts/tool.sh": _SH_HEAD + body + _SH_TAIL}
    )
    (finding,) = shell_findings(root)["findings"]
    assert finding.startswith("scripts/tool.sh:5: "), finding
    assert "`rc`" in finding and "line 6" in finding, finding
    assert _SH_CANNOT_SHOW in finding, finding


@pytest.mark.parametrize("template", [True, False], ids=["template", "project"])
def test_a_held_status_finding_warns_and_every_other_exit_fault_still_fails(
    tmp_path, monkeypatch, template
):
    """The held-status rule warns and never fails (scripts/expiring_tier_data.py
    `WARN_ONLY`): its finding keeps its text and goes to `exit-held-status`,
    which warns in the template and in a project with no baseline, while a
    bare `exit 3` beside it is still red under `exit-helper`."""
    held = 'false\nrc=$?\nrc=2\nexit_passthrough "$rc"\n'
    root = _sh_tree(
        tmp_path,
        monkeypatch,
        {
            "scripts/held.sh": _SH_HEAD + held + _SH_TAIL,
            "scripts/bare.sh": _SH_HEAD + "exit 3\n" + _SH_TAIL,
        },
    )
    manifest = root / "config" / "project.json"
    loaded = json.loads(manifest.read_text(encoding="utf-8"))
    loaded["expiring_tier"] = config_loader.read(str(_ROOT))["expiring_tier"]
    manifest.write_text(json.dumps(loaded, sort_keys=True), encoding="utf-8")
    if template:
        (root / expiring_tier.TEMPLATE_MARK).write_text("_subdirectory: .\n")
    shell = shell_findings(root)
    (finding,) = shell["held_status"]
    assert finding.startswith("scripts/held.sh:5: "), finding
    assert _SH_CANNOT_SHOW in finding and finding in shell["findings"], finding
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        red = exit_helper_red([], shell, str(root))
    warned = "\n".join(
        str(w.message)
        for w in caught
        if issubclass(w.category, expiring_tier.ExpiringTierWarning)
    )
    assert finding in warned and "exit-held-status" in warned, warned
    assert red, "the bare exit 3 was not red"
    assert all(line.startswith("scripts/bare.sh:") for line in red), red


# The fragment of the carriage-return finding that says the shell reads the
# CR as part of a word, true only where the CR ends a word.
_SH_CR_IN_A_WORD = "which the shell reads as part of its last word"
_SH_CR_CASES = {
    "every line, the first in the #! line": (
        _SH_GOOD.replace("\n", "\r\n"),
        1,
        "the system reads as part of the interpreter's name",
    ),
    "one line": (
        _SH_GOOD.replace("shellcheck tool.sh\n", "shellcheck tool.sh\r\n"),
        4,
        _SH_CR_IN_A_WORD,
    ),
    "the last line with no newline": (_SH_GOOD[:-1] + "\r", 7, _SH_CR_IN_A_WORD),
    "a substitution in a quoted word": (
        _SH_GOOD.replace(_SH_TAIL, 'x="$(true\r\n)"\n' + _SH_TAIL),
        7,
        _SH_CR_IN_A_WORD,
    ),
    "a comment": (
        _SH_GOOD.replace(_SH_TAIL, "# a note\r\n" + _SH_TAIL),
        7,
        "inside a comment",
    ),
    "a single-quoted string": (
        _SH_GOOD.replace(_SH_TAIL, "echo 'a\r\nb'\n" + _SH_TAIL),
        7,
        "inside a quoted string",
    ),
    "a double-quoted string": (
        _SH_GOOD.replace(_SH_TAIL, 'echo "a\r\nb"\n' + _SH_TAIL),
        7,
        "inside a quoted string",
    ),
    "a quoted here-document body": (
        _SH_GOOD.replace(_SH_TAIL, "cat <<'EOF'\na\r\nEOF\n" + _SH_TAIL),
        8,
        "inside a here-document body",
    ),
    "an unquoted here-document body": (
        _SH_GOOD.replace(_SH_TAIL, "cat <<EOF\na\r\nEOF\n" + _SH_TAIL),
        8,
        "inside a here-document body",
    ),
}


@pytest.mark.parametrize("case", list(_SH_CR_CASES.values()), ids=list(_SH_CR_CASES))
def test_a_carriage_return_line_end_is_one_finding_that_names_where_it_is(
    tmp_path, monkeypatch, case
):
    """A CR before a newline is red wherever it is, as the file's one
    finding; the finding says where the CR sits and claims the shell reads
    it as part of a word only where it ends one."""
    script, line, fragment = case
    root = _sh_tree(tmp_path, monkeypatch, {"scripts/tool.sh": script})
    (finding,) = shell_findings(root)["findings"]
    assert finding.startswith("scripts/tool.sh:%d: " % line), finding
    assert "carriage return" in finding and "LF line endings" in finding, finding
    assert fragment in finding, finding
    if fragment != _SH_CR_IN_A_WORD:
        assert _SH_CR_IN_A_WORD not in finding, finding


def test_a_carriage_return_in_a_here_document_names_the_way_to_write_crlf(
    tmp_path, monkeypatch
):
    """A here-document that must emit CRLF stays LF in the file; the finding
    names the way to add the carriage returns as the text is written."""
    body = "cat <<'EOF'\na\r\nEOF\n"
    script = _SH_GOOD.replace(_SH_TAIL, body + _SH_TAIL)
    root = _sh_tree(tmp_path, monkeypatch, {"scripts/tool.sh": script})
    (finding,) = shell_findings(root)["findings"]
    assert """awk '{ printf "%s\\r\\n", $0 }'""" in finding, finding


def test_a_carriage_return_in_a_file_the_gate_cannot_read_claims_no_place(
    tmp_path, monkeypatch
):
    """bash reads `esac` and a CR as one word, so a CRLF `case` cannot be
    read to its end: the finding names the carriage return and claims no
    place for it."""
    body = "case x in a) : ;;\r\nesac\r\n"
    script = _SH_GOOD.replace(_SH_TAIL, body + _SH_TAIL)
    root = _sh_tree(tmp_path, monkeypatch, {"scripts/tool.sh": script})
    (finding,) = shell_findings(root)["findings"]
    assert finding.startswith("scripts/tool.sh:7: "), finding
    assert "carriage return" in finding and "LF line endings" in finding, finding
    assert _SH_CR_IN_A_WORD not in finding and "inside" not in finding, finding


# The fragment of the finding at an ending whose handed name nothing binds.
_SH_RENAMES = "renames a wrapped tool's status"
# (body after `false` on line 3, the finding's line, a fragment of it) for
# each shape that writes `rc=$?` but binds nothing, with the ending on line 5.
_SH_NOT_BINDINGS = {
    "an echo of the assignment": ("echo rc=$?\n", 5, _SH_RENAMES),
    "a subshell": ("(rc=$?)\n", 4, _SH_CANNOT_SHOW),
    "a substitution": ("x=$(rc=$?)\n", 4, _SH_CANNOT_SHOW),
    "a pipeline": ("rc=$? | cat\n", 4, _SH_CANNOT_SHOW),
    "the background": ("rc=$? &\n", 4, _SH_CANNOT_SHOW),
    "an assignment before a command": ("rc=$? true\n", 4, _SH_CANNOT_SHOW),
}


@pytest.mark.parametrize(
    "case", list(_SH_NOT_BINDINGS.values()), ids=list(_SH_NOT_BINDINGS)
)
def test_only_a_bare_assignment_statement_binds_a_held_status(
    tmp_path, monkeypatch, case
):
    """`name=$?` binds the held name only as a whole simple command in the
    main shell; any other shape that writes it binds nothing and is one
    finding."""
    shape, line, fragment = case
    body = 'false\n%sexit_passthrough "$rc"\n' % shape
    root = _sh_tree(
        tmp_path, monkeypatch, {"scripts/tool.sh": _SH_HEAD + body + _SH_TAIL}
    )
    (finding,) = shell_findings(root)["findings"]
    assert finding.startswith("scripts/tool.sh:%d: " % line), finding
    assert fragment in finding, finding


@pytest.mark.parametrize(
    "line", list(_SH_BODY_WRITES.values()), ids=list(_SH_BODY_WRITES)
)
def test_a_held_status_an_unquoted_here_document_expands_is_a_finding(
    tmp_path, monkeypatch, line
):
    """An unquoted here-document body is expanded, so a name an expansion in
    it could write is a finding at its line."""
    body = 'false\nrc=$?\ncat <<EOF\n%s\nEOF\nexit_passthrough "$rc"\n' % line
    root = _sh_tree(
        tmp_path, monkeypatch, {"scripts/tool.sh": _SH_HEAD + body + _SH_TAIL}
    )
    (finding,) = shell_findings(root)["findings"]
    assert finding.startswith("scripts/tool.sh:6: "), finding
    assert _SH_CANNOT_SHOW in finding, finding


# (held name, the line that mentions it) for each word that holds the name
# but names no variable.
_SH_NOT_MENTIONS = {
    "a file name": ("rc", "ls a.rc"),
    "an option": ("rc", "cmd --rc"),
    "an argument": ("rc", "echo rc"),
    "a subcommand named status": ("status", "git status"),
    "a redirection target": ("rc", "echo x >rc.log"),
    "a case pattern": ("rc", 'case "$1" in rc) : ;; esac'),
    "a path run as a command": ("rc", "./rc.sh"),
    "an assigned value": ("rc", "x=rc"),
    "a quoted argument": ("rc", 'echo "rc is $rc"'),
    "an unquoted here-document": ("rc", "cat <<EOF\nrc is $rc\nEOF"),
}


@pytest.mark.parametrize(
    "case", list(_SH_NOT_MENTIONS.values()), ids=list(_SH_NOT_MENTIONS)
)
def test_a_word_that_names_no_variable_is_no_mention(tmp_path, monkeypatch, case):
    """A mention of a held name is a word that names the variable: a file
    name, an option or an argument of a command that names no variable is
    none."""
    name, line = case
    body = 'false\n{0}=$?\n{1}\nexit_passthrough "${0}"\n'.format(name, line)
    root = _sh_tree(
        tmp_path, monkeypatch, {"scripts/tool.sh": _SH_HEAD + body + _SH_TAIL}
    )
    assert shell_findings(root)["findings"] == []


def test_a_binding_after_the_ending_binds_nothing(tmp_path, monkeypatch):
    body = 'false\nexit_passthrough "$rc"\nrc=$?\n'
    root = _sh_tree(
        tmp_path, monkeypatch, {"scripts/tool.sh": _SH_HEAD + body + _SH_TAIL}
    )
    (finding,) = shell_findings(root)["findings"]
    assert finding.startswith("scripts/tool.sh:4: "), finding
    assert _SH_RENAMES in finding, finding


def test_each_ending_needs_its_own_binding_before_it(tmp_path, monkeypatch):
    """A binding before the second ending does not bind the first."""
    body = 'f() { exit_passthrough "$rc"; }\nfalse\nrc=$?\nexit_passthrough "$rc"\n'
    root = _sh_tree(
        tmp_path, monkeypatch, {"scripts/tool.sh": _SH_HEAD + body + _SH_TAIL}
    )
    (finding,) = shell_findings(root)["findings"]
    assert finding.startswith("scripts/tool.sh:3: "), finding
    assert _SH_RENAMES in finding, finding


class _Visits(list):
    """A list that counts each item it hands out, by iteration or by index."""

    def __init__(self, items):
        super().__init__(items)
        self.visits = 0

    def __iter__(self):
        for item in super().__iter__():
            self.visits += 1
            yield item

    def __getitem__(self, k):
        self.visits += 1
        return super().__getitem__(k)


class _Scanned(str):  # noqa: SLOT000 - str allows no slot for the visit count
    """A str that counts each character a `count` or a slice of it reads."""

    visits = 0

    def count(self, sub, start=0, end=None):
        stop = len(self) if end is None else end
        self.visits += max(0, stop - start)
        return super().count(sub, start, end)

    def __getitem__(self, k):
        if isinstance(k, slice):
            self.visits += len(range(*k.indices(len(self))))
        return super().__getitem__(k)


def test_the_held_status_scan_visits_each_span_a_bounded_number_of_times():
    """The scan of a held name walks the spans no command reads, the marks
    of the words and the text it counts lines in once, not once per use of
    the name: twice the comments, reads and mentions costs at most a little
    over twice the visits. `echo rc` is a word the marks judge, so the walk
    of the marks is counted, not skipped as a plain read is. A count, not a
    clock, so a slow host cannot fail it; it counts list indexing,
    iteration, `str.count` and slicing, and a scan made quadratic by some
    other means would pass it."""

    def visits(n):
        text = _Scanned(
            _SH_HEAD
            + "false\nrc=$?\n"
            + '# a comment\necho "$rc"\necho rc\n' * n
            + 'exit_passthrough "$rc"\n'
            + _SH_TAIL
        )
        _commands, spans, bindings, marks = shell_commands(str(text))
        spans, marks = _Visits(spans), _Visits(marks)
        _bound, other = _sh_name_uses(text, spans, "rc", bindings, marks)
        assert other == [], other
        return spans.visits + marks.visits + text.visits

    small, large = visits(500), visits(1000)
    assert small >= 500, small
    assert large <= 2 * small + 10, (small, large)


def test_a_carriage_return_inside_a_line_is_no_finding(tmp_path, monkeypatch):
    script = _SH_GOOD.replace(_SH_TAIL, "printf 'a\rb'\n" + _SH_TAIL)
    root = _sh_tree(tmp_path, monkeypatch, {"scripts/tool.sh": script})
    assert shell_findings(root) == {"files": 1, "findings": [], "held_status": []}


def test_a_shell_script_that_does_not_source_the_helper_is_a_finding(
    tmp_path, monkeypatch
):
    script = _SH_GOOD.replace(_SH_HEAD, "#!/bin/sh\n")
    root = _sh_tree(tmp_path, monkeypatch, {"scripts/tool.sh": script})
    assert shell_findings(root)["findings"] == [
        "scripts/tool.sh:1: does not source %s, so it cannot end through it; add "
        '`. "$(dirname "$0")/%s"` before its first command'
        % (et.HELPER_SH, os.path.basename(et.HELPER_SH))
    ]


_SH_BEFORE_SOURCE = {
    "an exit of a member": 'exit "$EXIT_USAGE"\n',
    "a failure": 'exit_fail "$EXIT_USAGE" a b c\n',
    "a passthrough": 'false || exit_passthrough "$?"\n',
    "a return of a member": 'f() { return "$EXIT_USAGE"; }\n',
}


@pytest.mark.parametrize(
    "body", list(_SH_BEFORE_SOURCE.values()), ids=list(_SH_BEFORE_SOURCE)
)
def test_an_ending_before_the_line_that_sources_the_helper_is_a_finding(
    tmp_path, monkeypatch, body
):
    """The helper's names are unset until the line that sources it, so an
    ending that needs them must come after that line, in the text."""
    script = "#!/bin/sh\n" + body + _SH_HEAD.split("\n", 1)[1] + _SH_TAIL
    root = _sh_tree(tmp_path, monkeypatch, {"scripts/tool.sh": script})
    (finding,) = shell_findings(root)["findings"]
    assert finding.startswith("scripts/tool.sh:2: "), finding
    assert "before line 3, which sources" in finding, finding


@pytest.mark.parametrize(
    "target",
    [
        '"$(dirname "$0")/lib.sh"',
        "./my_exit_codes.sh",
        '"$(dirname "$0")/exit_codes.sh.in"',
    ],
)
def test_a_shell_script_that_sources_another_file_is_a_finding(
    tmp_path, monkeypatch, target
):
    """Only a path ending in `/exit_codes.sh` is the helper; sourcing any
    other file leaves its names unset."""
    script = _SH_GOOD.replace('"$(dirname "$0")/exit_codes.sh"', target)
    root = _sh_tree(tmp_path, monkeypatch, {"scripts/tool.sh": script})
    (finding,) = shell_findings(root)["findings"]
    assert finding.startswith("scripts/tool.sh:1: does not source"), finding


# (opening, closing, levels a repetition spends) of each shape the reader
# nests into: a double quote is a level of its own.
_SH_NESTINGS = {
    "substitutions": ("$(", ")", 1),
    "quoted substitutions": ('"$(', ')"', 2),
    "expansions": ("${y:-", "}", 1),
    "quoted expansions": ('"${y:-', '}"', 2),
}


@pytest.mark.parametrize("shape", list(_SH_NESTINGS.values()), ids=list(_SH_NESTINGS))
def test_nesting_past_the_bound_is_one_finding_never_a_recursion_error(shape):
    """Past _SH_MAX_DEPTH levels the reader stops with one finding at the
    file and the line the nesting opens on; at the bound it reads."""
    opening, closing, levels = shape
    head = _SH_HEAD + "\n"

    def script(depth):
        return (
            head + "echo " + opening * depth + "a" + closing * depth + "\n" + _SH_TAIL
        )

    known, quiet = {"SUCCESS", "USAGE"}, {"SUCCESS"}
    at_bound = script(_SH_MAX_DEPTH // levels)
    assert shell_file_findings(at_bound, "s.sh", known, quiet) == []
    findings = shell_file_findings(script(3000), "s.sh", known, quiet)
    assert len(findings) == 1, findings[:3]
    assert findings[0].startswith("s.sh:4: cannot be read to its end"), findings
    assert "nests deeper than %d" % _SH_MAX_DEPTH in findings[0], findings


def test_a_backquote_counts_toward_the_nesting_bound():
    """A backquote is read by a reader of its own, which starts at the
    depth it was opened at, so the bound holds across it."""
    nested = "$(" * _SH_MAX_DEPTH + "a" + ")" * _SH_MAX_DEPTH
    text = _SH_HEAD + "echo `" + nested + "`\n" + _SH_TAIL
    (finding,) = shell_file_findings(text, "s.sh", {"SUCCESS"}, {"SUCCESS"})
    assert finding.startswith("s.sh:3: cannot be read to its end"), finding
    assert "nests deeper than %d" % _SH_MAX_DEPTH in finding, finding


def test_a_shell_script_that_never_ends_through_the_helper_is_a_finding(
    tmp_path, monkeypatch
):
    root = _sh_tree(tmp_path, monkeypatch, {"scripts/tool.sh": _SH_HEAD + "true\n"})
    (finding,) = shell_findings(root)["findings"]
    assert finding.startswith("scripts/tool.sh:1: never ends through"), finding


def test_the_helper_and_an_excluded_script_are_not_judged(tmp_path, monkeypatch):
    members = et.read_members(str(_ROOT))
    root = _sh_tree(
        tmp_path,
        monkeypatch,
        {
            et.HELPER_SH: et.render_shell(members),
            "vendor/tool.sh": "exit 3\n",
            "scripts/tool.sh": _SH_GOOD,
        },
        excluded={"vendor": "a vendored tool"},
    )
    assert shell_findings(root) == {"files": 1, "findings": [], "held_status": []}


def test_a_shell_script_found_by_its_shebang_is_judged(tmp_path, monkeypatch):
    root = _sh_tree(
        tmp_path, monkeypatch, {"bin/tool": "#!/usr/bin/env bash\nexit 3\n"}
    )
    findings = shell_findings(root)["findings"]
    assert findings[0].startswith("bin/tool:1: does not source"), findings
    assert findings[1].startswith("bin/tool:2: `exit 3` writes a number"), findings


def test_no_shell_script_and_no_reason_is_a_finding_not_a_pass(tmp_path, monkeypatch):
    root = _sh_tree(tmp_path, monkeypatch, {})
    result = shell_findings(root)
    assert result["files"] == 0
    assert len(result["findings"]) == 1 and "zero items" in result["findings"][0]


def test_no_shell_script_with_a_reason_passes(tmp_path, monkeypatch):
    root = _sh_tree(tmp_path, monkeypatch, {}, no_scripts="its gates are Python")
    assert shell_findings(root) == {"files": 0, "findings": [], "held_status": []}


def test_a_blank_no_scripts_reason_is_refused_not_a_pass(tmp_path, monkeypatch):
    root = _sh_tree(tmp_path, monkeypatch, {}, no_scripts="   ")
    with pytest.raises(config_loader.ConfigError, match="shell.no_scripts"):
        shell_findings(root)


def test_with_shell_off_every_shell_script_is_still_judged(tmp_path, monkeypatch):
    """The answer `shell` switches the shell tools only: the helper ships
    either way, so with `shell.enabled` false a script still ends through
    it, and a bare `exit 3` is a finding at its file and line."""
    root = _sh_tree(
        tmp_path,
        monkeypatch,
        {"scripts/ops/deploy.sh": "#!/bin/sh\nexit 3\n"},
        enabled=False,
    )
    result = shell_findings(root)
    assert result["files"] == 1, result
    assert any(
        f.startswith("scripts/ops/deploy.sh:2: `exit 3` writes a number")
        for f in result["findings"]
    ), result


def test_with_shell_off_no_shell_script_needs_no_reason(tmp_path, monkeypatch):
    """Off, a project with no shell script is the expected case, so zero
    scripts passes without `shell.no_scripts`; on, the same tree is the
    zero-items finding."""
    (tmp_path / "off").mkdir()
    (tmp_path / "on").mkdir()
    off = _sh_tree(tmp_path / "off", monkeypatch, {}, enabled=False)
    assert shell_findings(off) == {"files": 0, "findings": [], "held_status": []}
    on = _sh_tree(tmp_path / "on", monkeypatch, {}, enabled=True)
    (finding,) = shell_findings(on)["findings"]
    assert "shell.no_scripts gives no reason" in finding, finding


def test_with_no_repository_every_walked_shell_script_is_judged(tmp_path, monkeypatch):
    """A freshly generated project has no git yet and `make test` runs there:
    with no repository the gate judges every shell script the structure walk
    reaches, less the helper and `shell.excluded_paths`, as the
    committed-secrets gate falls back, rather than failing on git."""
    members = et.read_members(str(_ROOT))
    root = _sh_tree(
        tmp_path,
        monkeypatch,
        {
            et.HELPER_SH: et.render_shell(members),
            "vendor/tool.sh": "exit 3\n",
            "scripts/tool.sh": "#!/bin/sh\nexit 3\n",
        },
        excluded={"vendor": "a vendored tool"},
        git=False,
    )
    result = shell_findings(root)
    assert result["files"] == 1, result
    assert any(
        f.startswith("scripts/tool.sh:2: `exit 3` writes a number")
        for f in result["findings"]
    ), result
