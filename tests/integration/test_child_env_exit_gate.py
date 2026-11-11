"""
title: Child environment refusals stop at entry boundaries
summary: Follows project function references from main to build_child_env and fails an unhandled refusal, including references through imported libraries. Static analysis never executes an entry script.
"""

import ast
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "tests"))

import source_tree as st  # noqa: E402

pytestmark = pytest.mark.integration


def _catches(handler):
    names = (
        {
            node.id if isinstance(node, ast.Name) else node.attr
            for node in ast.walk(handler.type)
            if isinstance(node, (ast.Name, ast.Attribute))
        }
        if handler.type is not None
        else set()
    )
    return bool(names & {"ChildEnvError", "Exception", "BaseException"})


def refusal_findings(root):
    """Find entry functions with an unprotected path to the environment builder.

    References include callbacks and class bodies, conservatively. Dynamic
    getattr and cross-module object dispatch are outside this static check.
    A handler that re-raises cannot establish a refusal boundary.
    Any other handler of the refusal, or of Exception, is trusted to report it.
    A rule that also judged each handler's body flagged twelve handlers on
    entry paths and no hidden refusal.
    Each of the twelve translates the refusal to its script's own error,
    returns it through the script's refusal helper, or records the run red.
    tests/integration/test_swallowed_error_gate.py fails a handler whose body
    only drops the error or returns a fixed value.
    tests/integration/test_exit_gate.py fails a literal that main returns.
    """
    files = st.python_files(root)
    roots = st.import_layers(root)["search_roots"]
    trees = {
        path: st.parse(root, path)
        for path in files
        if path.startswith(("scripts/", "agents/", "evals/", "src/"))
    }
    definitions = {}
    imports = {}
    for path, tree in trees.items():
        imports[path] = st.bindings(root, path, tree, roots)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                definitions[path, node.name] = node

    def resolve(path, name, seen=frozenset()):
        key = (path, name)
        if key in seen:
            return None
        if key in definitions or key == ("scripts/child_env.py", "build_child_env"):
            return key
        head, _, tail = name.partition(".")
        target = imports.get(path, {}).get(head)
        if target is None:
            return None
        module, symbol = target
        return resolve(module, ".".join(filter(None, (symbol, tail))), seen | {key})

    def references(path, node):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
            resolve(path, ast.unparse(decorator))
            == ("scripts/child_env_entry.py", "child_env_errors")
            for decorator in node.decorator_list
        ):
            return
        if isinstance(node, ast.Try):
            handlers = [h for h in node.handlers if _catches(h)]
            protected = any(
                not any(
                    isinstance(n, ast.Raise)
                    and (
                        n.exc is None
                        or isinstance(n.exc, ast.Name)
                        and n.exc.id == h.name
                    )
                    for n in ast.walk(h)
                )
                for h in handlers
            )
            bodies = node.orelse + node.finalbody + node.handlers
            if not protected:
                bodies += node.body
            for child in bodies:
                yield from references(path, child)
            return
        if isinstance(node, (ast.Name, ast.Attribute)):
            name = ast.unparse(node)
            target = resolve(path, name)
            if target is not None:
                yield target
        for ast_child in ast.iter_child_nodes(node):
            yield from references(path, ast_child)

    edges = {
        key: set(references(key[0], node)) - {key} for key, node in definitions.items()
    }
    unsafe = {("scripts/child_env.py", "build_child_env")}
    while True:
        found = {key for key, targets in edges.items() if targets & unsafe}
        if found <= unsafe:
            break
        unsafe |= found
    return sorted(
        "%s:%d: ChildEnvError can escape main; report CONFIG before finish(main())"
        % (path, definitions[path, name].lineno)
        for path, name in unsafe
        if name == "main"
        and any(
            isinstance(node, ast.If) and "__main__" in ast.unparse(node.test)
            for node in trees[path].body
        )
    )


def test_entry_refusals_are_reported():
    findings = refusal_findings(_ROOT)
    assert not findings, "\n".join(findings)


@pytest.mark.parametrize(
    ("body", "escapes"),
    [
        ("return child()", True),
        (
            "try:\n        return child()\n    except ChildEnvError:\n        return 14",
            False,
        ),
        (
            "try:\n        pass\n    except ChildEnvError:\n        return 14\n    return child()",
            True,
        ),
        (
            "try:\n        return child()\n    except ChildEnvError:\n        raise",
            True,
        ),
        (
            "try:\n        return child()\n    except ChildEnvError as exc:\n        raise exc",
            True,
        ),
    ],
)
def test_gate_follows_a_new_entry_through_a_library(
    tmp_path, monkeypatch, body, escapes
):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    sources = {
        "scripts/child_env.py": "def build_child_env(): pass\nclass ChildEnvError(Exception): pass\n",
        "scripts/library.py": "from child_env import build_child_env as env\ndef child(): return env()\n",
        "scripts/future.py": (
            "from library import child\nfrom child_env import ChildEnvError\n"
            "def main():\n    "
            + body
            + "\nif __name__ == '__main__':\n    finish(main())\n"
        ),
    }
    for path, text in sources.items():
        (tmp_path / path).write_text(text, encoding="utf-8")
    monkeypatch.setattr(st, "python_files", lambda root: list(sources))
    monkeypatch.setattr(
        st, "import_layers", lambda root: {"search_roots": ["scripts/"]}
    )
    findings = refusal_findings(tmp_path)
    assert bool(findings) is escapes
    if findings:
        assert "scripts/future.py:" in findings[0]
