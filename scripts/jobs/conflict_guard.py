"""
title: conflict_guard — a job never runs over a conflicted file it reads
kind: script
layer: n/a
summary: The merge-conflict marker grammar copier's inline update writes, and the guard every `after` migration runs before it imports anything from the project. copier 9.x leaves a file both sides changed with `git merge-file` markers in it, and a job that then imports that module died on a SyntaxError traceback that named neither the file nor the remedy (a project's own edit to scripts/check_structure.py stopped the restamp so, measured on two downstream projects); a job whose module then read a conflicted data file died on a JSON parse error the same way. `conflict_lines` finds each hunk: an opening marker line, then a separator line, then a closing marker line, labels allowed after the outer two and a diff3 base section allowed between, so a lone separator (a Markdown setext underline) and marker characters inside a line are not conflicts. `job_closure` follows `import` and `from ... import` (packages, submodules and relative imports) from an entry file through each module it resolves on a search path under the project root, never into one outside it, scanning each for hunks before parsing it. Each module in that closure may declare the fixed project files it reads in a module-level `PROJECT_READS` tuple of root-relative POSIX literals, and exempt a path literal it never opens in `PROJECT_PATHS_NOT_READ` as (path, reason) pairs; `declared_reads` collects the first by AST, never by import, and raises GuardConfigError, naming the module and line, on a declaration it cannot read. `conflicted_inputs` names each conflicted module and each conflicted declared read with its hunk lines, skipping an absent read; `exit_if_conflicted` writes the job, each file and line, and the command to rerun on stderr in one line built on `REFUSAL` and exits 2, with no traceback, and exits 2 naming the declaration when it cannot check. Under an update a job is run with `--finish-with PYTHON` (`finish_with_arg`), and its rerun is the command that finishes the update (`finish_rerun`, scripts/jobs/finish_update.py), because copier stops at the first failed migration; `read_refusals` parses the line back, which is how scripts/audit_project.py tells a migration's refusal from any other failed update. It imports nothing from the project, so its own import cannot be the one that fails, and it spawns nothing; scripts/jobs/resolve_stamp_conflicts.py reads its marker constants from here, and tests/integration/test_copier_job_conflict_refusal.py proves every job's declarations complete. The union is over every module the job imports, so a job imports only a module whose code it runs: one kept for a constant hands the job each of its reads (restamp_docs importing check_structure was refused over a conflicted Makefile it never opens), and the same test fails a job's closure that holds a reading module from which nothing but literals is taken.
effect: read-only
"""

# 3.6-safe and stdlib-only on purpose: copier runs the jobs that import this
# under its own interpreter in a project that may have no virtualenv yet.
import ast
import os
import re
import shlex
import sys

__all__ = [
    "BASE",
    "CLOSE",
    "FINISH_FLAG",
    "FINISH_SCRIPT",
    "GuardConfigError",
    "MARKER_SIZE",
    "NOT_READ_NAME",
    "OPEN",
    "READS_NAME",
    "REFUSAL",
    "SPLIT",
    "conflict_line",
    "conflict_lines",
    "conflicted_imports",
    "conflicted_inputs",
    "declared_reads",
    "exit_if_conflicted",
    "finish_rerun",
    "finish_with_arg",
    "has_conflict",
    "job_closure",
    "job_rerun",
    "marker",
    "read_refusals",
    "refusal",
    "rerun_command",
]

# The module-level names a job's module declares its fixed project reads in,
# and the path literals it names but never opens (with a reason each).
READS_NAME = "PROJECT_READS"
NOT_READ_NAME = "PROJECT_PATHS_NOT_READ"

# The command that finishes an update a migration stopped, and the flag that
# hands a migration the interpreter to name in it.
FINISH_SCRIPT = "scripts/jobs/finish_update.py"
FINISH_FLAG = "--finish-with"

# This module names the finish script only to print it. A literal, not
# FINISH_SCRIPT: a declaration is read by AST, never by running the module.
PROJECT_PATHS_NOT_READ = (
    ("scripts/jobs/finish_update.py", "the command a refusal names, never opened"),
)

# `git merge-file` markers at its default size, any label (copier 9.x passes
# "before updating" / "last update" / "after updating"; nothing here depends on
# them). Spelled as repetitions so this file holds no marker text: a tree scan
# for leftover conflicts (test_copier_update.py's) reads it too.
MARKER_SIZE = 7
OPEN = "<" * MARKER_SIZE
BASE = "|" * MARKER_SIZE
SPLIT = "=" * MARKER_SIZE
CLOSE = ">" * MARKER_SIZE

# The words between a job's name and its files in the one line
# exit_if_conflicted writes; read_refusals reads that line back by them.
REFUSAL = "cannot run while files it reads are conflicted"
_REFUSAL_LINE = re.compile(
    r"^(?P<job>[\w.-]+): "
    + re.escape(REFUSAL)
    + r": (?P<items>.+); resolve them, then run `(?P<rerun>[^`]+)`$",
    re.MULTILINE,
)
_REFUSAL_ITEM = re.compile(r"^(?P<path>.+) \(line (?P<line>\d+)\)$")


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


class GuardConfigError(ValueError):
    """A `PROJECT_READS` declaration the guard cannot read, or a declared read
    that exists and cannot be opened: the guard cannot vouch for the job."""


def _string(node):
    # 3.6 and 3.7 parse a string as ast.Str, later ones as ast.Constant; the
    # name is compared rather than ast.Str touched, which 3.12 deprecates.
    if type(node).__name__ == "Constant" and isinstance(node.value, str):
        return node.value
    if type(node).__name__ == "Str":
        return node.s
    return None


def _assigned(stmt, name):
    """The value *stmt* binds to *name* at module level, or None."""
    if isinstance(stmt, ast.Assign):
        if any(isinstance(t, ast.Name) and t.id == name for t in stmt.targets):
            return stmt.value
    elif (
        isinstance(stmt, ast.AnnAssign)
        and isinstance(stmt.target, ast.Name)
        and stmt.target.id == name
    ):
        return stmt.value
    return None


def declared_reads(tree, path):
    """The root-relative POSIX paths the module *tree* (from *path*) declares
    in its module-level `PROJECT_READS`, in order; [] when it declares none.
    A value that is not a tuple or list of string literals, or an entry that
    is empty, absolute, holds a backslash or a `..` part, raises
    GuardConfigError as `<path>:<line>: ...`."""
    out = []
    for stmt in tree.body:
        value = _assigned(stmt, READS_NAME)
        if value is None:
            continue
        if not isinstance(value, (ast.Tuple, ast.List)):
            raise GuardConfigError(
                "%s:%d: %s must be a tuple of string literals"
                % (path, stmt.lineno, READS_NAME)
            )
        for element in value.elts:
            text = _string(element)
            where = "%s:%d: %s entry" % (path, element.lineno, READS_NAME)
            if text is None:
                raise GuardConfigError("%s is not a string literal" % where)
            if not text:
                raise GuardConfigError("%s is empty" % where)
            if "\\" in text:
                raise GuardConfigError("%s %r holds a backslash" % (where, text))
            if text.startswith("/"):
                raise GuardConfigError("%s %r is absolute" % (where, text))
            if ".." in text.split("/"):
                raise GuardConfigError("%s %r climbs out with .." % (where, text))
            out.append(text)
    return out


def _decode(raw):
    # The marker grammar is ASCII; latin-1 decodes any byte, so a read that is
    # not UTF-8 is still scanned rather than skipped.
    try:
        return raw.decode("utf-8")
    except ValueError:
        return raw.decode("latin-1")


def _walk(entry_file, root, search_path):
    """(modules, reads): {realpath: hunk lines} for every module the import
    walk from *entry_file* reaches under *root*, and the sorted set of the
    reads those modules declare. A conflicted module is not parsed, so neither
    its imports nor its declaration are followed; a module that does not
    decode or parse for any other reason is not followed either (its job's
    own import reports that)."""
    root = os.path.realpath(root)
    entry = os.path.realpath(entry_file)
    search = [os.path.realpath(p) for p in (search_path or [os.path.dirname(entry)])]
    modules = {}
    reads = set()
    queue = [entry]
    while queue:
        path = queue.pop()
        if path in modules or not _under(path, root):
            continue
        modules[path] = []
        try:
            with open(path, "rb") as fh:
                text = fh.read().decode("utf-8")
        except (OSError, ValueError):
            continue
        lines = conflict_lines(text)
        if lines:
            modules[path] = lines
            continue
        try:
            tree = ast.parse(text, path)
        except (SyntaxError, ValueError):
            continue
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        reads.update(declared_reads(tree, rel))
        queue.extend(
            os.path.realpath(target)
            for dotted, where in _imports(tree, path)
            for target in _resolve(dotted, where or search)
        )
    return modules, sorted(reads)


def _rel(path, root):
    return os.path.relpath(path, os.path.realpath(root)).replace(os.sep, "/")


def job_closure(entry_file, root, search_path=None):
    """Sorted (root-relative path, real path) of *entry_file* and every module
    it imports, transitively, that resolves to a file under *root* — the
    modules whose declarations guard the job. *search_path* is where an
    absolute import is looked up (default: the entry file's directory)."""
    modules, _reads = _walk(entry_file, root, search_path)
    return sorted((_rel(path, root), path) for path in modules)


def conflicted_imports(entry_file, root, search_path=None):
    """Sorted (root-relative path, hunk line) for every conflict hunk in
    *entry_file* and each module it imports, transitively, that resolves to a
    file under *root*; a name the search path does not resolve, or resolves
    outside *root*, is not followed. A conflicted file is reported and not
    parsed, so the imports inside it are not followed either."""
    modules, _reads = _walk(entry_file, root, search_path)
    return sorted(
        (_rel(path, root), line) for path, lines in modules.items() for line in lines
    )


def conflicted_inputs(entry_file, root, search_path=None):
    """conflicted_imports, and each conflict hunk in a fixed project file a
    module of that closure declares reading. An absent read is skipped (it
    cannot be conflicted); one that exists and cannot be read, or a
    declaration the guard cannot read, raises GuardConfigError."""
    modules, reads = _walk(entry_file, root, search_path)
    found = [
        (_rel(path, root), line) for path, lines in modules.items() for line in lines
    ]
    base = os.path.realpath(root)
    for rel in reads:
        path = os.path.join(base, *rel.split("/"))
        if not os.path.lexists(path):
            continue
        try:
            with open(path, "rb") as fh:
                text = _decode(fh.read())
        except OSError as exc:
            raise GuardConfigError("%s cannot be read: %s" % (rel, exc)) from exc
        found.extend((rel, line) for line in conflict_lines(text))
    return sorted(set(found))


def rerun_command(entry_file, root, argv):
    """The shell line that runs *entry_file* again from *root* with *argv*,
    under this interpreter: what a job that has no make target tells its
    owner to run once the conflicts are resolved."""
    script = os.path.relpath(os.path.realpath(entry_file), os.path.realpath(root))
    words = [sys.executable, script.replace(os.sep, "/")] + list(argv)
    return " ".join(shlex.quote(word) for word in words)


def finish_rerun(python):
    """The shell line that finishes an update a migration stopped, under the
    interpreter copier ran the migration with."""
    return shlex.quote(python) + " " + FINISH_SCRIPT


def finish_with_arg(argv):
    """The interpreter `--finish-with PYTHON` (or `--finish-with=PYTHON`) in
    *argv* names, or None: read before argparse, so a refusal over a module
    argparse's own job imports still names the finish command."""
    argv = list(argv)
    for i, word in enumerate(argv):
        if word == FINISH_FLAG and i + 1 < len(argv):
            return argv[i + 1]
        if word.startswith(FINISH_FLAG + "="):
            return word[len(FINISH_FLAG) + 1 :]
    return None


def job_rerun(entry_file, root, argv, finish_with=None):
    """The command a refusal names: the finish command under an update
    (*finish_with* is copier's interpreter), else rerun_command."""
    if finish_with:
        return finish_rerun(finish_with)
    return rerun_command(entry_file, root, argv)


def refusal(job, found, rerun):
    """The one line exit_if_conflicted writes for *found* (path, line) pairs."""
    return "%s: %s: %s; resolve them, then run `%s`\n" % (
        job,
        REFUSAL,
        ", ".join("%s (line %d)" % pair for pair in found),
        rerun,
    )


def exit_if_conflicted(entry_file, root, job, rerun, search_path=None):
    """Return None when nothing *entry_file* imports under *root*, and no
    file those modules declare reading, holds a conflict hunk. Otherwise write
    one line to stderr — *job*, each file and line, and *rerun*, the command
    to run once they are resolved — and raise SystemExit(2), so the caller
    stops before the import or read that would fail. A declaration the guard
    cannot read also exits 2, naming it: the guard fails closed."""
    try:
        found = conflicted_inputs(entry_file, root, search_path)
    except GuardConfigError as exc:
        sys.stderr.write("%s: cannot check the files it reads: %s\n" % (job, exc))
        raise SystemExit(2) from None
    if not found:
        return
    sys.stderr.write(refusal(job, found, rerun))
    raise SystemExit(2)


def read_refusals(text):
    """[(job, [(path, line)], rerun)] for each line of *text* that is exactly a
    refusal exit_if_conflicted writes, in order. A line whose file list holds
    an item without its `(line N)` is not a refusal: a reader that guessed
    would name a file the guard never named."""
    out = []
    for match in _REFUSAL_LINE.finditer(text):
        items = []
        for item in match.group("items").split(", "):
            found = _REFUSAL_ITEM.match(item)
            if found is None:
                items = None
                break
            items.append((found.group("path"), int(found.group("line"))))
        if items:
            out.append((match.group("job"), items, match.group("rerun")))
    return out
