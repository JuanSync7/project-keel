"""
title: Integration — the gate's scope is the whole corpus, not a hand-written subset
kind: tests
layer: n/a
summary: Pass 3's contract, read off the REAL Makefile recipes, the REAL pyproject and the REAL .pre-commit-config.yaml. (1) `lint-py` and `fmt` must cover every entry of `CODE_ROOTS` — imported from scripts/check_structure.py, never re-typed here, so the three scope lists cannot drift. (2) mypy's scope must ACCOUNT for every code root: each is either inside `[tool.mypy] files` or a declared, reasoned entry in config/practices.json rulesets.mypy.ratchet — a root may not simply be unmentioned. (3) ruff must actually be clean over that scope. (4) The static FE gates (lint-fe, typecheck-fe) SKIP when npm is absent; the frontend suites and `fe-browsers` exit 2 naming the target, the app and `make fe-install` when npm is absent or any app lacks node_modules, checked for every app before any suite runs, and every FE target is silent and green on a repo with no frontend app; CI installs the packages and the journey's browser before it runs `make test-fe`, and no CI step carries on past a failure. (5) Every bare-`python3` pre-commit entry must be legal under the documented old interpreter, since pre-commit `language: system` hooks exec the ambient python3. (6) The tools whose output IS the gate's verdict — ruff, mypy — must be pinned exactly in the `dev` extra, and pre-commit must run the SAME ruff, or the same tree gets different verdicts in different places. (7) Every frontend app the Makefile's FE_APPS glob finds wires a unit runner and a browser journey that `make verify` reaches and `make test` does not: each npm script the test-fe and fe-browsers recipes run is defined, the unit config refuses zero tests and a focused test and never collects the journeys, the journey config refuses a focused test, both suites hold at least one file, the journey config reads every config/project.json `layers.frontend.journey` key and spells no port, and the browser runner is pinned to one exact version every app and lockfile agree on. Imports nothing optional: this pin must never itself skip.
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

import makefile_copy

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402
import child_env  # noqa: E402

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
    return [a for a in argv[i + 1 :] if not a.startswith("-")]


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
        "`make verify` still reports green (scope=%s)" % (missing, sorted(scope))
    )


@pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
def test_fmt_covers_every_code_root():
    """A formatter narrower than the linter means `make fmt` cannot fix what
    `make lint-py` reports. Same source of truth."""
    scope = set(_tool_paths(_make_n("fmt"), "ruff format"))
    missing = [r for r in cs.CODE_ROOTS if r not in scope]
    assert not missing, "`make fmt` does not format %s (scope=%s)" % (
        missing,
        sorted(scope),
    )


def test_ruff_is_clean_over_every_code_root():
    """The scope widening only pays if the corpus is actually clean under it. Runs the
    real linter over the real roots rather than trusting the recipe."""
    r = subprocess.run(
        [sys.executable, "-m", "ruff", "check"] + list(cs.CODE_ROOTS),
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
def test_lint_gates_formatting_over_every_code_root():
    """`make fmt` REWRITES; nothing ever proved it had been run. A formatter that only
    exists as a fix-it command is decorative — the tree drifts and the gate stays green
    (measured: 109 files were unformatted while `make verify` passed). So `lint` must
    carry the read-only half over the SAME roots, imported from check_structure rather
    than re-typed, or this becomes a fourth scope list that can drift on its own."""
    scope = set(_tool_paths(_make_n("lint"), "ruff format"))
    missing = [r for r in cs.CODE_ROOTS if r not in scope]
    assert not missing, "`make lint` does not check formatting for %s (scope=%s)" % (
        missing,
        sorted(scope),
    )


def test_the_corpus_is_actually_formatted():
    """Wiring the check proves the recipe; this proves the CORPUS. Same split as
    test_ruff_is_clean_over_every_code_root — pass 3's lesson was that a ruleset can be
    provably SELECTED and never provably APPLIED."""
    r = subprocess.run(
        [sys.executable, "-m", "ruff", "format", "--check"] + list(cs.CODE_ROOTS),
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
    )
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
        "%s is both type-checked and declared pending" % sorted(checked & pending)
    )
    unaccounted = [r for r in cs.CODE_ROOTS if r not in checked and r not in pending]
    assert not unaccounted, (
        "code roots outside mypy's scope AND undeclared in "
        "config/practices.json rulesets.mypy.ratchet: %s" % unaccounted
    )
    strays = sorted((checked | pending) - set(cs.CODE_ROOTS))
    assert not strays, "mypy scope/ratchet names non-code-roots: %s" % strays


def test_declared_mypy_scope_matches_pyproject():
    """Same shape as check_M's ruff parity: config/practices.json declares the policy,
    pyproject enforces it, and they may not drift. Without this the declared scope
    could stay wide while `files` quietly narrowed."""
    declared = set(_practices()["rulesets"]["mypy"]["scope"])
    assert _mypy_files() == declared, (
        "pyproject [tool.mypy] files=%s but config/practices.json declares "
        "rulesets.mypy.scope=%s" % (sorted(_mypy_files()), sorted(declared))
    )


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
            "mypy `files`, not the ratchet)" % root
        )
        assert entry.get("removed_when", "").strip(), (
            "%s: needs `removed_when` — what makes this rung deletable" % root
        )


@pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
def test_typecheck_py_takes_its_scope_from_the_config():
    """`mypy src` on the command line OVERRIDES `[tool.mypy] files`, so widening the
    config would have been silently inert. The recipe must pass no paths."""
    paths = _tool_paths(_make_n("typecheck-py"), "-m mypy")
    assert paths == [], (
        "`make typecheck-py` passes mypy explicit paths %s, which override "
        "[tool.mypy] files and re-narrow the gate" % paths
    )


# --- the FE gates: lint skips without npm, a suite refuses -------------------


# Every per-app frontend gate and the npm script it runs in each app.
_FE_GATE_SCRIPTS = [
    ("lint-fe", "lint"),
    ("typecheck-fe", "typecheck"),
    ("test-fe-unit", "test:unit"),
    ("test-fe-e2e", "test:e2e"),
    ("fe-browsers", "test:e2e:browsers"),
]
_FE_GATES = [target for target, _script in _FE_GATE_SCRIPTS]
# The static gates still skip without npm or node_modules; the suites, and the
# browser download that feeds one, refuse instead, because a suite that ran
# nothing is not a pass.
_FE_SKIPPING = ["lint-fe", "typecheck-fe"]
_FE_REFUSING = ["test-fe-unit", "test-fe-e2e", "fe-browsers"]
_FE_INSTALL = "make fe-install"


def _fe_app(tmp_path, name="webapp", node_modules=True):
    """A minimal FE app the Makefile's FE_APPS shape can point at."""
    app = tmp_path / "fe" / name
    app.mkdir(parents=True)
    if node_modules:
        (app / "node_modules").mkdir()
    (app / "package.json").write_text(
        json.dumps(
            {
                "name": "probe",
                "private": True,
                "scripts": {script: "true" for _target, script in _FE_GATE_SCRIPTS},
            }
        )
    )
    return str(app) + "/"


def _run_make(target, fe_apps, path_env):
    make = shutil.which("make")
    env = {"PATH": path_env, "HOME": os.environ.get("HOME", "/tmp")}
    return subprocess.run(
        [make, target, "FE_APPS=%s" % fe_apps],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
@pytest.mark.parametrize("target", _FE_SKIPPING)
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
        % (target, r.stdout + r.stderr)
    )
    assert "npm not found" in r.stdout


@pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
@pytest.mark.parametrize("target", _FE_REFUSING)
def test_fe_suite_refuses_when_npm_is_absent(tmp_path, target):
    """A frontend suite that could not run tested nothing, so it exits 2, the
    refusal code run-web uses, naming itself, the app and the fix. PATH is an
    empty directory, as above."""
    emptybin = tmp_path / "emptybin"
    emptybin.mkdir()
    app = _fe_app(tmp_path)
    r = _run_make(target, app, str(emptybin))
    assert r.returncode == 2 and "Error 2" in r.stderr, r.stdout + r.stderr
    assert target + ": npm is not on PATH" in r.stderr, r.stderr
    assert app in r.stderr and _FE_INSTALL in r.stderr, r.stderr


def _recording_npm(tmp_path):
    """A directory holding an `npm` that records each call and exits 0."""
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    log = tmp_path / "npm-calls.log"
    npm = bindir / "npm"
    npm.write_text('#!/bin/sh\necho "$*" >> %s\nexit 0\n' % shlex.quote(str(log)))
    npm.chmod(0o755)
    return bindir, log


@pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
@pytest.mark.parametrize("target", _FE_REFUSING)
def test_fe_suite_refuses_an_app_without_node_modules(tmp_path, target):
    """Every app is checked before any suite runs, so one installed app ahead of
    an uninstalled one runs nothing: the refusal names the uninstalled app and
    npm is never called."""
    bindir, log = _recording_npm(tmp_path)
    ready = _fe_app(tmp_path, "ready")
    bare = _fe_app(tmp_path, "bare", node_modules=False)
    r = _run_make(target, ready + " " + bare, str(bindir) + ":/usr/bin:/bin")
    assert r.returncode == 2 and "Error 2" in r.stderr, r.stdout + r.stderr
    assert target + ": " + bare + " has no node_modules" in r.stderr, r.stderr
    assert _FE_INSTALL in r.stderr, r.stderr
    assert not log.exists(), "npm ran before the refusal: %s" % log.read_text()


@pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
@pytest.mark.parametrize("target", _FE_REFUSING)
def test_fe_suite_runs_every_installed_app(tmp_path, target):
    """The control for the two refusals: with npm present and every app
    installed, each app's script runs once and the target passes."""
    bindir, log = _recording_npm(tmp_path)
    apps = [_fe_app(tmp_path, "one"), _fe_app(tmp_path, "two")]
    r = _run_make(target, " ".join(apps), str(bindir) + ":/usr/bin:/bin")
    assert r.returncode == 0, r.stdout + r.stderr
    script = dict(_FE_GATE_SCRIPTS)[target]
    calls = log.read_text().splitlines()
    assert len(calls) == 2 and all(script in c for c in calls), calls


@pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
@pytest.mark.parametrize("target", _FE_GATES)
def test_fe_gate_is_silent_on_a_repo_with_no_frontend(tmp_path, target):
    """copier.yml prunes src/frontend entirely for `frontend_stack: none`, so
    FE_APPS-empty is a real downstream shape. It must exit 0 AND say nothing:
    a backend-only project has no frontend to skip or refuse."""
    emptybin = tmp_path / "emptybin"
    emptybin.mkdir()
    r = _run_make(target, "", str(emptybin))
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip() == "" and r.stderr.strip() == "", (
        "a repo with no frontend is told about npm:\n%s" % (r.stdout + r.stderr)
    )


@pytest.mark.skipif(
    shutil.which("make") is None or shutil.which("npm") is None,
    reason="needs make and npm",
)
@pytest.mark.parametrize("target,script", _FE_GATE_SCRIPTS)
@pytest.mark.parametrize("fault", ["fails", "missing"])
def test_fe_gate_still_fails_on_a_real_frontend_failure(
    tmp_path, target, script, fault
):
    """The non-regression half: making the guard skip must not make the gate toothless.
    With npm present and the app's script exiting non-zero, the target must fail; and
    an app that does not define the script at all fails too (npm's "Missing script"),
    so an app without the contract is red rather than skipped."""
    app = Path(_fe_app(tmp_path))
    npm_dir = str(Path(shutil.which("npm")).parent)
    # The control: the intact app passes, so the red below is the script's own
    # and not make refusing an unknown target.
    control = _run_make(target, str(app) + "/", npm_dir + ":/usr/bin:/bin")
    assert control.returncode == 0, control.stdout + control.stderr
    pkg = json.loads((app / "package.json").read_text())
    if fault == "fails":
        pkg["scripts"][script] = "false"
    else:
        del pkg["scripts"][script]
    (app / "package.json").write_text(json.dumps(pkg))
    r = _run_make(target, str(app) + "/", npm_dir + ":/usr/bin:/bin")
    assert r.returncode != 0, (
        "`make %s` passed despite the app's %s script failing:\n%s"
        % (target, script, r.stdout + r.stderr)
    )


# --- every frontend app wires a unit runner and a browser journey -----------

# The tools the shipped stacks chose for the two suites, by the files they read
# and the package whose version fixes the browser revision the shared cache must
# hold (docs/guides/dev-loops.md, "End-to-end coverage"). Everything else is read
# off its owner: the apps off the Makefile's FE_APPS glob, the npm scripts off
# the test-fe recipes, the journey keys off config/project.json.
_UNIT_CONFIG = "vitest.config.ts"
_JOURNEY_CONFIG = "playwright.config.ts"
_BROWSER_RUNNER = "@playwright/test"
_FE_SUITE_TARGETS = ("test-fe-unit", "test-fe-e2e")
_FE_SUITES = "test-fe"
# The target that downloads the browser the journey drives: outside `verify`,
# run once per host and by CI before the suites.
_FE_BROWSERS = "fe-browsers"
_EXACT_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
# The variable the browser runner reads for its browser cache's location: a
# fact of the runner, like _BROWSER_RUNNER, not of this project.
_BROWSER_CACHE_ENV = "PLAYWRIGHT_BROWSERS_PATH"
# A TCP port a config could spell instead of reading the key: the registered and
# dynamic ranges, where every loopback port keel uses sits.
_PORT_RANGE = range(1024, 65536)


def _merged_rules():
    """{target: (prereqs, recursions)} over keel's Makefile, a target's rules
    merged the way make merges them."""
    out = {}
    for rule in cs.make_target_rules((_ROOT / "Makefile").read_text("utf-8")):
        prereqs, recursions = out.setdefault(rule.target, ([], []))
        prereqs.extend(rule.prereqs)
        recursions.extend(rule.recursions)
    return out


def _reach(rules, name):
    """Every target *name* reaches through prerequisites and `$(MAKE)` goals."""
    seen, stack = set(), [name]
    while stack:
        prereqs, recursions = rules.get(stack.pop(), ([], []))
        for child in prereqs + recursions:
            if child not in seen:
                seen.add(child)
                stack.append(child)
    return seen


def _fe_app_dirs():
    """The app directories the Makefile's own FE_APPS glob finds in this tree."""
    text = (_ROOT / "Makefile").read_text("utf-8")
    m = re.search(
        r"^FE_APPS\s*:?=\s*\$\(dir \$\(wildcard ([^)\s]+)\)\)\s*$", text, re.MULTILINE
    )
    assert m, "the Makefile no longer discovers FE_APPS by a package.json glob"
    return sorted(p.parent for p in _ROOT.glob(m.group(1)))


def _suite_scripts():
    """{frontend suite or browser target: the npm script its recipe runs in each
    app}."""
    rules = {}
    for rule in cs.make_target_rules((_ROOT / "Makefile").read_text("utf-8")):
        rules.setdefault(rule.target, rule)
    out = {}
    for target in _FE_SUITE_TARGETS + (_FE_BROWSERS,):
        assert target in rules, "the Makefile has no `%s` target" % target
        scripts = set(
            re.findall(
                r"\bnpm run (?:-\S+ )*([\w:.-]+)", " ".join(rules[target].recipe)
            )
        )
        assert len(scripts) == 1, (target, sorted(scripts))
        (out[target],) = scripts
    return out


def _quoted(text):
    return re.findall(r"""['"]([^'"]+)['"]""", text)


def _option(source, key):
    """The value text of `key: <value>` in a config's source, or None."""
    m = re.search(r"\b%s\s*:\s*(\[[^\]]*\]|'[^']*'|\"[^\"]*\"|\w+)" % key, source)
    return m.group(1) if m else None


def _expand(pattern):
    """A glob with at most one `{a,b}` group, as the plain globs it stands for."""
    m = re.search(r"\{([^}]*)\}", pattern)
    if not m:
        return [pattern]
    return [
        pattern[: m.start()] + alt + pattern[m.end() :] for alt in m.group(1).split(",")
    ]


def _journey_keys():
    """The keys config/project.json declares under layers.frontend.journey, or
    None when the project has no frontend layer."""
    manifest = json.loads((_ROOT / "config" / "project.json").read_text("utf-8"))
    frontend = (manifest.get("layers") or {}).get("frontend")
    if frontend is None:
        return None
    journey = frontend.get("journey")
    assert isinstance(journey, dict) and journey, (
        "config/project.json layers.frontend has no `journey` block"
    )
    return sorted(k for k in journey if not k.startswith("_"))


def _locked_family(lock, name, pin, seen=None):
    """[(package, locked version)] for *name* and every dependency it pins to
    *pin*, transitively: the packages whose versions together fix the browser
    revision."""
    seen = set() if seen is None else seen
    if name in seen:
        return []
    seen.add(name)
    entry = (lock.get("packages") or {}).get("node_modules/" + name)
    if entry is None:
        return [(name, None)]
    out = [(name, entry.get("version"))]
    for dep, spec in sorted((entry.get("dependencies") or {}).items()):
        if spec == pin:
            out.extend(_locked_family(lock, dep, pin, seen))
    return out


def test_every_frontend_app_wires_both_suites():
    """CMP-4.S5: a frontend shipped with no test runner, so it had zero tests and
    the gate was green. Every app the gate discovers must define each npm script
    the gate runs; its unit runner must refuse zero tests and never collect the
    journeys; each suite must hold a file; its journey must take every
    `layers.frontend.journey` key from config/project.json and spell no port of
    its own; and the browser runner must be pinned exactly, to one version across
    apps and lockfiles, because that version fixes the browser revision the cache
    must hold and no browser is downloaded under the gate."""
    keys = _journey_keys()
    apps = _fe_app_dirs()
    if not apps:
        assert keys is None, (
            "config/project.json declares layers.frontend but the Makefile finds "
            "no frontend app: a pass over zero apps is not a pass"
        )
        pytest.skip("no frontend app and no layers.frontend: a backend-only project")
    assert keys, "frontend apps exist but config/project.json has no layers.frontend"
    scripts = _suite_scripts()
    problems, pins = [], {}
    for app in apps:
        rel = app.relative_to(_ROOT)
        pkg = json.loads((app / "package.json").read_text("utf-8"))
        defined = pkg.get("scripts") or {}
        for target, script in sorted(scripts.items()):
            if script not in defined:
                problems.append(
                    "%s: no npm script %r (`make %s`)" % (rel, script, target)
                )

        journey_cfg = app / _JOURNEY_CONFIG
        unit_cfg = app / _UNIT_CONFIG
        problems.extend(
            "%s: no %s" % (rel, cfg.name)
            for cfg in (unit_cfg, journey_cfg)
            if not cfg.is_file()
        )
        if not (unit_cfg.is_file() and journey_cfg.is_file()):
            continue
        journey_src = journey_cfg.read_text("utf-8")
        unit_src = unit_cfg.read_text("utf-8")

        test_dir = _option(journey_src, "testDir")
        test_match = _option(journey_src, "testMatch")
        if not test_dir or not test_match:
            problems.append(
                "%s: %s sets no testDir/testMatch" % (rel, journey_cfg.name)
            )
            continue
        (test_dir,), (test_match,) = _quoted(test_dir), _quoted(test_match)

        if (_option(unit_src, "passWithNoTests") or "") != "false":
            problems.append(
                "%s: %s does not set passWithNoTests: false" % (rel, unit_cfg.name)
            )
        # A focused test (`.only`) skips the rest of the suite and still exits 0;
        # the unit runner allows one whenever CI is unset, which is how verify
        # runs on a workstation. The journey side is forbidOnly, pinned below.
        if (_option(unit_src, "allowOnly") or "") != "false":
            problems.append(
                "%s: %s does not set allowOnly: false" % (rel, unit_cfg.name)
            )
        if (_option(journey_src, "forbidOnly") or "") != "true":
            problems.append(
                "%s: %s does not set forbidOnly: true" % (rel, journey_cfg.name)
            )
        include = _quoted(_option(unit_src, "include") or "")
        if not include:
            problems.append(
                "%s: %s has no explicit include list" % (rel, unit_cfg.name)
            )
        for pattern in include:
            top = pattern.split("/", 1)[0]
            if top == test_dir or any(c in top for c in "*?[{"):
                problems.append(
                    "%s: unit include %r can collect the journeys under %s/"
                    % (rel, pattern, test_dir)
                )
        units = [p for pat in include for g in _expand(pat) for p in app.glob(g)]
        journeys = list((app / test_dir).rglob(test_match))
        if not units:
            problems.append("%s: the unit runner's include matches no file" % rel)
        if not journeys:
            problems.append(
                "%s: no journey matches %s/%s" % (rel, test_dir, test_match)
            )

        ports = sorted(
            {
                int(n)
                for n in re.findall(r"\b\d+\b", journey_src)
                if int(n) in _PORT_RANGE
            }
        )
        if ports:
            problems.append(
                "%s: %s spells port-like literals %s" % (rel, journey_cfg.name, ports)
            )
        if "journey" not in journey_src:
            problems.append(
                "%s: %s never reads layers.frontend.journey" % (rel, journey_cfg.name)
            )
        # Read as a property (`journey.port`), not merely named: the loader's
        # own validation names every key, so a key it checks and then never
        # uses would otherwise pass.
        problems.extend(
            "%s: %s never reads layers.frontend.journey.%s"
            % (rel, journey_cfg.name, key)
            for key in keys
            if not re.search(r"\.%s\b" % re.escape(key), journey_src)
        )

        pin = (pkg.get("devDependencies") or {}).get(_BROWSER_RUNNER)
        if pin is None or not _EXACT_VERSION.match(pin):
            problems.append(
                "%s: %s is %r, not one exact version" % (rel, _BROWSER_RUNNER, pin)
            )
            continue
        pins[str(rel)] = pin
        lock = app / "package-lock.json"
        if lock.is_file():
            for name, version in _locked_family(
                json.loads(lock.read_text("utf-8")), _BROWSER_RUNNER, pin
            ):
                if version != pin:
                    problems.append(
                        "%s: package-lock.json resolves %s to %r, not %s"
                        % (rel, name, version, pin)
                    )
    if len(set(pins.values())) > 1:
        problems.append(
            "the apps pin different %s versions: %s" % (_BROWSER_RUNNER, pins)
        )
    assert problems == [], "\n".join(problems)


def test_verify_reaches_the_frontend_suites():
    """`make verify` must run both frontend suites, and `make test` must not:
    JUNIT_XML is pytest's report, the evidence record's only source of counts,
    and CI runs `make test-fe` as a step of its own after `make fe-browsers`."""
    rules = _merged_rules()
    for target in _FE_SUITE_TARGETS + (_FE_SUITES,):
        assert target in rules, "the Makefile has no `%s` target" % target
    verify = _reach(rules, "verify")
    missing = sorted(set(_FE_SUITE_TARGETS) - verify)
    assert missing == [], "`make verify` never reaches %s" % missing
    leaked = sorted(set(_FE_SUITE_TARGETS + (_FE_SUITES,)) & _reach(rules, "test"))
    assert leaked == [], "`make test` reaches %s; it must stay pytest's alone" % leaked


def _ci_run_lines():
    """[(step index, run command, continue-on-error value or None)] for every
    step of the CI workflow, in order. Stdlib line-scanning, for the reason
    _precommit_python3_entries gives: a yaml import would make this skip."""
    ci = _ROOT / ".github" / "workflows" / "ci.yml"
    if not ci.is_file():
        return None
    steps = []
    for line in ci.read_text("utf-8").splitlines():
        body = line.strip()
        if body.startswith("- "):
            steps.append({"run": None, "continue": None})
            body = body[2:].strip()
        if not steps:
            continue
        key, sep, value = body.partition(":")
        if not sep:
            continue
        value = value.split("#", 1)[0].strip()
        if key == "run":
            steps[-1]["run"] = value
        elif key == "continue-on-error":
            steps[-1]["continue"] = value
    return [(i, st["run"], st["continue"]) for i, st in enumerate(steps) if st["run"]]


def _ci_step_of(runs, target):
    hits = [i for i, run, _c in runs if run.split()[:2] == ["make", target]]
    assert hits, "no CI step runs `make %s`" % target
    return hits[0]


def test_ci_runs_the_frontend_suites_after_installing_them():
    """CI ran `make test`, which never reaches the frontend suites, so a frontend
    that broke its own tests stayed green there. The suites run as a step after
    the packages and the journey's browser are installed, and no step may carry
    on past a failure of either."""
    runs = _ci_run_lines()
    if runs is None:
        pytest.skip("no CI workflow in this project")
    install = _ci_step_of(runs, "fe-install")
    browsers = _ci_step_of(runs, _FE_BROWSERS)
    suites = _ci_step_of(runs, _FE_SUITES)
    assert install < browsers < suites, (install, browsers, suites)
    soft = [run for i, run, cont in runs if cont not in (None, "false")]
    assert soft == [], "CI steps that carry on past a failure: %s" % soft


def test_the_browser_cache_location_reaches_every_verify_goal(monkeypatch):
    """`make verify` starts each goal with the child allowlist
    (scripts/gate_evidence.py), while a direct `make test-fe` inherits the
    caller's environment. A browser cache located by the runner's own variable
    must reach both, or the journey passes alone and goes red under verify."""
    if _journey_keys() is None:
        pytest.skip("no layers.frontend: no browser journey to locate a cache for")
    monkeypatch.setenv(_BROWSER_CACHE_ENV, "/browser-cache-probe")
    env = child_env.build_child_env(root=str(_ROOT))
    assert env.get(_BROWSER_CACHE_ENV) == "/browser-cache-probe", (
        "config/project.json child_env.names drops %s, so the browser journey "
        "under `make verify` sees only the runner's default cache" % _BROWSER_CACHE_ENV
    )


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
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "__future__"
            and any(a.name == "annotations" for a in node.names)
        ):
            bad.append(
                "%s:%d: `from __future__ import annotations` (3.7+)"
                % (path.name, node.lineno)
            )
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
            if (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Name)
                and node.value.id in _PEP585_BUILTINS
            ):
                bad.append(
                    "%s:%d: evaluated `%s[...]` annotation (PEP 585, 3.9+)"
                    % (path.name, node.lineno, node.value.id)
                )
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
                bad.append(
                    "%s:%d: evaluated `X | Y` annotation (PEP 604, 3.10+)"
                    % (path.name, node.lineno)
                )
    return bad


def _local_imports(path):
    """Keel modules `path` imports by bare name from scripts/ — the `import
    child_env` a script reaches through scripts/ on sys.path. An entry in scripts/
    resolves against its own directory and scripts/; one elsewhere (api/) reaches
    no scripts/ module by bare name. An entry that parses at 3.6 but imports one
    that does not still aborts the commit, so that module is part of its surface."""
    scripts = _ROOT / "scripts"
    dirs = [scripts]
    if scripts in path.parents and path.parent != scripts:
        dirs.insert(0, path.parent)
    if scripts not in path.parents:
        return []
    tree = ast.parse(path.read_text(), str(path))
    found = []
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        for name in names:
            if "." in name:
                continue
            for d in dirs:
                sibling = d / (name + ".py")
                if sibling.is_file() and sibling != path:
                    found.append(sibling)
                    break
    return sorted(set(found))


def _precommit_python3_surface():
    """Every pre-commit `python3` entry plus each sibling module it imports."""
    out = []
    for entry in _precommit_python3_entries():
        path = _ROOT / entry
        out.append(path)
        out += _local_imports(path)
    return sorted(set(out))


def test_precommit_python3_entries_are_discoverable():
    """A discovery bug that finds nothing would make the next test vacuously green —
    the same never-actually-ran failure mode pass 2 had to fix once."""
    entries = _precommit_python3_entries()
    assert len(entries) >= 4, entries
    for e in entries:
        assert (_ROOT / e).is_file(), "%s: pre-commit entry does not exist" % e


def test_the_old_interpreter_surface_reaches_sibling_imports():
    """check_structure.py imports child_env from its own directory, so the 3.6
    guard must read child_env.py too, or a 3.7+ construct there aborts a commit
    while this suite stays green."""
    surface = [p.relative_to(_ROOT).as_posix() for p in _precommit_python3_surface()]
    assert "scripts/child_env.py" in surface, surface


def test_precommit_python3_entries_run_on_the_documented_old_interpreter():
    """pre-commit's `language: system` hooks build no environment — they exec `entry`
    under the committing shell's ambient PATH, so `python3` is whatever that host has
    (3.6.8 from a plain shell here; 3.11 only inside the venv). A hook that cannot be
    PARSED there does not degrade, it aborts the commit — and the heavy-dependency
    hooks' whole graceful-skip design depends on the file parsing first.

    Derived from the config, so a new `python3` hook is gated automatically."""
    offenders = []
    for path in _precommit_python3_surface():
        offenders += _too_new_syntax(path)
    assert not offenders, (
        "pre-commit `python3` entry points must be legal at Python %d.%d "
        "(docs/guides/deterministic-checks.md): \n  %s"
        % (PRECOMMIT_PYTHON_FLOOR + (("\n  ").join(offenders),))
    )


def test_precommit_python3_entries_actually_execute_on_an_old_interpreter():
    """The belt to the previous test's braces: if a genuinely old python3 is
    discoverable on this box, compile every entry with it for real. Opportunistic —
    it no-ops on a modern-only host, which is exactly why it may never be the only
    assertion."""
    old = None
    for cand in ("/usr/bin/python3", "/usr/bin/python3.6"):
        if not os.path.exists(cand):
            continue
        r = subprocess.run(
            [cand, "-c", "import sys; print('%d %d' % sys.version_info[:2])"],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            continue
        ver = tuple(int(x) for x in r.stdout.split())
        if PRECOMMIT_PYTHON_FLOOR <= ver < (3, 10):
            old = cand
            break
    if old is None:
        pytest.skip("no interpreter between the pre-commit floor and requires-python")

    for path in _precommit_python3_surface():
        entry = path.relative_to(_ROOT).as_posix()
        r = subprocess.run(
            [
                old,
                "-c",
                "import sys; compile(open(sys.argv[1]).read(), sys.argv[1], 'exec')",
                entry,
            ],
            cwd=str(_ROOT),
            capture_output=True,
            text=True,
        )
        assert r.returncode == 0, "%s does not parse under %s:\n%s" % (
            entry,
            old,
            r.stderr,
        )

    # Parsing is not running: the allowlist builder must also EXECUTE there, since
    # a gate hook calls it before every child it starts. -B keeps the old
    # interpreter from writing a 3.6 .pyc into scripts/__pycache__.
    r = subprocess.run(
        [
            old,
            "-B",
            "-c",
            "import sys; sys.path.insert(0, 'scripts'); import child_env; "
            "env = child_env.build_child_env(); "
            "assert 'PATH' in env and 'KEEL_PLANTED_SECRET' not in env, env; "
            "assert 'GIT_DIR' not in env, env; "
            "got = child_env.build_child_env(repo_context=True)['GIT_DIR']; "
            "assert got == '/nonexistent/.git', got",
        ],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        env=dict(os.environ, KEEL_PLANTED_SECRET="s", GIT_DIR="/nonexistent/.git"),
    )
    assert r.returncode == 0, "child_env does not run under %s:\n%s" % (old, r.stderr)


# --- the interpreter floor: a target that needs the project interpreter checks it first

# The Makefile target whose recipe is the floor check (scripts/check_python_version.py
# reads requires-python and names it). Every other fact below is read from the
# Makefile, .pre-commit-config.yaml and the scripts the recipes run.
_FLOOR_TARGET = "check-python"
_PY_CALL = re.compile(r"\$[({]PY[)}]")
_SHELL_SPLIT = re.compile(r"\|\||&&|;|\|")


def _precommit_python3_commands():
    """Each `entry: python3 <script> [args]` in .pre-commit-config.yaml, whole:
    the commands a `language: system` hook already runs under the old python3."""
    text = (_ROOT / ".pre-commit-config.yaml").read_text()
    return [
        " ".join(m.split())
        for m in re.findall(r"^\s*entry:\s*(python3\s+\S.*?)\s*$", text, re.MULTILINE)
    ]


def _imported_names(path):
    """(top-level name, is relative) for every import anywhere in *path*."""
    tree = ast.parse(path.read_text(), str(path))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend((a.name.split(".")[0], False) for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            out.append(((node.module or "").split(".")[0], node.level > 0))
    return out


def _old_python_safe(path, seen=None):
    """True when *path* and every keel module it imports by bare name parse under
    PRECOMMIT_PYTHON_FLOOR and import nothing but the standard library and each
    other: a script the floor would only delay, never protect."""
    seen = set() if seen is None else seen
    if path in seen:
        return True
    seen.add(path)
    if not path.is_file() or _too_new_syntax(path):
        return False
    local = {p.stem: p for p in _local_imports(path)}
    for name, relative in _imported_names(path):
        if relative:
            return False
        if name in local:
            if not _old_python_safe(local[name], seen):
                return False
        elif name not in sys.stdlib_module_names and name != "__future__":
            return False
    return True


def _py_commands(rule):
    """(recipe line index, the `$(PY) ...` command) for each shell command of
    *rule*'s recipe that runs the selected interpreter."""
    out = []
    for i, line in enumerate(rule.recipe):
        for part in _SHELL_SPLIT.split(line):
            m = _PY_CALL.search(part)
            if m:
                out.append((i, "python3 " + " ".join(part[m.end() :].split())))
    return out


def _floor_exempt(command, precommit, floor_command):
    """Why *command* (spelled `python3 ...`) runs safely without the floor, or None."""
    words = command.split()
    if command == floor_command:
        return "is the floor check"
    if len(words) > 2 and words[1] == "-m":
        if words[2] in sys.stdlib_module_names:
            return "runs a standard-library module"
        return None
    if command in precommit:
        return "is a pre-commit `python3` entry, held to the old interpreter"
    if len(words) > 1 and _old_python_safe(_ROOT / words[1]):
        return "parses on the old interpreter and imports only the stdlib and keel"
    return None


def _floor_report():
    """({target: [needy command]}, {target: reason it is floor-free}) for every
    target of keel's Makefile, and the targets missing the floor."""
    rules = {}
    for rule in cs.make_target_rules((_ROOT / "Makefile").read_text()):
        rules.setdefault(rule.target, rule)
    floor = rules[_FLOOR_TARGET]
    (floor_command,) = [c for _i, c in _py_commands(floor)]
    precommit = set(_precommit_python3_commands())

    def closure(name):
        seen, stack = set(), [name]
        while stack:
            for child in rules[stack.pop()].prereqs:
                if child in rules and child not in seen:
                    seen.add(child)
                    stack.append(child)
        return seen

    needy, safe, missing = {}, {}, []
    for name in sorted(rules):
        rule = rules[name]
        commands = _py_commands(rule)
        need = [
            (i, c)
            for i, c in commands
            if _floor_exempt(c, precommit, floor_command) is None
        ]
        if not commands:
            continue
        if not need:
            safe[name] = sorted(
                {_floor_exempt(c, precommit, floor_command) for _i, c in commands}
            )
            continue
        needy[name] = [c for _i, c in need]
        first = need[0][0]
        guarded_line = any(floor_command == c for i, c in commands if i < first)
        if _FLOOR_TARGET not in closure(name) and not guarded_line:
            missing.append(name)
    return needy, safe, missing


def test_every_target_that_needs_the_project_interpreter_checks_it_first():
    """`make audit-project` under the default PY (a host python3 3.6) died on a
    SyntaxError in scripts/audit_project.py instead of check-python's message
    naming requires-python (bedrock-platform, docs/design/downstream-feedback.md).
    A target that runs a module or script the old interpreter cannot run must
    reach the floor first: as a prerequisite, or as an earlier recipe line where a
    prerequisite would run before the recipe's own usage checks. Derived from the
    recipes: a command is floor-free only when it runs a standard-library module,
    is a pre-commit `python3` entry (held to the old interpreter by the tests
    above), or is a script that parses there and imports nothing outside the
    stdlib and keel's own 3.6-safe modules."""
    needy, safe, missing = _floor_report()
    assert missing == [], (
        "these targets run the project interpreter without `%s` first: %s\n%s"
        % (
            _FLOOR_TARGET,
            missing,
            "\n".join("  %s: %s" % (t, needy[t]) for t in missing),
        )
    )
    # Non-vacuity: the two cases that motivated the rule are seen as needy, and
    # the gate itself stays floor-free (it must run on the old interpreter).
    assert {"audit-project", "unit", "test"} <= set(needy), sorted(needy)
    assert {"check", "help", "check-docs", _FLOOR_TARGET} <= set(safe), sorted(safe)


def _old_python3():
    """A host python3 below requires-python, or None."""
    for cand in ("/usr/bin/python3", "/usr/bin/python3.6"):
        if not os.path.exists(cand):
            continue
        r = subprocess.run(
            [cand, "-c", "import sys; print('%d %d' % sys.version_info[:2])"],
            capture_output=True,
            text=True,
        )
        if r.returncode == 0 and tuple(int(x) for x in r.stdout.split()) < (3, 10):
            return cand
    return None


def test_needy_targets_fail_with_the_floor_message_on_an_old_python3(tmp_path):
    """The belt to the derivation above: on a host with an old python3, every
    needy target, run with PY pointed at it, stops on the floor's message -- never
    a traceback. In a scratch copy of the Makefile (with every makefile it
    includes), pyproject.toml and scripts/, so
    nothing a recipe would do can touch this checkout. A target whose every needy
    command runs a script this checkout lacks is a keel-only doer copier left
    out of a generated project: its stub answers before any interpreter runs,
    so it is held only to failing without a traceback. Opportunistic: a host with
    no old python3 skips, which is why it is never the only assertion."""
    old = _old_python3()
    if old is None:
        pytest.skip("no python3 below requires-python on this host")
    makefile_copy.copy_makefiles(tmp_path, _ROOT)
    shutil.copy(str(_ROOT / "pyproject.toml"), str(tmp_path / "pyproject.toml"))
    shutil.copytree(
        str(_ROOT / "scripts"),
        str(tmp_path / "scripts"),
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    needy, _safe, _missing = _floor_report()
    assert needy
    env = {k: v for k, v in os.environ.items() if k not in ("PY", "MAKEFLAGS")}
    held = []
    for target in sorted(needy):
        r = subprocess.run(
            ["make", "-s", target, "PY=" + old, "DEST=" + str(tmp_path / "nowhere")],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )
        out = r.stdout + r.stderr
        assert r.returncode != 0, (target, out)
        assert "Traceback" not in out and "SyntaxError" not in out, (target, out)
        scripts = [c.split()[1] for c in needy[target] if c.split()[1] != "-m"]
        stub = len(scripts) == len(needy[target]) and not any(
            (_ROOT / s).exists() for s in scripts
        )
        if not stub:
            assert "requires Python >=" in out, (target, out)
            held.append(target)
    # Non-vacuity: the stub exception never covers the targets that motivated
    # the floor, in keel or in a generated project.
    assert {"unit", "test"} <= set(held), sorted(held)


def test_py_defaults_to_the_project_venv_when_present(tmp_path):
    """A project with a .venv is run by it without anyone setting PY; without one,
    the default is python3; a caller's PY always wins."""
    makefile_copy.copy_makefiles(tmp_path, _ROOT)
    env = {k: v for k, v in os.environ.items() if k not in ("PY", "MAKEFLAGS")}

    def check_line(*overrides):
        r = subprocess.run(
            ["make", "-n", "-s", "check"] + list(overrides),
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            env=env,
        )
        assert r.returncode == 0, r.stdout + r.stderr
        return r.stdout.strip()

    assert check_line() == "python3 scripts/check_structure.py"
    venv_python = tmp_path / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("")
    assert check_line() == ".venv/bin/python scripts/check_structure.py"
    assert check_line("PY=python3.99") == "python3.99 scripts/check_structure.py"


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
        "without anything going red:\n"
        + "\n".join(offenders)
        + "\n\nRoute them through tests/optional_deps.importorskip(module, extra=...), "
        "or add the dependency to optional_deps.DELIBERATELY_OPTIONAL with a reason."
    )


def test_the_silent_skip_scan_actually_reaches_the_suite():
    """Backstop for the pin above: a scan that collects nothing passes vacuously.

    Both halves must be non-empty — real modules walked, and at least one real
    guarded import found — or a rename could quietly empty the scan.
    """
    modules = [p for p in _test_modules() if p.resolve() != Path(__file__).resolve()]
    assert len(modules) > 10, "the test-module scan found almost nothing: %s" % modules
    guarded = [
        p.name
        for p in modules
        if "optional_deps.importorskip(" in p.read_text() or _RAW_SKIP in p.read_text()
    ]
    assert guarded, "no module guards an optional import — has the pattern moved?"


def test_every_required_surface_is_installed_by_a_ci_step():
    """A surface CI declares required but never installs would fail every run;
    one it installs but never declares is the silent skip again. Read off the real
    workflow, so the two cannot drift."""
    ci = _ROOT / ".github" / "workflows" / "ci.yml"
    if not ci.is_file():
        pytest.skip("no CI workflow in this project")
    text = ci.read_text()
    declared = [ln for ln in text.splitlines() if optional_deps.ENV_VAR in ln]
    assert declared, (
        "no CI step declares %s, so every optional surface degrades to a skip and "
        "the suite can go green with whole gates unexecuted" % optional_deps.ENV_VAR
    )
    names = re.findall(r"[\w-]+", declared[0].split(":", 1)[1])
    assert names, "%s is declared empty in CI" % optional_deps.ENV_VAR
    for name in names:
        assert name in optional_deps.SURFACES, (
            "CI declares unknown surface %r (known: %s) — a typo here silently "
            "disables the guard" % (name, sorted(optional_deps.SURFACES))
        )
        assert optional_deps.SURFACES[name] in text, (
            "CI declares surface %r required but no step runs %r, so every run "
            "would fail on a missing import" % (name, optional_deps.SURFACES[name])
        )


# ---- scope: the toolchain itself ---------------------------------------------
# A linter is not a dependency like any other: its output IS the gate's verdict.
# Measured the hard way — `dev = [..., "ruff", "mypy", ...]` let CI resolve ruff
# 0.16.4 against the venv's 0.15.18, and because `extend-select` ADDS to ruff's
# defaults, 0.16's wider default set produced 464 findings from families this repo
# deliberately defers (UP031, E402, RUF100). Green locally, red in CI, with no code
# change between the two runs.
_GATE_TOOLS = ("ruff", "mypy")
_DEV_EXTRA = re.compile(r"^dev\s*=\s*\[(?P<items>[^\]]*)\]", re.MULTILINE)
_EXACT_PIN = re.compile(r'"(?P<name>[A-Za-z0-9_.-]+)==(?P<version>[0-9][^"]*)"')
# Bounded and non-greedy: `rev:` is the FIRST one after the repo line, but comment
# lines may sit between them, so this cannot demand the very next line.
_PRECOMMIT_RUFF = re.compile(
    r"ruff-pre-commit[\s\S]{0,400}?\n\s*rev:\s*v?(?P<rev>[0-9][^\s]*)"
)


def _dev_pins():
    """{name: version} for every EXACTLY pinned entry of the `dev` extra."""
    text = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = _DEV_EXTRA.search(text)
    assert m, "pyproject.toml has no `dev = [...]` extra — re-derive this check"
    return {
        p.group("name"): p.group("version")
        for p in _EXACT_PIN.finditer(m.group("items"))
    }


def test_the_tools_that_decide_the_gate_are_pinned_exactly():
    """`make lint` and `make typecheck` are what "done" means here, so their verdict
    must not depend on which day CI resolved them. A floating linter turns a green
    branch red on a release nobody in the repo chose — and worse, could turn a red
    one green. Bumping is fine; bumping DELIBERATELY, in a commit, is the point."""
    pins = _dev_pins()
    floating = [t for t in _GATE_TOOLS if t not in pins]
    assert not floating, (
        "these tools decide the gate's verdict but the `dev` extra does not pin them "
        "exactly: %s — pin with `==` and bump in its own commit" % floating
    )


def test_pre_commit_runs_the_same_ruff_as_the_gate():
    """A third ruff version is a third opinion. The hook ran v0.8.4 while the gate
    ran 0.15.18, and 0.8.4 REFORMATS two files 0.15.18 considers correct — so a
    developer with the hook installed and CI would have fought each other, each
    reporting the other's output as a defect."""
    pins = _dev_pins()
    assert "ruff" in pins, "pin ruff in the `dev` extra first"
    text = (_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    m = _PRECOMMIT_RUFF.search(text)
    assert m, ".pre-commit-config.yaml no longer pins ruff-pre-commit by rev"
    assert m.group("rev") == pins["ruff"], (
        "pre-commit runs ruff %s while the gate runs %s — the same file can be "
        "clean for one and dirty for the other" % (m.group("rev"), pins["ruff"])
    )


# ---- scope: what the SHIPPED documents claim the gate covers ------------------
# Two shipped files described a different gate than the one that runs: after
# check_N and check_O landed, scripts/README.md still named a range ending at M and
# the showcase catalogue one ending at I. Both ship verbatim, so every generated
# project
# inherited a false description of its own gate — and the showcase's copy is served
# live at /api/checks. (This comment states the old ranges in words on purpose:
# writing them in the matched form would make this file its own first finding.) The range is DERIVABLE from check_structure.py, so nothing
# here is a judgment call.
#
# CHANGELOG.md and docs/design/ are excluded on purpose: a changelog entry and a
# design narrative record what was true at a point in time, and rewriting history
# to match today is the opposite of the property this asserts.
# Two spellings, because only one of them was matched and the other went stale in
# silence: the guides roster described what check_structure.py proves as a "list"
# ending at S — with no leading "checks", so the narrower pattern never saw it —
# for the whole of checks T and U, in a row every generated project inherits. A
# range claim is a range claim whichever noun follows it. (Stated in words, not in
# the matched form: writing it out would make this file its own first finding.)
_CLAIMED_RANGE = re.compile(
    r"checks\s+A[\u2013-]([A-Z])\b|\bA[\u2013-]([A-Z])\s+(?:list|set|range)\b"
)
_HISTORICAL = ("CHANGELOG.md", "docs/design/")


def _highest_check_letter():
    text = (_ROOT / "scripts" / "check_structure.py").read_text(encoding="utf-8")
    letters = re.findall(r"^def check_([A-Z])\b", text, re.MULTILINE)
    assert letters, "no check_<LETTER> functions found — re-derive this check"
    return max(letters)


def test_every_shipped_description_of_the_gate_names_the_real_check_range():
    """A document that misdescribes the gate is worse than one that says nothing:
    the reader believes it, and here so does every descendant project."""
    highest = _highest_check_letter()
    wrong = []
    # check_structure's own walk, NOT `git ls-files`: this test ships verbatim into
    # every generated project, and a generated project is not a git repository
    # until its author runs `git init` — so the git form failed on arrival there,
    # which is precisely the defect class this file exists to catch. (Caught by the
    # answer-matrix guard in test_copier_generation.py, within one run of adding it.)
    for dirpath, _dirnames, filenames in cs.walk(str(_ROOT)):
        for filename in filenames:
            if not filename.endswith((".md", ".py")):
                continue
            path = Path(dirpath) / filename
            rel = str(path.relative_to(_ROOT))
            if rel.startswith(_HISTORICAL):
                continue
            wrong.extend(
                "%s claims checks A-%s" % (rel, claimed)
                for match in _CLAIMED_RANGE.findall(
                    path.read_text(encoding="utf-8", errors="replace")
                )
                for claimed in [next(g for g in match if g)]
                if claimed != highest
            )
    assert not wrong, (
        "check_structure.py defines checks through %s, but these shipped files "
        "describe a different gate: %s" % (highest, wrong)
    )
