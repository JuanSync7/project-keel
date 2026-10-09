#!/usr/bin/env python3
"""
title: finish_update — runs the `after` migrations a stopped `copier update` never ran
kind: script
layer: n/a
summary: The command every migration refusal names under an update. copier 9.x writes the new render, `.copier-answers.yml` with the new `_commit` included, into the project before its `after` migrations run, and stops at the first one that fails (TaskError), leaving the tree dirty with no later migration run; a second `copier update` then refuses the dirty tree, and committing first would record the new `_commit`, so the next update would never replay the migrations (copier 9.17, measured). Once the operator has resolved the files a refusal named, this job replays them. Preconditions, each a one-line exit 2 naming the fix: the project is a git work tree; `.copier-answers.yml` parses in the work tree and at HEAD (read-only, through review_docs' `git_argv`); the two record different `_commit` values, or no update is in progress. The template is `--template PATH`, else the answers' `_src_path` expanded the way copier's `get_repo` does (gh:/gl: shorthands, git URL prefixes, a local repository or bundle), else an exit 2 asking for `--template`; it is cloned into a temporary directory, checked out at the work tree's `_commit` and removed afterwards. Its copier.yml (or copier.yaml) is read with yaml.safe_load; `_envops`, `_jinja_extensions`, an `_answers_file` other than the one read, or a migration key other than `command` and `when` exit 2 naming it, since this job could not render them as copier does. Each migration is rendered in a sandboxed Jinja environment with StrictUndefined, so a name it does not supply fails closed: the answers that do not start with `_`, `_stage` (after), `_version_from` (HEAD's `_commit`), `_version_to` (the work tree's), `_copier_python` (this interpreter), `_copier_operation` (update) and `_copier_conf` (src_path, the checkout; dst_path, the project; answers_file). `when` goes through `cast_to_bool`, which mirrors copier's own (copier/_tools.py); a list command runs as argv, a string under /bin/sh, both from the project root in the allowlisted environment, in copier.yml's order. The first that exits non-zero stops the run, exit 2 naming it. `--dry-run` prints each kept command as one JSON line on stdout and runs nothing. It never stages, commits or edits the answers; the operator reviews and commits. Run as a script, it first asks scripts/jobs/conflict_guard.py whether a module it imports, or the answers file it declares reading, holds a conflict hunk, and if one does it names each file and its own rerun command and exits 2.
effect: writes
rerun: fixed-point
rerun_proof: test:tests/integration/test_finish_update.py
"""

# 3.6-safe and stdlib-only at import on purpose, like the other jobs: the
# operator runs this with the interpreter copier ran under, in a project that
# may have no virtualenv. yaml and jinja2 are copier's own dependencies, so
# that interpreter has them; they are imported only when needed.
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

_JOBS = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.dirname(_JOBS)
for _dir in (_JOBS, _SCRIPTS):
    if _dir not in sys.path:
        sys.path.insert(0, _dir)
# Run in a project mid-update; importing the siblings below would otherwise
# leave __pycache__/*.pyc in it. Only when run as a script.
if __name__ == "__main__":
    sys.dont_write_bytecode = True

import conflict_guard  # noqa: E402

# Before every import below: this runs where a module it imports, or the
# answers file it reads, may still hold a conflict hunk. Its own rerun, not
# the finish command, is what it names: it is the finish command.
if __name__ == "__main__":
    conflict_guard.exit_if_conflicted(
        __file__,
        os.path.dirname(_SCRIPTS),
        "finish_update",
        conflict_guard.rerun_command(__file__, os.path.dirname(_SCRIPTS), sys.argv[1:]),
        search_path=(_JOBS, _SCRIPTS),
    )

import child_env  # noqa: E402
import review_docs  # noqa: E402

# copier's default answers file. A template that names another is refused
# once its copier.yml is read: the commits below were read from this one.
ANSWERS_FILE = ".copier-answers.yml"
PROJECT_READS = (".copier-answers.yml",)
# The template's config file names copier accepts, in the order it tries them.
TEMPLATE_CONFIGS = ("copier.yml", "copier.yaml")
# copier.yml settings that change how copier renders a migration; this job
# renders with a plain sandboxed environment, so it refuses a template that
# sets one rather than render a command copier would render differently.
UNSUPPORTED_SETTINGS = ("_envops", "_jinja_extensions")
# The keys of a migration this job can replay as copier does. copier also
# reads `version` (a legacy filter on the two versions) and
# `working_directory`; replaying either here would be a guess.
MIGRATION_KEYS = ("command", "when")
# copier's default `when` for a migration (copier/_template.py).
DEFAULT_WHEN = '{{ _stage == "after" }}'
STAGE = "after"
OPERATION = "update"
SHELL = "/bin/sh"
INSTALL_HINT = (
    "run it with the interpreter copier runs under, or install keel's "
    "`template` extra (pip install -e '.[template]')"
)

# copier/_vcs.py get_repo, restated: the shorthands it expands and the URL
# shapes it hands to git untouched.
_REPLACEMENTS = (
    (re.compile(r"^gh:/?(.*\.git)$"), r"https://github.com/\1"),
    (re.compile(r"^gh:/?(.*)$"), r"https://github.com/\1.git"),
    (re.compile(r"^gl:/?(.*\.git)$"), r"https://gitlab.com/\1"),
    (re.compile(r"^gl:/?(.*)$"), r"https://gitlab.com/\1.git"),
)
_GIT_PREFIX = ("git@", "git://", "git+", "https://github.com/", "https://gitlab.com/")
_GIT_POSTFIX = ".git"
# copier/_tools.py cast_to_bool's YAML booleans and nulls.
_TRUE = ("y", "yes", "t", "true", "on")
_FALSE = ("n", "no", "f", "false", "off", "~", "null", "none")


class FinishError(Exception):
    """A precondition failed, or a step cannot be rendered or run."""


def cast_to_bool(value):
    """copier's own `cast_to_bool` (copier/_tools.py): a number is true unless
    zero; a string is false when blank or a YAML false/null, true when a YAML
    true; anything else is `bool(value)`."""
    try:
        return bool(float(value))
    except (TypeError, ValueError):
        pass
    try:
        lower = value.strip().lower()
    except AttributeError:
        return bool(value)
    if not lower:
        return False
    if lower in _TRUE:
        return True
    if lower in _FALSE:
        return False
    return bool(value)


def template_source(src_path, root):
    """The git source copier's `get_repo` makes of *src_path*, or None when it
    makes none. A relative local path is read from *root*, where an update
    is run."""
    url = src_path
    for pattern, replacement in _REPLACEMENTS:
        url = pattern.sub(replacement, url)
    if url.endswith(_GIT_POSTFIX) or url.startswith(_GIT_PREFIX):
        if url.startswith("git+"):
            return url[4:]
        if url.startswith("https://") and not url.endswith(_GIT_POSTFIX):
            return url + _GIT_POSTFIX
        return url
    path = os.path.expanduser(url) if url.startswith("~") else url
    path = os.path.join(root, path)
    if os.path.isdir(os.path.join(path, ".git")) or (
        os.path.isfile(path) and path.endswith(".bundle")
    ):
        return os.path.normpath(path)
    return None


def _yaml():
    try:
        import yaml
    except ImportError:
        raise FinishError("PyYAML is not importable; " + INSTALL_HINT) from None
    return yaml


def _jinja():
    try:
        import jinja2
        import jinja2.sandbox
    except ImportError:
        raise FinishError("jinja2 is not importable; " + INSTALL_HINT) from None
    return jinja2


def _run_git(argv, cwd, what):
    """git's stdout (bytes) for *argv* at *cwd*; FinishError naming *what*."""
    try:
        env = child_env.build_child_env()
        proc = subprocess.run(
            argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env
        )
    except (OSError, child_env.ChildEnvError) as e:
        raise FinishError("%s: %s" % (what, e)) from e
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise FinishError("%s: %s" % (what, err[-1] if err else "git failed"))
    return proc.stdout


def _read_git(root, *args):
    """A read-only git call in the project (review_docs' `git_argv`)."""
    try:
        argv = review_docs.git_argv(root, *args)
    except review_docs.GitConfigError as e:
        raise FinishError("git %s: %s" % (args[0], e)) from e
    return _run_git(argv, root, "git %s" % args[0])


def _answers(text, where):
    """The mapping *text* holds, with a string `_commit`; FinishError else."""
    try:
        data = _yaml().safe_load(text)
    except Exception as e:  # noqa: BLE001 -- any YAML error is a stated stop
        raise FinishError("%s is not YAML (%s); resolve it" % (where, e)) from e
    if not isinstance(data, dict) or not isinstance(data.get("_commit"), str):
        raise FinishError("%s records no `_commit`" % where)
    return data


def update_in_progress(root):
    """(answers in the work tree, the `_commit` HEAD's answers record): the
    update copier stopped. FinishError when there is none to finish."""
    try:
        inside = _read_git(root, "rev-parse", "--is-inside-work-tree")
    except FinishError:
        inside = b""
    if inside.strip() != b"true":
        raise FinishError("%s is not a git work tree; copier update needs one" % root)
    path = os.path.join(root, ANSWERS_FILE)
    try:
        with open(path, encoding="utf-8") as fh:
            current = _answers(fh.read(), ANSWERS_FILE)
    except OSError as e:
        raise FinishError("%s cannot be read: %s" % (ANSWERS_FILE, e)) from e
    head_text = _read_git(root, "cat-file", "blob", "HEAD:" + ANSWERS_FILE)
    head = _answers(head_text.decode("utf-8"), "HEAD:" + ANSWERS_FILE)
    if current["_commit"] == head["_commit"]:
        raise FinishError(
            "no update in progress: %s records the commit HEAD does (%s)"
            % (ANSWERS_FILE, head["_commit"])
        )
    return current, head["_commit"]


def checkout(source, commit, dest):
    """Clone *source* into *dest* and check out *commit* there."""
    _run_git(
        ["git", "clone", "--quiet", "--no-checkout", source, dest],
        None,
        "cloning the template %s" % source,
    )
    _run_git(
        ["git", "-c", "advice.detachedHead=false", "checkout", "--quiet", commit],
        dest,
        "the template %s has no commit %s; pass --template a clone that holds it"
        % (source, commit),
    )


def template_config(checkout_dir):
    """The template's copier settings, read from its checkout."""
    found = [
        name
        for name in TEMPLATE_CONFIGS
        if os.path.isfile(os.path.join(checkout_dir, name))
    ]
    if len(found) != 1:
        raise FinishError(
            "the template holds %s of %s; copier needs exactly one"
            % (len(found), " and ".join(TEMPLATE_CONFIGS))
        )
    with open(os.path.join(checkout_dir, found[0]), encoding="utf-8") as fh:
        try:
            config = _yaml().safe_load(fh.read())
        except Exception as e:  # noqa: BLE001 -- any YAML error is a stated stop
            raise FinishError("the template's %s: %s" % (found[0], e)) from e
    if not isinstance(config, dict):
        raise FinishError("the template's %s is not a mapping" % found[0])
    for key in UNSUPPORTED_SETTINGS:
        if key in config:
            raise FinishError(
                "the template sets %s, which this job cannot render as copier "
                "does; finish the update by hand" % key
            )
    answers_file = config.get("_answers_file", ANSWERS_FILE)
    if answers_file != ANSWERS_FILE:
        raise FinishError(
            "the template's answers file is %s, not %s" % (answers_file, ANSWERS_FILE)
        )
    return config


def migrations(config):
    """[(command, when)] from *config*'s `_migrations`, in order."""
    out = []
    for i, entry in enumerate(config.get("_migrations") or [], 1):
        if isinstance(entry, (str, list)):
            out.append((entry, DEFAULT_WHEN))
            continue
        if not isinstance(entry, dict) or "command" not in entry:
            raise FinishError("migration %d has no command" % i)
        extra = sorted(set(entry) - set(MIGRATION_KEYS))
        if extra:
            raise FinishError(
                "migration %d sets %s, which this job cannot replay; finish "
                "the update by hand" % (i, ", ".join(extra))
            )
        out.append((entry["command"], entry.get("when", DEFAULT_WHEN)))
    return out


def context(answers, version_from, root, checkout_dir):
    """The names a migration is rendered with (see the module summary)."""
    ctx = {k: v for k, v in answers.items() if not k.startswith("_")}
    ctx.update(
        {
            "_stage": STAGE,
            "_version_from": version_from,
            "_version_to": answers["_commit"],
            "_copier_python": sys.executable,
            "_copier_operation": OPERATION,
            "_copier_conf": {
                "src_path": checkout_dir,
                "dst_path": root,
                "answers_file": ANSWERS_FILE,
            },
        }
    )
    return ctx


def steps(config, ctx):
    """The commands to run, rendered: a list (argv) or a string (shell)."""
    jinja2 = _jinja()
    env = jinja2.sandbox.SandboxedEnvironment(undefined=jinja2.StrictUndefined)

    def render(text, i):
        try:
            return env.from_string(text).render(**ctx)
        except jinja2.TemplateError as e:
            raise FinishError("migration %d cannot be rendered: %s" % (i, e)) from e

    out = []
    for i, (command, when) in enumerate(migrations(config), 1):
        cond = render(when, i) if isinstance(when, str) else when
        if not cast_to_bool(cond):
            continue
        if isinstance(command, list):
            out.append([render(str(part), i) for part in command])
        else:
            out.append(render(command, i))
    return out


def run_steps(root, commands):
    """Run each command from *root*; FinishError on the first that fails."""
    for i, command in enumerate(commands, 1):
        argv = command if isinstance(command, list) else [SHELL, "-c", command]
        try:
            code = subprocess.run(
                argv, cwd=root, env=child_env.build_child_env()
            ).returncode
        except (OSError, child_env.ChildEnvError) as e:
            raise FinishError("step %d of %d: %s" % (i, len(commands), e)) from e
        if code != 0:
            raise FinishError(
                "step %d of %d exited %d: %s; fix what it names, then run this "
                "again" % (i, len(commands), code, json.dumps(command))
            )


def finish(root, template=None, dry_run=False):
    """Finish the update copier stopped in *root*; return the commands kept."""
    answers, version_from = update_in_progress(root)
    if template is not None:
        source = template_source(os.path.abspath(template), root)
        if source is None:
            raise FinishError("--template %s is not a git repository" % template)
    else:
        src_path = answers.get("_src_path")
        source = template_source(src_path, root) if isinstance(src_path, str) else None
        if source is None:
            raise FinishError(
                "the template %s (_src_path) cannot be found; pass --template "
                "a clone of it" % src_path
            )
    scratch = tempfile.mkdtemp(prefix="finish_update.")
    try:
        checkout_dir = os.path.join(scratch, "template")
        checkout(source, answers["_commit"], checkout_dir)
        config = template_config(checkout_dir)
        commands = steps(config, context(answers, version_from, root, checkout_dir))
        if not dry_run:
            run_steps(root, commands)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return commands


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Finish a copier update that stopped at a failed migration: once "
            "the files it named are resolved, run every `after` migration of "
            "the template version the update reached, in order, as copier "
            "would. Never stages or commits."
        )
    )
    parser.add_argument(
        "--template",
        metavar="PATH",
        default=None,
        help="a clone of the template (default: the answers' _src_path)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print each command it would run as one JSON line; run nothing",
    )
    args = parser.parse_args(argv)
    root = os.path.dirname(_SCRIPTS)
    try:
        commands = finish(root, args.template, args.dry_run)
    except FinishError as e:
        sys.stderr.write("finish_update: %s\n" % e)
        return 2
    if args.dry_run:
        for command in commands:
            sys.stdout.write(json.dumps(command) + "\n")
        return 0
    sys.stderr.write(
        "finish_update: update finished (%d steps ran); review the changes "
        "and commit them\n" % len(commands)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
