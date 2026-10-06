"""
title: Integration — the downstream audit judges a generated project and writes nothing
kind: tests
layer: n/a
summary: `scripts/audit_project.py` run against projects copier generates from this template. A project generated from the working tree audits with no letter error and no config arrival; the same project with four planted defects (an undeclared top-level directory, an unlabelled make target, a bare subprocess call, an unstamped doc edit) reports exactly those four under B, W, X and freshness, and its whole tree — `.git` included, bytes and modes, plus `.git/index`'s mtime — is identical after two audits whose JSON is byte-identical. A project generated at 7f0a68b, before the downstream-feedback campaign, reports the W and X errors and the config keys the update brings, each W/X finding labelled template-unedited (template-rendered in the manifest); every template-unedited error is resolved by the update, and the one owed error is the manifest's `effect_proof_skip` naming `audit-project`, the audit's kept blind spot. A planted defect in an edited file is owed, with an exact origin. A project generated at a70a7b5, before slice C2-1 moved git's repository variables out of `child_env.names`, owes no X error whether or not it added its own allowlist name: the audit merges that list item by item, as copier's line-level merge does. A generated project's own `make audit-project` is a stub that names the template checkout. Keel-only: copier's `tests/integration/test_copier_*.py` glob prunes it.
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
yaml = optional_deps.importorskip("yaml", extra="template")
# copier runs `_tasks` through plumbum, whose `local.env` is a snapshot taken at
# import, so the generation date is pinned through it (see test_copier_update.py).
plumbum = optional_deps.importorskip("plumbum", extra="template")

_ROOT = Path(__file__).resolve().parents[2]
_AUDIT = _ROOT / "scripts" / "audit_project.py"
# The last commit before the downstream-feedback campaign: bedrock-platform was
# generated from it, so it is the old revision whose update the audit previews.
_PRE_CAMPAIGN = "7f0a68b"
# The last commit before slice C2-1 moved git's repository variables out of
# child_env.names into child_env.repo_context_names.
_PRE_C2_1 = "a70a7b5"
_ANSWERS = {"project_name": "demo_proj", "frontend_stack": "none"}

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (_ROOT / "copier.yml").is_file(),
        reason="not a copier template — this is a generated project",
    ),
]


def _git(cwd, *argv, env=None):
    r = subprocess.run(
        ("git",) + argv, cwd=str(cwd), env=env, capture_output=True, text=True
    )
    assert r.returncode == 0, "git %s: %s%s" % (" ".join(argv), r.stdout, r.stderr)
    return r.stdout


def _tree(root):
    """Every path under *root*, `.git` included, relative -> (mode, bytes or the
    link target), plus the mtime_ns of `.git/index`. A stat refresh rewrites the
    index with the same entries, so the mtime is what catches it when the bytes
    alone might not."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(str(root), followlinks=False):
        dirnames.sort()
        for name in sorted(dirnames + filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, str(root))
            st = os.lstat(full)
            if os.path.islink(full):
                out[rel] = (st.st_mode, b"-> " + os.readlink(full).encode())
            elif os.path.isfile(full):
                with open(full, "rb") as fh:
                    out[rel] = (st.st_mode, fh.read())
            else:
                out[rel] = (st.st_mode, None)
    index = os.path.join(str(root), ".git", "index")
    out["<index mtime_ns>"] = os.stat(index).st_mtime_ns
    return out


def _porcelain(root, env):
    return subprocess.run(
        ["git", "--no-optional-locks", "status", "--porcelain=v1", "-z"],
        cwd=str(root),
        env=env,
        capture_output=True,
    ).stdout


def _audit(dest, today, json_out=True):
    """Run the template's audit as a CLI, the way `make audit-project` does."""
    argv = [sys.executable, str(_AUDIT), str(dest), "--today", today.isoformat()]
    if json_out:
        argv.append("--json")
    return subprocess.run(argv, cwd=str(_ROOT), capture_output=True, text=True)


def _errors(report, group):
    return [f for f in report["groups"][group] if f["tier"] == "error"]


def _letters(report):
    return report["summary"]["checks_run"]


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    """A project generated from this template, committed on its generation day.

    Yields (project, day, env). The template is `_ROOT` itself: the audit judges
    it against its own working tree, so DEST's `_commit` must resolve in it for
    the 3-way merge to have a base. On a dirty checkout copier commits the tree
    afresh and the base does not resolve; that path is the 2-way fallback the
    unit tests hold."""
    work = tmp_path_factory.mktemp("copier_audit")
    mp = pytest.MonkeyPatch()
    for var, value in hermetic_git.git_env_vars(work).items():
        mp.setenv(var, value)
    mp.setenv("COPIER_CACHE_DIR", str(work / "copier-cache"))
    try:
        epoch, day = doc_stamps.epoch_after_newest_stamp(_ROOT)
        project = work / "proj"
        with plumbum.local.env(SOURCE_DATE_EPOCH=str(epoch)):
            copier.run_copy(
                str(_ROOT),
                str(project),
                data=_ANSWERS,
                defaults=True,
                vcs_ref="HEAD",
                unsafe=True,
                quiet=True,
            )
        env = hermetic_git.git_env(work)
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = "@%d +0000" % epoch
        for argv in (
            ["init", "-q", "-b", "main"],
            ["add", "-A"],
            ["commit", "-qm", "g"],
        ):
            _git(project, *argv, env=env)
        yield project, day, env
    finally:
        mp.undo()


def test_a_project_generated_from_the_working_tree_audits_clean(generated):
    """(a) What the template generates today passes the template's gates today:
    no letter error, no config key the update would add or change, nothing
    stale, and the keel-only doer and its roster row did not ship."""
    project, day, _env = generated
    r = _audit(project, day)
    assert r.returncode == 0, r.stdout + r.stderr
    report = json.loads(r.stdout)
    assert len(_letters(report)) == 24
    assert report["summary"]["files_seen"] > 0
    assert {g: _errors(report, g) for g in _letters(report) if _errors(report, g)} == {}
    moving = [
        f for f in report["groups"]["config"] if f["kind"] in ("arrives", "updates")
    ]
    assert moving == [], moving
    assert report["groups"]["freshness"] == []

    assert not (project / "scripts" / "audit_project.py").exists()
    assert "audit_project.py" not in (project / "scripts" / "README.md").read_text()
    own = subprocess.run(
        [sys.executable, "scripts/check_structure.py"],
        cwd=str(project),
        capture_output=True,
        text=True,
    )
    assert own.returncode == 0, own.stdout + own.stderr


def test_four_planted_defects_audit_as_exactly_those_four_and_the_tree_is_byte_identical(
    generated, tmp_path
):
    """(b) Each plant is one defect a slice of the campaign gates, and the audit
    reports each under its letter with the check's own message. The proof of
    read-only is the whole tree, `.git` and the index's mtime included: porcelain
    alone cannot see an index rewrite."""
    project, day, env = generated
    dest = tmp_path / "planted"
    _git(tmp_path, "clone", "-q", "--no-hardlinks", str(project), str(dest), env=env)

    (dest / "zzz_undeclared").mkdir()
    (dest / "zzz_undeclared" / "data.txt").write_text("x\n")
    with open(dest / "Makefile", "a") as fh:
        fh.write("\nplanted: ## Does a thing\n\t@true\n")
    script = dest / "scripts" / "check_generic.py"
    with open(script, "a") as fh:
        fh.write(
            "\n\ndef _planted():\n"
            "    import subprocess\n\n"
            '    subprocess.run(["true"], check=True)\n'
        )
    doc = dest / "docs" / "guides" / "idempotency.md"
    with open(doc, "a") as fh:
        fh.write("\nA planted sentence nobody restamped.\n")

    # Not a defect: an unmodified tracked file whose mtime moved, so a stat
    # refresh is due. `git diff HEAD` or a plain `git status` would now rewrite
    # the index; a read-only reader must not.
    readme = dest / "README.md"
    os.utime(readme, (readme.stat().st_atime, readme.stat().st_mtime + 7))

    before, porcelain = _tree(dest), _porcelain(dest, env)
    later = day.fromordinal(day.toordinal() + 1)
    first, second = _audit(dest, later), _audit(dest, later)
    assert _tree(dest) == before, "the audit changed DEST's tree"
    assert _porcelain(dest, env) == porcelain
    assert first.stdout == second.stdout, "two --json runs differ"
    assert first.returncode == 1, first.stdout + first.stderr

    report = json.loads(first.stdout)
    errors = {g: _errors(report, g) for g in _letters(report) if _errors(report, g)}
    assert sorted(errors) == ["B", "W", "X"], errors
    assert [len(errors[g]) for g in ("B", "W", "X")] == [1, 1, 1], errors
    assert "zzz_undeclared" in errors["B"][0]["message"]
    assert "planted" in errors["W"][0]["message"]
    assert "scripts/check_generic.py" in errors["X"][0]["message"]
    # The generated project's `_commit` resolves here only when the template
    # tree was clean at generation; every origin follows from that, exactly
    # (no base -> every origin is unknown, the doer's documented 2-way path).
    resolved = report["base"]["resolved"]
    assert errors["B"][0]["origin"] == ("project" if resolved else "unknown")
    edited = "template-edited" if resolved else "unknown"
    assert errors["X"][0]["origin"] == edited
    assert errors["W"][0]["origin"] == edited
    assert all("resolved_by" not in f for g in errors for f in errors[g])
    assert report["summary"]["errors"] == 3, report["summary"]
    assert report["summary"]["resolved_by_update"] == 0, report["summary"]

    fresh = report["groups"]["freshness"]
    assert [f["path"] for f in fresh] == ["docs/guides/idempotency.md"], fresh
    assert "make restamp-docs" in fresh[0]["message"]
    assert fresh[0]["resolved_by"].startswith("copier update")
    assert [f["path"] for f in report["groups"]["restamp"]] == [
        "docs/guides/idempotency.md"
    ]


def test_a_project_whose_child_env_allowlists_a_repository_variable_owes_an_x_error(
    generated, tmp_path
):
    """A project that kept GIT_DIR in child_env.names (the template shipped it
    there before slice C2-1) is told, by the check's own message, which key
    marks it and what the fix is. The project's edit survives the merge, so
    the error is owed, not resolved by the update."""
    project, day, env = generated
    dest = tmp_path / "edited"
    _git(tmp_path, "clone", "-q", "--no-hardlinks", str(project), str(dest), env=env)
    r = _audit(dest, day)
    assert _errors(json.loads(r.stdout), "X") == [], r.stdout  # not vacuous

    manifest_path = dest / "config" / "project.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    names = manifest["child_env"]["names"]
    assert "GIT_DIR" not in names, "the template itself ships GIT_DIR in names"
    names.append("GIT_DIR")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    _git(dest, "commit", "-qam", "allowlist GIT_DIR", env=env)

    r = _audit(dest, day)
    assert r.returncode == 1, r.stdout + r.stderr
    report = json.loads(r.stdout)
    x = _errors(report, "X")
    assert len(x) == 1, x
    message = x[0]["message"]
    assert message.startswith("config/project.json: child_env.names lists GIT_DIR")
    assert "child_env.repo_context_names" in message, message
    assert "build_child_env(repo_context=True)" in message, message
    # The manifest is rendered from its `.jinja` twin, so with a base its origin
    # says so (audit_project.origin_of); without one every origin is unknown.
    resolved = report["base"]["resolved"]
    assert x[0]["origin"] == ("template-rendered" if resolved else "unknown"), x
    assert "resolved_by" not in x[0], x


def _generated_at(tmp_path_factory, ref):
    """A project generated at *ref* from a clone of this template, committed;
    yields (project, env). The clone is a plain `git clone`: the old revision is
    history, so the working tree does not matter, and keel is never written."""
    work = tmp_path_factory.mktemp("copier_audit_" + ref)
    mp = pytest.MonkeyPatch()
    for var, value in hermetic_git.git_env_vars(work).items():
        mp.setenv(var, value)
    mp.setenv("COPIER_CACHE_DIR", str(work / "copier-cache"))
    try:
        template = work / "template"
        _git(work, "clone", "-q", "--no-hardlinks", str(_ROOT), str(template))
        project = work / "proj"
        copier.run_copy(
            str(template),
            str(project),
            data=_ANSWERS,
            defaults=True,
            vcs_ref=ref,
            unsafe=True,
            quiet=True,
        )
        env = hermetic_git.git_env(work)
        for argv in (
            ["init", "-q", "-b", "main"],
            ["add", "-A"],
            ["commit", "-qm", "g"],
        ):
            _git(project, *argv, env=env)
        yield project, env
    finally:
        mp.undo()


@pytest.fixture(scope="module")
def pre_campaign(tmp_path_factory):
    """A project generated at 7f0a68b, before the downstream-feedback campaign."""
    yield from _generated_at(tmp_path_factory, _PRE_CAMPAIGN)


@pytest.fixture(scope="module")
def pre_c2_1(tmp_path_factory):
    """A project generated at a70a7b5, whose child_env.names still lists GIT_DIR
    and the other repository variables slice C2-1 moved out."""
    yield from _generated_at(tmp_path_factory, _PRE_C2_1)


def test_a_project_from_7f0a68b_audits_with_the_w_and_x_findings_the_update_brings(
    pre_campaign,
):
    """(c) The audit previews an update: the old project has no effect labels and
    no child allowlist, so W and X are red, and the config blocks that fix them
    arrive with the update. B stays empty, because every top-level directory of
    a 7f0a68b project is a taxonomy row. Each W/X finding sits in a file the
    project never edited, which is the evidence that the update itself replaces
    it, or in the manifest copier renders from its twin.

    Every letter error in a template-unedited file is reported as resolved by
    the update and is not owed. One W error is the audit's own blind spot, kept
    visible rather than special-cased: the merged manifest's `effect_proof_skip`
    names `audit-project`, which the old Makefile, judged as it stands, does not
    define; the update brings both. Its origin says the manifest is rendered,
    so it is owed and the exit stays 1."""
    project, env = pre_campaign
    answers = yaml.safe_load((project / ".copier-answers.yml").read_text())
    assert _PRE_CAMPAIGN in str(answers["_commit"])
    before = _tree(project)
    today = doc_stamps.newest_stamp(_ROOT)
    r = _audit(project, today)
    assert _tree(project) == before, "the audit changed DEST's tree"
    assert r.returncode == 1, r.stdout + r.stderr
    report = json.loads(r.stdout)
    assert report["base"]["resolved"], "7f0a68b must resolve in the template"

    arrived = {
        f["key"]
        for f in report["groups"]["config"]
        if f["kind"] == "arrives" and f.get("file") == "config/project.json"
    }
    for key in ("make_targets", "child_env", "models.credential_env"):
        assert key in arrived, (key, sorted(arrived))
    assert _errors(report, "W") and _errors(report, "X")
    assert _errors(report, "B") == []
    # The manifest is rendered from its twin, so its findings say so; every
    # other W/X finding is in a verbatim file the project never touched.
    origins = {
        f["message"].split(":", 1)[0]: f["origin"]
        for g in ("W", "X")
        for f in report["groups"][g]
    }
    assert "template-unedited" in origins.values(), origins
    for path, origin in origins.items():
        twin = path == "config/project.json"
        assert origin == ("template-rendered" if twin else "template-unedited"), path

    letter_errors = [f for g in _letters(report) for f in _errors(report, g)]
    unedited = [f for f in letter_errors if f["origin"] == "template-unedited"]
    assert unedited, "a 7f0a68b project has errors the update replaces"
    for f in unedited:
        assert f["resolved_by"].startswith("copier update"), f
    owed = [f for f in letter_errors if "resolved_by" not in f]
    assert len(owed) == 1, owed
    assert owed[0]["origin"] == "template-rendered", owed
    assert owed[0]["message"].startswith("config/project.json"), owed
    assert "effect_proof_skip" in owed[0]["message"], owed
    assert "audit-project" in owed[0]["message"], owed
    assert report["summary"]["errors"] == 1, report["summary"]
    assert report["summary"]["resolved_by_update"] == len(unedited)


@pytest.mark.parametrize("customised", [False, True], ids=["as-rendered", "own-name"])
def test_a_pre_c2_1_project_owes_no_x_error_for_the_moved_git_names(
    pre_c2_1, tmp_path, customised
):
    """The update moves GIT_DIR and its siblings out of child_env.names. A project
    that added its own allowlist name edited the same list, and copier's
    line-level merge keeps both edits, so the audit must judge the merged list:
    no X error is owed, and the config entry is a merge, not a conflict. The
    as-rendered project is the control (the template's value simply replaces
    its own)."""
    project, env = pre_c2_1
    dest = tmp_path / "dest"
    _git(tmp_path, "clone", "-q", "--no-hardlinks", str(project), str(dest), env=env)
    manifest_path = dest / "config" / "project.json"
    text = manifest_path.read_text(encoding="utf-8")
    assert '"GIT_DIR",' in text, "the pre-C2-1 template must list GIT_DIR in names"
    if customised:
        # One line, where a person adds a name, so the file keeps its layout.
        assert text.count('      "HOME",\n') == 1
        text = text.replace('      "HOME",\n', '      "HOME",\n      "MY_TOOL_HOME",\n')
        manifest_path.write_text(text, encoding="utf-8")
        _git(dest, "commit", "-qam", "allowlist MY_TOOL_HOME", env=env)

    r = _audit(dest, doc_stamps.newest_stamp(_ROOT))
    report = json.loads(r.stdout)
    assert report["base"]["resolved"], "a70a7b5 must resolve in the template"
    assert _errors(report, "X") == [], report["groups"]["X"]
    names = [
        f
        for f in report["groups"]["config"]
        if f.get("file") == "config/project.json" and f["key"] == "child_env.names"
    ]
    assert len(names) == 1, report["groups"]["config"]
    assert names[0]["kind"] == ("merges" if customised else "updates"), names
    assert names[0]["tier"] == "info", names
    if customised:
        assert "MY_TOOL_HOME" in names[0]["message"], names
        assert "GIT_DIR" in names[0]["message"], names


def test_the_shipped_audit_target_points_back_at_the_template(generated):
    """A generated project keeps the target but not the doer, so its stub must
    say where the doer is rather than fail obscurely; and the effect sweep must
    skip it, since it needs DEST."""
    project, _day, _env = generated
    # The printed command runs under `make -C <template>`, so DEST is absolute:
    # the one asked for, else this project.
    for argv, dest in (
        (["audit-project", "DEST=../sibling"], project.parent / "sibling"),
        (["audit-project"], project),
    ):
        r = subprocess.run(
            ["make", "-s"] + argv, cwd=str(project), capture_output=True, text=True
        )
        assert r.returncode == 2, r.stdout + r.stderr
        assert "make -C" in r.stdout and "_src_path" in r.stdout, r.stdout
        assert r.stdout.rstrip().endswith("DEST=%s" % os.path.abspath(str(dest))), (
            r.stdout
        )
    manifest = json.loads((project / "config" / "project.json").read_text())
    assert "audit-project" in manifest["make_targets"]["effect_proof_skip"]
    own = subprocess.run(
        [sys.executable, "scripts/check_structure.py"],
        cwd=str(project),
        capture_output=True,
        text=True,
    )
    assert not [ln for ln in own.stdout.splitlines() if "audit-project" in ln], (
        own.stdout
    )
