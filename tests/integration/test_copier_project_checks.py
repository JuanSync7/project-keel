"""
title: Integration — a project's own checks survive `copier update`
kind: tests
layer: n/a
summary: The reason `structure.project_checks` exists, exercised against the REAL template. A toy project generated from a clone of keel declares a `checks/` directory, adds a check there (the converse guarded-recipe rule one downstream project wrote into its own copy of scripts/check_structure.py), and commits; the template then changes scripts/check_structure.py; a real `copier update --trust --defaults --vcs-ref HEAD` exits 0, leaves that module merged and byte-identical to the new template's, and the toy's gate reports the planted violation from the project check and nothing from it once fixed. The old way, a project edit to check_structure.py on the line the template changes, still conflicts there; no copier job imports or reads that module (scripts/jobs/conflict_guard.py refuses a job only over the files it reads), so the update runs every migration, exits 0 and leaves the hunk for the merge, with no refusal, no traceback and no conflicted document's stamp rewritten. The same edit to a module the jobs do import (scripts/child_env.py) stops the update at the first migration with exit 2, the refusal naming that file and the command that finishes the update, and no traceback. The template's shipped manifest, rendered and `.jinja` twin, never carries the key, not even as null. Excluded from generated projects with the other `test_copier_*.py` meta-tests, which is where that last pin belongs: a project that adopts the extension point declares the key.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import doc_stamps
import hermetic_git
import optional_deps

copier = optional_deps.importorskip("copier", extra="template")
optional_deps.importorskip("copier.errors", extra="template")
# copier runs `_tasks` and `_migrations` through plumbum, whose `local.env` is a
# snapshot taken at import (test_copier_update.py says why).
plumbum = optional_deps.importorskip("plumbum", extra="template")

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))
import conflict_guard  # noqa: E402

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (_ROOT / ".git").exists(),
        reason="update needs a git checkout of the template, not a tarball",
    ),
    pytest.mark.skipif(
        not (_ROOT / "copier.yml").is_file(),
        reason="not a copier template — this is a generated project",
    ),
]

_CS = "scripts/check_structure.py"
# Spelled as repetitions so this file holds no marker text: the leftover-marker
# tree scans read it too.
_OPEN = "<" * 7
_FM = (
    "---\ntitle: %s\nkind: %s\nlayer: n/a\nstatus: stable\nsummary: %s\nid: %s\n"
    "created: 2026-01-01\nupdated: 2026-01-01\nvisibility: internal\n"
    "canonical: true\nowner: TBD\n---\n\n# %s\n\n%s\n"
)
# The converse of template check_W's guard rule, as a project check: a target
# whose recipe opens with $(WRITE_GUARD) carries [write]. It reuses the gate's
# own makefile readers through `import check_structure`.
_GUARDED = '''\
"""A recipe that opens with $(WRITE_GUARD) is labelled [write]."""

import check_structure

_GUARD_CALLS = ("$(WRITE_GUARD)", "${WRITE_GUARD}")


def check(root):
    found = []
    # The template's check_W already reports what the walk warns about.
    for relpath, text in check_structure.walk_makefiles(root, lambda m: None):
        for rule in check_structure.make_target_rules(text):
            first = (rule.first_recipe or "").split()
            if not first or first[0] not in _GUARD_CALLS or rule.help is None:
                continue
            labels = check_structure.parse_effect_labels(rule.help)[0]
            if labels is not None and "write" not in labels:
                found.append((
                    "error",
                    "%s:%d: `%s` opens its recipe with $(WRITE_GUARD) but is "
                    "labelled [%s]; label it [write]"
                    % (relpath, rule.lineno, rule.target, ",".join(labels)),
                ))
    return found
'''
_PLANTED = "\nplanted: ## [read] A target that is really a writer\n\t$(WRITE_GUARD)\n"


def _git(cwd, *argv):
    r = subprocess.run(("git",) + argv, cwd=str(cwd), capture_output=True, text=True)
    assert r.returncode == 0, "git %s failed:\n%s%s" % (
        " ".join(argv),
        r.stdout,
        r.stderr,
    )
    return r.stdout


def _label(root, name, body):
    d = root / name
    d.mkdir()
    for fname, kind in (("README.md", "readme"), ("AGENT.md", "rules")):
        (d / fname).write_text(
            _FM % (name, kind, body, "%s-%s" % (name, kind), name, body),
            encoding="utf-8",
        )
    os.symlink("AGENT.md", str(d / "CLAUDE.md"))


def _gate(project):
    r = subprocess.run(
        [sys.executable, _CS],
        cwd=str(project),
        capture_output=True,
        text=True,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
    )
    return r.returncode, r.stdout


@pytest.fixture()
def cycle(tmp_path, monkeypatch):
    """(template, project, update): a clone of keel, a toy generated from it and
    committed, and a callable that runs `copier update` the way the CLI does."""
    work = tmp_path / "work"
    work.mkdir()
    for var, value in hermetic_git.git_env_vars(work).items():
        monkeypatch.setenv(var, value)
    monkeypatch.setenv("COPIER_CACHE_DIR", str(work / "copier-cache"))
    template = hermetic_git.clone_including_worktree(_ROOT, work / "template", work)
    generated_epoch, _ = doc_stamps.epoch_after_newest_stamp(template, days=1)
    update_epoch, _ = doc_stamps.epoch_after_newest_stamp(template, days=2)
    project = work / "toy"
    with plumbum.local.env(SOURCE_DATE_EPOCH=str(generated_epoch)):
        copier.run_copy(
            str(template),
            str(project),
            data={"project_name": "toy", "frontend_stack": "none"},
            defaults=True,
            vcs_ref="HEAD",
            unsafe=True,
            quiet=True,
        )
    _git(project, "init", "--quiet", "-b", "main")
    _git(project, "add", "-A")
    _git(project, "commit", "--quiet", "-m", "generated")

    def update():
        # The CLI, not run_update: what a project owner sees is its output.
        return subprocess.run(
            [sys.executable, "-m", "copier", "update", "--trust", "--defaults"]
            + ["--vcs-ref", "HEAD", "--quiet"],
            cwd=str(project),
            capture_output=True,
            text=True,
            env=dict(os.environ, SOURCE_DATE_EPOCH=str(update_epoch)),
        )

    return template, project, update


def _template_edits(template, rel, old, new):
    path = template / rel
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, old
    path.write_text(text.replace(old, new), encoding="utf-8")
    _git(template, "commit", "--quiet", "-am", "template changes %s" % rel)
    return path.read_bytes()


def _template_edits_check_structure(template, old, new):
    return _template_edits(template, _CS, old, new)


def _both_sides_edit(template, project, rel, old):
    """The project and then the template each edit the one line *old* of
    *rel*, differently, so an update conflicts there."""
    path = project / rel
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, old
    path.write_text(text.replace(old, old.rstrip() + "  # mine\n"), encoding="utf-8")
    _git(project, "commit", "--quiet", "-am", "the project edits %s" % rel)
    _template_edits(template, rel, old, old.rstrip() + "  # theirs\n")


def _assert_no_conflicted_stamp_rewritten(project):
    unmerged_docs = {
        line.split("\t", 1)[1]
        for line in _git(project, "ls-files", "-u").splitlines()
        if line.endswith(".md")
    }
    for rel in unmerged_docs:
        ours = _git(project, "show", ":2:%s" % rel)
        text = (project / rel).read_text(encoding="utf-8")
        stamp = [ln for ln in ours.splitlines() if ln.startswith("updated:")][:1]
        assert not stamp or stamp[0] in text, rel


def test_project_check_survives_copier_update(cycle):
    template, project, update = cycle
    _label(project, "checks", "The project's own structure checks.")
    (project / "checks" / "guarded.py").write_text(_GUARDED, encoding="utf-8")
    manifest_path = project / "config" / "project.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["structure"]["extra_toplevel"] = ["checks"]
    manifest["structure"]["project_checks"] = "checks"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    _git(project, "add", "-A")
    _git(project, "commit", "--quiet", "-m", "a project check")
    base_code, base_out = _gate(project)
    assert "checks/guarded.py" not in base_out, base_out

    new_bytes = _template_edits_check_structure(
        template, "_OWN_ROOT = ROOT\n", "_OWN_ROOT = ROOT  # the template moved\n"
    )
    proc = update()

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _git(project, "ls-files", "-u") == ""
    cs_bytes = (project / _CS).read_bytes()
    assert _OPEN.encode() not in cs_bytes
    assert cs_bytes == new_bytes

    makefile = project / "Makefile"
    clean = makefile.read_text(encoding="utf-8")
    makefile.write_text(clean + _PLANTED, encoding="utf-8")
    code, out = _gate(project)
    assert code == 1
    assert [ln for ln in out.splitlines() if "checks/guarded.py" in ln] == [
        "ERROR checks/guarded.py: Makefile:%d: `planted` opens its recipe with "
        "$(WRITE_GUARD) but is labelled [read]; label it [write]"
        % (clean.count("\n") + 2)
    ], out
    makefile.write_text(clean, encoding="utf-8")
    code, out = _gate(project)
    assert "checks/guarded.py" not in out
    assert code == base_code, out


def test_update_over_conflicted_check_structure_finishes_and_leaves_it(cycle):
    # No copier job imports or reads the gate, so its conflict is the
    # operator's to merge like any other file's, and stops no migration.
    template, project, update = cycle
    _both_sides_edit(template, project, _CS, "_OWN_ROOT = ROOT\n")

    proc = update()
    out = proc.stdout + proc.stderr

    assert proc.returncode == 0, out
    assert _CS in _git(project, "ls-files", "-u")
    assert conflict_guard.conflict_lines((project / _CS).read_text(encoding="utf-8")), (
        _CS
    )
    assert conflict_guard.read_refusals(out) == [], out
    assert "Traceback" not in out and "SyntaxError" not in out, out
    _assert_no_conflicted_stamp_rewritten(project)


def test_update_over_a_conflicted_module_the_jobs_import_stops_cleanly(cycle):
    template, project, update = cycle
    rel = "scripts/child_env.py"
    _both_sides_edit(
        template, project, rel, 'PROJECT_READS = ("config/project.json",)\n'
    )

    proc = update()
    out = proc.stdout + proc.stderr

    assert proc.returncode != 0, out
    assert rel in _git(project, "ls-files", "-u")
    assert "Traceback" not in out and "SyntaxError" not in out, out
    found = conflict_guard.read_refusals(proc.stderr)
    assert len(found) == 1, out
    _job, items, rerun = found[0]
    assert [path for path, _line in items] == [rel], out
    lines = (project / rel).read_text(encoding="utf-8").split("\n")
    assert conflict_guard.marker(lines[items[0][1] - 1], conflict_guard.OPEN)
    assert rerun == conflict_guard.finish_rerun(sys.executable), out
    _assert_no_conflicted_stamp_rewritten(project)


@pytest.mark.parametrize("name", ["config/project.json", "config/project.json.jinja"])
def test_the_template_never_ships_the_key(name):
    # A key shipped beside `extra_toplevel`, even as null, conflicted on update
    # with every project that had declared a directory there (ADR-K-0014). A
    # template fact, so it lives here and is pruned from generated projects,
    # where a project that adopts the extension point declares the key.
    text = (_ROOT / name).read_text(encoding="utf-8")
    assert '"project_checks"' not in text, name
