#!/usr/bin/env python3
"""
title: launch — decide where a long script runs, and say why in one line
kind: script
layer: n/a
summary: The one place that decides where a long script runs, and the one that runs it, called as `launch.py [--root DIR] [--dry-run] -- <command>...`. It works out three facts from what is true now and fails closed toward the least shared harm. The host kind is `own` only when this host's lower-cased name matches an fnmatch pattern in the git-ignored file config/project.json `launcher.own_hosts_file` names; an absent, unreadable, malformed, empty or unmatched file means `shared`, and a set `inside_env` variable of the active farm adapter means `in-farm-job`. The script length comes from the launch key, argv with variable assignments and absolute paths removed: `long-listed` when `launcher.long_scripts` lists it, `long-recorded` when its last recorded run in `launcher.durations_file` took more than `launcher.long_after_seconds`, `short` only when its last run succeeded within that, and `unknown` otherwise, which counts as long. The farm is the `launcher.farm.adapters` entry `launcher.farm.adapter` names, behind the Farm interface: kind `none` (NoFarm) is no farm and is never asked to submit, and kind `argv` (ArgvFarm) submits through a config argv with the config env it renders. A farm job, an own host or a short script runs here; a long or unknown script on a shared host runs here limited (os.nice of `launcher.limited.niceness`, nothing else) when it is `launcher.local_only` or there is no farm, and goes to the farm otherwise. The command starts with `build_child_env` (scripts/child_env.py), given the model adapter `launcher.credentials` names for the launch key and, for a farm submission only, the adapter's rendered env; a launch whose environment would hold a credential name that key's `launcher.credentials` entry does not list is refused before anything runs. After a farm submission the status passes through, the command re-runs here limited when the farm did not allocate and the host is spare (max(load1, load5) per cpu at most `launcher.spare.max_load_per_cpu`; an unknown load is not spare), stops with ExitCode.NO_CAPACITY and runs nothing when it is not, and ends with exit 2 when the farm refused. Every decision is one stderr line naming the decision and its three reasons, never a host name or an absolute path; a fallback adds a second. Before it reads anything it refuses with exit 2 a config block that load_launcher_config rejects, a state path reached through a symlink (scripts/git_tree.py `through_symlink`), a state path git would list, and a git that ran and failed. `--dry-run` prints the decision and runs and writes nothing. A run writes the durations file whole: an `incomplete` entry before the command starts, then the outcome, the whole seconds, the status and where it ran, one canonical-JSON entry per launch key, written to a temporary file in the same directory and moved over the old one; an interrupt is recorded as `interrupted` with status 130, a submission the farm refused or whose submit program is absent restores the entry it replaced, and a farm that did not start the command on a host with no spare compute records `no-capacity`. Neither `incomplete` nor `no-capacity` replaces an entry whose measured duration is over `launcher.long_after_seconds` (`unmeasured_record`): no run was measured, so that one stays the last, and a full farm or a killed launch never hides a long script from long_scripts.py. Stdlib-only and 3.6-safe, because its shebang runs it under the host python3. It is defence in depth for shared compute, not a scheduler: it neither queues, retries nor caps CPU or memory (docs/adr/keel/K-0020-shared-compute-launcher.md).
effect: writes
rerun: fixed-point
rerun_proof: test:tests/integration/test_idempotence.py
"""

# NB: stdlib only, no `from __future__ import annotations`, no f-strings, no
# walrus, no dataclass, and only bare scripts/ siblings that keep the same rule
# (child_env, exit_codes, git_tree): the shebang runs this under the host python3, which
# may be 3.6 (tests/integration/test_gate_scope.py `_old_python_safe`).

import argparse
import contextlib
import fnmatch
import json
import math
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from typing import NamedTuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import child_env  # noqa: E402 — the one allowlist a child's environment comes from
import git_tree  # noqa: E402 — the one definition of what git lists
from exit_codes import ExitCode, finish, passthrough, report  # noqa: E402

__all__ = [
    "ADAPTER_KINDS",
    "FARM_OUTCOMES",
    "FARM_STATES",
    "HOST_KINDS",
    "LENGTH_KINDS",
    "PLACEHOLDERS",
    "RUN_OUTCOMES",
    "RUN_WHERE",
    "WHERE",
    "Adapter",
    "ArgvFarm",
    "Credential",
    "Decision",
    "Farm",
    "LauncherConfig",
    "LauncherConfigError",
    "NoFarm",
    "Size",
    "after_farm",
    "command_for",
    "decide",
    "durations_text",
    "explain",
    "host_kind",
    "load_launcher_config",
    "make_farm",
    "recorded_seconds",
    "render",
    "run_outcome",
    "run_where",
    "script_key",
    "script_length",
    "size_for",
    "spare",
    "unlisted_credentials",
    "unmeasured_record",
]

_MANIFEST = os.path.join("config", "project.json")
_BLOCK = "launcher"
_DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The closed vocabularies a decision is spelled in; the one-line explanation
# prints them verbatim, so a caller that reads stderr can match on them.
HOST_KINDS = ("in-farm-job", "own", "shared")
LENGTH_KINDS = ("long-listed", "long-recorded", "short", "unknown")
WHERE = ("here", "here-limited", "farm")
FARM_OUTCOMES = ("passthrough", "here-limited", "stop-no-capacity", "farm-refused")
ADAPTER_KINDS = ("argv", "none")
# What a farm's status says about one submission: the command ran (its own
# status), the farm did not allocate within its wait, or the farm refused it.
FARM_STATES = ("ran", "not-allocated", "refused")
# What one recorded run says: its outcome and where it ran. A record holding
# anything else is from another shape and reads as unknown, never as short.
RUN_OUTCOMES = ("succeeded", "failed", "interrupted", "no-capacity", "incomplete")
RUN_WHERE = ("own-host", "shared-host", "farm")
# The only names a submit word or a farm env value may hold, as `{name}`. A
# closed set substituted by exact token, never str.format, so a config value
# cannot reach an attribute or an index of what it is rendered with.
PLACEHOLDERS = (
    "cpus",
    "farm_error_status",
    "mem_gb",
    "minutes",
    "not_allocated_status",
    "wait_seconds",
)
_TOKEN = re.compile(r"\{([^{}]*)\}")

_TOP_KEYS = (
    "credentials",
    "default_size",
    "durations_file",
    "farm",
    "limited",
    "local_only",
    "long_after_seconds",
    "long_scripts",
    "own_hosts_file",
    "spare",
)
_SIZE_KEYS = ("cpus", "mem_gb", "minutes")
_ARGV_KEYS = (
    "env",
    "farm_error_status",
    "inside_env",
    "kind",
    "not_allocated_status",
    "submit",
)
_COMMENT = "_comment"
# os.nice's useful range: 0 would not limit anything, and 19 is the floor every
# Unix clamps to.
_NICE_MIN, _NICE_MAX = 1, 19
# A load per cpu above this is no real host's, so a threshold past it would call
# every host spare and switch the check off without saying so.
_LOAD_PER_CPU_MAX = 64
# A status the farm reserves must be one a process can exit with and one no
# other party already gives a meaning: 0 is success, 126 and 127 are the
# shell's "not executable" and "not found", 130 is an interrupt, and 255 is
# what an out-of-range status becomes.
_STATUS_MIN, _STATUS_MAX = 1, 254
_STATUS_TAKEN = (126, 127, 130)
# An environment variable name as POSIX shells spell one, the same rule
# scripts/child_env.py applies to the names it copies.
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# A make or shell variable assignment as one argv word: dropped from the launch
# key, so a PY path or a secret passed as NAME=VALUE never reaches the state file.
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# An adapter name is printed in the one-line explanation, so it is one plain word.
_ADAPTER_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
# Control characters would break the one stderr line apart.
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class LauncherConfigError(Exception):
    """config/project.json `launcher` cannot be used; the message names the key
    path and the fix."""


Size = NamedTuple("Size", [("cpus", int), ("mem_gb", int), ("minutes", int)])
Credential = NamedTuple("Credential", [("model_adapter", object), ("names", tuple)])
Adapter = NamedTuple(
    "Adapter",
    [
        ("name", str),
        ("kind", str),
        ("submit", tuple),
        ("env", dict),
        ("not_allocated_status", object),
        ("farm_error_status", object),
        ("inside_env", tuple),
    ],
)
LauncherConfig = NamedTuple(
    "LauncherConfig",
    [
        ("own_hosts_file", str),
        ("durations_file", str),
        ("long_after_seconds", int),
        ("long_scripts", dict),
        ("default_size", Size),
        ("local_only", dict),
        ("credentials", dict),
        ("niceness", int),
        ("max_load_per_cpu", float),
        ("farm_adapter", str),
        ("wait_seconds", int),
        ("adapters", dict),
    ],
)
# where: one of WHERE. farm_state is the farm part of the explanation, derived
# here so the line and the decision cannot disagree.
Decision = NamedTuple(
    "Decision",
    [
        ("where", str),
        ("key", str),
        ("adapter", str),
        ("niceness", int),
        ("farm_state", str),
    ],
)


# --- the config block ---------------------------------------------------------


def _path(*parts):
    return ".".join((_BLOCK,) + tuple(parts))


def _refuse_key(path, problem, fix):
    raise LauncherConfigError("config/project.json %s %s; %s" % (path, problem, fix))


def _object(value, path, required, optional=()):
    if not isinstance(value, dict):
        _refuse_key(path, "is not a JSON object", "write it as one")
    missing = [k for k in required if k not in value]
    if missing:
        _refuse_key(
            "%s.%s" % (path, missing[0]),
            "is missing",
            "add it (config/project.json.jinja holds the shipped default)",
        )
    unknown = sorted(
        k for k in value if k not in required and k not in optional and k != _COMMENT
    )
    if unknown:
        _refuse_key(
            "%s.%s" % (path, unknown[0]),
            "is not a key the launcher reads",
            "remove it, or correct its spelling",
        )
    return value


def _int(value, path, low, high=None):
    # type(), not isinstance: JSON `true` loads as a bool, which is an int.
    if type(value) is not int or value < low or (high is not None and value > high):
        bound = "%d or more" % low if high is None else "%d to %d" % (low, high)
        _refuse_key(path, "is %r, not a whole number %s" % (value, bound), "correct it")
    return value


def _text(value, path):
    if not isinstance(value, str) or not value.strip() or _CONTROL.search(value):
        _refuse_key(
            path,
            "is %r, not a non-blank one-line string" % (value,),
            "write it as one line of text",
        )
    return value


def _state_path(value, path):
    """A repo-relative POSIX path that stays inside the project: the launcher
    reads or writes there, so it may not climb out."""
    _text(value, path)
    parts = value.split("/")
    if value.startswith("/") or "\\" in value or ".." in parts or "" in parts:
        _refuse_key(
            path,
            "is %r, not a repo-relative path inside the project" % value,
            "write a relative path with no `..`, such as the shipped default",
        )
    return value


def _names(value, path):
    if not isinstance(value, list) or not all(
        isinstance(v, str) and _ENV_NAME.match(v) for v in value
    ):
        _refuse_key(
            path,
            "is %r, not a list of environment variable names" % (value,),
            "list names such as OPENAI_API_KEY",
        )
    if len(set(value)) != len(value):
        _refuse_key(path, "names a variable twice", "list each name once")
    return tuple(value)


def _size(value, path):
    _object(value, path, _SIZE_KEYS)
    return Size(*[_int(value[k], "%s.%s" % (path, k), 1) for k in _SIZE_KEYS])


def _launch_key(value, path):
    """A map key that script_key can produce: anything else would never match a
    launch, so the entry would be dead config that looks alive."""
    _text(value, path)
    words = value.split(" ")
    if "" in words or script_key(words, "/") != value:
        _refuse_key(
            path,
            "is not a launch key: script_key never produces it",
            "write the command as the launch line prints it, such as `make verify`",
        )
    return value


def _keyed(value, path, entry):
    if not isinstance(value, dict):
        _refuse_key(path, "is not a JSON object", "write it as one")
    out = {}
    for key in sorted(value):
        where = "%s.%s" % (path, key)
        _launch_key(key, where)
        out[key] = entry(value[key], where)
    return out


def _credential(available):
    def read(value, path):
        _object(value, path, ("model_adapter", "names"))
        adapter = value["model_adapter"]
        if adapter is not None and (
            not isinstance(adapter, str) or adapter not in available
        ):
            _refuse_key(
                path + ".model_adapter",
                "is %r, which config/project.json models.available does not list"
                % (adapter,),
                "name a listed model adapter, or null",
            )
        return Credential(adapter, _names(value["names"], path + ".names"))

    return read


def render(template, values):
    """*template* with each `{name}` replaced by str(values[name]), for a name in
    PLACEHOLDERS. Raises LauncherConfigError for any other `{...}`, an
    unmatched brace, or a placeholder *values* has no value for."""
    out, at = [], 0
    for match in _TOKEN.finditer(template):
        out.append(_literal(template[at : match.start()], template))
        name = match.group(1)
        if name not in PLACEHOLDERS:
            raise LauncherConfigError(
                "%r holds the placeholder %s, which is not one of {%s}"
                % (template, match.group(0), "}, {".join(PLACEHOLDERS))
            )
        if name not in values:
            raise LauncherConfigError(
                "%r holds the placeholder %s, which has no value here"
                % (template, match.group(0))
            )
        out.append(str(values[name]))
        at = match.end()
    out.append(_literal(template[at:], template))
    return "".join(out)


def _literal(text, template):
    if "{" in text or "}" in text:
        raise LauncherConfigError(
            "%r holds an unmatched brace; a placeholder is written {name}" % template
        )
    return text


def _templated(value, path):
    """Refuse a template that render would refuse, with every placeholder given
    a value, so a bad token is a config error before anything runs."""
    try:
        render(value, dict.fromkeys(PLACEHOLDERS, 1))
    except LauncherConfigError as exc:
        _refuse_key(path, "is not a valid template: %s" % exc, "correct it")
    return value


def _status(value, path):
    _int(value, path, _STATUS_MIN, _STATUS_MAX)
    if value in _STATUS_TAKEN:
        _refuse_key(
            path,
            "is %d, which already means not executable, not found or interrupted"
            % value,
            "choose another status in %d to %d" % (_STATUS_MIN, _STATUS_MAX),
        )
    return value


def _adapter(name, value, path):
    if not isinstance(name, str) or not _ADAPTER_NAME.match(name):
        _refuse_key(path, "is not a plain lower-case adapter name", "rename it")
    if not isinstance(value, dict) or value.get("kind") not in ADAPTER_KINDS:
        _refuse_key(
            path + ".kind",
            "is %r, not one of %s"
            % (value.get("kind") if isinstance(value, dict) else value, ADAPTER_KINDS),
            "use none (no farm) or argv (submit through a command)",
        )
    if value["kind"] == "none":
        _object(value, path, ("kind",))
        return Adapter(name, "none", (), {}, None, None, ())
    _object(value, path, _ARGV_KEYS)
    submit = value["submit"]
    if not isinstance(submit, list) or not submit:
        _refuse_key(path + ".submit", "is not a non-empty list", "list the argv words")
    for i, word in enumerate(submit):
        if not isinstance(word, str) or not word:
            _refuse_key(
                "%s.submit[%d]" % (path, i), "is %r, not a word" % (word,), "correct it"
            )
        _templated(word, "%s.submit[%d]" % (path, i))
    env = value["env"]
    if not isinstance(env, dict):
        _refuse_key(path + ".env", "is not a JSON object", "write it as one")
    for var in sorted(env):
        if not _ENV_NAME.match(var) or not isinstance(env[var], str):
            _refuse_key(
                "%s.env.%s" % (path, var),
                "is not a variable name with a string value",
                "correct it",
            )
        _templated(env[var], "%s.env.%s" % (path, var))
    absent = _status(value["not_allocated_status"], path + ".not_allocated_status")
    refused = _status(value["farm_error_status"], path + ".farm_error_status")
    if absent == refused:
        _refuse_key(
            path + ".farm_error_status",
            "equals not_allocated_status, so a refusal would read as a full farm",
            "give the two different statuses",
        )
    return Adapter(
        name,
        "argv",
        tuple(submit),
        dict(env),
        absent,
        refused,
        _names(value["inside_env"], path + ".inside_env"),
    )


def load_launcher_config(manifest):
    """LauncherConfig from config/project.json's parsed *manifest*. Raises
    LauncherConfigError naming the key path and the fix for an absent block, a
    missing, unknown or mistyped key, or a value outside its range."""
    if not isinstance(manifest, dict) or _BLOCK not in manifest:
        raise LauncherConfigError(
            "config/project.json has no `launcher` block; add it "
            "(config/project.json.jinja holds the shipped default)"
        )
    block = _object(manifest[_BLOCK], _BLOCK, _TOP_KEYS)
    limited = _object(block["limited"], _path("limited"), ("niceness",))
    spare_block = _object(block["spare"], _path("spare"), ("max_load_per_cpu",))
    threshold = spare_block["max_load_per_cpu"]
    if (
        not isinstance(threshold, (int, float))
        or isinstance(threshold, bool)
        or not math.isfinite(threshold)
        or not 0 < threshold <= _LOAD_PER_CPU_MAX
    ):
        _refuse_key(
            _path("spare", "max_load_per_cpu"),
            "is %r, not a number above 0 and at most %d"
            % (threshold, _LOAD_PER_CPU_MAX),
            "set the load per cpu below which this host counts as spare, such as 0.25",
        )
    farm = _object(
        block["farm"], _path("farm"), ("adapter", "wait_seconds", "adapters")
    )
    raw_adapters = farm["adapters"]
    if not isinstance(raw_adapters, dict) or not raw_adapters:
        _refuse_key(
            _path("farm", "adapters"),
            "is not a non-empty JSON object",
            "keep at least the none adapter",
        )
    adapters = {
        name: _adapter(name, raw_adapters[name], _path("farm", "adapters", name))
        for name in sorted(raw_adapters)
    }
    if farm["adapter"] not in adapters:
        _refuse_key(
            _path("farm", "adapter"),
            "is %r, which launcher.farm.adapters does not define" % (farm["adapter"],),
            "name one of %s" % ", ".join(sorted(adapters)),
        )
    models = manifest.get("models")
    available = (models or {}).get("available") if isinstance(models, dict) else None
    return LauncherConfig(
        own_hosts_file=_state_path(block["own_hosts_file"], _path("own_hosts_file")),
        durations_file=_state_path(block["durations_file"], _path("durations_file")),
        long_after_seconds=_int(
            block["long_after_seconds"], _path("long_after_seconds"), 1
        ),
        long_scripts=_keyed(block["long_scripts"], _path("long_scripts"), _size),
        default_size=_size(block["default_size"], _path("default_size")),
        local_only=_keyed(block["local_only"], _path("local_only"), _text),
        credentials=_keyed(
            block["credentials"],
            _path("credentials"),
            _credential(
                set(available) if isinstance(available, (dict, list)) else set()
            ),
        ),
        niceness=_int(
            limited["niceness"], _path("limited", "niceness"), _NICE_MIN, _NICE_MAX
        ),
        max_load_per_cpu=float(threshold),
        farm_adapter=farm["adapter"],
        wait_seconds=_int(farm["wait_seconds"], _path("farm", "wait_seconds"), 1),
        adapters=adapters,
    )


# --- the facts ------------------------------------------------------------------


def _key_word(word, root):
    if word.startswith("-") and "=" in word:
        # `--basetemp=/tmp/x`: the option names what was asked, the value is
        # where, and a where may be a home path.
        return word.split("=", 1)[0]
    if os.path.isabs(word):
        return _relative(word, root)
    return word


def _relative(word, root):
    path, base = os.path.normpath(word), os.path.normpath(root)
    if path == base:
        return "."
    prefix = base.rstrip(os.sep) + os.sep
    if path.startswith(prefix):
        return path[len(prefix) :]
    # Outside the project the directory says only whose machine it is.
    return os.path.basename(path) or path


def script_key(argv, root):
    """The launch key of *argv*: the program's basename, then each later word
    except a NAME=VALUE assignment, an `-opt=value` cut to `-opt`, and an
    absolute path made relative to *root* (its basename when outside), joined
    by single spaces. `['make', 'PY=.venv/bin/python', 'check-all']` is
    `make check-all`."""
    words = []
    for i, word in enumerate(argv):
        if i == 0:
            words.append(os.path.basename(word) or word)
        elif not _ASSIGNMENT.match(word):
            words.append(_key_word(word, root))
    return " ".join(words)


def host_kind(hostname, patterns_text, inside_job, unreadable=False):
    """(kind, reason), kind in HOST_KINDS. *patterns_text* is the own-hosts
    file's text, None when the file is absent; *unreadable* says it exists and
    could not be read. A farm job wins; otherwise the host is `own` only when
    its lower-cased name, trailing dot dropped, matches a pattern of the file's
    `own_hosts` list by fnmatch, and `shared` in every other case. The reason
    never names the host or a pattern."""
    if inside_job:
        return "in-farm-job", "already inside a farm job"
    if unreadable:
        return "shared", "own-hosts file unreadable"
    if patterns_text is None:
        return "shared", "no own-hosts file"
    try:
        data = json.loads(patterns_text)
    except ValueError:
        return "shared", "own-hosts file is not JSON"
    if not isinstance(data, dict):
        return "shared", "own-hosts file is not a JSON object"
    patterns = data.get("own_hosts")
    if not isinstance(patterns, list):
        return "shared", "own-hosts file has no own_hosts list"
    if not patterns:
        return "shared", "own_hosts is empty"
    if not all(isinstance(p, str) and p.strip() for p in patterns):
        return "shared", "own_hosts holds an entry that is not a pattern"
    name = hostname.strip().rstrip(".").lower() if isinstance(hostname, str) else ""
    if not name:
        return "shared", "this host reports no name"
    # fnmatch is the pattern language on purpose: the file holds patterns, not
    # names, and host names are case-insensitive, so both sides are lowered.
    if any(fnmatch.fnmatchcase(name, p.strip().lower()) for p in patterns):
        return "own", "an own_hosts pattern matches this host"
    return "shared", "no own_hosts pattern matches this host"


def _valid_record(record):
    if not isinstance(record, dict) or set(record) != {
        "outcome",
        "seconds",
        "status",
        "where",
    }:
        return False
    seconds, status = record["seconds"], record["status"]
    return (
        record["outcome"] in RUN_OUTCOMES
        and record["where"] in RUN_WHERE
        and (seconds is None or (type(seconds) is int and seconds >= 0))
        and (status is None or type(status) is int)
    )


def script_length(key, cfg, durations):
    """(kind, reason), kind in LENGTH_KINDS. *durations* is the parsed durations
    file, {launch key: record}, or None when it was unreadable or malformed.
    Only a run that succeeded proves a script short: a failed or interrupted run
    bounds the duration from below, so under the threshold it is unknown."""
    if key in cfg.long_scripts:
        return "long-listed", "listed in launcher.long_scripts"
    if durations is None:
        return "unknown", "durations file unreadable or malformed"
    if key not in durations:
        return "unknown", "never recorded"
    record = durations[key]
    if not _valid_record(record):
        return "unknown", "last record malformed"
    outcome, seconds = record["outcome"], record["seconds"]
    if outcome == "incomplete":
        return "unknown", "last run did not finish"
    if outcome == "no-capacity":
        return "unknown", "last attempt did not run"
    if seconds is None:
        return "unknown", "last run has no duration"
    limit = cfg.long_after_seconds
    if seconds > limit:
        return "long-recorded", "last run took %d s > %d s" % (seconds, limit)
    if outcome == "succeeded":
        return "short", "last run succeeded in %d s <= %d s" % (seconds, limit)
    return "unknown", "last run %s after %d s, a lower bound" % (outcome, seconds)


def spare(loadavg, ncpu, threshold):
    """(is spare, reason): max(load1, load5) / *ncpu* at most *threshold*. An
    absent or short *loadavg*, or an *ncpu* that is None or below 1, is an
    unknown load, which is never spare."""
    try:
        load = max(float(loadavg[0]), float(loadavg[1]))
    except (TypeError, IndexError, ValueError):
        return False, "load unknown"
    if type(ncpu) is not int or ncpu < 1 or not math.isfinite(load) or load < 0:
        return False, "load unknown"
    ratio = load / ncpu
    if ratio <= threshold:
        return True, "load %.4g per cpu <= %g" % (ratio, threshold)
    return False, "load %.4g per cpu > %g" % (ratio, threshold)


# --- the decision ---------------------------------------------------------------


def decide(host, length, cfg, key):
    """Decision for *host* and *length*, each a (kind, reason) pair, under
    *cfg*: a farm job, an own host or a short script runs here; a long or
    unknown script on a shared host runs here limited when local-only or with
    no farm, and goes to the farm otherwise."""
    if host[0] not in HOST_KINDS or length[0] not in LENGTH_KINDS:
        raise ValueError(
            "decide takes a host kind and a script length, not %r, %r"
            % (host[0], length[0])
        )
    adapter = cfg.adapters[cfg.farm_adapter]
    no_farm = adapter.kind == "none"

    def made(where, state):
        return Decision(where, key, adapter.name, cfg.niceness, state)

    if host[0] in ("in-farm-job", "own") or length[0] == "short":
        return made("here", "no farm configured" if no_farm else "not used")
    if key in cfg.local_only:
        return made(
            "here-limited",
            "no farm configured"
            if no_farm
            else "not used: local-only, %s" % cfg.local_only[key],
        )
    if no_farm:
        return made("here-limited", "no farm configured")
    return made("farm", "submitting, wait up to %d s" % cfg.wait_seconds)


def after_farm(status, adapter, spare_result):
    """One of FARM_OUTCOMES for the status an argv *adapter*'s submission ended
    with: farm-refused for its farm_error_status; for its not_allocated_status
    here-limited when *spare_result* (spare's pair) says spare, else
    stop-no-capacity; passthrough for every other status, the command's own."""
    if adapter.kind != "argv":
        raise ValueError(
            "after_farm reads an argv adapter's status, not %r" % adapter.kind
        )
    state = ArgvFarm(adapter).classify(status)
    if state == "refused":
        return "farm-refused"
    if state == "not-allocated":
        return "here-limited" if spare_result[0] is True else "stop-no-capacity"
    return "passthrough"


def explain(decision, host, length, farm_state=None):
    """The one line that says what was decided and why: `launch: <action>: host
    <kind> (<reason>); script "<key>" <kind> (<reason>); farm <adapter>
    (<state>)`. *farm_state* replaces the decision's own. The key is printed as
    a JSON string, so a quote or a line break in it stays on the line."""
    action = {
        "here": "run here",
        "here-limited": "run here limited (nice %d)" % decision.niceness,
        "farm": "submit to farm %s" % decision.adapter,
    }[decision.where]
    line = "launch: %s: host %s (%s); script %s %s (%s); farm %s (%s)" % (
        action,
        host[0],
        host[1],
        json.dumps(decision.key),
        length[0],
        length[1],
        decision.adapter,
        decision.farm_state if farm_state is None else farm_state,
    )
    # Every part is a fixed word or validated config; this holds the one-line
    # promise even for a value a future caller passes unchecked.
    return _CONTROL.sub(" ", line)


# --- the farm -------------------------------------------------------------------


class Farm(object):
    """What the launcher asks of a farm: the words that submit a command of a
    size, the variables the submission needs, and what a status it ended with
    says, one of FARM_STATES. `name` is the launcher.farm.adapters key."""

    name = ""

    def submit_argv(self, size, cfg):
        raise NotImplementedError

    def submit_env_extra(self, size, cfg):
        raise NotImplementedError

    def classify(self, status):
        raise NotImplementedError


class NoFarm(Farm):
    """Kind `none`: there is no farm, so decide never sends a command to it and
    every question is a caller's defect, raised as ValueError."""

    def __init__(self, adapter):
        self.name = adapter.name

    def _no_farm(self):
        raise ValueError(
            "the %s adapter is no farm, so nothing is submitted to it" % self.name
        )

    def submit_argv(self, size, cfg):
        self._no_farm()

    def submit_env_extra(self, size, cfg):
        self._no_farm()

    def classify(self, status):
        self._no_farm()


class ArgvFarm(Farm):
    """Kind `argv`: a submission is the adapter's `submit` words, each rendered,
    with the command after them, under the adapter's rendered `env`; its own
    reserved statuses say it did not allocate or refused."""

    def __init__(self, adapter):
        if adapter.kind != "argv":
            raise ValueError("ArgvFarm takes an argv adapter, not %r" % adapter.kind)
        self.adapter = adapter
        self.name = adapter.name

    def _values(self, size, cfg):
        return {
            "cpus": size.cpus,
            "farm_error_status": self.adapter.farm_error_status,
            "mem_gb": size.mem_gb,
            "minutes": size.minutes,
            "not_allocated_status": self.adapter.not_allocated_status,
            "wait_seconds": cfg.wait_seconds,
        }

    def submit_argv(self, size, cfg):
        values = self._values(size, cfg)
        return [render(word, values) for word in self.adapter.submit]

    def submit_env_extra(self, size, cfg):
        values = self._values(size, cfg)
        return {
            name: render(self.adapter.env[name], values)
            for name in sorted(self.adapter.env)
        }

    def classify(self, status):
        if type(status) is not int:
            raise TypeError("a farm status is an int, not %r" % (status,))
        if status == self.adapter.farm_error_status:
            return "refused"
        if status == self.adapter.not_allocated_status:
            return "not-allocated"
        return "ran"


def make_farm(cfg):
    """The Farm for the adapter `launcher.farm.adapter` names."""
    adapter = cfg.adapters[cfg.farm_adapter]
    if adapter.kind == "none":
        return NoFarm(adapter)
    return ArgvFarm(adapter)


def size_for(key, cfg):
    """The farm size of *key*: its `launcher.long_scripts` entry, else
    `launcher.default_size`."""
    return cfg.long_scripts.get(key, cfg.default_size)


def command_for(decision, farm, cfg, argv):
    """The argv list a runner is handed: *farm*'s submit words then *argv* for
    a farm decision, else *argv* alone. Never a shell string."""
    if decision.where == "farm":
        return farm.submit_argv(size_for(decision.key, cfg), cfg) + list(argv)
    return list(argv)


# --- the run record -------------------------------------------------------------


def run_outcome(returncode):
    """(outcome, status) for a child's *returncode*: the status as the shell
    spells it (passthrough), `interrupted` for the interrupt status, `succeeded`
    for 0 and `failed` for any other."""
    status = int(passthrough(returncode))
    if status == 0:
        return "succeeded", status
    if status == int(ExitCode.INTERRUPTED):
        return "interrupted", status
    return "failed", status


def recorded_seconds(record):
    """The whole seconds a well-formed *record* measured, else None: only a run
    that started and ended (succeeded, failed or interrupted) has a duration,
    so None is unknown and never zero."""
    if not _valid_record(record):
        return None
    if record["outcome"] not in ("succeeded", "failed", "interrupted"):
        return None
    return record["seconds"]


def run_where(where, host):
    """One of RUN_WHERE for a decision's *where* and the *host* kind: a farm
    submission or a run inside a farm job ran on the farm, an own host is
    `own-host`, and every other run shared this host."""
    if where not in WHERE or host not in HOST_KINDS:
        raise ValueError(
            "run_where takes a where and a host kind, not %r, %r" % (where, host)
        )
    if where == "farm" or host == "in-farm-job":
        return "farm"
    if host == "own":
        return "own-host"
    return "shared-host"


def durations_text(durations, key, record):
    """The whole durations file after *key*'s entry becomes *record*: every
    other well-formed entry kept, a malformed one dropped, *key* dropped when
    *record* is None, as canonical JSON (sorted keys, two-space indent, one
    final newline). *durations* None (unreadable) keeps nothing. Raises
    ValueError for a *record* that is not well formed."""
    if record is not None and not _valid_record(record):
        raise ValueError(
            "a run record holds outcome, seconds, status and where, not %r" % (record,)
        )
    kept = {
        k: v
        for k, v in (durations or {}).items()
        if isinstance(k, str) and k != key and _valid_record(v)
    }
    if record is not None:
        kept[key] = record
    return json.dumps(kept, indent=2, sort_keys=True) + "\n"


def unmeasured_record(previous, cfg, outcome, where):
    """The entry an attempt that measured no run leaves for its launch key:
    *outcome* `incomplete` (written before the command starts) or `no-capacity`
    (the farm never started it), with no seconds and no status. *previous* is
    kept instead when its measured duration is over
    `launcher.long_after_seconds`, because that run is still the last one
    measured: replacing it would make the launcher read the script as unknown,
    which routes the same way, but would hide it from long_scripts.py, which
    proposes only a measured duration. Raises ValueError for any other
    *outcome*."""
    if outcome not in ("incomplete", "no-capacity"):
        raise ValueError(
            "an attempt that measured no run is incomplete or no-capacity, not %r"
            % (outcome,)
        )
    seconds = recorded_seconds(previous)
    if seconds is not None and seconds > cfg.long_after_seconds:
        return previous
    return _record(outcome, None, None, where)


def unlisted_credentials(env_names, credential_names, allowed):
    """The sorted names of *env_names* that are credentials (in
    *credential_names*) and that *allowed*, the launch key's
    `launcher.credentials` names, does not list."""
    return sorted({n for n in env_names if n in credential_names and n not in allowed})


# --- the process ----------------------------------------------------------------


def _parse(argv):
    argv = list(argv)
    command = []
    if "--" in argv:
        cut = argv.index("--")
        argv, command = argv[:cut], argv[cut + 1 :]
    ap = argparse.ArgumentParser(
        prog="launch.py",
        usage="launch.py [--root DIR] [--dry-run] -- <command>...",
        description=(
            "Decide where a long command runs (here, here limited, or a job "
            "farm) from config/project.json `launcher`, and say why in one "
            "stderr line."
        ),
    )
    ap.add_argument(
        "--root",
        default=None,
        help="the project whose config/project.json and state files are read "
        "(default: the project this script ships in)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="print the decision line and run nothing",
    )
    return ap.parse_args(argv), command


def _refuse(message, next_step):
    return report(
        ExitCode.USAGE, "launch: refused before anything ran", message, next_step
    )


def _read(path):
    """(text, unreadable): None and False when the file is absent."""
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read(), False
    except FileNotFoundError:
        return None, False
    except (OSError, ValueError):
        return None, True


def _durations(path):
    """The durations file as {launch key: record}: {} when absent, None when it
    cannot be read or is not a JSON object, so every key reads as unknown."""
    text, unreadable = _read(path)
    if unreadable:
        return None
    if text is None:
        return {}
    try:
        data = json.loads(text)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _unsafe_state(root, cfg):
    """(what is wrong, what to do) for a state path that is linked, listed or
    unknowable, else None; main refuses with it."""
    state = [cfg.durations_file, cfg.own_hosts_file]
    linked = git_tree.through_symlink(root, state)
    if linked:
        return (
            "config/project.json launcher reaches %s through a symlink, so a read "
            "or a write there could land outside the project" % ", ".join(linked),
            "replace the symlink with a real file or directory inside the project",
        )
    try:
        listed = [p for p in state if not git_tree.is_ignored(root, p)]
    except git_tree.NoGitError:
        # With no repository nothing can commit the file, so nothing to refuse.
        listed = []
    except git_tree.GitFailedError as exc:
        return (
            "git could not say whether the launcher's state files are ignored, "
            "and a failure is not an answer (%s)" % exc,
            "repair the repository git reads here and run it again",
        )
    if listed:
        return (
            "git would list %s, so a host pattern or a run record could be "
            "committed" % ", ".join(listed),
            "keep config/project.json launcher.own_hosts_file and "
            "launcher.durations_file under paths .gitignore ignores",
        )
    return None


def _ncpu():
    """The cpus this process may run on, or None when the host does not say."""
    try:
        return len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        return os.cpu_count()


def _loadavg():
    """(load1, load5, load15), or None when this host does not report a load."""
    try:
        return os.getloadavg()
    except (AttributeError, OSError):
        return None


def _write_whole(path, text):
    """Replace *path* with *text* in one step: a reader sees the old file or
    the new one, never a part."""
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".durations-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(temporary, path)
    except BaseException:
        # A half-written temporary file is no record; it must not outlive the try.
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise


def _save(path, key, record):
    """Make *record* the entry for *key*, None to drop it, keeping every other
    entry as the file holds it now: re-read, so a concurrent launch of another
    key is kept unless it writes between this read and this write."""
    _write_whole(path, durations_text(_durations(path), key, record))


def _record(outcome, seconds, status, where):
    return {"outcome": outcome, "seconds": seconds, "status": status, "where": where}


def _seconds(start, end):
    # Whole seconds, to the nearest: the threshold is whole seconds, and a
    # fraction would make the record differ on every run.
    return int(round(max(0.0, end - start)))


def _attempt(argv, how, niceness, on_start, hooks):
    """Start *argv* once: lower this process's priority by *niceness* when it is
    not None, build the child's environment from the allowlist, refuse it when
    it holds an unlisted credential, call *on_start*, then spawn and wait.
    *how* is (credentials_for, extra, root, allowed); *hooks* is (runner,
    clock, nicer). (returncode, seconds, problem): problem is None after a run,
    and otherwise (kind, detail) with kind one of child-env, credential, nice,
    record, absent and interrupted; only interrupted ran anything."""
    credentials_for, extra, root, allowed = how
    runner, clock, nicer = hooks
    try:
        policy = child_env.load_policy(root)
        env = child_env.build_child_env(
            credentials_for=credentials_for, extra=extra, root=root
        )
    except child_env.ChildEnvError as exc:
        return None, None, ("child-env", str(exc))
    named = {n for names in policy.credentials.values() for n in names}
    unlisted = unlisted_credentials(
        env.keys(), named | set(policy.credentialed), allowed
    )
    if unlisted:
        return None, None, ("credential", unlisted)
    if niceness is not None:
        try:
            nicer(niceness)
        except OSError as exc:
            return None, None, ("nice", exc.__class__.__name__)
    try:
        on_start()
    except (OSError, ValueError) as exc:
        return None, None, ("record", exc.__class__.__name__)
    start = clock()
    try:
        if runner is None:
            done = subprocess.run(argv, cwd=os.getcwd(), env=env)
        else:
            done = runner(argv, cwd=os.getcwd(), env=env.copy())
    except KeyboardInterrupt:
        return None, _seconds(start, clock()), ("interrupted", None)
    except (FileNotFoundError, PermissionError) as exc:
        return None, None, ("absent", exc.__class__.__name__)
    return done.returncode, _seconds(start, clock()), None


def _stopped(problem, key, submitting, adapter):
    """The report for an attempt that did not run to an exit status."""
    kind, detail = problem
    on = json.dumps(key)
    if kind == "child-env":
        return _refuse(
            "the allowlist cannot build the command's environment (%s)" % detail,
            "correct config/project.json child_env or models, or the variable it names",
        )
    if kind == "credential":
        return _refuse(
            "the command's environment would hold the credential %s, which "
            "config/project.json launcher.credentials does not name for %s"
            % (", ".join(detail), on),
            "name it under launcher.credentials for that launch key, or stop "
            "child_env copying it",
        )
    if kind == "nice":
        return _refuse(
            "os.nice refused to lower this process's priority (%s), so it cannot "
            "run limited" % detail,
            "run it again, or on a host where it may lower its priority",
        )
    if kind == "record":
        return _refuse(
            "the run record under config/project.json launcher.durations_file "
            "could not be written (%s)" % detail,
            "make the launcher's state directory writable, then run it again",
        )
    if kind == "absent" and submitting:
        return report(
            ExitCode.BACKEND_ABSENT,
            "launch: the farm's submit program could not be started (%s), so "
            "nothing ran" % detail,
            on,
            "install it, or correct config/project.json launcher.farm.adapters.%s"
            ".submit" % adapter,
        )
    if kind == "absent":
        return _refuse(
            "the command could not be started (%s)" % detail,
            "check the program name after `--`",
        )
    return report(
        ExitCode.INTERRUPTED,
        "launch: interrupted while the command ran, recorded as interrupted",
        on,
        "run it again",
    )


def main(argv=None, runner=None, clock=None, nicer=None, loadavg=None):
    """Decide where the command after `--` runs, print the one line, run it
    there and record the run; the exit status. *runner*, *clock*, *nicer* and
    *loadavg* stand in for subprocess.run, time.monotonic, os.nice and
    os.getloadavg, so a test can drive a run without a farm or a busy host."""
    usage = "call it as `launch.py [--root DIR] [--dry-run] -- <command>...`"
    try:
        args, command = _parse(sys.argv[1:] if argv is None else argv)
    except SystemExit as exc:
        # argparse ends the process itself: status 0 after --help, and a usage
        # error it has already written to stderr otherwise.
        if not exc.code:
            return ExitCode.SUCCESS
        return _refuse("argparse refused the arguments above", usage)
    if not command:
        return _refuse("no command after `--`", usage)
    root = os.path.abspath(args.root or _DEFAULT_ROOT)
    try:
        with open(os.path.join(root, _MANIFEST), encoding="utf-8") as fh:
            cfg = load_launcher_config(json.load(fh))
    except LauncherConfigError as exc:
        return _refuse(str(exc), "correct config/project.json `launcher`")
    except (OSError, ValueError) as exc:
        return _refuse(
            "%s is unreadable or not JSON (%s)" % (_MANIFEST, exc.__class__.__name__),
            "restore config/project.json",
        )
    unsafe = _unsafe_state(root, cfg)
    if unsafe is not None:
        return _refuse(unsafe[0], unsafe[1])
    adapter = cfg.adapters[cfg.farm_adapter]
    # A read only: the names come from config, so a job started by the farm
    # never submits a job of its own.
    inside = any(os.environ.get(name) for name in adapter.inside_env)
    text, unreadable = _read(os.path.join(root, cfg.own_hosts_file))
    # gethostname, never getfqdn: the fully qualified name asks DNS.
    host = host_kind(socket.gethostname(), text, inside, unreadable=unreadable)
    key = script_key(command, root)
    path = os.path.join(root, cfg.durations_file)
    durations = _durations(path)
    length = script_length(key, cfg, durations)
    decision = decide(host, length, cfg, key)
    sys.stderr.write(explain(decision, host, length) + "\n")
    # Python before 3.9 block-buffers a piped stderr, so without the flush the
    # reason would reach the reader after the output of the command it names.
    sys.stderr.flush()
    if args.dry_run:
        return ExitCode.SUCCESS

    farm = make_farm(cfg)
    credential = cfg.credentials.get(key)
    allowed = credential.names if credential is not None else ()
    credentials_for = credential.model_adapter if credential is not None else None
    submitting = decision.where == "farm"
    extra = farm.submit_env_extra(size_for(key, cfg), cfg) if submitting else None
    previous = (durations or {}).get(key)
    previous = previous if _valid_record(previous) else None
    hooks = (runner, clock or time.monotonic, nicer or os.nice)

    def placeholder(where):
        return lambda: _save(
            path, key, unmeasured_record(previous, cfg, "incomplete", where)
        )

    where = run_where(decision.where, host[0])
    returncode, seconds, problem = _attempt(
        command_for(decision, farm, cfg, command),
        (credentials_for, extra, root, allowed),
        cfg.niceness if decision.where == "here-limited" else None,
        placeholder(where),
        hooks,
    )
    if problem is None and submitting:
        state = farm.classify(returncode)
        if state == "refused":
            _restore(path, key, previous)
            return report(
                ExitCode.USAGE,
                "launch: the farm refused the submission, so nothing ran",
                json.dumps(key),
                "read the farm's message above, and correct config/project.json "
                "launcher.farm.adapters.%s.submit or the request" % farm.name,
            )
        if state == "not-allocated":
            free = spare((loadavg or _loadavg)(), _ncpu(), cfg.max_load_per_cpu)
            if not free[0]:
                _keep(path, key, unmeasured_record(previous, cfg, "no-capacity", where))
                return report(
                    ExitCode.NO_CAPACITY,
                    "launch: the farm did not start the command within "
                    "launcher.farm.wait_seconds (%d s) and this host had no spare "
                    "compute (%s)" % (cfg.wait_seconds, free[1]),
                    json.dumps(key),
                    "run it again later, or raise config/project.json "
                    "launcher.farm.wait_seconds",
                )
            limited = decision._replace(where="here-limited")
            sys.stderr.write(
                explain(
                    limited,
                    host,
                    length,
                    farm_state="did not allocate within %d s; host spare (%s)"
                    % (cfg.wait_seconds, free[1]),
                )
                + "\n"
            )
            sys.stderr.flush()
            where = run_where(limited.where, host[0])
            submitting = False
            returncode, seconds, problem = _attempt(
                list(command),
                (credentials_for, None, root, allowed),
                cfg.niceness,
                placeholder(where),
                hooks,
            )
    if problem is not None and problem[0] == "interrupted":
        _keep(
            path, key, _record("interrupted", seconds, int(ExitCode.INTERRUPTED), where)
        )
        return _stopped(problem, key, submitting, farm.name)
    if problem is not None:
        if problem[0] == "absent":
            _restore(path, key, previous)
        return _stopped(problem, key, submitting, farm.name)
    outcome, status = run_outcome(returncode)
    _keep(path, key, _record(outcome, seconds, status, where))
    return passthrough(returncode)


def _restore(path, key, previous):
    """Put back the entry a run that never started replaced."""
    _keep(path, key, previous)


def _keep(path, key, record):
    """_save, saying so on stderr instead of raising: the run's own status
    outranks its record, so a record that cannot be written never hides it."""
    try:
        _save(path, key, record)
    except (OSError, ValueError) as exc:
        sys.stderr.write(
            "launch: the run record could not be written (%s); the exit status "
            "below is the run's\n" % exc.__class__.__name__
        )


if __name__ == "__main__":
    finish(main())
