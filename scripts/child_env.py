"""
title: child_env — the environment a child process inherits
kind: script
layer: n/a
summary: Builds the environment keel's code hands a process it starts. It starts from an empty dict and copies from os.environ only what config/project.json allows — a `child_env.names` entry, a name under a `child_env.prefixes` entry, a `make_targets` unattended or gate variable, and, for a named model adapter, that adapter's `models.credential_env` names — then adds the caller's `extra`. git's repository context (`child_env.repo_context_names`: the variables git binds to the repository it started a process in, such as a hook's GIT_DIR and GIT_INDEX_FILE) is never copied unless the call passes `repo_context=True`, and no allowlist source may list one; the opt-in is a keyword because it is one call's decision, visible where the child starts, not a project-wide setting. A missing, unreadable or malformed manifest is a ChildEnvError, never a fall-back to the parent's environment. It reads config/project.json on every call and writes nothing. scripts/check_structure.py check_X holds every spawn under the code roots to this helper. Defence-in-depth, not a sandbox (docs/adr/0012-child-process-environment-allowlist.md).
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
from typing import Dict, List, Mapping, NamedTuple, Optional, Tuple

__all__ = ["ChildEnvError", "build_child_env", "child_env_policy"]

_MANIFEST = os.path.join("config", "project.json")
_BLOCK = "child_env"
_BLOCK_KEYS = ("_comment", "names", "prefixes", "repo_context_names")
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

Policy = NamedTuple(
    "Policy",
    [
        ("names", Tuple[str, ...]),
        ("prefixes", Tuple[str, ...]),
        ("credentials", Dict[str, Tuple[str, ...]]),
        ("adapters", Optional[Tuple[str, ...]]),
        ("repo_context", Tuple[str, ...]),
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
        "repo_context_names)" % key
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

    extra_names: List[str] = []
    make_vars: Dict[str, List[str]] = {}
    targets = manifest.get("make_targets")
    if targets is not None and not isinstance(targets, dict):
        errs.append("make_targets must be an object")
    elif isinstance(targets, dict):
        for key in ("unattended_vars", "gate_vars"):
            if key in targets:
                got = _name_list(targets[key], "make_targets." + key, errs)
                extra_names.extend(got or [])
                if got is not None:
                    make_vars[key] = got

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
    if errs or names is None or prefixes is None or repo_context is None:
        return None, errs
    return (
        Policy(
            names=tuple(sorted(set(names) | set(extra_names))),
            prefixes=tuple(sorted(prefixes)),
            credentials=credentials,
            adapters=adapters,
            repo_context=tuple(sorted(repo_context)),
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
    Raises ChildEnvError on a missing, unreadable or malformed manifest, an
    adapter not in models.available, a ``repo_context`` that is not a bool, or
    an ``extra`` that is not name -> str."""
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
    for key in sorted(os.environ):
        if key in allowed or any(key.startswith(p) for p in policy.prefixes):
            env[key] = os.environ[key]
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
    return env
