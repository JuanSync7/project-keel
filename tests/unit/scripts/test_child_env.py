"""
title: Unit — child_env (the environment a child process inherits)
kind: tests
layer: n/a
summary: build_child_env starts from an empty dict and copies only what config/project.json allows — `child_env.names`, a name under a `child_env.prefixes` entry, the `make_targets` unattended and gate variables, and, for a named model adapter, that adapter's `models.credential_env` — then adds the caller's `extra` last. A planted secret such as AWS_SECRET_ACCESS_KEY or GITHUB_TOKEN never reaches the result unless declared, a declared name the parent lacks stays absent rather than empty, and a missing, unreadable or malformed manifest is a ChildEnvError, never a fall-back to the parent's environment. A `child_env.repo_context_names` variable reaches the result only when the call passes `repo_context=True`, and child_env_policy refuses an allowlist source that admits one, naming the source and the fix. A copied value carrying user information (a user part in a URL authority, a scheme-relative `//user@host` and a space in the password included; a whole value `user[:password]@host:port`; or, in a `*_proxy` variable, any user part urllib's proxy parser reads, `#`, `?` or `/` in the password and a scheme-less `token@proxy` included) is a ChildEnvError naming every such variable and never the value, whatever allowlist source copied it, unless `child_env.credentialed_values` names it, the called adapter declares it, or `extra` replaces it; child_env_policy refuses a credentialed_values entry that is malformed or that no allowlist source copies. A glibc locale list such as `LANGUAGE=sr_RS:sr@latin`, `name@domain`, and a non-proxy URL with an `@` after its host are copied verbatim. child_env_policy states the same rule without touching disk.
"""

import base64
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
        # Synthetic, not keel's: the rule must come from config, so a test that
        # passed only because the code knew git's names would fail here.
        "config_injection_names": ["TOOL_CONFIG_COUNT", "TOOL_CONFIG_PARAMETERS"],
        "config_injection_prefixes": ["TOOL_CONFIG_KEY_", "TOOL_CONFIG_VALUE_"],
        "credential_value_patterns": {"synthetic-token": "^SYNTH-[0-9]{6}$"},
        "login_name_schemes": ["vcs+login"],
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


def _own_policy_holds(manifest):
    """The policy *manifest* states is valid, lists no planted secret as a name,
    and mirrors what the manifest declares: each model adapter's credential
    names and the credentialed_values opt-ins. Read from the manifest, never a
    keel-only fact, so a project that opts a variable in passes the same check
    (that keel ships credentialed_values empty is pinned by the copier-excluded
    tests/integration/test_copier_generation.py)."""
    policy, errs = child_env.child_env_policy(manifest)
    assert policy is not None and errs == [], errs
    assert not set(_SECRETS) & set(policy.names)
    declared = manifest["models"].get("credential_env", {})
    assert policy.credentials == {
        adapter: tuple(sorted(names)) for adapter, names in declared.items()
    }, policy.credentials
    opted = manifest["child_env"].get("credentialed_values", {})
    assert policy.credentialed == tuple(sorted(opted)), policy.credentialed


def test_keels_own_policy_is_valid_and_never_lists_a_secret():
    _own_policy_holds(
        json.loads((_ROOT / "config" / "project.json").read_text("utf-8"))
    )


def _opt_in_name(manifest):
    """A name *manifest* itself allowlists, to opt in as a credentialed value:
    a proxy variable (a name ending `_proxy` in any case) when it lists one,
    the case an authenticating proxy brings, else its first allowlisted name --
    never a fixed name, because a project may drop the proxy names."""
    names = sorted(manifest["child_env"].get("names", []))
    proxies = [n for n in names if n.lower().endswith("_proxy")]
    if not (proxies or names):
        pytest.skip("config/project.json child_env.names allowlists no variable")
    return (proxies or names)[0]


def test_the_policy_check_holds_for_a_project_that_opts_a_variable_in():
    """The same check on this project's manifest with one of its allowlisted
    variables opted in, as an authenticating proxy is: a project that records
    one must not fail keel's own test."""
    manifest = json.loads((_ROOT / "config" / "project.json").read_text("utf-8"))
    manifest["child_env"]["credentialed_values"] = {
        _opt_in_name(manifest): "the project's proxy authenticates every request"
    }
    _own_policy_holds(manifest)


def _keel_policy():
    """Keel's own policy, read the way every consumer reads it."""
    manifest = json.loads((_ROOT / "config" / "project.json").read_text("utf-8"))
    policy, errs = child_env.child_env_policy(manifest)
    assert policy is not None and errs == [], errs
    return policy


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_keels_policy_holds_back_every_repository_variable_git_names(monkeypatch):
    """Keel's two lists are git's own: every name `--local-env-vars` prints is
    either repository context or configuration injection, never both, so a git
    that adds a variable reds this test rather than leaking it to a child."""
    policy = _keel_policy()
    r = subprocess.run(
        ["git", "rev-parse", "--local-env-vars"],
        capture_output=True,
        text=True,
        env=child_env.build_child_env(),
    )
    assert r.returncode == 0, r.stderr
    gits = set(r.stdout.split())
    assert len(gits) >= 10, r.stdout  # a pass over an empty listing is a failure
    held = set(policy.repo_context) | set(policy.config_injection)
    assert gits <= held, sorted(gits - held)
    assert not set(policy.repo_context) & set(policy.config_injection)
    assert {"GIT_NAMESPACE", "GIT_QUARANTINE_PATH"} <= set(policy.repo_context)
    # GIT_CONFIG is honoured by `git config` alone and is absent from the
    # listing on some git versions, so it is held by config, not by git's word.
    assert "GIT_CONFIG" in policy.config_injection
    for key in policy.repo_context:
        monkeypatch.setenv(key, "/planted")
    env = child_env.build_child_env(root=str(_ROOT))
    assert not set(policy.repo_context) & set(env), sorted(env)


# --- configuration injected through the environment -----------------------------------

_FAMILY = {
    "TOOL_CONFIG_COUNT": "1",
    "TOOL_CONFIG_KEY_0": "core.synthetic",
    "TOOL_CONFIG_VALUE_0": "/synthetic",
    "TOOL_CONFIG_KEY_17": "core.other",
    "TOOL_CONFIG_PARAMETERS": "'core.synthetic'='/synthetic2'",
}


def _in_family(key, policy):
    return key in policy.config_injection or any(
        key.startswith(p) for p in policy.config_injection_prefixes
    )


_ADMITS = [
    (
        "names",
        {"child_env__names": ["PATH", "HOME", "TOOL_CONFIG_PARAMETERS"]},
        "child_env.names",
        "TOOL_CONFIG_PARAMETERS",
    ),
    (
        "names-by-prefix",
        {"child_env__names": ["PATH", "HOME", "TOOL_CONFIG_KEY_0"]},
        "child_env.names",
        "TOOL_CONFIG_KEY_0",
    ),
    (
        "prefix-covers",
        {"child_env__prefixes": ["TOOL_"]},
        "child_env.prefixes",
        "TOOL_",
    ),
    (
        "prefix-overlaps",
        {"child_env__prefixes": ["TOOL_CONFIG_"]},
        "child_env.prefixes",
        "TOOL_CONFIG_",
    ),
    (
        "unattended",
        {"make_targets__unattended_vars": ["CI", "TOOL_CONFIG_COUNT"]},
        "make_targets.unattended_vars",
        "TOOL_CONFIG_COUNT",
    ),
    (
        "gate",
        {"make_targets__gate_vars": ["PY", "TOOL_CONFIG_COUNT"]},
        "make_targets.gate_vars",
        "TOOL_CONFIG_COUNT",
    ),
    (
        "credential",
        {"models__credential_env": {"a": ["A_KEY", "TOOL_CONFIG_PARAMETERS"]}},
        "models.credential_env.a",
        "TOOL_CONFIG_PARAMETERS",
    ),
]


@pytest.mark.parametrize(
    ("over", "source", "what"),
    [(o, s, w) for _, o, s, w in _ADMITS],
    ids=[i for i, _, _, _ in _ADMITS],
)
def test_a_policy_that_admits_a_config_injection_variable_is_refused_naming_the_source(
    tmp_path, parent, over, source, what
):
    """Every allowlist source that could copy a configuration-injection variable
    is refused, once, naming the source and the variable or prefix."""
    manifest = _manifest(**over)
    policy, errs = child_env.child_env_policy(manifest)
    assert policy is None and len(errs) == 1, errs
    assert source in errs[0] and what in errs[0], errs
    with pytest.raises(child_env.ChildEnvError):
        child_env.build_child_env(root=_root(tmp_path, manifest))
    assert child_env.child_env_policy(_MANIFEST)[1] == []


@pytest.mark.parametrize(
    "key",
    [
        "config_injection_names",
        "config_injection_prefixes",
        "credential_value_patterns",
    ],
)
def test_a_missing_config_injection_key_is_one_error_naming_the_fix(key):
    _, errs = child_env.child_env_policy(_manifest(**{"child_env__" + key: _DROP}))
    assert len(errs) == 1, errs
    assert "child_env." + key in errs[0] and "CONVENTIONS §15" in errs[0], errs
    empty = {} if key == "credential_value_patterns" else []
    _, errs = child_env.child_env_policy(_manifest(**{"child_env__" + key: empty}))
    assert len(errs) == 1 and "must not be empty" in errs[0], errs


def test_a_config_injection_prefix_may_hold_inner_underscores_and_must_end_in_one():
    for good in (["TOOL_CONFIG_KEY_"], ["Z_"]):
        policy, errs = child_env.child_env_policy(
            _manifest(child_env__config_injection_prefixes=good)
        )
        assert errs == [] and policy.config_injection_prefixes == tuple(good), errs
    for bad in ("TOOL_CONFIG_KEY", "_X_", "1A_", "A-B_"):
        _, errs = child_env.child_env_policy(
            _manifest(child_env__config_injection_prefixes=["TOOL_CONFIG_VALUE_", bad])
        )
        assert len(errs) == 1 and "`%s`" % bad in errs[0], (bad, errs)
    _, errs = child_env.child_env_policy(
        _manifest(child_env__config_injection_prefixes=["Z_", "Z_"])
    )
    assert len(errs) == 1 and "Z_" in errs[0] and "twice" in errs[0], errs
    # The allowlist's own prefixes keep their stricter grammar.
    _, errs = child_env.child_env_policy(
        _manifest(child_env__prefixes=["TOOL_CONFIG_KEY_"])
    )
    assert len(errs) == 1 and "child_env.prefixes" in errs[0], errs


@pytest.mark.parametrize("entry", ["TOOL_CONFIG_COUNT", "TOOL_CONFIG_KEY_X"])
def test_a_config_injection_entry_overlapping_repository_context_is_refused(entry):
    _, errs = child_env.child_env_policy(
        _manifest(child_env__repo_context_names=["GIT_DIR", "GIT_INDEX_FILE", entry])
    )
    assert len(errs) == 1, errs
    assert "child_env.repo_context_names" in errs[0] and entry in errs[0], errs


def test_the_config_injection_family_never_reaches_a_child(
    tmp_path, parent, monkeypatch
):
    """However the call is shaped, no member of the family is copied, and a
    count is never sent without its keys. extra= is the call site's literal and
    is honoured verbatim."""
    for key, value in _FAMILY.items():
        parent.setenv(key, value)
    root = _root(tmp_path, _MANIFEST)
    policy, _ = child_env.child_env_policy(_MANIFEST)
    for kwargs in ({}, {"repo_context": True}, {"credentials_for": "a"}):
        env = child_env.build_child_env(root=root, **kwargs)
        assert not [k for k in env if _in_family(k, policy)], (kwargs, sorted(env))
    env = child_env.build_child_env(root=root, extra={"TOOL_CONFIG_COUNT": "0"})
    assert env["TOOL_CONFIG_COUNT"] == "0"
    assert [k for k in env if _in_family(k, policy)] == ["TOOL_CONFIG_COUNT"]
    # Defence in depth: even a policy that admitted the family (one the
    # validator would refuse) copies none of it.
    widened = policy._replace(
        names=tuple(sorted(set(policy.names) | set(_FAMILY))),
        prefixes=("TOOL_",),
    )
    monkeypatch.setattr(child_env, "load_policy", lambda root=None: widened)
    env = child_env.build_child_env(root=root)
    assert not [k for k in env if _in_family(k, policy)], sorted(env)


def test_an_unknown_child_env_key_names_every_known_key():
    _, errs = child_env.child_env_policy(_manifest(child_env__bogus=1))
    assert len(errs) == 1 and "bogus" in errs[0], errs
    manifest = json.loads((_ROOT / "config" / "project.json").read_text("utf-8"))
    for key in set(manifest["child_env"]) | {"_comment"}:
        assert "`%s`" % key in errs[0].split("(the keys are", 1)[1], (key, errs)


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


# --- a credential recognised by the shape of its value --------------------------------


def _segment(raw):
    """One base64url JWT segment, unpadded, as a token issuer writes it."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


# A synthetic JWT, assembled at import: header, claims, a fake signature.
_JWT = ".".join(
    [_segment(b'{"alg":"HS256"}'), _segment(b'{"sub":"1234"}'), "Sf1Kx" * 4]
)

# Every literal is assembled from parts so no scanner reads this file as holding
# a credential, and no 12-character run of one may surface in an error, save a
# run of the label itself (a header's name is the label's word, not a secret).
_SHAPED = {
    "bearer": ("Bear" + "er " + "aB3dE5" * 4, "http-authorization"),
    "basic": (
        "Bas" + "ic " + "QWxhZGRp" + "bjpvcGVu" + "IHNlc2FtZQ==",
        "http-authorization",
    ),
    "token-scheme": ("tok" + "en " + "Zq9" * 6, "http-authorization"),
    "authorization-header": (
        "Author" + "ization: Bearer " + "aB3dE5" * 4,
        "authorization-header",
    ),
    "proxy-authorization-header": (
        "Proxy-Author" + "ization: Basic " + "QWxhZGRp" + "bjpvcGVu",
        "authorization-header",
    ),
    "jwt": (
        _JWT,
        "json-web-token",
    ),
    "prefixed-opaque": ("tok" + "_" + "aB3" * 12, "opaque-token"),
    "dashed-opaque": ("s" + "k-" + "Qr7" * 12, "opaque-token"),
    # `export X=" $(cat tokenfile)"` pads a token; a newline alone was caught
    # before, so a space or tab must be too.
    "space-padded-opaque": (" " + "aB3" * 12 + " ", "opaque-token"),
    "tab-padded-opaque": ("\t" + "Qr7" * 12, "opaque-token"),
    "authorization-header-no-space": (
        "Author" + "ization:Bearer " + "aB3dE5" * 4,
        "authorization-header",
    ),
    "pem": ("-----BEG" + "IN RSA PRIV" + "ATE KEY-----", "private-key"),
}


def _keel_manifest(**names):
    """Keel's own manifest, with extra allowlisted names, so the patterns under
    test are the ones keel ships."""
    manifest = json.loads((_ROOT / "config" / "project.json").read_text("utf-8"))
    manifest["child_env"]["names"] = sorted(
        set(manifest["child_env"]["names"]) | set(names.get("add", ()))
    )
    manifest["child_env"]["credentialed_values"] = names.get("credentialed", {})
    return manifest


def _runs(value, n=12):
    return {value[i : i + n] for i in range(max(1, len(value) - n + 1))}


@pytest.mark.parametrize("form", sorted(_SHAPED))
def test_a_credential_shaped_value_is_refused_naming_the_variable_and_label_never_the_value(
    tmp_path, parent, form
):
    """A value shaped like a header, a token or a key is refused by keel's
    shipped patterns, naming the variable and the label that matched; no
    rendering of the error carries any 12-character run of the value. The same
    exemptions apply as for user information."""
    value, label = _SHAPED[form]
    root = _root(tmp_path, _keel_manifest(add=["SVC_VALUE"]))
    parent.setenv("SVC_VALUE", value)
    with pytest.raises(child_env.ChildEnvError) as caught:
        child_env.build_child_env(root=root)
    exc = caught.value
    assert "SVC_VALUE=%s" % label in str(exc), exc
    assert "child_env.credentialed_values" in str(exc), exc
    for text in _texts(exc):
        carried = [r for r in _runs(value) if r in text and r.lower() not in label]
        assert not carried, "the error carries the value"
    assert exc.__cause__ is None and exc.__context__ is None
    assert (
        child_env.carries_credential("SVC_VALUE", value, child_env.load_policy(root))
        == label
    )
    (tmp_path / "exempt").mkdir()
    exempt = _root(
        tmp_path / "exempt",
        _keel_manifest(add=["SVC_VALUE"], credentialed={"SVC_VALUE": "a reason"}),
    )
    assert child_env.build_child_env(root=exempt)["SVC_VALUE"] == value
    parent.delenv("SVC_VALUE")
    env = child_env.build_child_env(root=root, extra={"SVC_VALUE": value})
    assert env["SVC_VALUE"] == value


# Each is a value some real environment holds; together they are the false-
# positive control for keel's patterns. "basic authentication" and "token
# placeholderstring" are the shapes only the http-authorization lookahead keeps.
_ORDINARY = {
    "SHA": "3f" + "a9c1e4b7d2" * 3 + "0b6e9d1a",
    "UUID": "123e4567-e89b-12d3-a456-426614174000",
    "PROSE": "basic authentication",
    "PLACEHOLDER": "token placeholderstring",
    "WORD": "Bearer",
    "CAMEL": "ThisIsALongCamelCaseIdentifierNameForTheBuild",
    "VERSION": "Python-3.11.4+local.build.20261008",
    "CERT": "-----BEGIN CERTIFICATE-----",
    "ONE_SEGMENT": _segment(b'{"alg":"HS256"}'),
    "LS_COLORS": "rs=0:di=01;34:ln=01;36:mh=00:pi=40;33",
    "MODULEPATH": "/etc/modulefiles:/usr/share/Modules/modulefiles",
    "HEADER_NAME": "X-Authorization-Mode",
    "SSH_URL": "ssh://git@host.example/org/repo",
    "SCP_URL": "git@host.example:org/repo.git",
    "UPPER_HEX": "ABCDEF0123456789ABCDEF0123456789AB",
    "PATH_LIKE": "/opt/toolchain-AB12cd34EF56gh78IJ90kl12MN34op/bin",
    # A colon-joined list whose entry is a directory named like the header: the
    # list's `:` is not a header colon, so none of these is a credential.
    "AUTHZ_DIR_LIST": "/opt/sso/authorization:/usr/bin:/bin",
    "AUTHZ_DIR_MIXED": "/home/u/.venvs/Authorization:Service/bin",
    "AUTHZ_DIR_FIRST": "authorization:/usr/bin",
    "AUTHZ_DIR_RELATIVE": "Proxy-Authorization:lib",
    "AUTHZ_HOST_PORT": "localhost,authorization:8080",
}


def test_an_ordinary_value_is_not_mistaken_for_a_credential(tmp_path, parent):
    values = dict(_ORDINARY)
    values.update({k: v for k, v in _CLEAN.items() if k != "PATH"})
    root = _root(tmp_path, _keel_manifest(add=sorted(values)))
    for key, value in values.items():
        parent.setenv(key, value)
    env = child_env.build_child_env(root=root)
    assert {k: env.get(k) for k in values} == values


@pytest.mark.parametrize(
    "path",
    [
        "/opt/sso/authorization:/usr/bin:/bin",
        "/usr/local/bin:/home/u/src/Authorization:/usr/bin",
        "authorization:/usr/bin",
    ],
)
def test_a_path_holding_a_directory_named_authorization_still_starts_a_child(
    tmp_path, parent, path
):
    """PATH is in every allowlist, so a pattern that read its `:` separator as a
    header colon would refuse every child the host starts; keel's shipped
    patterns copy such a PATH unchanged."""
    parent.setenv("PATH", path)
    root = _root(tmp_path, _keel_manifest())
    assert child_env.carries_credential("PATH", path, _keel_policy()) is None
    assert child_env.build_child_env(root=root)["PATH"] == path


def test_credential_value_patterns_are_validated_without_echoing_a_pattern():
    """A malformed pattern map is one error naming the key and the label; a
    pattern itself never appears in the error, since a project may write one
    that embeds a fragment of the secret it hunts."""
    literal = "SYNTH_LITERAL"
    cases = [
        (["^x$"], "child_env.credential_value_patterns must be an object"),
        ({"Bad_Label": "^x$"}, "Bad_Label"),
        ({"synthetic-token": 1}, "synthetic-token"),
        ({"synthetic-token": literal + "("}, "synthetic-token"),
        ({"synthetic-token": literal + "(?i)x"}, "synthetic-token"),
        ({"synthetic-token": "^x$", "other": literal + "[z-a]"}, "other"),
    ]
    for value, expected in cases:
        policy, errs = child_env.child_env_policy(
            _manifest(child_env__credential_value_patterns=value)
        )
        assert policy is None and len(errs) == 1, (value, errs)
        assert expected in errs[0], (value, errs)
        assert literal not in errs[0], errs
    _, errs = child_env.child_env_policy(
        _manifest(
            child_env__credential_value_patterns={"synthetic-token": literal + "(?i)x"}
        )
    )
    assert "global flag" in errs[0], errs


def test_the_value_patterns_come_from_config_not_code(tmp_path, parent):
    """The synthetic manifest's one pattern is the whole rule: its token is
    refused under its label, and keel's shapes pass, so nothing about them is
    written into the module."""
    root = _root(tmp_path, _manifest(child_env__names=["PATH", "HOME", "SVC_VALUE"]))
    parent.setenv("SVC_VALUE", "SYNTH-" + "123456")
    with pytest.raises(child_env.ChildEnvError) as caught:
        child_env.build_child_env(root=root)
    assert "SVC_VALUE=synthetic-token" in str(caught.value), caught.value
    for value, _ in _SHAPED.values():
        parent.setenv("SVC_VALUE", value)
        assert child_env.build_child_env(root=root)["SVC_VALUE"] == value
    source = (_ROOT / "scripts" / "child_env.py").read_text("utf-8")
    keel = _keel_manifest()["child_env"]["credential_value_patterns"]
    assert len(keel) >= 1
    for label, pattern in keel.items():
        assert label not in source and pattern not in source, label


def test_keels_value_patterns_scan_adversarial_values_in_linear_time():
    """Every inherited value meets every pattern, so a pattern that backtracks
    would stall each child start; 100 kB of each shape that tempts one must
    scan in well under two seconds."""
    import time

    policy = _keel_policy()
    assert policy.value_patterns, "a pass over zero patterns is a failure"
    n = 100000
    hostile = [
        "a" * n,
        " " * n,
        "Bearer " + " " * n + "x",
        "Bearer " + "a" * n + "!",
        "Bearer " + "A" * n + " x",
        "eyJ" + "a" * n,
        ".eyJ" * (n // 4),
        ".eyJaaaaaaaa" * (n // 12),
        "authorization" * (n // 13),
        "authorization:" + " " * n,
        "authorization:" + "a" * n,
        "/authorization:" * (n // 15),
        " " * n + "aB1",
        "\t" * n + "x",
        "aB" * (n // 2) + "1",
        "A1" * (n // 2),
        "-" * n,
        "-----BEGIN " + "A" * n,
        "x:" * (n // 2),
        "@" * n,
        "//" + "a:" * (n // 2),
    ]
    start = time.perf_counter()
    for value in hostile:
        child_env.carries_credential("SVC_VALUE", value, policy)
        child_env.carries_credential("https_proxy", value, policy)
    assert time.perf_counter() - start < 2.0


# --- a login name is not a credential in a login scheme -------------------------------


def test_a_login_name_alone_in_a_login_scheme_url_is_not_a_credential(tmp_path, parent):
    """In a listed scheme the user part is the account to log in as: it counts
    as a credential only with a non-empty password. Elsewhere, and in a proxy
    variable, the user part still counts."""
    root = _root(
        tmp_path,
        _manifest(child_env__names=["PATH", "HOME", "SVC_URL", "https_proxy"]),
    )
    policy = child_env.load_policy(root)
    copied = [
        "vcs+login://git@host.example/org/repo",
        "VCS+LOGIN://git@host.example/org/repo",
        "repo=vcs+login://git@host.example/x",
        "vcs+login://git:@host.example/x",
    ]
    refused = [
        "vcs+login://git:" + "pw@host.example/x",
        "https://" + "tokenvalue@host.example/x",
        "xvcs+login://git@host.example/x",
        "login://git@host.example/x",
    ]
    for value in copied:
        assert child_env.carries_credential("SVC_URL", value, policy) is None, value
        parent.setenv("SVC_URL", value)
        assert child_env.build_child_env(root=root)["SVC_URL"] == value
    for value in refused:
        assert child_env.carries_credential("SVC_URL", value, policy), value
        parent.setenv("SVC_URL", value)
        with pytest.raises(child_env.ChildEnvError):
            child_env.build_child_env(root=root)
    parent.delenv("SVC_URL")
    assert child_env.carries_credential("https_proxy", copied[0], policy)
    keel = _keel_policy()
    for scheme in ("ssh", "git+ssh", "ssh+git", "sftp"):
        value = scheme + "://git@host.example/org/repo"
        assert child_env.carries_credential("SVC_URL", value, keel) is None, value
        assert child_env.carries_credential(
            "SVC_URL", value.replace("git@", "git:" + "pw@"), keel
        )


def test_login_name_schemes_default_to_none_and_are_validated():
    policy, errs = child_env.child_env_policy(
        _manifest(child_env__login_name_schemes=_DROP)
    )
    assert errs == [] and policy.login_schemes == frozenset(), errs
    assert (
        child_env.carries_credential(
            "SVC_URL", "vcs+login://git@host.example/x", policy
        )
        == "url-userinfo"
    )
    for bad, expected in (
        ("ssh", "must be a list"),
        (["SSH"], "SSH"),
        (["1x"], "1x"),
        ([1], "child_env.login_name_schemes"),
        (["ssh", "ssh"], "twice"),
    ):
        _, errs = child_env.child_env_policy(
            _manifest(child_env__login_name_schemes=bad)
        )
        assert len(errs) == 1 and expected in errs[0], (bad, errs)
        assert "child_env.login_name_schemes" in errs[0], errs


def test_carries_credential_without_a_policy_keeps_its_structural_rules():
    """No policy means no patterns and no login schemes: the call answers with
    the structural label alone, so a value it once refused is still refused."""
    assert (
        child_env.carries_credential("SVC_URL", "ssh://git@host.example/x")
        == "url-userinfo"
    )
    assert (
        child_env.carries_credential("SVC_URL", "u:" + "p@proxy:3128")
        == "bare-authority"
    )
    assert child_env.carries_credential("https_proxy", "tok@proxy") == "proxy-userinfo"
    assert child_env.carries_credential("SVC_VALUE", _SHAPED["jwt"][0]) is None
    assert child_env.carries_credential("SVC_VALUE", "SYNTH-123456") is None
    assert child_env.carries_credential("PY", "C:/x+y@z,w~1") is None
