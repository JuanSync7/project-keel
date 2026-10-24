#!/usr/bin/env python3
"""
title: audit_dependencies — judge each frontend app's npm audit against the accepted risks config records
kind: script
layer: n/a
summary: `make fe-audit`'s doer. It audits each frontend app directory it is given (the Makefile passes FE_APPS) by running `npm audit --json` there, with `--include` naming dev, optional and peer so an .npmrc `omit=` cannot narrow it, under scripts/child_env.py `build_child_env` and config/project.json `dependency_audit.timeout_seconds`, or reads the saved report a `--report NAME=FILE` names instead, so a test never runs npm. A finding is one advisory a report's `via` entry names: its GHSA id (the last part of its `url`), its package and its severity. It judges each app against `dependency_audit.accepted.<app>`, rows of advisory id to package, reason and review_by day, on today's date (scripts/run_date.py `today`, read once at the entry point; a test hands in its own day). It fails (FAILURE) on four things, all listed before the one closing line: a finding at or above `dependency_audit.fail_at` that no row names with the same advisory and package; a row whose review_by day has passed; a row whose review_by is more than `dependency_audit.max_review_days` days after today, so an acceptance is renewed rather than parked; and a row whose advisory and package the app's report no longer holds, or whose app is not one it audited. A finding below fail_at that no row covers is listed and does not fail; a covered one is listed with its reason and day. It refuses a report it cannot trust rather than pass it: one that is not JSON, not `npm audit --json` version 2 (an unknown severity, a `via` url with no advisory id, a `via` item that is neither an advisory nor the name of another entry), whose `metadata.vulnerabilities` counts disagree with its entries, or whose `metadata.dependencies.total` is 0 or missing while the app's package.json declares a dependency, which is what an empty or root-only lockfile audits as. A package.json declares one when any of `dependencies`, `devDependencies` or `optionalDependencies` is non-empty, `peerDependencies` names a peer `peerDependenciesMeta` does not mark `optional: true`, or `workspaces` names a package glob, as a list or as an object's `packages` list, and then the next step also names a workspaces pattern that matches no directory. Such a report is USAGE from a saved file and BACKEND_ABSENT from a run, as is npm exiting 1 with no finding. An app directory with no package.json, one that is not a JSON object, no package-lock.json, a saved report that cannot be read and a `--report` name that is not an audited app are USAGE; npm that cannot be started, runs past the timeout, exits other than 0 or 1, or answers an `error` object is BACKEND_ABSENT, and the line carries npm's own diagnostic: the `error` object's `message` or `summary`, else the top-level `message` npm 11 writes when the registry cannot be reached or refuses the request, else npm's last stderr line other than its log pointer (`A complete log of this run can be found in:` and a path line split from it), never all of stderr. That text is first cut to `dependency_audit.max_shown_chars` characters, dropping the word the cut lands in and saying where it was cut, and every redaction pattern bounds its runs, so a registry's long or hostile body can neither flood the line nor stall the run. It is then redacted by structure, each rule rewriting only its own span so the cause stays: a URL keeps its scheme, host and port of at most five digits and loses its userinfo, everything before the authority's last `@`, and its path or query (`<path hidden>`); a host with no scheme, a dotted name whose last label is letters, an IPv4 address or any name with a port, at a word's start or after `//` or `@`, loses its path the same way, while a file path whose first part has no dot is kept; an `Authorization`/`Bearer`/`Basic` value, a scheme-less `user:pass@` up to its last `@` or `user@` before such a host, and any run of 20 or more token characters mixing letters and digits are `<hidden>`, except within a URL's scheme and port; so is the value after a key holding auth, token, password, passwd, secret, key, credential or cookie in any case: after `=` or `:` whatever it is, running to the line's end or the next `name=` after a space, through any quote, comma, `;` or `name:` inside it, a quoted one at least to its closing quote; and after whitespace every word of the clause up to its sentence's or line's end, `CLAUSE_WORDS` words judged one at a time and the rest of a longer sentence hidden whole, except a word scripts/audit_dependencies_data.py lists as a linking or cause word, matched without case or the marks around it, which is kept, a run of hidden words being one `<hidden>`; so an unknown cause word is hidden, and cause text after an assignment on its line is hidden with the value, while the advice, read from the raw text, is unchanged; a quoted value the cut leaves open is hidden from its quote to the end. A host, in a URL, before a scheme-less host's hidden path, or as the operand after `ENOTFOUND` or `getaddrinfo` up to a space, quote, comma, semicolon, `<` or `>`, is judged as one run, `+`, `=` and `%`-escapes included: kept when it is a DNS name of two or more labels with at most one trailing dot, or one label, each of letters, digits and hyphens, no UUID, and whose parts that are no word (a word is two or more letters, one outside a to f), joined by their hyphens and taken together, are not 20 or more mixed characters, unless that run is one word and then digits and hyphens only (`acme2024-111122223333`, `nexus3`), so a token behind a word prefix is hidden; a bracketed address is kept but for a zone id that, a leading `%25` dropped and no other escape decoded, is longer than 15 characters, no interface name's length, which is `%<hidden>` at any length with the host kept; any other host is kept when it mixes in no digit, as `localhost` does, and otherwise `<hidden>` whole. Whatever follows a URL's host and port is its path unless it opens with a comma or semicolon, which end the URL, and the path runs up to a space, quote, `<` or `>`. The next step follows the cause: the registry URL for npm's `ERR_INVALID_URL` or `Invalid URL`, registry credentials for a 401, 403 or authenticate failure, reachability for ENOTFOUND, ECONNREFUSED or ETIMEDOUT. A refused `dependency_audit` key, run date or child environment is CONFIG. Given no app and no row it says so and exits 0. It writes nothing in the tree; npm writes its own per-user log and cache.
effect: read-only
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys

_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import audit_dependencies_data  # noqa: E402
import child_env  # noqa: E402
import config_loader  # noqa: E402
import run_date  # noqa: E402
from exit_codes import ExitCode, finish, report  # noqa: E402

ROOT = os.path.dirname(_SCRIPTS)
_BLOCK = ("dependency_audit",)
_FIELDS = (
    "accepted",
    "fail_at",
    "max_review_days",
    "max_shown_chars",
    "timeout_seconds",
)
_WHERE = "config/project.json dependency_audit"
_KEY_PREFIX = "dependency_audit"
# The one argv the audit runs; a test points it at a program it controls. Each
# --include names a dependency type `npm audit --omit` accepts, so a user or
# project .npmrc `omit=` cannot narrow the audit: npm lets include win.
AUDIT_ARGV = (
    "npm",
    "audit",
    "--json",
    "--include=dev",
    "--include=optional",
    "--include=peer",
)
# The package.json fields whose packages npm puts in the tree it audits.
_DECLARING_FIELDS = (
    "dependencies",
    "devDependencies",
    "optionalDependencies",
    "peerDependencies",
)
# A shown diagnostic is redacted by structure, not by a list of known token
# shapes: a deny-list leaks every shape it does not name. Each rule rewrites
# only its own span, so the cause words around it (ENOTFOUND, E401, "Unable to
# authenticate") survive. In order:
# (a) a URL keeps its scheme, host and port; its userinfo, everything before
#     the authority's last `@`, is dropped and the rest, its path or query or
#     anything glued on, becomes _PATH_HIDDEN, since a registry token can sit
#     in either (`http://TOKEN@host/`, a `/TOKEN/` path);
# (c) an `Authorization`, `Bearer` or `Basic` scheme keeps its name and loses
#     its value, with any separator; a `realm="..."` parameter is kept;
# (b) a value after a key holding one of _SECRET_WORDS is hidden. After `=`
#     or `:` (an assignment) it is hidden whatever it is, to the line's end
#     or the next assignment (_NEXT_ASSIGNMENT). After whitespace (prose) the clause
#     that follows is read word by word, and a word is kept only when
#     scripts/audit_dependencies_data.py's closed vocabulary holds it: an
#     open list of "plain words" showed `hunter2` after a third linking word,
#     so an unknown word is hidden, cause words included. A quoted value is
#     hidden in both at least to its closing quote, or to the line's end;
# (a') a scheme-less `user:pass@host` loses everything before its last `@`,
#     and so does a `user@host` with no password before a host (_BARE_USER);
# (e) a scheme-less host (_BARE_HOST) loses its path as in (a);
# (d) any remaining run of 20 or more token characters that mixes letters and
#     digits becomes _HIDDEN. It is the fail-closed catch for a bare token of
#     a shape no rule above names (an npm, GitHub or legacy UUID token); it
#     also hides an integrity hash or a log file's timestamped name, which
#     costs the diagnostic that detail and keeps its cause word. It keeps a
#     URL's scheme and port, and judges a host whole where one sits: a URL's,
#     the one (e) left before its hidden path, and the one after `ENOTFOUND`
#     or `getaddrinfo` (_host_shown). A DNS name or a single label _is_label
#     keeps stays, since a host label such as an AWS CodeArtifact
#     domain-account pair has the token shape and is the cause a reader
#     needs; a bracketed address stays but for a zone id longer than any
#     interface name; any other host that mixes letters and digits is hidden
#     whole, so a token passed as the registry is still hidden, and one that
#     does not, as `localhost`, is kept.
# (c) runs before (b) because `Authorization` is itself a secret-word key, and
# (b) skips a value that is already hidden or is a scheme name. (e) runs after
# (b) so a secret word inside a path has its value hidden first.
# A registry or proxy chooses this text, so no pattern may backtrack more than
# linearly. A run is bounded unless a literal fixes where it starts (a URL's
# `://`, a separator, a quote) or it is the whole pattern, so no two open runs
# can trade characters. Unbounded, (b) took 7 s on "token" * 300 and 9 s on
# "a" * 16000.
# A URL's parts, shared by (a) and the spans (d) skips so the two cannot
# drift. A host is a bracketed IPv6 address, with its zone id if it has one,
# or a run of the characters a registry name may hold. The zone id's run has
# no bound, so a zone of any length is one host whose zone is hidden rather
# than no host at all: its `%` fixes where it starts, since the address part
# holds none, and `]` where it ends. A port is at most five
# digits, so a longer number is no port and falls into the path. Whatever
# follows the host and port is the path unless it opens with a comma or
# semicolon, which end the URL as a list does; the path then runs up to a
# space, quote, `<` or `>`, so a token glued on past a `)`, a comma or a
# stray character is hidden with it. A scheme is at most 16 characters, too
# short for (d), so keeping it can keep no token.
_SCHEME = r"\b[a-z][a-z0-9+.\-]{0,15}://"
_HOST = r"\[[0-9a-f:.]{2,45}(?:%[\w.\-~%]*)?\]|[\w.\-~%+=]{1,253}"
_PORT = r":\d{1,5}(?!\d)"
# A userinfo is everything before the last `@` of the authority, which ends
# at a `/`, `?` or `#`: the run is greedy and gives back to its last `@`, so a
# raw `@` in a password shows no part of it. `://` fixes where it starts.
_USERINFO = r"(?:[^\s/?#\"'<>]*@)?"
_URL = re.compile(
    r"(%s)%s(%s)?(%s)?([^\s\"'<>,;][^\s\"'<>]*)?" % (_SCHEME, _USERINFO, _HOST, _PORT),
    re.IGNORECASE,
)
_PATH_HIDDEN = "<path hidden>"
_HIDDEN = "<hidden>"
# An IPv6 zone id names an interface, and Linux caps an interface name at
# IFNAMSIZ, 16 bytes with its NUL; a longer zone id is no interface's.
_ZONE_LIMIT = 15
# A host with no scheme, as npm writes a registry in a `.npmrc` key or a
# fetch line, is one of: a dotted name whose last label is letters, an IPv4
# address, or any name with a port. It starts a word, or follows `//` or a
# userinfo's `@`, so the dotted part of a file path's later segment is no
# host. Its path, from the `/` on, is hidden as in (a); a host with nothing
# after its `/` is left. It runs after (b) and (a'), so a secret word in the
# path has had its value hidden, and that `<hidden>` is part of the path.
_BARE_START = r"(?<![\w.\-~%+=/:])"
_BARE_HOST = (
    r"(?:[A-Za-z0-9\-]{1,63}\.){1,126}[A-Za-z]{2,63}\.?"
    r"|\d{1,3}(?:\.\d{1,3}){3}"
    r"|[A-Za-z0-9\-]{1,63}(?=:\d)"
)
_BARE_URL = re.compile(
    r"%s((?://)?(?:%s)(?:%s)?)/(?:[^\s\"'<>,;]|%s)(?:[^\s\"'<>]|%s)*"
    % (_BARE_START, _BARE_HOST, _PORT, _HIDDEN, _HIDDEN)
)
# A quoted value may lack its closing quote, as when the cut lands inside
# it; it then runs to the end of the line, so no word of it is shown.
_VALUE = r"(?:\"[^\"]*\"?|'[^']*'?|[^\s\"',;]+)"
# The line has had its whitespace collapsed, so a run longer than 4 is not met.
_SEPARATOR_FORMS = r"\s{0,4}[=:]\s{0,4}|\s{1,4}"
_SEPARATOR = r"(%s)" % _SEPARATOR_FORMS
_SCHEME_VALUE = re.compile(
    r"\b(Authorization|Bearer|Basic)"
    + _SEPARATOR
    + r"(?:(Bearer|Basic|Token|Digest)(\s{1,4}))?(?!realm\b)"
    + _VALUE,
    re.IGNORECASE,
)
_SECRET_WORDS = (
    "auth",
    "token",
    "password",
    "passwd",
    "secret",
    "key",
    "credential",
    "cookie",
)
# Up to two linking words may stand between a secret word and an `=` or `:`
# (`password is: X`); the alternation is built from the data module.
_ASSIGNMENT = re.compile(
    r"(?:\s{1,4}(?:%s)\b){0,2}\s{0,4}[=:]\s{0,4}"
    % "|".join(map(re.escape, audit_dependencies_data.LINKING_WORDS)),
    re.IGNORECASE,
)
# The match starts at the secret word and leaves the key's text before it in
# place: matching that text too is what made the old pattern cubic.
_KEY = re.compile(r"(?:%s)[\w.\-]{0,64}[\"']?" % "|".join(_SECRET_WORDS), re.IGNORECASE)
# A value another rule already wrote, or a scheme name (c) keeps.
_DONE_VALUE = re.compile(r"<hidden>|(?:Bearer|Basic)\b", re.IGNORECASE)
# An assigned value runs to the line's end or to the next assignment: a
# `name=` after a space that no `;` or `,` comes before, since after one it
# is a cookie's next pair. A quote, a comma, a `;` or a `name:` can sit inside
# a passphrase, so none of them ends it.
_NEXT_ASSIGNMENT = re.compile(r"(?<![\s;,])\s{1,4}[A-Za-z_][\w.\-]{0,63}=")
# One word of a prose clause: a URL (a) rewrote is one word with its marker,
# and any other word runs to the next whitespace. The literal fixes where
# the marker's lazy run stops, so each word is read once.
_CLAUSE_WORD = re.compile(r"\s{1,4}(\S*?%s\S*|\S+)" % re.escape(_PATH_HIDDEN))
# The marks a word may carry that are no part of it for the vocabulary.
_WORD_MARKS = "\"'()[],;:.!?"
# The rest of a word a closing quote lands inside.
_CLAUSE_TAIL = re.compile(r"\S*")
_SPACE = re.compile(r"\s{0,4}")
_SENTENCE_END = re.compile(r"[.!?][\"')\]]*(?=\s|$)")
_VOCABULARY = frozenset(audit_dependencies_data.LINKING_WORDS) | frozenset(
    audit_dependencies_data.CAUSE_WORDS
)
# As in a URL, the password runs to the last `@` before a space or `/`.
_BARE_USERINFO = re.compile(r"(?<![\w/])[\w.\-]{1,64}:[^\s/]{1,256}@(?=[\w\-])")
# The places a host sits, which (d) judges by _host_shown rather than by the
# run alone: a URL's scheme, host and port as (a) left them, and the operand
# npm's resolver names after its error code, which is everything up to a
# space, quote, comma, semicolon, `<` or `>`. Each host is judged as one
# run, `+`, `=` and `%`-escapes included: split there, every piece of a token
# can be under 20 characters.
_URL_HOST = r"(?i:(%s)(%s)?(%s)?)" % (_SCHEME, _HOST, _PORT)
_BARE_URL_HOST = r"(?:(?<=//)|%s)([\w.\-]{1,253})(?=(?:%s)?/%s)" % (
    _BARE_START,
    _PORT,
    re.escape(_PATH_HIDDEN),
)
_RESOLVER_HOST = r"(\b(?:getaddrinfo(?: E[A-Z_]{1,31})?|ENOTFOUND) )([^\s\"'<>,;]+)"
_RUN = r"[A-Za-z0-9_\-+/=]{20,}"
# One pass: at each place a host is tried first, then a bare run.
_TOKEN_RUN = re.compile(
    r"%s|%s|%s|%s" % (_URL_HOST, _RESOLVER_HOST, _BARE_URL_HOST, _RUN)
)
_BARE_RUN = re.compile(_RUN)
_LETTER_AND_DIGIT = re.compile(r"(?=.*[A-Za-z])(?=.*[0-9])")
# A DNS label, and the shape of npm's legacy token, a UUID: its hyphens split
# it into parts too short for (d), so it is named here instead.
_LABEL = re.compile(r"[A-Za-z0-9\-]{1,63}")
_UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", re.IGNORECASE)
# A word part of a label: two or more letters, one outside a to f, so a
# fragment of a hex token is no word.
_WORD = re.compile(r"(?=[A-Za-z]*[G-Zg-z])[A-Za-z]{2,}")
# A run that is one word and then a number, digits and hyphens only, is a
# name's shape (`acme2024-111122223333`, `nexus3`): it turns from letters to
# digits once, where a random token's characters turn many times. Its input
# is one label, at most 63 characters.
_WORD_NUMBER = re.compile(r"(?=[A-Za-z]*[G-Zg-z])[A-Za-z]{2,63}[0-9\-]{1,63}")
# The advice a diagnostic's cause earns: a registry setting npm cannot parse
# as a URL, which stops it before any request; then a refused credential,
# then a registry that cannot be reached; anything else keeps the caller's
# advice.
_CONFIG_CAUSE = re.compile(r"\bERR_INVALID_URL\b|\bInvalid URL\b")
_CREDENTIAL_CAUSE = re.compile(r"\bE40[13]\b|\b40[13]\b|authenticat", re.IGNORECASE)
_REACH_CAUSE = re.compile(r"\b(?:ENOTFOUND|ECONNREFUSED|ETIMEDOUT)\b")
_CONFIG_ADVICE = (
    "check the registry URL in .npmrc or npm config is a full http:// or "
    "https:// URL (values not shown)"
)
_CREDENTIAL_ADVICE = "check the registry credentials in .npmrc (values not shown)"
_REACH_ADVICE = "check the registry is reachable from this host"
_CUT = "<cut to %d characters>"
# npm's closing pointer at its debug log, which names the log's path and not
# the cause; when the path is split onto the next line, that line goes too.
_LOG_POINTER = "A complete log of this run can be found in:"
_REPORT_VERSION = 2
# npm audit's own statuses: 0 found nothing, 1 found something; any other is
# npm failing, not an answer.
_ANSWERED = (0, 1)
_GUIDE = "docs/guides/deterministic-checks.md, section 16"
# A scheme-less userinfo with no password (`TOKEN@host/path`) is hidden as
# a URL's is: a word up to its last `@` before a host of _BARE_HOST's shape.
# The host must follow, so a package's `name@1.2.3` or `name@latest` is kept.
_BARE_USER = re.compile(
    r"(?<![^\s\"'(=,;])[^\s/\"'<>]{1,256}@(?=(?:%s)(?::\d|[/\s,;]|$))" % _BARE_HOST
)


class _Refused(Exception):
    """Nothing was judged; carries the report's three parts. Each subclass is
    one exit code, so the entry point names the member itself."""

    def __init__(self, what, on, next_step):
        super().__init__(what)
        self.what, self.on, self.next_step = what, on, next_step


class _Unusable(_Refused):
    """An argument, an app directory or a report cannot be used: USAGE."""


class _Unanswered(_Refused):
    """npm gave no answer to judge: BACKEND_ABSENT."""


class _Misconfigured(_Refused):
    """A setting, the run date or the child environment is refused: CONFIG."""


def _parse(argv):
    parser = argparse.ArgumentParser(
        prog="scripts/audit_dependencies.py",
        description="Judge each frontend app's npm audit against config/"
        "project.json dependency_audit.accepted: fail an uncovered finding at "
        "or above dependency_audit.fail_at, a row past its review_by day and a "
        "row whose advisory the audit no longer reports.",
    )
    parser.add_argument(
        "apps",
        nargs="*",
        metavar="APP_DIR",
        help="a frontend app directory, relative to the checkout; its name is "
        "the key under dependency_audit.accepted",
    )
    parser.add_argument(
        "--report",
        action="append",
        default=[],
        metavar="NAME=FILE",
        help="judge app NAME from the saved `npm audit --json` output in FILE "
        "instead of running npm; repeatable",
    )
    return parser.parse_args(argv)


def _settings(root):
    keys = config_loader.rows(*[_BLOCK + (field,) for field in _FIELDS])
    values = config_loader.resolve(
        config_loader.read(root), keys, config_loader.CONFIG_FILE
    )
    return {field: values[_BLOCK + (field,)] for field in _FIELDS}


def _apps(root, dirs):
    """{name: absolute dir} for each app directory given, in name order."""
    apps = {}
    for given in dirs:
        path = os.path.normpath(os.path.join(root, given))
        name = os.path.basename(path)
        if name in apps:
            raise _Unusable(
                "two app directories share the name %s" % name,
                given,
                "name each app directory once; its name is its key under %s.accepted"
                % _WHERE,
            )
        if not os.path.isfile(os.path.join(path, "package.json")):
            raise _Unusable(
                "the app directory has no package.json",
                given,
                "pass a frontend app directory, as the Makefile's FE_APPS does",
            )
        apps[name] = path
    return dict(sorted(apps.items()))


def _saved(pairs, apps):
    """{name: path} of each `--report NAME=FILE`."""
    saved = {}
    for pair in pairs:
        name, sep, path = pair.partition("=")
        if not sep or not name or not path or name not in apps:
            raise _Unusable(
                "--report takes NAME=FILE for an app directory it is given",
                pair,
                "name one of: %s" % (", ".join(apps) or "no app was given"),
            )
        saved[name] = path
    return saved


def npm_audit(app_dir, root, timeout):
    """(status, stdout, stderr) of AUDIT_ARGV run in *app_dir* under the allowlisted
    environment, or _Unanswered when it cannot be started or runs
    past *timeout* seconds. The audit reads the lockfile and the registry, so
    the app needs no node_modules."""
    try:
        env = child_env.build_child_env(root=root)
    except child_env.ChildEnvError as exc:
        raise _Misconfigured(
            "the child environment is refused",
            str(exc),
            "fix config/project.json child_env, then rerun",
        ) from exc
    try:
        done = subprocess.run(
            list(AUDIT_ARGV),
            cwd=app_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except OSError as exc:
        raise _Unanswered(
            "%s could not be started (%s)" % (AUDIT_ARGV[0], exc.strerror or exc),
            app_dir,
            "install Node.js so npm is on PATH, then rerun",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise _Unanswered(
            "%s ran past %d seconds" % (" ".join(AUDIT_ARGV), timeout),
            app_dir,
            "check the registry is reachable, or raise %s.timeout_seconds" % _WHERE,
        ) from exc
    return done.returncode, done.stdout, done.stderr


def _text(data):
    return data.decode("utf-8", "replace") if isinstance(data, bytes) else data


def _url_shown(match):
    scheme, host, port, path = match.groups()
    return "%s%s%s%s" % (
        scheme,
        host or "",
        port or "",
        "/" + _PATH_HIDDEN if path else "",
    )


def _scheme_shown(match):
    return "%s%s%s%s" % (
        match.group(1),
        match.group(2),
        (match.group(3) or "") + (match.group(4) or ""),
        _HIDDEN,
    )


def _key_values_shown(line):
    """*line* with the value after each secret word hidden: after `=` or `:`
    whatever it is (see _assigned_end), and in prose every word of the clause
    that follows the vocabulary does not hold (see _clause_shown)."""
    shown, at = [], 0
    while match := _KEY.search(line, at):
        end = match.end()
        shown.append(line[at:end])
        assigned = _ASSIGNMENT.match(line, end)
        start = (assigned or _SPACE.match(line, end)).end()
        if _DONE_VALUE.match(line, start):
            at = end
            continue
        if assigned:
            value_end = _assigned_end(line, start)
            if value_end > start:
                shown.append(line[end:start] + _HIDDEN)
                at = value_end
                continue
            at = end
            continue
        clause, at = _clause_shown(line, end)
        shown.append(clause)
    return "".join(shown) + line[at:]


def _assigned_end(line, start):
    """Where the value an assignment states, from *start*, ends; *start* when
    it states none. A quoted value runs at least to its closing quote."""
    if start >= len(line):
        return start
    scan = start
    if line[start] in "\"'":
        close = line.find(line[start], start + 1)
        scan = len(line) if close < 0 else close + 1
    following = _NEXT_ASSIGNMENT.search(line, scan)
    return following.start() if following else len(line)


def _clause_shown(line, at):
    """(the prose clause from *at* with each word outside the vocabulary
    hidden, where the clause ended). A run of hidden words is one marker, so
    a reader learns no word count. A quoted word is a value whatever it says,
    and it runs to its closing quote. The clause ends after a word that ends a
    sentence, before another secret word, at the line's end, or after
    CLAUSE_WORDS words, when the rest of its sentence is hidden whole."""
    pieces, words = [], 0
    while word := _CLAUSE_WORD.match(line, at):
        text = word.group(1)
        bare = text.strip(_WORD_MARKS).lower()
        if bare in _SECRET_WORDS:
            break
        if words == audit_dependencies_data.CLAUSE_WORDS:
            stop = _SENTENCE_END.search(line, at)
            at = stop.end() if stop else len(line)
            pieces.append((line[word.start() : word.start(1)], None))
            break
        words += 1
        end = word.end()
        if text[0] in "\"'":
            close = line.find(text[0], word.start(1) + 1)
            end = len(line) if close < 0 else _CLAUSE_TAIL.match(line, close + 1).end()
            pieces.append((line[word.start() : word.start(1)], None))
        elif bare in _VOCABULARY or text == _HIDDEN or _PATH_HIDDEN in text:
            pieces.append((line[at:end], text))
        else:
            pieces.append((line[word.start() : word.start(1)], None))
        at = end
        if _SENTENCE_END.search(line[word.start(1) : end]):
            break
    shown = []
    for index, (text, kept) in enumerate(pieces):
        if kept is not None:
            shown.append(text)
        elif index == 0 or pieces[index - 1][1] is not None:
            shown.append(text + _HIDDEN)
    return "".join(shown), at


def _is_token(run):
    """Whether *run* is one (d) hides: 20 or more token characters mixing
    letters and digits."""
    return bool(_BARE_RUN.fullmatch(run) and _LETTER_AND_DIGIT.match(run))


def _run_shown(match):
    run = match.group(0)
    return _HIDDEN if _is_token(run) else run


def _is_name(host):
    """Whether *host* is a DNS name rule (d) keeps whole: two or more labels,
    each one _is_label keeps. One trailing dot, which makes a name fully
    qualified, is allowed."""
    labels = host.removesuffix(".").split(".")
    return len(labels) >= 2 and all(_is_label(label) for label in labels)


def _is_label(label):
    """Whether *label* is a DNS label rule (d) keeps: letters, digits and
    hyphens, no UUID, and its parts that are no word, joined by hyphens, no
    run (d) would hide. A word part excuses only itself, so
    `my-domain-111122223333` is kept, and a token behind a word prefix, cut
    short by hyphens or by a short word inside it, is not."""
    if not _LABEL.fullmatch(label) or _UUID.fullmatch(label):
        return False
    rest = [part for part in label.split("-") if not _WORD.fullmatch(part)]
    return not _is_hidden_run("-".join(rest))


def _is_hidden_run(run):
    """Whether *run*, the parts of a label that are no word, is a token (d)
    hides: one that is a word and then a number is not."""
    return _is_token(run) and not _WORD_NUMBER.fullmatch(run)


def _address_shown(host):
    """The bracketed IPv6 *host* whole, or with its zone id hidden when that
    id, the `%25` that opens it decoded, is longer than any interface name."""
    at = host.find("%")
    if at < 0:
        return host
    zone = host[at + 1 : -1].removeprefix("25")
    return host[:at] + "%" + _HIDDEN + "]" if len(zone) > _ZONE_LIMIT else host


def _host_shown(host):
    """*host* whole when it is a DNS name or one label _is_label keeps
    (`nexus3`), and a bracketed address whole but for a zone id that can be
    no interface's (see _address_shown). Any other host that mixes letters
    and digits is hidden whole, whatever its length, since a token split at a
    symbol no label holds has pieces too short for (d); one that does not,
    such as `localhost`, is no token and stays."""
    if host.startswith("["):
        return _address_shown(host)
    if _is_name(host) or _is_label(host):
        return host
    return _HIDDEN if _LETTER_AND_DIGIT.match(host) else host


def _token_shown(match):
    scheme, host, port, said, operand, bare = match.groups()
    if scheme is not None:
        return scheme + _host_shown(host or "") + (port or "")
    if said is not None:
        return said + _host_shown(operand)
    if bare is not None:
        return _host_shown(bare)
    return _run_shown(match)


def _shown(text, limit):
    """*text* on one line, cut to *limit* characters and then redacted. A cut
    drops the word it lands in, since a token's fragment can be too short for
    rule (d), and the line says where it was cut."""
    line = " ".join(text.split())
    if len(line) <= limit:
        return _redacted(line)
    head = line[:limit]
    if line[limit] != " ":
        head = head.rpartition(" ")[0]
    return (_redacted(head) + " " + _CUT % limit).lstrip()


def _redacted(line):
    """*line* with every span that could carry a credential rewritten by the
    rules above and the rest of it kept."""
    line = _URL.sub(_url_shown, line)
    line = _SCHEME_VALUE.sub(_scheme_shown, line)
    line = _key_values_shown(line)
    line = _BARE_USERINFO.sub(_HIDDEN + "@", line)
    line = _BARE_USER.sub(_HIDDEN + "@", line)
    line = _BARE_URL.sub(r"\1/" + _PATH_HIDDEN, line)
    return _TOKEN_RUN.sub(_token_shown, line)


def _advice(said, fallback):
    """The next step *said*, npm's raw diagnostic, points at, else *fallback*."""
    if _CONFIG_CAUSE.search(said):
        return _CONFIG_ADVICE
    if _CREDENTIAL_CAUSE.search(said):
        return _CREDENTIAL_ADVICE
    if _REACH_CAUSE.search(said):
        return _REACH_ADVICE
    return fallback


def _last_line(stderr):
    """npm's last stderr line that is not its log pointer, raw; never the
    whole stream, which carries every warning. The caller shows it through
    _shown."""
    lines, skip_next = [], False
    for line in _text(stderr or "").splitlines():
        if skip_next:
            skip_next = False
            continue
        _, sep, tail = line.partition(_LOG_POINTER)
        if sep:
            skip_next = not tail.strip()
            continue
        if line.strip():
            lines.append(line)
    return lines[-1] if lines else "nothing on stderr"


def _error_text(doc, stderr):
    """What npm says went wrong, raw: the `error` object's `message` or
    `summary`, else the top-level `message` npm 11 writes, with `error` left
    blank, when the registry cannot be reached or refuses the request (a 401
    adds `statusCode`, `uri` and `headers` beside it), else npm's last stderr
    line. The caller shows it through _shown."""
    error = doc.get("error")
    for holder, key in ((error, "message"), (error, "summary"), (doc, "message")):
        said = holder.get(key) if isinstance(holder, dict) else None
        if isinstance(said, str) and said.strip():
            return said
    return _last_line(stderr)


def _declares_dependencies(app_dir):
    """Whether the app's package.json names any package npm would audit, and
    whether it names a workspaces pattern, as a pair."""
    path = os.path.join(app_dir, "package.json")
    try:
        with open(path, encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, ValueError) as exc:
        raise _Unusable(
            "the app's package.json cannot be read as JSON (%s)" % exc,
            path,
            "fix the app's package.json, then rerun",
        ) from exc
    if not isinstance(manifest, dict):
        raise _Unusable(
            "the app's package.json is not a JSON object",
            path,
            "fix the app's package.json, then rerun",
        )
    # A workspaces root declares its packages as a list of globs, or as an
    # object holding that list under `packages`; each is a dependency npm audits.
    workspaces = manifest.get("workspaces")
    if isinstance(workspaces, dict):
        workspaces = workspaces.get("packages")
    patterned = bool(workspaces)
    fields = [field for field in _DECLARING_FIELDS if field != "peerDependencies"]
    if any(manifest.get(field) for field in fields) or patterned:
        return True, patterned
    return bool(_required_peers(manifest)), patterned


def _required_peers(manifest):
    """The peer dependencies npm puts in the tree: a peer that
    `peerDependenciesMeta.<name>.optional` marks true is installed only when
    something else asks for it, so it alone declares nothing."""
    peers = manifest.get("peerDependencies")
    if not isinstance(peers, dict):
        return peers
    meta = manifest.get("peerDependenciesMeta")
    meta = meta if isinstance(meta, dict) else {}

    def optional(name):
        said = meta.get(name)
        return isinstance(said, dict) and said.get("optional") is True

    return [name for name in peers if not optional(name)]


def _report_of(name, app_dir, saved, root, settings, run_audit):
    """The findings of one app, from its saved file or a run. A report that
    cannot be judged is USAGE from a saved file, which the caller chose, and
    BACKEND_ABSENT from a run, where npm gave no usable answer. *settings*
    gives npm's timeout and how much of its diagnostic a line shows."""
    timeout, limit = settings["timeout_seconds"], settings["max_shown_chars"]
    declares, patterned = _declares_dependencies(app_dir)
    status, err = None, b""
    if name in saved:
        path = saved[name]
        try:
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
        except (OSError, UnicodeDecodeError) as exc:
            raise _Unusable(
                "the saved report cannot be read (%s)" % exc,
                path,
                "save it with `npm audit --json > FILE` in the app directory",
            ) from exc
        where = "app %s, the saved report %s" % (name, path)
        refuse, redo = _Unusable, "save it again with `npm audit --json > FILE`"
    else:
        if not os.path.isfile(os.path.join(app_dir, "package-lock.json")):
            raise _Unusable(
                "the app has no package-lock.json, so there is nothing to audit",
                app_dir,
                "run `make fe-install` to write it, then rerun",
            )
        status, out, err = run_audit(app_dir, root, timeout)
        where = "app %s, `%s` in %s" % (name, " ".join(AUDIT_ARGV), app_dir)
        refuse, redo = _Unanswered, "run it by hand in the app directory to see why"
        text = _text(out)
        if status not in _ANSWERED:
            raise _Unanswered(
                "npm audit exited %d, which is not an answer; npm's last stderr "
                "line: %s" % (status, _shown(_last_line(err), limit)),
                where,
                _advice(
                    _last_line(err), "run it by hand in the app directory to see why"
                )
                + ", then rerun",
            )
    try:
        doc = json.loads(text)
    except ValueError as exc:
        why = "the audit report is not JSON (%s)" % exc
        if status is not None:
            why += "; npm's last stderr line: %s" % _shown(_last_line(err), limit)
        raise refuse(why, where, redo + ", then rerun") from exc
    if isinstance(doc, dict) and "error" in doc:
        said = _error_text(doc, err)
        error = doc.get("error")
        code = error.get("code") if isinstance(error, dict) else None
        cause = " ".join(str(part) for part in (said, code, doc.get("statusCode")))
        raise _Unanswered(
            "npm audit answered an error, not a report: %s" % _shown(said, limit),
            where,
            _advice(cause, _REACH_ADVICE) + ", then rerun",
        )
    found = _findings(doc, where, refuse)
    _check_dependencies(doc, declares, patterned, where, refuse)
    if status == 1 and not found:
        raise _Unanswered(
            "npm audit exited 1, which says it found something, and its report "
            "holds no finding",
            where,
            "run it by hand in the app directory to see why, then rerun",
        )
    return found


def _not_a_report(where, why, refuse):
    return refuse(
        "the audit report is not npm audit --json version %d (%s)"
        % (_REPORT_VERSION, why),
        where,
        "give it the output of `npm audit --json` from npm 7 or later",
    )


def _check_dependencies(doc, declares, patterned, where, refuse):
    """Refuse a report that audited nothing while package.json declares a
    dependency: an empty or root-only lockfile audits as clean, and so does a
    workspaces root whose pattern (*patterned*) matches no directory."""
    # _check_counts has already refused a report whose metadata is not an object.
    counted = doc["metadata"].get("dependencies")
    total = counted.get("total") if isinstance(counted, dict) else None
    if declares and (type(total) is not int or total < 1):
        raise refuse(
            "the report audited no dependency (metadata.dependencies.total is %r) "
            "and the app's package.json declares some" % (total,),
            where,
            "run `make fe-install` so package-lock.json holds the tree%s, then "
            "audit again"
            % (
                ", or fix a workspaces pattern that matches no directory"
                if patterned
                else ""
            ),
        )


def _check_counts(doc, entries, where, refuse):
    """Refuse a report whose metadata.vulnerabilities disagrees with the
    entries it holds: npm counts one per entry, by the entry's severity."""
    metadata = doc.get("metadata")
    counts = metadata.get("vulnerabilities") if isinstance(metadata, dict) else None
    if not isinstance(counts, dict):
        raise _not_a_report(where, "no metadata.vulnerabilities", refuse)
    tally = dict.fromkeys(config_loader.AUDIT_SEVERITIES, 0)
    for severity in entries:
        tally[severity] += 1
    tally["total"] = len(entries)
    for key, want in tally.items():
        # type() and not isinstance: a JSON true is not a count of 1.
        if type(counts.get(key)) is not int or counts[key] != want:
            raise _not_a_report(
                where,
                "metadata.vulnerabilities.%s is %r and the report holds %d such "
                "entries" % (key, counts.get(key), want),
                refuse,
            )


def _findings(doc, where, refuse=_Unusable):
    """The sorted set of (advisory, package, severity, title) a report holds."""
    if not isinstance(doc, dict) or doc.get("auditReportVersion") != _REPORT_VERSION:
        raise _not_a_report(where, "auditReportVersion", refuse)
    vulnerabilities = doc.get("vulnerabilities")
    if not isinstance(vulnerabilities, dict):
        raise _not_a_report(where, "vulnerabilities", refuse)
    found = set()
    entries = []
    for entry in vulnerabilities.values():
        via = entry.get("via") if isinstance(entry, dict) else None
        if not isinstance(via, list):
            raise _not_a_report(where, "an entry with no via list", refuse)
        # A string item names another vulnerable package, which has its own
        # entry carrying the advisory; a dict is an advisory.
        for item in via:
            if isinstance(item, str):
                if item not in vulnerabilities:
                    raise _not_a_report(
                        where, "a via item naming no entry: %r" % (item,), refuse
                    )
                continue
            if not isinstance(item, dict):
                raise _not_a_report(
                    where,
                    "a via item that is neither an advisory nor a package: %r"
                    % (item,),
                    refuse,
                )
            url = item.get("url")
            advisory = (
                url.rstrip("/").rsplit("/", 1)[-1] if isinstance(url, str) else None
            )
            if not config_loader.is_advisory_id(advisory):
                raise _not_a_report(
                    where, "a via url with no GHSA id: %r" % (url,), refuse
                )
            severity = item.get("severity")
            if severity not in config_loader.AUDIT_SEVERITIES:
                raise _not_a_report(where, "severity %r" % (severity,), refuse)
            package = item.get("name")
            if not isinstance(package, str) or not package:
                raise _not_a_report(where, "a via entry with no package name", refuse)
            title = item.get("title")
            found.add(
                (advisory, package, severity, title if isinstance(title, str) else "")
            )
        severity = entry.get("severity")
        if severity not in config_loader.AUDIT_SEVERITIES:
            raise _not_a_report(where, "entry severity %r" % (severity,), refuse)
        entries.append(severity)
    _check_counts(doc, entries, where, refuse)
    return sorted(found)


def _judge(apps, reports, accepted, fail_at, max_review_days, today):
    """(failure lines, listed lines) of every app's findings and every row."""
    floor = config_loader.AUDIT_SEVERITIES.index(fail_at)
    failures, listed = [], []
    for name in apps:
        rows = accepted.get(name, {})
        held = set()
        for advisory, package, severity, title in reports[name]:
            held.add((advisory, package))
            row = rows.get(advisory)
            if row is not None and row["package"] == package:
                listed.append(
                    "%s: accepted %s %s (%s) until %s: %s"
                    % (
                        name,
                        advisory,
                        package,
                        severity,
                        row["review_by"],
                        row["reason"],
                    )
                )
            elif config_loader.AUDIT_SEVERITIES.index(severity) >= floor:
                failures.append(
                    "%s: %s %s (%s) is at or above fail_at %s and no accepted row "
                    "covers it: %s"
                    % (name, advisory, package, severity, fail_at, title)
                )
            else:
                listed.append(
                    "%s: %s %s (%s) is below fail_at %s, so it is listed, not "
                    "failed: %s" % (name, advisory, package, severity, fail_at, title)
                )
        for advisory, row in sorted(rows.items()):
            review_by = datetime.date.fromisoformat(row["review_by"])
            ahead = (review_by - today).days
            if ahead > max_review_days:
                failures.append(
                    "%s: the accepted row for %s %s is parked: review_by %s is %d "
                    "days after %s, more than %s.max_review_days (%d)"
                    % (
                        name,
                        advisory,
                        row["package"],
                        row["review_by"],
                        ahead,
                        today.isoformat(),
                        _KEY_PREFIX,
                        max_review_days,
                    )
                )
            if review_by < today:
                failures.append(
                    "%s: the accepted row for %s %s expired: review_by %s is before "
                    "%s"
                    % (
                        name,
                        advisory,
                        row["package"],
                        row["review_by"],
                        today.isoformat(),
                    )
                )
            if (advisory, row["package"]) not in held:
                failures.append(
                    "%s: the accepted row for %s %s is stale: the audit no longer "
                    "reports it" % (name, advisory, row["package"])
                )
    for name in sorted(set(accepted) - set(apps)):
        for advisory, row in sorted(accepted[name].items()):
            failures.append(
                "%s: the accepted row for %s %s is stale: %s is not an app this "
                "run audits" % (name, advisory, row["package"], name)
            )
    return failures, listed


def _run(root, args, settings, today, run_audit):
    apps = _apps(root, args.apps)
    saved = _saved(args.report, apps)
    accepted = settings["accepted"]
    if not apps and not accepted:
        sys.stdout.write(
            "no frontend app to audit and no accepted row, so nothing was judged\n"
        )
        return ExitCode.SUCCESS
    reports = {
        name: _report_of(name, path, saved, root, settings, run_audit)
        for name, path in apps.items()
    }
    failures, listed = _judge(
        apps,
        reports,
        accepted,
        settings["fail_at"],
        settings["max_review_days"],
        today,
    )
    for line in listed:
        sys.stdout.write(line + "\n")
    for line in failures:
        sys.stderr.write(line + "\n")
    if failures:
        return report(
            ExitCode.FAILURE,
            "%d dependency audit failure(s), listed above" % len(failures),
            ", ".join(sorted(set(apps) | set(accepted))),
            "fix the package; or accept the finding, or renew or remove the "
            "row, in %s.accepted with a reason and a review_by day (%s)"
            % (_WHERE, _GUIDE),
        )
    sys.stdout.write(
        "dependency audit: %d app(s) judged on %s, no failure\n"
        % (len(apps), today.isoformat())
    )
    return ExitCode.SUCCESS


def _today(root):
    try:
        return run_date.today(os.environ, run_date.load(root))
    except run_date.RunDateError as exc:
        raise _Misconfigured(
            "the run date is refused",
            str(exc),
            "fix config/project.json evidence.run_date or the variable it names",
        ) from exc


def main(argv=None, root=None, today=None, run_audit=None):
    """Audit and judge; *today* (a date) and *run_audit* (npm_audit's shape)
    are a test's own, else the run date and npm."""
    try:
        args = _parse(sys.argv[1:] if argv is None else argv)
    except SystemExit as exc:
        # argparse ends the process itself: status 0 after --help, and a usage
        # error it has already written to stderr otherwise.
        if not exc.code:
            return ExitCode.SUCCESS
        return report(
            ExitCode.USAGE,
            "argparse refused the arguments above",
            "the command line",
            "pass app directories and any --report NAME=FILE, as `make fe-audit` does",
        )
    root = os.path.abspath(ROOT if root is None else root)
    try:
        settings = _settings(root)
    except config_loader.ConfigError as exc:
        return report(
            ExitCode.CONFIG,
            "the dependency audit settings are refused",
            "; ".join(exc.lines),
            "fix the dependency_audit block of config/project.json, then rerun",
        )
    try:
        if today is None:
            today = _today(root)
        return _run(root, args, settings, today, run_audit or npm_audit)
    except _Unusable as exc:
        return report(ExitCode.USAGE, exc.what, exc.on, exc.next_step)
    except _Unanswered as exc:
        return report(ExitCode.BACKEND_ABSENT, exc.what, exc.on, exc.next_step)
    except _Misconfigured as exc:
        return report(ExitCode.CONFIG, exc.what, exc.on, exc.next_step)


if __name__ == "__main__":
    finish(main())
