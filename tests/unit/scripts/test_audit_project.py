"""
title: Unit — audit_project (another project judged by this template's gates)
kind: tests
layer: n/a
summary: scripts/audit_project.py pinned against a small fake template (a git history of a base and a newer commit, or uncommitted edits) and a keel-shaped DEST in a scratch directory. It refuses, exit 2 and naming each missing item, whatever is not a keel project; with a base it judges the tree a real `copier update` leaves on a scratch copy of DEST: an error the update brings a fix for is resolved, an error the update leaves is owed even in a file the project never edited, a key the update brings is judged with the file that uses it, and a file copier would conflict on is reported in the conflict group and its findings not judged, while the rest of the tree is judged with every conflict hunk the project's way and the template's way, never beside DEST's pre-update bytes: a cross-file finding both resolutions have is owed, one only one has is not judged (`resolve_conflict` keeps one side of each hunk, the diff3 base dropped, and refuses markers copier does not write); an update copier would refuse (DEST outside git, or uncommitted changes, each named) is an `update-refused` config warning with no exit change; `classify` names what the update did to each config key (arrives, updates, merges, removed-upstream; a list is one value; inputs never mutated); without a base nothing is predicted and DEST is judged as it stands; a failed update is exit 2 with the scratch path masked, unless it is an `after` migration refusing over files the update itself leaves conflicted, which the real update will do too: that is named under not checked with its rerun, the tree copier leaves is judged, and when the refused migration is the restamp or one before it the freshness and restamp groups name `make restamp-docs` instead of claiming the update rewrites the stamps, while a refusal naming a file the update did not conflict is still exit 2; a symlink leaving DEST is never written through; the scratch tree is removed on every path. The update's base config is rendered in memory from the template's twin with DEST's answers and copier.yml's derived defaults; findings are grouped A..Z then conflict, config, freshness and restamp, sorted, and the --json output is canonical and byte-identical across runs; an unreadable file has unknown origin, and malformed or wrongly typed answers are a refusal, not a traceback; a not-checked section is always present; and DEST's code, Makefile, git hooks and the commands its git config names (fsmonitor, a clean filter) are never run and its files never written. Excluded from generated projects with the doer.
"""

import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import audit_project as ap  # noqa: E402

import hermetic_git  # noqa: E402
import optional_deps  # noqa: E402

# The audit predicts the update by running copier itself (`python -m copier` in
# this interpreter), and `_generated` renders a DEST with it: without copier every
# prediction test fails for a reason that is not the audit's. Routed through
# optional_deps so CI, which declares the template surface, fails on a missing
# copier instead of skipping (test_copier_generator_contract.py pins this).
copier = optional_deps.importorskip("copier", extra="template")

pytestmark = pytest.mark.unit

TODAY = "2026-09-02"
# Every check letter, read from check_structure.py's own definitions rather than
# from the audit's LETTERS, so a letter the audit forgot to run shows as a
# difference instead of agreeing with itself; and rather than a hand-kept range,
# which went stale with each new letter.
_CHECK_LETTERS = sorted(
    re.findall(
        r"^def check_([A-Z])\b",
        (_ROOT / "scripts" / "check_structure.py").read_text(encoding="utf-8"),
        re.MULTILINE,
    )
)
_FM = (
    "---\ntitle: %s\nkind: %s\nlayer: n/a\nstatus: stable\nsummary: s\nid: %s\n"
    "created: 2026-01-01\nupdated: 2026-01-01\nvisibility: internal\n"
    "canonical: true\nowner: me\n---\n\n# t\n"
)
_POLICY = {
    "unattended_vars": ["CI", "RALPH"],
    "gate_runner_var": "RALPH",
    "gate_effects": ["local", "read"],
    "write_shapes": [],
    "area_dir": None,
    "effect_proof_skip": {},
    "effect_proof_kept_dirs": {"XDG_CONFIG_HOME": ".config"},
    "write_shape_exempt": {},
    "empty_test_selections": {},
    "gate_vars": ["PY"],
}
_GUARD = (
    'WRITE_GUARD = @if [ -n "$(CI)$(RALPH)" ]; then echo "refusing $@" >&2; '
    "exit 1; fi\n"
)
_COPIER_YML = """\
_exclude:
  - "copier.yml"
  - ".git"
project_name:
  type: str
  default: "my_project"
project_slug:
  type: str
  when: false
  default: "{{ project_name | lower | replace(' ', '_') }}"
profiles:
  type: str
  multiselect: true
  choices: [ai]
  default: []
"""
_TWIN_FORMAT = """\
{
  "name": "{{ project_slug }}",
  "structure": {"extra_toplevel": []},
  "make_targets": %s,
  "practices": {"profiles": {"ai": {{ "true" if "ai" in profiles else "false" }}}}
}
"""


def _twin(**policy):
    """The fake manifest twin, `make_targets` being _POLICY updated by *policy*
    and rendered on one line, so a template edit to it is a one-line edit."""
    return _TWIN_FORMAT % json.dumps(dict(_POLICY, **policy))


_TWIN = _twin()
_MAKEFILE = _GUARD + "a: ## [local] A\n\t@true\n"


def _git(cwd, *argv):
    proc = subprocess.run(
        ["git"] + list(argv),
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        env=dict(
            os.environ,
            GIT_AUTHOR_DATE="2026-01-01T12:00:00+0000",
            GIT_COMMITTER_DATE="2026-01-01T12:00:00+0000",
        ),
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def _label(root, name):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    slug = name.replace("/", "-")
    (d / "README.md").write_text(_FM % (name, "readme", slug + "-readme"))
    (d / "AGENT.md").write_text(_FM % (name, "rules", slug + "-rules"))
    if not (d / "CLAUDE.md").is_symlink():
        os.symlink("AGENT.md", str(d / "CLAUDE.md"))


@pytest.fixture(autouse=True)
def _hermetic(tmp_path, monkeypatch):
    """A hermetic git for the doer's own calls, today pinned, and the
    check_structure module state restored after each in-process audit."""
    work = tmp_path / "gitwork"
    work.mkdir()
    for key, value in hermetic_git.git_env_vars(work).items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    cs = ap.check_structure
    for name in ("ROOT", "errors", "warnings", "GOVERNED"):
        monkeypatch.setattr(cs, name, getattr(cs, name))
    monkeypatch.setattr(cs, "_CONFIG_READ", dict(cs._CONFIG_READ))
    monkeypatch.setattr(cs, "_READ_REPORTED", set(cs._READ_REPORTED))
    # The audit's scratch tree lives under tempfile's directory: one per test,
    # so a test can prove it is empty afterwards.
    systmp = tmp_path / "systmp"
    systmp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(systmp))


@pytest.fixture()
def template(tmp_path, monkeypatch):
    """A fake template: copier.yml and one config twin, nothing else. The doer's
    checks stay this checkout's; only where the update's config comes from moves."""
    root = tmp_path / "template"
    (root / "config").mkdir(parents=True)
    (root / "copier.yml").write_text(_COPIER_YML, encoding="utf-8")
    (root / "config" / "project.json.jinja").write_text(_TWIN, encoding="utf-8")
    monkeypatch.setattr(ap, "TEMPLATE", str(root))
    return root


def _dest(tmp_path, template, manifest=None, commit="0000000", name="dest"):
    """A keel-shaped DEST: answers naming the fake template, a labelled tree and
    its own config/project.json (default: the name only)."""
    dest = tmp_path / name
    for name in ("src", "tests", "docs", "config"):
        _label(dest, name)
    (dest / ".copier-answers.yml").write_text(
        "_commit: '%s'\n_src_path: %s\nprofiles: []\nproject_name: Demo\n"
        % (commit, template),
        encoding="utf-8",
    )
    (dest / "config" / "project.json").write_text(
        json.dumps({"name": "demo"} if manifest is None else manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    return dest


def _plant_b_and_w(dest):
    (dest / "zzz").mkdir()
    (dest / "zzz" / "data.txt").write_text("x\n")
    (dest / "Makefile").write_text(_GUARD + "planted: ## Does a thing\n\t@true\n")


def _commit_dest(dest):
    _git(dest, "init", "-q")
    _git(dest, "add", "-A")
    _git(dest, "commit", "-q", "-m", "generated")


def _template_commits(template, base_files, theirs_files, commit_theirs=True):
    """The fake template's history: *base_files* written and committed (the
    commit a project is generated from), then *theirs_files* written over it,
    as a second commit or, with *commit_theirs* False, left as uncommitted
    edits -- the two states of a checkout the audit snapshots. Returns the base
    sha."""
    for rel, text in base_files.items():
        path = template / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    _commit_dest(template)
    sha = _git(template, "rev-parse", "HEAD").strip()
    for rel, text in theirs_files.items():
        path = template / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    if theirs_files and commit_theirs:
        _git(template, "add", "-A")
        _git(template, "commit", "-q", "-m", "theirs")
    return sha


def _generated(tmp_path, template, sha, name="dest"):
    """A DEST as copier generates it from the fake template at *sha*: the
    labelled tree and answers of `_dest`, with every template file rendered
    over it by copier itself, so its bytes are what the update's base renders."""
    dest = _dest(tmp_path, template, commit=sha, name=name)
    proc = subprocess.run(
        [sys.executable, "-m", "copier", "copy", "--quiet", "--defaults"]
        + ["--overwrite", "--vcs-ref", sha, "--data", "project_name=Demo"]
        + [str(template), str(dest)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        env=dict(os.environ),
    )
    assert proc.returncode == 0, proc.stderr
    return dest


def _errors(report, group):
    return [f for f in report["groups"][group] if f["tier"] == "error"]


def _scratch_left(tmp_path):
    """What the audit left under tempfile's directory (the `_hermetic` one)."""
    return sorted(os.listdir(str(tmp_path / "systmp")))


def _snapshot(root):
    """Every path under *root* with its bytes (or link target), mode and mtime."""
    state = {}
    for dirpath, dirnames, filenames in os.walk(str(root)):
        dirnames.sort()
        for name in sorted(dirnames + filenames):
            full = os.path.join(dirpath, name)
            st = os.lstat(full)
            if os.path.islink(full):
                body = ("link", os.readlink(full))
            elif os.path.isfile(full):
                with open(full, "rb") as fh:
                    body = ("file", fh.read())
            else:
                body = ("dir", None)
            state[os.path.relpath(full, str(root))] = (body, st.st_mode, st.st_mtime_ns)
    return state


def _run(argv, capsys):
    code = ap.main(argv)
    out = capsys.readouterr()
    return code, out.out, out.err


# --- CLI ------------------------------------------------------------------------


def test_help_exits_zero_and_names_dest(capsys):
    with pytest.raises(SystemExit) as exc:
        ap.main(["--help"])
    assert exc.value.code == 0
    text = capsys.readouterr().out
    assert "DEST" in text and "--json" in text
    assert "DEST is never written" in text and "scratch copy" in text


# --- refusal: what is not a keel project ----------------------------------------


def _missing(dest):
    return dest / "absent"


def _a_file(dest):
    path = dest / "a_file"
    path.write_text("x\n")
    return path


def _no_answers(dest):
    (dest / ".copier-answers.yml").unlink()
    return dest


def _answers(text):
    def setup(dest):
        (dest / ".copier-answers.yml").write_text(text, encoding="utf-8")
        return dest

    return setup


def _manifest(text):
    def setup(dest):
        path = dest / "config" / "project.json"
        if text is None:
            path.unlink()
        else:
            path.write_text(text, encoding="utf-8")
        return dest

    return setup


@pytest.mark.parametrize(
    "setup, named",
    [
        (_missing, "not a directory"),
        (_a_file, "not a directory"),
        ("template", "is the template"),
        (_no_answers, ".copier-answers.yml"),
        (_answers("_commit: abc\nproject_name: x\n"), "_src_path"),
        (_answers("_commit: ''\n_src_path: /somewhere\n"), "_commit"),
        (_answers("- a list\n"), ".copier-answers.yml"),
        (_manifest(None), "config/project.json"),
        (_manifest("{not json"), "config/project.json"),
        (_manifest("[1, 2]"), "config/project.json"),
        (_answers("_commit: abc\n_src_path: /x\nproject_name: x\n1: y\n"), "key 1"),
        (
            _answers("_commit: abc\n_src_path: /x\nproject_name: x\nprofiles: null\n"),
            "cannot render",
        ),
    ],
    ids=[
        "missing",
        "a-file",
        "the-template",
        "no-answers",
        "no-src-path",
        "empty-commit",
        "answers-not-a-mapping",
        "no-manifest",
        "manifest-invalid",
        "manifest-a-list",
        "answer-key-not-a-string",
        "answer-of-the-wrong-type",
    ],
)
def test_refuses_what_is_not_a_keel_project(tmp_path, template, capsys, setup, named):
    dest = _dest(tmp_path, template)
    target = template if setup == "template" else setup(dest)
    before = _snapshot(tmp_path / "dest")
    code, out, err = _run([str(target)], capsys)
    assert code == 2
    assert named in err, err
    assert out == ""
    assert _snapshot(tmp_path / "dest") == before


def test_a_refusal_names_every_missing_item_at_once(tmp_path, template, capsys):
    dest = _dest(tmp_path, template)
    (dest / ".copier-answers.yml").write_text("project_name: x\n", encoding="utf-8")
    (dest / "config" / "project.json").unlink()
    code, _out, err = _run([str(dest)], capsys)
    assert code == 2
    for item in ("_src_path", "_commit", "config/project.json"):
        assert item in err, err


# --- the update's config: a key-level 3-way merge --------------------------------


def _kinds(changes):
    return {c["key"]: c["kind"] for c in changes}


def test_classify_names_what_the_update_did_to_each_key():
    """The audit merges nothing: copier's own update produced *predicted*, and
    classify reads each key's story from base (the template at `_commit`),
    ours (DEST) and predicted. Objects recurse with dotted keys; a list is one
    value; `_` keys are commentary and never reported."""
    base = {
        "same": 1,
        "tmpl_moved": "old",
        "ours_moved": "old",
        "both_moved": "old",
        "gone_upstream": 1,
        "listy": ["a", "b"],
        "names": ["GIT_DIR", "HOME"],
        "nest": {"inner": 1, "keep": True},
        "_comment": "base",
    }
    ours = {
        "same": 1,
        "tmpl_moved": "old",
        "ours_moved": "mine",
        "both_moved": "mine",
        "gone_upstream": 1,
        "listy": ["a", "b"],
        "names": ["GIT_DIR", "HOME", "MY_TOOL_HOME"],
        "nest": {"inner": 1, "keep": True},
        "_comment": "ours",
    }
    predicted = {
        "same": 1,
        "tmpl_moved": "new",
        "ours_moved": "mine",
        "both_moved": "merged",
        "listy": ["a", "c"],
        "names": ["HOME", "MY_TOOL_HOME"],
        "nest": {"inner": 2, "keep": True, "fresh": [1]},
        "arrived": {"a": 1},
        "_comment": "theirs",
    }
    inputs = copy.deepcopy((base, ours, predicted))

    changes = ap.classify(base, ours, predicted)

    assert (base, ours, predicted) == inputs
    assert _kinds(changes) == {
        "tmpl_moved": "updates",
        "both_moved": "merges",
        "gone_upstream": "removed-upstream",
        "listy": "updates",
        "names": "merges",
        "nest.inner": "updates",
        "nest.fresh": "arrives",
        "arrived": "arrives",
    }
    assert [c["key"] for c in changes] == sorted(c["key"] for c in changes)
    arrived = [c for c in changes if c["key"] == "arrived"][0]
    assert arrived["predicted"] == {"a": 1}
    names = [c for c in changes if c["key"] == "names"][0]
    msg = ap._config_message("config/project.json", names)
    assert "MY_TOOL_HOME" in msg and "GIT_DIR" in msg, msg
    # The predicted value is what copier wrote, whatever it is: an edited key
    # the update left as the project had it is not reported at all.
    assert ap.classify({"k": 1}, {"k": 2}, {"k": 2}) == []
    # No base: nothing is known about the project's edits, so a key the
    # template lacks is not "removed", and only arrivals and updates remain.
    assert _kinds(ap.classify(None, {"a": 1, "own": 1}, {"a": 2, "b": 3})) == {
        "a": "updates",
        "b": "arrives",
    }


def test_origin_names_what_git_at_the_base_says_about_the_path(tmp_path, monkeypatch):
    """A file copier renders from a `.jinja` twin is template-rendered even when
    the template also carries the plain file (copier never copies a plain twin);
    a verbatim file is unedited or edited by its bytes against the base; a path
    the base lacks is the project's; no base, or no path token, is unknown."""
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.json").write_text("{}\n")
    (tmp_path / "Makefile").write_text("same\n")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "s.py").write_text("edited\n")
    (tmp_path / "zzz").mkdir()
    tree = {
        "config/project.json": "blob",
        "config/project.json.jinja": "blob",
        "Makefile": "blob",
        "scripts": "tree",
        "scripts/s.py": "blob",
    }
    monkeypatch.setattr(
        ap, "_blob", lambda sha, path: b"same\n" if path == "Makefile" else b"x\n"
    )
    dest, sha = str(tmp_path), "f" * 40
    assert ap.origin_of(dest, "config/project.json: k", sha, tree) == (
        "template-rendered"
    )
    assert ap.origin_of(dest, "Makefile: target t", sha, tree) == "template-unedited"
    assert ap.origin_of(dest, "scripts/s.py:3: spawn", sha, tree) == "template-edited"
    assert ap.origin_of(dest, "zzz/ is not a taxonomy row", sha, tree) == "project"
    assert ap.origin_of(dest, "Makefile: target t", None, tree) == "unknown"
    assert ap.origin_of(dest, "", sha, tree) == "unknown"
    # A path neither DEST nor the base has, which the predicted tree has: the
    # update brings it.
    predicted = tmp_path.parent / "predicted"
    (predicted / "mk").mkdir(parents=True)
    (predicted / "mk" / "new.mk").write_text("x\n")
    assert ap.origin_of(dest, "mk/new.mk: t", sha, tree, str(predicted)) == (
        "template-new"
    )
    assert ap.origin_of(dest, "mk/new.mk: t", sha, tree) == "unknown"


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root reads a 000 file"
)
def test_an_unreadable_file_has_unknown_origin_not_a_crash(tmp_path, monkeypatch):
    """check_structure reports an unreadable file itself; its origin is evidence
    the audit cannot read, so it is `unknown`, never a traceback whose exit 1
    would read as "errors found"."""
    (tmp_path / "scripts").mkdir()
    locked = tmp_path / "scripts" / "locked.py"
    locked.write_text("x\n")
    locked.chmod(0)
    monkeypatch.setattr(ap, "_blob", lambda sha, path: b"x\n")
    try:
        origin = ap.origin_of(
            str(tmp_path),
            "scripts/locked.py: unreadable",
            "f" * 40,
            {"scripts": "tree", "scripts/locked.py": "blob"},
        )
    finally:
        locked.chmod(0o644)
    assert origin == "unknown"


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root reads mode-000 files"
)
def test_an_unreadable_doc_is_reported_not_a_traceback(tmp_path, template, capsys):
    """Every reader the audit drives (the letters, the freshness judge, the
    restamp list, origin) meets the same unreadable doc; the audit completes and
    names it under restamp instead of dying with a traceback whose exit 1 would
    read as "errors found"."""
    dest = _dest(tmp_path, template)
    _commit_dest(dest)
    locked = dest / "docs" / "README.md"
    locked.chmod(0)
    try:
        code, out, _err = _run([str(dest), "--today", TODAY, "--json"], capsys)
    finally:
        locked.chmod(0o644)
    report = json.loads(out)
    named = [f for f in report["groups"]["restamp"] if f["path"] == "docs/README.md"]
    assert [f["tier"] for f in named] == ["warning"], report["groups"]["restamp"]
    assert "cannot read" in named[0]["message"]
    assert code == report["exit"]


def test_theirs_is_rendered_from_the_twin_with_dest_answers_and_derived_defaults():
    """Against this checkout's real twin: `project_slug` is derived from
    copier.yml's default, never re-typed, and keel's `template` block stays out."""
    answers = {
        "project_name": "Demo Proj",
        "frontend_stack": "none",
        "transports": [],
        "profiles": ["ai"],
        "backend_python": ">=3.10",
        "a_dropped_question": 1,
        "_commit": "ignored",
    }
    configs, notes = ap.render_configs(ap.worktree_reader(ap.TEMPLATE), answers)
    project = configs["config/project.json"]
    assert project["name"] == "demo_proj"
    assert project["practices"]["profiles"]["ai"] is True
    assert "template" not in project
    assert "frontend" not in project["layers"]
    assert configs["config/practices.json"] == json.loads(
        (_ROOT / "config" / "practices.json").read_text(encoding="utf-8")
    )
    assert any(
        n.startswith("new question showcase (template default: true)") for n in notes
    ), notes
    assert any("a_dropped_question" in n for n in notes), notes
    assert not any("project_slug" in n or "_commit" in n for n in notes), notes


def test_an_undefined_template_variable_is_a_named_error(tmp_path, template):
    (template / "config" / "project.json.jinja").write_text(
        '{"x": "{{ nowhere_defined }}"}\n', encoding="utf-8"
    )
    with pytest.raises(ap.AuditError) as exc:
        ap.render_configs(ap.worktree_reader(str(template)), {"project_name": "d"})
    assert "nowhere_defined" in str(exc.value)


# --- the report -------------------------------------------------------------------


def test_findings_are_grouped_sorted_and_json_is_byte_identical(
    tmp_path, template, capsys
):
    sha = _template_commits(
        template,
        {"config/project.json.jinja": _TWIN},
        {"config/project.json.jinja": _twin(gate_effects=["local", "read", "cost"])},
    )
    dest = _generated(tmp_path, template, sha)
    _plant_b_and_w(dest)
    argv = [str(dest), "--today", TODAY]

    code, text, err = _run(argv, capsys)
    assert code == 1, err
    headers = re.findall(r"^\[([A-Za-z]+)\]", text, re.MULTILINE)
    assert _CHECK_LETTERS and headers == _CHECK_LETTERS + [
        "conflict",
        "config",
        "freshness",
        "restamp",
        "retired",
    ]
    b_block = text.split("[B]", 1)[1].split("[C]", 1)[0]
    w_block = text.split("[W]", 1)[1].split("[X]", 1)[0]
    assert "zzz" in b_block and "planted" in w_block
    config_block = text.split("[config]", 1)[1].split("[freshness]", 1)[0]
    lines = [ln for ln in config_block.splitlines()[1:] if ln.strip()]
    # Errors, then warnings (here: the update copier refuses on a DEST outside
    # git), then info, each sorted by message.
    by_tier = sorted(lines, key=lambda ln: (ap.TIERS.index(ln.split()[0].lower()), ln))
    assert lines == by_tier and any("make_targets" in ln for ln in lines)
    assert lines[0].split()[0] == "WARNING", lines
    assert "0 conflicted file(s) not judged" in text, text

    _c1, first, _e1 = _run(argv + ["--json"], capsys)
    _c2, second, _e2 = _run(argv + ["--json"], capsys)
    assert first == second
    report = json.loads(first)
    assert report["base"]["resolved"] == sha
    assert (
        json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n" == first
    )
    assert report["summary"]["checks_run"] == _CHECK_LETTERS
    assert report["summary"]["conflicts"] == 0
    assert sorted(report["groups"]) == sorted(ap.GROUPS)  # JSON sorts keys
    assert ap.GROUPS[-5:] == ("conflict", "config", "freshness", "restamp", "retired")
    assert report["summary"]["files_seen"] > 0
    assert [f["tier"] for f in report["groups"]["B"]] == ["error"]
    assert [f["tier"] for f in report["groups"]["W"]] == ["error"]
    for output in (text, first):
        rest = output.replace(os.path.realpath(str(dest)), "DEST")
        assert str(tmp_path) not in rest and os.path.realpath(str(tmp_path)) not in rest
    assert _scratch_left(tmp_path) == []


def test_each_group_is_sorted_by_tier_then_message(
    tmp_path, template, capsys, monkeypatch
):
    """Whatever order the checks emit in, a group reads errors, then warnings,
    then info, each sorted by message: two audits of one tree diff cleanly."""
    dest = _dest(tmp_path, template)
    emitted = [
        ("B", "warning", "m-warn"),
        ("B", "error", "z-err"),
        ("B", "warning", "a-warn"),
        ("B", "error", "a-err"),
    ]
    monkeypatch.setattr(
        ap.check_structure, "run_checks", lambda root, **_kw: list(emitted)
    )
    _code, out, _err = _run([str(dest), "--today", TODAY, "--json"], capsys)
    b = [(f["tier"], f["message"]) for f in json.loads(out)["groups"]["B"]]
    assert b == [
        ("error", "a-err"),
        ("error", "z-err"),
        ("warning", "a-warn"),
        ("warning", "m-warn"),
    ]


def test_a_pass_over_zero_files_fails(tmp_path, template, capsys, monkeypatch):
    """A tree in which the checks saw no file proves nothing: exit 1 with no
    error, never a green audit over nothing."""
    dest = _dest(tmp_path, template)
    monkeypatch.setattr(ap.check_structure, "walk", lambda root: iter(()))
    code, out, _err = _run([str(dest), "--today", TODAY, "--json"], capsys)
    report = json.loads(out)
    assert report["summary"]["files_seen"] == 0
    assert report["summary"]["errors"] == 0
    assert (code, report["exit"]) == (1, 1)


def test_a_commit_that_reads_as_an_option_never_reaches_git(monkeypatch):
    calls = []
    monkeypatch.setattr(ap, "_git", lambda *a, **k: calls.append(a) or (0, "x", ""))
    for commit in ("--all", "-h", "", None):
        assert ap.resolve_commit(commit) is None
    assert calls == []
    assert ap.resolve_commit("abc123") == "x"
    assert len(calls) == 1


def test_exit_code_follows_letter_errors_only(tmp_path, template, capsys):
    dest = _dest(tmp_path, template)
    _commit_dest(dest)
    # A body edit to a committed governed doc: a freshness finding, which the
    # update's own restamp migration clears, so it does not fail the audit.
    readme = dest / "docs" / "README.md"
    readme.write_text(readme.read_text() + "\nedited\n")
    code, out, _err = _run([str(dest), "--today", TODAY, "--json"], capsys)
    report = json.loads(out)
    assert code == 0, report
    assert [f["path"] for f in report["groups"]["freshness"]] == ["docs/README.md"]
    assert report["groups"]["freshness"][0]["resolved_by"].startswith("copier update")
    assert "make restamp-docs" in report["groups"]["freshness"][0]["message"]
    assert [f["path"] for f in report["groups"]["restamp"]] == ["docs/README.md"]
    assert [c["key"] for c in report["groups"]["config"] if c["kind"] == "arrives"]
    assert report["exit"] == 0

    (dest / "zzz").mkdir()
    assert ap.main([str(dest), "--today", TODAY]) == 1
    capsys.readouterr()
    assert ap.main([str(dest / "nope"), "--today", TODAY]) == 2


# --- the predicted tree: what `copier update` leaves ------------------------------

_PLANTED = "planted: ## Does a thing\n\t@true\n"
_LABELLED = "planted: ## [local] Does a thing\n\t@true\n"
# Lines after the target, so an edit at the end of the file is not adjacent
# to an edit of the target's line (git's merge conflicts on touching hunks).
_TAIL = "\nother: ## [local] Other\n\t@true\n\nlast: ## [local] Last\n\t@true\n"


def test_a_key_the_update_brings_is_judged_with_the_file_that_uses_it(
    tmp_path, template, capsys
):
    """The 7f0a68b class: the update adds a target to the Makefile and names it
    in the manifest's effect_proof_skip. Judged as one tree, the entry and its
    target arrive together; a view that merged only the manifest would call the
    entry stale against the old Makefile and owe a W error."""
    sha = _template_commits(
        template,
        {"config/project.json.jinja": _TWIN, "Makefile": _MAKEFILE},
        {
            "config/project.json.jinja": _twin(effect_proof_skip={"x": "reason"}),
            "Makefile": _MAKEFILE + "x: ## [local] X\n\t@true\n",
        },
    )
    dest = _generated(tmp_path, template, sha)

    code, out, err = _run([str(dest), "--today", TODAY, "--json"], capsys)
    report = json.loads(out)
    assert _errors(report, "W") == [], report["groups"]["W"]
    assert report["summary"]["errors"] == 0, report["summary"]
    assert (code, report["exit"]) == (0, 0), err
    kinds = {(c["key"], c["kind"]) for c in report["groups"]["config"]}
    assert ("make_targets.effect_proof_skip.x", "arrives") in kinds, kinds
    assert _scratch_left(tmp_path) == []


@pytest.mark.parametrize("commit_theirs", [True, False], ids=["committed", "dirty"])
def test_an_error_the_update_does_not_fix_is_owed_even_in_an_unedited_file(
    tmp_path, template, capsys, commit_theirs
):
    """A file the project never edited is replaced by the template's, which may
    carry the same defect: the error is owed. Holds whether the template's newer
    state is a commit or uncommitted edits in the checkout."""
    sha = _template_commits(
        template,
        {"config/project.json.jinja": _TWIN, "Makefile": _GUARD + _PLANTED},
        {"Makefile": _GUARD + _PLANTED + _TAIL},
        commit_theirs=commit_theirs,
    )
    dest = _generated(tmp_path, template, sha)

    code, out, err = _run([str(dest), "--today", TODAY, "--json"], capsys)
    report = json.loads(out)
    w = report["groups"]["W"]
    assert [(f["tier"], f["origin"]) for f in w] == [("error", "template-unedited")]
    assert "resolved_by" not in w[0], w
    assert report["summary"]["errors"] == 1, report["summary"]
    assert report["summary"]["resolved_by_update"] == 0, report["summary"]
    assert (code, report["exit"]) == (1, 1), err
    # The snapshot never wrote the template checkout (its uncommitted edits
    # included).
    assert (template / "Makefile").read_text() == _GUARD + _PLANTED + _TAIL


@pytest.mark.parametrize("commit_theirs", [True, False], ids=["committed", "dirty"])
def test_an_error_the_update_fixes_is_resolved_and_an_edited_copy_is_judged_merged(
    tmp_path, template, capsys, commit_theirs
):
    """The template labels the target. The project that never touched its
    Makefile and the project that appended a line both receive the label
    through copier's merge, so in both the W error is resolved by the update:
    the per-file "unedited" proxy owed the edited one."""
    sha = _template_commits(
        template,
        {"config/project.json.jinja": _TWIN, "Makefile": _GUARD + _PLANTED + _TAIL},
        {"Makefile": _GUARD + _LABELLED + _TAIL},
        commit_theirs=commit_theirs,
    )
    for name, edit in (("unedited", ""), ("edited", "# edited\n")):
        dest = _generated(tmp_path, template, sha, name=name)
        makefile = dest / "Makefile"
        makefile.write_text(makefile.read_text() + edit, encoding="utf-8")

        code, out, err = _run([str(dest), "--today", TODAY, "--json"], capsys)
        report = json.loads(out)
        w = report["groups"]["W"]
        assert [f["tier"] for f in w] == ["error"], (name, w)
        assert w[0]["resolved_by"].startswith("copier update"), (name, w)
        origin = "template-edited" if edit else "template-unedited"
        assert w[0]["origin"] == origin, (name, w)
        assert report["summary"]["errors"] == 0, (name, report["summary"])
        assert report["summary"]["resolved_by_update"] == 1, (name, report["summary"])
        assert report["summary"]["counts"]["W"]["resolved_by_update"] == 1
        assert report["summary"]["conflicts"] == 0, (name, report["groups"])
        assert (code, report["exit"]) == (0, 0), (name, err)
        _c, text, _e = _run([str(dest), "--today", TODAY], capsys)
        assert "[W] 1 error(s) (1 resolved by the update)" in text, text
        assert "0 error(s) owed, 1 resolved by the update" in text, text
    assert _scratch_left(tmp_path) == []


def test_a_file_copier_would_conflict_on_is_reported_not_judged(
    tmp_path, template, capsys
):
    """The project and the template changed the same line: copier leaves
    conflict markers, which no check may parse. The file is reported in the
    conflict group, judged as DEST holds it, and its findings are not counted."""
    sha = _template_commits(
        template,
        {"config/project.json.jinja": _TWIN, "Makefile": _GUARD + _LABELLED + _TAIL},
        {"Makefile": _GUARD + "planted: ## [local] Does it better\n\t@true\n" + _TAIL},
    )
    dest = _generated(tmp_path, template, sha)
    (dest / "Makefile").write_text(_GUARD + _PLANTED + _TAIL, encoding="utf-8")

    code, out, err = _run([str(dest), "--today", TODAY, "--json"], capsys)
    report = json.loads(out)
    conflict = report["groups"]["conflict"]
    assert [(f["tier"], f["path"]) for f in conflict] == [("warning", "Makefile")]
    assert conflict[0]["message"].startswith(
        "Makefile: copier update leaves a conflict"
    )
    assert report["summary"]["conflicts"] == 1
    w = report["groups"]["W"]
    assert [(f["tier"], f.get("unjudged")) for f in w] == [("error", "conflict")], w
    assert report["summary"]["errors"] == 0, report["summary"]
    assert (code, report["exit"]) == (0, 0), err
    for g in ap.LETTERS:
        for f in report["groups"][g]:
            assert "<<<<<<<" not in f["message"], f
    _c, text, _e = _run([str(dest), "--today", TODAY], capsys)
    assert "1 conflicted file(s) not judged" in text, text


_BETTER = "planted: ## [local] Does it better\n\t@true\n"
_X = "x: ## [local] X\n\t@true\n"


@pytest.mark.parametrize(
    "x_lands, owed_x",
    [
        # The update's target lands in lines copier merges cleanly: it is in
        # the tree however the conflict is resolved, so its manifest entry is
        # not stale.
        ("clean", False),
        # The update's target lands inside the conflict hunk: kept the
        # project's way it is gone and its entry is stale, kept the template's
        # way it is there. The finding depends on the resolution: not judged.
        ("in-conflict", None),
    ],
)
def test_a_finding_beside_a_conflict_is_judged_on_both_resolutions(
    tmp_path, template, capsys, x_lands, owed_x
):
    """A conflict in the Makefile must not put the pre-update Makefile next to
    the post-update manifest: check_W reads the Makefile but reports the
    manifest's stale `effect_proof_skip` entry against config/project.json, a
    file copier merged cleanly. The tree is judged with every conflict hunk the
    project's way and again the template's way: a finding in both is owed (the
    entry `y`, whose target no side defines), one in only one depends on how
    the conflict is resolved and is not judged, one in neither is absent."""
    if x_lands == "clean":
        theirs_makefile = _GUARD + _BETTER + _TAIL + "\n" + _X
    else:
        theirs_makefile = _GUARD + _BETTER + _X + _TAIL
    sha = _template_commits(
        template,
        {"config/project.json.jinja": _TWIN, "Makefile": _GUARD + _PLANTED + _TAIL},
        {
            "config/project.json.jinja": _twin(
                effect_proof_skip={"x": "reason", "y": "reason"}
            ),
            "Makefile": theirs_makefile,
        },
    )
    dest = _generated(tmp_path, template, sha)
    (dest / "Makefile").write_text(_GUARD + _LABELLED + _TAIL, encoding="utf-8")

    code, out, err = _run([str(dest), "--today", TODAY, "--json"], capsys)
    report = json.loads(out)
    assert [f["path"] for f in report["groups"]["conflict"]] == ["Makefile"]
    w = {
        re.search(r"`(\w+)`", f["message"]).group(1): f
        for f in _errors(report, "W")
        if f["message"].startswith("config/project.json:")
    }
    assert sorted(w) == (["y"] if owed_x is False else ["x", "y"]), w
    assert "unjudged" not in w["y"] and "resolved_by" not in w["y"], w
    if owed_x is None:
        assert w["x"]["unjudged"] == "conflict", w
    assert report["summary"]["errors"] == 1, report["summary"]
    assert (code, report["exit"]) == (1, 1), err
    for g in ap.LETTERS:
        for f in report["groups"][g]:
            assert "<<<<<<<" not in f["message"], f
    assert _scratch_left(tmp_path) == []


_CONFLICTED = (
    b"keep 1\n"
    b"<<<<<<< before updating\n"
    b"project 1\n"
    b"=======\n"
    b"template 1\n"
    b">>>>>>> after updating\n"
    b"keep 2\n"
    b"<<<<<<< before updating\n"
    b"project 2\n"
    b"||||||| last update\n"
    b"base 2\n"
    b"=======\n"
    b">>>>>>> after updating\n"
)


@pytest.mark.parametrize(
    "side, want",
    [
        ("project", b"keep 1\nproject 1\nkeep 2\nproject 2\n"),
        ("template", b"keep 1\ntemplate 1\nkeep 2\n"),
    ],
)
def test_resolve_conflict_keeps_one_side_of_every_hunk(side, want):
    """Each hunk copier writes (the diff3 base section too) resolves to one
    side; what copier merged cleanly outside the hunks stays either way."""
    assert ap.resolve_conflict(_CONFLICTED, side) == want


@pytest.mark.parametrize(
    "data",
    [
        b"<<<<<<< before updating\nx\n=======\ny\n",
        b"x\n>>>>>>> after updating\n",
        b"<<<<<<< before updating\n<<<<<<< before updating\n",
    ],
    ids=["unclosed", "stray-close", "nested"],
)
def test_resolve_conflict_refuses_markers_copier_does_not_write(data):
    """A guess at a malformed hunk would judge a tree no resolution makes."""
    with pytest.raises(ValueError):
        ap.resolve_conflict(data, "project")


@pytest.mark.parametrize(
    "state, refused",
    [
        ("committed", None),
        ("modified", "dirty"),
        ("untracked", "dirty"),
        ("no-git", "git"),
    ],
)
def test_an_update_copier_would_refuse_is_named(
    tmp_path, template, capsys, state, refused
):
    """The scratch copy is committed, so copier updates it whatever DEST's git
    state; the real update refuses a DEST with uncommitted changes and one
    outside git. The config group warns of that refusal, naming each
    uncommitted path, and the prediction still stands: no exit change."""
    sha = _template_commits(template, {"config/project.json.jinja": _TWIN}, {})
    dest = _generated(tmp_path, template, sha)
    if state != "no-git":
        _commit_dest(dest)
    if state == "modified":
        readme = dest / "docs" / "README.md"
        readme.write_text(readme.read_text() + "\nlocal\n")
    elif state == "untracked":
        (dest / "docs" / "notes.txt").write_text("x\n")

    code, out, err = _run([str(dest), "--today", TODAY, "--json"], capsys)
    report = json.loads(out)
    refusals = [c for c in report["groups"]["config"] if c["kind"] == "update-refused"]
    if refused is None:
        assert refusals == [], refusals
    else:
        assert [c["tier"] for c in refusals] == ["warning"], refusals
        assert refused in refusals[0]["message"], refusals
        assert "copier update" in refusals[0]["message"], refusals
    if state == "modified":
        assert refusals[0]["paths"] == ["docs/README.md"], refusals
    if state == "untracked":
        assert refusals[0]["paths"] == ["docs/notes.txt"], refusals
    assert code == report["exit"], err
    _c, text, _e = _run([str(dest), "--today", TODAY], capsys)
    if refused is not None:
        assert refusals[0]["message"] in text, text


def test_without_a_base_the_project_is_judged_as_it_stands(tmp_path, template, capsys):
    """`_commit` resolves nowhere: copier cannot update either, so nothing is
    predicted and no scratch is made. DEST's own config names nothing stale, so
    a key only the template has must not reach the checks."""
    (template / "config" / "project.json.jinja").write_text(
        _twin(effect_proof_skip={"x": "reason"}), encoding="utf-8"
    )
    dest = _dest(tmp_path, template, manifest={"name": "demo", "make_targets": _POLICY})
    (dest / "Makefile").write_text(_MAKEFILE, encoding="utf-8")

    code, out, err = _run([str(dest), "--today", TODAY, "--json"], capsys)
    report = json.loads(out)
    assert _errors(report, "W") == [], report["groups"]["W"]
    arrivals = [c["key"] for c in report["groups"]["config"] if c["kind"] == "arrives"]
    assert "make_targets.effect_proof_skip.x" in arrivals, report["groups"]["config"]
    assert {c["tier"] for c in report["groups"]["config"]} == {"info"}
    assert any(i["item"].startswith("no base") for i in report["not_checked"])
    assert report["base"]["resolved"] is None
    assert (code, report["exit"]) == (0, 0), err
    assert _scratch_left(tmp_path) == []


def test_a_failed_update_is_exit_2_and_leaves_no_scratch(tmp_path, template, capsys):
    """A copier update that fails (here: the template needs a copier that does
    not exist) is a report the audit cannot build: exit 2 naming copier, the
    scratch path masked, nothing printed on stdout and nothing left behind."""
    sha = _template_commits(template, {"config/project.json.jinja": _TWIN}, {})
    dest = _generated(tmp_path, template, sha)
    (template / "copier.yml").write_text(
        "_min_copier_version: '999'\n" + _COPIER_YML, encoding="utf-8"
    )
    _git(template, "commit", "-q", "-am", "needs a copier that does not exist")
    before = _snapshot(dest)

    code, out, err = _run([str(dest), "--today", TODAY], capsys)
    assert code == 2, out + err
    assert out == ""
    assert "copier" in err and "<scratch>" in err, err
    assert str(tmp_path / "systmp") not in err, err
    assert _scratch_left(tmp_path) == []
    assert _snapshot(dest) == before


# --- a migration that refuses over a conflicted import ----------------------------

# A fake `after` migration: the guard every keel job runs first, then the import
# it guards. *job* and *rerun* are what it names; *body* what it imports.
_JOB = """\
import os
import sys

_JOBS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [_JOBS, os.path.dirname(_JOBS)]
import conflict_guard  # noqa: E402

conflict_guard.exit_if_conflicted(
    __file__, os.getcwd(), %r, %r, search_path=[_JOBS, os.path.dirname(_JOBS)]
)
%s
"""


def _migrating_template(template, jobs, theirs):
    """The fake template with one `after` migration per (stem, rerun, imports
    dep) in *jobs*, in order, the real conflict_guard beside them, and
    scripts/dep.py; the base tagged v0.1.0 and *theirs* committed over it as
    v0.2.0 (copier runs migrations only between two versions). Returns the
    base's tag, which a generated DEST records as its `_commit`."""
    migrations = "".join(
        '  - command: ["{{ _copier_python }}", "scripts/jobs/%s.py"]\n'
        "    when: \"{{ _stage == 'after' }}\"\n" % stem
        for stem, _rerun, _dep in jobs
    )
    base = {
        "copier.yml": _COPIER_YML + "_migrations:\n" + migrations,
        "config/project.json.jinja": _TWIN,
        "scripts/dep.py": "VALUE = 1\n",
        "scripts/jobs/conflict_guard.py": (
            _ROOT / "scripts" / "jobs" / "conflict_guard.py"
        ).read_text(encoding="utf-8"),
    }
    for stem, rerun, dep in jobs:
        base["scripts/jobs/%s.py" % stem] = _JOB % (
            stem,
            rerun,
            "import dep  # noqa: E402,F401" if dep else "",
        )
    sha = _template_commits(template, base, {})
    _git(template, "tag", "v0.1.0", sha)
    for rel, text in theirs.items():
        (template / rel).write_text(text, encoding="utf-8")
    _git(template, "add", "-A")
    _git(template, "commit", "-q", "-m", "theirs")
    _git(template, "tag", "v0.2.0")
    return "v0.1.0"


def _refused(report):
    return [i for i in report["not_checked"] if i["item"].startswith("migration ")]


def test_a_migration_refusing_over_a_conflict_the_update_leaves_is_not_checked(
    tmp_path, template, capsys
):
    """copier stops at the first `after` migration that refuses, and the real
    update of this project will refuse the same way: the audit reports the tree
    copier leaves, names the job and its rerun under not checked, and exits on
    the findings, never 2 (bedrock-platform's restamp over its edited
    check_structure.py, docs/design/downstream-feedback.md)."""
    tag = _migrating_template(
        template, [("job", "make job", True)], {"scripts/dep.py": "VALUE = 2\n"}
    )
    dest = _generated(tmp_path, template, tag)
    (dest / "scripts" / "dep.py").write_text("VALUE = 3\n", encoding="utf-8")

    code, out, err = _run([str(dest), "--today", TODAY, "--json"], capsys)
    assert code in (0, 1), err
    report = json.loads(out)
    assert code == report["exit"]
    assert [f["path"] for f in report["groups"]["conflict"]] == ["scripts/dep.py"]
    assert _refused(report) == [
        {
            "item": "migration job and every migration after it",
            "reason": "it refused over conflicted scripts/dep.py exactly as the real "
            "update will (copier stops at the first failed migration); resolve "
            "those files, then run `make job`",
        }
    ], report["not_checked"]
    _c, text, _e = _run([str(dest), "--today", TODAY], capsys)
    assert "  - migration job and every migration after it: it refused" in text
    assert _scratch_left(tmp_path) == []


def test_a_refusal_naming_a_file_the_update_did_not_conflict_is_exit_2(
    tmp_path, template, capsys
):
    """The project committed markers of its own: the update leaves no conflict
    there, so the refusal is not the update's prediction but a broken project.
    The audit cannot tell what the update would leave: exit 2, as any failed
    update."""
    tag = _migrating_template(
        template, [("job", "make job", True)], {"scripts/other.py": "X = 1\n"}
    )
    dest = _generated(tmp_path, template, tag)
    (dest / "scripts" / "dep.py").write_text(
        "%s mine\nVALUE = 3\n%s\nVALUE = 1\n%s theirs\n" % ("<" * 7, "=" * 7, ">" * 7),
        encoding="utf-8",
    )

    code, out, err = _run([str(dest), "--today", TODAY], capsys)
    assert code == 2, out + err
    assert out == ""
    assert "copier update of <scratch>" in err and "failed" in err, err
    assert "scripts/dep.py (line 1)" in err, err
    assert _scratch_left(tmp_path) == []


@pytest.mark.parametrize(
    "jobs, restamped",
    [
        # The restamp itself refuses: no stamp is rewritten.
        ([("restamp_docs", "make restamp-docs", True)], False),
        # A job before it refuses: copier never reaches the restamp.
        (
            [("job", "make job", True), ("restamp_docs", "make restamp-docs", False)],
            False,
        ),
        # The restamp ran before the job that refused: the stamps are rewritten.
        (
            [("restamp_docs", "make restamp-docs", False), ("job", "make job", True)],
            True,
        ),
    ],
    ids=["restamp-refuses", "earlier-job-refuses", "restamp-ran-first"],
)
def test_a_refused_restamp_does_not_claim_the_update_rewrites_stamps(
    tmp_path, template, capsys, jobs, restamped
):
    tag = _migrating_template(template, jobs, {"scripts/dep.py": "VALUE = 2\n"})
    dest = _generated(tmp_path, template, tag)
    (dest / "scripts" / "dep.py").write_text("VALUE = 3\n", encoding="utf-8")
    _commit_dest(dest)
    readme = dest / "docs" / "README.md"
    readme.write_text(readme.read_text() + "\nedited\n")

    code, out, err = _run([str(dest), "--today", TODAY, "--json"], capsys)
    assert code in (0, 1), err
    report = json.loads(out)
    fresh = report["groups"]["freshness"]
    stamps = report["groups"]["restamp"]
    assert [f["path"] for f in fresh] == ["docs/README.md"], fresh
    assert [f["path"] for f in stamps] == ["docs/README.md"], stamps
    if restamped:
        assert fresh[0]["resolved_by"] == ap.FRESHNESS_RESOLVED_BY
        assert "will rewrite this stamp" in stamps[0]["message"]
    else:
        assert fresh[0]["resolved_by"] != ap.FRESHNESS_RESOLVED_BY
        assert "`%s`" % ap.RESTAMP_RERUN in fresh[0]["resolved_by"], fresh
        assert "will rewrite" not in stamps[0]["message"], stamps
        assert "`%s`" % ap.RESTAMP_RERUN in stamps[0]["message"], stamps
    # Warning-tier: what names the remedy changes, not what is counted.
    assert report["summary"]["counts"]["freshness"]["resolved_by_update"] == 0


def test_the_restamp_rerun_the_audit_names_is_the_one_the_restamp_prints(tmp_path):
    """RESTAMP_RERUN is not a second copy of a fact: it is read back from what
    scripts/jobs/restamp_docs.py prints when it refuses."""
    proj = tmp_path / "proj"
    shutil.copytree(
        str(_ROOT / "scripts"),
        str(proj / "scripts"),
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    target = proj / "scripts" / "check_structure.py"
    target.write_text(
        target.read_text(encoding="utf-8")
        + "%s a\nx\n%s\ny\n%s b\n" % ("<" * 7, "=" * 7, ">" * 7),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, "scripts/jobs/restamp_docs.py", "--quiet"],
        cwd=str(proj),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    assert proc.returncode == 2, proc.stderr
    (refusal,) = ap.conflict_guard.read_refusals(proc.stderr)
    assert (refusal[0], refusal[2]) == (ap.RESTAMP_JOB, ap.RESTAMP_RERUN)


def test_a_symlink_leaving_dest_is_never_written_through(tmp_path, template, capsys):
    """Copier writes through a symlink, so a link out of DEST copied as a link
    would let the update write outside the scratch tree. The copy holds the
    target's bytes instead, and the report says so."""
    sha = _template_commits(
        template,
        {"config/project.json.jinja": _TWIN, "Makefile": _MAKEFILE},
        {"Makefile": _MAKEFILE + _TAIL},
    )
    dest = _generated(tmp_path, template, sha)
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "Makefile"
    target.write_text(_MAKEFILE, encoding="utf-8")
    (dest / "Makefile").unlink()
    os.symlink(str(target), str(dest / "Makefile"))
    before = (target.read_bytes(), target.stat().st_mtime_ns)
    link_before = _snapshot(dest)

    code, out, err = _run([str(dest), "--today", TODAY, "--json"], capsys)
    assert code in (0, 1), err
    assert (target.read_bytes(), target.stat().st_mtime_ns) == before
    assert _snapshot(dest) == link_before
    named = [i for i in json.loads(out)["not_checked"] if i["item"] == "Makefile"]
    assert named and "outside DEST" in named[0]["reason"], json.loads(out)[
        "not_checked"
    ]
    assert _scratch_left(tmp_path) == []


def test_not_checked_section_is_always_present(tmp_path, template, capsys):
    dest = _dest(tmp_path, template)
    _code, text, _err = _run([str(dest), "--today", TODAY], capsys)
    _code, out, _err = _run([str(dest), "--today", TODAY, "--json"], capsys)
    items = json.loads(out)["not_checked"]
    joined = "\n".join("%s: %s" % (i["item"], i["reason"]) for i in items)
    for needle in ("effect sweep", "test suite", "shell", "5-line cap"):
        assert needle in joined, joined
        assert needle in text
    no_git = [i for i in items if i["reason"].startswith("no git")]
    assert sorted(i["item"] for i in no_git) == ["freshness", "restamp"]
    # _commit 0000000 resolves nowhere: nothing is predicted.
    assert any(i["item"].startswith("no base") for i in items), joined
    assert "no base" in text


def test_dest_code_is_never_imported_or_run(tmp_path, template, capsys):
    """With a base that resolves, so the prediction runs: neither the audit nor
    the copy's git or copier child runs DEST's code, make targets, git hooks
    (`.git/hooks`, a `core.hooksPath`) or the commands its git config names."""
    sha = _template_commits(template, {"config/project.json.jinja": _TWIN}, {})
    dest = _generated(tmp_path, template, sha)
    sentinel = tmp_path / "sentinel"
    (dest / "scripts").mkdir()
    for name in ("check_structure.py", "child_env.py", "review_docs.py"):
        (dest / "scripts" / name).write_text(
            "raise SystemExit('DEST code was imported')\n"
        )
    (dest / "Makefile").write_text(
        _GUARD + "x: ## [local] X\n\ttouch %s.make\n" % sentinel
    )
    _commit_dest(dest)
    hook = tmp_path / "fsmonitor.sh"
    hook.write_text("#!/bin/sh\ntouch %s.fsmonitor\nexit 1\n" % sentinel)
    hook.chmod(0o755)
    _git(dest, "config", "core.fsmonitor", str(hook))
    # A clean filter DEST's config names, selected by its own attributes: git
    # status re-hashes a stat-dirty file through it unless the audit stops it.
    clean = tmp_path / "clean.sh"
    clean.write_text("#!/bin/sh\ntouch %s.filter\ncat\n" % sentinel)
    clean.chmod(0o755)
    _git(dest, "config", "filter.probe.clean", str(clean))
    (dest / ".git" / "info").mkdir(exist_ok=True)
    (dest / ".git" / "info" / "attributes").write_text("*.md filter=probe\n")
    # Every hook a commit runs, in DEST's own hooks directory and in one its
    # config names: the copy is committed, and copier commits in it too.
    for hooks in (dest / ".git" / "hooks", tmp_path / "hooks"):
        hooks.mkdir(exist_ok=True)
        for name in ("pre-commit", "post-commit", "post-checkout"):
            path = hooks / name
            path.write_text("#!/bin/sh\ntouch %s.hook\n" % sentinel)
            path.chmod(0o755)
    _git(dest, "config", "core.hooksPath", str(tmp_path / "hooks"))
    readme = dest / "docs" / "README.md"
    os.utime(str(readme), (readme.stat().st_atime, readme.stat().st_mtime + 7))
    assert not list(tmp_path.glob("sentinel*"))

    code, out, err = _run([str(dest), "--today", TODAY, "--json"], capsys)

    assert code in (0, 1), err
    assert "conflicts" in json.loads(out)["summary"]
    assert not list(tmp_path.glob("sentinel*"))
    roots = [os.path.realpath(str(p)) for p in (dest, tmp_path / "systmp")]
    for module in list(sys.modules.values()):
        path = os.path.realpath(getattr(module, "__file__", None) or "")
        for root in roots:
            assert not path.startswith(root + os.sep), path
    assert _scratch_left(tmp_path) == []


@pytest.mark.parametrize("with_base", [False, True], ids=["as-it-stands", "predicted"])
def test_audit_never_runs_dest_project_checks(tmp_path, template, capsys, with_base):
    """DEST's `structure.project_checks` modules are DEST code: the audit runs
    the template's lettered checks only, on DEST as it stands and on the copy
    an update leaves, and names what it did not run."""
    manifest = {
        "name": "demo",
        "structure": {"extra_toplevel": ["checks"], "project_checks": "checks"},
    }
    if with_base:
        sha = _template_commits(template, {"config/project.json.jinja": _TWIN}, {})
        dest = _generated(tmp_path, template, sha)
        (dest / "config" / "project.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
    else:
        dest = _dest(tmp_path, template, manifest=manifest)
    _label(dest, "checks")
    sentinel = tmp_path / "sentinel"
    (dest / "checks" / "x.py").write_text(
        "open(%r, 'w').close()\n\ndef check(root):\n    return [('error', 'x')]\n"
        % str(sentinel),
        encoding="utf-8",
    )
    _commit_dest(dest)

    code, out, err = _run([str(dest), "--today", TODAY, "--json"], capsys)

    assert code in (0, 1), err
    report = json.loads(out)
    assert not sentinel.exists()
    assert not [g for g in report["groups"] if g.startswith("project:")]
    items = [i["item"] for i in report["not_checked"]]
    assert any("structure.project_checks" in item for item in items), items


def test_dest_config_is_never_written(tmp_path, template, capsys):
    dest = _dest(tmp_path, template)
    _commit_dest(dest)
    watched = [dest / "config" / "project.json", dest / ".copier-answers.yml"]
    before = [(p.read_bytes(), p.stat().st_mtime_ns) for p in watched]
    whole = _snapshot(dest)
    _code, out, _err = _run([str(dest), "--today", TODAY, "--json"], capsys)
    assert any(c["kind"] == "arrives" for c in json.loads(out)["groups"]["config"])
    assert [(p.read_bytes(), p.stat().st_mtime_ns) for p in watched] == before
    assert _snapshot(dest) == whole


# --- the retired group: a file the update deletes ---------------------------------


def test_retired_group_flags_only_an_edited_copy_the_update_deletes(
    tmp_path, template, capsys
):
    """copier's update deletes every file the template retired, edited or not.
    The guard migration puts an edited one back; this fake template has no
    migrations at all, so nothing does, as when a later `rm` migration deletes
    a named path. The audit names the edited copy the update would delete,
    with the same rule as the guard (keep_edited_retired.is_edited): a copy
    that differs only in its `updated:` stamp is not an edit."""
    old = _FM % ("old", "doc", "docs-old")
    sha = _template_commits(
        template,
        {
            "config/project.json.jinja": _TWIN,
            "docs/edited.md": old,
            "docs/stamped.md": old.replace("docs-old", "docs-stamped"),
            "docs/plain.md": old.replace("docs-old", "docs-plain"),
        },
        {},
    )
    _git(template, "rm", "-q", "docs/edited.md", "docs/stamped.md", "docs/plain.md")
    _git(template, "commit", "-q", "-m", "retire three docs")
    dest = _generated(tmp_path, template, sha)
    edited = dest / "docs" / "edited.md"
    edited.write_text(edited.read_text().replace("owner: me", "owner: us"))
    stamped = dest / "docs" / "stamped.md"
    stamped.write_text(
        stamped.read_text().replace("updated: 2026-01-01", "updated: 2026-02-02")
    )

    code, out, err = _run([str(dest), "--today", TODAY, "--json"], capsys)
    report = json.loads(out)
    retired = report["groups"]["retired"]
    assert [(f["tier"], f["path"]) for f in retired] == [("error", "docs/edited.md")]
    assert retired[0]["message"] == (
        "the update deletes docs/edited.md, which the project edited"
    ), retired
    assert report["summary"]["counts"]["retired"]["error"] == 1, report["summary"]
    assert report["summary"]["errors"] == 1, report["summary"]
    assert (code, report["exit"]) == (1, 1), err
    _c, text, _e = _run([str(dest), "--today", TODAY], capsys)
    assert "the update deletes docs/edited.md, which the project edited" in text
