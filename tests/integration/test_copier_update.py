"""
title: Integration — `copier update` carries template improvements downstream
kind: tests
layer: n/a
summary: The upgrade channel ADR-0004 chose copier for, exercised end to end against the REAL template — clone keel into a scratch dir, generate a project, commit it, evolve the clone, then `copier update`. Proves new template files arrive, template edits land, the project's own edits survive, the `.gitignore` divergence twin holds, `_commit` advances and `_src_path` stays resolvable. Skipped on a bare local clone without the optional `template` extra; CI installs `.[dev,template]` and sets KEEL_REQUIRE_TEMPLATE=1, so there a missing copier is a hard failure instead of a silent skip.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import hermetic_git

# The optional 'template' extra. CI installs it and sets KEEL_REQUIRE_TEMPLATE=1, so a
# missing copier is a HARD collection error there — these tests silently skipping in CI
# is the hole pass 2 closes. A bare local clone leaves the flag unset and still skips
# gracefully. (Same guard in test_copier_generation.py; they must not drift.) Keep the
# two imports in one branch: `yaml` is copier's own dependency, never a new one, so it
# is present exactly when copier is.
if os.environ.get("KEEL_REQUIRE_TEMPLATE") == "1":
    import copier
    import yaml
else:
    copier = pytest.importorskip("copier")
    yaml = pytest.importorskip("yaml")

_ROOT = Path(__file__).resolve().parents[2]
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("git") is None, reason="copier update needs git"),
    pytest.mark.skipif(not (_ROOT / ".git").exists(),
                       reason="update needs a git checkout of the template, not a tarball"),
    pytest.mark.skipif(not (_ROOT / "copier.yml").is_file(),
                       reason="not a copier template — this is a generated project"),
]

# The template's own git config must not be the developer's, and copier shells out to
# git itself — so the neutralisation has to be environment, not `git -c`. The config
# text and the vars that select it live in ONE place (hermetic_git) because this module
# and test_copier_generation.py each grew their own copy and they drifted: this one
# omitted `core.excludesFile`, so a `*.yml` line in the developer's
# ~/.config/git/ignore failed a CORRECT tree here while the sibling passed.

# What "upstream" gains after the project was generated (the update must deliver it).
_NEW_FILE = "docs/upstream-only.txt"
_NEW_FILE_TEXT = "This file only ever existed in the newer template.\n"
_UPSTREAM_EDIT = "\n# upstream marker added after the project was generated\n"
_UPSTREAM_IGNORE = "*.upstream-junk"

# What the project itself changes afterwards (the update must NOT clobber it). These
# must be files the template's own step-3 edits do not touch: appending to the same
# file from both sides conflicts even when the two edits are on different lines.
_LOCAL_FILE = "local-only.txt"
_LOCAL_EDIT = "\nA paragraph the downstream project wrote itself.\n"


def _git(*argv, cwd):
    r = subprocess.run(("git",) + argv, cwd=str(cwd), capture_output=True, text=True)
    assert r.returncode == 0, "git %s failed:\n%s%s" % (" ".join(argv), r.stdout, r.stderr)
    return r.stdout


def _answers(project):
    return yaml.safe_load((project / ".copier-answers.yml").read_text())


@pytest.fixture(scope="module")
def upgraded(tmp_path_factory):
    """generate -> commit -> evolve the template -> `copier update`.

    Module-scoped because the whole cycle costs ~15s and every assertion below reads
    the same resulting tree. Yields (template, project, commit_before).

    The template is a clone of keel at HEAD, so keel itself is never written to — and
    so UNCOMMITTED template edits are deliberately not exercised here (unlike the
    sibling generation tests, where copier's own clone auto-commits them). Commit a
    `copier.yml` change before expecting this test to reflect it.
    """
    mp = pytest.MonkeyPatch()
    work = tmp_path_factory.mktemp("copier_update")
    for var, value in hermetic_git.git_env_vars(work).items():
        mp.setenv(var, value)
    mp.setenv("COPIER_CACHE_DIR", str(work / "copier-cache"))
    try:
        # A throwaway clone is the template: real history, real copier.yml, and a repo
        # we may commit to.
        template = work / "template"
        _git("clone", "--quiet", "--no-hardlinks", str(_ROOT), str(template), cwd=work)

        # 1. a project generated from it, exactly as `make new` does
        project = work / "proj"
        copier.run_copy(str(template), str(project),
                        data={"project_name": "demo_proj", "frontend_stack": "none"},
                        defaults=True, vcs_ref="HEAD", unsafe=False, quiet=True)
        _git("init", "--quiet", "-b", "main", cwd=project)
        _git("add", "-A", cwd=project)
        _git("commit", "--quiet", "-m", "generated from keel", cwd=project)
        commit_before = _answers(project)["_commit"]

        # 2. the project evolves on its own (files the template never touches)
        (project / _LOCAL_FILE).write_text("mine\n")
        readme = project / "README.md"
        readme.write_text(readme.read_text() + _LOCAL_EDIT)
        _git("add", "-A", cwd=project)
        _git("commit", "--quiet", "-m", "downstream work", cwd=project)

        # 3. the template evolves: a new file, an edit to a verbatim-copied file, and a
        #    new ignore rule in BOTH .gitignore twins (as a real keel change would make
        #    it — the twins diverge only over .copier-answers.yml).
        (template / _NEW_FILE).write_text(_NEW_FILE_TEXT)
        for name in (".editorconfig", ".gitignore", ".gitignore.jinja"):
            p = template / name
            extra = _UPSTREAM_EDIT if name == ".editorconfig" else (
                "\n# upstream new ignore rule\n%s\n" % _UPSTREAM_IGNORE)
            p.write_text(p.read_text() + extra)
        _git("add", "-A", cwd=template)
        _git("commit", "--quiet", "-m", "template improves", cwd=template)

        # 4. the upgrade. vcs_ref="HEAD" is LOAD-BEARING: with no argument copier
        #    updates to the newest *tag*, so the moment keel carries one this whole
        #    cycle silently no-ops (measured: rc=0, `_commit` frozen, nothing
        #    delivered, 4 of 7 assertions below then fail). defaults=True is mandatory
        #    — copier refuses a non-interactive update without it ("Interactive session
        #    required"). overwrite=True is what the `copier update` CLI itself passes.
        copier.run_update(str(project), defaults=True, overwrite=True,
                          vcs_ref="HEAD", unsafe=False, quiet=True)
        yield template, project, commit_before
    finally:
        mp.undo()


def test_update_delivers_new_template_files(upgraded):
    """A file added to the template after generation reaches the project."""
    _, project, _ = upgraded
    assert (project / _NEW_FILE).read_text() == _NEW_FILE_TEXT


def test_update_delivers_edits_to_existing_files(upgraded):
    """An edit to an already-copied file is merged in, not skipped."""
    _, project, _ = upgraded
    assert _UPSTREAM_EDIT.strip() in (project / ".editorconfig").read_text()


def test_update_advances_the_recorded_commit(upgraded):
    """`_commit` moves to the new template revision — otherwise the next update would
    replay this one — while `_src_path` still names a RESOLVABLE origin. (The literal
    `.` that `copier copy .` used to record resolves to the generated project itself
    and kills every update; see test_copier_generator_contract.py.)"""
    template, project, commit_before = upgraded
    answers = _answers(project)
    # `git describe --tags --always` is exactly what copier records, so this holds
    # whether or not the template carries release tags.
    described = _git("describe", "--tags", "--always", cwd=template).strip()
    assert str(answers["_commit"]) != str(commit_before)
    assert str(answers["_commit"]) == described
    assert Path(answers["_src_path"]).is_absolute()
    assert (Path(answers["_src_path"]) / "copier.yml").is_file()


def test_update_preserves_downstream_work(upgraded):
    """The whole point of `update` over `recopy`: the project's own commits stay."""
    _, project, _ = upgraded
    assert (project / _LOCAL_FILE).exists()
    assert _LOCAL_EDIT.strip() in (project / "README.md").read_text()


def test_update_keeps_the_gitignore_divergence_twin(upgraded):
    """`.gitignore.jinja` is the one twin that deliberately differs from keel's own
    file (it drops the `.copier-answers.yml` ignore so the answers file is TRACKED
    downstream). An update must carry the twin's new rules WITHOUT re-introducing that
    line from keel's plain `.gitignore`, or every future update of every clone dies."""
    _, project, _ = upgraded
    lines = [ln.strip() for ln in (project / ".gitignore").read_text().splitlines()]
    assert _UPSTREAM_IGNORE in lines            # the upstream's new rule arrived
    assert ".copier-answers.yml" not in lines   # ...and the twin still diverges
    assert ".copier-answers.yml" in _git("ls-files", cwd=project).split()


def test_update_leaves_no_conflicts(upgraded):
    """A clean update must leave no `.rej` files, no inline conflict markers and no
    unmerged paths — otherwise "it worked" is hiding a broken tree. (copier 9 defaults
    to conflict="inline", so a real collision shows up as markers + `UU`, not `.rej`.)"""
    _, project, _ = upgraded
    assert not list(project.rglob("*.rej"))
    assert not _git("diff", "--name-only", "--diff-filter=U", cwd=project).split()
    marked = [str(p.relative_to(project)) for p in project.rglob("*")
              if p.is_file() and not p.is_symlink() and ".git/" not in str(p)
              and b"<<<<<<<" in p.read_bytes()]
    assert marked == []


def test_updated_project_still_passes_its_own_gate(upgraded):
    """The real judge: the upgraded tree is still a structurally valid project."""
    _, project, _ = upgraded
    r = subprocess.run([sys.executable, "scripts/check_structure.py"],
                       cwd=str(project), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
