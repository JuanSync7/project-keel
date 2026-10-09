"""
title: child_env — the environment a child process inherits
kind: script
layer: n/a
summary: Builds the environment keel's code hands a process it starts. It starts from an empty dict and copies from os.environ only what config/project.json allows — a `child_env.names` entry, a name under a `child_env.prefixes` entry, a `make_targets` unattended or gate variable, and, for a named model adapter, that adapter's `models.credential_env` names — then adds the caller's `extra`. git's repository context (`child_env.repo_context_names`: the variables git binds to the repository it started a process in, such as a hook's GIT_DIR and GIT_INDEX_FILE) is never copied unless the call passes `repo_context=True`, and no allowlist source may list one; the opt-in is a keyword because it is one call's decision, visible where the child starts, not a project-wide setting. A copied value that carries user information is a credential whatever its variable is called: a user part in a URL's authority (after `scheme://` or a leading `//`, read as RFC 3986 reads it), a whole value that is a scheme-less `user[:password]@host:port`, or, in a variable a proxy reader takes (a name ending `_proxy` in any case), any user part urllib's proxy parser finds. carries_credential states that rule, and build_child_env refuses such a value with a ChildEnvError that names the variable and never the value, unless `child_env.credentialed_values` names it with a reason, the chosen adapter's `models.credential_env` declares it, or the call's `extra` replaces it; the same holds for a value matching a `child_env.credential_value_patterns` regular expression (the error names the variable and the pattern's label), and in a `child_env.login_name_schemes` URL (ssh, say) a user part with no password is a login name, not a credential. The configuration-injection family (`child_env.config_injection_names` and `config_injection_prefixes`: the variables through which a parent hands git its `-c` settings) is never copied from the parent, and child_env_policy refuses any allowlist source that admits a member. A missing, unreadable or malformed manifest is a ChildEnvError, never a fall-back to the parent's environment; a manifest that does not parse because an update left a merge-conflict hunk in it is named as that conflict, with the hunk's line and the step that finishes the update, using the grammar of scripts/jobs/conflict_guard.py, loaded by path only then (when it cannot load, the parse error stands and says the markers were not checked). It reads config/project.json on every call, declares that read in `PROJECT_READS` so a copier job whose imports reach it refuses over a conflicted manifest, and writes nothing. scripts/check_structure.py check_X holds every spawn under the code roots to this helper. Defence-in-depth, not a sandbox (docs/adr/keel/K-0012-child-process-environment-allowlist.md).
"""

# NB: stdlib only, no `from __future__ import annotations`, no f-strings, no walrus,
# no `list[str]` or `X | None` annotations. check_structure.py and cdmon_sync.py
# import this module, and .pre-commit-config.yaml runs them under a bare `python3`,
# which on a `language: system` hook is the committing shell's (3.6.8 on this
# host). tests/integration/test_gate_scope.py parses and runs it there.
# It does not import check_structure: check_structure imports it, and a gate
# runner child must not pay for the whole gate to build an environment.

import importlib.util
import json
import os
import re
from typing import (
    Dict,
    FrozenSet,
    Iterable,
    List,
    Mapping,
    NamedTuple,
    Optional,
    Set,
    Tuple,
)

__all__ = [
    "ChildEnvError",
    "build_child_env",
    "carries_credential",
    "child_env_policy",
    "load_policy",
]

_MANIFEST = os.path.join("config", "project.json")
# The fixed project file this module reads, declared for scripts/jobs/
# conflict_guard.py: a copier job whose imports reach here refuses, naming the
# file, when an update leaves it conflicted.
PROJECT_READS = ("config/project.json",)
# The merge-conflict grammar, loaded by path only when the manifest does not
# parse: importing it would put scripts/jobs on every caller's import path.
_GRAMMAR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "jobs", "conflict_guard.py"
)
_FINISH_DOC = "docs/guides/generate-and-upgrade.md, 'Finish an update that stopped'"
_BLOCK = "child_env"
_BLOCK_KEYS = (
    "_comment",
    "names",
    "prefixes",
    "repo_context_names",
    "config_injection_names",
    "config_injection_prefixes",
    "credential_value_patterns",
    "login_name_schemes",
    "credentialed_values",
)
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PREFIX = re.compile(r"^[A-Za-z][A-Za-z0-9]*_$")
# A configuration-injection prefix names a numbered family (git's
# GIT_CONFIG_KEY_<n>), so unlike an allowlist prefix it may hold inner
# underscores; it is a refusal list, and a longer prefix refuses less, never more.
_INJECTION_PREFIX = re.compile(r"^[A-Za-z][A-Za-z0-9_]*_$")
# A credential_value_patterns label: it is printed in a refusal instead of the
# value, so it is a plain word list a log reader can search for.
_LABEL = re.compile(r"^[a-z][a-z0-9-]*$")
# RFC 3986 section 3.1, lower-cased: a scheme is case-insensitive.
_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*$")
_SCHEME_CHAR = re.compile(r"[A-Za-z0-9+.-]")
# A global inline flag (`(?i)`) anywhere but the start: Python 3.11 refuses to
# compile it and 3.6 only warns, so the gate would disagree across the two
# interpreters keel runs under. Checked on the text, before compiling.
_LATE_GLOBAL_FLAG = re.compile(r".\(\?[aiLmsux]+\)")
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
        ("config_injection", FrozenSet[str]),
        ("config_injection_prefixes", Tuple[str, ...]),
        # (label, compiled pattern), sorted by label; object, not
        # typing.Pattern, which the 3.6 hook interpreter's typing lacks.
        ("value_patterns", Tuple[Tuple[str, object], ...]),
        ("login_schemes", FrozenSet[str]),
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


def _missing(key: str, what: str) -> str:
    """The refusal for a required key an older manifest lacks."""
    return (
        "child_env.%s is missing -- add it, %s; keel's own config/project.json "
        "carries the list (see CONVENTIONS §15)" % (key, what)
    )


def _injection(
    block: Dict[str, object], errs: List[str]
) -> Tuple[Optional[List[str]], Optional[List[str]]]:
    """child_env.config_injection_names and _prefixes, each None when invalid.

    Both are required and non-empty: an absent or empty refusal list would
    refuse nothing and look like a guard."""
    names: Optional[List[str]] = None
    key = "config_injection_names"
    if key not in block:
        errs.append(
            _missing(
                key,
                "listing the variables through which a parent hands git "
                "configuration (`git -c` settings, an extra config file)",
            )
        )
    elif block[key] == []:
        errs.append(
            "child_env.%s must not be empty -- an empty list refuses none of "
            "the variables that carry a parent's git configuration" % key
        )
    else:
        names = _name_list(block[key], "child_env." + key, errs)

    prefixes: Optional[List[str]] = None
    key = "config_injection_prefixes"
    value = block.get(key)
    if key not in block:
        errs.append(
            _missing(
                key,
                "listing the prefixes of the numbered variables a parent hands "
                "git configuration through (GIT_CONFIG_KEY_<n>)",
            )
        )
    elif value == []:
        errs.append(
            "child_env.%s must not be empty -- an empty list refuses none of "
            "the numbered configuration variables" % key
        )
    elif not isinstance(value, list) or not all(isinstance(p, str) for p in value):
        errs.append("child_env.%s must be a list of prefixes ending in `_`" % key)
    else:
        bad = [p for p in value if not _INJECTION_PREFIX.match(p)]
        dup = sorted({p for p in value if value.count(p) > 1})
        if bad:
            errs.append(
                "child_env.%s: %s is not a letter-led prefix ending in `_`"
                % (key, ", ".join("`%s`" % p for p in bad))
            )
        elif dup:
            errs.append("child_env.%s names %s twice" % (key, ", ".join(dup)))
        else:
            prefixes = list(value)
    return names, prefixes


def _injects(source: str, names: List[str], fix: str) -> str:
    """The refusal for an allowlist source that admits configuration injection."""
    return (
        "%s %s, which child_env.config_injection_names or "
        "child_env.config_injection_prefixes marks as configuration a parent "
        "hands git through the environment -- a child would run git with the "
        "parent's `-c` settings (a hook path or a credential helper among them); "
        "%s" % (source, ", ".join(sorted(names)), fix)
    )


def _admits_injection(
    injection: List[str],
    injection_prefixes: List[str],
    names: Optional[List[str]],
    prefixes: Optional[List[str]],
    make_vars: Dict[str, List[str]],
    credentials: Dict[str, Tuple[str, ...]],
) -> List[str]:
    """One error per allowlist source that would copy a configuration-injection
    variable: a listed name in the family, or an allowlist prefix that covers,
    or is covered by, a family member."""
    family = set(injection)

    def hits(listed: Iterable[str]) -> List[str]:
        return sorted(
            n
            for n in listed
            if n in family or any(n.startswith(p) for p in injection_prefixes)
        )

    errs: List[str] = []
    sources: List[Tuple[str, Optional[List[str]]]] = [("child_env.names", names)]
    sources.extend(("make_targets." + key, make_vars[key]) for key in sorted(make_vars))
    sources.extend(
        ("models.credential_env." + adapter, list(credentials[adapter]))
        for adapter in sorted(credentials)
    )
    for source, listed in sources:
        hit = hits(listed or ())
        if hit:
            errs.append(
                _injects(source + " lists", hit, "remove them from %s" % source)
            )
    for prefix in sorted(prefixes or ()):
        hit = sorted(n for n in family if n.startswith(prefix)) + sorted(
            p
            for p in injection_prefixes
            if p.startswith(prefix) or prefix.startswith(p)
        )
        if hit:
            errs.append(
                _injects(
                    "child_env.prefixes `%s` admits" % prefix,
                    hit,
                    "remove `%s` from child_env.prefixes and list the names it "
                    "was for in child_env.names" % prefix,
                )
            )
    return errs


def _injection_overlap(
    repo_context: List[str], injection: List[str], injection_prefixes: List[str]
) -> List[str]:
    """One error when a name is both repository context and injection: the two
    lists are held back for different reasons, and a name in both would leave
    `repo_context=True` handing a child the parent's configuration."""
    hit = sorted(
        n
        for n in repo_context
        if n in injection or any(n.startswith(p) for p in injection_prefixes)
    )
    if not hit:
        return []
    return [
        "child_env.repo_context_names lists %s, which child_env.config_injection_names "
        "or child_env.config_injection_prefixes also covers -- a variable is "
        "repository context or configuration injection, never both; remove it "
        "from one" % ", ".join(hit)
    ]


def _value_patterns(
    block: Dict[str, object], errs: List[str]
) -> Optional[Tuple[Tuple[str, object], ...]]:
    """child_env.credential_value_patterns as sorted (label, compiled), else None.

    An error names the label and never the pattern: a project may write a
    pattern that holds a fragment of the secret it hunts."""
    key = "credential_value_patterns"
    if key not in block:
        errs.append(
            _missing(
                key,
                "mapping a label to a regular expression a credential's value "
                "matches (a header, a token, a key)",
            )
        )
        return None
    value = block[key]
    if not isinstance(value, dict):
        errs.append(
            "child_env.%s must be an object of label -> regular expression" % key
        )
        return None
    if not value:
        errs.append(
            "child_env.%s must not be empty -- an empty map recognises no "
            "credential by its value" % key
        )
        return None
    compiled: List[Tuple[str, object]] = []
    ok = True
    for label in sorted(value):
        pattern = value[label]
        where = "child_env.%s `%s`" % (key, label)
        if not _LABEL.match(label):
            errs.append("%s: the label is not lower-case words joined by `-`" % where)
            ok = False
        elif not isinstance(pattern, str):
            errs.append("%s must be a regular expression string" % where)
            ok = False
        elif _LATE_GLOBAL_FLAG.search(pattern):
            errs.append(
                "%s sets a global flag after its start, which Python 3.11 refuses "
                "-- scope it, `(?i:...)`, or move it to the start (the pattern "
                "is not shown)" % where
            )
            ok = False
        else:
            try:
                compiled.append((label, re.compile(pattern)))
            except re.error:
                # The message is not kept: re.error quotes the pattern.
                errs.append(
                    "%s is not a valid regular expression (the pattern is not "
                    "shown)" % where
                )
                ok = False
    return tuple(compiled) if ok else None


def _login_schemes(
    block: Dict[str, object], errs: List[str]
) -> Optional[FrozenSet[str]]:
    """child_env.login_name_schemes, else None (errs grows). Absent is empty:
    no scheme, so every user part counts, the fail-closed reading."""
    key = "login_name_schemes"
    value = block.get(key, [])
    where = "child_env." + key
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        errs.append("%s must be a list of URL schemes such as `ssh`" % where)
        return None
    bad = [v for v in value if not _SCHEME.match(v)]
    if bad:
        errs.append(
            "%s: %s is not a lower-case URL scheme (RFC 3986 section 3.1)"
            % (where, ", ".join("`%s`" % v for v in bad))
        )
        return None
    dup = sorted({v for v in value if value.count(v) > 1})
    if dup:
        errs.append("%s names %s twice" % (where, ", ".join(dup)))
        return None
    return frozenset(value)


def _is_login(value: str, at: int, login_schemes: FrozenSet[str], longest: int) -> bool:
    """Whether the scheme ending at value[at] (the `:` of `://`) is a login
    scheme. Bounded: it reads at most the longest scheme plus one character,
    so the scan stays linear however many `://` the value holds."""
    window = value[max(0, at - longest - 1) : at].lower()
    for scheme in login_schemes:
        if window.endswith(scheme):
            before = at - len(scheme) - 1
            # `xssh://` is the scheme `xssh`, not `ssh`.
            if before < 0 or not _SCHEME_CHAR.match(value[before]):
                return True
    return False


def _authorities(
    value: str, login_schemes: FrozenSet[str] = frozenset()
) -> List[Tuple[str, bool]]:
    """Each URL authority in value, as RFC 3986 delimits it (rule 1), with
    whether its scheme is a login scheme. Linear: a scan stops at the next `/`,
    and every later `://` holds one."""
    longest = max([len(s) for s in login_schemes] or [0])
    starts = [(2, False)] if value.startswith("//") else []
    at = value.find("://")
    while at != -1:
        login = bool(login_schemes) and _is_login(value, at, login_schemes, longest)
        starts.append((at + 3, login))
        at = value.find("://", at + 3)
    found = []
    for start, login in starts:
        end = _AUTHORITY_END.search(value, start)
        found.append((value[start : end.start() if end else len(value)], login))
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


def carries_credential(
    name: str, value: str, policy: Optional[Policy] = None
) -> Optional[str]:
    """The label of the credential variable ``name``'s ``value`` carries, or
    None. Pure.

    The structural labels come first: `proxy-userinfo` (a user part a proxy
    reader finds in a `*_proxy` value), `bare-authority` (a whole value
    `user[:password]@host:port`) and `url-userinfo` (a user part in a URL's
    authority; in a ``policy.login_schemes`` URL only one with a password).
    Then, given a policy, each ``child_env.credential_value_patterns`` label
    in order. It is the rule build_child_env refuses a copied value by, for a
    caller that puts a value somewhere else a child can read (make's command
    line)."""
    if name.lower().endswith(_PROXY_SUFFIX) and _proxy_userinfo(value):
        return "proxy-userinfo"
    if _BARE_AUTHORITY.match(value):
        return "bare-authority"
    schemes = policy.login_schemes if policy is not None else frozenset()
    for authority, login in _authorities(value, schemes):
        user = authority.rpartition("@")[0]
        # In a login scheme the user part is the account to log in as; only a
        # password after it is a secret.
        if user.partition(":")[2] if login else user:
            return "url-userinfo"
    if policy is not None:
        for label, pattern in policy.value_patterns:
            if pattern.search(value):  # type: ignore[attr-defined]
                return label
    return None


def _credentialed(leaked: List[Tuple[str, str]]) -> str:
    """The refusal for copied values that carry a credential. Pure.

    It names the variables and the label each matched, and never a value: the
    value is the credential, and this message reaches logs and terminals."""
    names = sorted(name for name, _ in leaked)
    return (
        "build_child_env: %s %s a credential (user information in a URL's "
        "authority, a whole value `user[:password]@host:port`, a user part a "
        "proxy reader finds in a `*_proxy` value, or a match for "
        "child_env.credential_value_patterns), which would reach every child -- "
        "remove it from each, or, if this project's children must authenticate "
        "with it, name each in config/project.json child_env.credentialed_values "
        "with the reason (docs/adr/keel/K-0012-child-process-environment-allowlist.md) "
        "(matched: %s)"
        % (
            ", ".join(names),
            "holds" if len(names) == 1 else "hold",
            ", ".join("%s=%s" % pair for pair in sorted(leaked)),
        )
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
    known = ", ".join("`%s`" % k for k in sorted(_BLOCK_KEYS))
    errs.extend(
        "child_env has an unknown key `%s` (the keys are %s)" % (key, known)
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

    injection, injection_prefixes = _injection(block, errs)
    value_patterns = _value_patterns(block, errs)
    login_schemes = _login_schemes(block, errs)

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
    if injection is not None and injection_prefixes is not None:
        errs.extend(
            _admits_injection(
                injection, injection_prefixes, names, prefixes, make_vars, credentials
            )
        )
        if repo_context is not None:
            errs.extend(_injection_overlap(repo_context, injection, injection_prefixes))
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
        or injection is None
        or injection_prefixes is None
        or value_patterns is None
        or login_schemes is None
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
            config_injection=frozenset(injection),
            config_injection_prefixes=tuple(sorted(injection_prefixes)),
            value_patterns=value_patterns,
            login_schemes=login_schemes,
        ),
        [],
    )


def _hunk_line(path: str) -> Optional[int]:
    """The line of the first merge-conflict hunk in *path*, or None; raises
    whatever loading the grammar or reading the file raises."""
    spec = importlib.util.spec_from_file_location("_keel_conflict_grammar", _GRAMMAR)
    if spec is None or spec.loader is None:
        raise ImportError("no loader for %s" % _GRAMMAR)
    grammar = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(grammar)
    with open(path, "rb") as fh:
        text = fh.read().decode("utf-8", "replace")
    line = grammar.conflict_line(text)
    return None if line is None else int(line)


def _unparsed(path: str, exc: ValueError) -> str:
    """The message for a manifest that does not parse: the conflict an update
    left in it when there is one, else the parse error itself. A grammar that
    cannot load leaves the parse error standing and says so."""
    unchecked = ""
    try:
        line = _hunk_line(path)
    except Exception as why:  # noqa: BLE001 -- any failure keeps the parse error
        line = None
        unchecked = " (conflict markers not checked: %s)" % why
    if line is not None:
        return (
            "%s holds a merge-conflict hunk at line %d, so no child may start "
            "without an allowlist; resolve it, then finish the update (%s)"
            % (_MANIFEST, line, _FINISH_DOC)
        )
    return "%s cannot be read (%s), so no child may start without an allowlist%s" % (
        _MANIFEST,
        exc,
        unchecked,
    )


def load_policy(root: Optional[str] = None) -> Policy:
    """The policy *root*'s config/project.json states (default: the project
    this module ships in), or ChildEnvError naming every fault. Reads; writes
    nothing."""
    if root is None:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, _MANIFEST)
    try:
        with open(path, encoding="utf-8") as fh:
            manifest = json.load(fh)
    except OSError as exc:
        raise ChildEnvError(
            "%s cannot be read (%s), so no child may start without an allowlist"
            % (_MANIFEST, exc)
        ) from exc
    except ValueError as exc:
        raise ChildEnvError(_unparsed(path, exc)) from exc
    policy, errs = child_env_policy(manifest)
    if policy is None:
        raise ChildEnvError("; ".join(_located(e) for e in errs))
    return policy


def _injected(key: str, policy: Policy) -> bool:
    """Whether key is a configuration-injection variable the policy names."""
    return key in policy.config_injection or any(
        key.startswith(p) for p in policy.config_injection_prefixes
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
    A value copied from the parent that carries user information or matches a
    ``child_env.credential_value_patterns`` pattern (carries_credential, given
    the policy) is a credential: it is refused unless
    ``child_env.credentialed_values`` names its variable, the ``credentials_for`` adapter's ``models.credential_env``
    declares it, or ``extra`` replaces it. ``extra`` itself is the call site's
    own literal and is not judged.
    Raises ChildEnvError on a missing, unreadable or malformed manifest, an
    adapter not in models.available, a ``repo_context`` that is not a bool, an
    ``extra`` that is not name -> str, or a copied value carrying a credential
    (the error names the variables and the labels they matched, never a
    value). No configuration-injection variable is copied from the parent."""
    # The type, not truthiness: "no" and 1 are truthy, and an opt-in that hands
    # a child the parent's repository must be the call site's explicit True.
    if type(repo_context) is not bool:
        raise ChildEnvError(
            "repo_context must be True or False, got %r" % (repo_context,)
        )
    policy = load_policy(root)

    allowed = set(policy.names)
    env: Dict[str, str] = {}
    # What the allowlist copies unasked; only these are judged for a credential.
    inherited: Set[str] = set()
    # The configuration-injection family is skipped on every copy path, even
    # one the validator would have refused: a parent's `-c` settings never
    # reach a child's git (extra=, the call site's own literal, still may).
    for key in sorted(os.environ):
        if _injected(key, policy):
            continue
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
            if key in os.environ and not _injected(key, policy):
                env[key] = os.environ[key]
    if repo_context:
        for key in policy.repo_context:
            if key in os.environ and not _injected(key, policy):
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
    leaked: List[Tuple[str, str]] = []
    for key in sorted(inherited - exempt - replaced):
        label = carries_credential(key, env[key], policy)
        if label is not None:
            leaked.append((key, label))
    if leaked:
        # No `from`, and raised outside any except: no chained exception may
        # carry the value.
        raise ChildEnvError(_credentialed(leaked))
    return env
