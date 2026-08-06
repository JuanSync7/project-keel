"""
title: Integration — `copier update` carries template improvements downstream
kind: tests
layer: n/a
summary: The upgrade channel ADR-0004 chose copier for, exercised end to end against the REAL template — clone keel into a scratch dir, generate a project, commit it, evolve the clone, then `copier update`. Proves new template files arrive, template edits land, the project's own edits survive, the `.gitignore` divergence twin holds, `_commit` advances and `_src_path` stays resolvable. Skipped on a bare local clone without the optional `template` extra; CI installs `.[dev,template]` and declares the surface required (KEEL_REQUIRED_EXTRAS), so there a missing copier is a hard failure instead of a silent skip.
"""
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
optional_deps.importorskip("copier.errors", extra="template")
yaml = optional_deps.importorskip("yaml", extra="template")

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


def _clone_template(dest, work):
    """Clone keel into `dest` INCLUDING the uncommitted working tree.

    `git clone` carries only HEAD, so an edit you have not committed yet is
    invisible to the template these tests actually exercise. That is not
    hypothetical: a whole `_migrations` block sat in the working tree while this
    module ran against a clone that had none, so the migrations "silently did
    nothing" — they did not exist. The symptom (a feature that no-ops) looks
    nothing like the cause (the harness tests a different tree), which is what
    made it expensive.

    So replay the working-tree diff as a real commit in the clone: what you are
    editing is what gets tested. On a clean tree — CI, and any run after you
    commit — the patch is empty and this is exactly a plain clone.

    `git diff HEAD` covers modifications, deletions and files already `git add`ed;
    a brand-new file that has never been staged is still invisible, so `git add`
    it before expecting these tests to see it.
    """
    _git("clone", "--quiet", "--no-hardlinks", str(_ROOT), str(dest), cwd=work)
    patch = subprocess.run(("git", "diff", "HEAD", "--binary"), cwd=str(_ROOT),
                           capture_output=True)
    assert patch.returncode == 0, patch.stderr.decode("utf-8", "replace")
    if patch.stdout.strip():
        applied = subprocess.run(("git", "apply", "--index", "-"), cwd=str(dest),
                                 input=patch.stdout, capture_output=True)
        assert applied.returncode == 0, (
            "could not replay keel's working tree onto its clone:\n"
            + applied.stderr.decode("utf-8", "replace"))
        _git("commit", "--quiet", "-m", "uncommitted working tree under test", cwd=dest)
    return dest


@pytest.fixture(scope="module")
def upgraded(tmp_path_factory):
    """generate -> commit -> evolve the template -> `copier update`.

    Module-scoped because the whole cycle costs ~15s and every assertion below reads
    the same resulting tree. Yields (template, project, commit_before).

    The template is a clone of keel, so keel itself is never written to. The clone
    carries the uncommitted working tree too (see `_clone_template`), so an edit you
    are still working on is the edit under test.
    """
    mp = pytest.MonkeyPatch()
    work = tmp_path_factory.mktemp("copier_update")
    for var, value in hermetic_git.git_env_vars(work).items():
        mp.setenv(var, value)
    mp.setenv("COPIER_CACHE_DIR", str(work / "copier-cache"))
    try:
        # A throwaway clone is the template: real history, real copier.yml, and a repo
        # we may commit to.
        template = _clone_template(work / "template", work)

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
        #    unsafe=True is what `copier update --trust` passes, and keel's `_migrations`
        #    make it mandatory: copier classes a template carrying them as unsafe and
        #    refuses to update without trust (pinned by the restack tests below).
        copier.run_update(str(project), defaults=True, overwrite=True,
                          vcs_ref="HEAD", unsafe=True, quiet=True)
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


# --- retirement: what an update must REMOVE when an answer changes -------------
#
# `_exclude` is a GENERATION-time filter and nothing more. On update copier renders
# the old template copy with the UNION of the old and new excludes — deliberately,
# "to prevent deletion" (copier/_main.py) — so an excluded path is never retired,
# only never created. Retirement needs `_migrations`, which is a separate mechanism
# with a separate trust requirement; both halves are pinned here.


@pytest.fixture(scope="module")
def restacked(tmp_path_factory):
    """generate with one frontend stack -> commit -> `copier update` to the other.

    The ordinary reason anyone re-answers a question, and the case `_exclude`
    structurally cannot handle. Yields (project, refusal), where `refusal` is the
    error from the deliberate no-trust attempt made first: `_check_unsafe` is the
    very first statement of `run_update`, so that attempt cannot have mutated
    anything, and folding it in here buys the trust assertion without a second
    ~15s generate/commit cycle.
    """
    mp = pytest.MonkeyPatch()
    work = tmp_path_factory.mktemp("copier_restack")
    for var, value in hermetic_git.git_env_vars(work).items():
        mp.setenv(var, value)
    mp.setenv("COPIER_CACHE_DIR", str(work / "copier-cache"))
    try:
        template = _clone_template(work / "template", work)
        project = work / "proj"
        copier.run_copy(str(template), str(project),
                        data={"project_name": "demo_proj",
                              "frontend_stack": "react-vite"},
                        defaults=True, vcs_ref="HEAD", unsafe=False, quiet=True)
        _git("init", "--quiet", "-b", "main", cwd=project)
        _git("add", "-A", cwd=project)
        _git("commit", "--quiet", "-m", "generated from keel", cwd=project)

        with pytest.raises(copier.errors.UnsafeTemplateError) as refusal:
            copier.run_update(str(project), defaults=True, overwrite=True,
                              data={"frontend_stack": "astro"},
                              vcs_ref="HEAD", unsafe=False, quiet=True)

        copier.run_update(str(project), defaults=True, overwrite=True,
                          data={"frontend_stack": "astro"},
                          vcs_ref="HEAD", unsafe=True, quiet=True)
        yield project, refusal.value
    finally:
        mp.undo()


def test_update_retires_the_frontend_stack_the_new_answer_declined(restacked):
    """The declined stack must be GONE, not merely un-recreated."""
    project, _ = restacked
    assert (project / "src" / "frontend" / "astro").is_dir()
    assert not (project / "src" / "frontend" / "react-vite").exists(), (
        "`copier update` left the previously-chosen frontend on disk while "
        ".copier-answers.yml says the project uses the other one — _exclude cannot "
        "retire a path, so this needs a mirroring _migrations entry")


def test_restacked_project_records_only_the_new_answer(restacked):
    """Disk and answers must agree; a stale tree with a fresh answers file is the
    same defect wearing a disguise."""
    project, _ = restacked
    assert _answers(project)["frontend_stack"] == "astro"


def test_restacked_project_still_passes_its_own_gate(restacked):
    """The real judge, and why this matters beyond tidiness: a stale stack leaves
    dangling CLAUDE.md -> AGENT.md symlinks and a stack config/project.json does not
    declare, which check_structure reports as errors. The project's own gate goes red
    through no act of its own."""
    project, _ = restacked
    r = subprocess.run([sys.executable, "scripts/check_structure.py"],
                       cwd=str(project), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_update_without_trust_refuses_a_template_carrying_migrations(restacked):
    """Retirement is not free: `_migrations` run arbitrary commands, so copier classes
    the template as unsafe and `copier update` now REFUSES without `--trust` instead of
    silently skipping them. That makes `--trust` part of the documented update command
    rather than a nicety — pinned here so the docs and the behaviour cannot drift.
    Generation is unaffected: `_check_unsafe` only counts migrations on `update`, which
    is why `make new` still needs no trust flag (the run_copy above uses unsafe=False)."""
    _, refusal = restacked
    assert "migrations" in str(refusal)

@pytest.fixture(scope="module")
def unshowcased(tmp_path_factory):
    """generate WITH the showcase -> commit -> `copier update` declining it.

    The other reason anyone re-answers: a project that took the bundled demo to see
    how the thing works, then wants it gone. `_exclude` cannot deliver that — the
    tree already has the files — so this is the live proof for the showcase
    migrations, in the same shape as `restacked`. Kept as a separate module-scoped
    fixture rather than folded into that one because a project cannot restack its
    frontend and drop the showcase in a single update without conflating which
    answer removed what.
    """
    mp = pytest.MonkeyPatch()
    work = tmp_path_factory.mktemp("copier_unshowcase")
    for var, value in hermetic_git.git_env_vars(work).items():
        mp.setenv(var, value)
    mp.setenv("COPIER_CACHE_DIR", str(work / "copier-cache"))
    try:
        template = _clone_template(work / "template", work)
        project = work / "proj"
        copier.run_copy(str(template), str(project),
                        data={"project_name": "demo_proj",
                              "frontend_stack": "react-vite", "showcase": True},
                        defaults=True, vcs_ref="HEAD", unsafe=False, quiet=True)
        assert (project / "src" / "backend" / "showcase").is_dir(), (
            "the fixture must start FROM a project that has the showcase, or the "
            "retirement below proves nothing")
        _git("init", "--quiet", "-b", "main", cwd=project)
        _git("add", "-A", cwd=project)
        _git("commit", "--quiet", "-m", "generated from keel", cwd=project)

        copier.run_update(str(project), defaults=True, overwrite=True,
                          data={"showcase": False},
                          vcs_ref="HEAD", unsafe=True, quiet=True)
        yield project
    finally:
        mp.undo()


def test_update_retires_the_showcase_the_new_answer_declined(unshowcased):
    """Every part of it, not just the package: a half-retired showcase leaves a REST
    app importing a router that is gone, or a `site-static` target calling a deleted
    exporter. Both are silent until someone runs them."""
    survivors = [p for p in (
        "src/backend/showcase",
        "api/rest_fastapi/showcase_api.py",
        "scripts/jobs/export_showcase_static.py",
        "scripts/jobs/build_llms_txt.py",
        "tests/unit/backend/test_showcase.py",
        "tests/integration/test_showcase_repo.py",
        "tests/integration/test_showcase_api.py",
        "docs/guides/showcase-site.md",
    ) if (unshowcased / p).exists()]
    assert not survivors, (
        "`copier update` recorded showcase=false but left these on disk: %s" % survivors)


def test_retiring_the_showcase_keeps_what_never_depended_on_it(unshowcased):
    """The migrations must not over-reach. The corpus outlives the showcase — mcp/,
    the agents and scripts/query_corpus.py all read wiki/corpus.json — so deleting
    its producers along with the demo would break working surfaces to tidy up an
    unrelated one. (`wiki/corpus.json` itself is not asserted here: it is a generated
    view no project ships, built by `make site-data`. That no migration deletes it is
    pinned in test_copier_generation.py, where copier.yml is already parsed.)"""
    for kept in ("mcp", "agents", "api/rest_fastapi/aad",
                 "scripts/query_corpus.py", "scripts/jobs/build_corpus.py",
                 "scripts/jobs/link_corpus.py", "scripts/jobs/check_corpus.py",
                 "src/backend/example_feature", "src/frontend/react-vite"):
        assert (unshowcased / kept).exists(), (
            "%s does not depend on the showcase but the retirement removed it" % kept)


def test_unshowcased_project_records_the_new_answer_and_passes_its_own_gate(unshowcased):
    """Disk and answers agree, and the project's own gate is the judge of that."""
    assert _answers(unshowcased)["showcase"] is False
    r = subprocess.run([sys.executable, "scripts/check_structure.py"],
                       cwd=str(unshowcased), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
