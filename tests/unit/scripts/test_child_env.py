"""
title: Unit — child_env (the environment a child process inherits)
kind: tests
layer: n/a
summary: build_child_env starts from an empty dict and copies only what config/project.json allows — `child_env.names`, a name under a `child_env.prefixes` entry, the `make_targets` unattended and gate variables, and, for a named model adapter, that adapter's `models.credential_env` — then adds the caller's `extra` last. A planted secret such as AWS_SECRET_ACCESS_KEY or GITHUB_TOKEN never reaches the result unless declared, a declared name the parent lacks stays absent rather than empty, and a missing, unreadable or malformed manifest is a ChildEnvError, never a fall-back to the parent's environment. A `child_env.repo_context_names` variable reaches the result only when the call passes `repo_context=True`, and child_env_policy refuses an allowlist source that admits one, naming the source and the fix. A copied value carrying user information (a user part in a URL authority, a scheme-relative `//user@host` and a space in the password included; a whole value `user[:password]@host:port`; or, in a `*_proxy` variable, any user part urllib's proxy parser reads, `#`, `?` or `/` in the password and a scheme-less `token@proxy` included) is a ChildEnvError naming every such variable and never the value, whatever allowlist source copied it, unless `child_env.credentialed_values` names it, the called adapter declares it, or `extra` replaces it; child_env_policy refuses a credentialed_values entry that is malformed or that no allowlist source copies. A glibc locale list such as `LANGUAGE=sr_RS:sr@latin`, `name@domain`, and a non-proxy URL with an `@` after its host are copied verbatim. child_env_policy states the same rule without touching disk.
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
    (
        "credentialed-not-object",
        _manifest(child_env__credentialed_values=["HTTPS_PROXY"]),
        "child_env.credentialed_values must be an object",
    ),
    (
        "credentialed-no-reason",
        _manifest(child_env__credentialed_values={"PATH": "  "}),
        "carries no reason",
    ),
    (
        "credentialed-bad-name",
        _manifest(child_env__credentialed_values={"A-B": "r"}),
        "is not an environment variable name",
    ),
    (
        "credentialed-stale",
        _manifest(child_env__credentialed_values={"NOT_COPIED": "r"}),
        "child_env.credentialed_values names `NOT_COPIED`, which no allowlist "
        "source copies",
    ),
    (
        "credentialed-adapter-only",
        _manifest(child_env__credentialed_values={"A_KEY": "r"}),
        "models.credential_env",
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
    # Keel opts no variable in: the key ships, empty, so a project sees where an
    # authenticating proxy's opt-in goes without receiving one.
    assert manifest["child_env"]["credentialed_values"] == {}
    assert policy.credentialed == ()


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


# --- a credential carried inside an allowlisted value ---------------------------------

# The password, and the user it belongs to, that no error text may carry.
_PW = "s3cr3t-pw"
_USER = "alice"
# Refused in every copied variable: an RFC 3986 section 3.2 authority (after
# `scheme://` or a leading `//`, up to the first `/`, `?` or `#`) with a user
# part, or a whole value that is a scheme-less `user[:password]@host:port`.
_FORMS = {
    "url": "http://%s:%s@127.0.0.1:9" % (_USER, _PW),
    "bare": "%s:%s@proxy:3128" % (_USER, _PW),
    "token": "https://%s@host/x" % _PW,
    # urllib.request._parse_proxy reads user and password out of each of these
    # (measured, 3.6.8 and 3.11), and urlsplit puts the space inside the netloc.
    "scheme-relative": "//%s:%s@proxy:8080" % (_USER, _PW),
    "space-in-password": "http://%s:%s x@127.0.0.1:9" % (_USER, _PW),
    "bare-token-with-port": "%s@proxy.example:8080" % _PW,
}
# Each source build_child_env copies from unasked: (variable, manifest overrides,
# call keywords). The make_targets variables come from _MANIFEST itself.
_SOURCES = {
    "names": ("HTTPS_PROXY", {"child_env__names": ["PATH", "HOME", "HTTPS_PROXY"]}, {}),
    "lowercase": (
        "https_proxy",
        {"child_env__names": ["PATH", "HOME", "https_proxy"]},
        {},
    ),
    "prefix": ("LC_X", {"child_env__prefixes": ["LC_"]}, {}),
    "gate-var": ("PY", {}, {}),
    "unattended-var": ("CI", {}, {}),
    "repo-context": ("GIT_DIR", {}, {"repo_context": True}),
}


def _texts(exc):
    """Every rendering of exc a caller could print or log."""
    return [str(exc), repr(exc)] + [str(a) for a in exc.args]


@pytest.mark.parametrize("form", sorted(_FORMS))
@pytest.mark.parametrize("source", sorted(_SOURCES))
def test_a_credential_in_a_copied_value_is_refused_naming_the_variable_never_the_value(
    tmp_path, parent, source, form
):
    """A value carrying URL user information is a credential, whatever the
    variable is called and whichever allowlist source copies it. The refusal
    names the variable and the opt-in, and no rendering of it carries the
    password or the user, nor chains an exception that does."""
    name, over, kwargs = _SOURCES[source]
    parent.setenv(name, _FORMS[form])
    root = _root(tmp_path, _manifest(**over))
    with pytest.raises(child_env.ChildEnvError) as caught:
        child_env.build_child_env(root=root, **kwargs)
    exc = caught.value
    assert name in str(exc) and "child_env.credentialed_values" in str(exc), exc
    for text in _texts(exc):
        assert _PW not in text and _USER not in text, "the error carries the value"
    assert exc.__cause__ is None and exc.__context__ is None
    if kwargs:
        # The rule judges only what is copied: without the opt-in the
        # repository variable never reaches the child, so nothing is refused.
        assert name not in child_env.build_child_env(root=root)


def test_every_credentialed_variable_is_named_in_one_error(tmp_path, parent):
    """Several offenders are one error listing all of them, sorted, never one a
    round; a second call says exactly the same."""
    names = ["PATH", "HOME", "ALL_PROXY", "HTTPS_PROXY", "https_proxy"]
    for key in names[2:]:
        parent.setenv(key, _FORMS["url"])
    root = _root(tmp_path, _manifest(child_env__names=names))
    messages = []
    for _ in range(2):
        with pytest.raises(child_env.ChildEnvError) as caught:
            child_env.build_child_env(root=root)
        messages.append(str(caught.value))
    assert "ALL_PROXY, HTTPS_PROXY, https_proxy" in messages[0], messages[0]
    assert messages[0] == messages[1]


# The false-positive control: each holds an `@` or a `://`, and none carries
# user information, so a detector that matches either alone fails here.
_CLEAN = {
    "HTTPS_PROXY": "http://proxy:8080",
    "HTTP_PROXY": "http://[::1]:8080/",
    "NO_PROXY": "localhost,.corp,127.0.0.1",
    "USER": "me@corp.example",
    "PATH": "/usr/bin:/opt/tool@2.1/bin:/n/node_modules/@scope/bin",
    "REPO_URL": "git@github.com:org/repo.git",
    # Not a proxy name, so read as RFC 3986 reads a URL: the `@` is past the host.
    "SVC_URL": "https://host:443/p?q=a@b",
    "PKG_URL": "https://registry.example/@scope/pkg",
    # glibc LANGUAGE is a colon-joined locale list, and a locale may carry an
    # @modifier, so `x:y@z` is an ordinary value (sr_RS@latin is a glibc locale).
    "LANGUAGE": "sr_RS:sr@latin",
    "LC_MESSAGES": "ca_ES:ca@valencia",
    # urllib reads an empty user here and sends no Proxy-Authorization.
    "http_proxy": "http://@proxy",
    "https_proxy": "",
}


def test_a_value_without_user_information_is_copied_verbatim(tmp_path, parent):
    for key, value in _CLEAN.items():
        parent.setenv(key, value)
    root = _root(tmp_path, _manifest(child_env__names=["HOME"] + sorted(_CLEAN)))
    env = child_env.build_child_env(root=root)
    assert {k: env.get(k) for k in _CLEAN} == _CLEAN


def test_a_name_in_credentialed_values_passes_its_value_through(tmp_path, parent):
    """The opt-in is per variable: listing HTTPS_PROXY does not also clear its
    lowercase twin, which the same proxy usually sets."""
    reason = "the site proxy authenticates every request"
    manifest = _manifest(
        child_env__names=["PATH", "HOME", "HTTPS_PROXY", "https_proxy"],
        child_env__credentialed_values={"HTTPS_PROXY": reason},
    )
    policy, errs = child_env.child_env_policy(manifest)
    assert errs == [] and policy.credentialed == ("HTTPS_PROXY",), errs
    root = _root(tmp_path, manifest)
    parent.setenv("HTTPS_PROXY", _FORMS["url"])
    parent.setenv("https_proxy", _FORMS["url"])
    with pytest.raises(child_env.ChildEnvError) as caught:
        child_env.build_child_env(root=root)
    msg = str(caught.value)
    assert "https_proxy" in msg and "HTTPS_PROXY" not in msg, msg
    parent.delenv("https_proxy")
    assert child_env.build_child_env(root=root)["HTTPS_PROXY"] == _FORMS["url"]


def test_an_adapters_declared_credential_is_exempt_for_that_adapter_only(
    tmp_path, parent
):
    """models.credential_env declares a credential for one adapter's child; every
    other call still refuses the same copied value."""
    manifest = _manifest(
        child_env__names=["PATH", "HOME", "HTTPS_PROXY"],
        models__credential_env={"a": ["A_KEY", "HTTPS_PROXY"], "b": ["B_KEY"]},
    )
    root = _root(tmp_path, manifest)
    parent.setenv("HTTPS_PROXY", _FORMS["url"])
    env = child_env.build_child_env(root=root, credentials_for="a")
    assert env["HTTPS_PROXY"] == _FORMS["url"]
    for kwargs in ({}, {"credentials_for": "b"}):
        with pytest.raises(child_env.ChildEnvError) as caught:
            child_env.build_child_env(root=root, **kwargs)
        assert "HTTPS_PROXY" in str(caught.value), kwargs


def test_extra_replaces_a_credentialed_parent_value_and_is_not_judged(tmp_path, parent):
    """The judgement runs on what the parent hands over, after extra: a key extra
    replaces never carries the parent's value, and extra is the call site's own
    literal."""
    root = _root(tmp_path, _manifest(child_env__names=["PATH", "HOME", "HTTPS_PROXY"]))
    parent.setenv("HTTPS_PROXY", _FORMS["url"])
    env = child_env.build_child_env(
        root=root, extra={"HTTPS_PROXY": "http://proxy:8080"}
    )
    assert env["HTTPS_PROXY"] == "http://proxy:8080"
    # A credentialed literal on the same key is the call site's decision too.
    env = child_env.build_child_env(root=root, extra={"HTTPS_PROXY": "http://u:p@h"})
    assert env["HTTPS_PROXY"] == "http://u:p@h"
    parent.delenv("HTTPS_PROXY")
    env = child_env.build_child_env(root=root, extra={"SVC_URL": "http://u:p@h"})
    assert env["SVC_URL"] == "http://u:p@h"


def test_credentialed_values_is_optional_and_may_be_empty():
    """Absent and empty both mean no exemption, the fail-closed state, so an
    older manifest without the key stays valid. A stale entry beside a broken
    names list is not a second error for one root cause."""
    for manifest in (_MANIFEST, _manifest(child_env__credentialed_values={})):
        policy, errs = child_env.child_env_policy(manifest)
        assert errs == [] and policy.credentialed == (), errs
    _, errs = child_env.child_env_policy(
        _manifest(
            child_env__names=["PATH", "PATH"],
            child_env__credentialed_values={"NOT_COPIED": "r"},
        )
    )
    assert len(errs) == 1 and "twice" in errs[0], errs


# Refused only in a variable a proxy reader takes: urllib.request reads every
# variable whose lower-cased name ends `_proxy` (getproxies_environment), and its
# _parse_proxy takes the user information up to the last `@` before the first `/`
# after the first `@`, so `#`, `?`, `/` and a scheme-less user part all ride
# into Proxy-Authorization. Each was measured on 3.11; outside a proxy name an
# RFC 3986 reader finds no user information in any of them.
_PROXY_ONLY = {
    "hash-in-password": "http://%s:%s#x@127.0.0.1:9" % (_USER, _PW),
    "query-in-password": "http://%s:%s?x@127.0.0.1:9" % (_USER, _PW),
    "slash-in-password": "http://%s:%s/x@127.0.0.1:9" % (_USER, _PW),
    "bare-slash-in-password": "%s:%s/x@127.0.0.1:9" % (_USER, _PW),
    "bare-token": "%s@proxy" % _PW,
    # 3.11 reads user `proxy.corp` and password `8080/p?q=` + the secret.
    "at-in-query": "http://proxy.corp:8080/p?q=%s@b" % _PW,
}


@pytest.mark.parametrize("form", sorted(_PROXY_ONLY))
@pytest.mark.parametrize("name", ["HTTPS_PROXY", "https_proxy", "Ftp_Proxy"])
def test_a_proxy_variable_is_judged_as_a_proxy_reader_reads_it(
    tmp_path, parent, name, form
):
    """A `*_proxy` value is refused wherever urllib's proxy parser finds a user
    part, by name and never by value; the same value in another variable is
    copied, because no URL reader takes user information from it there."""
    root = _root(
        tmp_path, _manifest(child_env__names=["PATH", "HOME", name, "SVC_URL"])
    )
    parent.setenv(name, _PROXY_ONLY[form])
    with pytest.raises(child_env.ChildEnvError) as caught:
        child_env.build_child_env(root=root)
    assert name in str(caught.value), caught.value
    for text in _texts(caught.value):
        assert _PW not in text and _USER not in text, "the error carries the value"
    parent.delenv(name)
    parent.setenv("SVC_URL", _PROXY_ONLY[form])
    assert child_env.build_child_env(root=root)["SVC_URL"] == _PROXY_ONLY[form]


@pytest.mark.parametrize(
    "value",
    ["sr_RS:sr@latin", "ca_ES:ca@valencia", "sr_RS@latin:sr_RS:en", "de_DE:de@euro"],
)
def test_a_locale_list_with_a_modifier_is_not_a_credential(tmp_path, parent, value):
    """Keel's own manifest allowlists LANGUAGE; a Serbian-Latin or Valencian
    user's value must not stop every child from starting."""
    parent.setenv("LANGUAGE", value)
    assert child_env.build_child_env(root=str(_ROOT))["LANGUAGE"] == value


def test_carries_credential_is_the_rule_build_child_env_applies():
    """The predicate is public so a caller that puts a value somewhere other
    than a child's environment (make's command line) judges it the same way."""
    assert child_env.carries_credential("PY", _FORMS["url"])
    assert child_env.carries_credential("https_proxy", _PROXY_ONLY["bare-token"])
    assert not child_env.carries_credential("PY", _PROXY_ONLY["bare-token"])
    assert not child_env.carries_credential("LANGUAGE", "sr_RS:sr@latin")
    assert not child_env.carries_credential("PY", "C:/x+y@z,w~1")
