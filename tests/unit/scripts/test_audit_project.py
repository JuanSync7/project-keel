"""
title: Unit — audit_project (another project judged by this template's gates)
kind: tests
layer: n/a
summary: scripts/audit_project.py pinned against a small fake template and a keel-shaped DEST in a scratch directory. It refuses, exit 2 and naming each missing item, whatever is not a keel project; its config view is a key-level 3-way merge (arrives, updates, conflict, removed-upstream as copier's replay of the project's edits leaves them; lists atomic; `_` keys kept; inputs never mutated); the update's config is rendered in memory from the template's twin with DEST's answers and copier.yml's derived defaults; findings are grouped A..X then config, freshness and restamp, sorted, and the --json output is canonical and byte-identical across runs; the exit code follows owed letter errors only, an error in a template-unedited file being counted as resolved by the update; an unreadable file has unknown origin, and malformed or wrongly typed answers are a refusal, not a traceback; a not-checked section is always present; and DEST's code, Makefile and the commands its git config names (fsmonitor, a clean filter) are never run and its files never written. Excluded from generated projects with the doer.
"""

import copy
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import audit_project as ap  # noqa: E402

import hermetic_git  # noqa: E402

pytestmark = pytest.mark.unit

TODAY = "2026-09-02"
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
    "gate_vars": ["PY"],
}
_GUARD = (
    'WRITE_GUARD = @if [ -n "$(CI)$(RALPH)" ]; then echo "refusing $@" >&2; '
    "exit 1; fi\n"
)
_COPIER_YML = """\
_exclude:
  - "copier.yml"
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
_TWIN = """\
{
  "name": "{{ project_slug }}",
  "structure": {"extra_toplevel": []},
  "make_targets": %s,
  "practices": {"profiles": {"ai": {{ "true" if "ai" in profiles else "false" }}}}
}
""" % json.dumps(_POLICY)


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


def _dest(tmp_path, template, manifest=None, commit="0000000"):
    """A keel-shaped DEST: answers naming the fake template, a labelled tree and
    its own config/project.json (default: the name only)."""
    dest = tmp_path / "dest"
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
    assert "writes nothing" in text and "runs none" in text


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


def test_merge_is_a_key_level_three_way():
    base = {
        "same": 1,
        "tmpl_moved": "old",
        "ours_moved": "old",
        "both_moved": "old",
        "gone_upstream": 1,
        "gone_but_edited": 1,
        "deleted_by_project": 5,
        "listy": ["a", "b"],
        "nest": {"inner": 1, "keep": True},
        "_comment": "base",
    }
    ours = {
        "same": 1,
        "tmpl_moved": "old",
        "ours_moved": "mine",
        "both_moved": "mine",
        "gone_upstream": 1,
        "gone_but_edited": 2,
        "listy": ["a", "b"],
        "nest": {"inner": 1},
        "project_own": "x",
        "_comment": "ours",
    }
    theirs = {
        "same": 1,
        "tmpl_moved": "new",
        "ours_moved": "old",
        "both_moved": "theirs",
        "deleted_by_project": 5,
        "listy": ["a", "c"],
        "nest": {"inner": 2, "keep": True, "fresh": [1]},
        "arrived": {"a": 1},
        "_comment": "theirs",
    }
    inputs = copy.deepcopy((base, ours, theirs))

    merged, changes = ap.merge(base, ours, theirs)

    assert (base, ours, theirs) == inputs
    assert merged == {
        "same": 1,
        "tmpl_moved": "new",
        "ours_moved": "mine",
        "both_moved": "mine",
        # Copier replays the project's own edits onto a fresh render: a key the
        # template dropped and the project never edited is dropped with it; an
        # edited one is an edit to a line that is gone, which is a conflict.
        "gone_but_edited": 2,
        "listy": ["a", "c"],
        # The project dropped `keep`; the template did not change it, so it stays
        # dropped, as a line-level merge of the rendered file would leave it.
        "nest": {"inner": 2, "fresh": [1]},
        "project_own": "x",
        "arrived": {"a": 1},
        "_comment": "ours",
    }
    assert _kinds(changes) == {
        "tmpl_moved": "updates",
        "both_moved": "conflict",
        "gone_upstream": "removed-upstream",
        "gone_but_edited": "conflict",
        "listy": "updates",
        "nest.inner": "updates",
        "nest.fresh": "arrives",
        "arrived": "arrives",
    }
    arrived = [c for c in changes if c["key"] == "arrived"][0]
    assert arrived["theirs"] == {"a": 1}


def test_a_list_is_replaced_whole_never_merged_by_element():
    merged, changes = ap.merge({"l": [1, 2]}, {"l": [1, 2, 3]}, {"l": [1]})
    assert merged == {"l": [1, 2, 3]} and _kinds(changes) == {"l": "conflict"}


def test_without_a_base_only_arrivals_are_reported():
    merged, changes = ap.merge(
        None, {"a": 1, "b": {"c": 1}}, {"a": 2, "b": {"c": 2, "d": 3}, "e": 4}
    )
    assert merged == {"a": 1, "b": {"c": 1, "d": 3}, "e": 4}
    assert _kinds(changes) == {"b.d": "arrives", "e": "arrives"}


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
    dest = _dest(tmp_path, template)
    _plant_b_and_w(dest)
    argv = [str(dest), "--today", TODAY]

    code, text, err = _run(argv, capsys)
    assert code == 1, err
    headers = re.findall(r"^\[([A-Za-z]+)\]", text, re.MULTILINE)
    assert headers == [chr(c) for c in range(ord("A"), ord("X") + 1)] + [
        "config",
        "freshness",
        "restamp",
    ]
    b_block = text.split("[B]", 1)[1].split("[C]", 1)[0]
    w_block = text.split("[W]", 1)[1].split("[X]", 1)[0]
    assert "zzz" in b_block and "planted" in w_block
    config_block = text.split("[config]", 1)[1].split("[freshness]", 1)[0]
    lines = [ln for ln in config_block.splitlines()[1:] if ln.strip()]
    assert lines == sorted(lines) and any("make_targets" in ln for ln in lines)

    _c1, first, _e1 = _run(argv + ["--json"], capsys)
    _c2, second, _e2 = _run(argv + ["--json"], capsys)
    assert first == second
    report = json.loads(first)
    assert (
        json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n" == first
    )
    assert report["summary"]["checks_run"] == [
        chr(c) for c in range(ord("A"), ord("X") + 1)
    ]
    assert report["summary"]["files_seen"] > 0
    assert [f["tier"] for f in report["groups"]["B"]] == ["error"]
    assert [f["tier"] for f in report["groups"]["W"]] == ["error"]
    for output in (text, first):
        rest = output.replace(os.path.realpath(str(dest)), "DEST")
        assert str(tmp_path) not in rest and os.path.realpath(str(tmp_path)) not in rest


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
        ap.check_structure, "run_checks", lambda root, overrides=None: list(emitted)
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


def test_an_error_in_a_file_the_update_replaces_is_not_owed(tmp_path, template, capsys):
    """The audit answers "what does this project owe after the update". A
    finding in a file the project never edited (its bytes equal the template's
    at `_commit`) is replaced by the update, so it is reported as resolved by
    the update and neither counts as owed nor fails the exit; the same defect
    in a file the project edited is owed."""
    makefile = _GUARD + "planted: ## Does a thing\n\t@true\n"
    (template / "Makefile").write_text(makefile, encoding="utf-8")
    _commit_dest(template)
    sha = _git(template, "rev-parse", "HEAD").strip()
    rendered, _notes = ap.render_configs(
        ap.worktree_reader(str(template)), {"project_name": "Demo", "profiles": []}
    )
    dest = _dest(tmp_path, template, rendered["config/project.json"], commit=sha)
    (dest / "Makefile").write_text(makefile, encoding="utf-8")

    code, out, err = _run([str(dest), "--today", TODAY, "--json"], capsys)
    report = json.loads(out)
    w = report["groups"]["W"]
    assert [(f["tier"], f["origin"]) for f in w] == [("error", "template-unedited")]
    assert w[0]["resolved_by"].startswith("copier update"), w
    assert report["summary"]["errors"] == 0, report["summary"]
    assert report["summary"]["resolved_by_update"] == 1
    assert report["summary"]["counts"]["W"]["resolved_by_update"] == 1
    assert (code, report["exit"]) == (0, 0), err
    _c, text, _e = _run([str(dest), "--today", TODAY], capsys)
    assert "[W] 1 error(s) (1 resolved by the update)" in text, text
    assert "0 error(s) owed, 1 resolved by the update" in text, text

    (dest / "Makefile").write_text(makefile + "# edited\n", encoding="utf-8")
    code, out, _err = _run([str(dest), "--today", TODAY, "--json"], capsys)
    report = json.loads(out)
    w = report["groups"]["W"]
    assert [(f["tier"], f["origin"]) for f in w] == [("error", "template-edited")]
    assert "resolved_by" not in w[0]
    assert (report["summary"]["errors"], report["summary"]["resolved_by_update"]) == (
        1,
        0,
    )
    assert code == 1


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
    assert "base" in joined  # _commit 0000000 resolves nowhere: a 2-way merge


def test_dest_code_is_never_imported_or_run(tmp_path, template, capsys):
    dest = _dest(tmp_path, template)
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
    readme = dest / "docs" / "README.md"
    os.utime(str(readme), (readme.stat().st_atime, readme.stat().st_mtime + 7))
    assert not list(tmp_path.glob("sentinel*"))

    code, _out, err = _run([str(dest), "--today", TODAY], capsys)

    assert code in (0, 1), err
    assert not list(tmp_path.glob("sentinel*"))
    root = os.path.realpath(str(dest))
    for module in list(sys.modules.values()):
        path = getattr(module, "__file__", None) or ""
        assert not os.path.realpath(path).startswith(root + os.sep), path


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
