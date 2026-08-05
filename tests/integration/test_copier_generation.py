"""
title: Integration — copier generates a structurally valid, tailored project
kind: tests
layer: n/a
summary: `copier` renders keel's root template into a new project — the manifest is tailored to the answers, the un-chosen frontend stack is pruned, CLAUDE.md->AGENT.md symlinks are preserved, keel's own template meta-tests are pruned, and check_structure passes. Skipped on a bare local clone without the optional `template` extra; CI installs `.[dev,template]` and declares the surface required (KEEL_REQUIRED_EXTRAS), so there a missing copier is a hard failure instead of a silent skip.
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import hermetic_git
import optional_deps

# The optional 'template' extra. CI installs it and declares it required, so a missing
# copier is a HARD collection error there — these tests silently skipping in CI is the
# hole pass 2 closes. A bare local clone leaves the declaration unset and still skips
# gracefully. `yaml` is copier's own dependency, never a new one, so it belongs to the
# same surface. (The skip/fail decision itself lives in tests/optional_deps.py, which
# is also what stops a fourth copy of this guard from drifting.)
copier = optional_deps.importorskip("copier", extra="template")
yaml = optional_deps.importorskip("yaml", extra="template")

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
    pytest.mark.skipif(not (_ROOT / "copier.yml").is_file(),
                       reason="not a copier template — this is a generated project"),
]

# The one licensed difference between .gitignore and its .jinja twin. Kept as
# literals so a drift on EITHER side fails loudly instead of silently widening.
_KEEL_ANSWERS_BLOCK = (
    "# copier writes this into GENERATED projects (records answers for `copier update`);\n"
    "# keel is the template, not a generated project, so it never commits one of its own.\n"
    ".copier-answers.yml\n"
)
_TWIN_ANSWERS_BLOCK = (
    "# NOTE: `.copier-answers.yml` is deliberately NOT ignored — it records the template\n"
    "# answers and `copier update` needs it. A clone or CI checkout without it cannot\n"
    "# update at all. (Keel's own .gitignore ignores its copy: keel is the template.)\n"
)

# The ONLY licensed differences between pyproject.toml and its .jinja twin: the three
# fields that are answers rather than policy. Everything else in that file shapes the
# gate and must be identical, so it is pinned as text below.
_PYPROJECT_ANSWER_FIELDS = (
    ("# Python src-layout. Distribution metadata for Project Keel.",
     "# Python src-layout. Distribution metadata for {{ project_title }}."),
    ('name = "project_keel"', 'name = "{{ project_slug }}"'),
    ('requires-python = ">=3.10"', 'requires-python = "{{ backend_python }}"'),
)


def _generate(dest, **data):
    """Render the keel template (from git HEAD) into dest with the given answers."""
    copier.run_copy(str(_ROOT), str(dest), data=data, defaults=True,
                    vcs_ref="HEAD", unsafe=False, quiet=True)


def _gitignore_lines(path):
    """Ignore-pattern lines only — comments and blanks stripped."""
    return [ln.strip() for ln in Path(path).read_text().split("\n")
            if ln.strip() and not ln.strip().startswith("#")]


def _hermetic_git_env(tmp_path):
    """A git environment that ignores the DEVELOPER's machine — see hermetic_git.

    Delegates rather than restating the config: this module and
    test_copier_update.py each used to carry their own copy, and the copies
    drifted (the sibling's omitted `core.excludesFile`), which is exactly the
    failure the shared module documents.
    """
    return hermetic_git.git_env(tmp_path)


@pytest.mark.parametrize("stack", ["react-vite", "astro", "none"])
def test_generated_project_is_tailored_and_valid(stack, tmp_path):
    dest = tmp_path / "proj"
    _generate(dest, project_name="demo_proj", frontend_stack=stack)

    # 1. the manifest is tailored to the answers (and valid JSON)
    manifest = json.loads((dest / "config" / "project.json").read_text())
    assert manifest["name"] == "demo_proj"
    frontend = manifest["layers"].get("frontend")
    if stack == "none":
        assert frontend is None
        assert not (dest / "src" / "frontend").exists()      # pruned entirely
    else:
        assert frontend["stack"] == stack
        assert frontend["available"] == [stack]              # only the chosen one
        assert (dest / "src" / "frontend" / stack).is_dir()
        other = "astro" if stack == "react-vite" else "react-vite"
        assert not (dest / "src" / "frontend" / other).exists()  # un-chosen pruned

    # 2. CLAUDE.md -> AGENT.md symlinks are preserved (check_I depends on it)
    assert (dest / "tests" / "CLAUDE.md").is_symlink()

    # 3. copier recorded the answers so `copier update` works later
    assert (dest / ".copier-answers.yml").exists()

    # 4. the structural gate passes on the generated tree (the real judge of "valid")
    r = subprocess.run([sys.executable, "scripts/check_structure.py"],
                       cwd=str(dest), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_default_transports_prune_the_addon_dirs(tmp_path):
    """No add-ons selected: REST+MCP are the always-shipped foundation, and the
    self-contained add-on dirs (api/grpc, api/edge_nginx) are pruned — so `available`
    lists only what actually ships and check_H sees no undeclared api/ dir."""
    dest = tmp_path / "proj"
    _generate(dest, project_name="demo_proj")   # default transports = [] (no add-ons)
    manifest = json.loads((dest / "config" / "project.json").read_text())
    assert manifest["transports"]["enabled"] == ["rest", "mcp"]
    assert set(manifest["transports"]["available"]) == {"rest", "mcp"}   # add-ons pruned
    assert (dest / "api" / "rest_fastapi").is_dir()                      # foundation ships
    assert (dest / "mcp").is_dir()
    assert not (dest / "api" / "grpc").exists()                         # add-on pruned
    assert not (dest / "api" / "edge_nginx").exists()


def test_selected_addon_transport_ships_and_is_declared(tmp_path):
    """Selecting an add-on keeps its dir and declares it; the un-selected one is still
    pruned. This is the gap that used to leak every transport regardless of the answer."""
    dest = tmp_path / "proj"
    _generate(dest, project_name="demo_proj", transports=["grpc"])
    manifest = json.loads((dest / "config" / "project.json").read_text())
    assert manifest["transports"]["enabled"] == ["rest", "mcp", "grpc"]
    assert set(manifest["transports"]["available"]) == {"rest", "mcp", "grpc"}
    assert (dest / "api" / "grpc").is_dir()                             # selected -> ships
    assert not (dest / "api" / "edge_nginx").exists()                  # un-selected -> pruned
    # the tailored tree still passes its own structural gate
    r = subprocess.run([sys.executable, "scripts/check_structure.py"],
                       cwd=str(dest), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_nondefault_name_and_python_propagate_and_stay_valid(tmp_path):
    """A free-text name + a non-default requires-python must reach *every* file that
    declares them — else check_H fails (layers.backend.python != requires-python) or
    the 'tailored' name is a lie. This is the case defaults masked: with backend_python
    left at '>=3.10' the pyproject already matched by luck, so the twin was never
    exercised. Guards the project_slug/project_title derivation and the pyproject twin."""
    dest = tmp_path / "proj"
    _generate(dest, project_name="Acme Widgets", frontend_stack="astro",
              backend_python=">=3.11", transports=["grpc"], profiles=["ai"])

    manifest = json.loads((dest / "config" / "project.json").read_text())
    pyproject = (dest / "pyproject.toml").read_text()
    readme = (dest / "README.md").read_text()

    # identifier form (PEP 508-valid slug) reaches both manifest and package metadata
    assert manifest["name"] == "acme_widgets"
    assert 'name = "acme_widgets"' in pyproject
    # the non-default python reaches both, so check_H's equality holds (the gating bug)
    assert manifest["layers"]["backend"]["python"] == ">=3.11"
    assert 'requires-python = ">=3.11"' in pyproject
    # display form (title-cased) reaches the README heading + frontmatter title
    assert "\n# Acme Widgets\n" in readme
    assert "\ntitle: Acme Widgets\n" in readme

    # the real judge: the generated tree passes its own structural gate
    r = subprocess.run([sys.executable, "scripts/check_structure.py"],
                       cwd=str(dest), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


# --- the upgrade channel (ADR-0004's whole justification) ------------------
#
# copier reads .copier-answers.yml from the WORKING TREE, so an ignored-but-
# present file still updates in the directory copier created. The break happens
# one step later: a teammate's `git clone`, a CI checkout or a fresh machine has
# no answers file at all, and `copier update` fails outright with "Cannot update
# because cannot obtain old template references from `.copier-answers.yml`".
# So the assertion that matters is TRACKED-BY-GIT, not merely exists-on-disk.

def test_generated_project_commits_its_copier_answers(tmp_path):
    """A generated project must TRACK .copier-answers.yml, or every clone of it
    loses the ability to `copier update` — the one capability ADR-0004 chose
    copier for. Keel's own .gitignore ignores the file (keel is the template,
    never a generated project); the .gitignore.jinja twin drops that line."""
    dest = tmp_path / "proj"
    _generate(dest, project_name="demo_proj", frontend_stack="none")

    assert (dest / ".copier-answers.yml").exists()
    assert ".copier-answers.yml" not in _gitignore_lines(dest / ".gitignore")

    # the real judge: git itself, in a fresh repo made from the generated tree
    env = _hermetic_git_env(tmp_path)
    for argv in (["git", "init", "-q"], ["git", "add", "-A"]):
        r = subprocess.run(argv, cwd=str(dest), capture_output=True, text=True, env=env)
        assert r.returncode == 0, r.stdout + r.stderr
    tracked = subprocess.run(["git", "ls-files"], cwd=str(dest),
                             capture_output=True, text=True, env=env).stdout.split("\n")
    assert ".copier-answers.yml" in tracked


def test_generated_project_starts_its_own_changelog(tmp_path):
    """CHANGELOG.md ships verbatim unless twinned, which hands the new project
    KEEL's release history — a dated `[0.1.0]` it never released, describing keel's
    `.gitignore.jinja` twin and `_min_copier_version` bump as if they were its own
    changes. A descendant starts empty, and records where it came from instead."""
    dest = tmp_path / "proj"
    _generate(dest, project_name="Acme Widgets", frontend_stack="none")
    text = (dest / "CHANGELOG.md").read_text()

    # Naming keel as the ORIGIN is wanted (that is the provenance story). What must
    # not leak is keel's release HISTORY and its internals-as-your-changes.
    for leaked in ("project_keel", ".gitignore.jinja", "_min_copier_version"):
        assert leaked not in text, (
            "keel's own changelog content leaked into the generated project: %r" % leaked)
    releases = [ln for ln in text.splitlines() if ln.startswith("## [")]
    assert releases == ["## [Unreleased]"], (
        "a generated project must start with no releases of its own, got: %r" % releases)
    assert "# Acme Widgets" in text          # it is the PROJECT's changelog
    assert "project-keel" in text            # ...that records where it came from


def test_generated_project_does_not_ship_keels_template_meta_tests(tmp_path):
    """These copier tests are META-tests: they generate FROM this repo and assert on
    `copier.yml` and the `.jinja` twins, neither of which exists in a project
    generated BY it. `.github/workflows/ci.yml` ships verbatim and now installs the
    `template` extra, so an un-pruned meta-test would RUN downstream and fail on
    keel-only files — turning every descendant's CI red. Prune them at generation."""
    dest = tmp_path / "proj"
    _generate(dest, project_name="demo_proj", frontend_stack="none")

    leaked = sorted(p.name for p in (dest / "tests" / "integration").glob("test_copier_*.py"))
    assert leaked == [], (
        "keel's own template meta-tests shipped into the generated project: %s — they "
        "assert on copier.yml/.jinja twins that a generated project does not have" % leaked)
    # ...and the rest of the suite is still there (the prune is surgical, not a
    # `tests/integration` wipe).
    assert (dest / "tests" / "integration" / "test_showcase_api.py").is_file()
    assert (dest / "tests" / "integration" / "README.md").is_file()


def test_gitignore_twin_stays_pinned_to_keels_own(tmp_path):
    """`.gitignore.jinja` is a DIVERGENCE twin: unlike the project.json/pyproject/
    README twins it must NOT reproduce keel's file, because keel is the template
    and a generated project is not. Its one licensed difference is the
    copier-answers block. Nothing else may drift — and no gate knows the twins
    exist yet (see docs/design/keel-hardening-plan.md, pass 5), so pin it here."""
    keel_text = (_ROOT / ".gitignore").read_text()
    twin_text = (_ROOT / ".gitignore.jinja").read_text()

    assert ".copier-answers.yml" in _gitignore_lines(_ROOT / ".gitignore")
    assert twin_text == keel_text.replace(_KEEL_ANSWERS_BLOCK, _TWIN_ANSWERS_BLOCK), (
        "the twin drifted from .gitignore beyond the copier-answers block; "
        "re-derive it rather than hand-patching one side"
    )

    # and the twin is what a generated project actually gets
    dest = tmp_path / "proj"
    _generate(dest, project_name="demo_proj", frontend_stack="none")
    assert (dest / ".gitignore").read_text() == twin_text
    assert not (dest / ".gitignore.jinja").exists()   # the suffix is consumed


# --- the gate a DESCENDANT gets -------------------------------------------------
# `Makefile` has no `.jinja` twin, so it ships VERBATIM: pass 3's widened
# `CODE_ROOTS` lint scope lands in every generated project. `pyproject.toml` does
# NOT ship verbatim — copier's `_render_path` returns early for any path with a
# `.jinja` sibling, so a descendant's pyproject comes ENTIRELY from
# `pyproject.toml.jinja`. Widening one side and not the other hands every
# descendant a gate that is red on arrival. The tests below judge the generated
# project by ITS OWN shipped config, so they fail whichever side drifts.

def _code_roots_from_makefile(makefile_text):
    """The lint scope the generated Makefile actually ships, derived not re-typed.

    Mirrors `PY_ROOTS := $(wildcard $(CODE_ROOTS))`: the declared roots filtered to
    the ones copier left in place.
    """
    for line in makefile_text.splitlines():
        if line.startswith("CODE_ROOTS"):
            _, _, rhs = line.partition(":=")
            return rhs.split()
    raise AssertionError("the generated Makefile declares no CODE_ROOTS")


def test_a_generated_project_is_lint_clean_on_arrival(tmp_path):
    """`make lint` must be GREEN in a freshly generated project.

    A descendant's first act is to run the gate; if it is red on arrival the user
    cannot tell keel's debt from their own, and pass 3's whole point — that a green
    gate means something — is inverted downstream.
    """
    dest = tmp_path / "proj"
    _generate(dest, project_name="demo_proj", frontend_stack="none")

    roots = [r for r in _code_roots_from_makefile((dest / "Makefile").read_text())
             if (dest / r).exists()]
    assert "scripts" in roots and "src" in roots, roots   # not a vacuous empty scope

    # run from the generated tree so ruff reads the GENERATED pyproject.toml
    r = subprocess.run([sys.executable, "-m", "ruff", "check", *roots],
                       cwd=str(dest), capture_output=True, text=True)
    assert r.returncode == 0, (
        "a freshly generated project fails its own `make lint-py` over the roots its "
        "own Makefile ships (%s) — pyproject.toml.jinja has drifted from the Makefile:\n%s"
        % (" ".join(roots), r.stdout + r.stderr))


def test_pyproject_twin_stays_pinned_to_keels_own():
    """`pyproject.toml.jinja` is a PARITY twin: it must reproduce keel's own
    `pyproject.toml` except for the per-answer fields.

    Unlike `.gitignore.jinja` (a DIVERGENCE twin) there is nothing a descendant
    should have differently here — every gate-shaping key (ruff carve-outs, mypy
    `files`, the mypy ratchet) is exactly what keel gates itself with. Left to
    drift, the twin re-opens in every descendant the blind spot pass 3 closed
    here, and silently: a narrower mypy still exits 0.

    Asserted as text, not key-by-key, so a drift in ANY key fails — a key-by-key
    check only ever pins the keys someone already thought of. (General twin
    parity for all five twins is check_N, pass 5 of the hardening plan; this
    pins the one twin whose drift is load-bearing today.)
    """
    keel_text = (_ROOT / "pyproject.toml").read_text()
    twin_text = (_ROOT / "pyproject.toml.jinja").read_text()

    expected = keel_text
    for keel_literal, rendered in _PYPROJECT_ANSWER_FIELDS:
        assert keel_text.count(keel_literal) == 1, (
            "%r is no longer a unique line in pyproject.toml — re-derive the "
            "substitution list rather than letting the twin check go vacuous"
            % keel_literal)
        expected = expected.replace(keel_literal, rendered)

    assert twin_text == expected, (
        "pyproject.toml.jinja drifted from pyproject.toml beyond the per-answer "
        "fields; re-derive it from pyproject.toml rather than hand-patching one side"
    )


# The README's "delete what you don't need" advice, read out of the GENERATED
# project's own README rather than restated here — so adding a directory to that
# sentence is covered by this test instead of quietly widening a false promise.
_DELETE_ADVICE = re.compile(r"Delete any optional dirs you don't need \(([^)]*)\)")
_BACKTICKED = re.compile(r"`([^`]+)`")


def _readme_deletable_dirs(project):
    text = (project / "README.md").read_text()
    hit = _DELETE_ADVICE.search(text)
    assert hit, (
        "the generated README no longer carries the 'delete any optional dirs' "
        "sentence this test verifies; re-derive it rather than deleting the pin")
    return [name.rstrip("/") for name in _BACKTICKED.findall(hit.group(1))]


def test_the_readmes_delete_advice_leaves_a_green_gate(tmp_path):
    """Doing exactly what the generated README says must not break the project.

    It used to: the README named `models/` among the dirs you may delete, but
    `config/project.json` declares the model adapters and their directory, so
    following the advice produced `3 error(s)` and exit 1 on a project whose owner
    had done nothing wrong. Advice that reddens the gate is worse than no advice —
    the first thing a new user does is exactly what the README told them to.
    """
    dest = tmp_path / "proj"
    _generate(dest, project_name="demo_proj", frontend_stack="none")
    deletable = _readme_deletable_dirs(dest)
    assert deletable, "the delete-advice sentence lists no directories"

    for name in deletable:
        assert (dest / name).exists(), (
            "the README offers to delete %r, which a generated project does not "
            "even have" % name)
        shutil.rmtree(str(dest / name))

    r = subprocess.run([sys.executable, "scripts/check_structure.py"],
                       cwd=str(dest), capture_output=True, text=True)
    assert r.returncode == 0, (
        "following the README's own delete advice breaks the generated project's "
        "gate:\n" + r.stdout + r.stderr)


def test_deleting_a_manifest_declared_dir_is_caught_and_the_documented_fix_works(tmp_path):
    """The other half: `models/` is NOT free to delete, and the README says so.

    Two claims, both load-bearing. (1) The caveat is real — deleting `models/`
    alone must fail, or the README would be warning about nothing. (2) The remedy
    the README gives actually works, so a user who follows it lands green rather
    than stuck.
    """
    dest = tmp_path / "proj"
    _generate(dest, project_name="demo_proj", frontend_stack="none")
    assert "models" not in _readme_deletable_dirs(dest), (
        "the README lists `models/` as free to delete, but the manifest declares "
        "the adapters that live there — that advice reddens the gate")

    shutil.rmtree(str(dest / "models"))
    r = subprocess.run([sys.executable, "scripts/check_structure.py"],
                       cwd=str(dest), capture_output=True, text=True)
    assert r.returncode != 0, (
        "deleting `models/` no longer fails the gate, so the README's caveat about "
        "clearing the manifest is now warning about nothing — re-derive it")

    manifest = dest / "config" / "project.json"
    data = json.loads(manifest.read_text())
    data["models"]["available"] = {}
    data["models"]["default"] = None
    manifest.write_text(json.dumps(data, indent=2) + "\n")

    r = subprocess.run([sys.executable, "scripts/check_structure.py"],
                       cwd=str(dest), capture_output=True, text=True)
    assert r.returncode == 0, (
        "the fix the README documents for a deleted `models/` does not produce a "
        "green gate:\n" + r.stdout + r.stderr)


# An `_exclude` entry is ANSWER-DRIVEN when it is wrapped in a jinja condition;
# stripping the tags leaves the path it prunes. Derived from copier.yml rather than
# listed here, so a prune added later is covered without anyone remembering to.
_JINJA_TAG = re.compile(r"\{%.*?%\}")


def _answer_driven_prunes():
    """(copier.yml config, [(entry, path)] for each conditional `_exclude` entry)."""
    cfg = yaml.safe_load((_ROOT / "copier.yml").read_text())
    prunes = [(entry, _JINJA_TAG.sub("", entry).strip())
              for entry in cfg.get("_exclude", []) if "{%" in entry]
    return cfg, [(entry, path) for entry, path in prunes if path]


def test_every_answer_driven_prune_has_a_retirement_migration():
    """`_exclude` prunes at GENERATION; only `_migrations` RETIRES on update.

    A project that answered `react-vite` and later re-answers `astro` does not get
    the react-vite tree removed by the exclude — copier renders the old template
    copy with the UNION of old and new excludes, on purpose, so update never
    deletes. Without a mirroring migration the declined stack stays on disk, the
    answers file disagrees with the tree, and the project's own gate goes red.

    So the two halves are a contract, and this asserts the contract for the whole
    CLASS: every conditional exclude, including ones added after this was written,
    must name its path in some migration command. Adding a prune without its
    retirement fails here rather than surfacing later as a mystery in someone
    else's project. (That the retirement actually WORKS is
    tests/integration/test_copier_update.py's restack tests; this only pins that
    it exists.)
    """
    cfg, prunes = _answer_driven_prunes()
    assert prunes, (
        "no conditional _exclude entries found — either copier.yml stopped pruning "
        "by answer or the syntax moved; re-derive this check rather than leaving it "
        "vacuously green")

    commands = " ".join(
        m["command"] if isinstance(m, dict) else str(m)
        for m in cfg.get("_migrations", []))
    # Word-boundary, not substring: plain `in` would let the `src/frontend/react-vite`
    # migration vouch for the separate `src/frontend` prune and pass vacuously.
    missing = [(entry, path) for entry, path in prunes
               if not re.search(r"(?<![\w./-])%s(?![\w./-])" % re.escape(path), commands)]
    assert not missing, (
        "these _exclude entries prune a path at generation but no _migrations entry "
        "retires it on update, so a project that re-answers keeps it forever:\n"
        + "\n".join("  %s   (path: %s)" % (entry, path) for entry, path in missing))


# Shipped-verbatim surfaces that name paths. Each ships into every generated
# project unrendered, so any directory they hardcode must survive the answers.
_VERBATIM_PATH_SURFACES = ("Makefile", ".github/workflows", "scripts")
_FRONTEND_REF = re.compile(r"src/frontend/([A-Za-z0-9][A-Za-z0-9._-]*)")


@pytest.mark.parametrize("stack", ["react-vite", "astro", "none"])
def test_no_shipped_file_points_at_a_frontend_the_answers_pruned(stack, tmp_path):
    """The generalisation of the meta-test prune, and of pass 2's `ci.yml` fix.

    `copier.yml` prunes the un-chosen `src/frontend/<stack>` directories, but the
    files that USE them ship verbatim and are not answer-aware. Measured before
    this pin, on a project generated with the DEFAULT answers:
    `.github/workflows/pages.yml` ran `npm ci` in `src/frontend/astro` (red on the
    first push to main), `make run-web` died with ENOENT, and
    `scripts/jobs/export_showcase_static.py` wrote its default output INTO the
    pruned directory — resurrecting a stack the user declined.

    Scans the generated tree rather than keel's, and derives the referenced
    directories from the text, so a new hardcode in any shipped recipe is caught
    without anyone remembering to extend a list.

    Comment-only lines are dropped first: this rule governs what the file DOES,
    not what it explains, and the fixes here are documented by comments that name
    the very path they removed. The deliberate consequence is leniency toward a
    path buried in a Python string literal — a false negative, never a false
    positive, which is the right way round for a rule that fails a build.
    """
    dest = tmp_path / "proj"
    _generate(dest, project_name="demo_proj", frontend_stack=stack)

    offenders = []
    for surface in _VERBATIM_PATH_SURFACES:
        root = dest / surface
        paths = [root] if root.is_file() else sorted(
            p for p in root.rglob("*") if p.is_file() and p.suffix in (".yml", ".yaml", ".py"))
        for path in paths:
            code = "\n".join(ln for ln in path.read_text().splitlines()
                             if not ln.lstrip().startswith("#"))
            offenders.extend(
                "%s -> src/frontend/%s" % (path.relative_to(dest), referenced)
                for referenced in sorted(set(_FRONTEND_REF.findall(code)))
                if not (dest / "src" / "frontend" / referenced).is_dir())

    assert offenders == [], (
        "with frontend_stack=%r these shipped-verbatim files still point at a "
        "frontend directory copier pruned, so the generated project fails the "
        "moment that recipe runs:\n  %s" % (stack, "\n  ".join(sorted(offenders))))


def test_meta_tests_neutralise_themselves_in_a_project_that_still_has_them(tmp_path):
    """The stopgap for the defect `_exclude` structurally cannot fix.

    Pruning at generation does not help a project generated BEFORE the prune
    existed: copier renders the old template copy with the UNION of old and new
    excludes precisely so update never deletes anything, so those projects keep
    keel's meta-tests forever — and `copier update` hands them the newer `ci.yml`
    that installs the `template` extra and declares it required. Their CI
    then goes red because of the update meant to fix CI.

    Simulates exactly that: a real generated project, with the meta-tests copied
    back in, run the way CI runs them. They must SKIP, not fail — and not by
    accident of a missing copier, so the required-extra flag is set.
    """
    dest = tmp_path / "proj"
    _generate(dest, project_name="demo_proj", frontend_stack="none")

    metas = sorted((_ROOT / "tests" / "integration").glob("test_copier_*.py"))
    assert metas, "no meta-test modules found — has the naming convention moved?"
    for meta in metas:
        assert not (dest / "tests" / "integration" / meta.name).exists(), (
            "%s was not pruned at generation" % meta.name)
        shutil.copy2(str(meta), str(dest / "tests" / "integration" / meta.name))

    env = dict(os.environ)
    env[optional_deps.ENV_VAR] = "template,dev,transport"   # as CI declares it
    env["PYTHONPATH"] = "src:."
    # Only the meta-modules. The generated project's OTHER integration tests read a
    # corpus that `make site-data` builds, so collecting the whole directory here
    # would fail for a reason that has nothing to do with what this test asserts.
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
        + ["tests/integration/%s" % m.name for m in metas],
        cwd=str(dest), capture_output=True, text=True, env=env)

    assert r.returncode == 0, (
        "keel's template meta-tests FAIL inside a generated project that still "
        "carries them, so any descendant predating the prune goes red on its next "
        "`copier update`:\n" + r.stdout[-4000:] + r.stderr[-2000:])
    assert "skipped" in r.stdout, (
        "expected the meta-tests to skip themselves in a non-template tree:\n"
        + r.stdout[-2000:])
