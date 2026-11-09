"""
title: Test helper — discover scripts whose parsed checkout reaches the config loader
kind: tests
layer: n/a
summary: Follows AST imports, function calls and plain bindings from scripts' --root arguments to config_loader.read. Unresolved loader roots fail with file and line; coverage comparisons refuse missing, stale and empty cases.
"""

import ast
from pathlib import Path

import source_tree as st

_LOADER = ("scripts/config_loader.py", "read")
_ROOT = "parsed root"
_NAMESPACE = "parsed arguments"
_FIXED = "fixed value"
_UNKNOWN = "unresolved root"
_PATH_CALLS = {
    "str",
    "Path",
    "pathlib.Path",
    "os.fspath",
    "os.path.abspath",
    "os.path.realpath",
    "os.path.normpath",
    "os.path.expanduser",
    "os.path.dirname",
    "os.path.basename",
}


def _dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _dotted(node.value) + "." + node.attr
    return ""


def _merge(values):
    if _UNKNOWN in values:
        return _UNKNOWN
    if _ROOT in values:
        return _ROOT
    if all(value == _FIXED for value in values):
        return _FIXED
    return _UNKNOWN


class _Discovery:
    def __init__(self, root, search_roots):
        self.root = root
        self.search_roots = search_roots
        self.trees = {}
        self.scopes = {}
        self.edges = {}
        self.readers = set()
        self.destinations = {"root"}

    def scope(self, key):
        if key in self.scopes:
            return self.scopes[key]
        file, name = key
        if file not in self.trees:
            self.trees[file] = st.parse(self.root, file)
        tree = self.trees[file]
        node = (
            tree
            if not name
            else next(
                (
                    n
                    for n in tree.body
                    if isinstance(n, ast.FunctionDef) and n.name == name
                ),
                None,
            )
        )
        if node is None:
            return None
        imports = st.bindings(str(self.root), file, tree, self.search_roots)
        if name:
            imports.update(st.bindings(str(self.root), file, node, self.search_roots))
        # Fixture trees need no copy of the loader: its import is the terminal
        # operation being recognized, rather than code to execute or inspect.
        for item in list(st.scope_nodes(tree)) + list(st.scope_nodes(node)):
            if isinstance(item, ast.Import):
                for alias in item.names:
                    if alias.name in {"config_loader", "scripts.config_loader"}:
                        imports[alias.asname or alias.name] = (_LOADER[0], None)
            if isinstance(item, ast.ImportFrom) and item.module in {
                "config_loader",
                "scripts.config_loader",
            }:
                for alias in item.names:
                    imports[alias.asname or alias.name] = (_LOADER[0], alias.name)
        assignments = []
        nodes = list(st.scope_nodes(node))
        for item in nodes:
            if isinstance(item, ast.Assign):
                assignments.extend((target, item.value) for target in item.targets)
            elif isinstance(item, ast.AnnAssign) and item.value is not None:
                assignments.append((item.target, item.value))
        result = (node, imports, assignments, nodes)
        self.scopes[key] = result
        return result

    def binding(self, key, expression, before=None):
        spelling = _dotted(expression)
        if not spelling:
            return None
        assignments = self.scope(key)[2]
        before = expression.lineno if before is None else before
        for target, value in reversed(assignments):
            if target.lineno >= before:
                continue
            if _dotted(target) == spelling:
                return key, value, None
            if isinstance(target, (ast.Tuple, ast.List)):
                for index, part in enumerate(target.elts):
                    if _dotted(part) == spelling:
                        return key, value, index
        if key[1]:
            args = self.scope(key)[0].args
            if spelling in {
                arg.arg for arg in args.posonlyargs + args.args + args.kwonlyargs
            }:
                return None
            return self.binding((key[0], ""), expression, before=10**9)
        return None

    def symbol(self, key, expression, seen=frozenset()):
        spelling = _dotted(expression)
        token = (key, spelling)
        if not spelling or token in seen:
            return None
        seen = seen | {token}
        binding = self.binding(key, expression)
        if binding is not None and binding[2] is None:
            return self.symbol(binding[0], binding[1], seen)
        imports = self.scope(key)[1]
        parts = spelling.split(".")
        for size in range(len(parts), 0, -1):
            prefix = ".".join(parts[:size])
            if prefix not in imports:
                continue
            file, attribute = imports[prefix]
            tail = parts[size:]
            if attribute is None and len(tail) == 1:
                attribute = tail[0]
            elif tail:
                return None
            target = (file, attribute)
            if target == _LOADER:
                return target
            if attribute is None:
                return None
            scope = self.scope((file, ""))
            if any(
                isinstance(n, ast.FunctionDef) and n.name == attribute
                for n in scope[0].body
            ):
                return target
            return self.symbol((file, ""), ast.Name(id=attribute, lineno=10**9), seen)
        tree = self.trees[key[0]]
        if any(
            isinstance(n, ast.FunctionDef) and n.name == spelling for n in tree.body
        ):
            return key[0], spelling
        return None

    def graph(self, key):
        if key in self.edges:
            return
        self.edges[key] = []
        scope = self.scope(key)
        if scope is None:
            return
        for node in scope[3]:
            if isinstance(node, (ast.Lambda, ast.ClassDef, ast.AsyncFunctionDef)) or (
                key[1] and isinstance(node, ast.FunctionDef)
            ):
                for child in ast.walk(node):
                    if (
                        isinstance(child, ast.Call)
                        and self.symbol(key, child.func) == _LOADER
                    ):
                        raise AssertionError(
                            "%s:%d: cannot resolve config loader root in %s"
                            % (key[0], child.lineno, type(node).__name__)
                        )
            if not isinstance(node, ast.Call):
                continue
            target = self.symbol(key, node.func)
            if target is None:
                continue
            self.edges[key].append((node, target))
            if target == _LOADER:
                self.readers.add(key)
            else:
                self.graph(target)

    def argument(self, call, index, name):
        if index < len(call.args) and not isinstance(call.args[index], ast.Starred):
            return call.args[index]
        return next((kw.value for kw in call.keywords if kw.arg == name), None)

    def value(self, key, node, parameters, seen=frozenset()):
        if node is None:
            return _FIXED
        token = (key, id(node))
        if token in seen:
            return _UNKNOWN
        seen = seen | {token}
        binding = self.binding(key, node)
        if binding is not None:
            owner, expression, index = binding
            value = self.value(owner, expression, parameters, seen)
            if index is not None:
                return (
                    value[index]
                    if isinstance(value, tuple) and index < len(value)
                    else _UNKNOWN
                )
            return value
        if isinstance(node, ast.Constant):
            return _FIXED
        if isinstance(node, ast.Name):
            return parameters.get(
                node.id, _FIXED if node.id == "__file__" else _UNKNOWN
            )
        if isinstance(node, ast.Attribute):
            base = self.value(key, node.value, parameters, seen)
            if base == _NAMESPACE:
                return _ROOT if node.attr in self.destinations else _FIXED
            return _UNKNOWN
        if isinstance(node, (ast.Tuple, ast.List)):
            return tuple(self.value(key, n, parameters, seen) for n in node.elts)
        if isinstance(node, ast.BoolOp):
            return _merge([self.value(key, n, parameters, seen) for n in node.values])
        if isinstance(node, ast.IfExp):
            return _merge(
                [self.value(key, n, parameters, seen) for n in (node.body, node.orelse)]
            )
        if isinstance(node, ast.Call):
            spelling = _dotted(node.func)
            if isinstance(node.func, ast.Attribute) and node.func.attr == "parse_args":
                return _NAMESPACE
            if spelling in _PATH_CALLS:
                return (
                    self.value(key, node.args[0], parameters, seen)
                    if node.args
                    else _FIXED
                )
            if spelling == "os.getcwd":
                return _FIXED
            if isinstance(node.func, ast.Attribute) and node.func.attr in {
                "resolve",
                "absolute",
            }:
                return self.value(key, node.func.value, parameters, seen)
            target = self.symbol(key, node.func)
            if target == ("scripts/corpus_level.py", "checkout"):
                return self.value(
                    key, self.argument(node, 0, "root"), parameters, seen
                ), _FIXED
            if target is not None and target != _LOADER:
                values = self.parameters(key, node, target, parameters, seen)
                returned = [
                    self.value(target, n.value, values, seen)
                    for n in self.scope(target)[3]
                    if isinstance(n, ast.Return)
                ]
                if returned and all(value == returned[0] for value in returned):
                    return returned[0]
        return _UNKNOWN

    def parameters(self, key, call, target, parameters, seen=frozenset()):
        args = self.scope(target)[0].args
        result = {}
        positional = args.posonlyargs + args.args
        defaults = dict(
            zip(
                (arg.arg for arg in positional[len(positional) - len(args.defaults) :]),
                args.defaults,
                strict=True,
            )
        )
        defaults.update(
            (arg.arg, default)
            for arg, default in zip(args.kwonlyargs, args.kw_defaults, strict=True)
            if default is not None
        )
        for index, arg in enumerate(positional):
            expression = self.argument(call, index, arg.arg)
            if expression is not None:
                result[arg.arg] = self.value(key, expression, parameters, seen)
            elif arg.arg in defaults:
                result[arg.arg] = self.value(
                    (target[0], ""), defaults[arg.arg], {}, seen
                )
            else:
                result[arg.arg] = _UNKNOWN
        for arg in args.kwonlyargs:
            expression = self.argument(call, len(call.args), arg.arg)
            if expression is not None:
                result[arg.arg] = self.value(key, expression, parameters, seen)
            elif arg.arg in defaults:
                result[arg.arg] = self.value(
                    (target[0], ""), defaults[arg.arg], {}, seen
                )
            else:
                result[arg.arg] = _UNKNOWN
        return result

    def reads_root(self, key, parameters, active=frozenset()):
        if key in active or key not in self.readers:
            return False
        active = active | {key}
        found = False
        for call, target in self.edges[key]:
            if target == _LOADER:
                expression = self.argument(call, 0, "root")
                value = (
                    self.value(key, expression, parameters)
                    if expression is not None
                    else _UNKNOWN
                )
                if value not in (_ROOT, _FIXED):
                    raise AssertionError(
                        "%s:%d: cannot resolve config loader root %s"
                        % (
                            key[0],
                            call.lineno,
                            ast.unparse(expression)
                            if expression is not None
                            else "<expanded or missing root>",
                        )
                    )
                found |= value == _ROOT
            elif target in self.readers:
                values = self.parameters(key, call, target, parameters)
                found |= self.reads_root(target, values, active)
        return found

    def script(self, file):
        tree = self.scope((file, ""))[0]
        declarations = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_argument"
            and any(
                isinstance(arg, ast.Constant) and arg.value == "--root"
                for arg in node.args
            )
        ]
        if not declarations:
            return False
        self.destinations = {
            next(
                (
                    kw.value.value
                    for kw in node.keywords
                    if kw.arg == "dest" and isinstance(kw.value, ast.Constant)
                ),
                "root",
            )
            for node in declarations
        }
        entries = [(file, "")]
        if any(isinstance(n, ast.FunctionDef) and n.name == "main" for n in tree.body):
            entries.append((file, "main"))
        for key in entries:
            self.graph(key)
        changed = True
        while changed:
            before = len(self.readers)
            self.readers.update(
                key
                for key, edges in self.edges.items()
                if any(target in self.readers for _call, target in edges)
            )
            changed = len(self.readers) != before
        return any(self.reads_root(key, {}) for key in entries)


def derive_scripts(root, search_roots):
    """Scripts declaring --root whose parsed checkout reaches config_loader.read.

    Use the structure gate's walk exclusions. Follow plain assignments, imported
    aliases/re-exports, positional/keyword helper parameters, argparse namespaces,
    tuple unpacking, boolean defaults, path normalization and corpus checkout.
    A loader argument outside those forms is an error with file and line.
    """
    discovery = _Discovery(root, search_roots)
    return {
        relative
        for relative in st.python_files(Path(root) / "scripts")
        if discovery.script("scripts/" + relative)
    }


def select_cases(root, cases):
    """Template completeness rule: copier.yml requires every listed script.

    Generated projects may omit scripts already checked by the template; return
    each exclusion's reason so callers can expose it as a skip. Use the included
    rows for both discovery comparison and executable CLI cases.
    """
    root = Path(root)
    missing = {
        script for script, _extra in cases if not (root / "scripts" / script).is_file()
    }
    if (root / "copier.yml").is_file():
        assert not missing, "\n".join(
            "scripts/%s: listed script missing from copier template" % script
            for script in sorted(missing)
        )
    excluded = {
        script: (
            "scripts/%s: absent in generated project; "
            "the copier template checks every listed script" % script
        )
        for script in sorted(missing)
    }
    return [row for row in cases if row[0] not in missing], excluded


def check_cases(derived, listed, exemptions=None):
    """Fail when discovery is empty or its script set differs from CLI cases."""
    exemptions = {} if exemptions is None else exemptions
    for name, reason in exemptions.items():
        assert isinstance(reason, str) and reason.strip(), (
            "%s: exemption needs a reason" % name
        )
        assert name in listed - derived, "%s: stale exemption" % name
    findings = [] if derived else ["root-config discovery found zero scripts"]
    findings.extend(
        "scripts/%s: derived but not parametrized" % name
        for name in sorted(derived - listed)
    )
    findings.extend(
        "scripts/%s: parametrized but not derived" % name
        for name in sorted(listed - derived - exemptions.keys())
    )
    assert not findings, "\n".join(findings)
