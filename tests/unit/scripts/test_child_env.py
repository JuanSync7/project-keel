"""
title: Unit — child_env (the environment a child process inherits)
kind: tests
layer: n/a
summary: build_child_env starts from an empty dict and copies only what config/project.json allows — `child_env.names`, a name under a `child_env.prefixes` entry, the `make_targets` unattended and gate variables, and, for a named model adapter, that adapter's `models.credential_env` — then adds the caller's `extra` last. A planted secret such as AWS_SECRET_ACCESS_KEY or GITHUB_TOKEN never reaches the result unless declared, a declared name the parent lacks stays absent rather than empty, and a missing, unreadable or malformed manifest is a ChildEnvError, never a fall-back to the parent's environment. A `child_env.repo_context_names` variable reaches the result only when the call passes `repo_context=True`, and child_env_policy refuses an allowlist source that admits one, naming the source and the fix. child_env_policy states the same rule without touching disk.
"""

import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import child_env  # noqa: E402

pytestmark = pytest.mark.unit

_MANIFEST = {
    "child_env": {
        "_comment": "test",
        "names": ["PATH", "HOME"],
        "prefixes": [],
        "repo_context_names": ["GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE"],
    },
    "make_targets": {"unattended_vars": ["CI", "RALPH"], "gate_vars": ["PY"]},
    "models": {
        "available": {"a": "models", "b": "models", "fake": "models"},
        "credential_env": {"a": ["A_KEY"], "b": ["B_KEY"]},
    },
}
# Each one is a credential some real parent environment here holds.
_SECRETS = {
    "AWS_SECRET_ACCESS_KEY": "s1",
    "AWS_SESSION_TOKEN": "s2",
    "GITHUB_TOKEN": "s3",
    "ANTHROPIC_API_KEY": "s4",
    "OPENAI_API_KEY": "s5",
    "KEEL_PLANTED_SECRET": "s6",
}


def _manifest(**over):
    m = copy.deepcopy(_MANIFEST)
    for dotted, value in over.items():
        node = m
        keys = dotted.split("__")
        for k in keys[:-1]:
            node = node[k]
        if value is _DROP:
            node.pop(keys[-1], None)
        else:
            node[keys[-1]] = value
    return m


_DROP = object()


def _root(tmp_path, manifest):
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "config" / "project.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    return str(tmp_path)


@pytest.fixture
def parent(monkeypatch):
    """A parent environment holding PATH, HOME and every planted secret, and
    nothing else, so a result is compared against a known whole."""
    for key in list(os.environ):
        monkeypatch.delenv(key)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setenv("HOME", "/home/someone")
    for key, value in _SECRETS.items():
        monkeypatch.setenv(key, value)
    return monkeypatch


def test_a_child_gets_only_allowlisted_names(tmp_path, parent):
    env = child_env.build_child_env(root=_root(tmp_path, _MANIFEST))
    assert env == {"PATH": "/usr/bin:/bin", "HOME": "/home/someone"}
    assert not set(_SECRETS) & set(env)


def test_a_prefix_admits_its_family_and_nothing_else(tmp_path, parent):
    # A prefix matches at the START of a name only: CALC_SECRET and SSO_LC_TOKEN
    # carry `LC_` mid-name, and a substring match would hand them over.
    for key in ("LC_ALL", "LC_CTYPE", "LCX", "LC", "CALC_SECRET", "SSO_LC_TOKEN"):
        parent.setenv(key, "C")
    root = _root(tmp_path, _manifest(child_env__prefixes=["LC_"]))
    env = child_env.build_child_env(root=root)
    assert env["LC_ALL"] == "C" and env["LC_CTYPE"] == "C"
    for key in ("LCX", "LC", "CALC_SECRET", "SSO_LC_TOKEN"):
        assert key not in env, key


def test_unattended_and_gate_vars_come_from_make_targets(tmp_path, parent):
    parent.setenv("CI", "1")
    parent.setenv("RALPH", "1")
    parent.setenv("PY", "/x/python")
    env = child_env.build_child_env(root=_root(tmp_path, _MANIFEST))
    assert env["CI"] == "1" and env["RALPH"] == "1" and env["PY"] == "/x/python"


def test_an_adapter_gets_its_declared_credentials_and_no_other_adapters(
    tmp_path, parent
):
    parent.setenv("A_KEY", "ka")
    parent.setenv("B_KEY", "kb")
    root = _root(tmp_path, _MANIFEST)
    env = child_env.build_child_env(credentials_for="a", root=root)
    assert env["A_KEY"] == "ka" and "B_KEY" not in env
    assert not set(_SECRETS) & set(env)
    plain = child_env.build_child_env(root=root)
    assert "A_KEY" not in plain and "B_KEY" not in plain


def test_an_adapter_without_a_credential_entry_gets_the_base_allowlist(
    tmp_path, parent
):
    env = child_env.build_child_env(
        credentials_for="fake", root=_root(tmp_path, _MANIFEST)
    )
    assert env == {"PATH": "/usr/bin:/bin", "HOME": "/home/someone"}


def test_a_declared_credential_the_parent_lacks_is_absent_not_empty(tmp_path, parent):
    env = child_env.build_child_env(
        credentials_for="a", root=_root(tmp_path, _MANIFEST)
    )
    assert "A_KEY" not in env


def test_an_adapter_not_in_models_available_is_an_error(tmp_path, parent):
    with pytest.raises(child_env.ChildEnvError) as caught:
        child_env.build_child_env(
            credentials_for="typo", root=_root(tmp_path, _MANIFEST)
        )
    assert "typo" in str(caught.value) and "models.available" in str(caught.value)


def test_extra_is_applied_last_and_validated(tmp_path, parent):
    root = _root(tmp_path, _MANIFEST)
    env = child_env.build_child_env(extra={"PATH": "/only", "RALPH": "1"}, root=root)
    assert env["PATH"] == "/only" and env["RALPH"] == "1"
    for bad in ({"X": 1}, {"bad name": "v"}, {"MAKEFLAGS": "x"}):
        with pytest.raises(child_env.ChildEnvError):
            child_env.build_child_env(extra=bad, root=root)


def test_the_error_is_not_a_runtime_error():
    """A caller that skips on ModelUnavailable (a RuntimeError) must not skip a
    broken allowlist."""
    assert not issubclass(child_env.ChildEnvError, RuntimeError)


_BROKEN = [
    ("no child_env block", _manifest(child_env=_DROP), "no child_env block"),
    ("names not a list", _manifest(child_env__names="PATH"), "child_env.names"),
    ("invalid name", _manifest(child_env__names=["PATH", "A-B"]), "child_env.names"),
    ("duplicate name", _manifest(child_env__names=["PATH", "PATH"]), "child_env.names"),
    ("empty prefix", _manifest(child_env__prefixes=[""]), "child_env.prefixes"),
    ("prefix without underscore", _manifest(child_env__prefixes=["LC"]), "prefixes"),
    ("MAKEFLAGS in names", _manifest(child_env__names=["MAKEFLAGS"]), "MAKEFLAGS"),
    ("unknown key", _manifest(child_env__globs=["X*"]), "globs"),
    (
        "credential key not available",
        _manifest(models__credential_env={"nope": ["K"]}),
        "nope",
    ),
    (
        "credential value not a list",
        _manifest(models__credential_env={"a": "A_KEY"}),
        "credential_env",
    ),
    (
        "gate_vars not names",
        _manifest(make_targets__gate_vars=["P Y"]),
        "make_targets.gate_vars",
    ),
    (
        "repo-context-missing",
        _manifest(child_env__repo_context_names=_DROP),
        "repo_context_names is missing",
    ),
    (
        "repo-context-empty",
        _manifest(child_env__repo_context_names=[]),
        "at least one",
    ),
    (
        "repo-context-bad-name",
        _manifest(child_env__repo_context_names=["git dir"]),
        "child_env.repo_context_names",
    ),
    (
        "repo-context-duplicate",
        _manifest(child_env__repo_context_names=["GIT_DIR", "GIT_DIR"]),
        "child_env.repo_context_names names GIT_DIR twice",
    ),
    (
        "repo-context-make-control",
        _manifest(child_env__repo_context_names=["MAKEFLAGS"]),
        "child_env.repo_context_names names MAKEFLAGS",
    ),
]


@pytest.mark.parametrize(
    ("manifest", "names"),
    [(m, n) for _, m, n in _BROKEN],
    ids=[i for i, _, _ in _BROKEN],
)
def test_a_malformed_manifest_fails_closed(tmp_path, parent, manifest, names):
    policy, errs = child_env.child_env_policy(manifest)
    assert policy is None and errs and any(names in e for e in errs), errs
    with pytest.raises(child_env.ChildEnvError) as caught:
        child_env.build_child_env(root=_root(tmp_path, manifest))
    assert "config/project.json" in str(caught.value) and names in str(caught.value)


# Each is a side door that would re-admit a repository variable the default
# drops. The fragment is the source the message must name.
_OVERLAP = [
    (
        "overlap-names",
        _manifest(child_env__names=["PATH", "HOME", "GIT_DIR"]),
        "child_env.names lists GIT_DIR,",
    ),
    (
        "overlap-prefix",
        _manifest(child_env__prefixes=["GIT_"]),
        "child_env.prefixes `GIT_` admits GIT_DIR, GIT_INDEX_FILE, GIT_WORK_TREE,",
    ),
    (
        "overlap-gate-vars",
        _manifest(make_targets__gate_vars=["PY", "GIT_DIR"]),
        "make_targets.gate_vars lists GIT_DIR,",
    ),
    (
        "overlap-unattended-vars",
        _manifest(make_targets__unattended_vars=["CI", "GIT_WORK_TREE"]),
        "make_targets.unattended_vars lists GIT_WORK_TREE,",
    ),
    (
        "overlap-credentials",
        _manifest(models__credential_env={"a": ["A_KEY", "GIT_INDEX_FILE"]}),
        "models.credential_env.a lists GIT_INDEX_FILE,",
    ),
]


@pytest.mark.parametrize(
    ("manifest", "source"),
    [(m, s) for _, m, s in _OVERLAP],
    ids=[i for i, _, _ in _OVERLAP],
)
def test_an_allowlisted_repository_variable_names_its_source_and_the_fix(
    tmp_path, parent, manifest, source
):
    """No allowlist source may re-admit what child_env.repo_context_names marks
    as bound to the parent's repository: exactly one error, naming the source,
    the key that marks it, and the per-call opt-in that is the fix."""
    policy, errs = child_env.child_env_policy(manifest)
    assert policy is None and len(errs) == 1, errs
    assert source in errs[0], errs
    assert "child_env.repo_context_names" in errs[0], errs
    assert "build_child_env(repo_context=True)" in errs[0], errs
    with pytest.raises(child_env.ChildEnvError) as caught:
        child_env.build_child_env(root=_root(tmp_path, manifest))
    assert source in str(caught.value)
    # The same manifest with the overlap gone is valid: the guard is not vacuous.
    assert child_env.child_env_policy(_MANIFEST)[1] == []


def test_a_manifest_without_repo_context_names_says_to_move_the_git_names_out(
    tmp_path, parent
):
    """A project from before repo_context_names existed still lists GIT_DIR and
    its siblings in child_env.names. One round of `make check` must tell it both
    halves of the fix -- add the key, and move git's repository variables out of
    names -- and name the git variables names lists, so the reader need not
    discover the overlap in a second round."""
    manifest = _manifest(
        child_env__repo_context_names=_DROP,
        child_env__names=["PATH", "GIT_CONFIG_GLOBAL", "GIT_DIR", "GIT_WORK_TREE"],
    )
    policy, errs = child_env.child_env_policy(manifest)
    assert policy is None and len(errs) == 1, errs
    msg = errs[0]
    assert "child_env.repo_context_names is missing" in msg, msg
    assert "remove" in msg and "from child_env.names" in msg, msg
    assert "git rev-parse --local-env-vars" in msg, msg
    assert "GIT_CONFIG_GLOBAL, GIT_DIR, GIT_WORK_TREE" in msg, msg
    with pytest.raises(child_env.ChildEnvError) as caught:
        child_env.build_child_env(root=_root(tmp_path, manifest))
    assert "GIT_DIR" in str(caught.value)
    # No git name in names: the message says what to add and lists nothing.
    _, errs = child_env.child_env_policy(_manifest(child_env__repo_context_names=_DROP))
    assert len(errs) == 1 and "GIT_" not in errs[0], errs


def test_an_overlap_is_not_reported_when_its_source_is_already_broken():
    """One root cause, one error: a names list that is itself invalid is not
    also reported as overlapping."""
    _, errs = child_env.child_env_policy(
        _manifest(child_env__names=["GIT_DIR", "GIT_DIR"])
    )
    assert len(errs) == 1 and "twice" in errs[0], errs


_HOOK = {"GIT_DIR": "/r/.git", "GIT_INDEX_FILE": "/r/.git/index", "GIT_WORK_TREE": "/r"}


def test_a_repository_context_name_reaches_a_child_only_on_request(tmp_path, parent):
    """A git hook's GIT_DIR/GIT_INDEX_FILE/GIT_WORK_TREE bind the hook's own git
    to the repository being committed; a child that runs git anywhere else would
    act on that repository instead. Dropped by default, copied on repo_context=True,
    and a literal in extra (applied last) still wins."""
    for key, value in _HOOK.items():
        parent.setenv(key, value)
    root = _root(tmp_path, _MANIFEST)
    base = {"PATH": "/usr/bin:/bin", "HOME": "/home/someone"}
    calls = [
        ({}, base),
        ({"repo_context": True}, dict(base, **_HOOK)),
        ({"repo_context": False}, base),
        ({"extra": {"GIT_DIR": "/x/.git"}}, dict(base, GIT_DIR="/x/.git")),
        (
            {"repo_context": True, "extra": {"GIT_DIR": "/x/.git"}},
            dict(base, **dict(_HOOK, GIT_DIR="/x/.git")),
        ),
    ]
    for kwargs, expected in calls:
        first = child_env.build_child_env(root=root, **kwargs)
        assert first == expected, kwargs
        assert child_env.build_child_env(root=root, **kwargs) == first, kwargs


def test_an_empty_repository_variable_is_present_not_absent(tmp_path, parent):
    """git exports GIT_PREFIX='' at the top of a work tree. Present-but-empty is
    a value: dropped by default like any other, copied as '' on opt-in."""
    parent.setenv("GIT_DIR", "")
    root = _root(tmp_path, _MANIFEST)
    assert "GIT_DIR" not in child_env.build_child_env(root=root)
    assert child_env.build_child_env(root=root, repo_context=True)["GIT_DIR"] == ""


@pytest.mark.parametrize("value", ["yes", 1, None, 0])
def test_repo_context_must_be_a_bool(tmp_path, parent, value):
    """A truthy string or an int is refused, never coerced: the opt-in is the
    call site's explicit decision."""
    with pytest.raises(child_env.ChildEnvError) as caught:
        child_env.build_child_env(root=_root(tmp_path, _MANIFEST), repo_context=value)
    assert "repo_context" in str(caught.value)


def test_an_absent_manifest_fails_closed(tmp_path, parent):
    with pytest.raises(child_env.ChildEnvError) as caught:
        child_env.build_child_env(root=str(tmp_path))
    assert "config/project.json" in str(caught.value)


def test_an_unreadable_manifest_fails_closed(tmp_path, parent):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(child_env.ChildEnvError) as caught:
        child_env.build_child_env(root=str(tmp_path))
    assert "config/project.json" in str(caught.value)


def test_a_manifest_that_is_not_an_object_fails_closed():
    policy, errs = child_env.child_env_policy([])
    assert policy is None and errs


def test_two_calls_give_the_same_environment(tmp_path, parent):
    root = _root(tmp_path, _manifest(child_env__prefixes=["LC_"]))
    parent.setenv("LC_ALL", "C")
    assert child_env.build_child_env(root=root) == child_env.build_child_env(root=root)


def test_the_default_root_is_the_project_this_module_ships_in(parent):
    """No root reads keel's own config/project.json: PATH comes through, a planted
    secret does not."""
    env = child_env.build_child_env()
    assert env["PATH"] == "/usr/bin:/bin"
    assert not set(_SECRETS) & set(env)


def test_keels_own_policy_is_valid_and_never_lists_a_secret():
    manifest = json.loads((_ROOT / "config" / "project.json").read_text("utf-8"))
    policy, errs = child_env.child_env_policy(manifest)
    assert policy is not None and errs == [], errs
    assert not set(_SECRETS) & set(policy.names)
    assert "ANTHROPIC_API_KEY" in policy.credentials["claude-code-headless"]


# git's own `--local-env-vars` list also carries these three. They hold the
# parent's `-c` settings, not a repository location, and keel's names never
# list them, so the allowlist already drops them (config/project.json says why).
_CONFIG_INJECTION = {"GIT_CONFIG", "GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS"}


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_keels_policy_holds_back_every_repository_variable_git_names(monkeypatch):
    """Keel's list is git's own, so a git that adds a location variable reds
    this test rather than leaking it to a child."""
    manifest = json.loads((_ROOT / "config" / "project.json").read_text("utf-8"))
    policy, errs = child_env.child_env_policy(manifest)
    assert policy is not None and errs == [], errs
    r = subprocess.run(
        ["git", "rev-parse", "--local-env-vars"],
        capture_output=True,
        text=True,
        env=child_env.build_child_env(),
    )
    assert r.returncode == 0, r.stderr
    gits = set(r.stdout.split()) - _CONFIG_INJECTION
    assert len(gits) >= 10, r.stdout  # a pass over an empty listing is a failure
    assert gits <= set(policy.repo_context), sorted(gits - set(policy.repo_context))
    assert {"GIT_NAMESPACE", "GIT_QUARANTINE_PATH"} <= set(policy.repo_context)
    assert not _CONFIG_INJECTION & set(policy.repo_context)
    for key in policy.repo_context:
        monkeypatch.setenv(key, "/planted")
    env = child_env.build_child_env(root=str(_ROOT))
    assert not set(policy.repo_context) & set(env), sorted(env)
