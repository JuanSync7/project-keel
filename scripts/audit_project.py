#!/usr/bin/env python3
"""
title: audit_project — another keel project judged by this template's current gates
kind: script
layer: n/a
summary: Answers "what would this template's current gates say about DEST once `copier update` has landed?" by judging one consistent tree, the one the update leaves, never a mix of merged and unmerged files. It builds that tree in a scratch directory (`tempfile.TemporaryDirectory`, prefix `keel-audit-`, removed on every exit path): a clone of this checkout with its uncommitted edits committed on top (a snapshot, so the template's own index is never refreshed), a copy of DEST's files (the ones git does not ignore; a symlink leaving DEST is copied as its target's bytes, so nothing is written through it), and a real `copier update --trust --conflict inline` of the copy against the snapshot, run as a child process with an allowlisted environment and a hermetic git config. check_structure's letters (A..Y) run in-process on the copy before and after the update: a letter finding after the update is owed; one present only before is resolved by the update; a path copier leaves conflicted is reported in the `conflict` group, and the tree after the update is then checked twice, every conflict hunk the project's way and every hunk the template's way (`resolve_conflict`, read from copier's own markers), so no check parses a marker and no conflicted file is put back to DEST's bytes beside the update's other files: a finding both resolutions have is owed, one only one has depends on how the conflict is resolved and is not judged, and a finding in a conflicted file is not judged. The `retired` group names each DEST file the update deletes that the project edited (an error, owed: the same `is_edited` rule scripts/jobs/keep_edited_retired.py applies; the prediction runs that guard migration as the real update does, so a file still deleted after it is one a later `rm` migration removes or one copier deleted without running migrations). The config group warns (`update-refused`) when the real update would refuse DEST: outside git, or with uncommitted changes, which it names. The config group names what the update did to each key of each JSON config (`classify`: arrives, updates, merges, removed-upstream) from the template's render at DEST's `_commit`, DEST's file and the predicted file. Every finding carries an origin evidence kind (template-unedited, template-edited, template-rendered, template-new, project, unknown) read from git at `_commit`; a file that cannot be read is `unknown`. When `_commit` does not resolve here nothing is predicted: DEST is judged as it stands and the not-checked section says so. It adds the freshness judge (scripts/jobs/review_docs.py) and the restamp writer's `pending` list (scripts/jobs/restamp_docs.py) on DEST, both of which the update's last migration clears. A "not checked" section names every proof it does not run, including that the update's tasks run the project's merged restamp step inside the scratch copy. DEST and this checkout are never written: DEST is read with open() and ast and its git with name-level commands built by `review_docs.git_argv` that write nothing and switch off fsmonitor, signature verification and every filter driver its git config names; no make target, hook or module of DEST runs in this process. Exit 0 when no letter or `retired` error is owed, 1 when one is (or no file was seen), 2 on a usage error, a refusal (DEST is not a keel project, or its answers are malformed), a template render error (including answers of the wrong type), a failed copier update or a missing extra. Keel-only: excluded from generated projects (docs/design/downstream-feedback.md, slice 5); a generated project's `make audit-project` stub points back at the template checkout.
effect: writes
rerun: fixed-point
rerun_proof: test:tests/integration/test_copier_audit.py
"""

from __future__ import annotations

import argparse
import calendar
import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import namedtuple

_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
for _dir in (_SCRIPTS, os.path.join(_SCRIPTS, "jobs")):
    if _dir not in sys.path:
        sys.path.insert(0, _dir)

import check_structure  # noqa: E402
import child_env  # noqa: E402
import keep_edited_retired  # noqa: E402
import restamp_docs  # noqa: E402
import review_docs  # noqa: E402

# The template checkout whose gates judge DEST: the one this file ships in.
TEMPLATE = os.path.dirname(_SCRIPTS)
ANSWERS = ".copier-answers.yml"
MANIFEST = "config/project.json"
LETTERS = tuple(letter for letter, _fn in check_structure.CHECKS)
GROUPS = LETTERS + ("conflict", "config", "freshness", "restamp", "retired")
TIERS = ("error", "warning", "info")
FRESHNESS_RESOLVED_BY = "copier update (_migrations: restamp_docs)"
# A letter finding in the tree before the update that the tree the update
# leaves does not have: the update itself resolves it.
UPDATE_RESOLVES = "copier update (absent from the tree the update leaves)"
UNJUDGED_CONFLICT = "conflict"
EXTRA_HINT = "needs the 'template' extra (pip install -e \".[template]\")"
SCRATCH_PREFIX = "keel-audit-"
# The scratch tree's own name in a message, in place of its real path: the
# path differs every run, and the report must not.
SCRATCH_MASK = "<scratch>"

# What the audit does not prove, always printed: a cap or a skip that is not
# named here is a silent one. (item, reason).
NOT_CHECKED = (
    (
        "make-target effect sweep",
        "a runtime proof: it runs each [local] target in a scratch copy, which "
        "runs project code; after the update run `make verify` in the project",
    ),
    (
        "the project's test suite, lint and typecheck",
        "runtime proofs that run project code; after the update run `make verify` "
        "in the project",
    ),
    (
        "check-corpus, check-openapi, check-aad, check-cdmon",
        "the rest of `make check-all` builds or imports project artefacts; run "
        "`make check-all` in the project after the update",
    ),
    (
        "shell-script spawns",
        "check_X reads Python with ast; a child process started from a shell "
        "script or a Makefile recipe is not seen",
    ),
    (
        "nested makefiles outside the include walk",
        "check_W reads the Makefile and what it includes; a makefile reached only "
        "through `make -C` is not read",
    ),
    (
        "check_N's 5-line cap",
        "check_N prints at most 5 differing lines per twin; inert in a generated "
        "project, which declares no twins",
    ),
    (
        "files DEST's git ignores",
        "not copied into the scratch copy the update runs on, so neither run "
        "judges them (a DEST outside git is copied as check_structure walks it)",
    ),
    (
        "code the update runs",
        "the predicted tree is a real `copier update` of a scratch copy, so the "
        "template's `_tasks` and `_migrations` run there: keel's run "
        "scripts/jobs/restamp_docs.py as the update merges it with the project's "
        "edits, which imports the copy's scripts/ modules. It runs with an "
        "allowlisted environment, a hermetic git config with no hooks, and no "
        "DEST .git, inside a scratch directory removed on exit; the project runs "
        "the same step on its own update",
    ),
)


class AuditError(Exception):
    """A template input the audit cannot use (copier.yml, a twin, an answer it
    needs), or an update copier refused. Exit 2: a report built on a guessed
    config or a half-made tree would mislead."""


# What rendering or casting DEST's answers raises when an answer has a type
# the template does not expect; each becomes an AuditError (exit 2).
_DATA_ERRORS = (TypeError, ValueError, AttributeError, KeyError, IndexError)


# --- git, read-only ---------------------------------------------------------


def _git(cwd, *args, binary=False):
    """(returncode, stdout, stderr) of a read-only git call at *cwd*; returncode
    None when git is absent. The judge's argv on every call: no index
    write-back, and no command the repository's own config names (fsmonitor,
    filter drivers, the signature verifier). When git will not list the
    filter drivers the call is not made: returncode 128, git's own refusal."""
    if shutil.which("git") is None:
        return None, b"" if binary else "", "git is not installed"
    try:
        argv = review_docs.git_argv(cwd, *args)
    except review_docs.GitConfigError as exc:
        return 128, b"" if binary else "", "cannot list filter drivers: %s" % exc
    proc = subprocess.run(
        argv,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=not binary,
        env=child_env.build_child_env(),
    )
    err = proc.stderr.decode("utf-8", "replace") if binary else proc.stderr
    return proc.returncode, proc.stdout, err


def resolve_commit(commit):
    """The full sha *commit* names in TEMPLATE, or None when it names nothing
    there (a WIP commit, a shallow clone, another fork). A name that starts with
    `-` is not looked up: it would reach git as an option."""
    if not commit or commit.startswith("-"):
        return None
    code, out, _err = _git(
        TEMPLATE, "rev-parse", "--verify", "-q", commit + "^{commit}"
    )
    return out.strip() if code == 0 and out.strip() else None


def _tree_at(sha):
    """{path: "blob" | "tree"} of every path in TEMPLATE at *sha*."""
    code, out, err = _git(TEMPLATE, "ls-tree", "-r", "-t", "-z", sha)
    if code != 0:
        raise AuditError("cannot list the template at %s: %s" % (sha, err.strip()))
    tree = {}
    for entry in out.split("\0"):
        if not entry:
            continue
        meta, _tab, path = entry.partition("\t")
        tree[path] = meta.split()[1]
    return tree


def _blob(sha, path):
    """The bytes of *path* in TEMPLATE at *sha*."""
    code, out, err = _git(
        TEMPLATE, "cat-file", "blob", "%s:%s" % (sha, path), binary=True
    )
    if code != 0:
        raise AuditError("cannot read %s at %s: %s" % (path, sha, err.strip()))
    return out


def template_revision():
    """`git describe --always` of TEMPLATE plus `-dirty` when its tracked files
    differ from HEAD, else "unknown". `describe --dirty` itself rewrites
    .git/index (measured, git 2.43.5), so dirtiness is the judge's read-only
    `modified_paths`."""
    code, out, _err = _git(TEMPLATE, "describe", "--always")
    if code != 0 or not out.strip():
        return "unknown"
    dirty = review_docs.modified_paths(TEMPLATE)
    return out.strip() + ("-dirty" if dirty else "")


# --- readers ----------------------------------------------------------------


def worktree_reader(root):
    """A reader over the files under *root*: relpath -> text, or None when the
    path is not a file there."""

    def read(relpath):
        full = os.path.join(root, relpath)
        if not os.path.isfile(full):
            return None
        with open(full, encoding="utf-8") as fh:
            return fh.read()

    return read


def git_reader(sha):
    """A reader over TEMPLATE at *sha*: relpath -> text, or None when the path
    is not a file there."""
    tree = _tree_at(sha)

    def read(relpath):
        if tree.get(relpath) != "blob":
            return None
        return _blob(sha, relpath).decode("utf-8")

    return read


# --- rendering the template's configs in memory -----------------------------


def _extras():
    """(yaml, jinja2), imported only when needed: the template extra, which
    also provides the copier the prediction runs as a child (checked here, so
    a missing one is exit 2 naming the extra, not a failed update)."""
    import jinja2
    import yaml

    if importlib.util.find_spec("copier") is None:
        raise ImportError("No module named 'copier'")
    return yaml, jinja2


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _cast(yaml, value, qtype):
    """A rendered default cast to its question's type, as copier casts it."""
    if not isinstance(value, str):
        return value
    if qtype == "bool":
        parsed = yaml.safe_load(value) if value.strip() else False
        return bool(parsed)
    if qtype == "int":
        return int(value)
    if qtype == "float":
        return float(value)
    if qtype in ("yaml", "json"):
        return yaml.safe_load(value)
    return value


def render_configs(reader, answers):
    """({config relpath: parsed data or None}, notes) for every path in
    check_structure.JSON_CONFIGS, rendered in memory from the template *reader*
    reads, with *answers* (DEST's) as the context.

    A `<path><suffix>` twin is rendered with jinja2 under StrictUndefined; a
    plain file is copied verbatim, as copier copies it. Every copier.yml
    question absent from the answers is given its default, rendered in
    copier.yml order, so a derived (`when: false`) value such as project_slug
    is computed, never re-typed. *notes* names each question the answers lack
    (copier update would ask it) and each answer the template no longer asks."""
    yaml, jinja2 = _extras()
    spec_text = reader("copier.yml")
    if spec_text is None:
        spec_text = reader("copier.yaml")
    if spec_text is None:
        raise AuditError("the template has no copier.yml")
    try:
        spec = yaml.safe_load(spec_text)
    except yaml.YAMLError as exc:
        raise AuditError("copier.yml is not valid YAML: %s" % exc) from exc
    if not isinstance(spec, dict):
        raise AuditError("copier.yml is not a mapping")
    suffix = spec.get("_templates_suffix", ".jinja")
    env = jinja2.Environment(
        keep_trailing_newline=True, undefined=jinja2.StrictUndefined
    )

    def render(text, context, what):
        try:
            return env.from_string(text).render(**context)
        except jinja2.UndefinedError as exc:
            raise AuditError("%s: %s" % (what, exc)) from exc
        except jinja2.TemplateError as exc:
            raise AuditError("%s: cannot render (%s)" % (what, exc)) from exc
        # An answer of a type the template does not expect (`profiles: null`):
        # the data is DEST's, so its failure is a named refusal, never a crash.
        except _DATA_ERRORS as exc:
            raise AuditError(
                "%s: cannot render with DEST's answers (%s: %s)"
                % (what, type(exc).__name__, exc)
            ) from exc

    def cast(value, qtype, what):
        try:
            return _cast(yaml, value, qtype)
        except _DATA_ERRORS + (yaml.YAMLError,) as exc:
            raise AuditError(
                "%s: cannot cast to %s (%s: %s)"
                % (what, qtype, type(exc).__name__, exc)
            ) from exc

    questions = [
        (name, q if isinstance(q, dict) else {"default": q})
        for name, q in spec.items()
        if not name.startswith("_")
    ]
    context = {
        k: v
        for k, v in answers.items()
        if not k.startswith("_") and k in dict(questions)
    }
    notes = []
    for name, q in questions:
        if name in context:
            continue
        default = q.get("default")
        if isinstance(default, str):
            default = render(default, context, "copier.yml `%s` default" % name)
        value = cast(default, q.get("type", "str"), "copier.yml `%s` default" % name)
        context[name] = value
        when = q.get("when", True)
        if isinstance(when, str):
            what = "copier.yml `%s` when" % name
            when = cast(render(when, context, what), "bool", what)
        if when:
            notes.append(
                "new question %s (template default: %s)" % (name, _canonical(value))
            )
    notes.extend(
        "answer %s is no longer a template question; ignored" % name
        for name in sorted(answers)
        if not name.startswith("_") and name not in context
    )

    configs = {}
    for relpath in check_structure.JSON_CONFIGS:
        rel = relpath.replace(os.sep, "/")
        twin = reader(rel + suffix) if suffix else None
        if twin is not None:
            text = render(twin, context, rel + suffix)
        else:
            text = reader(rel)
            if text is not None and not suffix:
                text = render(text, context, rel)
        if text is None:
            configs[rel] = None
            continue
        try:
            configs[rel] = json.loads(text)
        except ValueError as exc:
            raise AuditError("%s renders to invalid JSON: %s" % (rel, exc)) from exc
    return configs, sorted(notes)


# --- what the update did to each config key --------------------------------

_ABSENT = object()


def _change(key, kind, base, ours, predicted):
    change = {"key": key, "kind": kind}
    for name, value in (("base", base), ("ours", ours), ("predicted", predicted)):
        if value is not _ABSENT:
            change[name] = copy.deepcopy(value)
    return change


def classify(base, ours, predicted, _prefix=""):
    """[change], sorted by key: what the update did to each key of one JSON
    object, read from the template's render at the project's `_commit`
    (*base*), DEST's file (*ours*) and the file the update leaves
    (*predicted*). Pure; inputs are not mutated. The audit merges nothing:
    copier did, and this names the outcome.

    Objects recurse with dotted keys; a list and every scalar is one value;
    `_`-prefixed keys (commentary) are not reported, nor is a key the update
    leaves as the project has it. Kinds: `arrives` (absent from ours, present
    after the update), `removed-upstream` (present in ours, gone after it),
    `updates` (the project left it as rendered and the update changes it),
    `merges` (the project edited it and the update leaves a value that is
    neither the project's nor the base's: both edits are in it). A value the
    update returns to the base over the project's edit is reported as an
    update, never dropped. With *base* None (the project's `_commit` is
    unknown) nothing is known about edits: a key the template lacks may be the
    project's own, so only arrivals and updates are reported."""
    changes = []
    for k in sorted(set(ours) | set(predicted)):
        if k.startswith("_"):
            continue
        key = _prefix + k
        o = ours.get(k, _ABSENT)
        p = predicted.get(k, _ABSENT)
        b = base.get(k, _ABSENT) if isinstance(base, dict) else _ABSENT
        if o is _ABSENT:
            changes.append(_change(key, "arrives", b, o, p))
            continue
        if p is _ABSENT:
            if base is not None:
                changes.append(_change(key, "removed-upstream", b, o, p))
            continue
        if isinstance(o, dict) and isinstance(p, dict):
            # No base: nothing known. A base without this object: it is new.
            sub = None if base is None else (b if isinstance(b, dict) else {})
            changes.extend(classify(sub, o, p, key + "."))
            continue
        if p == o:
            continue
        if base is not None and o != b and p != b:
            changes.append(_change(key, "merges", b, o, p))
        else:
            changes.append(_change(key, "updates", b, o, p))
    return sorted(changes, key=lambda c: c["key"])


def _shown(value):
    """A value as the report shows it: canonical JSON, commentary keys dropped."""

    def strip(v):
        if isinstance(v, dict):
            return {k: strip(x) for k, x in v.items() if not k.startswith("_")}
        if isinstance(v, list):
            return [strip(x) for x in v]
        return v

    return _canonical(strip(value))


def _config_message(rel, change):
    key, kind = change["key"], change["kind"]
    if kind == "arrives":
        return "%s: `%s` will arrive with the update (template default: %s)" % (
            rel,
            key,
            _shown(change["predicted"]),
        )
    if kind == "updates":
        return "%s: `%s` will change with the update (template value: %s)" % (
            rel,
            key,
            _shown(change["predicted"]),
        )
    if kind == "merges":
        return (
            "%s: `%s` was edited by you and by the template; copier's merge keeps "
            "both edits (rendered at your base: %s; yours: %s; after the update: %s)"
            % (
                rel,
                key,
                _shown(change["base"]),
                _shown(change["ours"]),
                _shown(change["predicted"]),
            )
        )
    return "%s: `%s` is no longer in the template; the update removes it" % (
        rel,
        key,
    )


# --- refusal ----------------------------------------------------------------


def _load_dest(dest, yaml):
    """(answers, manifest) of a keel project at *dest*, or raise _Refusal naming
    every item that makes it not one."""
    problems = []
    answers = None
    path = os.path.join(dest, ANSWERS)
    if not os.path.isfile(path):
        problems.append("%s: missing" % ANSWERS)
    else:
        try:
            with open(path, encoding="utf-8") as fh:
                answers = yaml.safe_load(fh)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            problems.append("%s: unreadable (%s)" % (ANSWERS, exc))
        else:
            if not isinstance(answers, dict):
                problems.append("%s: not a mapping" % ANSWERS)
                answers = None
            else:
                # Copier writes every answer under a string key; `1: x` is not one.
                problems.extend(
                    "%s: key %r is not a string" % (ANSWERS, key)
                    for key in sorted(answers, key=repr)
                    if not isinstance(key, str)
                )
    for key in ("_src_path", "_commit"):
        value = (answers or {}).get(key)
        if value is not None and not isinstance(value, str):
            # `_commit: 0000000` unquoted is the int 0: copier writes a string.
            problems.append("%s: `%s` is not a string (%r)" % (ANSWERS, key, value))
        elif not value or not value.strip():
            problems.append("%s: `%s` missing or empty" % (ANSWERS, key))
    manifest = None
    path = os.path.join(dest, MANIFEST)
    try:
        with open(path, encoding="utf-8") as fh:
            manifest = json.load(fh)
    except FileNotFoundError:
        problems.append("%s: missing" % MANIFEST)
    except (OSError, ValueError) as exc:
        problems.append("%s: unreadable (%s)" % (MANIFEST, exc))
    else:
        if not isinstance(manifest, dict):
            problems.append("%s: not a JSON object" % MANIFEST)
    if problems:
        raise _Refusal(problems)
    return answers, manifest


class _Refusal(Exception):
    def __init__(self, problems):
        super().__init__("; ".join(problems))
        self.problems = problems


# --- origin -----------------------------------------------------------------


def _token(message):
    """The leading path-like token of a check message, trailing `/` dropped."""
    head = message.split(None, 1)[0] if message.strip() else ""
    head = head.split(":", 1)[0]
    return head.rstrip("/")


def origin_of(dest, message, base_sha, tree, predicted=None):
    """The evidence kind for a finding: what git at `_commit` says about the
    path the message names, and, for a path neither DEST nor the base has,
    whether the tree the update leaves under *predicted* has it
    (`template-new`). `unknown` without a base or a path, or when the path's
    bytes cannot be read."""
    if base_sha is None:
        return "unknown"
    token = _token(message)
    if not token or token.startswith(("/", "..")):
        return "unknown"
    full = os.path.join(dest, token)
    # copier renders a `.jinja` twin and never copies its plain sibling, so the
    # twin decides even when the template carries both (config/project.json).
    if tree.get(token + ".jinja") == "blob":
        return "template-rendered"
    kind = tree.get(token)
    if kind == "blob":
        if not os.path.isfile(full) or os.path.islink(full):
            return "template-edited"
        try:
            with open(full, "rb") as fh:
                ours = fh.read()
        except OSError:
            # check_structure has already reported the file as unreadable; with
            # its bytes unknown, so is whether the project edited it.
            return "unknown"
        same = ours == _blob(base_sha, token)
        return "template-unedited" if same else "template-edited"
    if kind is not None:
        return "unknown"  # a directory the template ships: no single owner
    if os.path.lexists(full):
        return "project"
    if predicted is not None and os.path.lexists(os.path.join(predicted, token)):
        return "template-new"
    return "unknown"


def _git_refusal(dest):
    """None when DEST is in a git work tree git will read, else the reason."""
    code, out, err = _git(dest, "rev-parse", "--is-inside-work-tree")
    if code is None:
        return "no git: git is not installed"
    if code == 0 and out.strip() == "true":
        return None
    first = (err.strip().splitlines() or ["not a work tree"])[0]
    if "not a git repository" in first or code == 0:
        return "no git work tree at DEST"
    return "git refused DEST: %s" % first


def update_refusal(dest):
    """None when a real `copier update` of DEST would start, else
    (message, paths). copier updates only a project in git with nothing
    uncommitted, tracked or not (its own `git status --porcelain`), while the
    scratch copy is committed whatever DEST's state: a prediction that does not
    say so previews an update the project cannot yet run."""
    refusal = _git_refusal(dest)
    if refusal is not None:
        return (
            "DEST is not a git work tree (%s): `copier update` updates only a "
            "git-tracked project; the prediction judges a committed copy" % refusal,
            [],
        )
    modified = review_docs.modified_paths(dest)
    code, out, err = _git(dest, "ls-files", "--others", "--exclude-standard", "-z")
    if modified is None or code != 0:
        raise AuditError("git refused to list DEST's uncommitted changes: %s" % err)
    paths = sorted(modified | {p for p in out.split("\0") if p})
    if not paths:
        return None
    return (
        "DEST is dirty (%d uncommitted path(s)): `copier update` refuses to run "
        "until they are committed or stashed; the prediction judges them as if "
        "committed" % len(paths),
        paths,
    )


# --- the predicted tree: a real update of a scratch copy ---------------------

# Everything the prediction learned; *root* is valid only inside the scratch
# directory's lifetime. *before* is check_structure's findings on the copy
# before the update; *afters* one list of findings per resolution of the tree
# the update leaves (one when nothing conflicts, else one per RESOLUTIONS
# side); *conflicts* the paths copier left unmerged; *configs* {JSON config
# relpath: parsed, None or _UNUSABLE}.
Prediction = namedtuple("Prediction", "root before afters conflicts configs")

# copier's own conflict markers: `git merge-file -L "before updating" -L "last
# update" -L "after updating"` in copier's update (copier/_main.py), the lines
# copier itself reads to call a file conflicted. The base section appears only
# under a diff3 conflict style.
_MARK_PROJECT = b"<<<<<<< before updating"
_MARK_BASE = b"||||||| last update"
_MARK_SPLIT = b"======="
_MARK_TEMPLATE = b">>>>>>> after updating"
# The two ways the tree the update leaves is judged when a file conflicts:
# every conflict hunk as the project had it, and as the template brings it.
RESOLUTIONS = ("project", "template")

# The git every child in the scratch tree runs under: no user or system config
# of the machine, no hook (a commit in the copy must run nothing of DEST's or
# the user's), no excludes file, no fsmonitor, no background gc.
_SCRATCH_GITCONFIG = (
    "[user]\n\tname = keel audit\n\temail = keel-audit@example.invalid\n"
    "[init]\n\tdefaultBranch = main\n"
    "[commit]\n\tgpgsign = false\n"
    "[tag]\n\tgpgSign = false\n"
    "[core]\n\thooksPath = %s\n\texcludesFile = %s\n\tfsmonitor = false\n"
    "[gc]\n\tauto = 0\n"
) % (os.devnull, os.devnull)


def _mask(text, scratch):
    return text.replace(scratch, SCRATCH_MASK)


def _scratch_env(scratch, today):
    """What every child the prediction runs gets on top of the allowlist
    (`extra=` of `child_env.build_child_env`): the hermetic git above, commit
    dates and SOURCE_DATE_EPOCH pinned to *today* at midnight UTC (two runs on
    one day commit the same trees), and copier's settings, cache and temporary
    files inside the scratch tree."""
    gitconfig = os.path.join(scratch, "gitconfig")
    settings = os.path.join(scratch, "copier-settings.yml")
    tmp = os.path.join(scratch, "tmp")
    os.mkdir(tmp)
    with open(gitconfig, "w", encoding="utf-8") as fh:
        fh.write(_SCRATCH_GITCONFIG)
    with open(settings, "w", encoding="utf-8") as fh:
        fh.write("{}\n")
    epoch = calendar.timegm(today.timetuple())
    date = "@%d +0000" % epoch
    return {
        "GIT_CONFIG_GLOBAL": gitconfig,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_DATE": date,
        "GIT_COMMITTER_DATE": date,
        "SOURCE_DATE_EPOCH": str(epoch),
        "COPIER_SETTINGS_PATH": settings,
        "XDG_CACHE_HOME": os.path.join(scratch, "cache"),
        "TMPDIR": tmp,
        "TMP": tmp,
        "TEMP": tmp,
    }


def _child(argv, cwd, extra, scratch, what):
    """stdout of *argv* run in the scratch tree, or AuditError naming *what*
    with the tail of its output, the scratch path masked."""
    proc = subprocess.run(
        argv,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        env=child_env.build_child_env(extra=extra),
    )
    if proc.returncode != 0:
        lines = [ln for ln in (proc.stderr or proc.stdout).splitlines() if ln.strip()]
        raise AuditError(
            _mask(
                "%s failed (exit %d): %s"
                % (what, proc.returncode, " | ".join(lines[-8:]) or "no output"),
                scratch,
            )
        )
    return proc.stdout


def _snapshot_template(scratch, extra, not_checked):
    """A clone of TEMPLATE with its uncommitted state committed on top: what
    copier would render from the checkout, without copier's own handling of a
    dirty local template, which runs a plain `git status` there and rewrites
    the checkout's index. TEMPLATE is only read: the clone, the judge's
    read-only status, and `ls-files`."""
    snap = os.path.join(scratch, "template")
    _child(
        ["git", "clone", "-q", "--no-hardlinks", TEMPLATE, snap],
        scratch,
        extra,
        scratch,
        "git clone of the template checkout",
    )
    dirty = review_docs.modified_paths(TEMPLATE)
    if dirty is None:
        raise AuditError("git refused to list the template checkout's changes")
    code, out, err = _git(TEMPLATE, "ls-files", "--others", "--exclude-standard", "-z")
    if code != 0:
        raise AuditError("cannot list the template's untracked files: %s" % err.strip())
    untracked = {p for p in out.split("\0") if p and not p.endswith("/")}
    for rel in sorted(dirty | untracked):
        src, dst = os.path.join(TEMPLATE, rel), os.path.join(snap, rel)
        if rel in untracked and os.path.islink(src):
            # A link the checkout never tracked is a local convenience, not
            # template content (keel's own root carries one to a sibling tree).
            not_checked.append(
                {
                    "item": rel,
                    "reason": "an untracked symlink in the template checkout: not "
                    "in the snapshot the update renders from (`git add` it to "
                    "include it)",
                }
            )
            continue
        if os.path.lexists(dst) and not os.path.isdir(dst):
            os.remove(dst)
        if os.path.islink(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.symlink(os.readlink(src), dst)
        elif os.path.isfile(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
    if dirty or untracked:
        _child(["git", "add", "-A"], snap, extra, scratch, "git add in the snapshot")
        _child(
            ["git", "commit", "-q", "--allow-empty", "-m", "audit: checkout state"],
            snap,
            extra,
            scratch,
            "git commit in the snapshot",
        )
    return snap


def _dest_paths(dest):
    """DEST's relpaths the copy takes: what git lists (tracked and untracked,
    ignored files left out) in a work tree, else what check_structure walks;
    the answers file always."""
    if _git_refusal(dest) is None:
        code, out, err = _git(dest, "ls-files", "-c", "-o", "--exclude-standard", "-z")
        if code != 0:
            raise AuditError("git refused to list DEST's files: %s" % err.strip())
        rels = {p for p in out.split("\0") if p}
    else:
        rels = set()
        for dirpath, dirnames, filenames in check_structure.walk(dest):
            links = [d for d in dirnames if os.path.islink(os.path.join(dirpath, d))]
            for name in filenames + links:
                rels.add(os.path.relpath(os.path.join(dirpath, name), dest))
    if os.path.lexists(os.path.join(dest, ANSWERS)):
        rels.add(ANSWERS)
    return sorted(rels)


def _copy_entry(dest, rel, copy_root, not_checked):
    """Copy DEST's *rel* into *copy_root*, naming in *not_checked* what it
    leaves out.
    A symlink stays a link only when it resolves inside DEST (an absolute
    target made relative, so it points into the copy): copier writes through
    a link, so one leaving DEST is copied as its target's bytes, or not at all
    when it dangles or names a directory."""
    if rel.endswith("/"):
        not_checked.append(
            {"item": rel.rstrip("/"), "reason": "a nested git repository: not copied"}
        )
        return
    src, dst = os.path.join(dest, rel), os.path.join(copy_root, rel)
    if not os.path.lexists(src):
        return  # tracked, deleted in the working tree: DEST lacks it
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.islink(src):
        target = os.readlink(src)
        resolved = os.path.realpath(src)
        if resolved == dest or resolved.startswith(dest + os.sep):
            if os.path.isabs(target):
                target = os.path.relpath(
                    os.path.relpath(resolved, dest), os.path.dirname(rel) or "."
                )
            os.symlink(target, dst)
            return
        if os.path.isfile(resolved):
            shutil.copyfile(resolved, dst)
            reason = (
                "a symlink to a file outside DEST: the copy holds the target's "
                "bytes, so the update cannot write through it"
            )
        else:
            reason = (
                "a symlink outside DEST to a directory or to nothing: not copied, "
                "so neither run judges it"
            )
        not_checked.append({"item": rel, "reason": reason})
        return
    if os.path.isdir(src):
        not_checked.append(
            {"item": rel, "reason": "a submodule: not copied, so neither run judges it"}
        )
        return
    if not os.path.isfile(src):
        return
    try:
        shutil.copy2(src, dst)
    except OSError as exc:
        not_checked.append(
            {
                "item": rel,
                "reason": "unreadable (%s): not copied, so neither run judges it"
                % exc.strerror,
            }
        )


def _leaks(found, scratch):
    for _letter, _tier, message in found:
        if scratch in message:
            raise AuditError(
                "a check message names the scratch tree, so the report would "
                "differ every run: %s" % _mask(message, scratch)
            )


def resolve_conflict(data, side):
    """*data*, the bytes of a file copier left conflicted, with every conflict
    hunk resolved one way: *side* "project" keeps the lines before updating,
    "template" the lines after updating; lines outside a hunk (copier's clean
    merge) are kept either way. Raises ValueError when the markers do not nest
    as copier writes them."""
    if side not in RESOLUTIONS:
        raise ValueError("unknown side %r" % side)
    out = []
    section = None  # None outside a hunk, else "project", "base" or "template"
    for line in data.splitlines(True):
        mark = line.rstrip()
        if section is None:
            if mark == _MARK_PROJECT:
                section = "project"
            elif mark in (_MARK_BASE, _MARK_TEMPLATE):
                raise ValueError("%r outside a conflict hunk" % mark.decode())
            else:
                out.append(line)
            continue
        if mark == _MARK_BASE and section == "project":
            section = "base"
        elif mark == _MARK_SPLIT and section in ("project", "base"):
            section = "template"
        elif mark == _MARK_TEMPLATE and section == "template":
            section = None
        elif mark == _MARK_PROJECT:
            raise ValueError("a conflict hunk opens inside another")
        elif section == side:
            out.append(line)
    if section is not None:
        raise ValueError("a conflict hunk is never closed")
    return b"".join(out)


def _judge_resolutions(root, conflicts):
    """check_structure's findings on *root* once per RESOLUTIONS side, each
    conflicted file rewritten with its hunks that side's way, so no check
    parses a marker and every file is the one tree the update leaves. A
    conflicted path the update removed is absent on both sides."""
    held = {}
    for rel in conflicts:
        path = os.path.join(root, rel)
        if os.path.isfile(path) and not os.path.islink(path):
            with open(path, "rb") as fh:
                held[rel] = fh.read()
    afters = []
    for side in RESOLUTIONS:
        for rel in sorted(held):
            try:
                body = resolve_conflict(held[rel], side)
            except ValueError as exc:
                raise AuditError(
                    "%s: copier's conflict markers do not read as copier writes "
                    "them: %s" % (rel, exc)
                ) from None
            with open(os.path.join(root, rel), "wb") as fh:
                fh.write(body)
        afters.append(check_structure.run_checks(root))
    return afters


def predict(dest, yaml, scratch, today, not_checked):
    """The Prediction for DEST, built under *scratch* (a realpath the caller
    owns and removes): the snapshot, the copy committed in its own repository,
    the checks before, `copier update` as a child, the checks after (once per
    RESOLUTIONS side when a file conflicts). Appends what it could not copy to
    *not_checked*. Raises AuditError when a child fails."""
    extra = _scratch_env(scratch, today)
    snap = _snapshot_template(scratch, extra, not_checked)
    root = os.path.join(scratch, "project")
    os.mkdir(root)
    for rel in _dest_paths(dest):
        _copy_entry(dest, rel, root, not_checked)
    answers_path = os.path.join(root, ANSWERS)
    with open(answers_path, encoding="utf-8") as fh:
        answers = yaml.safe_load(fh)
    answers["_src_path"] = snap
    os.remove(answers_path)  # a link inside DEST: write the copy, not its target
    with open(answers_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(answers, fh, sort_keys=True, default_flow_style=False)
    for argv in (
        ["git", "init", "-q"],
        ["git", "add", "-A"],
        ["git", "commit", "-q", "--allow-empty", "-m", "audit: DEST as it stands"],
    ):
        _child(argv, root, extra, scratch, "git %s in the copy" % argv[1])

    before = check_structure.run_checks(root)
    _child(
        [sys.executable, "-m", "copier", "update", "--trust", "--defaults"]
        + ["--skip-answered", "--quiet", "--vcs-ref", "HEAD", "--conflict", "inline"]
        + [root],
        scratch,
        extra,
        scratch,
        "copier update of %s" % root,
    )
    out = _child(
        ["git", "ls-files", "-u", "-z"], root, extra, scratch, "git ls-files -u"
    )
    conflicts = sorted(
        {entry.split("\t", 1)[1] for entry in out.split("\0") if "\t" in entry}
    )
    # Never a conflicted file put back to DEST's bytes beside the update's
    # other files: a check that reads it and reports against another file
    # (W reads the Makefile, reports the manifest) would judge a mix again.
    if conflicts:
        afters = _judge_resolutions(root, conflicts)
    else:
        afters = [check_structure.run_checks(root)]
    for found in [before] + afters:
        _leaks(found, scratch)
    configs = {
        rel.replace(os.sep, "/"): _read_dest_json(root, rel)
        for rel in check_structure.JSON_CONFIGS
    }
    return Prediction(root, before, afters, conflicts, configs)


# --- the audit --------------------------------------------------------------


def _config_changes(rel, base, ours, predicted):
    """The config-group entries for one JSON config: a whole-file arrival when
    DEST lacks it, else one entry per key `classify` reports."""
    if ours is None:
        return [
            {
                "tier": "info",
                "kind": "arrives",
                "key": "",
                "file": rel,
                "message": "%s: the whole file will arrive with the update" % rel,
            }
        ]
    return [
        {
            "tier": "info",
            "kind": change["kind"],
            "key": change["key"],
            "file": rel,
            "message": _config_message(rel, change),
        }
        for change in classify(base, ours, predicted)
    ]


def _judged_as_it_stands(dest, manifest, theirs, commit, groups, not_checked):
    """No base: copier cannot update a project whose `_commit` this checkout
    lacks, so nothing is predicted. DEST is judged as it stands (origins
    unknown) and the config group names only what the template would add or
    change, read from this checkout's render."""
    not_checked.append(
        {
            "item": "no base: the update cannot be predicted",
            "reason": "_commit %s does not resolve in the template checkout, so "
            "DEST is judged as it stands, every origin is unknown, and the config "
            "group compares DEST with this checkout's render (only arrivals and "
            "updates)" % commit,
        }
    )
    for letter, tier, message in check_structure.run_checks(dest):
        groups[letter].append({"tier": tier, "message": message, "origin": "unknown"})
    for rel in sorted(theirs):
        t = theirs[rel]
        if not isinstance(t, dict):
            continue  # the template has no such file: DEST's stands as it is
        ours = manifest if rel == MANIFEST else _read_dest_json(dest, rel)
        if ours is _UNUSABLE:
            continue  # check_structure reports the unreadable file itself
        groups["config"].extend(_config_changes(rel, None, ours, t))


def _judged_after_update(
    dest, yaml, manifest, base_sha, tree, answers, today, groups, not_checked
):
    """The update predicted in a scratch copy: letter findings after it are
    owed, findings only before it are resolved by it, a conflicted path is
    reported and its findings are not judged, nor is a finding that only one
    resolution of the conflicts has."""
    bases, _notes = render_configs(git_reader(base_sha), answers)
    refused = update_refusal(dest)
    if refused is not None:
        groups["config"].append(
            {
                "tier": "warning",
                "kind": "update-refused",
                "key": "",
                "paths": refused[1],
                "message": refused[0],
            }
        )
    with tempfile.TemporaryDirectory(prefix=SCRATCH_PREFIX) as tmp:
        scratch = os.path.realpath(tmp)
        try:
            pred = predict(dest, yaml, scratch, today, not_checked)
        except OSError as exc:
            raise AuditError(
                _mask("building the scratch copy failed: %s" % exc, scratch)
            ) from None
        conflicts = set(pred.conflicts)

        def finding(tier, message):
            f = {
                "tier": tier,
                "message": message,
                "origin": origin_of(dest, message, base_sha, tree, pred.root),
            }
            if _token(message) in conflicts:
                f["unjudged"] = UNJUDGED_CONFLICT
            return f

        # A finding every resolution has is the update's whatever the project
        # chooses; one only some have depends on that choice, so is not judged.
        common = set(pred.afters[0]).intersection(*pred.afters[1:])
        after = set().union(*pred.afters)
        listed = set()
        for found in pred.afters:
            for item in found:
                if item in listed and found is not pred.afters[0]:
                    continue
                listed.add(item)
                letter, tier, message = item
                f = finding(tier, message)
                if item not in common:
                    f["unjudged"] = UNJUDGED_CONFLICT
                groups[letter].append(f)
        for letter, tier, message in sorted(set(pred.before) - after):
            f = finding(tier, message)
            if "unjudged" not in f:
                f["resolved_by"] = UPDATE_RESOLVES
            groups[letter].append(f)

        for rel in pred.conflicts:
            groups["conflict"].append(
                {
                    "tier": "warning",
                    "path": rel,
                    "message": "%s: copier update leaves a conflict here (the "
                    "project and the template changed the same lines); resolve "
                    "it after the update; findings in this file, and any that "
                    "depend on how it is resolved, are not judged" % rel,
                }
            )
        for rel in sorted(pred.configs):
            predicted = pred.configs[rel]
            ours = manifest if rel == MANIFEST else _read_dest_json(dest, rel)
            if ours is _UNUSABLE or not isinstance(predicted, dict):
                continue  # unreadable on a side: check_structure reports it
            if rel in conflicts:
                groups["config"].append(
                    {
                        "tier": "info",
                        "kind": "conflict",
                        "key": "",
                        "file": rel,
                        "message": "%s: copier update leaves a conflict here; its "
                        "keys are not classified" % rel,
                    }
                )
                continue
            groups["config"].extend(
                _config_changes(rel, bases.get(rel) or {}, ours, predicted)
            )
        groups["retired"].extend(_retired(dest, base_sha, tree, pred.root))


def _dest_bytes(dest, rel):
    """DEST's *rel* as git would store it: a symlink's target, a file's bytes,
    or None when it is neither."""
    full = os.path.join(dest, rel)
    if os.path.islink(full):
        return os.fsencode(os.readlink(full))
    if not os.path.isfile(full):
        return None
    with open(full, "rb") as fh:
        return fh.read()


def _retired(dest, base_sha, tree, after_root):
    """A finding per DEST file the predicted update deletes that the project
    edited, judged by the guard migration's own rule
    (keep_edited_retired.is_edited) against the template's blob at `_commit`.
    The prediction runs the same update, guard included, so a file still
    deleted after it is one the real update deletes: a later `rm` migration
    removed it, or copier ran no migration."""
    found = []
    for rel in _dest_paths(dest):
        if rel == ANSWERS or os.path.lexists(os.path.join(after_root, rel)):
            continue
        ours = _dest_bytes(dest, rel)
        if ours is None:
            continue
        if tree.get(rel) == "blob":
            if keep_edited_retired.is_edited(ours, _blob(base_sha, rel)):
                found.append(
                    {
                        "tier": "error",
                        "path": rel,
                        "message": "the update deletes %s, which the project "
                        "edited" % rel,
                    }
                )
        elif tree.get(rel + check_structure._TWIN_SUFFIX) == "blob":
            found.append(
                {
                    "tier": "warning",
                    "path": rel,
                    "message": "the update deletes %s, which the template renders "
                    "from %s%s, so whether the project edited it is not judged"
                    % (rel, rel, check_structure._TWIN_SUFFIX),
                }
            )
    return found


def audit(dest, today):
    """The report for the keel project at *dest* (a realpath), as a dict.
    Raises _Refusal or AuditError."""
    yaml, _jinja2 = _extras()
    answers, manifest = _load_dest(dest, yaml)
    not_checked = [{"item": item, "reason": reason} for item, reason in NOT_CHECKED]
    groups = {g: [] for g in GROUPS}

    src = answers["_src_path"]
    if os.path.realpath(os.path.expanduser(src)) != os.path.realpath(TEMPLATE):
        groups["config"].append(
            {
                "tier": "info",
                "kind": "src-path",
                "message": "DEST's _src_path is %s, not this checkout; judged by this "
                "checkout's gates" % src,
            }
        )

    theirs, notes = render_configs(worktree_reader(TEMPLATE), answers)
    for note in notes:
        kind = "new-question" if note.startswith("new question") else "dropped-answer"
        groups["config"].append({"tier": "info", "kind": kind, "message": note})

    commit = answers["_commit"]
    base_sha = resolve_commit(commit)
    tree = {}
    if base_sha is None:
        _judged_as_it_stands(dest, manifest, theirs, commit, groups, not_checked)
    else:
        tree = _tree_at(base_sha)
        _judged_after_update(
            dest, yaml, manifest, base_sha, tree, answers, today, groups, not_checked
        )

    refusal = _git_refusal(dest)
    if refusal is not None:
        not_checked.extend(
            {"item": item, "reason": refusal} for item in ("freshness", "restamp")
        )
    else:
        _freshness(dest, today, base_sha, tree, groups, not_checked)

    files_seen = sum(len(files) for _d, _s, files in check_structure.walk(dest))
    for g in GROUPS:
        groups[g].sort(key=lambda f: (TIERS.index(f["tier"]), f["message"]))
    counts = {}
    for g in GROUPS:
        counts[g] = {
            tier: sum(1 for f in groups[g] if f["tier"] == tier) for tier in TIERS
        }
        counts[g]["resolved_by_update"] = sum(
            1 for f in groups[g] if f["tier"] == "error" and "resolved_by" in f
        )
        counts[g]["unjudged"] = sum(1 for f in groups[g] if "unjudged" in f)
    # Owed: what the project must fix itself once the update has landed. An
    # error the update resolves, or one in a file the update leaves
    # conflicted, is reported, never counted toward the exit.
    resolved = sum(counts[g]["resolved_by_update"] for g in LETTERS)
    errors = sum(
        1
        for g in LETTERS
        for f in groups[g]
        if f["tier"] == "error" and "resolved_by" not in f and "unjudged" not in f
    ) + sum(1 for f in groups["retired"] if f["tier"] == "error")
    warnings = sum(
        1
        for g in GROUPS
        for f in groups[g]
        if f["tier"] == "warning"
        and not (g in LETTERS and ("resolved_by" in f or "unjudged" in f))
    )
    code = 1 if errors or files_seen == 0 else 0
    return {
        "dest": dest,
        "template": {"revision": template_revision()},
        "base": {"commit": commit, "resolved": base_sha},
        "today": today.isoformat(),
        "groups": groups,
        "not_checked": sorted(not_checked, key=lambda i: (i["item"], i["reason"])),
        "summary": {
            "checks_run": list(LETTERS),
            "files_seen": files_seen,
            "counts": counts,
            "errors": errors,
            "resolved_by_update": resolved,
            "warnings": warnings,
            "conflicts": len(groups["conflict"]),
        },
        "exit": code,
    }


_UNUSABLE = object()


def _read_dest_json(dest, rel):
    """DEST's parsed config at *rel*, None when absent, _UNUSABLE when it cannot
    be read or is not an object."""
    path = os.path.join(dest, rel)
    if not os.path.lexists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return _UNUSABLE
    return data if isinstance(data, dict) else _UNUSABLE


def _freshness(dest, today, base_sha, tree, groups, not_checked):
    """The freshness judge's findings and the restamp writer's pending list,
    both of which the update's last migration (restamp_docs) clears."""
    records = review_docs.collect(dest)
    if records is None:
        not_checked.extend(
            {"item": item, "reason": "git refused to list DEST's documents"}
            for item in ("freshness", "restamp")
        )
        return
    for finding in review_docs.stale_findings(records, today.isoformat()):
        message = "%s: %s" % (finding["path"], finding["reason"])
        groups["freshness"].append(
            {
                "tier": "warning",
                "path": finding["path"],
                "message": message,
                "expected": finding["expected"],
                "updated": finding["updated"],
                "resolved_by": FRESHNESS_RESOLVED_BY,
                "origin": origin_of(dest, message, base_sha, tree),
            }
        )
    errs = []
    try:
        rows = restamp_docs.pending(dest, today, errs)
    except restamp_docs.RestampError as exc:
        not_checked.append(
            {
                "item": "restamp",
                "reason": "git gave a date restamp_docs refuses: %s" % exc,
            }
        )
        return
    for path, current, target in rows:
        groups["restamp"].append(
            {
                "tier": "info",
                "path": path,
                "current": current,
                "target": target,
                "message": "%s: `updated: %s` -> `%s`; the update's last migration "
                "(restamp_docs) will rewrite this stamp" % (path, current, target),
            }
        )
    for path, reason in errs:
        groups["restamp"].append(
            {
                "tier": "warning",
                "path": path,
                "message": "%s: %s" % (path, reason),
            }
        )


# --- output -----------------------------------------------------------------


def render_json(report):
    return json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def render_text(report):
    lines = [
        "audit-project: %s" % report["dest"],
        "template: %s" % report["template"]["revision"],
        "base: %s (%s)"
        % (
            report["base"]["commit"],
            report["base"]["resolved"] or "does not resolve here",
        ),
        "today: %s" % report["today"],
        "",
    ]
    counts = report["summary"]["counts"]
    for g in GROUPS:
        c = counts[g]
        resolved = (
            " (%d resolved by the update)" % c["resolved_by_update"]
            if c["resolved_by_update"]
            else ""
        )
        unjudged = (
            " (%d not judged: %s)" % (c["unjudged"], UNJUDGED_CONFLICT)
            if c["unjudged"]
            else ""
        )
        lines.append(
            "[%s] %d error(s)%s%s, %d warning(s), %d info"
            % (g, c["error"], resolved, unjudged, c["warning"], c["info"])
        )
        for f in report["groups"][g]:
            origin = "[%s] " % f["origin"] if "origin" in f else ""
            lines.append("  %-8s %s%s" % (f["tier"].upper(), origin, f["message"]))
    lines.append("")
    lines.append("not checked:")
    lines.extend("  - %s: %s" % (i["item"], i["reason"]) for i in report["not_checked"])
    s = report["summary"]
    lines.append("")
    lines.append(
        "audit-project: %d error(s) owed, %d resolved by the update, %d warning(s), "
        "%d conflicted file(s) not judged, over %d file(s); checks %s..%s"
        % (
            s["errors"],
            s["resolved_by_update"],
            s["warnings"],
            s["conflicts"],
            s["files_seen"],
            LETTERS[0],
            LETTERS[-1],
        )
    )
    lines.append("exit: %d" % report["exit"])
    return "\n".join(lines) + "\n"


_HELP = """\
Report what DEST, another keel-generated project, would fail under this
template's CURRENT gates once `copier update` has landed.

The audit judges one tree, the one the update leaves. It runs a real
`copier update` on a scratch copy of DEST (a temporary directory removed on
exit) against a snapshot of this checkout, and runs check_structure A..Y on
the copy before and after. DEST is never written, nor DEST/.git, nor this
checkout; it runs none of DEST's code in this process.

An error after the update is owed. An error only before it is resolved by
the update. A file copier leaves conflicted is listed in the conflict group,
and its findings are not judged; the tree is then checked with every conflict
hunk the project's way and again the template's way, and a finding only one
of the two has is not judged either. The config group names what the update
does to each key of DEST's JSON configs, and warns when the real update would
refuse DEST (outside git, or uncommitted changes). The doc-freshness judge and the restamp
writer's pending list are read from DEST.

The update's own tasks and migrations run in the scratch copy: keel's run the
project's restamp step there, as the project's own update would.

Without a base (DEST's _commit does not resolve here) nothing is predicted:
DEST is judged as it stands, and the not-checked section says so.

Exit: 0 no owed letter error; 1 one is owed (or no file was seen); 2 usage
error, DEST is not a keel project, a template render error, a failed copier
update, or a missing extra.
"""


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="audit_project.py",
        description=_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "dest", metavar="DEST", help="the keel project to audit (read only)"
    )
    ap.add_argument(
        "--json", action="store_true", help="canonical JSON (sort_keys) on stdout"
    )
    ap.add_argument(
        "--today",
        metavar="YYYY-MM-DD",
        help="the date freshness calls today (default: SOURCE_DATE_EPOCH, else the clock)",
    )
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)

    try:
        _extras()
    except ImportError as exc:
        print("audit_project: %s: %s" % (EXTRA_HINT, exc), file=sys.stderr)
        return 2
    try:
        today = review_docs.resolve_today(args.today, os.environ)
    except review_docs.DateSourceError as exc:
        print("audit_project: %s" % exc, file=sys.stderr)
        return 2

    dest = os.path.realpath(args.dest)
    if not os.path.isdir(dest):
        print("audit_project: DEST %s is not a directory" % args.dest, file=sys.stderr)
        return 2
    if dest == os.path.realpath(TEMPLATE):
        print(
            "audit_project: DEST %s is the template itself; audit a project "
            "generated from it" % args.dest,
            file=sys.stderr,
        )
        return 2
    try:
        report = audit(dest, today)
    except _Refusal as exc:
        print("audit_project: %s is not a keel project:" % args.dest, file=sys.stderr)
        for problem in exc.problems:
            print("  - %s" % problem, file=sys.stderr)
        return 2
    except AuditError as exc:
        print("audit_project: %s" % exc, file=sys.stderr)
        return 2
    sys.stdout.write(render_json(report) if args.json else render_text(report))
    return report["exit"]


if __name__ == "__main__":
    sys.exit(main())
