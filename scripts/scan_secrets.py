#!/usr/bin/env python3
"""
title: scan_secrets — the secret scanner's adapter, over what a commit would carry and over every commit
kind: script
layer: n/a
summary: The gitleaks adapter: runs the scanner config/project.json `secrets.scanner` pins and prints each finding as `file:line rule`, a history finding with its commit's first 12 hex digits after it, never the value. A `secrets.scanner.name` other than gitleaks is CONFIG before anything runs, because the flags, rules file and report fields here are gitleaks's own; another scanner is a second adapter. Every mode runs only the program recorded in `secrets.scanner.record_file`, never one found on PATH: no record, one naming another program or rev, a recorded path that is gone or a program whose digest changed is BACKEND_ABSENT naming `make secrets-install`, never a skip. `write_record`, which scripts/install_scanner.py calls, records an absolute path, `secrets.scanner.rev` and the program's sha256, rewriting the file only when its bytes would change. `--staged` scans the staged diff and passes git's repository context, so the index a hook commits is the one judged; a stage that adds or changes no file (nothing staged, or deletions only) is NOTHING_JUDGED, because a scan over zero files proves nothing. `--staged-or-history`, the pre-commit hook's mode, scans the staged diff, or every commit when nothing is staged, as under `pre-commit run --all-files`. `--history` scans every commit `secrets.scanner.history_log_opts` reaches, and options that reach no commit are NOTHING_JUDGED. The scanner is handed redaction, the inline allow comments ignored, an empty ignore directory, a config that only extends its default rules, the finding status `secrets.scanner.leak_exit_code` and a JSON report in a temporary directory, under the allowlisted environment (scripts/child_env.py). Its status and its report must agree: 0 with an empty list, the finding status with findings; anything else, a report that is not a JSON list of findings included, is BACKEND_ABSENT with the scanner's stderr excerpt, because the scanner gave no verdict, so FAILURE always means a finding. A git command that ran and failed is USAGE. `secrets.scanner.exclusions` removes the findings of one rule in one exact file; one the history scan did not use is CONFIG. A scan beside the scanner's own config or ignore file (`secrets.scanner.refused_files`, anywhere git would commit it or at the root) is CONFIG before the scanner runs, because such a file decides what is judged. No repository, or a history with no commit, is NOTHING_JUDGED. Stdlib-only and 3.6-safe, because the pre-commit hook runs it under the host's python3.
effect: writes
rerun: fixed-point
rerun_proof: test:tests/unit/scripts/test_scan_secrets.py
"""

import argparse
import hashlib
import json
import os
import posixpath
import shutil
import subprocess
import sys
import tempfile

_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import config_loader  # noqa: E402
import git_tree  # noqa: E402
from child_env import ChildEnvError, build_child_env  # noqa: E402
from exit_codes import ExitCode, finish, report  # noqa: E402

ROOT = os.path.dirname(_SCRIPTS)
_BLOCK = ("secrets", "scanner")
_FIELDS = (
    "exclusions",
    "history_log_opts",
    "leak_exit_code",
    "name",
    "record_file",
    "refused_files",
    "rev",
)
_WHERE = "config/project.json secrets.scanner"
# The scanner this module adapts: the flags _run_scanner hands it, _RULES and
# _FINDING_FIELDS are its own. config/project.json secrets.scanner.name must
# name it; another scanner is a second adapter, which this check then admits.
_ADAPTER = "gitleaks"
_STAGED, _HISTORY, _STAGED_OR_HISTORY = "staged", "history", "staged-or-history"
_INSTALL = (
    "run `make secrets-install`, which downloads the pinned scanner release, "
    "checks its sha256 and records it"
)
# The scanner's own config: its default rules and nothing else, so neither a
# config named in the environment nor one in the tree changes what is judged.
_RULES = "[extend]\nuseDefault = true\n"
_FINDING_FIELDS = (("File", str), ("StartLine", int), ("RuleID", str))
_SHORT_COMMIT = 12


def _parse(argv):
    parser = argparse.ArgumentParser(
        prog="scripts/scan_secrets.py",
        description="Run the secret scanner config/project.json secrets.scanner "
        "pins, the one `make secrets-install` recorded.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--staged", action="store_true", help="scan what the next commit would carry"
    )
    mode.add_argument(
        "--history",
        action="store_true",
        help="scan every commit secrets.scanner.history_log_opts reaches",
    )
    mode.add_argument(
        "--staged-or-history",
        action="store_true",
        help="the pre-commit hook's mode: scan the staged diff, or, when nothing "
        "is staged (`pre-commit run --all-files`), every commit",
    )
    return parser.parse_args(argv)


def settings(root):
    """The secrets.scanner settings this adapter reads, by field name; raises
    config_loader.ConfigError on a refused value."""
    keys = config_loader.rows(*[_BLOCK + (field,) for field in _FIELDS])
    values = config_loader.resolve(
        config_loader.read(root), keys, config_loader.CONFIG_FILE
    )
    return {field: values[_BLOCK + (field,)] for field in _FIELDS}


def sha256(path):
    """The hex sha256 of the file at *path*, read in chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_if_changed(path, data):
    """Write the bytes *data* to *path* through a sibling temporary file, only
    when they differ, so a second run leaves the file and its time untouched.
    True when it wrote."""
    try:
        with open(path, "rb") as fh:
            if fh.read() == data:
                return False
    except FileNotFoundError:
        pass
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    handle, scratch = tempfile.mkstemp(dir=folder, prefix=".scanner-")
    try:
        with os.fdopen(handle, "wb") as fh:
            fh.write(data)
        os.replace(scratch, path)
    except BaseException:
        os.unlink(scratch)
        raise
    return True


def record_is_ignored(root, cfg):
    """True when git would never commit the record at
    secrets.scanner.record_file, which names one machine's path."""
    try:
        return git_tree.is_ignored(root, cfg["record_file"])
    except git_tree.NoGitError:
        # With no repository nothing can commit the record, and the shipped
        # .gitignore ignores it once one exists.
        return True


def write_record(root, cfg, path):
    """Record the scanner at the absolute *path* under the configured name and
    rev with its sha256, the one record every scan runs; True when the file
    changed. The caller has checked record_is_ignored."""
    record = {
        "name": cfg["name"],
        "path": path,
        "rev": cfg["rev"],
        "sha256": sha256(path),
    }
    text = json.dumps(record, sort_keys=True, indent=2) + "\n"
    return write_if_changed(
        os.path.join(root, cfg["record_file"]), text.encode("utf-8")
    )


def _recorded(root, cfg):
    """(the recorded program, None), or (None, why it cannot be run)."""
    rel = cfg["record_file"]
    try:
        with open(os.path.join(root, rel), encoding="utf-8") as fh:
            record = json.load(fh)
    except FileNotFoundError:
        return None, "there is no scanner record at %s" % rel
    except (OSError, ValueError) as exc:
        return None, "the scanner record %s cannot be read (%s)" % (rel, exc)
    if not isinstance(record, dict):
        return None, "the scanner record %s is not a JSON object" % rel
    want = (cfg["name"], cfg["rev"])
    have = (record.get("name"), record.get("rev"))
    if have != want:
        return None, "the scanner record %s names %s %s, and config names %s %s" % (
            (rel,) + have + want
        )
    path = record.get("path")
    if not isinstance(path, str) or not os.path.isabs(path):
        return None, "the scanner record %s holds no absolute path" % rel
    if not (os.path.isfile(path) and os.access(path, os.X_OK)):
        return None, "the recorded scanner %s is gone" % path
    if sha256(path) != record.get("sha256"):
        return None, "the recorded scanner %s changed after it was recorded" % path
    return path, None


def _refused(root, cfg):
    """The paths of the scanner's own config and ignore files a scan of *root*
    would sit beside: any git would commit, and any present at the root, where
    the scanner reads its ignore file whatever it is told."""
    names = set(cfg["refused_files"])
    hits = [p for p in git_tree.candidate_files(root) if posixpath.basename(p) in names]
    hits.extend(
        n
        for n in sorted(names)
        if n not in hits and os.path.lexists(os.path.join(root, n))
    )
    return hits


def _findings(text):
    """The findings in a report, or None when it is not a JSON list of them."""
    try:
        loaded = json.loads(text)
    except ValueError:
        return None
    if not isinstance(loaded, list):
        return None
    for item in loaded:
        if not isinstance(item, dict):
            return None
        for field, kind in _FINDING_FIELDS:
            if not isinstance(item.get(field), kind) or isinstance(
                item.get(field), bool
            ):
                return None
    return loaded


def _verdict(status, text, leak):
    """(findings, None) when the status and the report agree, else
    (whatever findings the report held, why they disagree)."""
    findings = None if text is None else _findings(text)
    if text is not None and findings is None:
        return [], "wrote a report that is not a JSON list of findings"
    if status not in (0, leak):
        return findings or [], "exited %d, its own error" % status
    if findings is None:
        return [], "exited %d without a report" % status
    if status == 0 and findings:
        return findings, "exited 0 with %d findings in its report" % len(findings)
    if status == leak and not findings:
        return [], "exited %d, its finding status, with an empty report" % leak
    return findings, None


def _line(finding):
    text = "%s:%d %s" % (finding["File"], finding["StartLine"], finding["RuleID"])
    commit = finding.get("Commit")
    if isinstance(commit, str) and commit:
        text += " " + commit[:_SHORT_COMMIT]
    return text


def _run_scanner(root, cfg, program, staged):
    """(status, report text or None, stderr) of one scanner run."""
    scratch = tempfile.mkdtemp(prefix="scan_secrets-")
    try:
        ignore_dir = os.path.join(scratch, "ignore")
        os.mkdir(ignore_dir)
        rules = os.path.join(scratch, "rules.toml")
        with open(rules, "w", encoding="utf-8") as fh:
            fh.write(_RULES)
        report_path = os.path.join(scratch, "report.json")
        argv = [program, "git"]
        if staged:
            argv += ["--pre-commit", "--staged"]
        else:
            # The `=` form, because each option starts with `-` and would
            # otherwise read as a flag of the scanner's own.
            argv.append("--log-opts=" + " ".join(cfg["history_log_opts"]))
        argv += [
            "--redact",
            "--ignore-gitleaks-allow",
            "--gitleaks-ignore-path",
            ignore_dir,
            "--config",
            rules,
            "--exit-code",
            str(cfg["leak_exit_code"]),
            "--report-format",
            "json",
            "--report-path",
            report_path,
            "--no-banner",
            root,
        ]
        done = subprocess.run(  # noqa: S603 — argv list, never a shell string
            argv,
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=build_child_env(repo_context=staged),
        )
        text = None
        if os.path.exists(report_path):
            with open(report_path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        return done.returncode, text, done.stderr.decode("utf-8", "replace")
    finally:
        shutil.rmtree(scratch)


def _scan(root, cfg, mode):
    name = cfg["name"]
    try:
        refused = _refused(root, cfg)
    except git_tree.NoGitError:
        return report(
            ExitCode.NOTHING_JUDGED,
            "there is no git repository, so no commit to scan",
            root,
            "git init && git add -A && git commit, then rerun",
        )
    if refused:
        return report(
            ExitCode.CONFIG,
            "the scanner's own config or ignore file is in the tree: %s"
            % ", ".join(refused),
            "%s.refused_files" % _WHERE,
            "delete each; an excused finding is a secrets.scanner.exclusions "
            "entry with its reason",
        )
    # Every mode runs the recorded program and never one found on PATH, so
    # the commit hook, `make secret-scan` and CI judge with one checked build.
    program, why = _recorded(root, cfg)
    if program is None:
        return report(
            ExitCode.BACKEND_ABSENT, why, "%s %s" % (name, cfg["rev"]), _INSTALL
        )
    staged = mode != _HISTORY
    # A scan of an empty stage passes over zero files, which proves nothing.
    if staged and not git_tree.staged_paths(root, repo_context=True):
        if mode == _STAGED:
            return report(
                ExitCode.NOTHING_JUDGED,
                "nothing is staged that the next commit would add or change",
                root,
                "stage the files to commit with git add, then rerun; "
                "make secret-scan scans the history",
            )
        # `pre-commit run --all-files` runs the hook outside a commit, so
        # the hook judges every commit instead of passing over nothing.
        sys.stdout.write(
            "scan_secrets: nothing is staged, so every commit is scanned\n"
        )
        staged = False
    if staged:
        on = "the staged diff of %s" % root
    else:
        options = " ".join(cfg["history_log_opts"])
        if git_tree.head_commit(root) is None:
            return report(
                ExitCode.NOTHING_JUDGED,
                "the repository has no commit, so no history to scan",
                root,
                "git add -A && git commit, then rerun",
            )
        # A range of zero commits is a scan over nothing, which the scanner
        # reports as clean.
        if not git_tree.log_commits(root, cfg["history_log_opts"]):
            return report(
                ExitCode.NOTHING_JUDGED,
                "`git log %s` reaches no commit, so the history scan would "
                "judge nothing" % options,
                "%s.history_log_opts" % _WHERE,
                "widen the options to reach at least one commit, then rerun",
            )
        on = "every commit `git log %s` reaches in %s" % (options, root)
    try:
        status, text, stderr = _run_scanner(root, cfg, program, staged)
    except OSError as exc:
        return report(
            ExitCode.BACKEND_ABSENT,
            "%s cannot be run (%s)" % (program, exc),
            on,
            _INSTALL,
        )
    findings, problem = _verdict(status, text, cfg["leak_exit_code"])
    excused = cfg["exclusions"]
    used = set()
    left = []
    for finding in findings:
        key = (finding["File"], finding["RuleID"])
        if key[1] in excused.get(key[0], {}):
            used.add(key)
        else:
            left.append(finding)
    for line in sorted(_line(f) for f in left):
        sys.stdout.write(line + "\n")
    unused = sorted(
        "%s %s" % (path, rule)
        for path, rules in excused.items()
        for rule in rules
        if (path, rule) not in used
    )
    if problem is not None:
        sys.stderr.write(
            "scan_secrets: %s stderr (last %d characters):\n%s\n"
            % (name, git_tree.STDERR_MAX, stderr[-git_tree.STDERR_MAX :].rstrip())
        )
        # Not FAILURE, which is a finding: the scanner gave no verdict, so the
        # fix is to the scanner, never to a credential.
        return report(
            ExitCode.BACKEND_ABSENT,
            "%s %s" % (name, problem),
            on,
            "read its stderr above, and reinstall it with `make secrets-install` "
            "if it is broken; a scan that cannot be read is never a pass",
        )
    if left:
        if unused and not staged:
            sys.stderr.write(
                "scan_secrets: exclusions this scan did not use: %s\n"
                % "; ".join(unused)
            )
        return report(
            ExitCode.FAILURE,
            "%d candidate secret%s found" % (len(left), "" if len(left) == 1 else "s"),
            on,
            "rotate each credential at its provider before removing it, because "
            "history keeps the value; a fake one kept on purpose gets a "
            "%s.exclusions entry with its reason" % _WHERE,
        )
    if unused and not staged:
        return report(
            ExitCode.CONFIG,
            "exclusions the scan did not use: %s" % "; ".join(unused),
            "%s.exclusions" % _WHERE,
            "remove each, or correct its path or rule id",
        )
    sys.stdout.write(
        "scan_secrets: %s scan clean (%s %s, %d excused)\n"
        % (_STAGED if staged else _HISTORY, name, cfg["rev"], len(findings))
    )
    return ExitCode.SUCCESS


def main(argv=None, root=None):
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
            "call it with exactly one of --staged, --history or --staged-or-history",
        )
    root = os.path.abspath(ROOT if root is None else root)
    try:
        cfg = settings(root)
        if cfg["name"] != _ADAPTER:
            return report(
                ExitCode.CONFIG,
                "secrets.scanner.name is %r, and scripts/scan_secrets.py adapts "
                "%s only" % (cfg["name"], _ADAPTER),
                "%s.name" % _WHERE,
                "name %s, or add an adapter for that scanner first" % _ADAPTER,
            )
        if args.staged:
            return _scan(root, cfg, _STAGED)
        if args.history:
            return _scan(root, cfg, _HISTORY)
        return _scan(root, cfg, _STAGED_OR_HISTORY)
    except config_loader.ConfigError as exc:
        return report(
            ExitCode.CONFIG,
            "the secret scanner settings are refused",
            "; ".join(exc.lines),
            "fix the secrets.scanner block of config/project.json, then rerun",
        )
    except ChildEnvError as exc:
        return report(
            ExitCode.CONFIG,
            "the scanner's environment cannot be built (%s)" % exc,
            "config/project.json child_env",
            "fix the child_env block, then rerun",
        )
    except git_tree.GitFailedError as exc:
        # Not FAILURE, which is a finding: git could not read the input.
        return report(
            ExitCode.USAGE,
            "git failed (%s)" % exc,
            root,
            "fix the repository git cannot read, then rerun",
        )


if __name__ == "__main__":
    finish(main())
