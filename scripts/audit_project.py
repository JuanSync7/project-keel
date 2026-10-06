#!/usr/bin/env python3
"""
title: audit_project — another keel project judged by this template's current gates
kind: script
layer: n/a
summary: Answers "what would this template's current gates say about DEST once `copier update` has landed?" without updating anything. It runs every check_structure letter (A..X) in-process against DEST's files through `run_checks`, with each JSON config the checks read replaced in memory by a key-level 3-way merge: base is the template at DEST's `_commit`, ours is DEST, theirs is this checkout, and base and theirs are rendered from the template's `.jinja` twin with DEST's answers plus copier.yml's derived defaults. It adds the freshness judge (scripts/jobs/review_docs.py) and the restamp writer's `pending` list (scripts/jobs/restamp_docs.py), both of which the update's last migration clears. Every finding reuses the check's own message and carries an origin evidence kind (template-unedited, template-edited, template-rendered, project, unknown) read from git at `_commit`; a file that cannot be read is `unknown`. A letter error in a template-unedited file is reported as resolved by the update (the update replaces the file) and is not owed. A "not checked" section names every proof it does not run. DEST is data: its files are read with open() and ast, its git with name-level commands built by `review_docs.git_argv` that write nothing and switch off fsmonitor, signature verification and every filter driver DEST's git config names, and none of its code, make targets or hooks run. Exit 0 when no letter error is owed, 1 when one is (or no file was seen), 2 on a usage error, a refusal (DEST is not a keel project, or its answers are malformed), a template render error (including answers of the wrong type) or a missing extra. Keel-only: excluded from generated projects (docs/design/downstream-feedback.md, slice 5); a generated project's `make audit-project` stub points back at the template checkout.
effect: read-only
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import subprocess
import sys

_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
for _dir in (_SCRIPTS, os.path.join(_SCRIPTS, "jobs")):
    if _dir not in sys.path:
        sys.path.insert(0, _dir)

import check_structure  # noqa: E402
import child_env  # noqa: E402
import restamp_docs  # noqa: E402
import review_docs  # noqa: E402

# The template checkout whose gates judge DEST: the one this file ships in.
TEMPLATE = os.path.dirname(_SCRIPTS)
ANSWERS = ".copier-answers.yml"
MANIFEST = "config/project.json"
LETTERS = tuple(letter for letter, _fn in check_structure.CHECKS)
GROUPS = LETTERS + ("config", "freshness", "restamp")
TIERS = ("error", "warning", "info")
FRESHNESS_RESOLVED_BY = "copier update (_migrations: restamp_docs)"
# A letter finding in a file whose bytes equal the template's at `_commit`: the
# update replaces that file with this checkout's, so the project owes nothing.
UPDATE_REPLACES = "copier update (replaces this file, which the project never edited)"
EXTRA_HINT = "needs the 'template' extra (pip install -e \".[template]\")"

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
        "template-shipped files other than the JSON configs",
        "the update 3-way merges them; the audit judges them as they stand "
        "today, and each finding's origin says whether the update replaces them",
    ),
    (
        "check_N's 5-line cap",
        "check_N prints at most 5 differing lines per twin; inert in a generated "
        "project, which declares no twins",
    ),
)


class AuditError(Exception):
    """A template input the audit cannot use (copier.yml, a twin, an answer it
    needs). Exit 2: a report built on a guessed config would mislead."""


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
    """(yaml, jinja2), imported only when needed: the template extra."""
    import jinja2
    import yaml

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


# --- the merge --------------------------------------------------------------


def _change(key, kind, ours, theirs, has_ours=True):
    change = {"key": key, "kind": kind, "theirs": copy.deepcopy(theirs)}
    if has_ours:
        change["ours"] = copy.deepcopy(ours)
    return change


_ABSENT = object()


def merge(base, ours, theirs, _prefix=""):
    """(merged, changes): the key-level 3-way merge of a JSON object, as
    copier's update leaves it -- the project's own edits (base -> ours) replayed
    onto the template's fresh render (theirs). Pure; inputs are not mutated.

    Objects recurse; lists and scalars are atomic. `_`-prefixed keys
    (commentary) keep ours. Kinds: `arrives` (new in the template, the project
    never had it), `updates` (the project left it as rendered, the template
    changed it), `conflict` (both changed it, kept as ours), `removed-upstream`
    (the template dropped a key the project never edited, so it goes). With
    *base* None (the project's `_commit` is unknown) nothing is known about
    edits, so only arrivals are reported and every present key keeps ours."""
    merged = {}
    changes = []
    keys = list(ours) + [k for k in theirs if k not in ours]
    for k in keys:
        key = _prefix + k
        o = ours.get(k, _ABSENT)
        t = theirs.get(k, _ABSENT)
        b = base.get(k, _ABSENT) if isinstance(base, dict) else _ABSENT
        if k.startswith("_"):
            merged[k] = copy.deepcopy(o if o is not _ABSENT else t)
            continue
        if o is _ABSENT:
            if b is _ABSENT:
                merged[k] = copy.deepcopy(t)
                changes.append(_change(key, "arrives", None, t, has_ours=False))
            elif b != t:
                changes.append(_change(key, "conflict", None, t, has_ours=False))
            continue  # deleted by the project; stays deleted
        if t is _ABSENT:
            if b is _ABSENT or base is None:
                merged[k] = copy.deepcopy(o)
            elif o == b:
                changes.append(_change(key, "removed-upstream", o, None))
            else:
                merged[k] = copy.deepcopy(o)
                changes.append(_change(key, "conflict", o, None))
            continue
        if isinstance(o, dict) and isinstance(t, dict):
            # No base: nothing known. A base without this object: it is new.
            sub = None if base is None else (b if isinstance(b, dict) else {})
            merged[k], inner = merge(sub, o, t, key + ".")
            changes.extend(inner)
            continue
        if o == t or base is None:
            merged[k] = copy.deepcopy(o)
        elif b is not _ABSENT and o == b:
            merged[k] = copy.deepcopy(t)
            changes.append(_change(key, "updates", o, t))
        elif b is not _ABSENT and t == b:
            merged[k] = copy.deepcopy(o)
        else:
            merged[k] = copy.deepcopy(o)
            changes.append(_change(key, "conflict", o, t))
    return merged, sorted(changes, key=lambda c: c["key"])


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
            _shown(change["theirs"]),
        )
    if kind == "updates":
        return "%s: `%s` will change with the update (template value: %s)" % (
            rel,
            key,
            _shown(change["theirs"]),
        )
    if kind == "removed-upstream":
        return "%s: `%s` is no longer in the template; the update removes it" % (
            rel,
            key,
        )
    return "%s: `%s` copier will show a conflict here (yours: %s, template: %s)" % (
        rel,
        key,
        _shown(change["ours"]) if "ours" in change else "deleted",
        _shown(change["theirs"]) if change["theirs"] is not None else "removed",
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


def origin_of(dest, message, base_sha, tree):
    """The evidence kind for a finding: what git at `_commit` says about the
    path the message names. `unknown` without a base or a path, or when the
    path's bytes cannot be read."""
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
    return "unknown"


# --- the audit --------------------------------------------------------------


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


def audit(dest, today):
    """The report for the keel project at *dest* (a realpath), as a dict.
    Raises _Refusal or AuditError."""
    yaml, _jinja2 = _extras()
    answers, manifest = _load_dest(dest, yaml)
    not_checked = [{"item": item, "reason": reason} for item, reason in NOT_CHECKED]
    config = []

    src = answers["_src_path"]
    if os.path.realpath(os.path.expanduser(src)) != os.path.realpath(TEMPLATE):
        config.append(
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
        config.append({"tier": "info", "kind": kind, "message": note})

    commit = answers["_commit"]
    base_sha = resolve_commit(commit)
    tree = {}
    bases = None
    if base_sha is not None:
        tree = _tree_at(base_sha)
        bases, _notes = render_configs(git_reader(base_sha), answers)
    else:
        not_checked.append(
            {
                "item": "three-way config merge",
                "reason": "base unavailable: _commit %s does not resolve in the "
                "template checkout, so the merge is 2-way (only arrivals are "
                "reported) and every origin is unknown" % commit,
            }
        )

    overrides = {}
    for rel in sorted(theirs):
        t = theirs[rel]
        if t is None or not isinstance(t, dict):
            continue  # the template has no such file: DEST's stands as it is
        ours = manifest if rel == MANIFEST else _read_dest_json(dest, rel)
        if ours is _UNUSABLE:
            continue  # check_structure reports the unreadable file itself
        if ours is None:
            overrides[rel] = t
            config.append(
                {
                    "tier": "info",
                    "kind": "arrives",
                    "key": "",
                    "file": rel,
                    "message": "%s: the whole file will arrive with the update" % rel,
                }
            )
            continue
        base = None if bases is None else (bases.get(rel) or {})
        merged, changes = merge(base, ours, t)
        overrides[rel] = merged
        config.extend(
            {
                "tier": "warning" if change["kind"] == "conflict" else "info",
                "kind": change["kind"],
                "key": change["key"],
                "file": rel,
                "message": _config_message(rel, change),
            }
            for change in changes
        )

    groups = {g: [] for g in GROUPS}
    for letter, tier, message in check_structure.run_checks(dest, overrides):
        finding = {
            "tier": tier,
            "message": message,
            "origin": origin_of(dest, message, base_sha, tree),
        }
        if finding["origin"] == "template-unedited":
            finding["resolved_by"] = UPDATE_REPLACES
        groups[letter].append(finding)
    groups["config"] = config

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
    # Owed: what the project must fix itself once the update has landed. An
    # error the update resolves is reported, never counted toward the exit.
    resolved = sum(counts[g]["resolved_by_update"] for g in LETTERS)
    errors = sum(counts[g]["error"] for g in LETTERS) - resolved
    warnings = sum(counts[g]["warning"] for g in GROUPS)
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
        lines.append(
            "[%s] %d error(s)%s, %d warning(s), %d info"
            % (g, c["error"], resolved, c["warning"], c["info"])
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
        "audit-project: %d error(s) owed, %d resolved by the update, %d warning(s) "
        "over %d file(s); checks %s..%s"
        % (
            s["errors"],
            s["resolved_by_update"],
            s["warnings"],
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

Runs check_structure A..X in-process against DEST's files, with DEST's
config/project.json (and config/practices.json) replaced in memory by the
3-way merge the update would produce; adds the doc-freshness judge and the
restamp writer's pending list. The audit writes nothing: not in DEST, not
in DEST/.git, not here.
It runs none of DEST's code: no import, no make target, no git hook.

An error in a file the project never edited (its bytes equal the template's
at DEST's `_commit`) is reported as resolved by the update, which replaces
that file; it is not owed and does not fail the exit.

Exit: 0 no owed letter error; 1 one is owed (or no file was seen); 2 usage
error, DEST is not a keel project, a template render error, or a missing extra.
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
