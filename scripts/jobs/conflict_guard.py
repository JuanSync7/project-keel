"""
title: conflict_guard — a job never runs over a conflicted import
kind: script
layer: n/a
summary: The merge-conflict marker grammar copier's inline update writes, and the guard every `after` migration runs before it imports anything from the project. copier 9.x leaves a file both sides changed with `git merge-file` markers in it, and a job that then imports that module died on a SyntaxError traceback that named neither the file nor the remedy (a project's own edit to scripts/check_structure.py stopped the restamp so, measured on two downstream projects). `conflict_lines` finds each hunk: an opening marker line, then a separator line, then a closing marker line, labels allowed after the outer two and a diff3 base section allowed between, so a lone separator (a Markdown setext underline) and marker characters inside a line are not conflicts. `conflicted_imports` follows `import` and `from ... import` (packages, submodules and relative imports) from an entry file through each module it resolves on a search path under the project root, never into one outside it, scanning each for hunks before parsing it; `exit_if_conflicted` names the job, each conflicted file and line, and the command to rerun on stderr and exits 2, with no traceback. It imports nothing from the project, so its own import cannot be the one that fails, and it spawns nothing; scripts/jobs/resolve_stamp_conflicts.py reads its marker constants from here.
effect: read-only
"""

# 3.6-safe and stdlib-only on purpose: copier runs the jobs that import this
# under its own interpreter in a project that may have no virtualenv yet.
import ast
import os
import shlex
import sys

__all__ = [
    "BASE",
    "CLOSE",
    "MARKER_SIZE",
    "OPEN",
    "SPLIT",
    "conflict_line",
    "conflict_lines",
    "conflicted_imports",
    "exit_if_conflicted",
    "has_conflict",
    "marker",
    "rerun_command",
]

# `git merge-file` markers at its default size, any label (copier 9.x passes
# "before updating" / "last update" / "after updating"; nothing here depends on
# them). Spelled as repetitions so this file holds no marker text: a tree scan
# for leftover conflicts (test_copier_update.py's) reads it too.
MARKER_SIZE = 7
OPEN = "<" * MARKER_SIZE
BASE = "|" * MARKER_SIZE
SPLIT = "=" * MARKER_SIZE
CLOSE = ">" * MARKER_SIZE


def marker(line, mark):
    """True when *line* is *mark*, alone or followed by a space and a label.
    SPLIT carries no label, so only the bare line is one."""
    body = line.rstrip("\r\n")
    if mark == SPLIT:
        return body == mark
    return body == mark or body.startswith(mark + " ")


def conflict_lines(text):
    """The 1-based line of the opening marker of each complete hunk in *text*,
    in order. Lenient on purpose: a guard must see every hunk a merge could
    leave, so a second opening marker before the close restarts the hunk
    rather than refusing it (scripts/jobs/resolve_stamp_conflicts.py is the
    strict reader, because it writes)."""
    found = []
    opened = None
    split = False
    for lineno, line in enumerate(text.splitlines(), 1):
        if marker(line, OPEN):
            opened, split = lineno, False
        elif opened is not None and not split and marker(line, SPLIT):
            split = True
        elif split and marker(line, CLOSE):
            found.append(opened)
            opened, split = None, False
    return found


def conflict_line(text):
    """The line of the first hunk's opening marker, or None."""
    lines = conflict_lines(text)
    return lines[0] if lines else None


def has_conflict(text):
    """True when *text* holds at least one complete conflict hunk."""
    return conflict_line(text) is not None


def _under(path, root):
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def _resolve(dotted, search_path):
    """The files that importing *dotted* executes, outermost package first:
    `<dir>/<part>/__init__.py` for each package and `<dir>/<last>.py` (or its
    package) for the module, from the first search directory that has the
    first part. [] when no directory has it (the standard library)."""
    parts = dotted.split(".")
    for base in search_path:
        files = []
        here = base
        for i, part in enumerate(parts):
            package = os.path.join(here, part, "__init__.py")
            module = os.path.join(here, part + ".py")
            if os.path.isfile(package):
                files.append(package)
                here = os.path.join(here, part)
            elif os.path.isfile(module) and i == len(parts) - 1:
                files.append(module)
            else:
                break
        if files:
            return files
    return []


def _imports(tree, path):
    """(dotted name, search directories or None) for each import in *tree*; a
    relative import is resolved from *path*'s own package directory, and
    `from X import y` also names X.y, which is a submodule when one exists."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend((alias.name, None) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = os.path.dirname(path)
                for _ in range(node.level - 1):
                    base = os.path.dirname(base)
                where = [base]
            else:
                where = None
            prefix = node.module or ""
            if prefix:
                out.append((prefix, where))
            for alias in node.names:
                if alias.name != "*":
                    name = prefix + "." + alias.name if prefix else alias.name
                    out.append((name, where))
    return out


def conflicted_imports(entry_file, root, search_path=None):
    """Sorted (root-relative path, hunk line) for every conflict hunk in
    *entry_file* and each module it imports, transitively, that resolves to a
    file under *root*. *search_path* is where an absolute import is looked up
    (default: the entry file's own directory); a name it does not resolve, or
    resolves outside *root*, is not followed. A conflicted file is reported and
    not parsed, so the imports inside it are not followed either; a file that
    does not parse for any other reason is not followed (its job's own import
    reports that)."""
    root = os.path.realpath(root)
    entry = os.path.realpath(entry_file)
    search = [os.path.realpath(p) for p in (search_path or [os.path.dirname(entry)])]
    found = []
    seen = set()
    queue = [entry]
    while queue:
        path = queue.pop()
        if path in seen or not _under(path, root):
            continue
        seen.add(path)
        try:
            with open(path, "rb") as fh:
                text = fh.read().decode("utf-8")
        except (OSError, ValueError):
            continue
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        lines = conflict_lines(text)
        if lines:
            found.extend((rel, line) for line in lines)
            continue
        try:
            tree = ast.parse(text, path)
        except (SyntaxError, ValueError):
            continue
        queue.extend(
            os.path.realpath(target)
            for dotted, where in _imports(tree, path)
            for target in _resolve(dotted, where or search)
        )
    return sorted(found)


def rerun_command(entry_file, root, argv):
    """The shell line that runs *entry_file* again from *root* with *argv*,
    under this interpreter: what a job that has no make target tells its
    owner to run once the conflicts are resolved."""
    script = os.path.relpath(os.path.realpath(entry_file), os.path.realpath(root))
    words = [sys.executable, script.replace(os.sep, "/")] + list(argv)
    return " ".join(shlex.quote(word) for word in words)


def exit_if_conflicted(entry_file, root, job, rerun, search_path=None):
    """Return None when nothing *entry_file* imports under *root* holds a
    conflict hunk. Otherwise write one message to stderr — *job*, each file
    and line, and *rerun*, the command to run once they are resolved — and
    raise SystemExit(2), so the caller stops before the import that would
    raise a SyntaxError."""
    found = conflicted_imports(entry_file, root, search_path)
    if not found:
        return
    sys.stderr.write(
        "%s: cannot run while modules it imports are conflicted: %s; resolve "
        "them, then run `%s`\n"
        % (job, ", ".join("%s (line %d)" % pair for pair in found), rerun)
    )
    raise SystemExit(2)
