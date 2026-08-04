"""
title: Integration — copier generates a structurally valid, tailored project
kind: tests
layer: n/a
summary: `copier` renders keel's root template into a new project — the manifest is tailored to the answers, the un-chosen frontend stack is pruned, CLAUDE.md->AGENT.md symlinks are preserved, keel's own template meta-tests are pruned, and check_structure passes. Skipped on a bare local clone without the optional `template` extra; CI installs `.[dev,template]` and sets KEEL_REQUIRE_TEMPLATE=1, so there a missing copier is a hard failure instead of a silent skip.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# The optional 'template' extra. CI installs it and sets KEEL_REQUIRE_TEMPLATE=1, so a
# missing copier is a HARD collection error there — these tests silently skipping in CI
# is the hole pass 2 closes. A bare local clone leaves the flag unset and still skips
# gracefully. (Same guard in test_copier_update.py; they must not drift.)
if os.environ.get("KEEL_REQUIRE_TEMPLATE") == "1":
    import copier
else:
    copier = pytest.importorskip("copier")

_ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration

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
    """A git environment that ignores the DEVELOPER's machine.

    `git add -A` honours global excludes, and git reads `$XDG_CONFIG_HOME/git/ignore`
    (i.e. ~/.config/git/ignore) with no config entry at all — so a single `*.yml`
    line there, or a `core.excludesFile` naming `.copier-answers.yml`, silently
    fails the tracked-answers assertion below on someone else's laptop. Neutralise
    global + system config and point excludesFile at nothing.
    (test_copier_update.py sets the equivalent via monkeypatch for copier's own
    git subprocesses; keep the two in step.)
    """
    cfg = tmp_path / "gitconfig"
    cfg.write_text("[user]\n\tname = Keel Test\n\temail = keel-test@example.invalid\n"
                   "[core]\n\texcludesFile = %s\n\tfsmonitor = false\n"
                   "[init]\n\tdefaultBranch = main\n" % os.devnull)
    env = dict(os.environ)
    env.update(GIT_CONFIG_GLOBAL=str(cfg), GIT_CONFIG_SYSTEM=os.devnull,
               GIT_CONFIG_NOSYSTEM="1")
    return env


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
