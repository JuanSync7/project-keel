"""
title: Integration — the generator's own entry points stay wired up
kind: tests
layer: n/a
summary: Pins on the ways keel's generator rots silently, read off the real `make -n new` recipe and the real CI workflow. (1) `make new` must hand copier a RESOLVABLE template path — copier records the CLI argument verbatim as `_src_path`, so a literal `.` resolves to the generated project itself and `copier update` dies there on an unhandled traceback. (2) It must refuse a dirty template, whose `_commit` would exist only in copier's throwaway clone. (3) CI must install the optional `template` extra AND declare it required, or every copier test importorskips and the template's own generation/update gates never run. (4) A test module that imports copier routes the import through `optional_deps`; one that only names copier in a string imports nothing that could skip. Imports nothing optional on purpose — this pin must never itself skip, or the fix it guards is circular.
"""

import ast
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

import ci_adapters

_ROOT = Path(__file__).resolve().parents[2]

# Self-neutralising downstream. `_exclude` prunes these modules at GENERATION, but
# copier's `_exclude` can never retire a file on `copier update` — it renders the old
# template copy with the UNION of the old and new excludes precisely so nothing is
# deleted (copier/_main.py). So a project generated BEFORE the prune landed still ships
# them, and `copier update` hands it the newer ci.yml that installs the `template`
# extra and declares it required — turning its CI red via the very update meant
# to fix CI (measured: 6 of 8 failed). A meta-test only means anything where a
# `copier.yml` exists, so say so here rather than relying on pruning alone.
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (_ROOT / "copier.yml").is_file(),
        reason="not a copier template — this is a generated project",
    ),
]


def _make_n_new(**overrides):
    """The `new` recipe as make would run it — expanded, but not executed."""
    argv = ["make", "-n", "new", "DEST=probe-dest-never-created"]
    argv += ["%s=%s" % kv for kv in overrides.items()]
    r = subprocess.run(argv, cwd=str(_ROOT), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def _recipe_line(stdout, needle):
    """One expanded recipe line (backslash continuations rejoined) containing needle."""
    lines = stdout.splitlines()
    hits = [i for i, ln in enumerate(lines) if needle in ln]
    assert len(hits) == 1, "expected exactly one %r line in:\n%s" % (needle, stdout)
    i = hits[0]
    block = [lines[i]]
    while block[-1].rstrip().endswith("\\"):
        i += 1
        block.append(lines[i])
    return "\n".join(block)


@pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
def test_make_new_hands_copier_a_resolvable_template_path():
    """`make new` is keel's advertised generator entry point, and copier stores the
    source argument verbatim in the generated project's `.copier-answers.yml`. With
    a relative argument the recorded origin is re-resolved against the *project's*
    cwd on update: copier clones the project as if it were the template and git dies
    with `pathspec '<keel sha>' did not match any file(s) known to git` — a raw
    plumbum traceback, no diagnostic. So the argument must be absolute and must
    actually be this template (`copier.yml` present)."""
    argv = shlex.split(_recipe_line(_make_n_new(), "copier copy"))
    # `copier copy [options] SRC DEST` — take SRC positionally from the end rather
    # than as "the word after `copy`", which broke the moment --vcs-ref was added.
    assert argv[-1] == "probe-dest-never-created", (
        "DEST is not the last argument of the copy recipe: %r" % argv
    )
    src = Path(argv[-2])

    assert src.is_absolute(), (
        "`make new` passes copier the relative template path %r; copier records it "
        "verbatim as _src_path, so `copier update` in the generated project resolves "
        "it against the project and fails" % str(src)
    )
    assert src.resolve() == _ROOT.resolve()
    assert (src / "copier.yml").is_file(), (
        "%s is not a copier template root (no copier.yml)" % src
    )


@pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
def test_make_new_pins_the_template_revision_it_generates_from():
    """With no `--vcs-ref`, copier does not use HEAD — `Template.ref` is None and it
    resolves `self.ref or get_latest_tag(...)` (copier/_template.py), i.e. the newest
    TAG. Harmless only while keel has no tags; the moment `v0.1.0` is cut (the
    outstanding pass-1 item) `make new` starts generating from the tag, so a
    maintainer smoke-testing a template change gets a project that silently does not
    contain it. Every automated copier test already pins `vcs_ref="HEAD"`; the shipped
    recipe must be explicit too, and overridable for a release smoke-test."""
    line = _recipe_line(_make_n_new(), "copier copy")
    argv = shlex.split(line)

    assert "--vcs-ref" in argv, (
        "`make new` passes copier no --vcs-ref, so once keel is tagged it generates "
        "from the newest tag instead of the working checkout:\n" + line
    )
    assert argv[argv.index("--vcs-ref") + 1] == "HEAD", (
        "the default template revision must be HEAD (the checkout the user is "
        "looking at), not %r" % argv[argv.index("--vcs-ref") + 1]
    )

    # ...and overridable, so cutting a release can smoke-test the tag itself.
    pinned = shlex.split(_recipe_line(_make_n_new(VCS_REF="v9.9.9"), "copier copy"))
    assert pinned[pinned.index("--vcs-ref") + 1] == "v9.9.9", (
        "VCS_REF= does not override the default revision"
    )


@pytest.mark.skipif(
    shutil.which("make") is None or shutil.which("git") is None,
    reason="needs make and git",
)
def test_make_new_refuses_a_template_that_is_not_a_git_checkout(tmp_path):
    """`git status --porcelain 2>/dev/null` prints nothing AND discards rc=128 outside
    a repository, so the dirty-tree guard read a ZIP download or an
    `rsync --exclude=.git` copy as *clean* and generated happily. copier then records
    no `_commit` at all and the project can never `copier update` — the exact harm the
    guard exists to prevent, waved through by the guard itself. Being repo-less is not
    a dirtiness question, so ALLOW_DIRTY must NOT override it."""
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    guard = _recipe_line(_make_n_new(), "rev-parse")

    r = subprocess.run(
        ["sh", "-c", guard], cwd=str(plain), capture_output=True, text=True
    )
    assert r.returncode == 2, (
        "`make new` does not refuse a non-git template, so it hands the user a "
        "project with no recorded `_commit` and no way to update:\n"
        + r.stdout
        + r.stderr
    )
    assert "git" in r.stdout.lower(), "the refusal must say what is wrong"

    forced = subprocess.run(
        ["sh", "-c", _recipe_line(_make_n_new(ALLOW_DIRTY="1"), "rev-parse")],
        cwd=str(plain),
        capture_output=True,
        text=True,
    )
    assert forced.returncode == 2, (
        "ALLOW_DIRTY=1 overrode the not-a-git-checkout refusal; it is an escape hatch "
        "for uncommitted work, and no amount of it can produce a `_commit`"
    )


@pytest.mark.skipif(
    shutil.which("make") is None or shutil.which("git") is None,
    reason="needs make and git",
)
def test_make_new_refuses_a_dirty_template(tmp_path):
    """The other half of the resolvable-origin contract. From a dirty template copier
    commits the working changes into its own throwaway clone and records THAT sha as
    `_commit` — a commit no clone of keel has ever seen, so the generated project dies
    on the same `pathspec ... did not match` as the relative-path bug. `make new` must
    refuse, with an `ALLOW_DIRTY=1` escape hatch for template authors iterating.

    Drives the real recipe text against real git repos rather than pinning a string."""

    def run_guard(stdout, cwd):
        return subprocess.run(
            ["sh", "-c", _recipe_line(stdout, "git status --porcelain")],
            cwd=str(cwd),
            capture_output=True,
            text=True,
        )

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=str(repo), capture_output=True, text=True)

    clean = run_guard(_make_n_new(), repo)
    assert clean.returncode == 0, "the guard rejects a CLEAN tree:\n" + clean.stdout

    (repo / "wip.txt").write_text("uncommitted work\n")
    dirty = run_guard(_make_n_new(), repo)
    assert dirty.returncode == 2, (
        "`make new` does not refuse a dirty template, so it can hand the user a project "
        "whose `_commit` exists only in copier's throwaway clone:\n" + dirty.stdout
    )
    assert "ALLOW_DIRTY" in dirty.stdout, "the refusal must name its escape hatch"

    allowed = run_guard(_make_n_new(ALLOW_DIRTY="1"), repo)
    assert allowed.returncode == 0, "ALLOW_DIRTY=1 must override the refusal"


def _shipped_ci_steps():
    """{adapter name: its steps} for every CI adapter keel ships, the GitLab one
    read from its `.jinja` twin (tests/ci_adapters.py shipped)."""
    adapters = ci_adapters.shipped(_ROOT)
    assert adapters, (
        "keel ships no CI adapter of config/project.json ci_pipeline.adapters"
    )
    return {
        name: ci_adapters.adapter_steps(path, name) for name, path in adapters.items()
    }


def test_ci_installs_the_optional_template_extra():
    """`template = ["copier>=9"]` is an optional extra. Until CI installs it, every
    copier test skips and the generation/update gates are decorative. Held for
    every CI adapter keel ships."""
    for name, steps in _shipped_ci_steps().items():
        installs = [s["run"] for s in steps if "pip install -e" in s["run"]]
        assert installs, "%s no longer does an editable install of the project" % name
        assert any("template" in run for run in installs), (
            "no %s step installs the `template` extra, so copier is absent and every "
            "tests/integration/test_copier_*.py silently skips:\n"
            % name
            + "\n".join(installs)
        )


def test_ci_declares_the_template_surface_required_for_the_suite():
    """Installing the extra is not enough: a broken install would degrade back to a
    silent skip. The suite step must declare the `template` surface required so a
    missing copier is a hard collection error in CI (a bare local clone leaves the
    declaration unset and still skips gracefully). Held for every CI adapter keel
    ships.

    Named surface, not just "the variable is present": declaring `dev,transport` and
    quietly dropping `template` would satisfy a mere-presence check while putting the
    generation and update gates straight back to sleep."""
    for name, steps in _shipped_ci_steps().items():
        suite = [s for s in steps if s["run"] == "make test"]
        assert len(suite) == 1, "expected exactly one `make test` step in %s" % name
        env = suite[0]["env"]
        assert "KEEL_REQUIRED_EXTRAS" in env, (
            "the %s step that runs the suite declares no required surfaces, so a "
            "missing `template` extra would skip the copier tests instead of "
            "failing: %s" % (name, env)
        )
        assert "template" in env["KEEL_REQUIRED_EXTRAS"].split(","), (
            "the %s suite step declares required surfaces but not `template`, so the "
            "copier generation/update gates can silently skip in CI again: %s"
            % (name, env)
        )


_IMPORT_CALLS = {"importorskip", "import_module", "__import__"}

# How a copier load in a test module reaches copier.
_ROUTED = "routed"  # optional_deps.importorskip(..., extra="template")
_SKIPS = "skips"  # any other importorskip, which CI's declaration cannot reach
_PLAIN = "plain"  # an import statement, importlib.import_module or __import__
_UNRESOLVED = "unresolved"  # an import call whose callee the scan cannot name

# The import functions a callee can resolve to, by qualified name.
_CALLEE_KINDS = {
    "importlib.import_module": _PLAIN,
    "__import__": _PLAIN,
    "builtins.__import__": _PLAIN,
    "pytest.importorskip": _SKIPS,
}
_ROUTED_CALLEE = "optional_deps.importorskip"
# The parameter each import function takes the module name in, by keyword.
_MODULE_KEYWORDS = {"module", "modname", "name"}
_COPIER_MODULE = re.compile(r"copier(\.[A-Za-z_]\w*)*")
# A name bound to something the scan cannot name: a parameter, a loop target,
# a call's result, or two different bindings in one scope.
_UNKNOWN = "<unknown>"
_DEF = "<def>"  # a function or class this module defines
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
_SCOPE_NODES = (*_FUNCTIONS, ast.ClassDef, ast.Lambda, ast.Module)


def _is_copier(name):
    return _COPIER_MODULE.fullmatch(name) is not None


class _Scope:
    """The names one module, class, function or lambda body binds."""

    def __init__(self, node, parent):
        self.node = node
        self.parent = parent
        self.names = {}

    def bind(self, name, value):
        self.names.setdefault(name, []).append(value)


def _outer_parts(node):
    """The parts of a def, class or lambda that run where it is written."""
    parts = list(getattr(node, "decorator_list", []))
    if isinstance(node, ast.ClassDef):
        return parts + node.bases + [kw.value for kw in node.keywords]
    defaults = node.args.defaults + [d for d in node.args.kw_defaults if d]
    return parts + defaults


def _direct_bindings(node):
    """The (name, value) pairs *node* binds itself, and the nodes under it
    that may bind more."""
    if isinstance(node, ast.Import):
        heads = [(a, a.name.split(".")[0]) for a in node.names]
        return [(a.asname or h, a.name if a.asname else h) for a, h in heads], []
    if isinstance(node, ast.ImportFrom):
        prefix = "." * node.level + (node.module or "")
        return [
            (a.asname or a.name, "%s.%s" % (prefix, a.name)) for a in node.names
        ], []
    if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names = [(t.id, node.value) for t in targets if isinstance(t, ast.Name)]
        rest = [t for t in targets if not isinstance(t, ast.Name)]
        return names, [*rest, node.value]
    if isinstance(node, (ast.Global, ast.Nonlocal)):
        return [(name, _UNKNOWN) for name in node.names], []
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
        return [(node.id, _UNKNOWN)], []
    # An except handler or a match capture binds its name to what was raised
    # or matched, which the scan cannot name.
    name = getattr(node, "name", None)
    bound = [(name, _UNKNOWN)] if isinstance(name, str) else []
    return bound, list(ast.iter_child_nodes(node))


def _scopes(tree):
    """Each scope node in *tree* mapped to the _Scope of the names it binds."""
    scopes = {}

    def build(node, parent):
        scope = scopes[node] = _Scope(node, parent)
        if not isinstance(node, (ast.Module, ast.ClassDef)):
            args = node.args
            for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs]:
                scope.bind(arg.arg, _UNKNOWN)
            for arg in (args.vararg, args.kwarg):
                if arg is not None:
                    scope.bind(arg.arg, _UNKNOWN)
        pending = list(node.body) if isinstance(node.body, list) else [node.body]
        while pending:
            child = pending.pop()
            if isinstance(child, _SCOPE_NODES):
                if not isinstance(child, ast.Lambda):
                    scope.bind(child.name, _DEF)
                pending.extend(_outer_parts(child))
                build(child, scope)
                continue
            names, rest = _direct_bindings(child)
            for name, value in names:
                scope.bind(name, value)
            pending.extend(rest)

    build(tree, None)
    return scopes


def _resolve(name, scope, seen):
    """What *name* refers to where *scope* reads it, as _qualified returns."""
    current = scope
    while current is not None:
        # A class body's names are not visible inside the methods it defines.
        visible = current is scope or not isinstance(current.node, ast.ClassDef)
        if visible and name in current.names:
            values = set()
            for value in current.names[name]:
                if isinstance(value, ast.expr):
                    value = (
                        _UNKNOWN
                        if id(value) in seen
                        else _qualified(value, current, seen | {id(value)})
                    )
                values.add(value)
            return values.pop() if len(values) == 1 else _UNKNOWN
        current = current.parent
    return "__import__" if name == "__import__" else None


def _qualified(expr, scope, seen=frozenset()):
    """The dotted name *expr* refers to; _UNKNOWN when it is bound to something
    the scan cannot name, None when nothing in the module binds it."""
    if isinstance(expr, ast.Name):
        return _resolve(expr.id, scope, seen)
    if isinstance(expr, ast.Attribute):
        base = _qualified(expr.value, scope, seen)
        if base is None:
            return None
        return _UNKNOWN if base in (_UNKNOWN, _DEF) else "%s.%s" % (base, expr.attr)
    return _UNKNOWN


def _argument(call, position, keywords):
    """The string constant *call* passes at *position* or by one of *keywords*."""
    values = [kw.value for kw in call.keywords if kw.arg in keywords]
    if len(call.args) > position:
        values.append(call.args[position])
    if len(values) == 1 and isinstance(values[0], ast.Constant):
        value = values[0].value
        return value if isinstance(value, str) else None
    return None


def _is_routed_callee(callee):
    return callee == _ROUTED_CALLEE or callee.endswith("." + _ROUTED_CALLEE)


def _load_kind(node, scope):
    """How *node* loads copier or a copier submodule, or None when it does not."""
    if isinstance(node, ast.Import):
        return _PLAIN if any(_is_copier(a.name) for a in node.names) else None
    if isinstance(node, ast.ImportFrom):
        return _PLAIN if node.level == 0 and _is_copier(node.module or "") else None
    if not isinstance(node, ast.Call):
        return None
    # A module name computed at run time cannot be read here, so such a call is
    # not judged; the named-modules backstop in the contract test still holds
    # the two gate modules.
    module = _argument(node, 0, _MODULE_KEYWORDS)
    if module is None or not _is_copier(module):
        return None
    callee = _qualified(node.func, scope)
    if callee in _CALLEE_KINDS:
        return _CALLEE_KINDS[callee]
    if callee not in (None, _UNKNOWN, _DEF) and _is_routed_callee(callee):
        extra = _argument(node, 1, {"extra"})
        return _ROUTED if extra == "template" else _SKIPS
    # A bare name bound to something unnamed, such as an alias assigned from a
    # call or a parameter, may be an import function, so it fails closed; so
    # does any callee spelled like one that resolves to nothing known.
    if callee == _UNKNOWN and isinstance(node.func, ast.Name):
        return _UNRESOLVED
    spelled = getattr(node.func, "attr", getattr(node.func, "id", None))
    return _UNRESOLVED if spelled in _IMPORT_CALLS else None


def _routes(stmt, scope):
    """Whether *stmt* is itself a routed copier load, run whenever it is reached."""
    value = getattr(stmt, "value", None)
    plain_statement = isinstance(stmt, (ast.Expr, ast.Assign, ast.AnnAssign))
    return (
        plain_statement
        and isinstance(value, ast.Call)
        and _load_kind(value, scope) == _ROUTED
    )


def _copier_loads(text):
    """Each copier load in *text* as (line, kind, ok), in source order.

    A routed load is ok. A plain load is ok when a routed load runs before it
    on every path that reaches it. Any other load is not ok.
    """
    # A module that only names copier in a string, such as the render scan in
    # test_copier_ship_set.py, loads nothing, so it has no loads to judge.
    tree = ast.parse(text)
    scopes = _scopes(tree)
    loads = set()

    def body(stmts, scope, sink, relying, *, guarded):
        # A function runs when it is called, which for a test is after the
        # module has finished importing, so a function defined here starts
        # guarded when this body is guarded by its end.
        end = guarded or any(_routes(s, scope) for s in stmts)
        block(stmts, guarded, scope, end, relying, sink)

    def relies(fn, relying):
        # Whether *fn* reaches a plain load, itself or through a function it
        # calls, when it is called before any guard has run.
        dry = set()
        body(fn.body, scopes[fn], dry, relying, guarded=False)
        return any(kind == _PLAIN and not ok for _, _, kind, ok in dry)

    def block(stmts, guarded, scope, deferred, relying, sink):
        # A routed load guards the statements after it in its block. One under
        # an if, a try or a loop guards only that inner block, because it may
        # not run.
        defs = [s for s in stmts if isinstance(s, _FUNCTIONS)]
        while True:  # each pass reaches one more link of a helper chain
            more = relying | {s.name for s in defs if relies(s, relying)}
            if more == relying:
                break
            relying = more
        now = guarded
        for stmt in stmts:
            if isinstance(stmt, (*_FUNCTIONS, ast.ClassDef)):
                for part in _outer_parts(stmt):
                    visit(part, now, scope, deferred, relying, sink)
            if isinstance(stmt, _FUNCTIONS):
                body(stmt.body, scopes[stmt], sink, relying, guarded=deferred)
            elif isinstance(stmt, ast.ClassDef):
                inner = scopes[stmt]
                ends = now or any(_routes(s, inner) for s in stmt.body)
                block(stmt.body, now, inner, deferred or ends, relying, sink)
            else:
                visit(stmt, now, scope, deferred, relying, sink)
            now = now or _routes(stmt, scope)

    def visit(node, guarded, scope, deferred, relying, sink):
        # A lambda is judged where it is written, not where it is called.
        scope = scopes.get(node, scope) if isinstance(node, ast.Lambda) else scope
        kind = _load_kind(node, scope)
        if kind is not None:
            ok = kind == _ROUTED or (kind == _PLAIN and guarded)
            sink.add((node.lineno, node.col_offset, kind, ok))
        # A call made before the guard, here or in a decorator or a default
        # that runs where its def stands, to a function that reaches a plain
        # load runs that load unguarded, so the call is the fault.
        called = getattr(getattr(node, "func", None), "id", None)
        if isinstance(node, ast.Call) and called in relying and not guarded:
            sink.add((node.lineno, node.col_offset, _PLAIN, False))
        for _, child in ast.iter_fields(node):
            if isinstance(child, list) and child and isinstance(child[0], ast.stmt):
                block(child, guarded, scope, deferred, relying, sink)
            elif isinstance(child, list):
                for item in child:
                    if isinstance(item, ast.AST):
                        visit(item, guarded, scope, deferred, relying, sink)
            elif isinstance(child, ast.AST):
                visit(child, guarded, scope, deferred, relying, sink)

    body(tree.body, scopes[tree], loads, frozenset(), guarded=False)
    return [(line, kind, ok) for line, _, kind, ok in sorted(loads)]


_ROUTE = 'optional_deps.importorskip("copier", extra="template")'

_LOAD_CASES = {
    "import": ("import copier\n", [(_PLAIN, False)]),
    "import_submodule_alias": ("import copier.vcs as v\n", [(_PLAIN, False)]),
    "from_import": ("from copier import run_copy\n", [(_PLAIN, False)]),
    "import_module": (
        'import importlib\nm = importlib.import_module("copier")\n',
        [(_PLAIN, False)],
    ),
    "dunder_import": ('__import__("copier")\n', [(_PLAIN, False)]),
    "routed": ("import optional_deps\ncopier = %s\n" % _ROUTE, [(_ROUTED, True)]),
    "routed_submodule": (
        "import optional_deps\n"
        't = optional_deps.importorskip("copier._tools", extra="template")\n',
        [(_ROUTED, True)],
    ),
    "routed_positional_extra": (
        'import optional_deps\noptional_deps.importorskip("copier", "template")\n',
        [(_ROUTED, True)],
    ),
    "routed_keywords": (
        "import optional_deps\n"
        'optional_deps.importorskip(module="copier", extra="template")\n',
        [(_ROUTED, True)],
    ),
    "routed_alias": (
        "import optional_deps as deps\n"
        'deps.importorskip("copier", extra="template")\nimport copier\n',
        [(_ROUTED, True), (_PLAIN, True)],
    ),
    "routed_from_import": (
        "from optional_deps import importorskip\n"
        'importorskip("copier", extra="template")\n',
        [(_ROUTED, True)],
    ),
    "other_extra": (
        'import optional_deps\noptional_deps.importorskip("copier", extra="docs")\n',
        [(_SKIPS, False)],
    ),
    "pytest_skip": (
        'import pytest\ncopier = pytest.importorskip("copier")\n',
        [(_SKIPS, False)],
    ),
    "aliased_pytest_skip": (
        'from pytest import importorskip as skip\nskip("copier")\n',
        [(_SKIPS, False)],
    ),
    "assigned_alias": (
        'import pytest\nload = pytest.importorskip\nload("copier")\n',
        [(_SKIPS, False)],
    ),
    "alias_rebound_in_another_scope": (
        'from pytest import importorskip as load\nload("copier")\n'
        "def test_other():\n    from json import loads as load\n",
        [(_SKIPS, False)],
    ),
    "alias_bound_two_ways": (
        "from optional_deps import importorskip as load\nimport pytest\n"
        'load = pytest.importorskip\nload("copier", extra="template")\n',
        [(_UNRESOLVED, False)],
    ),
    "parameter_callee": (
        'def test_x(load):\n    load("copier")\n',
        [(_UNRESOLVED, False)],
    ),
    "aliased_import_module": (
        'from importlib import import_module as load\nload("copier")\n',
        [(_PLAIN, False)],
    ),
    "keyword_import": (
        'import importlib\nimportlib.import_module(name="copier")\n',
        [(_PLAIN, False)],
    ),
    "unrelated_method": ('registry.import_module("copier")\n', [(_UNRESOLVED, False)]),
    "guard_then_import": (
        "import optional_deps\n%s\nimport copier\n" % _ROUTE,
        [(_ROUTED, True), (_PLAIN, True)],
    ),
    "import_before_guard": (
        "import optional_deps\nimport copier\n%s\n" % _ROUTE,
        [(_PLAIN, False), (_ROUTED, True)],
    ),
    "conditional_guard": (
        "import optional_deps\nif False:\n    %s\nimport copier\n" % _ROUTE,
        [(_ROUTED, True), (_PLAIN, False)],
    ),
    "deferred_guard": (
        "import optional_deps\ndef _g():\n    %s\nimport copier\n" % _ROUTE,
        [(_ROUTED, True), (_PLAIN, False)],
    ),
    "guard_in_test_function": (
        "import optional_deps\n"
        "def test_x():\n    %s\n    from copier import run_copy\n" % _ROUTE,
        [(_ROUTED, True), (_PLAIN, True)],
    ),
    "module_guard_reaches_function": (
        "import optional_deps\n%s\ndef f():\n    import copier\n" % _ROUTE,
        [(_ROUTED, True), (_PLAIN, True)],
    ),
    "module_guard_after_test": (
        "import optional_deps\ndef test_copy():\n    import copier\n%s\n" % _ROUTE,
        [(_PLAIN, True), (_ROUTED, True)],
    ),
    "method_before_module_guard": (
        "import optional_deps\n"
        "class TestX:\n    def test_a(self):\n        import copier\n%s\n" % _ROUTE,
        [(_PLAIN, True), (_ROUTED, True)],
    ),
    "function_called_before_guard": (
        "import optional_deps\ndef load():\n    import copier\nload()\n%s\n" % _ROUTE,
        [(_PLAIN, True), (_PLAIN, False), (_ROUTED, True)],
    ),
    "nested_function_called_before_guard": (
        "import optional_deps\ndef test_x():\n"
        "    def load():\n        import copier\n    load()\n    %s\n" % _ROUTE,
        [(_PLAIN, True), (_PLAIN, False), (_ROUTED, True)],
    ),
    "helper_in_decorator_before_guard": (
        "import optional_deps\nimport pytest\ndef cases():\n"
        "    from copier import run_copy\n    return [run_copy]\n"
        '@pytest.mark.parametrize("copy", cases())\n'
        "def test_copy(copy):\n    pass\n%s\n" % _ROUTE,
        [(_PLAIN, True), (_PLAIN, False), (_ROUTED, True)],
    ),
    "helper_in_default_before_guard": (
        "import optional_deps\ndef load():\n    import copier\n"
        "def test_copy(copier=load()):\n    pass\n%s\n" % _ROUTE,
        [(_PLAIN, True), (_PLAIN, False), (_ROUTED, True)],
    ),
    "helper_chain_called_before_guard": (
        "import optional_deps\ndef load():\n    import copier\n"
        "def build():\n    return load()\nbuild()\n%s\n" % _ROUTE,
        [(_PLAIN, True), (_PLAIN, False), (_ROUTED, True)],
    ),
    "helper_called_from_conditional_test": (
        "import optional_deps\ndef helper():\n    import copier\n"
        "if True:\n    def test_copy():\n        helper()\n%s\n" % _ROUTE,
        [(_PLAIN, True), (_ROUTED, True)],
    ),
    "no_guard_anywhere": (
        "def test_copy():\n    import copier\n",
        [(_PLAIN, False)],
    ),
    "string_only": ('names = {"copier"}\n', []),
    "string_call_argument": (
        'raise ValueError("copier.yml: top level is not a mapping")\n',
        [],
    ),
    "relative_import": ("from .copier import x\n", []),
    "other_package": ("import copierish\n", []),
}


@pytest.mark.parametrize(
    ("text", "loads"), list(_LOAD_CASES.values()), ids=list(_LOAD_CASES)
)
def test_each_copier_load_is_classified_by_how_it_reaches_copier(text, loads):
    assert [(kind, ok) for _, kind, ok in _copier_loads(text)] == loads


def test_copier_test_modules_hard_fail_when_the_surface_is_required():
    """Both halves of the guard live in the test modules themselves: whatever guards
    the `copier` import must route through `optional_deps`, or CI's declaration
    reaches a module that ignores it and the skip comes back.

    (The general "no module may silently skip a dependency CI installs" scan is in
    test_gate_scope.py, which ships downstream; this pins the two modules whose skip
    would specifically decommission the template's own gates.)"""
    guarded = []
    for path in sorted((_ROOT / "tests").rglob("test_*.py")):
        # Skip THIS file. Its detector cases load copier in strings it parses,
        # and its own scan must not count itself as a guarded module: that made
        # `guarded` permanently non-empty and the backstop below unfireable.
        # Deleting every real copier test module left this test green
        # (measured: `1 passed`).
        if path.resolve() == Path(__file__).resolve():
            continue
        loads = _copier_loads(path.read_text())
        if not loads:
            continue
        guarded.append(path.name)
        faults = [(line, kind) for line, kind, ok in loads if not ok]
        assert not faults, (
            "%s loads copier where CI's required-surface declaration cannot reach "
            'it: each load must be optional_deps.importorskip(..., extra="template") '
            "or follow one that runs before it in its own block or an enclosing "
            "one, and nothing may skip copier another way. (line, kind): %s"
            % (path.name, faults)
        )
    # Named explicitly, not just "something was found": a rename or a rewrite that
    # drops the guard must be a failure, not a quietly smaller set.
    missing = {"test_copier_generation.py", "test_copier_update.py"} - set(guarded)
    assert not missing, (
        "these copier test modules no longer guard copier through optional_deps, so "
        "they can silently skip in CI again: %s (found: %s)"
        % (sorted(missing), guarded)
    )


# copier's `multiselect:` question type landed in 9.1.0. `_min_copier_version` exists
# to convert "your copier is too old" into copier's own clear message; declaring a
# floor BELOW the oldest release that can actually render this template turns the
# gate into a lie — 9.0.1 passes it and then dies with the exact mystery error the
# gate advertises preventing (`ValueError: Could not convert [] to string`).
_FEATURE_FLOORS = [
    ("9.1.0", "multiselect:", "multiselect questions"),
    # The `command:`/`when:` migration form landed in copier 9.3.0 ("add simpler
    # migrations configuration syntax", #1510). Measured in 9.2.0's source rather
    # than assumed: `migration_tasks` does `parse(migration["version"])` with no
    # guard, so an entry that carries `command:` instead of `version:` is a raw
    # KeyError mid-update — the unhandled-traceback shape this floor converts into
    # copier's own clear message. 9.3.0 branches on the format instead.
    ("9.3.0", "_stage ==", "new-format _migrations (command:/when:)"),
    # `_tasks` and the `{{ _copier_python }}` they run under are older than the
    # 9.3.0 floor; the row pins them to it so a floor lowered past them fails here.
    ("9.3.0", "_copier_python", "_tasks run under copier's own interpreter"),
]


def _yaml_keys_and_values(text):
    """copier.yml with every comment line dropped: what copier reads, not what
    the comments say about it."""
    return "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))


def test_copier_yml_uses_no_variable_newer_than_its_floor():
    """`_copier_operation` would have said "copy" or "update" to a task directly,
    but it is newer than the declared floor, so a copier the floor admits would
    render it empty and the task would run in the wrong mode. The writer needs
    no mode at all: it derives what to stamp from git (what git would commit),
    which is the same answer on copy and on update."""
    used = _yaml_keys_and_values((_ROOT / "copier.yml").read_text())
    assert "_copier_operation" not in used


def test_the_restamp_runs_one_way_wherever_copier_runs_it():
    """copier runs the copy task in every render an update makes (two scratch
    copies and the real project) and the last migration once more. A mode flag
    on one invocation and not the others made their stamp lines disagree: one
    `.rej` per governed document under `--conflict rej`, and 105 of 113
    documents stale when generating into a repository with history (both
    measured). So every invocation of the writer carries the same arguments,
    except the migration's `--finish-with` pair: it changes only the command a
    refusal names, never a byte the writer writes, and a copy has no update to
    finish (tests/integration/test_copier_job_conflict_refusal.py)."""
    used = _yaml_keys_and_values((_ROOT / "copier.yml").read_text())
    calls = [ln.strip() for ln in used.splitlines() if "restamp_docs.py" in ln]
    assert len(calls) >= 2, "the copy task and the update migration both restamp"
    finish = ', "--finish-with", "{{ _copier_python }}"'
    argv = {re.sub(r"^(- )?(command: )?", "", c).replace(finish, "") for c in calls}
    assert len(argv) == 1, "restamp invocations differ: %s" % sorted(argv)


def _migrations(used):
    """[(command, when)] of copier.yml's `_migrations`, in order, read as text
    (this module imports nothing optional, so no yaml)."""
    lines = used.splitlines()
    start = lines.index("_migrations:")
    entries = []
    for ln in lines[start + 1 :]:
        if ln and not ln.startswith(" "):
            break
        stripped = ln.strip()
        if stripped.startswith("- command:"):
            entries.append([stripped[len("- command:") :].strip(), None])
        elif stripped.startswith("when:") and entries:
            entries[-1][1] = stripped[len("when:") :].strip()
    return [tuple(e) for e in entries]


def test_the_stamp_resolver_runs_after_the_merge_and_just_before_the_restamp():
    """copier writes conflict markers in `_apply_update`, after every `_tasks`
    run, so only an `after` migration sees them. The resolver must precede the
    restamp migration: the restamp rewrites the project side of a conflicted
    document's stamp (an identical-sides conflict no reader resolves, measured
    on a 7f0a68b project) and, on a project whose check_structure.py conflicts,
    crashes before anything after it runs. The restamp stays last."""
    entries = _migrations(_yaml_keys_and_values((_ROOT / "copier.yml").read_text()))
    assert len(entries) >= 2
    assert "restamp_docs.py" in entries[-1][0], entries[-1]
    command, when = entries[-2]
    assert "scripts/jobs/resolve_stamp_conflicts.py" in command, entries[-2]
    assert when == "\"{{ _stage == 'after' }}\"", when
    assert sum("resolve_stamp_conflicts.py" in c for c, _ in entries) == 1


def test_declared_copier_floor_covers_every_feature_the_template_uses():
    """`_min_copier_version` must be >= the newest copier feature copier.yml relies
    on. A floor that admits a copier which then crashes is worse than no floor: the
    user is told the version was checked."""
    text = (_ROOT / "copier.yml").read_text()
    declared = None
    for line in text.splitlines():
        if line.startswith("_min_copier_version:"):
            declared = line.split(":", 1)[1].strip().strip("\"'")
    assert declared, "copier.yml declares no _min_copier_version"
    as_tuple = tuple(int(p) for p in declared.split("."))

    for floor, marker, why in _FEATURE_FLOORS:
        if marker not in text:
            continue
        need = tuple(int(p) for p in floor.split("."))
        assert as_tuple >= need, (
            "copier.yml uses %s (needs copier >= %s) but declares "
            "_min_copier_version: %r — that version passes the gate and then fails "
            "to render" % (why, floor, declared)
        )


# --- trust: every copier command a user is told to run carries it ---------------

_COPIER_CMD = re.compile(r"\bcopier\s+(copy|update)\b")


def _fenced_lines(text):
    """The lines inside ``` fences: what a reader copies and runs."""
    inside, out = False, []
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            inside = not inside
            continue
        if inside:
            out.append(line)
    return out


def _documented_copier_commands():
    """(where, line) for every copier invocation keel tells someone to run: the
    fenced blocks of every tracked Markdown file and Markdown template twin, the
    expanded `make new` recipe, and the showcase's setup steps."""
    found = []
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.md", "*.md.jinja"],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
    )
    assert listed.returncode == 0, listed.stderr
    for rel in sorted(p for p in listed.stdout.split("\0") if p):
        path = _ROOT / rel
        if path.is_symlink() or not path.is_file():
            continue
        found.extend(
            (rel, line.strip())
            for line in _fenced_lines(path.read_text(encoding="utf-8"))
            if _COPIER_CMD.search(line)
        )
    if shutil.which("make") is not None:
        found.append(("make -n new", _recipe_line(_make_n_new(), "copier copy")))
    import backend.showcase as showcase  # keel-only: this module skips downstream

    found.extend(
        ("backend.showcase.SETUP_STEPS", step.command)
        for step in showcase.SETUP_STEPS
        if step.command and _COPIER_CMD.search(step.command)
    )
    return found


def test_every_documented_copier_command_carries_trust():
    """`_tasks` (the doc restamp) and `_migrations` (answer retirement) make keel
    an unsafe template, so copier REFUSES both `copy` and `update` without
    `--trust` (docs/adr/keel/K-0010-generation-needs-trust-to-stamp-docs.md). A command
    shown without the flag is a command that fails for the reader who copies it."""
    found = _documented_copier_commands()
    assert len(found) >= 3, (
        "found almost no copier commands -- is the scan broken? %r" % found
    )
    missing = [
        "%s: %s" % (where, line) for where, line in found if "--trust" not in line
    ]
    assert not missing, "copier commands without --trust:\n  " + "\n  ".join(missing)
