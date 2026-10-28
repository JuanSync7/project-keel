"""
title: Test helper — copy listed files with every project module they import
kind: tests
layer: n/a
summary: copy_with_imports copies the files a fixture lists from a project root into a scratch directory, each at its own relative path, together with every project module a listed Python file imports, followed to its end; imports_closure is the list it copies. An import resolves the way the copied file meets it at run time: first against the importer's own directory (a script's directory is the head of its sys.path), then against scripts/, which every tests/ helper and scripts/jobs/ module puts on its path. tests/source_tree.py import_edges reads the imports, so an import inside a function counts and a standard-library or installed name never resolves to a project file. A fixture that lists its entry scripts this way keeps starting when one of them begins importing a new sibling; a hand-kept list does not. A listed file that does not exist raises AssertionError naming it, before anything is written. It cannot see an import made through importlib or `__import__`, or one a module finds through a sys.path entry other than those two; that file stays the calling test's to list.
effect: writes
rerun: fixed-point
rerun_proof: tests/integration/test_script_copy.py
"""

import os
import posixpath
import shutil

import source_tree

_PY = ".py"
# Every tests/ helper and scripts/jobs/ module puts scripts/ on its sys.path.
_SHARED_ROOT = "scripts/"


def imports_closure(root, relpaths):
    """*relpaths* and every project module a listed `.py` imports, transitively,
    as a sorted list of relative paths under *root*. Raises AssertionError
    naming each listed file *root* does not hold."""
    root = str(root)
    missing = [
        rel
        for rel in relpaths
        if not os.path.isfile(os.path.join(root, *rel.split("/")))
    ]
    if missing:
        raise AssertionError(
            "cannot copy from %s: no such file %s" % (root, ", ".join(sorted(missing)))
        )
    seen = set(relpaths)
    todo = sorted(rel for rel in seen if rel.endswith(_PY))
    while todo:
        importer = todo.pop()
        own = posixpath.dirname(importer)
        search_roots = [own + "/" if own else "", _SHARED_ROOT]
        for _importer, _lineno, imported in source_tree.import_edges(
            root, [importer], search_roots
        ):
            if imported not in seen:
                seen.add(imported)
                todo.append(imported)
    return sorted(seen)


def copy_with_imports(dest, root, relpaths):
    """Copy *imports_closure* of *relpaths* from *root* into *dest*, each at
    its relative path. -> the relative paths written, sorted.

    Each file is a whole-file overwrite, so a second call into the same *dest*
    writes the same bytes."""
    dest = str(dest)
    written = imports_closure(root, relpaths)
    for rel in written:
        target = os.path.join(dest, *rel.split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy(os.path.join(str(root), *rel.split("/")), target)
    return written
