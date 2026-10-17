"""
title: exit_code_table — generate the exit-code table from the enum and the gate's scripts
kind: script
layer: n/a
summary: Writes the region between the `<!-- exit-codes:begin -->` and `<!-- exit-codes:end -->` lines of the guide config/project.json `doc_drift.limits_guide` names. The region holds two tables. The first has one row per member of ExitCode, read from the syntax tree of scripts/exit_codes.py and never by importing it: value, name, meaning, what to do. The second has one row per script a recipe reachable from make `doc_drift.gate_target` runs, naming the values that script's entry function can return and `passes through` when it returns a wrapped tool's status. `read_script` is the one reader of what a script can exit with, and it reads a closed grammar from the syntax tree: SUCCESS itself, `report(<member>, ...)`, `passthrough(...)`, a conditional between those, a name every binding of which is a plain assignment of those, or a call to a function of the same module whose every return is one of those, plus the member of every `fail(<member>, ...)` call in the module; any other return, a name also bound another way (a parameter, an unpacking, a loop, `+=`, `:=`, `as`, `global`), a `report` of a member with nothing to report, and a function that can reach its end without returning, is a finding, never a guess. `passthrough` marks a wrapped tool's status, so one handed the script's own status is a finding too: the entry function's result (the function `finish` is handed, or `main`), directly or through a plain-assigned name, an int literal, a member, a `report`, or a call to a function of the module whose every return is one of those, including such a status under a sign (`-1`), in an arithmetic or `and`/`or` whose every operand is one, or handed to a builtin the module does not rebind (`int(main())`); and so is an entry line that hands `finish` a `passthrough(...)`. A helper that converts another process's status (one of its returns reads it) passes. An enum member written with an annotation is refused, not skipped. `--check` writes nothing and exits 1 naming each difference when the region is stale. It reads config/project.json `doc_drift` through scripts/config_loader.py and refuses, exit CONFIG, a manifest or block it cannot use, after the loader's line for each key at fault. It refuses, exit 2, a guide or marker that is missing, repeated or out of order, a guide reached through a symlink (scripts/git_tree.py `through_symlink`) and a script whose exits it cannot read. It replaces the file whole through a temporary file beside it and never touches `updated:`. It does not hold exits to the helper (tests/integration/test_exit_gate.py does) and it does not write the per-script prose below the region, which is hand-written. Needs the project interpreter.
effect: writes
rerun: fixed-point
rerun_proof: make:check-exit-codes
"""

import argparse
import ast
import builtins
import collections
import os
import sys

_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_SCRIPTS)
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import check_structure as cs  # noqa: E402
import config_loader  # noqa: E402
import exit_codes as _helper  # noqa: E402
import git_tree  # noqa: E402

__all__ = [
    "BEGIN",
    "END",
    "MEMBER_COLUMNS",
    "PASSES_THROUGH",
    "SCRIPT_COLUMNS",
    "Member",
    "Reading",
    "TableConfigError",
    "TableError",
    "code_findings",
    "dropped_results",
    "exit_cell",
    "exit_codes",
    "gate_scripts",
    "helper_bindings",
    "helper_symbol",
    "load_policy",
    "main",
    "own_nodes",
    "read_members",
    "read_script",
    "render",
    "split_region",
    "table_findings",
    "wanted_text",
]

MANIFEST = "config/project.json"
BLOCK = "doc_drift"
GUIDE_KEY = "limits_guide"
TARGET_KEY = "gate_target"
# Where the enum lives, and the names this reader follows from it.
HELPER = "scripts/exit_codes.py"
HELPER_MODULE = "exit_codes"
ENUM = "ExitCode"
_REPORT, _PASSTHROUGH, _FINISH, _FAIL = "report", "passthrough", "finish", "fail"
# The keyword `report` and `fail` take their code under.
_CODE = "code"
# Statements that bind their own name, and the `match` patterns that capture
# one (named, not referenced: the pattern classes arrived in Python 3.10).
_DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
_CAPTURES = ("MatchAs", "MatchStar", "MatchMapping")
# The function read when a script's entry block hands nothing to `finish`.
_DEFAULT_ENTRY = "main"
# `passthrough` marks a status a wrapped tool produced. Handed one this script
# chose (main's result, a literal, a member, or a function of the module whose
# every return is one of those), it would pass a main returning integers off as
# a wrapper.
_OWN_STATUS = (
    "passthrough wraps a wrapped tool's status, never this script's own (the "
    "entry function's result, a literal, a member, or a function of this module "
    "that returns only those); return ExitCode members from main"
)
_PASSTHROUGH_HANDED = (
    "the entry line is finish(main()); call passthrough inside main where the "
    "wrapped tool's status is read"
)

BEGIN = "<!-- exit-codes:begin -->"
END = "<!-- exit-codes:end -->"
MEMBER_COLUMNS = ("Exit", "Name", "Meaning", "What to do")
SCRIPT_COLUMNS = ("Script", "Exit")
PASSES_THROUGH = "passes through"
# A cell is split on this character by every reader of a pipe table, so text
# holding one cannot be a cell.
_CELL_BREAKERS = ("|", "\n", "\r")
_TEMP_SUFFIX = ".tmp"

Member = collections.namedtuple("Member", "name value meaning action")
# names: the member names an entry function can return; passes: it can return
# a wrapped tool's status; findings: each return outside the grammar.
Reading = collections.namedtuple("Reading", "names passes findings")


class TableError(Exception):
    """The table cannot be built. Carries the three parts of the line the
    process ends on: what failed, on which input, what to do next."""

    def __init__(self, what, on, next_step):
        Exception.__init__(self, "%s: %s; %s" % (what, on, next_step))
        self.what, self.on, self.next_step = what, on, next_step


class TableConfigError(TableError):
    """config/project.json `doc_drift` cannot be used: an edit to the config,
    not to the guide or a script, clears it."""


# --- the enum, read from the syntax tree ---------------------------------------


def _parse(path, relpath):
    try:
        with open(path, encoding="utf-8") as fh:
            return ast.parse(fh.read(), filename=relpath)
    except (OSError, ValueError, SyntaxError) as exc:
        raise TableError(
            "cannot read a Python file",
            "%s (%s)" % (relpath, exc),
            "restore the file or fix its syntax",
        ) from exc


def _literal(node, kind):
    """The value of a literal of exactly *kind*, else None (a bool is no int)."""
    if isinstance(node, ast.Constant) and type(node.value) is kind:
        return node.value
    return None


def read_members(root):
    """Every member of the enum in *root*'s helper, in value order, read from
    the class body: `NAME = (<int>, <meaning>, <action>)`. Reading the file,
    never importing it, lets a caller judge a tree other than the running one.
    Raises TableError when the class is missing, a member is not that shape,
    two members share a value, or a text cannot be a table cell."""
    tree = _parse(os.path.join(root, HELPER), HELPER)
    enum = next(
        (n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == ENUM),
        None,
    )
    if enum is None:
        raise TableError(
            "the helper defines no exit-code enum",
            "%s has no class %s" % (HELPER, ENUM),
            "restore the class",
        )
    members = []
    for node in enum.body:
        # An annotated assignment is a member at run time too; it is refused
        # with the other shapes, because a skipped member has no row.
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        plain = isinstance(node, ast.Assign)
        shape = node.value.elts if isinstance(node.value, ast.Tuple) else []
        parts = [_literal(e, k) for e, k in zip(shape, (int, str, str), strict=False)]
        named = (
            plain and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
        )
        if not named or len(shape) != 3 or None in parts:
            raise TableError(
                "an exit-code member is not `NAME = (<int>, <meaning>, <action>)`",
                "%s:%d" % (HELPER, node.lineno),
                "write the member as three literals",
            )
        member = Member(node.targets[0].id, *parts)
        for text in (member.meaning, member.action):
            if not text.strip() or any(c in text for c in _CELL_BREAKERS):
                raise TableError(
                    "an exit-code member's text is blank or cannot be a table cell",
                    "%s:%d (%s)" % (HELPER, node.lineno, member.name),
                    "write one line of text with no `|` in it",
                )
        members.append(member)
    if not members:
        raise TableError(
            "the exit-code enum has no member",
            "%s class %s" % (HELPER, ENUM),
            "restore its members",
        )
    values = [m.value for m in members]
    if len(set(values)) != len(values):
        raise TableError(
            "two exit-code members share a value",
            "%s class %s" % (HELPER, ENUM),
            "give each member its own value",
        )
    return sorted(members, key=lambda m: m.value)


# --- what a script can exit with, read from the syntax tree --------------------


def helper_bindings(tree):
    """(names, modules) *tree* binds from the helper: {local name: helper
    symbol} for each `from exit_codes import <symbol> [as <local>]`, and the
    local names of `import exit_codes [as <local>]`. A plain assignment that
    rebinds one (`die = fail`, `_f = exit_codes.fail`, `h = exit_codes`) adds
    its target too, followed through chains, so a second name is never a way
    past a gate that asks what a call is."""
    names, modules = {}, set()
    aliases = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module == HELPER_MODULE:
                for alias in node.names:
                    names[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == HELPER_MODULE:
                    modules.add(alias.asname or alias.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            aliases.extend(
                (target.id, node.value)
                for target in targets
                if isinstance(target, ast.Name)
            )
    # Each pass binds at least one new name or ends, so a chain resolves in
    # as many passes as it has links.
    changed = True
    while changed:
        changed = False
        for target, value in aliases:
            if target in names or target in modules:
                continue
            if isinstance(value, ast.Name) and value.id in modules:
                modules.add(target)
                changed = True
                continue
            symbol = helper_symbol(value, (names, modules))
            if symbol is not None:
                names[target] = symbol
                changed = True
    return names, modules


def helper_symbol(node, bindings):
    """The helper symbol the expression *node* names (`report`, or
    `exit_codes.report` through an imported module name), else None."""
    names, modules = bindings
    if isinstance(node, ast.Name):
        return names.get(node.id)
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in modules
    ):
        return node.attr
    return None


def own_nodes(func):
    """Every node of *func*'s body. A nested function is yielded and not
    entered: its returns are its own."""
    stack = list(func.body)
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            stack.extend(ast.iter_child_nodes(node))


class _Reader:
    """One script's reading. A return is followed through the closed grammar
    the module header states; whatever falls outside it becomes a finding."""

    def __init__(self, tree, relpath, quiet_names):
        self.relpath = relpath
        self.bindings = helper_bindings(tree)
        self.quiet = quiet_names
        self.functions = {
            n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)
        }
        self.module_scope = self._bindings(own_nodes(tree)) + ({},)
        # A name some function declares `global` or `nonlocal` can be rebound
        # from a scope other than the one that returns it.
        self.shared = {
            name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Global, ast.Nonlocal))
            for name in node.names
        }
        self.names, self.passes, self.findings = set(), False, []
        # The functions whose result `finish` is handed: their status is the
        # script's own by definition.
        self.entries = {_DEFAULT_ENTRY}
        self._visited = set()
        # The assigned values being followed now: one met again is a cycle.
        self._following = set()

    @staticmethod
    def _bindings(nodes, parameters=()):
        """(assigned, opaque) for the statements *nodes* of one scope.
        *assigned* is {name: [value]} for each `name = value` and
        `name: T = value`, the one binding the reader follows. *opaque* holds
        every name bound any other way, starting with *parameters*: an
        unpacking, a loop or comprehension target, `+=`, `:=`, `with ... as`,
        `except ... as`, an import, `del`, a `match` capture, and a nested
        `def` or `class`. What an opaque name holds is not read."""
        assigned, opaque = {}, set(parameters)
        followed = set()
        nodes = list(nodes)
        for node in nodes:
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            else:
                continue
            for target in targets:
                if isinstance(target, ast.Name):
                    followed.add(id(target))
                    if node.value is not None:
                        assigned.setdefault(target.id, []).append(node.value)
        for node in nodes:
            if isinstance(node, ast.Name):
                if not isinstance(node.ctx, ast.Load) and id(node) not in followed:
                    opaque.add(node.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                opaque.update(
                    (alias.asname or alias.name).split(".")[0] for alias in node.names
                )
            elif isinstance(node, _DEFINITIONS):
                opaque.add(node.name)
            elif (
                isinstance(node, ast.ExceptHandler) or type(node).__name__ in _CAPTURES
            ):
                opaque.update(
                    name
                    for name in (
                        getattr(node, "name", None),
                        getattr(node, "rest", None),
                    )
                    if name
                )
        return assigned, opaque

    def _finding(self, node, why):
        self.findings.append("%s:%d: %s" % (self.relpath, node.lineno, why))

    def _member(self, node):
        if isinstance(node, ast.Attribute) and (
            helper_symbol(node.value, self.bindings) == ENUM
        ):
            return node.attr
        return None

    def _reported(self, node):
        """The members `report`'s first argument can be: a member that has
        something to report, or a conditional between such members. The
        helper raises on anything else, so anything else is a finding."""
        if isinstance(node, ast.IfExp):
            self._reported(node.body)
            self._reported(node.orelse)
        elif self._member(node) in self.quiet:
            self._finding(
                node,
                "`report` is handed %s.%s, which has nothing to report: return "
                "the member itself" % (ENUM, self._member(node)),
            )
        elif self._member(node) is not None:
            self.names.add(self._member(node))
        else:
            self._finding(node, "`report` is handed a code that is not a member")

    def reported_call(self, call, symbol):
        """Judge the code a `report` or `fail` call is handed."""
        code = call.args[0] if call.args else None
        for keyword in call.keywords:
            if keyword.arg == _CODE and code is None:
                code = keyword.value
        if code is None:
            self._finding(call, "`%s` is called with no code" % symbol)
        else:
            self._reported(code)

    def _name(self, node, scope):
        """Follow a returned name to each value a plain assignment binds it
        to. A name bound any other way as well is a finding: the reader would
        be guessing which binding the return sees."""
        assigned, opaque, _nested = scope
        if node.id not in assigned and node.id not in opaque:
            assigned, opaque, _nested = self.module_scope
        if node.id in opaque or node.id in self.shared:
            self._finding(
                node,
                "returns `%s`, which is bound by something other than "
                "`%s = <exit code>` (a parameter, an unpacking, a loop, `+=`, "
                "`:=`, `as`, `global`): bind it by plain assignment only"
                % (node.id, node.id),
            )
        elif not assigned.get(node.id):
            self._finding(node, "returns `%s`, which nothing binds" % node.id)
        else:
            for expr in assigned[node.id]:
                if id(expr) in self._following:
                    self._finding(node, "returns `%s`, bound to itself" % node.id)
                    continue
                self._following.add(id(expr))
                self.value(expr, scope)
                self._following.discard(id(expr))

    def value(self, node, scope):
        """Follow one returned expression. *scope* is (assigned, opaque,
        nested functions) of the function it is returned from."""
        _assigned, _opaque, nested = scope
        member = self._member(node)
        if member is not None:
            self.names.add(member)
            if member not in self.quiet:
                self._finding(
                    node,
                    "returns %s.%s without `report`: a failure says what failed, "
                    "on which input and what to do next" % (ENUM, member),
                )
        elif isinstance(node, ast.IfExp):
            self.value(node.body, scope)
            self.value(node.orelse, scope)
        elif isinstance(node, ast.Call):
            symbol = helper_symbol(node.func, self.bindings)
            target = node.func.id if isinstance(node.func, ast.Name) else None
            if symbol == _REPORT:
                self.reported_call(node, symbol)
            elif symbol == _PASSTHROUGH:
                if node.args and self.own_status(node.args[0], scope, set()):
                    self._finding(node, _OWN_STATUS)
                else:
                    self.passes = True
            elif target in nested or target in self.functions:
                self.function(nested.get(target) or self.functions[target])
            else:
                self._finding(
                    node,
                    "returns the result of a call that is neither the helper's "
                    "nor a function of this module",
                )
        elif isinstance(node, ast.Name):
            self._name(node, scope)
        else:
            self._finding(
                node,
                "returns a value that is not an exit code: return an %s member "
                "through `report`, or `passthrough(...)`" % ENUM,
            )

    def own_status(self, node, scope, seen):
        """True when the expression *node* handed to `passthrough` is a status
        this script chose rather than one a wrapped tool produced: an int
        literal, a member, a `report`, a call to an entry function, a
        conditional both of whose branches are such, a sign over such
        (`-1`), an arithmetic or `and`/`or` whose every operand is such, a
        call to a builtin the module does not rebind whose every argument is
        such (`int(main())`), a name every plain assignment of which is such,
        or a call to a function of this module whose every return is such. A
        name bound any other way, an attribute, a subscript and a call to
        anything else are read as a tool's status.
        *seen* holds the functions and assigned values being followed, so a
        cycle ends."""
        if isinstance(node, ast.Constant):
            return isinstance(node.value, int)
        if self._member(node) is not None:
            return True
        if isinstance(node, ast.IfExp):
            return self.own_status(node.body, scope, seen) and self.own_status(
                node.orelse, scope, seen
            )
        # `-1`, `main() + 0` and `main() or 0` compute nothing a tool produced
        # when every operand is the script's own.
        if isinstance(node, ast.UnaryOp):
            return self.own_status(node.operand, scope, seen)
        if isinstance(node, (ast.BinOp, ast.BoolOp)):
            operands = (
                node.values if isinstance(node, ast.BoolOp) else [node.left, node.right]
            )
            return all(self.own_status(value, scope, seen) for value in operands)
        if isinstance(node, ast.Name):
            where = scope
            if node.id not in scope[0] and node.id not in scope[1]:
                where = self.module_scope
            assigned, opaque, _nested = where
            values = assigned.get(node.id)
            if not values or node.id in opaque or node.id in self.shared:
                return False
            # A value met again is a name bound to itself: it adds no status.
            fresh = [value for value in values if id(value) not in seen]
            seen = seen | {id(value) for value in fresh}
            return all(self.own_status(value, where, seen) for value in fresh)
        if not isinstance(node, ast.Call):
            return False
        if helper_symbol(node.func, self.bindings) == _REPORT:
            return True
        target = node.func.id if isinstance(node.func, ast.Name) else None
        if target in self.entries:
            return True
        func = scope[2].get(target) or self.functions.get(target)
        if func is None and self._builtin(target, scope):
            # `int(main())` converts the script's status; it reads no tool's.
            arguments = list(node.args) + [kw.value for kw in node.keywords]
            return bool(arguments) and all(
                self.own_status(value, scope, seen) for value in arguments
            )
        if func is None or id(func) in seen:
            return func is not None
        seen = seen | {id(func)}
        inner = self._scope(func)
        returns = [n.value for n in own_nodes(func) if isinstance(n, ast.Return)]
        return bool(returns) and all(
            value is not None and self.own_status(value, inner, seen)
            for value in returns
        )

    def _builtin(self, name, scope):
        """True when *name* is a builtin this module does not rebind: no
        assignment, import, parameter or definition in *scope* or at module
        level gives it another meaning."""
        if name is None or not hasattr(builtins, name):
            return False
        return not any(
            name in where[0] or name in where[1] for where in (scope, self.module_scope)
        )

    def handed_passthrough(self, node, seen=frozenset()):
        """True when the expression `finish` is handed is a `passthrough` call,
        directly or through a name a plain assignment binds to one. *seen*
        holds the assigned values being followed, so `rc = rc` ends."""
        if isinstance(node, ast.Name):
            values = [
                value
                for value in self.module_scope[0].get(node.id, ())
                if id(value) not in seen
            ]
            seen = seen | {id(value) for value in values}
            return any(self.handed_passthrough(value, seen) for value in values)
        return (
            isinstance(node, ast.Call)
            and helper_symbol(node.func, self.bindings) == _PASSTHROUGH
        )

    def _scope(self, func):
        """(assigned, opaque, nested functions) of the function *func*."""
        nodes = list(own_nodes(func))
        parameters = [a.arg for a in ast.walk(func.args) if isinstance(a, ast.arg)]
        return self._bindings(nodes, parameters) + (
            {n.name: n for n in nodes if isinstance(n, ast.FunctionDef)},
        )

    def function(self, func):
        if id(func) in self._visited:
            return
        self._visited.add(id(func))
        nodes = list(own_nodes(func))
        scope = self._scope(func)
        returns = [n for n in nodes if isinstance(n, ast.Return)]
        if not returns:
            self._finding(func, "`%s` returns no exit code" % func.name)
        elif not _ends(func.body):
            self._finding(
                func,
                "`%s` can reach its end without returning an exit code" % func.name,
            )
        for node in returns:
            if node.value is None or _is_none(node.value):
                self._finding(node, "`%s` returns nothing" % func.name)
            else:
                self.value(node.value, scope)


def _ends(body):
    """True when control cannot run off the end of the statement list *body*:
    its last statement returns, raises, or is a branch, `try`, `with` or
    `while True` whose every way out does. Anything else may fall through."""
    if not body:
        return False
    last = body[-1]
    if isinstance(last, (ast.Return, ast.Raise)):
        return True
    if isinstance(last, ast.If):
        return _ends(last.body) and _ends(last.orelse)
    if isinstance(last, (ast.With, ast.AsyncWith)):
        return _ends(last.body)
    if isinstance(last, ast.Try):
        if _ends(last.finalbody):
            return True
        tried = _ends(last.orelse) if last.orelse else _ends(last.body)
        return tried and all(_ends(h.body) for h in last.handlers)
    if isinstance(last, ast.While):
        endless = isinstance(last.test, ast.Constant) and last.test.value is True
        return endless and not any(isinstance(n, ast.Break) for n in ast.walk(last))
    return False


def _is_none(node):
    return isinstance(node, ast.Constant) and node.value is None


def _is_main_guard(node):
    """`if __name__ == "__main__":`, compared in either order."""
    if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
        return False
    sides = [node.test.left] + list(node.test.comparators)
    return (
        len(sides) == 2
        and len(node.test.ops) == 1
        and isinstance(node.test.ops[0], ast.Eq)
        and any(isinstance(s, ast.Name) and s.id == "__name__" for s in sides)
        and any(_literal(s, str) == "__main__" for s in sides)
    )


def entry_blocks(tree):
    """The module-level `if __name__ == "__main__":` statements of *tree*."""
    return [n for n in tree.body if _is_main_guard(n)]


def finish_calls(tree, bindings):
    """Each call of the helper's `finish` inside an entry block of *tree*."""
    return [
        node
        for block in entry_blocks(tree)
        for node in ast.walk(block)
        if isinstance(node, ast.Call) and helper_symbol(node.func, bindings) == _FINISH
    ]


def read_tree(tree, relpath, quiet_names):
    """The Reading of a parsed script: what its entry block hands `finish`,
    or its `main` when the block hands nothing. *quiet_names* are the members
    that may be returned without `report`."""
    reader = _Reader(tree, relpath, quiet_names)
    # `fail` ends the process from anywhere in the module, not only from the
    # entry function, so every call of it is a code this script can exit with.
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and (
            helper_symbol(node.func, reader.bindings) == _FAIL
        ):
            reader.reported_call(node, _FAIL)
    handed = finish_calls(tree, reader.bindings)
    reader.entries.update(_called_functions(handed, reader))
    for call in handed:
        if len(call.args) != 1 or call.keywords:
            reader._finding(call, "`finish` takes exactly what `main` returned")
            continue
        if reader.handed_passthrough(call.args[0]):
            reader._finding(call, _PASSTHROUGH_HANDED)
        reader.value(call.args[0], reader.module_scope)
    if not handed:
        if _DEFAULT_ENTRY in reader.functions:
            reader.function(reader.functions[_DEFAULT_ENTRY])
        else:
            reader.findings.append(
                "%s: no entry function: nothing is handed to `finish` and there "
                "is no `%s`" % (relpath, _DEFAULT_ENTRY)
            )
    return Reading(frozenset(reader.names), reader.passes, reader.findings)


def _called_functions(calls, reader):
    """The names of the module's functions the arguments of *calls* call,
    directly or through a name a module-level plain assignment binds."""
    assigned = reader.module_scope[0]
    nodes = [arg for call in calls for arg in call.args]
    nodes += [
        value
        for node in list(nodes)
        for name in ast.walk(node)
        if isinstance(name, ast.Name)
        for value in assigned.get(name.id, ())
    ]
    return {
        node.func.id
        for expr in nodes
        for node in ast.walk(expr)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in reader.functions
    }


def code_findings(tree, relpath, quiet_names):
    """Each `report` or `fail` call anywhere in *tree* whose code the helper
    would refuse at run time: not a member, or a member in *quiet_names*. It
    reads a module with no entry block too, which `read_tree` never judges."""
    reader = _Reader(tree, relpath, quiet_names)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            symbol = helper_symbol(node.func, reader.bindings)
            if symbol in (_REPORT, _FAIL):
                reader.reported_call(node, symbol)
    return sorted(reader.findings)


def dropped_results(tree):
    """Each expression statement in an entry block of *tree* that calls a
    function of the module and drops what it returns, as (statement, function
    name). A function counts when some `return` of its own carries a value. A
    value that is used (`print(f())`) is not dropped, and a value dropped by
    another callable (`asyncio.run(main())`) is not seen."""
    returning = {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and any(
            isinstance(n, ast.Return) and n.value is not None and not _is_none(n.value)
            for n in own_nodes(node)
        )
    }
    return [
        (node, node.value.func.id)
        for block in entry_blocks(tree)
        for node in ast.walk(block)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id in returning
    ]


def _quiet_names(members):
    # Only a status of zero has nothing to report.
    return frozenset(m.name for m in members if m.value == 0)


def read_script(path, relpath, members):
    """The Reading of the script at *path*, judged against *members*. A name
    the enum does not define is a finding and yields no code."""
    reading = read_tree(_parse(path, relpath), relpath, _quiet_names(members))
    known = {m.name for m in members}
    unknown = sorted(reading.names - known)
    findings = list(reading.findings) + [
        "%s: names %s.%s, which %s does not define" % (relpath, ENUM, name, HELPER)
        for name in unknown
    ]
    return Reading(reading.names & known, reading.passes, findings)


def exit_codes(path, root=None):
    """(values, passes_through) for the script at *path*, by the enum of
    *root* (this checkout when None). Findings are read_script's to report; a
    return outside the grammar adds no value here."""
    members = read_members(ROOT if root is None else str(root))
    reading = read_script(str(path), os.path.basename(str(path)), members)
    return {m.value for m in members if m.name in reading.names}, reading.passes


def gate_scripts(root, target):
    """Every `*.py` a recipe reachable from make *target* runs, sorted. A
    makefile this cannot read fully is a TableError, never a smaller set."""
    warns = []
    makefiles = cs.walk_makefiles(str(root), warns.append)
    advice = "fix the Makefile, or config/project.json `%s.%s`" % (BLOCK, TARGET_KEY)
    if warns:
        raise TableError("cannot read a makefile", "; ".join(warns), advice)
    if not makefiles:
        raise TableError("no Makefile -- zero items", str(root), advice)
    rules = cs._make_rules("\n".join(text for _path, text in makefiles))
    if target not in rules:
        raise TableError("the Makefile has no such target", "`%s`" % target, advice)
    unresolved = []
    scripts = cs._scripts_reachable_from(rules, target, unresolved)
    if unresolved:
        raise TableError(
            "`make %s` reaches `$(MAKE)` call(s) that cannot be followed" % target,
            "; ".join(unresolved),
            advice,
        )
    return sorted(scripts)


# --- the region ------------------------------------------------------------------


def load_policy(root):
    """(guide, gate target) from config/project.json `doc_drift`, read through
    scripts/config_loader.py. Raises TableConfigError carrying the loader's
    lines: both keys are required, so there is no default path in code."""
    paths = ((BLOCK, GUIDE_KEY), (BLOCK, TARGET_KEY))
    try:
        values = config_loader.resolve(
            config_loader.read(root), config_loader.rows(*paths), MANIFEST
        )
    except config_loader.ConfigError as exc:
        raise TableConfigError(
            "the manifest block cannot be used",
            "%s `%s`: %s" % (MANIFEST, BLOCK, "; ".join(exc.lines)),
            "correct it as the lines above say",
        ) from exc
    return tuple(values[path] for path in paths)


def split_region(text, guide):
    """(before, region, after) of *text* around the one BEGIN line and the
    one END line after it; *before* ends with the BEGIN line and *after*
    starts with the END line. Raises TableError otherwise."""
    lines = text.splitlines(True)
    begins = [i for i, ln in enumerate(lines) if ln.rstrip("\r\n") == BEGIN]
    ends = [i for i, ln in enumerate(lines) if ln.rstrip("\r\n") == END]
    if len(begins) != 1 or len(ends) != 1 or begins[0] > ends[0]:
        raise TableError(
            "the guide does not hold exactly one `%s` line followed by one `%s` "
            "line" % (BEGIN, END),
            guide,
            "write the two marker lines, each alone on its line, where the "
            "table belongs",
        )
    begin, end = begins[0], ends[0]
    return (
        "".join(lines[: begin + 1]),
        "".join(lines[begin + 1 : end]),
        "".join(lines[end:]),
    )


def exit_cell(values, passes):
    """The Exit cell of a script row: its values in order, then the phrase
    that says a wrapped tool's status passes through."""
    words = [str(v) for v in sorted(values)]
    return ", ".join(words + ([PASSES_THROUGH] if passes else []))


def _table(columns, rows):
    lines = ["| " + " | ".join(columns) + " |"]
    lines.append("|" + "|".join("-" * (len(c) + 2) for c in columns) + "|")
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return lines


def render(members, script_rows, newline="\n"):
    """The region's text: the member table, a blank line, the script table.
    *script_rows* is [(script, values, passes)]."""
    lines = _table(
        MEMBER_COLUMNS,
        [(str(m.value), "`%s`" % m.name, m.meaning, m.action) for m in members],
    )
    lines.append("")
    lines.extend(
        _table(
            SCRIPT_COLUMNS,
            [("`%s`" % s, exit_cell(v, p)) for s, v, p in sorted(script_rows)],
        )
    )
    return "".join(line + newline for line in lines)


def _script_rows(root, target, members):
    """[(script, values, passes)] for each gate script; TableError when one is
    missing, has a return outside the grammar, or yields no code at all."""
    scripts = gate_scripts(root, target)
    if not scripts:
        raise TableError(
            "the gate runs no script -- zero items",
            "make %s" % target,
            "check config/project.json `%s.%s`" % (BLOCK, TARGET_KEY),
        )
    rows, findings = [], []
    for script in scripts:
        path = os.path.join(root, script)
        if not os.path.isfile(path):
            findings.append("the gate runs %s, which does not exist" % script)
            continue
        reading = read_script(path, script, members)
        findings.extend(reading.findings)
        if not reading.names and not reading.passes:
            findings.append("%s: no exit code derived -- zero items" % script)
        values = {m.value for m in members if m.name in reading.names}
        rows.append((script, values, reading.passes))
    if findings:
        raise TableError(
            "cannot read what %d script(s) of the gate exit with" % len(findings),
            " | ".join(findings),
            "end each through `finish(main())` with `main` returning members "
            "(%s)" % HELPER,
        )
    return rows


def wanted_text(root):
    """(guide, its text now, its text with the region regenerated). Raises
    TableError when the table cannot be built or the guide cannot take it."""
    guide, target = load_policy(root)
    linked = git_tree.through_symlink(root, [guide, guide + _TEMP_SUFFIX])
    if linked:
        raise TableError(
            "the guide is reached through a symlink or lies outside the project",
            ", ".join(linked),
            "point config/project.json `%s.%s` at a real file inside the "
            "project" % (BLOCK, GUIDE_KEY),
        )
    try:
        with open(os.path.join(root, guide), encoding="utf-8", newline="") as fh:
            text = fh.read()
    except (OSError, ValueError) as exc:
        raise TableError(
            "cannot read the guide",
            "%s (%s)" % (guide, exc),
            "restore it, or correct config/project.json `%s.%s`" % (BLOCK, GUIDE_KEY),
        ) from exc
    before, _region, after = split_region(text, guide)
    members = read_members(root)
    # The region ends its lines the way the marker line above it does.
    newline = "\r\n" if before.endswith("\r\n") else "\n"
    region = render(members, _script_rows(root, target, members), newline)
    return guide, text, before + region + after


def _rows(region, columns):
    table = cs._pipe_table(region, columns)
    return None if table is None else table[1]


def table_findings(root):
    """Each difference between the guide's region and what the enum and the
    gate's scripts say, named: a member no row names, a row no member backs, a
    row that says something else, and the same for script rows. An unbuildable
    table is one finding. Empty when the region is byte-identical."""
    try:
        guide, text, wanted = wanted_text(root)
    except TableError as exc:
        return [str(exc)]
    if text == wanted:
        return []
    have, want = split_region(text, guide)[1], split_region(wanted, guide)[1]
    findings = []
    for columns, noun in ((MEMBER_COLUMNS, "member"), (SCRIPT_COLUMNS, "script")):
        key = 1 if columns is MEMBER_COLUMNS else 0
        have_rows, want_rows = _rows(have, columns), _rows(want, columns)
        if have_rows is None:
            findings.append(
                "%s: no table with the columns %s" % (guide, ", ".join(columns))
            )
            continue
        named = {row[key]: row for row in have_rows if key < len(row)}
        backed = {row[key]: row for row in want_rows}
        findings.extend(
            "%s: the exit-code table names no %s %s" % (guide, noun, name)
            for name in sorted(set(backed) - set(named))
        )
        findings.extend(
            "%s: the row `| %s |` names %s %s, which nothing backs"
            % (guide, " | ".join(named[name]), noun, name)
            for name in sorted(set(named) - set(backed))
        )
        findings.extend(
            "%s: the row for %s %s is `| %s |`, and the generator writes `| %s |`"
            % (guide, noun, name, " | ".join(named[name]), " | ".join(backed[name]))
            for name in sorted(set(named) & set(backed))
            if named[name] != backed[name]
        )
    return findings or [
        "%s: the exit-code region is not what the generator writes" % guide
    ]


def _write(root, guide, text):
    path = os.path.join(root, guide)
    temp = path + _TEMP_SUFFIX
    with open(temp, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    os.replace(temp, path)


def main(argv=None, root=None):
    """Regenerate the exit-code region of the limits guide, or with --check
    only say whether it is current."""
    ap = argparse.ArgumentParser(
        description="Generate the exit-code table in the limits guide from the "
        "ExitCode enum and the scripts the gate runs"
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="write nothing; exit 1 if the table in the guide is stale",
    )
    args = ap.parse_args(argv)
    root = ROOT if root is None else str(root)
    try:
        guide, text, wanted = wanted_text(root)
    except TableConfigError as exc:
        return _helper.report(
            _helper.ExitCode.CONFIG,
            "exit_code_table: " + exc.what,
            exc.on,
            exc.next_step,
        )
    except TableError as exc:
        return _helper.report(
            _helper.ExitCode.USAGE,
            "exit_code_table: " + exc.what,
            exc.on,
            exc.next_step,
        )
    if args.check:
        if text != wanted:
            for finding in table_findings(root):
                sys.stderr.write(finding + "\n")
            return _helper.report(
                _helper.ExitCode.FAILURE,
                "exit_code_table: the exit-code table is stale",
                guide,
                "regenerate with `make exit-codes`",
            )
        print("exit-code table up to date: %s" % guide)
        return _helper.ExitCode.SUCCESS
    if text == wanted:
        print("exit-code table unchanged: %s" % guide)
        return _helper.ExitCode.SUCCESS
    try:
        _write(root, guide, wanted)
    except OSError as exc:
        return _helper.report(
            _helper.ExitCode.USAGE,
            "exit_code_table: cannot write the guide",
            "%s (%s)" % (guide, exc),
            "make the file and its directory writable, then run `make exit-codes`",
        )
    print("wrote the exit-code table: %s" % guide)
    return _helper.ExitCode.SUCCESS


if __name__ == "__main__":
    _helper.finish(main())
