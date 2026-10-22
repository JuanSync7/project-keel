"""
title: Unit — apply_refactor (edit application and its default gate)
kind: tests
layer: n/a
summary: apply_one applies a search/replace only when the target text occurs EXACTLY once, so a refactor edit is unambiguous — zero or multiple matches raise before anything is written. plan_edits refuses, before any write and so in a dry run too, an edit to a path the root's config/project.json `agents` block protects (a protected path covers everything under it, a protected name or glob covers each file name it matches anywhere, an editable name carves a README.md back out), judged on the path as written and on its realpath, case-folded, so a symlink, a directory link, a case variant, a new file and a full `content` replacement are refused alike; git's own state, a nested .gitignore, .gitattributes, the frontend tests and configs the default stack ships, a root conftest.py, the .jinja twins of .gitignore and .copier-answers.yml and make check-openapi's checker are each refused; every template twin of a protected file is itself protected, derived from git's own list, with a fault-injection twin; a file git does not track (.venv, node_modules, an untracked source file, git's state even with its entry removed) and a root outside a git work tree are refused before any write; `src/m.py` and `./src/m.py` compose as one file; an absolute path, a `..` part and a hard-linked file are refused outright; removing an entry from the config lets that edit apply, so the config and not a literal drives the refusal; and an unusable policy (no file, no block, an empty map, a blank reason, a `..` key, a map that leaves config/project.json uncovered) is a config fault the CLI returns as ExitCode.CONFIG. The default gate is scripts/run_make_target.py, so a refused gate (a target labelled wider than a gate may run) and a gate that changed the tree are both red and roll the edit back, and so is a gate that raises any exception. The gate is the caller's: a spec that names a gate, or holds any key outside its closed vocabulary, is refused before any write, an empty gate is refused rather than defaulted, and the CLI's --gate defaults to verify; repeated --allow binds a run to those files, so an edit to any other is refused and an empty binding refuses every edit.
"""

import json
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "tests"))

import apply_refactor as ar  # noqa: E402
import check_structure as cs  # noqa: E402
import config_loader  # noqa: E402
from exit_codes import ExitCode  # noqa: E402

import hermetic_git  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _hermetic_git(tmp_path_factory, monkeypatch):
    """Every git call here, the doer's own included, under the hermetic git
    config: the doer takes its environment from child_env, which copies
    GIT_CONFIG_* from os.environ."""
    work = tmp_path_factory.mktemp("git-home")
    for key, value in hermetic_git.git_env_vars(work).items():
        monkeypatch.setenv(key, value)


def _git(root, *argv):
    subprocess.run(
        ["git", *argv], cwd=str(root), check=True, capture_output=True, env=os.environ
    )


def _track(root, rel):
    """Make *root* a git work tree if it is not one, and track *rel* in it:
    the doer edits only a file git tracks."""
    if not (root / ".git").exists():
        _git(root, "init", "-q")
    _git(root, "add", "--", rel)


def test_apply_one_replaces_a_unique_match():
    assert ar.apply_one("a = 1\nb = 2\n", "b = 2", "b = 3") == "a = 1\nb = 3\n"


def test_apply_one_raises_when_not_present():
    with pytest.raises(ar.RefactorError):
        ar.apply_one("x = 1\n", "nope", "y")


def test_apply_one_raises_on_ambiguous_match():
    with pytest.raises(ar.RefactorError):
        ar.apply_one("pass\npass\n", "pass", "return")


def test_apply_one_preserves_the_rest_of_the_text():
    src = "class C:\n    pass\n"
    out = ar.apply_one(src, "    pass", "    __slots__ = ()")
    assert out == "class C:\n    __slots__ = ()\n"


# --- the default gate is the read-only gate runner ------------------------------


def _template_agents():
    """The template's own `agents` block, read, never typed, so a test of the
    policy follows the shipped seed."""
    manifest = json.loads((_ROOT / "config" / "project.json").read_text("utf-8"))
    return manifest["agents"]


def _policy_tree(root, agents=None):
    """Write *root*/config/project.json holding only an `agents` block: the
    template's, or *agents* when given."""
    block = _template_agents() if agents is None else agents
    path = root / "config" / "project.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"agents": block}, indent=2), encoding="utf-8")
    _track(root, "config/project.json")
    return path


def _spec(tmp_path):
    _policy_tree(tmp_path)
    f = _plant(tmp_path, "m.py")
    return f, {"edits": [{"file": "m.py", "find": "keep = 1", "replace": "keep = 2"}]}


def _fake_run_target(result):
    calls = []

    def run_target(
        target, cwd=None, timeout=None, extra=None, runner=None, snapshot=None
    ):
        calls.append((target, cwd, timeout))
        return dict(result, target=target)

    run_target.calls = calls
    return run_target


def test_no_timeout_leaves_the_limit_to_the_configured_one(tmp_path, monkeypatch):
    """apply_and_gate passes None, so run_make_target reads
    make_targets.gate_timeout_seconds rather than a number fixed here."""
    _f, spec = _spec(tmp_path)
    fake = _fake_run_target(
        {"ok": True, "returncode": 0, "output": "", "changed": [], "refused": None}
    )
    monkeypatch.setattr(ar.run_make_target, "run_target", fake)
    ar.apply_and_gate(spec, str(tmp_path), gate="check")
    assert fake.calls == [("check", str(tmp_path), None)]


def test_the_default_gate_goes_through_run_make_target(tmp_path, monkeypatch):
    f, spec = _spec(tmp_path)
    fake = _fake_run_target(
        {
            "ok": True,
            "returncode": 0,
            "output": "green\n",
            "changed": [],
            "refused": None,
        }
    )
    monkeypatch.setattr(ar.run_make_target, "run_target", fake)
    res = ar.apply_and_gate(spec, str(tmp_path), gate="check", timeout=7)
    assert fake.calls == [("check", str(tmp_path), 7)]
    assert res["applied"] is True and f.read_text(encoding="utf-8") == "keep = 2\n"


def test_a_refused_gate_is_red_and_rolls_back(tmp_path, monkeypatch):
    f, spec = _spec(tmp_path)
    fake = _fake_run_target(
        {
            "ok": False,
            "returncode": None,
            "output": "run_make_target: refused: `make fmt` is labelled [tree]",
            "changed": [],
            "refused": "`make fmt` is labelled [tree]",
        }
    )
    monkeypatch.setattr(ar.run_make_target, "run_target", fake)
    res = ar.apply_and_gate(spec, str(tmp_path), gate="fmt")
    assert res["rolled_back"] is True and res["applied"] is False
    assert "[tree]" in res["gate_output"]
    assert f.read_text(encoding="utf-8") == "keep = 1\n"


def test_a_gate_that_dirtied_the_tree_is_red_and_names_the_paths(tmp_path, monkeypatch):
    f, spec = _spec(tmp_path)
    fake = _fake_run_target(
        {
            "ok": False,
            "returncode": 0,
            "output": "ok\n",
            "changed": ["wiki/x.json"],
            "refused": None,
        }
    )
    monkeypatch.setattr(ar.run_make_target, "run_target", fake)
    res = ar.apply_and_gate(spec, str(tmp_path), gate="check")
    assert res["rolled_back"] is True and "wiki/x.json" in res["gate_output"]
    assert f.read_text(encoding="utf-8") == "keep = 1\n"


def _raise(exc):
    def gate_runner(gate, cwd, timeout):
        raise exc

    return gate_runner


@pytest.mark.parametrize(
    "exc",
    [
        ar.run_make_target.child_env.ChildEnvError("child_env.names: bad"),
        KeyError("result"),
        RuntimeError("gate crashed"),
    ],
    ids=["child-env-error", "key-error", "runtime-error"],
)
def test_a_gate_that_raises_anything_is_red_and_rolls_back(tmp_path, exc):
    """The rollback contract is "a non-returning gate never leaves an ungated
    write behind", so it cannot depend on which exception type the gate raised."""
    f, spec = _spec(tmp_path)
    res = ar.apply_and_gate(spec, str(tmp_path), gate="check", gate_runner=_raise(exc))
    assert res["rolled_back"] is True and res["applied"] is False
    assert type(exc).__name__ in res["gate_output"]
    assert f.read_text(encoding="utf-8") == "keep = 1\n"


# --- an agent edit cannot reach the code that judges it ------------------------

_KEEP = "keep = 1\n"


def _plant(root, rel, text=_KEEP, track=True):
    """Write *rel* under *root* and, unless *track* is false, track it, so a
    refusal a test expects is the rule's and never the tracked-file rule's."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if track:
        _track(root, rel)
    return path


def _snapshot(root):
    """Every entry under *root* (links not followed), and each regular file's
    bytes and modification time, so a refused edit is proven to write nothing."""
    entries, files = set(), {}
    for top, dirs, names in os.walk(str(root), followlinks=False):
        for name in dirs + names:
            path = os.path.join(top, name)
            entries.add(os.path.relpath(path, str(root)))
            if name in names and not os.path.islink(path):
                with open(path, "rb") as fh:
                    files[path] = (fh.read(), os.stat(path).st_mtime_ns)
    return entries, files


def _edit(rel, find="keep = 1", replace="keep = 2"):
    return {"edits": [{"file": rel, "find": find, "replace": replace}]}


def _case_path(root):
    _plant(root, "scripts/check_structure.py")
    return _edit("scripts/check_structure.py"), "agents.protected_paths.scripts"


def _case_tests(root):
    _plant(root, "tests/test_x.py")
    return _edit("tests/test_x.py"), "agents.protected_paths.tests"


def _case_makefile(root):
    _plant(root, "Makefile")
    return _edit("Makefile"), "agents.protected_names.Makefile"


def _case_sub_makefile(root):
    _plant(root, "sub/Makefile")
    return _edit("sub/Makefile"), "agents.protected_names.Makefile"


def _case_lower_makefile(root):
    _plant(root, "makefile")
    return _edit("makefile"), "agents.protected_names.makefile"


def _case_upper_makefile(root):
    _plant(root, "MAKEFILE")
    return _edit("MAKEFILE"), "agents.protected_names.makefile"


def _case_upper_dir(root):
    _plant(root, "SCRIPTS/x.py")
    return _edit("SCRIPTS/x.py"), "agents.protected_paths.scripts"


def _case_self(root):
    return (
        _edit("config/project.json", find='"protected_paths"', replace='"gone"'),
        "agents.protected_paths.config",
    )


def _case_practices(root):
    _plant(root, "config/practices.json")
    return _edit("config/practices.json"), "agents.protected_paths.config"


def _case_adr(root):
    _plant(root, "docs/adr/keel/K-0001-x.md")
    return _edit("docs/adr/keel/K-0001-x.md"), "agents.protected_paths.docs/adr"


def _case_agent_md(root):
    _plant(root, "AGENT.md")
    return _edit("AGENT.md"), "agents.protected_names.AGENT.md"


def _case_claude_symlink(root):
    _plant(root, "AGENT.md")
    os.symlink("AGENT.md", str(root / "CLAUDE.md"))
    return _edit("CLAUDE.md"), "agents.protected_names.CLAUDE.md"


def _case_file_symlink(root):
    _plant(root, "scripts/check_structure.py")
    (root / "docs").mkdir()
    os.symlink("../scripts/check_structure.py", str(root / "docs" / "notes.md"))
    return _edit("docs/notes.md"), "agents.protected_paths.scripts"


def _case_dir_symlink(root):
    _plant(root, "tests/test_x.py")
    (root / "docs").mkdir()
    os.symlink("../tests", str(root / "docs" / "dirlink"))
    return _edit("docs/dirlink/test_x.py"), "agents.protected_paths.tests"


def _case_content(root):
    _plant(root, "scripts/apply_refactor.py")
    spec = {"edits": [{"file": "scripts/apply_refactor.py", "content": "pass\n"}]}
    return spec, "agents.protected_paths.scripts"


def _case_new_file(root):
    (root / "scripts").mkdir()
    return {
        "edits": [{"file": "scripts/new.py", "content": "pass\n"}]
    }, "agents.protected_paths.scripts"


def _case_hard_link(root):
    target = _plant(root, "tests/t.py")
    (root / "src").mkdir()
    os.link(str(target), str(root / "src" / "a.py"))
    return _edit("src/a.py"), "hard links"


def _case_git_config(root):
    # core.fsmonitor in .git/config runs inside the gate's own `git status`.
    text = (root / ".git" / "config").read_text(encoding="utf-8")
    spec = {"edits": [{"file": ".git/config", "content": text + "[core]\n"}]}
    return spec, "agents.protected_paths..git"


def _case_git_hook(root):
    _plant(root, ".git/hooks/pre-commit", track=False)
    return _edit(".git/hooks/pre-commit"), "agents.protected_paths..git"


def _case_gitignore(root):
    _plant(root, "src/.gitignore")
    return _edit("src/.gitignore"), "agents.protected_names..gitignore"


def _case_gitattributes(root):
    _plant(root, ".gitattributes")
    return _edit(".gitattributes"), "agents.protected_names..gitattributes"


def _case_unit_test(root):
    _plant(root, "src/frontend/app/src/App.test.tsx")
    return (
        _edit("src/frontend/app/src/App.test.tsx"),
        "agents.protected_names.*.test.*",
    )


def _case_e2e_spec(root):
    _plant(root, "src/frontend/app/e2e/counter.spec.ts")
    return (
        _edit("src/frontend/app/e2e/counter.spec.ts"),
        "agents.protected_names.*.spec.*",
    )


def _case_tsconfig_app(root):
    _plant(root, "src/frontend/app/tsconfig.app.json")
    return (
        _edit("src/frontend/app/tsconfig.app.json"),
        "agents.protected_names.tsconfig*.json",
    )


def _case_lockfile(root):
    _plant(root, "src/frontend/app/package-lock.json")
    return (
        _edit("src/frontend/app/package-lock.json"),
        "agents.protected_names.package-lock.json",
    )


def _case_conftest(root):
    _plant(root, "conftest.py")
    return _edit("conftest.py"), "agents.protected_names.conftest.py"


def _case_gitignore_twin(root):
    _plant(root, ".gitignore.jinja")
    return _edit(".gitignore.jinja"), "agents.protected_paths..gitignore.jinja"


def _case_answers_twin(root):
    _plant(root, ".copier-answers.yml.jinja")
    return (
        _edit(".copier-answers.yml.jinja"),
        "agents.protected_paths..copier-answers.yml.jinja",
    )


def _case_openapi_checker(root):
    _plant(root, "api/rest_fastapi/export_openapi.py")
    return (
        _edit("api/rest_fastapi/export_openapi.py"),
        "agents.protected_paths.api/rest_fastapi/export_openapi.py",
    )


_PROTECTED_CASES = {
    "path": _case_path,
    "tests-path": _case_tests,
    "name": _case_makefile,
    "name-in-a-subdirectory": _case_sub_makefile,
    "lower-makefile": _case_lower_makefile,
    "case-of-a-name": _case_upper_makefile,
    "case-of-a-path": _case_upper_dir,
    "the-policy-itself": _case_self,
    "practices": _case_practices,
    "adr": _case_adr,
    "agent-md": _case_agent_md,
    "claude-md-symlink": _case_claude_symlink,
    "file-symlink-into-scripts": _case_file_symlink,
    "directory-symlink-into-tests": _case_dir_symlink,
    "content-replacement": _case_content,
    "new-file-under-a-protected-dir": _case_new_file,
    "hard-link-to-a-test": _case_hard_link,
    "git-config": _case_git_config,
    "git-hook": _case_git_hook,
    "nested-gitignore": _case_gitignore,
    "gitattributes": _case_gitattributes,
    "frontend-unit-test": _case_unit_test,
    "frontend-e2e-spec": _case_e2e_spec,
    "tsconfig-app": _case_tsconfig_app,
    "frontend-lockfile": _case_lockfile,
    "root-conftest": _case_conftest,
    "gitignore-twin": _case_gitignore_twin,
    "copier-answers-twin": _case_answers_twin,
    "openapi-checker-outside-scripts": _case_openapi_checker,
}


def _refusal(exc_info):
    return str(exc_info.value)


@pytest.mark.parametrize("case", sorted(_PROTECTED_CASES))
def test_a_planted_edit_to_each_protected_class_is_refused_before_any_write(
    tmp_path, case, capsys
):
    _policy_tree(tmp_path)
    spec, rule = _PROTECTED_CASES[case](tmp_path)
    rel = spec["edits"][0]["file"]
    before = _snapshot(tmp_path)
    with pytest.raises(ar.RefactorError) as plan:
        ar.plan_edits(spec, str(tmp_path))
    with pytest.raises(ar.RefactorError) as applied:
        ar.apply_and_gate(spec, str(tmp_path), gate="none")
    for text in (_refusal(plan), _refusal(applied)):
        assert "edit 0" in text and rel in text, text
        assert rule.casefold() in text.casefold(), text
    spec_file = tmp_path.parent / ("%s-spec.json" % case)
    spec_file.write_text(json.dumps(spec), encoding="utf-8")
    argv = ["--spec", str(spec_file), "--root", str(tmp_path), "--gate", "none"]
    assert ar.main(argv + ["--dry-run"]) == ExitCode.USAGE
    assert ar.main(argv) == ExitCode.USAGE
    assert rule.casefold() in capsys.readouterr().err.casefold()
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "section, name, rel",
    [
        ("protected_paths", "scripts", "scripts/check_structure.py"),
        ("protected_names", "Makefile", "Makefile"),
        ("protected_names", "*.test.*", "src/App.test.tsx"),
    ],
    ids=["path", "name", "glob"],
)
def test_removing_a_protection_from_config_lets_that_edit_apply(
    tmp_path, section, name, rel
):
    """The control: the refusal is read from the config. Every key that
    case-folds to the removed one goes with it, because matching is
    case-folded (`Makefile` and `makefile` are one protection)."""
    agents = _template_agents()
    agents[section] = {
        k: v for k, v in agents[section].items() if k.casefold() != name.casefold()
    }
    _policy_tree(tmp_path, agents)
    target = _plant(tmp_path, rel)
    with pytest.raises(ar.RefactorError):
        ar.plan_edits(_edit(rel), str(tmp_path), policy=ar.load_policy(str(_ROOT)))
    res = ar.apply_and_gate(_edit(rel), str(tmp_path), gate="none")
    assert res["applied"] is True, res
    assert target.read_text(encoding="utf-8") == "keep = 2\n"


def _template_twins():
    """Every template twin keel tracks, as (twin, the file it renders), read from
    git and the suffix copier.yml `_templates_suffix` and check_structure share."""
    suffix = cs._TWIN_SUFFIX
    out = subprocess.run(
        ["git", "ls-files", "-z", "--", "*" + suffix],
        cwd=str(_ROOT),
        check=True,
        capture_output=True,
        env=os.environ,
    ).stdout.decode("utf-8")
    return [(t, t[: -len(suffix)]) for t in sorted(out.split("\0")) if t]


def _unprotected_twins(policy, twins):
    """Each twin whose rendered file the policy protects and which it leaves
    editable: an agent would edit the twin and copier would render the judge."""
    return [
        twin
        for twin, plain in twins
        if ar.protected_by(PurePosixPath(plain).parts, policy) is not None
        and ar.protected_by(PurePosixPath(twin).parts, policy) is None
    ]


def test_a_template_twin_of_a_protected_file_is_protected_too(tmp_path):
    """The class F10 named: `.gitignore.jinja` and `.copier-answers.yml.jinja`
    were editable while the files they render were judges. Every twin is
    derived from the tree, so a twin added later is held too. Only in the
    template: a generated project renders its twins and ships none."""
    if not (_ROOT / "copier.yml").is_file():
        pytest.skip("not a copier template — a generated project has no twins")
    twins = _template_twins()
    policy = ar.load_policy(str(_ROOT))
    held = [
        t for t, plain in twins if ar.protected_by(PurePosixPath(plain).parts, policy)
    ]
    assert len(held) >= 3, ("too few protected twins to judge", twins)
    assert _unprotected_twins(policy, twins) == []
    # Fault injection: drop one twin's own entry and exactly that twin reds.
    agents = _template_agents()
    agents["protected_paths"].pop(".gitignore.jinja")
    _policy_tree(tmp_path, agents)
    assert _unprotected_twins(ar.load_policy(str(tmp_path)), twins) == [
        ".gitignore.jinja"
    ]


def test_an_ordinary_edit_still_applies_and_a_readme_under_a_protected_dir_is_editable(
    tmp_path,
):
    _policy_tree(tmp_path)
    module = _plant(tmp_path, "src/backend/m.py")
    readme = _plant(tmp_path, "scripts/README.md")
    for rel, path in (("src/backend/m.py", module), ("scripts/README.md", readme)):
        res = ar.apply_and_gate(_edit(rel), str(tmp_path), gate="none")
        assert res["applied"] is True, (rel, res)
        assert path.read_text(encoding="utf-8") == "keep = 2\n"
    judge = _plant(tmp_path, "scripts/check_structure.py")
    os.symlink("../scripts/check_structure.py", str(tmp_path / "src" / "README.md"))
    with pytest.raises(ar.RefactorError) as exc:
        ar.plan_edits(_edit("src/README.md"), str(tmp_path))
    assert "agents.protected_paths.scripts" in str(exc.value)
    assert judge.read_text(encoding="utf-8") == _KEEP


_UNTRACKED = {
    # The toolchain the gate runs: the gate's own pytest, and a frontend
    # app's vitest. Both are ignored, so git never lists them.
    "venv": ".venv/lib/python3.11/site-packages/_pytest/main.py",
    "node-modules": "src/frontend/app/node_modules/vitest/index.js",
    "untracked-source": "src/new.py",
}


@pytest.mark.parametrize("case", sorted(_UNTRACKED))
def test_an_edit_to_a_file_git_does_not_track_is_refused_before_any_write(
    tmp_path, case
):
    _policy_tree(tmp_path)
    _plant(tmp_path, ".gitignore", ".venv\nnode_modules\n")
    rel = _UNTRACKED[case]
    _plant(tmp_path, rel, track=False)
    before = _snapshot(tmp_path)
    with pytest.raises(ar.RefactorError) as exc:
        ar.plan_edits(_edit(rel), str(tmp_path))
    text = str(exc.value)
    assert "edit 0" in text and rel in text, text
    assert "is not a file git tracks" in text, text
    with pytest.raises(ar.RefactorError):
        ar.apply_and_gate(_edit(rel), str(tmp_path), gate="none")
    assert _snapshot(tmp_path) == before
    # The control: an untracked source file, once tracked, applies.
    if case == "untracked-source":
        _track(tmp_path, rel)
        res = ar.apply_and_gate(_edit(rel), str(tmp_path), gate="none")
        assert res["applied"] is True, res


def test_git_state_is_refused_by_the_tracked_rule_even_when_unlisted(tmp_path):
    """Two layers: with `.git` dropped from protected_paths, .git/config is
    still refused, because git never tracks its own state."""
    agents = _template_agents()
    agents["protected_paths"].pop(".git")
    _policy_tree(tmp_path, agents)
    config = tmp_path / ".git" / "config"
    text = config.read_text(encoding="utf-8")
    spec = {"edits": [{"file": ".git/config", "content": text + "[core]\n"}]}
    with pytest.raises(ar.RefactorError) as exc:
        ar.apply_and_gate(spec, str(tmp_path), gate="none")
    assert "is not a file git tracks" in str(exc.value), str(exc.value)
    assert config.read_text(encoding="utf-8") == text


def test_an_edit_outside_a_git_work_tree_is_refused(tmp_path):
    root = tmp_path / "bare"
    root.mkdir()
    block = json.dumps({"agents": _template_agents()})
    (root / "config").mkdir()
    (root / "config" / "project.json").write_text(block, encoding="utf-8")
    module = _plant(root, "m.py", track=False)
    with pytest.raises(ar.RefactorError) as exc:
        ar.apply_and_gate(_edit("m.py"), str(root), gate="none")
    assert "edit 0" in str(exc.value) and "git" in str(exc.value), str(exc.value)
    assert module.read_text(encoding="utf-8") == _KEEP


def test_two_spellings_of_one_file_compose_as_one_file(tmp_path):
    """`src/m.py` and `./src/m.py` are one file, so the second edit composes
    on the first instead of overwriting it from the same original."""
    _policy_tree(tmp_path)
    module = _plant(tmp_path, "src/m.py", "a\nc\n")
    spec = {
        "edits": [
            {"file": "src/m.py", "find": "a", "replace": "A"},
            {"file": "./src/m.py", "find": "c", "replace": "C"},
        ]
    }
    res = ar.apply_and_gate(spec, str(tmp_path), gate="none", allow=["src/m.py"])
    assert res["applied"] is True and res["files"] == ["src/m.py"], res
    assert module.read_text(encoding="utf-8") == "A\nC\n"


@pytest.mark.parametrize(
    "rel",
    ["src/../scripts/check_structure.py", "src/../src/m.py", "<absolute>"],
    ids=["parent-into-a-judge", "parent-back-inside", "absolute-inside-the-root"],
)
def test_a_parent_part_or_absolute_path_is_refused_even_inside_the_root(tmp_path, rel):
    _policy_tree(tmp_path)
    _plant(tmp_path, "src/m.py")
    _plant(tmp_path, "scripts/check_structure.py")
    if rel == "<absolute>":
        rel = str(tmp_path / "src" / "m.py")
    before = _snapshot(tmp_path)
    with pytest.raises(ar.RefactorError) as exc:
        ar.apply_and_gate(_edit(rel), str(tmp_path), gate="none")
    assert "a path with '..' or an absolute path is refused" in str(exc.value)
    assert "edit 0" in str(exc.value)
    assert _snapshot(tmp_path) == before


def _broken(mutate):
    def build(root):
        agents = _template_agents()
        mutate(agents)
        _policy_tree(root, agents)

    return build


def _no_file(root):
    return None


def _no_block(root):
    path = root / "config" / "project.json"
    path.parent.mkdir(parents=True)
    path.write_text("{}", encoding="utf-8")


def _drop_config(agents):
    agents["protected_paths"].pop("config")


_UNUSABLE = {
    "no-config-file": (_no_file, "config/project.json"),
    "no-agents-block": (_no_block, "agents.protected_paths"),
    "empty-protected-paths": (
        _broken(lambda a: a.update(protected_paths={})),
        "agents.protected_paths",
    ),
    "blank-reason": (
        _broken(lambda a: a["protected_names"].update({"AGENT.md": " "})),
        "agents.protected_names",
    ),
    "parent-part-key": (
        _broken(lambda a: a["protected_paths"].update({"../up": "a reason"})),
        "agents.protected_paths",
    ),
    "config-not-covered": (_broken(_drop_config), "agents.protected_paths"),
}


@pytest.mark.parametrize("case", sorted(_UNUSABLE))
def test_an_unusable_edit_policy_is_a_config_fault(tmp_path, case, capsys):
    build, named = _UNUSABLE[case]
    root = tmp_path / "root"
    root.mkdir()
    build(root)
    module = _plant(root, "src/m.py")
    with pytest.raises(config_loader.ConfigError) as exc:
        ar.load_policy(str(root))
    assert named in str(exc.value), str(exc.value)
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(_edit("src/m.py")), encoding="utf-8")
    before = _snapshot(root)
    code = ar.main(["--spec", str(spec_file), "--root", str(root), "--gate", "none"])
    assert code == ExitCode.CONFIG
    assert named in capsys.readouterr().err
    assert _snapshot(root) == before
    assert module.read_text(encoding="utf-8") == _KEEP


# --- the gate is the caller's, never the spec's ---------------------------------


def _recording_gate(seen):
    def gate_runner(gate, cwd, timeout):
        seen.append(gate)
        return True, "green"

    return gate_runner


def test_a_spec_that_names_a_gate_is_refused_and_the_callers_gate_runs(tmp_path):
    """A spec is model-written, so the gate it names would let the model pick
    its own judge; `"gate": "none"` once applied with no gate at all."""
    f, spec = _spec(tmp_path)
    gated = dict(spec, gate="none")
    before = _snapshot(tmp_path)
    with pytest.raises(ar.RefactorError) as plan:
        ar.plan_edits(gated, str(tmp_path))
    seen = []
    with pytest.raises(ar.RefactorError) as applied:
        ar.apply_and_gate(gated, str(tmp_path), gate_runner=_recording_gate(seen))
    for text in (str(plan.value), str(applied.value)):
        assert "names a gate ('none')" in text, text
        assert "the caller's --gate" in text, text
    spec_file = tmp_path.parent / "gated-spec.json"
    spec_file.write_text(json.dumps(gated), encoding="utf-8")
    argv = ["--spec", str(spec_file), "--root", str(tmp_path)]
    assert ar.main(argv + ["--gate", "none"]) == ExitCode.USAGE
    assert ar.main(argv + ["--dry-run"]) == ExitCode.USAGE
    assert seen == [] and _snapshot(tmp_path) == before

    res = ar.apply_and_gate(spec, str(tmp_path), gate_runner=_recording_gate(seen))
    assert seen == ["verify"] and res["gate"] == "verify" and res["applied"] is True
    assert f.read_text(encoding="utf-8") == "keep = 2\n"


@pytest.mark.parametrize(
    "spec, named",
    [
        ({"edits": [], "notes": "x"}, "'notes'"),
        (
            {"edits": [{"file": "m.py", "find": "a", "replace": "b", "mode": "w"}]},
            "edit 0: unknown key 'mode'",
        ),
    ],
    ids=["unknown-top-level-key", "unknown-edit-key"],
)
def test_a_spec_key_outside_the_closed_vocabulary_is_refused(tmp_path, spec, named):
    _policy_tree(tmp_path)
    _plant(tmp_path, "m.py", "a\n")
    before = _snapshot(tmp_path)
    with pytest.raises(ar.RefactorError) as exc:
        ar.apply_and_gate(spec, str(tmp_path), gate="none")
    assert named in str(exc.value), str(exc.value)
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("gate", [None, ""], ids=["none-value", "empty"])
def test_an_absent_gate_is_refused_not_defaulted_from_the_spec(tmp_path, gate):
    f, spec = _spec(tmp_path)
    with pytest.raises(ar.RefactorError) as exc:
        ar.apply_and_gate(spec, str(tmp_path), gate=gate)
    assert "no gate given" in str(exc.value)
    assert f.read_text(encoding="utf-8") == _KEEP


def test_an_edit_outside_the_allowed_files_is_refused(tmp_path):
    _policy_tree(tmp_path)
    a = _plant(tmp_path, "src/a.py")
    b = _plant(tmp_path, "src/b.py")
    before = _snapshot(tmp_path)
    with pytest.raises(ar.RefactorError) as exc:
        ar.apply_and_gate(
            _edit("src/b.py"), str(tmp_path), gate="none", allow=["src/a.py"]
        )
    text = str(exc.value)
    assert "edit 0" in text and "src/b.py" in text, text
    assert "is not a file this run was bound to (--allow src/a.py)" in text, text
    with pytest.raises(ar.RefactorError):
        ar.plan_edits(_edit("src/a.py"), str(tmp_path), allow=[])
    # One allowed edit beside one refused edit refuses the whole spec.
    both = {"edits": _edit("src/a.py")["edits"] + _edit("src/b.py")["edits"]}
    with pytest.raises(ar.RefactorError):
        ar.apply_and_gate(both, str(tmp_path), gate="none", allow=["src/a.py"])
    assert _snapshot(tmp_path) == before

    res = ar.apply_and_gate(
        _edit("./src/a.py"), str(tmp_path), gate="none", allow=["src/a.py"]
    )
    assert res["applied"] is True and a.read_text(encoding="utf-8") == "keep = 2\n"
    # No binding: only the deny floor applies.
    res = ar.apply_and_gate(_edit("src/b.py"), str(tmp_path), gate="none", allow=None)
    assert res["applied"] is True and b.read_text(encoding="utf-8") == "keep = 2\n"


def test_the_cli_binds_the_run_to_its_allow_flags(tmp_path, capsys):
    _policy_tree(tmp_path)
    _plant(tmp_path, "src/a.py")
    b = _plant(tmp_path, "src/b.py")
    spec_file = tmp_path.parent / "allow-spec.json"
    spec_file.write_text(json.dumps(_edit("src/b.py")), encoding="utf-8")
    argv = ["--spec", str(spec_file), "--root", str(tmp_path), "--gate", "none"]
    assert ar.main(argv + ["--allow", "src/a.py"]) == ExitCode.USAGE
    assert "--allow src/a.py" in capsys.readouterr().err
    assert b.read_text(encoding="utf-8") == _KEEP
    assert ar.main(argv + ["--allow", "src/a.py", "--allow", "src/b.py"]) == 0
    assert b.read_text(encoding="utf-8") == "keep = 2\n"


def test_the_cli_defaults_the_gate_to_verify_and_takes_none_only_as_a_flag(
    tmp_path, monkeypatch
):
    seen = []

    def fake(spec, root, gate="unset", timeout=0, allow=None, **kwargs):
        seen.append(gate)
        return {"practice": "", "gate": gate, "applied": True, "files": []}

    monkeypatch.setattr(ar, "apply_and_gate", fake)
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(_edit("m.py")), encoding="utf-8")
    argv = ["--spec", str(spec_file), "--root", str(tmp_path)]
    assert ar.main(argv) == 0
    assert ar.main(argv + ["--gate", "none"]) == 0
    assert seen == ["verify", "none"]


def test_the_cli_timeout_is_unset_unless_given(tmp_path, monkeypatch):
    """No --timeout reaches apply_and_gate as None (the configured limit); a
    given one is passed through unchanged."""
    seen = []

    def fake(spec, root, gate="unset", timeout=0, allow=None, **kwargs):
        seen.append(timeout)
        return {"practice": "", "gate": gate, "applied": True, "files": []}

    monkeypatch.setattr(ar, "apply_and_gate", fake)
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(_edit("m.py")), encoding="utf-8")
    argv = ["--spec", str(spec_file), "--root", str(tmp_path)]
    assert ar.main(argv) == 0
    assert ar.main(argv + ["--timeout", "42"]) == 0
    assert seen == [None, 42]
