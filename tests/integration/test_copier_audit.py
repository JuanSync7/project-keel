"""
title: Integration — the downstream audit judges a generated project and writes nothing
kind: tests
layer: n/a
summary: `scripts/audit_project.py` run against projects copier generates from this template. The audit judges the tree a real `copier update` leaves, built in a scratch copy; the parity test runs that update itself, on an independent clone of each old project against `hermetic_git.clone_including_worktree`, and holds the audit's owed and warned letter findings equal to `check_structure.py --root` on the result; for a 7f0a68b project whose own `.PHONY` edit makes copier conflict on the Makefile, the result is resolved both ways by git's `merge-file --ours/--theirs` over copier's index stages, and the audit's judged findings equal what both resolutions have outside the conflicted file, with nothing owed; for a 7f0a68b project that edited its own scripts/check_structure.py, copier conflicts on it and the restamp migration refuses in the real update and in the audit alike, which names the migration under not checked, exits on the findings (none owed) and never 2. A project generated from the working tree audits with no letter error, no config arrival and no conflict; the same project with four planted defects (an undeclared top-level directory, an unlabelled make target, a bare subprocess call, an unstamped doc edit) reports exactly those four under B, W, X and freshness, and its whole tree — `.git` included, bytes and modes, plus `.git/index`'s mtime — is identical after two audits whose JSON is byte-identical, with no `keel-audit-*` scratch left behind. A project generated at 7f0a68b, before the downstream-feedback campaign, owes nothing: every W/X error it has today is absent from the tree the update leaves, and the config keys the update brings are reported. A project generated at a70a7b5, before slice CMP-2.S1 moved git's repository variables out of `child_env.names`, owes no X error whether or not it added its own allowlist name, and the config group calls that list an update or a merge from copier's own merge. A project generated at 29e45f0, before slice CMP-2.S2, receives `child_env.credentialed_values` as an info arrival with the template default `{}` and owes no X error. A project generated at 7dbcc0c, before slice CMP-3.S4, that recorded its own `child_env.credentialed_values` and `prefixes` keeps both through a real update with nothing unmerged, and its audit owes no X error. The template checkout's index is never refreshed by an audit. A generated project's own `make audit-project` is a stub that names the template checkout. Keel-only: copier's `tests/integration/test_copier_*.py` glob prunes it.
"""

import json
import os
import shutil
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
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure  # noqa: E402

# The last commit before the downstream-feedback campaign: bedrock-platform was
# generated from it, so it is the old revision whose update the audit previews.
_PRE_CAMPAIGN = "7f0a68b"
# The last commit before slice CMP-2.S1 moved git's repository variables out of
# child_env.names into child_env.repo_context_names.
_PRE_C2_1 = "a70a7b5"
# The last commit before slice CMP-2.S2 added child_env.credentialed_values.
_PRE_C2_2 = "29e45f0"
# The last commit before slice CMP-3.S4 added four child_env keys beside the
# credentialed_values line a project customises.
_PRE_C3_4 = "7dbcc0c"
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


def _audit(dest, today, json_out=True, tmpdir=None, audit=_AUDIT):
    """Run the template's audit as a CLI, the way `make audit-project` does;
    *tmpdir* is the system temporary directory it sees, where its scratch
    copy lives."""
    argv = [sys.executable, str(audit), str(dest), "--today", today.isoformat()]
    if json_out:
        argv.append("--json")
    env = dict(os.environ)
    if tmpdir is not None:
        env["TMPDIR"] = str(tmpdir)
    return subprocess.run(
        argv, cwd=str(audit.parents[1]), env=env, capture_output=True, text=True
    )


def _scratch_left(tmpdir):
    return sorted(p.name for p in Path(tmpdir).iterdir() if "keel-audit-" in p.name)


def _predicted(report):
    """The audit's letter findings in the tree the update leaves, as
    (tier, message): those it neither resolves nor leaves unjudged."""
    return {
        (f["tier"], f["message"])
        for g in _letters(report)
        for f in report["groups"][g]
        if "resolved_by" not in f and "unjudged" not in f
    }


def _gate(root):
    """`check_structure.py --root` on *root*, as a set of (tier, message)."""
    r = subprocess.run(
        [sys.executable, str(_ROOT / "scripts" / "check_structure.py"), "--root"]
        + [str(root)],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
    )
    assert r.returncode in (0, 1), r.stdout + r.stderr
    found = set()
    for line in r.stdout.splitlines():
        if line.startswith("WARN  "):
            found.add(("warning", line[len("WARN  ") :]))
        elif line.startswith("ERROR "):
            found.add(("error", line[len("ERROR ") :]))
    return found


def _errors(report, group):
    return [f for f in report["groups"][group] if f["tier"] == "error"]


def _owed(report, group):
    """The errors in `group` the project still owes after the update: not ones
    the update resolves, and not ones in a file copier leaves conflicted."""
    return [
        f
        for f in _errors(report, group)
        if not f.get("resolved_by") and not f.get("unjudged")
    ]


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


def test_a_project_generated_from_the_working_tree_audits_clean(generated, tmp_path):
    """(a) What the template generates today passes the template's gates today:
    no letter error, no config key the update would add or change, nothing
    stale, and the keel-only doer and its roster row did not ship."""
    project, day, _env = generated
    r = _audit(project, day, tmpdir=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    report = json.loads(r.stdout)
    # Every letter the template's gate registers runs, read from the registry
    # rather than counted here, so a new letter does not need this line edited.
    assert _letters(report) == [letter for letter, _fn in check_structure.CHECKS]
    assert report["summary"]["conflicts"] == 0, report["groups"]["conflict"]
    assert _scratch_left(tmp_path) == []
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
    systmp = tmp_path / "systmp"
    systmp.mkdir()
    first, second = (
        _audit(dest, later, tmpdir=systmp),
        _audit(dest, later, tmpdir=systmp),
    )
    assert _scratch_left(systmp) == []
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
    assert report["summary"]["conflicts"] == 0, report["groups"]["conflict"]

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
    there before slice CMP-2.S1) is told, by the check's own message, which key
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
    and the other repository variables slice CMP-2.S1 moved out."""
    yield from _generated_at(tmp_path_factory, _PRE_C2_1)


@pytest.fixture(scope="module")
def pre_c2_2(tmp_path_factory):
    """A project generated at 29e45f0, whose child_env has no credentialed_values."""
    yield from _generated_at(tmp_path_factory, _PRE_C2_2)


@pytest.fixture(scope="module")
def pre_c3_4(tmp_path_factory):
    """A project generated at 7dbcc0c, whose child_env ends in credentialed_values."""
    yield from _generated_at(tmp_path_factory, _PRE_C3_4)


def _customise(dest, env):
    """Add the project's own allowlist name to a pre-CMP-2.S1 manifest, on its own
    line where a person adds one, so the file keeps its layout; committed."""
    manifest_path = dest / "config" / "project.json"
    text = manifest_path.read_text(encoding="utf-8")
    assert text.count('      "HOME",\n') == 1
    text = text.replace('      "HOME",\n', '      "HOME",\n      "MY_TOOL_HOME",\n')
    manifest_path.write_text(text, encoding="utf-8")
    _git(dest, "commit", "-qam", "allowlist MY_TOOL_HOME", env=env)


def _edit_phony(dest, env):
    """Add the project's own target to its Makefile, naming it on the `.PHONY`
    line the template's update also changes, as a project adds one: copier
    leaves the Makefile conflicted. Committed."""
    path = dest / "Makefile"
    text = path.read_text(encoding="utf-8")
    assert text.count(".PHONY: help ") == 1
    text = text.replace(".PHONY: help ", ".PHONY: help mytarget ", 1)
    text += "\nmytarget: ## [local] The project's own target\n\t@echo hi\n"
    path.write_text(text, encoding="utf-8")
    _git(dest, "commit", "-qam", "the project's own target", env=env)


def _edit_gate(dest, env):
    """Rewrite the `summary:` line of the project's own scripts/check_structure.py,
    a line every later template commit also changes, as bedrock-platform did:
    copier leaves the file conflicted, and the restamp migration, which imports
    it, refuses. Committed."""
    path = dest / "scripts" / "check_structure.py"
    lines = path.read_text(encoding="utf-8").splitlines(True)
    assert lines[3].startswith("summary: "), lines[3]
    lines[3] = "summary: The project's own structure gate, edited for its own checks.\n"
    path.write_text("".join(lines), encoding="utf-8")
    _git(dest, "commit", "-qam", "own gate summary", env=env)


_CUSTOMISE = {"own-name": _customise, "phony": _edit_phony, "gate": _edit_gate}


def _resolved_gate(upd, conflicted, side, env):
    """`check_structure.py --root` on the real update with every conflict hunk
    taken one way, rebuilt by git's own `merge-file --ours/--theirs` from the
    index stages copier records (1 base, 2 the project, 3 the template), not
    from the audit's reading of the markers."""
    for rel in conflicted:
        stages = []
        for n in (2, 1, 3):
            stage = upd.parent / ("stage%d" % n)
            r = subprocess.run(
                ["git", "show", ":%d:%s" % (n, rel)],
                cwd=str(upd),
                env=env,
                capture_output=True,
            )
            stage.write_bytes(r.stdout if r.returncode == 0 else b"")
            stages.append(str(stage))
        r = subprocess.run(
            ["git", "merge-file", "-p", side] + stages, env=env, capture_output=True
        )
        assert r.returncode == 0, r.stderr
        (upd / rel).write_bytes(r.stdout)
    return _gate(upd)


def _real_update(dest, work, day, env):
    """What a real `copier update` leaves: an independent clone of *dest*
    updated in-process against `clone_including_worktree(_ROOT)` (not the
    audit's own snapshot), on *day*. Returns (the updated clone, the paths it
    leaves unmerged, the failed task's CalledProcessError or None): an `after`
    migration that refuses stops copier there, and the tree it leaves is still
    the one to compare."""
    template = work / "template"
    hermetic_git.clone_including_worktree(_ROOT, template, work)
    upd = work / "updated"
    _git(work, "clone", "-q", "--no-hardlinks", str(dest), str(upd), env=env)
    answers_path = upd / ".copier-answers.yml"
    answers = yaml.safe_load(answers_path.read_text(encoding="utf-8"))
    answers["_src_path"] = str(template)
    answers_path.write_text(yaml.safe_dump(answers, sort_keys=True), encoding="utf-8")
    _git(upd, "commit", "-qam", "point at the template clone", env=env)
    mp = pytest.MonkeyPatch()
    for var, value in hermetic_git.git_env_vars(work).items():
        mp.setenv(var, value)
    mp.setenv("COPIER_CACHE_DIR", str(work / "copier-cache"))
    failed = None
    try:
        with plumbum.local.env(SOURCE_DATE_EPOCH=str(doc_stamps.epoch_of(day))):
            copier.run_update(
                str(upd),
                defaults=True,
                overwrite=True,
                skip_answered=True,
                vcs_ref="HEAD",
                conflict="inline",
                unsafe=True,
                quiet=True,
            )
    except subprocess.CalledProcessError as exc:
        failed = exc
    finally:
        mp.undo()
    out = _git(upd, "ls-files", "-u", "-z", env=env)
    unmerged = sorted({e.split("\t", 1)[1] for e in out.split("\0") if "\t" in e})
    return upd, unmerged, failed


def _token(message):
    return message.split(None, 1)[0].split(":", 1)[0].rstrip("/")


@pytest.mark.parametrize(
    "fixture, customise",
    [
        ("pre_campaign", None),
        ("pre_campaign", "phony"),
        ("pre_c2_1", None),
        ("pre_c2_1", "own-name"),
        ("pre_c2_2", None),
        ("pre_campaign", "gate"),
    ],
    ids=[
        "7f0a68b",
        "7f0a68b-conflict",
        "a70a7b5-as-rendered",
        "a70a7b5-own-name",
        "29e45f0",
        "7f0a68b-edited-gate",
    ],
)
def test_predicted_findings_equal_check_structure_on_a_real_update(
    request, tmp_path, fixture, customise
):
    """The audit's prediction is the tree a real update leaves: its owed and
    warned letter findings equal what check_structure says about an
    independent clone after `copier update`, exactly. Every finding it calls
    resolved by the update is absent there. When copier leaves a file
    conflicted, the real update is judged twice, every hunk the project's way
    and every hunk the template's way: what the audit judges is what both
    have, outside the conflicted file (the 7f0a68b project that names its own
    target on the `.PHONY` line owes nothing; a pre-update Makefile beside the
    post-update manifest owed the `audit-project` entry). When a migration
    refuses over a file the update conflicts, the real update stops there
    too, and the audit names that migration under not checked instead of
    failing (the 7f0a68b project that edited its own check_structure.py)."""
    project, env = request.getfixturevalue(fixture)
    dest = tmp_path / "dest"
    _git(tmp_path, "clone", "-q", "--no-hardlinks", str(project), str(dest), env=env)
    if customise:
        _CUSTOMISE[customise](dest, env)
    day = doc_stamps.newest_stamp(_ROOT)
    systmp = tmp_path / "systmp"
    systmp.mkdir()
    r = _audit(dest, day, tmpdir=systmp)
    assert r.returncode in (0, 1), r.stdout + r.stderr
    report = json.loads(r.stdout)
    assert report["base"]["resolved"], "%s must resolve in the template" % fixture
    assert _scratch_left(systmp) == []

    work = tmp_path / "real"
    work.mkdir()
    upd, unmerged, failed = _real_update(dest, work, day, env)
    assert [f["path"] for f in report["groups"]["conflict"]] == unmerged
    refused = [i for i in report["not_checked"] if i["item"].startswith("migration ")]
    assert len(refused) == (failed is not None), (refused, failed)
    if failed is not None:
        job = refused[0]["item"].split()[1]
        assert "scripts/jobs/%s.py" % job in [str(w) for w in failed.cmd], failed
    if customise == "gate":
        # Non-vacuous: the restamp refuses over the conflicted gate, as it did
        # on bedrock-platform, and the audit says so instead of exit 2.
        assert unmerged == ["scripts/check_structure.py"], unmerged
        assert refused and refused[0]["item"].startswith("migration restamp_docs ")
        assert "scripts/check_structure.py" in refused[0]["reason"], refused
        assert report["summary"]["errors"] == 0, report["summary"]
    if customise == "phony":
        # Non-vacuous: the case this fixture exists for has a conflict.
        assert unmerged == ["Makefile"], unmerged
        assert report["summary"]["errors"] == 0, report["summary"]
    if unmerged:
        sides = [_resolved_gate(upd, unmerged, s, env) for s in ("--ours", "--theirs")]
        gate = {f for f in sides[0] & sides[1] if _token(f[1]) not in unmerged}
    else:
        sides = [_gate(upd)]
        gate = sides[0]
    predicted = _predicted(report)
    # Non-vacuous: the F warnings a generated project carries are on both sides.
    assert any(tier == "warning" for tier, _m in predicted), predicted
    assert predicted == gate, (sorted(predicted - gate), sorted(gate - predicted))
    resolved = {
        (f["tier"], f["message"])
        for g in _letters(report)
        for f in report["groups"][g]
        if "resolved_by" in f
    }
    seen = set().union(*sides)
    assert not resolved & seen, sorted(resolved & seen)


def test_a_project_from_7f0a68b_owes_nothing_the_update_fixes(pre_campaign, tmp_path):
    """(c) The audit previews an update: the old project has no effect labels and
    no child allowlist, so W and X are red as it stands, and the update brings
    the labels, the allowlist and the config blocks together. Judged as the one
    tree the update leaves, nothing is owed, including the manifest's
    `effect_proof_skip` entry naming `audit-project`, whose target arrives in
    the same update (a view that merged only the manifest owed it)."""
    project, env = pre_campaign
    answers = yaml.safe_load((project / ".copier-answers.yml").read_text())
    assert _PRE_CAMPAIGN in str(answers["_commit"])
    before, porcelain = _tree(project), _porcelain(project, env)
    today = doc_stamps.newest_stamp(_ROOT)
    systmp = tmp_path / "systmp"
    systmp.mkdir()
    r = _audit(project, today, tmpdir=systmp)
    again = _audit(project, today, tmpdir=systmp)
    assert _tree(project) == before, "the audit changed DEST's tree"
    assert _porcelain(project, env) == porcelain
    assert r.stdout == again.stdout, "two --json runs differ"
    assert _scratch_left(systmp) == []
    assert r.returncode == 0, r.stdout + r.stderr
    report = json.loads(r.stdout)
    assert report["base"]["resolved"], "7f0a68b must resolve in the template"

    letter_errors = [f for g in _letters(report) for f in _errors(report, g)]
    owed = [f for f in letter_errors if "resolved_by" not in f]
    assert owed == [], owed
    assert report["summary"]["errors"] == 0, report["summary"]
    assert report["summary"]["conflicts"] == 0, report["groups"]["conflict"]
    # Resolved: exactly the errors the project has as it stands that the tree
    # the update leaves does not (here: all of them, since none is owed).
    as_it_stands = {m for tier, m in _gate(project) if tier == "error"}
    assert as_it_stands, "a 7f0a68b project fails today's gates as it stands"
    assert {f["message"] for f in letter_errors} == as_it_stands
    assert report["summary"]["resolved_by_update"] == len(as_it_stands)
    assert _errors(report, "W") and _errors(report, "X")
    assert _errors(report, "B") == []

    arrived = {
        f["key"]
        for f in report["groups"]["config"]
        if f["kind"] == "arrives" and f.get("file") == "config/project.json"
    }
    for key in (
        "make_targets",
        "child_env",
        "models.credential_env",
        "structure",
        "adr",
    ):
        assert key in arrived, (key, sorted(arrived))
    # The update moves keel's ADRs into their own number space; this project
    # never edited one, so none is kept and nothing collides. As it stands it
    # holds ADRs and no `adr` block, which the update brings.
    ys = _errors(report, "Y")
    assert [f for f in ys if "resolved_by" not in f] == [], ys
    assert [f["message"].split(" -- ")[0] for f in ys] == [
        "config/project.json: adr is missing"
    ], ys
    assert report["groups"]["retired"] == [], report["groups"]["retired"]
    practices = [
        f
        for f in report["groups"]["config"]
        if f.get("file") == "config/practices.json"
        and f["kind"] in ("arrives", "updates")
    ]
    assert practices, report["groups"]["config"]


@pytest.mark.parametrize("customised", [False, True], ids=["as-rendered", "own-name"])
def test_a_pre_c2_1_project_owes_no_x_error_for_the_moved_git_names(
    pre_c2_1, tmp_path, customised
):
    """The update moves GIT_DIR and its siblings out of child_env.names. A project
    that added its own allowlist name edited the same list, and copier's
    line-level merge keeps both edits: no X error is owed, and the config group
    calls the list a merge, read from copier's own result. The as-rendered
    project is the control (the template's value simply replaces its own)."""
    project, env = pre_c2_1
    dest = tmp_path / "dest"
    _git(tmp_path, "clone", "-q", "--no-hardlinks", str(project), str(dest), env=env)
    text = (dest / "config" / "project.json").read_text(encoding="utf-8")
    assert '"GIT_DIR",' in text, "the pre-CMP-2.S1 template must list GIT_DIR in names"
    if customised:
        _customise(dest, env)

    systmp = tmp_path / "systmp"
    systmp.mkdir()
    r = _audit(dest, doc_stamps.newest_stamp(_ROOT), tmpdir=systmp)
    report = json.loads(r.stdout)
    assert report["base"]["resolved"], "a70a7b5 must resolve in the template"
    assert report["summary"]["conflicts"] == 0, report["groups"]["conflict"]
    assert _scratch_left(systmp) == []
    assert _owed(report, "X") == [], report["groups"]["X"]
    # The old tree lacks the key the update brings, so the error is real before
    # the update and gone after it: reported, but as resolved, never as owed.
    moved = [f for f in _errors(report, "X") if "repo_context_names" in f["message"]]
    assert moved and all(f["resolved_by"].startswith("copier update") for f in moved)
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


def test_a_pre_c2_2_project_receives_the_new_child_env_keys_as_arrivals_and_owes_no_x_error(
    pre_c2_2, tmp_path
):
    """credentialed_values and login_name_schemes are optional, so an older
    project owes nothing for lacking them: the audit reports each as a config
    key the update brings. The configuration-injection lists and the value
    patterns are required, so the project as it stands fails X for each, and
    the update resolves every one: nothing is owed. The `adr` block
    (CONVENTIONS §19), the `work_naming` block (CONVENTIONS §20), `layers.app`
    and `make_targets.empty_test_selections` and `write_shape_exempt`
    (CONVENTIONS §15) arrive beside them. `structure.project_checks` does
    not: the template never ships it, because a key beside `extra_toplevel`
    would conflict with every project that declared one."""
    project, _env = pre_c2_2
    before = _tree(project)
    systmp = tmp_path / "systmp"
    systmp.mkdir()
    r = _audit(project, doc_stamps.newest_stamp(_ROOT), tmpdir=systmp)
    assert _tree(project) == before, "the audit changed DEST's tree"
    assert _scratch_left(systmp) == []
    report = json.loads(r.stdout)
    assert report["base"]["resolved"], "29e45f0 must resolve in the template"
    assert _owed(report, "X") == [], report["groups"]["X"]
    required = (
        "child_env.config_injection_names",
        "child_env.config_injection_prefixes",
        "child_env.credential_value_patterns",
    )
    resolved = _errors(report, "X")
    assert sorted(k for f in resolved for k in required if k in f["message"]) == sorted(
        required
    ), resolved
    assert all(f["resolved_by"].startswith("copier update") for f in resolved), resolved
    arrived = [
        f
        for f in report["groups"]["config"]
        if f["kind"] == "arrives" and f.get("file") == "config/project.json"
    ]
    assert {f["key"] for f in arrived} == {
        "adr",
        "child_env.config_injection_names",
        "child_env.config_injection_prefixes",
        "child_env.credential_value_patterns",
        "child_env.credentialed_values",
        "child_env.login_name_schemes",
        "layers.app",
        "make_targets.empty_test_selections",
        "make_targets.write_shape_exempt",
        "work_naming",
    }, arrived
    values = [f for f in arrived if f["key"] == "child_env.credentialed_values"]
    assert "template default: {}" in values[0]["message"], arrived
    assert {f["tier"] for f in arrived} == {"info"}, arrived


def test_an_update_keeps_a_projects_own_child_env_lines_without_a_conflict(
    pre_c3_4, tmp_path
):
    """credentialed_values and prefixes are where a project records its own
    allowlist decisions, so the template's new child_env keys must not land on
    a line next to either: git merges adjacent edits as one conflicting hunk,
    the manifest stops parsing, and the update's own tasks then refuse to start
    a child. Both customisations survive the update, nothing is unmerged, and
    the audit of the customised project produces a report owing no X error."""
    project, env = pre_c3_4
    path = project / "config" / "project.json"
    text = path.read_text(encoding="utf-8")
    edits = (
        ('"credentialed_values": {}', '"credentialed_values": {"HTTPS_PROXY": "r"}'),
        ('"prefixes": ["LC_"]', '"prefixes": ["LC_", "SLURM_"]'),
    )
    for old, new in edits:
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")
    _git(project, "commit", "-qam", "own child_env decisions", env=env)
    day = doc_stamps.newest_stamp(_ROOT)
    upd, unmerged, failed = _real_update(project, tmp_path, day, env)
    assert (unmerged, failed) == ([], None), (unmerged, failed)
    block = json.loads((upd / "config" / "project.json").read_text("utf-8"))[
        "child_env"
    ]
    assert block["credentialed_values"] == {"HTTPS_PROXY": "r"}, block
    assert block["prefixes"] == ["LC_", "SLURM_"], block
    keel = json.loads((_ROOT / "config" / "project.json").read_text("utf-8"))
    for key in (
        "config_injection_names",
        "config_injection_prefixes",
        "credential_value_patterns",
        "login_name_schemes",
    ):
        assert block[key] == keel["child_env"][key], key
    systmp = tmp_path / "systmp"
    systmp.mkdir()
    r = _audit(project, day, tmpdir=systmp)
    assert r.returncode == 0, r.stdout + r.stderr
    report = json.loads(r.stdout)
    assert _owed(report, "X") == [], report["groups"]["X"]
    assert report["summary"]["conflicts"] == 0, report["groups"]["conflict"]


# Resolved once, before any test puts a shim first on PATH.
_REAL_GIT = shutil.which("git")


def test_copiers_own_git_sees_no_config_injection_or_repository_variable(
    pre_c2_2, tmp_path, monkeypatch
):
    """The audit runs `copier update` as a child through build_child_env, so
    copier's git (and every other git the audit starts) inherits neither a
    parent's `git -c` configuration nor its repository. A shim first on PATH
    logs the NAMES each git call sees, never a value, then runs the real git."""
    import child_env

    project, _env = pre_c2_2
    policy = child_env.load_policy(str(_ROOT))
    shim_dir = tmp_path / "shim"
    shim_dir.mkdir()
    log = tmp_path / "git-env-names.log"
    shim = shim_dir / "git"
    shim.write_text(
        "#!/bin/sh\n"
        "echo '--call' >> '%s'\n"
        "awk 'BEGIN { for (k in ENVIRON) print k }' >> '%s'\n"
        "exec '%s' \"$@\"\n" % (log, log, _REAL_GIT),
        encoding="utf-8",
    )
    shim.chmod(0o755)
    planted = {
        "GIT_DIR": str(tmp_path / "decoy.git"),
        "GIT_INDEX_FILE": str(tmp_path / "decoy.index"),
    }
    for name in policy.config_injection:
        planted[name] = "1" if name.endswith("COUNT") else str(tmp_path / "decoy")
    for prefix in policy.config_injection_prefixes:
        planted[prefix + "0"] = "core.synthetic"
    held = set(policy.config_injection) | set(policy.repo_context)
    for name, value in planted.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("PATH", str(shim_dir) + os.pathsep + os.environ["PATH"])

    systmp = tmp_path / "systmp"
    systmp.mkdir()
    r = _audit(project, doc_stamps.newest_stamp(_ROOT), tmpdir=systmp)
    lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    calls = lines.count("--call")
    assert calls > 0, "no git call went through the shim: the guard is vacuous"
    leaked = sorted(
        {
            n
            for n in lines
            if n in held
            or any(n.startswith(p) for p in policy.config_injection_prefixes)
        }
    )
    assert leaked == [], leaked
    assert r.returncode in (0, 1), r.stdout + r.stderr
    assert json.loads(r.stdout)["base"]["resolved"], r.stdout


def test_the_audit_never_refreshes_the_template_index(pre_c2_2, tmp_path):
    """Copier run straight against a dirty local template runs a plain `git
    status` there, which rewrites its index. The audit snapshots the checkout
    by clone instead, so a template whose tracked file is stat-dirty keeps its
    index bytes, its index mtime and its status. The audit run is the copy's
    own scripts/audit_project.py, so the copy is the template it judges by."""
    project, env = pre_c2_2
    template = tmp_path / "template"
    hermetic_git.clone_including_worktree(_ROOT, template, tmp_path)
    readme = template / "README.md"
    os.utime(readme, (readme.stat().st_atime, readme.stat().st_mtime + 7))
    index = template / ".git" / "index"
    before = (index.read_bytes(), index.stat().st_mtime_ns)
    porcelain = _porcelain(template, env)
    systmp = tmp_path / "systmp"
    systmp.mkdir()

    r = _audit(
        project,
        doc_stamps.newest_stamp(_ROOT),
        tmpdir=systmp,
        audit=template / "scripts" / "audit_project.py",
    )
    assert r.returncode in (0, 1), r.stdout + r.stderr
    assert json.loads(r.stdout)["base"]["resolved"], "29e45f0 must resolve"
    assert (index.read_bytes(), index.stat().st_mtime_ns) == before
    assert _porcelain(template, env) == porcelain
    assert _scratch_left(systmp) == []


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


# --- ADR number spaces: an update moves keel's ADRs to docs/adr/keel ------------

_KEEL_ADRS = 15


def _own_adr(number, slug, title):
    """A project ADR as a project writes one, in its own number space."""
    return (
        "---\n"
        'title: "ADR-%s: %s"\n'
        "kind: adr\nlayer: n/a\nstatus: accepted\nowner: us\ntags: [adr]\n"
        'summary: "%s."\n'
        "id: docs-adr-%s-%s\ncreated: 2026-10-01\nupdated: 2026-10-01\n"
        "visibility: internal\ncanonical: true\n---\n\n# ADR-%s: %s\n\n"
        "The project's own decision.\n"
    ) % (number, title, title, number, slug, number, title)


@pytest.fixture(scope="module")
def adr_update(pre_campaign, tmp_path_factory):
    """One real update of a 7f0a68b project that wrote two ADRs of its own --
    one numbered 0010, which keel's own 0010 collided with before the number
    spaces split -- edited `owner:` on keel's 0002 (what project-jarvis did to
    0001-0004) and moved only the `updated:` stamp of keel's 0003. Yields
    (the updated clone, the update's stderr, env). stderr is read at the file
    descriptor: copier's migrations are child processes."""
    project, env = pre_campaign
    work = tmp_path_factory.mktemp("adr_update")
    dest = work / "dest"
    _git(work, "clone", "-q", "--no-hardlinks", str(project), str(dest), env=env)
    adr = dest / "docs" / "adr"
    (adr / "0010-areas-of-our-own.md").write_text(
        _own_adr("0010", "areas-of-our-own", "Areas of our own"), encoding="utf-8"
    )
    (adr / "0013-our-own-decision.md").write_text(
        _own_adr("0013", "our-own-decision", "Our own decision"), encoding="utf-8"
    )
    edited = adr / "0002-agent-surface-and-discovery.md"
    text = edited.read_text(encoding="utf-8")
    assert text.count("\nowner: TBD\n") == 1
    edited.write_text(text.replace("\nowner: TBD\n", "\nowner: us\n"), encoding="utf-8")
    stamped = adr / "0003-agent-control-flow-runtime.md"
    text = stamped.read_text(encoding="utf-8")
    old_stamp = [ln for ln in text.splitlines() if ln.startswith("updated: ")][0]
    stamped.write_text(
        text.replace(old_stamp + "\n", "updated: 2026-10-06\n", 1), encoding="utf-8"
    )
    _git(dest, "add", "-A", env=env)
    _git(dest, "commit", "-qm", "our own ADRs and an owner", env=env)
    real = work / "real"
    real.mkdir()
    sink = work / "stderr.txt"
    saved = os.dup(2)
    try:
        with open(str(sink), "wb") as fh:
            os.dup2(fh.fileno(), 2)
            upd, unmerged, failed = _real_update(
                dest, real, doc_stamps.newest_stamp(_ROOT), env
            )
    finally:
        os.dup2(saved, 2)
        os.close(saved)
    assert (unmerged, failed) == ([], None), (unmerged, failed)
    yield dest, upd, sink.read_text(encoding="utf-8", errors="replace"), env


def _adr_names(root, sub=""):
    d = Path(root) / "docs" / "adr" / sub
    return sorted(
        n for n in os.listdir(str(d)) if n[:1].isdigit() or n.startswith("K-")
    )


def test_an_update_from_7f0a68b_moves_template_adrs_and_keeps_the_projects_own(
    adr_update,
):
    """keel's ADRs arrive in docs/adr/keel as K- files, every unedited old copy
    is retired, and the project's own ADRs -- its 0010 included -- stay where
    they are, in the number space the project owns."""
    _dest, upd, _err, _env = adr_update
    keel = _adr_names(upd, "keel")
    assert len(keel) == _KEEL_ADRS and all(n.startswith("K-") for n in keel), keel
    assert keel == sorted(
        n
        for n in os.listdir(str(_ROOT / "docs" / "adr" / "keel"))
        if n.startswith("K-")
    )
    assert _adr_names(upd) == [
        "0002-agent-surface-and-discovery.md",  # edited: kept (next test)
        "0010-areas-of-our-own.md",
        "0013-our-own-decision.md",
    ]
    errors = {m for tier, m in _gate(upd) if tier == "error"}
    assert [m for m in errors if "docs/adr" in m and "duplicate id" not in m] == []


def test_an_update_keeps_and_reports_a_template_adr_the_project_edited(adr_update):
    """copier deletes the retired 0002 though the project edited it; the guard
    migration puts the project's bytes back and says so. The restamp migration
    then moves its `updated:` value, because the project's committed edit left
    the stamp stale; every other byte is the project's. What the gate then
    owes is exactly check_A's duplicate id: the kept copy and K-0002 share it,
    and the project chooses (docs/adr/README.md)."""
    dest, upd, err, _env = adr_update
    rel = "docs/adr/0002-agent-surface-and-discovery.md"

    def unstamped(path):
        lines = path.read_text(encoding="utf-8").splitlines(True)
        return [ln for ln in lines if not ln.startswith("updated: ")]

    assert unstamped(upd / rel) == unstamped(dest / rel)
    assert "\nowner: us\n" in (upd / rel).read_text(encoding="utf-8")
    assert (
        "kept %s: the project edited it and the template retired it "
        "(now docs/adr/keel/K-0002-agent-surface-and-discovery.md)" % rel
    ) in err, err
    errors = sorted(m for tier, m in _gate(upd) if tier == "error")
    assert len(errors) == 1, errors
    # The id is the one 0002 has carried since the first commit (the file
    # name grew "-and-discovery" later; the id did not).
    assert "duplicate id 'docs-adr-0002-agent-surface'" in errors[0], errors
    assert rel in errors[0] and "K-0002-agent-surface-and-discovery.md" in errors[0]


def test_a_restamp_only_difference_is_not_kept(adr_update):
    """A copy that differs from the template's only in the `updated:` stamp the
    restamp writer moves is not an edit: its retirement stands, silently."""
    _dest, upd, err, _env = adr_update
    assert not (upd / "docs" / "adr" / "0003-agent-control-flow-runtime.md").exists()
    assert (upd / "docs/adr/keel/K-0003-agent-control-flow-runtime.md").is_file()
    assert "0003-agent-control-flow-runtime" not in err, err
