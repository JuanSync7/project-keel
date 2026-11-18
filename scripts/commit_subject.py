#!/usr/bin/env python3
"""
title: Commit subjects — one policy matcher for history and message files
kind: script
layer: n/a
summary: Judges a subject against commit_subject policy through one pure matcher. The message-file CLI reads config through config_loader from the current project directory, skips leading blank and comment lines, and refuses findings with FAILURE, unreadable input with USAGE and malformed policy with CONFIG. Stdlib-only and 3.6-safe for the host hook interpreter; it starts no process and writes no file.
effect: read-only
"""

import argparse
import os
import re

import config_loader
from exit_codes import ExitCode, finish, report

__all__ = ["load_policy", "subject_findings"]

_FIELDS = ("types", "scope_chars", "adoption_boundary")


def load_policy(root):
    """Load and validate commit_subject through the declared loader rows."""
    loaded = config_loader.read(root)
    values = config_loader.resolve(
        loaded,
        config_loader.rows(*[("commit_subject", field) for field in _FIELDS]),
        "config/project.json",
    )
    return {field: values[("commit_subject", field)] for field in _FIELDS}


def subject_findings(subject, policy):
    """Return findings for one subject against an already loaded policy."""
    pattern = r"(?:%s)(?:\([%s]+\))?!?: (?P<description>[^\r\n]+)" % (
        "|".join(re.escape(value) for value in policy["types"]),
        re.escape(policy["scope_chars"]),
    )
    match = re.fullmatch(pattern, subject)
    if match is not None:
        description = match.group("description")
        if description == description.strip(" "):
            return []
    return [
        "commit_subject: %r does not match <type>(<scope>)!: <description>; "
        "use a declared type, optional scope and !, and a non-empty description "
        "with no leading or trailing space" % subject
    ]


class _UsageError(ValueError):
    """The CLI cannot read the requested message."""


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise _UsageError(message)


def main(argv=None):
    """Judge the first non-comment, nonblank line in the message file."""
    parser = _Parser(description="Judge a commit subject using commit_subject policy.")
    parser.add_argument("--message-file", required=True, help="commit message to judge")
    try:
        args = parser.parse_args(argv)
    except _UsageError as exc:
        return report(
            ExitCode.USAGE,
            str(exc),
            "commit_subject command line",
            "pass --message-file PATH",
        )
    try:
        policy = load_policy(os.getcwd())
    except config_loader.ConfigError as exc:
        return report(
            ExitCode.CONFIG,
            str(exc),
            "commit_subject policy",
            "repair the named key in config/project.json",
        )
    try:
        with open(args.message_file, encoding="utf-8") as stream:
            subject = next(
                (
                    line.rstrip("\r\n")
                    for line in stream
                    if line.strip() and not line.startswith("#")
                ),
                "",
            )
    except (OSError, UnicodeError) as exc:
        return report(
            ExitCode.USAGE,
            "cannot read message: %s" % exc,
            args.message_file,
            "provide a readable UTF-8 message file",
        )
    findings = subject_findings(subject, policy)
    if findings:
        return report(
            ExitCode.FAILURE,
            "; ".join(findings),
            args.message_file,
            "write a subject in the declared shape",
        )
    return ExitCode.SUCCESS


if __name__ == "__main__":
    finish(main())
