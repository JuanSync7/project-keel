"""
title: child_env — the environment a child process inherits
kind: script
layer: n/a
summary: Builds the environment keel's code hands a process it starts. It starts from an empty dict and copies from os.environ only what config/project.json allows — a `child_env.names` entry, a name under a `child_env.prefixes` entry, a `make_targets` unattended or gate variable, and, for a named model adapter, that adapter's `models.credential_env` names — then adds the caller's `extra`. git's repository context (`child_env.repo_context_names`: the variables git binds to the repository it started a process in, such as a hook's GIT_DIR and GIT_INDEX_FILE) is never copied unless the call passes `repo_context=True`, and no allowlist source may list one; the opt-in is a keyword because it is one call's decision, visible where the child starts, not a project-wide setting. A copied value that carries user information is a credential whatever its variable is called: a user part in a URL's authority (after `scheme://` or a leading `//`, read as RFC 3986 reads it), a whole value that is a scheme-less `user[:password]@host:port`, or, in a variable a proxy reader takes (a name ending `_proxy` in any case), any user part urllib's proxy parser finds. carries_credential states that rule, and build_child_env refuses such a value with a ChildEnvError that names the variable and never the value, unless `child_env.credentialed_values` names it with a reason, the chosen adapter's `models.credential_env` declares it, or the call's `extra` replaces it. A missing, unreadable or malformed manifest is a ChildEnvError, never a fall-back to the parent's environment. It reads config/project.json on every call and writes nothing. scripts/check_structure.py check_X holds every spawn under the code roots to this helper. Defence-in-depth, not a sandbox (docs/adr/0012-child-process-environment-allowlist.md).
"""

# NB: stdlib only, no `from __future__ import annotations`, no f-strings, no walrus,
# no `list[str]` or `X | None` annotations. check_structure.py and cdmon_sync.py
# import this module, and .pre-commit-config.yaml runs them under a bare `python3`,
# which on a `language: system` hook is the committing shell's (3.6.8 on this
# host). tests/integration/test_gate_scope.py parses and runs it there.
# It does not import check_structure: check_structure imports it, and a gate
# runner child must not pay for the whole gate to build an environment.

import json
import os
import re
from typing import Dict, List, Mapping, NamedTuple, Optional, Set, Tuple

__all__ = ["ChildEnvError", "build_child_env", "carries_credential", "child_env_policy"]

_MANIFEST = os.path.join("config", "project.json")
_BLOCK = "child_env"
_BLOCK_KEYS = (
    "_comment",
    "names",
    "prefixes",
    "repo_context_names",
    "credentialed_values",
)
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PREFIX = re.compile(r"^[A-Za-z][A-Za-z0-9]*_$")
# make passes its command-line variables to every child through these. Carrying
# one across a Python hop would hand a nested make the outer make's goals and
# overrides, which no label of the nested target declared.
_MAKE_CONTROL = ("MAKEFLAGS", "MAKEFILES", "MAKELEVEL", "MAKEOVERRIDES", "MFLAGS")
# git's environment namespace (git(1), ENVIRONMENT VARIABLES). It decides
# nothing: it only picks the child_env.names entries a manifest without
# repo_context_names is told to check, since that manifest names no set itself.
_GIT_NAMESPACE = "GIT_"
# Where a value is judged decides what counts, because the readers disagree.
# 1. A URL authority starts after every literal `://` and after a leading `//`
#    (RFC 3986 section 3.2, the scheme-relative form included: urllib reads a
#    user and password out of `//u:p@proxy:8080`). It ends at the first `/`, `?`
#    or `#`; whitespace does not end it, because urllib.parse.urlsplit keeps
#    `u:p x@h` in the netloc (measured). Its user information, which curl, git,
#    pip and urllib all send, is the text before its last `@`; a token rides
#    there with no password, so any non-empty user part counts. Anchoring on the
#    literal `://` rather than matching a scheme keeps the scan linear
#    (`[A-Za-z][A-Za-z0-9+.-]*://` backtracked: 0.40 s on a 20 kB value).
_AUTHORITY_END = re.compile(r"[/?#]")
# 2. A whole value that is a scheme-less authority with an explicit port,
#    `user[:password]@host:port`, is read as an address by any client handed it.
#    The port is what separates it from ordinary values with `x:y@z` in them: a
#    glibc LANGUAGE list (`sr_RS:sr@latin`), USER's `name@domain` and an
#    scp-style `git@host:org/repo` never end in `@host:digits`.
_BARE_AUTHORITY = re.compile(r"^[^\s/@]+@(?:\[[0-9A-Fa-f:.]+\]|[^\s/@:\[\]]+):[0-9]+$")
# 3. A variable a proxy reader takes is judged as that reader reads it.
#    urllib.request.getproxies_environment takes every variable whose lower-cased
#    name ends in this suffix (curl reads `<scheme>_proxy` and ALL_PROXY), and
#    _parse_proxy, the widest reader measured, treats a scheme-less value as a
#    whole authority and a URL's authority as running to the first `/` after its
#    first `@`. So in a proxy value `#`, `?`, `/`, whitespace and a scheme-less
#    user part all reach Proxy-Authorization (measured on 3.11:
#    `http://u:p#w@h:9`, `tok@proxy`, and `http://h:8080/p?q=a@b`, read as user
#    `h`), while outside a proxy name rules 1 and 2 decide.
_PROXY_SUFFIX = "_proxy"
# urllib's _splittype: a scheme is the text before the first `:`, if no `/`
# comes first.
_PROXY_SCHEME = re.compile(r"[^/:]+:")

Policy = NamedTuple(
    "Policy",
    [
        ("names", Tuple[str, ...]),
        ("prefixes", Tuple[str, ...]),
        ("credentials", Dict[str, Tuple[str, ...]]),
        ("adapters", Optional[Tuple[str, ...]]),
        ("repo_context", Tuple[str, ...]),
        ("credentialed", Tuple[str, ...]),
    ],
)


class ChildEnvError(Exception):
    """The allowlist cannot be built, so no child may start.

    Deliberately not a RuntimeError: a caller that skips an absent model on
    models.ModelUnavailable (a RuntimeError) must not skip a broken config."""


def _name_list(value: object, where: str, errs: List[str]) -> Optional[List[str]]:
    """value as a list of unique, valid, non-control names, else None (errs grows)."""
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        errs.append("%s must be a list of environment variable names" % where)
        return None
    bad = [v for v in value if not _NAME.match(v)]
    if bad:
        errs.append(
            "%s: %s is not an environment variable name"
            % (where, ", ".join("`%s`" % v for v in bad))
        )
        return None
    dup = sorted({v for v in value if value.count(v) > 1})
    if dup:
        errs.append("%s names %s twice" % (where, ", ".join(dup)))
        return None
    control = [v for v in value if v in _MAKE_CONTROL]
    if control:
        errs.append(
            "%s names %s, which make uses to hand its command line to a child -- "
            "a nested make would inherit goals and overrides no label declared"
            % (where, ", ".join(control))
        )
        return None
    return list(value)


def _bound(source: str, names: List[str], fix: str) -> str:
    """The refusal for an allowlist source that re-admits a repository variable."""
    return (
        "%s %s, which child_env.repo_context_names marks as bound to the "
        "repository the parent was started in -- a child that runs git in another "
        "directory would act on that repository; %s (a child that must act on the "
        "parent's repository passes build_child_env(repo_context=True))"
        % (source, ", ".join(sorted(names)), fix)
    )


def _overlaps(
    repo_context: List[str],
    names: Optional[List[str]],
    prefixes: Optional[List[str]],
    make_vars: Dict[str, List[str]],
    credentials: Dict[str, Tuple[str, ...]],
) -> List[str]:
    """One error per allowlist source that would copy a repo_context name.

    A source that failed its own validation is None or absent here, so one root
    cause never also reports as an overlap."""
    bound = set(repo_context)
    errs: List[str] = []
    sources: List[Tuple[str, Optional[List[str]]]] = [("child_env.names", names)]
    sources.extend(("make_targets." + key, make_vars[key]) for key in sorted(make_vars))
    sources.extend(
        ("models.credential_env." + adapter, list(credentials[adapter]))
        for adapter in sorted(credentials)
    )
    for source, listed in sources:
        hit = sorted(bound & set(listed or ()))
        if hit:
            errs.append(_bound(source + " lists", hit, "remove them from %s" % source))
    for prefix in sorted(prefixes or ()):
        hit = sorted(n for n in bound if n.startswith(prefix))
        if hit:
            errs.append(
                _bound(
                    "child_env.prefixes `%s` admits" % prefix,
                    hit,
                    "remove `%s` from child_env.prefixes and list the names it "
                    "was for in child_env.names" % prefix,
                )
            )
    return errs


def _missing_repo_context(names: object) -> str:
    """The refusal for a manifest from before repo_context_names existed.

    Such a project's child_env.names usually still lists GIT_DIR and its
    siblings, and the overlap check needs the missing key to see them, so this
    one message carries both halves of the fix and names the candidates."""
    msg = (
        "child_env.repo_context_names is missing -- add it, listing the variables "
        "git binds to the repository it started a process in (`git rev-parse "
        "--local-env-vars`), and remove each of them from child_env.names, where "
        "a child would act on the parent's repository; keel's own "
        "config/project.json carries the list"
    )
    listed = names if isinstance(names, list) else []
    candidates = sorted(
        {n for n in listed if isinstance(n, str) and n.startswith(_GIT_NAMESPACE)}
    )
    if candidates:
        msg += (
            " (child_env.names lists %s: move each one `git rev-parse "
            "--local-env-vars` prints, keep the rest)" % ", ".join(candidates)
        )
    return msg


def _authorities(value: str) -> List[str]:
    """Each URL authority in value, as RFC 3986 delimits it (rule 1). Linear:
    a scan stops at the next `/`, and every later `://` holds one."""
    starts = [2] if value.startswith("//") else []
    at = value.find("://")
    while at != -1:
        starts.append(at + 3)
        at = value.find("://", at + 3)
    found = []
    for start in starts:
        end = _AUTHORITY_END.search(value, start)
        found.append(value[start : end.start() if end else len(value)])
    return found


def _proxy_userinfo(value: str) -> str:
    """The user information urllib's _parse_proxy reads from value (rule 3)."""
    scheme = _PROXY_SCHEME.match(value)
    rest = value[scheme.end() :] if scheme else value
    if not rest.startswith("/"):
        authority = value
    elif not rest.startswith("//"):
        return ""  # urllib refuses a proxy URL with no authority
    else:
        at = rest.find("@")
        end = rest.find("/", at if at != -1 else 2)
        authority = rest[2:] if end == -1 else rest[2:end]
    return authority.rpartition("@")[0]


def carries_credential(name: str, value: str) -> bool:
    """True when variable ``name``'s ``value`` carries user information. Pure.

    It is the rule build_child_env refuses a copied value by, for a caller that
    puts a value somewhere else a child can read (make's command line)."""
    if name.lower().endswith(_PROXY_SUFFIX) and _proxy_userinfo(value):
        return True
    if _BARE_AUTHORITY.match(value):
        return True
    return any(auth.rpartition("@")[0] for auth in _authorities(value))


def _credentialed(leaked: List[str]) -> str:
    """The refusal for copied values that carry a credential. Pure.

    It names the variables and never a value: the value is the credential, and
    this message reaches logs and terminals."""
    return (
        "build_child_env: %s %s user information (a `user[:password]@` in a "
        "URL's authority, a whole value `user[:password]@host:port`, or any user "
        "part a proxy reader finds in a `*_proxy` value), which is a "
        "credential and would reach every child -- remove the user information "
        "from each, or, if this project's children must authenticate with it, "
        "name each in config/project.json child_env.credentialed_values with the "
        "reason (docs/adr/0012-child-process-environment-allowlist.md)"
        % (", ".join(leaked), "holds" if len(leaked) == 1 else "hold")
    )


def _credentialed_values(value: object, errs: List[str]) -> Optional[Dict[str, str]]:
    """child_env.credentialed_values as name -> reason, else None (errs grows)."""
    if not isinstance(value, dict):
        errs.append(
            "child_env.credentialed_values must be an object of variable name -> "
            "reason (why this project's children may receive that variable's "
            "credential)"
        )
        return None
    bad = sorted(k for k in value if not _NAME.match(k))
    if bad:
        errs.append(
            "child_env.credentialed_values: %s is not an environment variable name"
            % ", ".join("`%s`" % k for k in bad)
        )
    bare = sorted(
        k
        for k in value
        if _NAME.match(k) and not (isinstance(value[k], str) and value[k].strip())
    )
    if bare:
        errs.append(
            "child_env.credentialed_values: %s carries no reason -- an entry says "
            "why this project's children may receive that variable's credential"
            % ", ".join("`%s`" % k for k in bare)
        )
    if bad or bare:
        return None
    return dict(value)


def _stale_credentialed(
    credentialed: Dict[str, str],
    copied: List[str],
    prefixes: List[str],
    repo_context: List[str],
) -> List[str]:
    """One error per credentialed_values entry no allowlist source copies.

    Such an entry grants nothing and reads as a reviewed exemption, so it is
    refused the way check_W refuses a stale effect_proof_skip entry."""
    return [
        "child_env.credentialed_values names `%s`, which no allowlist source "
        "copies (child_env.names, child_env.prefixes, child_env.repo_context_names "
        "or the make_targets variables) -- drop the stale entry; a model adapter's "
        "credential is declared in models.credential_env" % key
        for key in sorted(credentialed)
        if key not in copied
        and key not in repo_context
        and not any(key.startswith(p) for p in prefixes)
    ]


def _located(message: str) -> str:
    """message, prefixed with the manifest's path unless it already names it."""
    return message if message.startswith(_MANIFEST) else "%s: %s" % (_MANIFEST, message)


def child_env_policy(manifest: object) -> Tuple[Optional[Policy], List[str]]:
    """config/project.json (parsed) -> (policy, errs). Pure.

    policy is None whenever errs is not empty: a consumer refuses rather than
    half-trusting an allowlist. The errors name the key and what is wrong,
    without the manifest's path (each caller adds it)."""
    if not isinstance(manifest, dict):
        return None, ["the manifest must be a JSON object"]
    if _BLOCK not in manifest:
        return None, [
            "config/project.json has no child_env block -- a child process would "
            "have no allowlist to run with"
        ]
    block = manifest[_BLOCK]
    if not isinstance(block, dict):
        return None, ["child_env must be an object"]
    errs: List[str] = []
    errs.extend(
        "child_env has an unknown key `%s` (the keys are names, prefixes, "
        "repo_context_names, credentialed_values)" % key
        for key in sorted(block)
        if key not in _BLOCK_KEYS
    )
    names = _name_list(block.get("names"), "child_env.names", errs)
    repo_context: Optional[List[str]] = None
    if "repo_context_names" not in block:
        errs.append(_missing_repo_context(block.get("names")))
    elif block["repo_context_names"] == []:
        # A pass over zero names would hold nothing back and look like a guard.
        errs.append(
            "child_env.repo_context_names must name at least one variable -- an "
            "empty list holds back none of git's repository context"
        )
    else:
        repo_context = _name_list(
            block["repo_context_names"], "child_env.repo_context_names", errs
        )
    prefixes = block.get("prefixes")
    if not isinstance(prefixes, list) or not all(isinstance(p, str) for p in prefixes):
        errs.append("child_env.prefixes must be a list of prefixes such as `LC_`")
        prefixes = None
    else:
        bad = [p for p in prefixes if not _PREFIX.match(p)]
        if bad:
            errs.append(
                "child_env.prefixes: %s is not a letter-led prefix ending in `_` "
                "(a shorter one would admit a whole family of unrelated names)"
                % ", ".join("`%s`" % p for p in bad)
            )
            prefixes = None

    # Absent is no exemption, which already fails closed, so the key is
    # optional; empty is valid for the same reason (unlike repo_context_names,
    # it is an exemption list, not a guard).
    credentialed: Optional[Dict[str, str]] = {}
    if "credentialed_values" in block:
        credentialed = _credentialed_values(block["credentialed_values"], errs)

    extra_names: List[str] = []
    make_vars: Dict[str, List[str]] = {}
    make_ok = True
    targets = manifest.get("make_targets")
    if targets is not None and not isinstance(targets, dict):
        errs.append("make_targets must be an object")
        make_ok = False
    elif isinstance(targets, dict):
        for key in ("unattended_vars", "gate_vars"):
            if key in targets:
                got = _name_list(targets[key], "make_targets." + key, errs)
                extra_names.extend(got or [])
                if got is not None:
                    make_vars[key] = got
                else:
                    make_ok = False

    credentials: Dict[str, Tuple[str, ...]] = {}
    adapters: Optional[Tuple[str, ...]] = None
    models = manifest.get("models")
    if models is not None and not isinstance(models, dict):
        errs.append("models must be an object")
    elif isinstance(models, dict):
        available = models.get("available")
        if isinstance(available, dict):
            adapters = tuple(sorted(available))
        cred = models.get("credential_env")
        if cred is not None:
            if not isinstance(cred, dict):
                errs.append(
                    "models.credential_env must map a model adapter to the "
                    "credential names its child process needs"
                )
            else:
                for adapter in sorted(cred):
                    if adapters is None or adapter not in adapters:
                        errs.append(
                            "models.credential_env names `%s`, which is not in "
                            "models.available (%s)"
                            % (adapter, ", ".join(adapters or ()))
                        )
                        continue
                    got = _name_list(
                        cred[adapter], "models.credential_env.%s" % adapter, errs
                    )
                    if got is not None:
                        credentials[adapter] = tuple(sorted(got))

    if repo_context is not None:
        errs.extend(_overlaps(repo_context, names, prefixes, make_vars, credentials))
    # Judged only against sources that validated, so one root cause (a broken
    # names list, say) is never also reported as a stale entry.
    if (
        credentialed
        and names is not None
        and prefixes is not None
        and repo_context is not None
        and make_ok
    ):
        errs.extend(
            _stale_credentialed(
                credentialed, names + extra_names, prefixes, repo_context
            )
        )
    if (
        errs
        or names is None
        or prefixes is None
        or repo_context is None
        or credentialed is None
    ):
        return None, errs
    return (
        Policy(
            names=tuple(sorted(set(names) | set(extra_names))),
            prefixes=tuple(sorted(prefixes)),
            credentials=credentials,
            adapters=adapters,
            repo_context=tuple(sorted(repo_context)),
            credentialed=tuple(sorted(credentialed)),
        ),
        [],
    )


def build_child_env(
    credentials_for: Optional[str] = None,
    extra: Optional[Mapping[str, str]] = None,
    root: Optional[str] = None,
    repo_context: bool = False,
) -> Dict[str, str]:
    """The environment for a child process, built from the allowlist.

    ``credentials_for`` names a model adapter whose ``models.credential_env``
    names are added; ``extra`` is applied last, so a caller can set a variable
    explicitly. ``root`` is the project whose config/project.json is read
    (default: the project this module ships in). A declared name the parent
    lacks stays absent, never empty.
    ``repo_context=True`` also copies each ``child_env.repo_context_names``
    variable the parent holds (an empty value included): only for a child that
    must act on the repository git started the parent in, such as a hook helper
    on a bare repository, which cannot rediscover it from its cwd. Every other
    call leaves it False, so a child that runs git in another directory finds
    that directory's repository.
    A value copied from the parent that carries user information
    (carries_credential) is a credential: it is refused unless ``child_env.credentialed_values`` names its
    variable, the ``credentials_for`` adapter's ``models.credential_env``
    declares it, or ``extra`` replaces it. ``extra`` itself is the call site's
    own literal and is not judged.
    Raises ChildEnvError on a missing, unreadable or malformed manifest, an
    adapter not in models.available, a ``repo_context`` that is not a bool, an
    ``extra`` that is not name -> str, or a copied value carrying a credential
    (the error names the variables, never a value)."""
    # The type, not truthiness: "no" and 1 are truthy, and an opt-in that hands
    # a child the parent's repository must be the call site's explicit True.
    if type(repo_context) is not bool:
        raise ChildEnvError(
            "repo_context must be True or False, got %r" % (repo_context,)
        )
    if root is None:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, _MANIFEST)
    try:
        with open(path, encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError) as exc:
        raise ChildEnvError(
            "%s cannot be read (%s), so no child may start without an allowlist"
            % (_MANIFEST, exc)
        ) from exc
    policy, errs = child_env_policy(manifest)
    if policy is None:
        raise ChildEnvError("; ".join(_located(e) for e in errs))

    allowed = set(policy.names)
    env: Dict[str, str] = {}
    # What the allowlist copies unasked; only these are judged for a credential.
    inherited: Set[str] = set()
    for key in sorted(os.environ):
        if key in allowed or any(key.startswith(p) for p in policy.prefixes):
            env[key] = os.environ[key]
            inherited.add(key)
    if credentials_for is not None:
        if policy.adapters is not None and credentials_for not in policy.adapters:
            raise ChildEnvError(
                "%s: model adapter `%s` is not in models.available (%s), so it has "
                "no declared credentials"
                % (
                    _MANIFEST,
                    credentials_for,
                    ", ".join(policy.adapters),
                )
            )
        for key in policy.credentials.get(credentials_for, ()):
            if key in os.environ:
                env[key] = os.environ[key]
    if repo_context:
        for key in policy.repo_context:
            if key in os.environ:
                env[key] = os.environ[key]
                inherited.add(key)
    replaced: Set[str] = set()
    for key in sorted(extra or {}):
        value = (extra or {})[key]
        if not isinstance(key, str) or not _NAME.match(key) or key in _MAKE_CONTROL:
            raise ChildEnvError(
                "extra key %r is not an environment variable name a child may be "
                "given" % (key,)
            )
        if not isinstance(value, str):
            raise ChildEnvError(
                "extra value for %s must be a str, got %s" % (key, type(value).__name__)
            )
        env[key] = value
        replaced.add(key)
    # After extra, so a replaced parent value is never judged: it never reaches
    # the child.
    exempt = set(policy.credentialed)
    if credentials_for is not None:
        exempt |= set(policy.credentials.get(credentials_for, ()))
    leaked = sorted(
        k
        for k in inherited
        if k not in exempt and k not in replaced and carries_credential(k, env[k])
    )
    if leaked:
        # No `from`, and raised outside any except: no chained exception may
        # carry the value.
        raise ChildEnvError(_credentialed(leaked))
    return env
