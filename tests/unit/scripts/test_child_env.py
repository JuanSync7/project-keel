"""
title: Unit — child_env (the environment a child process inherits)
kind: tests
layer: n/a
summary: build_child_env starts from an empty dict and copies only what config/project.json allows — `child_env.names`, a name under a `child_env.prefixes` entry, the `make_targets` unattended and gate variables, and, for a named model adapter, that adapter's `models.credential_env` — then adds the caller's `extra` last. A planted secret such as AWS_SECRET_ACCESS_KEY or GITHUB_TOKEN never reaches the result unless declared, a declared name the parent lacks stays absent rather than empty, and a missing, unreadable or malformed manifest is a ChildEnvError, never a fall-back to the parent's environment. child_env_policy states the same rule without touching disk.
"""

import copy
import json
import os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import child_env  # noqa: E402

pytestmark = pytest.mark.unit

_MANIFEST = {
    "child_env": {"_comment": "test", "names": ["PATH", "HOME"], "prefixes": []},
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
