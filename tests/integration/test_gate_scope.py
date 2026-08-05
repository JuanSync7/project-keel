"""
title: Integration — the gate's scope is the whole corpus, not a hand-written subset
kind: tests
layer: n/a
summary: Pass 3's contract, read off the REAL Makefile recipes, the REAL pyproject and the REAL .pre-commit-config.yaml. (1) `lint-py` and `fmt` must cover every entry of `CODE_ROOTS` — imported from scripts/check_structure.py, never re-typed here, so the three scope lists cannot drift. (2) mypy's scope must ACCOUNT for every code root: each is either inside `[tool.mypy] files` or a declared, reasoned entry in config/practices.json rulesets.mypy.ratchet — a root may not simply be unmentioned. (3) ruff must actually be clean over that scope. (4) The FE gates must SKIP, not hard-fail, when npm is absent (`command -v npm || exit 0` exits only its own recipe sub-shell). (5) Every bare-`python3` pre-commit entry must be legal under the documented old interpreter, since pre-commit `language: system` hooks exec the ambient python3. Imports nothing optional: this pin must never itself skip.
"""
import ast
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.integration

# The interpreter floor a `language: system` pre-commit hook must survive. Stated in
# docs/guides/deterministic-checks.md:46 ("the host's pre-commit `python3` may be
# **old** — this repo's is 3.6") and re-derived in the header comments of
# scripts/agent_surface/generate_aad_schema.py and api/rest_fastapi/export_openapi.py.
# It is deliberately NOT `requires-python`, which governs the distribution built from
# src/. Single constant here rather than a 13th restatement; the durable home is a
# key in config/project.json (see the pass-3 report) — that file is machine-checked
# and owned elsewhere.
PRECOMMIT_PYTHON_FLOOR = (3, 6)

# PEP 585 generics: illegal in an EVALUATED annotation below 3.9.
_PEP585_BUILTINS = frozenset(["list", "dict", "tuple", "set", "frozenset", "type"])


def _make_n(target, *overrides):
    """One `make -n <target>` expansion — what make WOULD run, without running it."""
    argv = ["make", "-n", target] + list(overrides)
    r = subprocess.run(argv, cwd=str(_ROOT), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def _tool_paths(stdout, needle):
    """Path arguments of the expanded recipe line containing `needle`.

    Reads the REAL recipe the way test_copier_generator_contract.py does, so the
    assertion tracks the Makefile rather than a copy of it.
    """
    hits = [ln for ln in stdout.splitlines() if needle in ln]
    assert len(hits) == 1, "expected exactly one %r line in:\n%s" % (needle, stdout)
    argv = shlex.split(hits[0])
    i = argv.index(needle.split()[-1])
    return [a for a in argv[i + 1:] if not a.startswith("-")]


# --- scope: ruff ------------------------------------------------------------


@pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
def test_lint_py_covers_every_code_root():
    """`make verify` is what tells an agent a change is done. If `lint-py` lints a
    hand-written subset, the gate is green over code it never read. CODE_ROOTS is the
    repo's ONE declared list of Python roots (check_structure.py already walks it for
    the structural checks), so the lint scope must be that list — imported, not
    re-typed, or this test becomes a second list that can drift too."""
    scope = set(_tool_paths(_make_n("lint-py"), "ruff check"))
    missing = [r for r in cs.CODE_ROOTS if r not in scope]
    assert not missing, (
        "`make lint-py` does not lint %s — those roots are outside the gate while "
        "`make verify` still reports green (scope=%s)" % (missing, sorted(scope)))


@pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
def test_fmt_covers_every_code_root():
    """A formatter narrower than the linter means `make fmt` cannot fix what
    `make lint-py` reports. Same source of truth."""
    scope = set(_tool_paths(_make_n("fmt"), "ruff format"))
    missing = [r for r in cs.CODE_ROOTS if r not in scope]
    assert not missing, (
        "`make fmt` does not format %s (scope=%s)" % (missing, sorted(scope)))


def test_ruff_is_clean_over_every_code_root():
    """The scope widening only pays if the corpus is actually clean under it. Runs the
    real linter over the real roots rather than trusting the recipe."""
    r = subprocess.run(
        [sys.executable, "-m", "ruff", "check"] + list(cs.CODE_ROOTS),
        cwd=str(_ROOT), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


# --- scope: mypy ------------------------------------------------------------


def _practices():
    with open(str(_ROOT / "config" / "practices.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _mypy_files():
    """`[tool.mypy] files` read off the real pyproject with check_structure's own
    TOML scanner — the same reader check_M trusts, so the two agree by construction."""
    with open(str(_ROOT / "pyproject.toml"), encoding="utf-8") as fh:
        text = fh.read()
    entries = cs._toml_targets(text).get("tool.mypy.files", [])
    assert entries, "pyproject.toml has no [tool.mypy] files"
    rhs = " ".join(r for (_, r, _) in entries)
    return set(re.findall(r'"([^"]+)"', rhs))


def test_mypy_scope_accounts_for_every_code_root():
    """mypy's blind spot is the expensive half of pass 3: `files = ["src"]` left 8 of
    the 9 code roots untyped-checked. Full strict over all of them is 1272 errors, so
    the honest contract is not "everything is checked" but "nothing is UNMENTIONED":
    every code root is either in mypy's `files` or a declared ratchet entry in
    config/practices.json. A new root added to CODE_ROOTS fails this until someone
    decides, in data, which side it is on."""
    mypy = _practices()["rulesets"]["mypy"]
    checked = _mypy_files()
    pending = {k for k in mypy.get("ratchet", {}) if not k.startswith("_")}

    assert not (checked & pending), (
        "%s is both type-checked and declared pending" % sorted(checked & pending))
    unaccounted = [r for r in cs.CODE_ROOTS if r not in checked and r not in pending]
    assert not unaccounted, (
        "code roots outside mypy's scope AND undeclared in "
        "config/practices.json rulesets.mypy.ratchet: %s" % unaccounted)
    strays = sorted((checked | pending) - set(cs.CODE_ROOTS))
    assert not strays, "mypy scope/ratchet names non-code-roots: %s" % strays


def test_declared_mypy_scope_matches_pyproject():
    """Same shape as check_M's ruff parity: config/practices.json declares the policy,
    pyproject enforces it, and they may not drift. Without this the declared scope
    could stay wide while `files` quietly narrowed."""
    declared = set(_practices()["rulesets"]["mypy"]["scope"])
    assert _mypy_files() == declared, (
        "pyproject [tool.mypy] files=%s but config/practices.json declares "
        "rulesets.mypy.scope=%s" % (sorted(_mypy_files()), sorted(declared)))


def test_every_mypy_ratchet_entry_states_its_cost_and_its_exit():
    """A ratchet rung that records neither its size nor what removes it is just an
    exclusion with better manners. Each pending root must carry a measured error
    count and the condition that deletes the entry."""
    ratchet = _practices()["rulesets"]["mypy"].get("ratchet", {})
    for root, entry in sorted(ratchet.items()):
        if root.startswith("_"):
            continue
        assert isinstance(entry, dict), "%s: ratchet entry must be an object" % root
        assert isinstance(entry.get("errors"), int) and entry["errors"] >= 1, (
            "%s: needs a measured `errors` count >= 1 (a root at zero belongs in "
            "mypy `files`, not the ratchet)" % root)
        assert entry.get("removed_when", "").strip(), (
            "%s: needs `removed_when` — what makes this rung deletable" % root)


@pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
def test_typecheck_py_takes_its_scope_from_the_config():
    """`mypy src` on the command line OVERRIDES `[tool.mypy] files`, so widening the
    config would have been silently inert. The recipe must pass no paths."""
    paths = _tool_paths(_make_n("typecheck-py"), "-m mypy")
    assert paths == [], (
        "`make typecheck-py` passes mypy explicit paths %s, which override "
        "[tool.mypy] files and re-narrow the gate" % paths)


# --- the FE gates skip, not fail, without npm -------------------------------


def _fe_app(tmp_path):
    """A minimal FE app the Makefile's FE_APPS shape can point at."""
    app = tmp_path / "fe" / "webapp"
    (app / "node_modules").mkdir(parents=True)
    (app / "package.json").write_text(json.dumps(
        {"name": "probe", "private": True,
         "scripts": {"lint": "true", "typecheck": "true"}}))
    return str(app) + "/"


def _run_make(target, fe_apps, path_env):
    make = shutil.which("make")
    env = {"PATH": path_env, "HOME": os.environ.get("HOME", "/tmp")}
    return subprocess.run([make, target, "FE_APPS=%s" % fe_apps],
                          cwd=str(_ROOT), capture_output=True, text=True, env=env)


@pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
@pytest.mark.parametrize("target", ["lint-fe", "typecheck-fe"])
def test_fe_gate_skips_when_npm_is_absent(tmp_path, target):
    """`command -v npm >/dev/null || { echo skipping; exit 0; }` is its OWN shell: the
    `exit 0` ends that line, and make runs the loop on the next line anyway, which
    then dies on `npm: command not found`. So the guard prints "skipping" and fails
    two lines later. The Makefile ships VERBATIM downstream, so every generated
    project's `make lint` breaks on any host without node.

    PATH is an EMPTY directory, not a curated one: make invokes /bin/sh by absolute
    path and the recipe uses only shell builtins, so this is hermetic rather than
    "this host happens to lack npm"."""
    emptybin = tmp_path / "emptybin"
    emptybin.mkdir()
    r = _run_make(target, _fe_app(tmp_path), str(emptybin))
    assert r.returncode == 0, (
        "`make %s` hard-failed with npm absent instead of skipping:\n%s"
        % (target, r.stdout + r.stderr))
    assert "npm not found" in r.stdout


@pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
@pytest.mark.parametrize("target", ["lint-fe", "typecheck-fe"])
def test_fe_gate_is_silent_on_a_repo_with_no_frontend(tmp_path, target):
    """copier.yml prunes src/frontend entirely for `frontend_stack: none`, so
    FE_APPS-empty is a real downstream shape. It must exit 0 AND say nothing about
    npm — a backend-only project has no frontend to skip."""
    emptybin = tmp_path / "emptybin"
    emptybin.mkdir()
    r = _run_make(target, "", str(emptybin))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "npm not found" not in r.stdout, (
        "a repo with no frontend is told npm is missing:\n%s" % r.stdout)


@pytest.mark.skipif(shutil.which("make") is None or shutil.which("npm") is None,
                    reason="needs make and npm")
@pytest.mark.parametrize("target,script", [("lint-fe", "lint"), ("typecheck-fe", "typecheck")])
def test_fe_gate_still_fails_on_a_real_frontend_failure(tmp_path, target, script):
    """The non-regression half: making the guard skip must not make the gate toothless.
    With npm present and the app's script exiting non-zero, the target must fail."""
    app = Path(_fe_app(tmp_path))
    pkg = json.loads((app / "package.json").read_text())
    pkg["scripts"][script] = "false"
    (app / "package.json").write_text(json.dumps(pkg))
    npm_dir = str(Path(shutil.which("npm")).parent)
    r = _run_make(target, str(app) + "/", npm_dir + ":/usr/bin:/bin")
    assert r.returncode != 0, (
        "`make %s` passed despite the app's %s script failing:\n%s"
        % (target, script, r.stdout + r.stderr))


# --- pre-commit entry points parse under the documented interpreter ---------


def _precommit_python3_entries():
    """Every `entry: python3 <script>` in .pre-commit-config.yaml, derived from the
    file. Stdlib line-scanning on purpose: pyyaml is only a transitive `template`
    extra, so a yaml import would make this test SKIP in the dependency-free
    configuration it most needs to run in."""
    text = (_ROOT / ".pre-commit-config.yaml").read_text()
    # `(\S+)` then STOP: several entries carry arguments (`... --check`), so
    # anchoring the match to end-of-line would silently find only the argument-less
    # one and hand the callers a vacuous green.
    return re.findall(r"^\s*entry:\s*python3\s+(\S+)", text, re.MULTILINE)


def _too_new_syntax(path):
    """Constructs in `path` that a `python3` at PRECOMMIT_PYTHON_FLOOR cannot run.

    Note `ast.parse(..., feature_version=(3, 6))` accepts BOTH hazards below, so it
    is a false green; these are explicit walks. Annotations are checked because
    forbidding `from __future__ import annotations` means every annotation is
    EVALUATED at def time — deleting the future import alone leaves
    `list[str] | None` raising TypeError instead of SyntaxError.
    """
    tree = ast.parse(path.read_text(), str(path))
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "__future__" \
                and any(a.name == "annotations" for a in node.names):
            bad.append("%s:%d: `from __future__ import annotations` (3.7+)"
                       % (path.name, node.lineno))
        if isinstance(node, ast.NamedExpr):
            bad.append("%s:%d: walrus operator (3.8+)" % (path.name, node.lineno))

    annotations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.arg) and node.annotation is not None:
            annotations.append(node.annotation)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns:
            annotations.append(node.returns)
        elif isinstance(node, ast.AnnAssign):
            annotations.append(node.annotation)
    for ann in annotations:
        for node in ast.walk(ann):
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) \
                    and node.value.id in _PEP585_BUILTINS:
                bad.append("%s:%d: evaluated `%s[...]` annotation (PEP 585, 3.9+)"
                           % (path.name, node.lineno, node.value.id))
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
                bad.append("%s:%d: evaluated `X | Y` annotation (PEP 604, 3.10+)"
                           % (path.name, node.lineno))
    return bad


def test_precommit_python3_entries_are_discoverable():
    """A discovery bug that finds nothing would make the next test vacuously green —
    the same never-actually-ran failure mode pass 2 had to fix once."""
    entries = _precommit_python3_entries()
    assert len(entries) >= 4, entries
    for e in entries:
        assert (_ROOT / e).is_file(), "%s: pre-commit entry does not exist" % e


def test_precommit_python3_entries_run_on_the_documented_old_interpreter():
    """pre-commit's `language: system` hooks build no environment — they exec `entry`
    under the committing shell's ambient PATH, so `python3` is whatever that host has
    (3.6.8 from a plain shell here; 3.11 only inside the venv). A hook that cannot be
    PARSED there does not degrade, it aborts the commit — and the heavy-dependency
    hooks' whole graceful-skip design depends on the file parsing first.

    Derived from the config, so a new `python3` hook is gated automatically."""
    offenders = []
    for entry in _precommit_python3_entries():
        offenders += _too_new_syntax(_ROOT / entry)
    assert not offenders, (
        "pre-commit `python3` entry points must be legal at Python %d.%d "
        "(docs/guides/deterministic-checks.md): \n  %s"
        % (PRECOMMIT_PYTHON_FLOOR + (("\n  ").join(offenders),)))


def test_precommit_python3_entries_actually_execute_on_an_old_interpreter():
    """The belt to the previous test's braces: if a genuinely old python3 is
    discoverable on this box, compile every entry with it for real. Opportunistic —
    it no-ops on a modern-only host, which is exactly why it may never be the only
    assertion."""
    old = None
    for cand in ("/usr/bin/python3", "/usr/bin/python3.6"):
        if not os.path.exists(cand):
            continue
        r = subprocess.run([cand, "-c", "import sys; print('%d %d' % sys.version_info[:2])"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            continue
        ver = tuple(int(x) for x in r.stdout.split())
        if PRECOMMIT_PYTHON_FLOOR <= ver < (3, 10):
            old = cand
            break
    if old is None:
        pytest.skip("no interpreter between the pre-commit floor and requires-python")

    for entry in _precommit_python3_entries():
        r = subprocess.run(
            [old, "-c", "import sys; compile(open(sys.argv[1]).read(), sys.argv[1], 'exec')",
             entry],
            cwd=str(_ROOT), capture_output=True, text=True)
        assert r.returncode == 0, "%s does not parse under %s:\n%s" % (entry, old, r.stderr)


# --- scope: a dependency CI installs must never degrade into a silent skip ----
#
# The same shape as every scope pin above, applied to the test suite's own
# preconditions. `pytest.importorskip` turns a broken install into a green run
# with the assertions never executed — invisible, because a skip in a 300-test
# run reads as "that optional thing again". Measured instance: `jsonschema` was
# in no extra, so the AAD schema-validation assertion had never run anywhere.

sys.path.insert(0, str(_ROOT / "tests"))

import optional_deps  # noqa: E402

_RAW_SKIP = "pytest.importorskip("


def _test_modules():
    return sorted(p for p in (_ROOT / "tests").rglob("test_*.py"))


def test_no_test_module_silently_skips_a_dependency_ci_installs():
    """Every guarded import goes through `optional_deps`, or is declared opt-in.

    A raw `pytest.importorskip` is only honest for a surface nobody promised to
    install. For anything CI installs on purpose it is a hole: the module skips,
    the run stays green, and the gate the import guards never executes.
    """
    offenders = []
    for path in _test_modules():
        # This module names the searched-for literal as its own filter string, so
        # without the self-exclusion it would always match itself and the scan
        # would never be able to find a real offender. (Exactly the trap that made
        # an earlier meta-test unfireable — see test_copier_generator_contract.py.)
        if path.resolve() == Path(__file__).resolve():
            continue
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if _RAW_SKIP not in line or line.lstrip().startswith("#"):
                continue
            if any(name in line for name in optional_deps.DELIBERATELY_OPTIONAL):
                continue
            offenders.append("%s:%d: %s" % (path.relative_to(_ROOT), i, line.strip()))
    assert not offenders, (
        "these guarded imports skip silently instead of failing when CI declares "
        "the surface required, so the assertions behind them can stop running "
        "without anything going red:\n" + "\n".join(offenders)
        + "\n\nRoute them through tests/optional_deps.importorskip(module, extra=...), "
          "or add the dependency to optional_deps.DELIBERATELY_OPTIONAL with a reason.")


def test_the_silent_skip_scan_actually_reaches_the_suite():
    """Backstop for the pin above: a scan that collects nothing passes vacuously.

    Both halves must be non-empty — real modules walked, and at least one real
    guarded import found — or a rename could quietly empty the scan.
    """
    modules = [p for p in _test_modules() if p.resolve() != Path(__file__).resolve()]
    assert len(modules) > 10, "the test-module scan found almost nothing: %s" % modules
    guarded = [p.name for p in modules
               if "optional_deps.importorskip(" in p.read_text()
               or _RAW_SKIP in p.read_text()]
    assert guarded, "no module guards an optional import — has the pattern moved?"


def test_every_required_surface_is_installed_by_a_ci_step():
    """A surface CI declares required but never installs would fail every run;
    one it installs but never declares is the silent skip again. Read off the real
    workflow, so the two cannot drift."""
    ci = (_ROOT / ".github" / "workflows" / "ci.yml")
    if not ci.is_file():
        pytest.skip("no CI workflow in this project")
    text = ci.read_text()
    declared = [ln for ln in text.splitlines() if optional_deps.ENV_VAR in ln]
    assert declared, (
        "no CI step declares %s, so every optional surface degrades to a skip and "
        "the suite can go green with whole gates unexecuted" % optional_deps.ENV_VAR)
    names = re.findall(r"[\w-]+", declared[0].split(":", 1)[1])
    assert names, "%s is declared empty in CI" % optional_deps.ENV_VAR
    for name in names:
        assert name in optional_deps.SURFACES, (
            "CI declares unknown surface %r (known: %s) — a typo here silently "
            "disables the guard" % (name, sorted(optional_deps.SURFACES)))
        assert optional_deps.SURFACES[name] in text, (
            "CI declares surface %r required but no step runs %r, so every run "
            "would fail on a missing import"
            % (name, optional_deps.SURFACES[name]))
