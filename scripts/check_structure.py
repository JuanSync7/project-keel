#!/usr/bin/env python3
"""
title: check_structure — the deterministic conventions gate
summary: Stdlib-only, 3.6-safe enforcement of CONVENTIONS.md — labeling, taxonomy, package boundaries, tool/agent governance, manifest and ruleset parity, twin parity, the machine-readable module contract, Makefile help parity, cross-reference resolution, check-catalogue parity, rosters, practice mechanisms, policy reachability, writer rerun declarations, make-target effect labels, child-process environments, and ADR number spaces (checks A-Y). Exit 1 on any error; warnings never fail the build.

check_structure.py - enforce the project conventions (see CONVENTIONS.md).

Checks:
  A. Frontmatter validity on README.md / AGENT.md / CLAUDE.md, docs/**,
     test-docs/** *.md, and agents/**/*.tool.md; a 'deprecated' or
     'superseded' document names its successor in superseded_by
  B. Closed taxonomy (ERR): every non-hidden top-level dir is in TAXONOMY or
     declared in config/project.json structure.extra_toplevel; a declaration
     exists and is not redundant; every top-level dir and every agents/<name>/
     has README.md + CLAUDE.md. An undeclared symlinked dir WARNs (no check
     reads through a link)
  C. Each src/ directory containing *.py is a package: __init__.py with __all__
  D. The __init__ boundary: no absolute import of another package's _private module
  E. Authored coverage (ERR): every __all__-exported symbol defined in-file
     has a docstring — the corpus's symbol summaries (WARN until ADR-K-0008)
  F. Tool specs governed (ERR) + accountability (WARN): tool/agent docs are
     owned; a spec's body is the seven CONVENTIONS §10 sections in order, its
     Side effects opens with the word for its tool_effect, and its When to use
     carries a `- NOT` bullet (the negative-scope line)
  G. Tool<->agent binding (ERR): tools.md <-> '## Used by' agree; tool_command invokes public_api
  H. Project facts in config/project.json agree with the tree (ERR); an
     undeclared leftover stack/transport dir WARNs (CONVENTIONS section 15).
     An optional 'runtimes' block is validated the same way (section 16)
  I. Agent-rules symlink (ERR): every CLAUDE.md is a symlink to its sibling
     AGENT.md, and every AGENT.md has that sibling (CONVENTIONS section 5)
  J. No third-party exception leaks across a library boundary (ERR): a raise of
     an exception TYPE imported from a foreign (non-local, non-stdlib) module
     (coding-practices; owned-exception-boundary in config/practices.json)
  K. Frozen-config gate (ERR): a class carrying the DECLARED marker
     (tokens.config_marker, "# practice: frozen-config") must be provably
     immutable (frozen dataclass / NamedTuple / attrs-frozen); else wrap or waive
     with "# practice-ok". Keyed on the marker, never a *Config name suffix (§18)
  L. Naked-tensor domain gate (WARN): only when the cuda profile is enabled
     (project.json practices.profiles), a function parameter annotated with a
     bare tensor base type (tokens.tensor_base_types) and no shape comment WARNs.
     Advisory heuristic (a token may name a local class) — never an error
  M. Ruleset parity (ERR): pyproject.toml must not silently loosen the lint/type
     policy declared in config/practices.json rulesets — every ruff extend_select
     family is selected, every mypy flag is enforced, no 'deferred' family is
     selected, no ruff per-file-ignore or per-module mypy relaxation is
     undeclared (config/practices.json rulesets; CONVENTIONS section 15)
  N. Template twin parity (ERR): every `*.jinja` twin is declared in
     config/project.json template.twins and matches its declared kind — a parity
     twin carries no stale non-templated line, a divergence twin still diverges,
     a generated one has no committed plain file. Render-free (no jinja2 here),
     so it bounds what it proves; the byte-exact rendered comparison lives in
     tests/integration. Silent in a generated project, which has no twins.
  O. Module header contract (ERR): every CODE_ROOTS module docstring carries
     explicit, non-empty title:/summary: lines — the grammar build_corpus
     reads. Without them the corpus falls back to filename/first-prose-line
     and labels the result 'authored'; an undocumented module is silently
     DROPPED from the corpus entirely (ADR-K-0008)
  P. Makefile help parity (ERR): every `## `-annotated target is one the
     `help` recipe's own grep pattern lists. The pattern is read out of the
     recipe, not restated here, so the check cannot agree with a wrong one;
     a recipe it cannot read is a stated WARN ('unverified'), never a pass
  Q. Cross-references resolve (ERR): every relative Markdown link (file,
     directory, #anchor) in prose names a real target, and every `§N`
     citation names a numbered section — of CONVENTIONS.md unless a document
     is named in front of it (`docs/guides/python-style.md §3`). Links inside
     fenced or inline code are illustrations and are not checked
  R. Check catalogue parity (ERR): docs/guides/deterministic-checks.md and
     the triggers agree on one membership — every catalogued script exists,
     an error-tier row is reachable from `make check-all`, a report row is
     run by some target, every script check-all reaches is catalogued, and
     the hooks table matches .pre-commit-config.yaml. A catalogue this
     check cannot read is a stated WARN
  S. Roster parity (ERR): a README declaring `## What ships here` names every
     member of its directory exactly once and nothing else (Member column),
     and every row's `Not for` cell is filled. Opt-in by the heading
  T. Practice mechanisms resolve (ERR): every config/practices.json entry's
     `enforced_by` names a check letter, script, test, make target or guide
     section that exists (a closed grammar; ruff/mypy codes are accepted)
  U. Policy documents are reachable (ERR): a practice enforced BY a document
     must sit within one hop of the root AGENT.md -- named there, or named in
     a document named there. A rule nobody reads is unenforceable in principle
  V. Writers declare their second run (ERR): a module that writes to the
     filesystem says `effect: writes` in its header and says what re-running
     it does (`rerun:` from a closed set); a `rerun: fixed-point` claim names
     a `rerun_proof:` in check_T's grammar. The detector resolves the base of
     each call (`os.replace`, never `str.replace`), so it under-reports rather
     than over-reports: a write behind subprocess is invisible to it, and a
     declared write it cannot see is a stated WARN ('unverified'), never a pass
  W. Make targets declare their effect (ERR): every `## `-annotated target
     opens its help with one bracketed label of EFFECT_LABELS words in
     canonical order (`local` alone), the same label on every rule that
     annotates the target; a composite covers what its prerequisites and
     `$(MAKE)` calls reach; a [write] target, or one whose name ends in a
     config/project.json `make_targets.write_shapes` suffix, opens its recipe
     with $(WRITE_GUARD) and no `-` prefix; the guard, read as make stores it,
     tests exactly the `unattended_vars` names, has no `-` prefix and exits 1;
     with an `area_dir`, each <area>.mk there is included, opens with one
     `##@ <area>` header and prefixes its public targets `<area>-`. A
     recursion it cannot resolve is a stated WARN ('unverified'), never a pass
  X. A child process gets an allowlisted environment (ERR): every
     subprocess/asyncio spawn in a .py at the root or under any top-level
     directory but tests/ passes env= built by child_env.build_child_env
     (scripts/child_env.py), directly or through a name bound only to that
     call and afterwards only read; a **kwargs spawn, an
     os.system/popen/exec*/spawn*, pty.spawn or subprocess.getoutput, a spawn
     API referenced without a call and a spawn name bound two ways in one
     scope are errors, as is a helper call whose arguments carry os.environ,
     directly or through a name within the module; and config/project.json
     `child_env` (with `credentialed_values` naming only a variable the
     allowlist copies) and `models.credential_env` are well-formed. Names resolve
     with Python's scope rules; a spawn through an unresolvable receiver
     (`self.runner(...)`, an alias of the module) or a parent value crossing a
     function parameter is under-reported, never over-reported
  Y. ADR number spaces (ERR): config/project.json `adr` is well-formed once
     the tree holds a `kind: adr` document; a project-space ADR is
     NNNN-<slug>.md without the template prefix, a template-space ADR is
     <prefix>NNNN-<slug>.md that `adr.template_adrs` lists (and every listed
     name is a file there), a `kind: adr` document lives directly in one of
     the two spaces, a number is unique within its space, and an ADR's kind
     is adr and its title begins ADR-<prefix?>NNNN: for its own file
     (CONVENTIONS §19). WARN when both spaces are empty

Exit 0 = clean, 1 = errors. Warnings never fail the build. Stdlib only; 3.6+.

`--root PATH` judges another tree with this checkout's checks (default: this
checkout). `run_checks(root)` is the same run as a function: it resets the
module state a run accumulates and returns (letter, tier, message) per finding
without printing. scripts/audit_project.py is its caller, on the scratch copy a
real `copier update` leaves.
"""

import argparse
import ast
import collections
import io
import json
import os
import posixpath
import re
import sys
import tokenize
from urllib.parse import unquote

# The allowlist's owner is scripts/child_env.py, beside this file; reading its
# policy from there keeps check_X and the helper one rule, not two.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import child_env  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The checkout this module ships in. ROOT is rebound by run_checks; main()'s
# default must stay the template whatever an earlier run judged.
_OWN_ROOT = ROOT

IGNORE_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".astro",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    ".eggs",
    "htmlcov",
}

KINDS = {
    "readme",
    "rules",
    "package",
    "module",
    "tests",
    "test-doc",
    "doc",
    "spec",
    "design",
    "adr",
    "config",
    "script",
    "agent",
    "mcp",
    "api",
    "wiki",
    "demo",
    "model",
    "eval",
    "container",
    "ops",
    "tool",  # agents/tools/*.tool.md adapters
}
TOOL_EFFECTS = {"read-only", "writes", "model-call"}
LAYERS = {"frontend", "backend", "shared", "app", "cross-cutting", "n/a"}
STATUSES = {
    "draft",
    "stable",
    "deprecated",
    "template",  # general lifecycle
    "proposed",
    "accepted",
    "superseded",  # ADR lifecycle
}
VISIBILITIES = {"public", "internal", "confidential", "restricted"}
REQUIRED_KEYS = (
    "title",
    "kind",
    "layer",
    "status",
    "summary",
    "id",
    "created",
    "updated",
    "visibility",
    "canonical",
)

TAXONOMY = [
    "src",
    "tests",
    "test-docs",
    "docs",
    "agents",
    "mcp",
    "api",
    "wiki",
    "scripts",
    "config",
    "demo",
    "containers",
    "evals",
    "ops",
    "models",
    "runtimes",
]
REQUIRED_TOPLEVEL = ["src", "tests", "docs"]
CODE_ROOTS = [
    "src",
    "tests",
    "api",
    "models",
    "mcp",
    "agents",
    "demo",
    "scripts",
    "runtimes",
]

# check_V's scope: the code that runs AS the product. CODE_ROOTS minus `tests`,
# because a test writes a scratch tree by design -- holding every `tmp_path`
# fixture to a writer's declaration would make the rule noise, and a rule that is
# noise is a rule authors learn to skip. A test that writes into the REPO is a
# different defect, and not this one's to catch.
WRITER_ROOTS = [r for r in CODE_ROOTS if r != "tests"]

errors = []
warnings = []
GOVERNED = []  # (relpath, kind, owner) for frontmatter docs check_A validated


def err(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


def rel(p):
    return os.path.relpath(p, ROOT)


def walk(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        yield dirpath, dirnames, filenames


# --- reading the files the gate is KEYED ON -----------------------------------
#
# ABSENT and UNREADABLE are different facts and must not share a code path.
# A file that is not there is a legitimate shape: copier prunes what a generated
# project did not select, so "no config/practices.json" must degrade in silence.
# A file that IS there but cannot be decoded/parsed is a gate defect: every check
# keyed on it stops gating while the run still exits 0 (the silent-green gate).
# These two helpers make that split once, so no caller has to catch blind.

_CONFIG_READ = {}  # relpath -> parsed JSON or _NO_DATA (parsed once)
_READ_REPORTED = set()  # absolute paths already reported unreadable (report once)

# "The gate got no data" — distinct from the JSON literal `null`, which parses
# fine and is a SHAPE error the caller must still get to report.
_NO_DATA = object()

# The ways a file on disk can fail to become the thing the gate needs. Named so
# every reader states the SAME closed set: anything outside it is a bug in the
# gate, and a gate must fail loudly on its own bugs rather than warn and skip.
UNREADABLE = (OSError, ValueError)  # ValueError covers UnicodeDecodeError
UNPARSEABLE = UNREADABLE + (SyntaxError,)  # ...plus ast.parse (NUL -> ValueError)


def _read_text(path, report):
    """A UTF-8 file's text, or None: absent is silent, unreadable is reported.

    Still degrades to None after reporting, so one bad file never aborts the run.
    `report` is the caller's tier (err for a file whose loss disables a check,
    warn for one whose loss only costs an advisory). Reported at most once per
    path — several checks read the same registry.
    """
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except UNREADABLE as e:
        if path not in _READ_REPORTED:
            _READ_REPORTED.add(path)
            report("%s: unreadable (%s)" % (rel(path), e))
        return None


def _read_json_config(relpath):
    """A JSON config under ROOT as parsed data, else _NO_DATA.

    Same split as _read_text plus invalid JSON — a file the gate can see but
    cannot use, which is the case that silently disabled check_K/L/M. Memoised
    per path so one broken registry yields one error, not one per consumer.
    Returns _NO_DATA (not None) when there is nothing to hand back, so a JSON
    literal `null` stays a caller-visible shape error instead of masquerading
    as a failed read.
    """
    if relpath in _CONFIG_READ:
        return _CONFIG_READ[relpath]
    data = _NO_DATA
    text = _read_text(os.path.join(ROOT, relpath), err)
    if text is not None:
        try:
            data = json.loads(text)
        except ValueError as e:
            err("%s: unreadable (invalid JSON: %s)" % (relpath, e))
    _CONFIG_READ[relpath] = data
    return data


def parse_frontmatter(path):
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except UNREADABLE as e:
        err("%s: cannot read (%s)" % (rel(path), e))
        return {}
    if not text.startswith("---"):
        return None
    data = {}
    for line in text.splitlines()[1:]:
        if line.strip() == "---":
            return data
        if line[:1] in (" ", "\t"):
            continue  # nested key (e.g. cdmon's cdm: sub-keys) - not top-level
        if ":" in line:
            k, _, v = line.partition(":")
            data[k.strip()] = v.strip()
    return None  # block never closed


def check_frontmatter(path, seen_ids):
    fm = parse_frontmatter(path)
    if fm is None:
        err("%s: missing or unterminated frontmatter block" % rel(path))
        return
    for k in REQUIRED_KEYS:
        if not fm.get(k):
            err("%s: frontmatter missing required key '%s'" % (rel(path), k))
    if fm.get("kind") and fm["kind"] not in KINDS:
        err("%s: invalid kind '%s'" % (rel(path), fm["kind"]))
    if fm.get("layer") and fm["layer"] not in LAYERS:
        err("%s: invalid layer '%s'" % (rel(path), fm["layer"]))
    if fm.get("status") and fm["status"] not in STATUSES:
        err("%s: invalid status '%s'" % (rel(path), fm["status"]))
    if fm.get("visibility") and fm["visibility"] not in VISIBILITIES:
        err("%s: invalid visibility '%s'" % (rel(path), fm["visibility"]))
    # Corpus: id must be unique across the corpus.
    fid = fm.get("id")
    if fid:
        if fid in seen_ids:
            err("%s: duplicate id '%s' (also in %s)" % (rel(path), fid, seen_ids[fid]))
        else:
            seen_ids[fid] = rel(path)
    # Corpus: a path-like canonical pointer must resolve to a real file.
    can = fm.get("canonical")
    if (
        can
        and can not in ("true", "false", "self")
        and ("/" in can or can.endswith(".md"))
        and not os.path.exists(os.path.join(ROOT, can))
    ):
        err("%s: canonical target '%s' does not exist" % (rel(path), can))
    # Corpus: replaced content must point at its successor, whichever word the
    # lifecycle uses for "replaced" (general: deprecated; ADRs: superseded).
    status = fm.get("status")
    if status in ("deprecated", "superseded") and not fm.get("superseded_by"):
        err("%s: status is '%s' but no 'superseded_by' is set" % (rel(path), status))
    if not fm.get("owner"):
        warn("%s: frontmatter missing 'owner'" % rel(path))


def check_A():
    seen_ids = {}
    seen_real = set()  # dedupe symlink + target (CLAUDE.md -> AGENT.md)
    for dirpath, _, filenames in walk(ROOT):
        top = rel(dirpath).split(os.sep)[0]
        in_docs = top in ("docs", "test-docs")
        for f in filenames:
            is_tool = f.endswith(".tool.md") and top == "agents"
            if (
                f in ("README.md", "AGENT.md", "CLAUDE.md")
                or (in_docs and f.endswith(".md"))
                or is_tool
            ):
                full = os.path.join(dirpath, f)
                real = os.path.realpath(full)
                if real in seen_real:
                    continue
                seen_real.add(real)
                check_frontmatter(full, seen_ids)
                fm = parse_frontmatter(full)  # cheap re-parse for the roll-up
                if fm:
                    GOVERNED.append((rel(full), fm.get("kind"), fm.get("owner")))


def _declared_toplevel():
    """The top-level names config/project.json declares beyond TAXONOMY.

    Reads `structure.extra_toplevel`, a plain list of names. An absent manifest
    or key declares nothing, silently: check_H already warns on a missing
    manifest, and a project that has not run `copier update` yet has no key.
    Every entry the rule would never consult is an ERROR rather than a skip, so
    a declaration cannot sit in the manifest looking like it does something.
    A malformed manifest declares nothing, so it can never turn the gate green.
    """
    manifest = _read_json_config(os.path.join("config", "project.json"))
    if not isinstance(manifest, dict):
        return []  # absent is silent; unreadable/non-object is reported elsewhere
    structure = _expect(manifest.get("structure"), dict, "structure", {})
    names = _expect(
        structure.get("extra_toplevel"), list, "structure.extra_toplevel", []
    )
    accepted = []
    for name in names:
        if (
            not isinstance(name, str)
            or not name
            or "/" in name
            or "\\" in name
            or name in (".", "..")
        ):
            err(
                "config/project.json: structure.extra_toplevel entry %r is not a "
                "top-level directory name" % (name,)
            )
        elif name.startswith(".") or name in IGNORE_DIRS:
            err(
                "config/project.json: structure.extra_toplevel '%s' is outside the "
                "taxonomy rule (hidden or ignored by the gate); remove it" % name
            )
        elif name in TAXONOMY:
            err(
                "config/project.json: structure.extra_toplevel '%s' is already in "
                "the taxonomy (CONVENTIONS section 2); remove the redundant "
                "declaration" % name
            )
        elif name in accepted:
            err("config/project.json: structure.extra_toplevel names '%s' twice" % name)
        else:
            accepted.append(name)
    return accepted


def _require_labels(relpath, why=""):
    """ERROR for each of README.md / CLAUDE.md missing from ROOT/relpath."""
    for need in ("README.md", "CLAUDE.md"):
        if not os.path.isfile(os.path.join(ROOT, relpath, need)):
            err("%s/: missing %s%s" % (relpath, need, why))


def check_B():
    """The top level is a closed vocabulary, and what it admits is labelled.

    See CONVENTIONS section 2 ("The taxonomy is closed") and section 15.
    """
    for d in REQUIRED_TOPLEVEL:
        if not os.path.isdir(os.path.join(ROOT, d)):
            err("required top-level dir '%s/' is missing" % d)
    declared = _declared_toplevel()
    for d in TAXONOMY:
        if os.path.isdir(os.path.join(ROOT, d)):
            _require_labels(d)
    for d in declared:
        if not os.path.isdir(os.path.join(ROOT, d)):
            err(
                "config/project.json: structure.extra_toplevel declares '%s/' but "
                "it does not exist; delete the declaration" % d
            )
        else:
            _require_labels(d)
    for name in sorted(os.listdir(ROOT)):
        full = os.path.join(ROOT, name)
        if name.startswith(".") or name in IGNORE_DIRS or not os.path.isdir(full):
            continue  # hidden (section 5), tool dirs, files and dangling links
        if name in TAXONOMY or name in declared:
            continue
        # An undeclared symlinked directory WARNs; it is never an ERROR and never
        # silent. walk() is os.walk with followlinks=False, so no check (A, C, D,
        # I, O, V...) ever reads through the link: its contents are ungated, and
        # the WARN says so on every run. It is not an ERROR because git stores a
        # symlink as a path, not as project content, and this gate cannot ask git
        # whether the link is tracked (stdlib-only, no git: Alternatives in
        # docs/adr/keel/K-0009-release-identity-and-the-tag-ordering-rule.md). An
        # ERROR would turn keel's own local gate red over an untracked stray link
        # at the root, and every copier generation from a dirty tree with it,
        # since copier's dirty-HEAD clone runs `git add -A` and copies the link
        # into the project. It is not a loophole for a real directory: turning
        # `parked/` into `parked -> elsewhere` moves the content out of the
        # repository, and a real directory beside a link to it still errors.
        # The cost: a tracked link to an in-repo directory also only warns.
        if os.path.islink(full):
            warn(
                "%s/: symlinked directory outside the taxonomy; no check reads "
                "through a link, so its contents are ungated -- remove it, or "
                "declare it in config/project.json structure.extra_toplevel "
                "(CONVENTIONS section 2)" % name
            )
            continue
        err(
            "%s/: top-level directory is not in the taxonomy (CONVENTIONS section "
            "2) -- move it under an existing directory, or declare it in "
            "config/project.json structure.extra_toplevel and give it a README.md "
            "and CLAUDE.md" % name
        )
    # Every immediate subdirectory of agents/ is held, not only agents/<name>/:
    # the shared agents/tools/ (section 10) is a sibling of the agents (section
    # 13), so the message names the position rather than calling it an agent.
    for name in _subdirs("agents"):
        if not name.startswith("."):
            _require_labels(
                os.path.join("agents", name),
                " (every directory directly under agents/ is labelled, "
                "CONVENTIONS sections 10 and 13)",
            )


def check_C():
    srcroot = os.path.join(ROOT, "src")
    if not os.path.isdir(srcroot):
        return
    for dirpath, _, filenames in walk(srcroot):
        if not any(f.endswith(".py") for f in filenames):
            continue
        if "__init__.py" not in filenames:
            err(
                "%s/: has .py files but no __init__.py (package boundary)"
                % rel(dirpath)
            )
            continue
        init = os.path.join(dirpath, "__init__.py")
        try:
            with open(init, encoding="utf-8-sig") as fh:
                if "__all__" not in fh.read():
                    err(
                        "%s: __init__.py defines no __all__ (public API surface)"
                        % rel(init)
                    )
        except UNREADABLE as e:
            err("%s: cannot read (%s)" % (rel(init), e))


def _private_segment(dotted):
    if not dotted:
        return False
    for part in dotted.split("."):
        if part.startswith("_") and not part.startswith("__"):
            return True
    return False


def check_D():
    for croot in CODE_ROOTS:
        base = os.path.join(ROOT, croot)
        if not os.path.isdir(base):
            continue
        for dirpath, _, filenames in walk(base):
            for f in filenames:
                if not f.endswith(".py"):
                    continue
                full = os.path.join(dirpath, f)
                try:
                    with open(full, encoding="utf-8-sig") as fh:
                        tree = ast.parse(fh.read(), filename=full)
                except UNPARSEABLE as e:
                    warn("%s: could not parse (%s)" % (rel(full), e))
                    continue
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        if node.level == 0 and _private_segment(node.module):
                            err(
                                "%s:%d: absolute import of private module '%s' "
                                "crosses a package boundary - import from the "
                                "package public API instead"
                                % (rel(full), node.lineno, node.module)
                            )
                    elif isinstance(node, ast.Import):
                        for alias in node.names:
                            if _private_segment(alias.name):
                                err(
                                    "%s:%d: import of private module '%s' "
                                    "crosses a package boundary"
                                    % (rel(full), node.lineno, alias.name)
                                )


def _exported_names(tree):
    """Return the string elements of a top-level __all__ literal, or []."""
    out = []
    for node in tree.body:
        # An annotated `__all__: list[str] = [...]` is an AnnAssign, not an
        # Assign — matching only Assign made annotated exports invisible to
        # this reader (and identically to its twin), found by a mutation check
        # in the ADR-K-0008 pass. Both readers changed together; the parity is
        # pinned by tests/unit/scripts/test_check_corpus.py::
        # test_exported_names_parity_with_the_corpus_reader. Deliberately a
        # top-level LITERAL reader: `__all__ +=` / .extend / conditional forms
        # are invisible (zero occurrences in-tree; recorded as deferred in the
        # hardening plan).
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
        for t in targets:
            if (
                isinstance(t, ast.Name)
                and t.id == "__all__"
                and isinstance(node.value, (ast.List, ast.Tuple))
            ):
                for elt in node.value.elts:
                    val = getattr(elt, "s", None)  # 3.6 ast.Str
                    if val is None and isinstance(elt, ast.Constant):
                        val = elt.value  # 3.8+ ast.Constant
                    if isinstance(val, str):
                        out.append(val)
    return out


def check_E():
    """ERROR when an __all__-exported symbol defined in-file has no docstring.
    Authored docstrings are the canonical corpus summaries — a gap is a symbol
    an agent can name but not explain. WARN until ADR-K-0008 promoted it (the
    tree measured zero findings, so promotion cost nothing)."""
    for croot in CODE_ROOTS:
        base = os.path.join(ROOT, croot)
        if not os.path.isdir(base):
            continue
        for dirpath, _, filenames in walk(base):
            for f in filenames:
                if not f.endswith(".py"):
                    continue
                full = os.path.join(dirpath, f)
                try:
                    with open(full, encoding="utf-8-sig") as fh:
                        tree = ast.parse(fh.read(), filename=full)
                except UNPARSEABLE:
                    continue  # check_D already warns on parse failure (same roots)
                exported = _exported_names(tree)
                if not exported:
                    continue
                defs = {}
                for node in tree.body:
                    if isinstance(
                        node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                    ):
                        defs[node.name] = node
                for name in sorted(exported):
                    nd = defs.get(name)  # only names DEFINED here (skip re-exports)
                    if nd is not None and not ast.get_docstring(nd):
                        err(
                            "%s: exported symbol '%s' has no docstring "
                            "(authored summary missing; ADR-K-0008)" % (rel(full), name)
                        )


# The body of a `kind: tool` spec, as CONVENTIONS §10 names it: seven sections
# in this order. `## Side effects` opens with the word for the declared effect,
# and `## When to use` carries at least one `- NOT` bullet — the negative-scope
# line that says what the tool is NOT for and names the sibling that is. Six of
# seven specs carried it by discipline; the rule makes the seventh, and every
# later one, carry it too.
_TOOL_SECTIONS = (
    "Command",
    "Purpose",
    "When to use",
    "Args",
    "Output",
    "Side effects",
    "Used by",
)
_EFFECT_WORD = {
    "read-only": "READ-ONLY",
    "writes": "WRITES",
    "model-call": "MODEL-CALL",
}
_NOT_BULLET = re.compile(r"^\s*[-*]\s+NOT\b")


def _sections(text):
    """[(heading text, [body lines])] for every `## ` heading outside fenced code."""
    out = []
    for line in _unfenced_lines(text):
        if line.startswith("## "):
            out.append((line[3:].strip(), []))
        elif out:
            out[-1][1].append(line)
    return out


def _tool_spec_body_findings(relpath, text, tool_effect):
    """relpath: the spec; text: its full text; tool_effect: the frontmatter value.
    -> error strings. Pure; check_F does the reads."""
    errs = []
    sections = _sections(text)
    names = [name for name, _ in sections]
    missing = [name for name in _TOOL_SECTIONS if name not in names]
    if missing:
        errs.append(
            "%s: tool spec body lacks the section(s) %s -- CONVENTIONS §10 names "
            "seven: %s"
            % (
                relpath,
                ", ".join("'## %s'" % m for m in missing),
                ", ".join(_TOOL_SECTIONS),
            )
        )
    present = [name for name in names if name in _TOOL_SECTIONS]
    expected = [name for name in _TOOL_SECTIONS if name in present]
    if present != expected:
        errs.append(
            "%s: tool spec sections are out of order (%s) -- CONVENTIONS §10 "
            "fixes the order: %s"
            % (relpath, " > ".join(present), " > ".join(_TOOL_SECTIONS))
        )
    body = dict(sections)
    effects = [ln.strip() for ln in body.get("Side effects", []) if ln.strip()]
    want = _EFFECT_WORD.get(tool_effect)
    if want is not None and "Side effects" in body:
        first = effects[0].split()[0].rstrip(".,:;") if effects else ""
        if first != want:
            errs.append(
                "%s: '## Side effects' opens with '%s' but tool_effect is '%s', so "
                "it must open with %s -- the body and the frontmatter are read by "
                "different agents and must not disagree"
                % (relpath, first or "(nothing)", tool_effect, want)
            )
    if "When to use" in body and not any(
        _NOT_BULLET.match(ln) for ln in body["When to use"]
    ):
        errs.append(
            "%s: '## When to use' has no '- NOT ...' bullet -- say what this tool is "
            "NOT for and name the sibling that is (the discriminator between "
            "tools; CONVENTIONS §10)" % relpath
        )
    return errs


def check_F():
    """ERROR on malformed tool specs; WARN when tool/agent docs lack a real owner."""
    agents_dir = os.path.join(ROOT, "agents")
    if os.path.isdir(agents_dir):
        # Validate EVERY *.tool.md under agents/ (not just agents/tools/), so a
        # misplaced/malformed spec cannot dodge governance.
        for dirpath, _, filenames in walk(agents_dir):
            for f in sorted(filenames):
                if not f.endswith(".tool.md"):
                    continue
                full = os.path.join(dirpath, f)
                fm = parse_frontmatter(full)
                if not fm:
                    continue  # check_A already errored on bad/missing frontmatter
                if fm.get("kind") != "tool":
                    err("%s: tool spec must have kind 'tool'" % rel(full))
                inv = fm.get("public_api")
                if not inv or inv == "none":
                    err(
                        "%s: tool spec missing 'public_api' (the wrapped script)"
                        % rel(full)
                    )
                elif not os.path.exists(os.path.join(ROOT, inv)):
                    err("%s: public_api target '%s' does not exist" % (rel(full), inv))
                eff = fm.get("tool_effect")
                if eff not in TOOL_EFFECTS:
                    err(
                        "%s: tool_effect must be one of %s"
                        % (rel(full), sorted(TOOL_EFFECTS))
                    )
                cmd = fm.get("tool_command") or ""
                if inv and inv != "none" and inv not in cmd:
                    err(
                        "%s: tool_command does not invoke public_api '%s'"
                        % (rel(full), inv)
                    )
                text = _read_text(full, err)
                if text is not None:
                    for m in _tool_spec_body_findings(rel(full), text, eff):
                        err(m)
    # accountability roll-up (warning): tools/agents must name a real owner
    for path, kind, owner in GOVERNED:
        if kind in ("tool", "agent") and (not owner or owner == "TBD"):
            warn(
                "accountability: %s (%s) has no real owner (missing or 'TBD')"
                % (path, kind)
            )


def _tool_used_by(path):
    """Agent dirs (agents/<name>) listed under a tool spec's '## Used by'."""
    out = []
    in_section = False
    text = _read_text(path, err)  # unreadable -> the cross-check below goes
    if text is None:  # vacuous, or names the OTHER side wrongly
        return out
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("## "):
            in_section = s.lower() == "## used by"
            continue
        if in_section and s.startswith("- "):
            ref = s[2:].strip().rstrip("/")
            if ref.startswith("agents/"):
                out.append(ref)
    return out


def _manifest_specs(path):
    """Tool-spec basenames referenced in an agent's tools.md (../tools/X.tool.md)."""
    out = []
    text = _read_text(path, err)  # unreadable -> see _tool_used_by
    if text is None:
        return out
    marker, end = "../tools/", ".tool.md"
    i = 0
    while True:
        j = text.find(marker, i)
        if j < 0:
            break
        k = text.find(end, j)
        if k < 0:
            break
        out.append(text[j + len(marker) : k])
        i = k + 1
    return out


def check_G():
    """Enforce the bidirectional tool<->agent binding (CONVENTIONS §10)."""
    agents_dir = os.path.join(ROOT, "agents")
    tools_dir = os.path.join(agents_dir, "tools")
    if not os.path.isdir(agents_dir):
        return
    existing = set()
    if os.path.isdir(tools_dir):
        for f in os.listdir(tools_dir):
            if f.endswith(".tool.md"):
                existing.add(f[: -len(".tool.md")])
    spec_to_agents = {}
    for s in existing:
        spec_to_agents[s] = set(_tool_used_by(os.path.join(tools_dir, s + ".tool.md")))
    agent_to_specs = {}
    for name in sorted(os.listdir(agents_dir)):
        man = os.path.join(agents_dir, name, "tools.md")
        if name == "tools" or not os.path.isfile(man):
            continue
        agent_to_specs["agents/" + name] = set(_manifest_specs(man))
    for agent, specs in agent_to_specs.items():
        for s in specs:
            if s not in existing:
                err(
                    "%s/tools.md: references unknown tool spec "
                    "'../tools/%s.tool.md'" % (agent, s)
                )
            elif agent not in spec_to_agents.get(s, set()):
                err(
                    "%s/tools.md: uses '%s' but agents/tools/%s.tool.md "
                    "'## Used by' omits %s" % (agent, s, s, agent)
                )
    for s in sorted(spec_to_agents):
        for agent in spec_to_agents[s]:
            if s not in agent_to_specs.get(agent, set()):
                err(
                    "agents/tools/%s.tool.md: '## Used by' names %s but its "
                    "tools.md omits '%s'" % (s, agent, s)
                )


def _requires_python():
    """Return pyproject.toml's requires-python value, or None if absent."""
    text = _read_text(os.path.join(ROOT, "pyproject.toml"), err)
    if text is None:
        return None
    m = re.search(r'requires-python\s*=\s*(["\'])([^"\']+)\1', text)
    return m.group(2).strip() if m else None


def _subdirs(relpath):
    """Immediate sub-directory names under ROOT/relpath, minus IGNORE_DIRS."""
    base = os.path.join(ROOT, relpath)
    if not os.path.isdir(base):
        return []
    return [
        name
        for name in sorted(os.listdir(base))
        if name not in IGNORE_DIRS and os.path.isdir(os.path.join(base, name))
    ]


def _expect(val, typ, label, default):
    """Return val if it is `typ` (None becomes default); else record an error.

    A malformed manifest gets a clean error, never a traceback or a silent
    pass (e.g. an 'available' written as an object instead of a list).
    """
    if val is None:
        return default
    if not isinstance(val, typ):
        want = "a list" if typ is list else "an object" if typ is dict else typ.__name__
        err("config/project.json: %s must be %s" % (label, want))
        return default
    return val


def check_H():
    """Project facts in config/project.json agree with the tree.

    Declared facts are enforced (errors); a stack or transport present on
    disk but absent from the manifest is a WARN (an undeclared leftover).
    Stdlib JSON, so it runs under the old pre-commit interpreter (no tomllib).
    See CONVENTIONS section 15.
    """
    path = os.path.join(ROOT, "config", "project.json")
    if not os.path.isfile(path):
        warn("config/project.json: not found; project facts are unenforced")
        return
    manifest = _read_json_config(os.path.join("config", "project.json"))
    if manifest is _NO_DATA:
        return  # _read_json_config already reported it
    if not isinstance(manifest, dict):  # incl. a literal `null` — a shape error
        err("config/project.json: top level must be a JSON object")
        return
    layers = _expect(manifest.get("layers"), dict, "layers", {})

    backend = _expect(layers.get("backend"), dict, "layers.backend", {})
    bpath = backend.get("path")
    if (
        isinstance(bpath, str)
        and bpath
        and not os.path.isdir(os.path.join(ROOT, bpath))
    ):
        err("config/project.json: layers.backend.path '%s' does not exist" % bpath)
    bpy = backend.get("python")
    if isinstance(bpy, str) and bpy:
        have = _requires_python()
        if have is not None and have != bpy:
            err(
                "config/project.json: layers.backend.python '%s' != pyproject "
                "requires-python '%s'" % (bpy, have)
            )

    frontend = _expect(layers.get("frontend"), dict, "layers.frontend", {})
    froot = frontend.get("root")
    if isinstance(froot, str) and froot:
        available = _expect(
            frontend.get("available"), list, "layers.frontend.available", []
        )
        stack = frontend.get("stack")
        if (
            isinstance(stack, str)
            and stack
            and not os.path.isdir(os.path.join(ROOT, froot, stack))
        ):
            err(
                "config/project.json: layers.frontend.stack '%s' has no dir "
                "under %s/" % (stack, froot)
            )
        for a in available:
            if isinstance(a, str) and not os.path.isdir(os.path.join(ROOT, froot, a)):
                warn(
                    "config/project.json: declared frontend stack '%s' is "
                    "missing (%s/%s)" % (a, froot, a)
                )
        for d in _subdirs(froot):
            if d not in available:
                warn(
                    "%s/%s: present but not in config/project.json "
                    "layers.frontend.available (undeclared stack)" % (froot, d)
                )

    transports = _expect(manifest.get("transports"), dict, "transports", {})
    enabled = _expect(transports.get("enabled"), list, "transports.enabled", [])
    avail = _expect(transports.get("available"), dict, "transports.available", {})
    for t in enabled:
        if t not in avail:
            err(
                "config/project.json: transports.enabled '%s' not in "
                "transports.available" % t
            )
        elif isinstance(avail[t], str) and not os.path.isdir(
            os.path.join(ROOT, avail[t])
        ):
            err(
                "config/project.json: enabled transport '%s' -> '%s' does not "
                "exist" % (t, avail[t])
            )
    declared = {v for v in avail.values() if isinstance(v, str)}
    for d in _subdirs("api"):
        if os.path.join("api", d) not in declared:
            warn(
                "api/%s: present but not in config/project.json "
                "transports.available (undeclared transport)" % d
            )

    # Agent runtimes (optional block): the default must be an available engine
    # and each engine's dir must exist (CONVENTIONS section 16).
    runtimes = manifest.get("runtimes")
    if runtimes is not None:
        runtimes = _expect(runtimes, dict, "runtimes", {})
        r_avail = _expect(runtimes.get("available"), dict, "runtimes.available", {})
        r_default = runtimes.get("default")
        if r_default is not None and r_default not in r_avail:
            err(
                "config/project.json: runtimes.default '%s' not in "
                "runtimes.available" % r_default
            )
        for nm in sorted(r_avail):
            d = r_avail[nm]
            if isinstance(d, str) and not os.path.isdir(os.path.join(ROOT, d)):
                err(
                    "config/project.json: runtime '%s' -> '%s' does not exist" % (nm, d)
                )

    # Model adapters (optional block): the default must be an available adapter
    # and each adapter's dir must exist. models/registry.py is the code source of
    # truth; this manifest is the project's curated list, surfaced by the showcase.
    models = manifest.get("models")
    if models is not None:
        models = _expect(models, dict, "models", {})
        m_avail = _expect(models.get("available"), dict, "models.available", {})
        m_default = models.get("default")
        if m_default is not None and m_default not in m_avail:
            err(
                "config/project.json: models.default '%s' not in "
                "models.available" % m_default
            )
        for nm in sorted(m_avail):
            d = m_avail[nm]
            if isinstance(d, str) and not os.path.isdir(os.path.join(ROOT, d)):
                err("config/project.json: model '%s' -> '%s' does not exist" % (nm, d))

    # Practice profiles (optional block): domain profiles are DEFINED in
    # config/practices.json and ENABLED here (CONVENTIONS section 15). A
    # non-boolean flag is a provable error; an enabled flag that names no
    # defined profile is inert (activates nothing) -> WARN, not err.
    practices_blk = manifest.get("practices")
    if practices_blk is not None:
        practices_blk = _expect(practices_blk, dict, "practices", {})
        profiles = practices_blk.get("profiles")
        if profiles is not None:
            profiles = _expect(profiles, dict, "practices.profiles", {})
            errs, warns_ = _profile_flag_findings(profiles, _defined_profile_names())
            for m in errs:
                err(m)
            for m in warns_:
                warn(m)


def _defined_profile_names():
    """The set of domain-profile names DEFINED in config/practices.json, or None
    when it cannot be authoritatively determined (file absent or not a dict,
    'profiles' missing or not a dict, or only '_'-prefixed keys). Returning None
    suppresses the enabled-but-undefined WARN, so a registry-side SHAPE typo never
    breaks a consuming repo's build (mirrors _stdlib_exc_modules' safe degrade).
    A present-but-unreadable registry is NOT such a typo — _read_json_config
    reports it — because it silently disables check_K/L/M as well as this WARN."""
    data = _read_json_config(os.path.join("config", "practices.json"))
    if not isinstance(data, dict):
        return None
    profs = data.get("profiles")
    if not isinstance(profs, dict):
        return None
    names = {k for k in profs if not str(k).startswith("_")}
    return names or None


def _profile_flag_findings(profiles, defined):
    """(errors, warnings) for a practices.profiles dict. A non-boolean value is a
    provable error; an enabled (True) flag whose name is not in `defined` (when
    known) is inert and only warns. `defined` is a name set or None (unknown)."""
    errs, warns_ = [], []
    for name in sorted(profiles):
        if str(name).startswith("_"):
            continue
        val = profiles[name]
        if not isinstance(val, bool):
            errs.append(
                "config/project.json: practices.profiles.%s must be true "
                "or false (a boolean), not %s" % (name, type(val).__name__)
            )
            continue
        if val is True and defined is not None and name not in defined:
            warns_.append(
                "config/project.json: practices.profiles.%s is enabled "
                "but names no profile defined in config/practices.json "
                "profiles %s; it will activate nothing" % (name, sorted(defined))
            )
    return errs, warns_


def check_I():
    """ERROR when CLAUDE.md is not a symlink to its sibling AGENT.md.

    CONVENTIONS section 5: AGENT.md is the canonical, vendor-neutral agent-rules
    file; CLAUDE.md is a symlink to it so every agent tool reads one source. A
    regular-file CLAUDE.md is a copy that drifts silently -- require the link.
    Also flag an AGENT.md with no CLAUDE.md sibling (rules an agent can't find).
    """
    for dirpath, _, filenames in walk(ROOT):
        has_agent = "AGENT.md" in filenames
        if "CLAUDE.md" in filenames:
            claude = os.path.join(dirpath, "CLAUDE.md")
            if not os.path.islink(claude):
                err(
                    "%s: must be a symlink to the sibling AGENT.md, not a "
                    "regular file (CONVENTIONS section 5)" % rel(claude)
                )
            elif os.readlink(claude) != "AGENT.md":
                err(
                    "%s: symlink target '%s' must be exactly 'AGENT.md' "
                    "(a relative sibling link)" % (rel(claude), os.readlink(claude))
                )
            elif not os.path.isfile(os.path.join(dirpath, "AGENT.md")):
                err("%s: symlink target AGENT.md does not exist" % rel(claude))
        elif has_agent:
            err(
                "%s/AGENT.md: has no sibling CLAUDE.md symlink "
                "(CONVENTIONS section 5)" % rel(dirpath)
            )


# --- check_J: no third-party exception leaks across a library boundary --------

# Library/doer code where wrapping a foreign exception matters. Transport
# adapters (api/, mcp/) and tests/ are excluded: speaking a framework's own
# exception dialect there (e.g. FastAPI's HTTPException) is correct, not a leak.
J_ROOTS = ["src", "models", "runtimes", "agents"]

_PRACTICE_OK_RE = re.compile(r"^#\s*practice-ok\b")

# Fallback set of stdlib modules whose exceptions may be raised unwrapped. The
# real list is DATA in config/practices.json (tokens.stdlib_exception_modules);
# this is only used when that file is absent, so the gate degrades gracefully.
_STDLIB_EXC_FALLBACK = [
    "json",
    "urllib",
    "http",
    "socket",
    "ssl",
    "subprocess",
    "asyncio",
    "sqlite3",
    "struct",
    "pickle",
    "xml",
    "configparser",
    "argparse",
    "queue",
    "threading",
    "multiprocessing",
    "concurrent",
    "decimal",
    "os",
    "io",
    "re",
    "hashlib",
    "csv",
    "zlib",
    "gzip",
    "tarfile",
    "zipfile",
]


def _practice_ok_lines(text):
    """Line numbers carrying a `# practice-ok` suppression pragma (tokenize, so a
    `#` inside a string literal is never mistaken for a comment)."""
    out = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT and _PRACTICE_OK_RE.match(
                tok.string.strip()
            ):
                out.add(tok.start[0])
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        pass
    return out


def _local_top_names():
    """Top-level import names that resolve to a local package (repo-root dirs +
    src/ subdirs). A relative import is always local and never listed here."""
    tops = set()
    for name in os.listdir(ROOT):
        if os.path.isdir(os.path.join(ROOT, name)):
            tops.add(name)
    srcdir = os.path.join(ROOT, "src")
    if os.path.isdir(srcdir):
        for name in os.listdir(srcdir):
            if os.path.isdir(os.path.join(srcdir, name)):
                tops.add(name)
    return tops


def _stdlib_exc_modules():
    """Declared stdlib modules whose exceptions may be raised unwrapped
    (config/practices.json tokens.stdlib_exception_modules), else the fallback."""
    data = _read_json_config(os.path.join("config", "practices.json"))
    tokens = data.get("tokens") if isinstance(data, dict) else None
    if isinstance(tokens, dict):
        mods = tokens.get("stdlib_exception_modules")
        if isinstance(mods, list) and mods:
            return set(mods)
    return set(_STDLIB_EXC_FALLBACK)


def _import_top_map(tree):
    """bound name -> top-level module segment, for ABSOLUTE imports only
    (relative imports are local, so their bound names are omitted by design)."""
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            top = node.module.split(".")[0]
            for a in node.names:
                out[a.asname or a.name] = top
        elif isinstance(node, ast.Import):
            for a in node.names:
                top = a.name.split(".")[0]
                out[a.asname or top] = top
    return out


def _raised_root_name(exc):
    """Leftmost Name id of a raised exception (Name or attribute chain), or None
    for a bare `raise` or a raised local-variable expression."""
    if exc is None:
        return None
    target = exc.func if isinstance(exc, ast.Call) else exc
    while isinstance(target, ast.Attribute):
        target = target.value
    if isinstance(target, ast.Name):
        return target.id
    return None


def _foreign_exception_raises(tree, local_tops, stdlib_mods, pragma):
    """(lineno, name) for every `raise X(...)` whose X is an exception TYPE
    imported from a foreign module (neither a local package nor a declared
    stdlib module). Builtins (never imported), bare re-raises, raised local
    variables, and pragma-suppressed lines are all excluded — so the rule keys
    on 'foreign import', not on a name suffix (CONVENTIONS §18)."""
    imports = _import_top_map(tree)
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise):
            continue
        name = _raised_root_name(node.exc)
        if name is None or name not in imports:
            continue
        top = imports[name]
        if top in local_tops or top in stdlib_mods:
            continue
        line = getattr(node, "lineno", 0)
        if line in pragma:
            continue
        out.append((line, name))
    return out


def check_J():
    """No third-party exception leaks across a library boundary (coding-practices
    gate; owned-exception-boundary in config/practices.json). Raising a foreign
    exception TYPE forces callers to import that vendor to catch it; wrap it in an
    owned error. Judgment-call smells (DI, isinstance chains) are advisory in
    check_practices.py; this GATE fires only on the provable case."""
    local_tops = _local_top_names()
    stdlib_mods = _stdlib_exc_modules()
    for croot in J_ROOTS:
        base = os.path.join(ROOT, croot)
        if not os.path.isdir(base):
            continue
        for dirpath, _, filenames in walk(base):
            for f in filenames:
                if not f.endswith(".py"):
                    continue
                full = os.path.join(dirpath, f)
                try:
                    with open(full, encoding="utf-8-sig") as fh:
                        text = fh.read()
                    tree = ast.parse(text, filename=full)
                except UNPARSEABLE as e:
                    warn("%s: could not parse (%s)" % (rel(full), e))
                    continue
                pragma = _practice_ok_lines(text)
                for line, name in _foreign_exception_raises(
                    tree, local_tops, stdlib_mods, pragma
                ):
                    err(
                        "%s:%d: raises third-party exception '%s' across a package "
                        "boundary - wrap it in an owned error "
                        "(or add `# practice-ok: <reason>`)" % (rel(full), line, name)
                    )


# --- shared registry readers (config/practices.json, config/project.json) -----


def _load_practices():
    """config/practices.json as a dict, else {} — absent degrades to silence, a
    present-but-unreadable registry is reported (it disables check_K/L/M).
    Read BY PATH, never imported (it is DATA — CONVENTIONS section 18)."""
    data = _read_json_config(os.path.join("config", "practices.json"))
    return data if isinstance(data, dict) else {}


def _profiles_on():
    """Domain profiles enabled in config/project.json practices.profiles. Mirrors
    check_practices.profiles_on() exactly (value is True, '_'-keys stripped).
    An unreadable manifest is reported by _read_json_config, never swallowed:
    it would otherwise silently return check_L before it does any work."""
    proj = _read_json_config(os.path.join("config", "project.json"))
    practices = proj.get("practices") if isinstance(proj, dict) else None
    prof = practices.get("profiles") if isinstance(practices, dict) else None
    if not isinstance(prof, dict):
        return set()
    return {k for k in prof if prof[k] is True and not str(k).startswith("_")}


# --- check_K: frozen-config gate ----------------------------------------------
#
# A class carrying the DECLARED marker (tokens.config_marker) must be provably
# immutable. Unlike check_J (which fires only on a proven leak, so recognizer
# gaps are safe misses), check_K is INVERTED: a marked class the recognizer
# cannot prove immutable is an ERROR. So recognition is broad and alias-resolving,
# and any residual gap (a frozen base class, a functional namedtuple()) is a
# documented WAIVER case (`# practice-ok: <reason>`), never a silent false error.


def _class_kw_line(node, lines):
    """The 1-based source line of the `class` keyword. On 3.8+ ClassDef.lineno is
    already the `class` line; on 3.6 it is the first DECORATOR line. A decorator
    call may span several physical lines (Black/ruff wrap long `@dataclass(...)`),
    so max(decorator lineno)+1 is NOT reliable — it can land inside the call. Scan
    the source forward from node.lineno for the first line whose text starts with
    `class` instead; decorators immediately precede their class, so the first such
    line is this class's keyword line on every interpreter."""
    start = getattr(node, "lineno", 0)
    n = len(lines)
    i = start
    while i <= n:
        if 1 <= i <= n:
            s = lines[i - 1].lstrip()
            if s.startswith(("class ", "class\t")):
                return i
        i += 1
    return start


def _exact_marker_lines(text, marker):
    """{lineno: column} for every comment whose body EQUALS `marker` exactly (not
    a substring — so `# NOTE: not practice: frozen-config` never marks a class).
    The column lets the caller reject a marker indented inside an earlier body."""
    out = {}
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if (
                tok.type == tokenize.COMMENT
                and tok.string.lstrip("#").strip() == marker
            ):
                out[tok.start[0]] = tok.start[1]
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        pass
    return out


def _class_is_marked(node, marker_cols, lines):
    """True when a marker sits on this class's own header lines (decorators or the
    `class` line, any column), or on the line DIRECTLY above it at the SAME indent
    as the `class` keyword. The same-indent rule is what stops a marker written as
    an indented note inside an earlier class body from bleeding onto the class
    below it (its column would be deeper than this class's col_offset)."""
    kw = _class_kw_line(node, lines)
    decs = [getattr(d, "lineno", kw) for d in getattr(node, "decorator_list", [])]
    top = min([kw] + decs)  # first physical line of the header
    for ln in marker_cols:
        if top <= ln <= kw:
            return True
    above = top - 1
    return marker_cols.get(above) == getattr(node, "col_offset", 0)


def _binding_map(tree):
    """bound-name -> (module_top, original_attr) for absolute imports, so an alias
    like `from dataclasses import dataclass as dc` resolves to ('dataclasses',
    'dataclass'). Relative imports are local and intentionally omitted."""
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            top = node.module.split(".")[0]
            for a in node.names:
                out[a.asname or a.name] = (top, a.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                top = a.name.split(".")[0]
                out[a.asname or top] = (top, a.name.split(".")[-1])
    return out


def _dotted_tail(node):
    """Last attribute/name segment of a decorator or base expression
    (attrs.frozen -> 'frozen', a bare Name -> its id)."""
    tgt = node.func if isinstance(node, ast.Call) else node
    if isinstance(tgt, ast.Attribute):
        return tgt.attr
    if isinstance(tgt, ast.Name):
        return tgt.id
    return None


def _resolves_to(name, binding, want_module, want_attrs):
    b = binding.get(name)
    if b is None:
        return False
    top, orig = b
    return top == want_module and orig in want_attrs


def _kw_true(node):
    """3.6-safe `is True` test: 3.8+ ast.Constant(value=True), 3.6 NameConstant."""
    cn = node.__class__.__name__
    if cn in ("Constant", "NameConstant"):
        return getattr(node, "value", None) is True
    return False


def _is_frozen_dataclass(node, binding):
    for dec in getattr(node, "decorator_list", []):
        base = dec.func if isinstance(dec, ast.Call) else dec
        tail = _dotted_tail(dec)
        is_dc = False
        if isinstance(base, ast.Name):
            is_dc = (tail == "dataclass") or _resolves_to(
                base.id, binding, "dataclasses", ("dataclass",)
            )
        elif isinstance(base, ast.Attribute):
            is_dc = tail == "dataclass"
        if is_dc and isinstance(dec, ast.Call):
            for kw in dec.keywords:
                if kw.arg == "frozen" and _kw_true(kw.value):
                    return True
    return False


def _is_namedtuple(node, binding):
    for b in getattr(node, "bases", []):
        tail = _dotted_tail(b)
        if isinstance(b, ast.Name):
            if tail == "NamedTuple" or _resolves_to(
                b.id, binding, "typing", ("NamedTuple",)
            ):
                return True
        elif isinstance(b, ast.Attribute) and tail == "NamedTuple":
            return True
    return False


def _is_attrs_frozen(node, binding):
    """@attr.frozen / @attrs.frozen / @frozen (always immutable), or
    @attr.s(frozen=True) / @define(frozen=True) (immutable only with frozen=True)."""
    for dec in getattr(node, "decorator_list", []):
        tail = _dotted_tail(dec)
        if tail == "frozen":
            return True
        if tail in ("s", "attrs", "define") and isinstance(dec, ast.Call):
            for kw in dec.keywords:
                if kw.arg == "frozen" and _kw_true(kw.value):
                    return True
    return False


def _is_immutable_config(node, binding):
    return (
        _is_frozen_dataclass(node, binding)
        or _is_namedtuple(node, binding)
        or _is_attrs_frozen(node, binding)
    )


def _span_pragma(lo, hi, pragma):
    return any(lo <= ln <= hi for ln in pragma)


def _frozen_config_violations(tree, text, marker, pragma):
    """(class_kw_line, class_name) for every class DECLARED frozen-config by the
    exact marker that is not provably immutable and not waived. Pure: no I/O."""
    marker_cols = _exact_marker_lines(text, marker)
    if not marker_cols:
        return []
    lines = text.split("\n")
    binding = _binding_map(tree)
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if not _class_is_marked(node, marker_cols, lines):
            continue
        kw = _class_kw_line(node, lines)
        decs = [getattr(d, "lineno", kw) for d in getattr(node, "decorator_list", [])]
        if _span_pragma(min([kw] + decs), kw, pragma):
            continue
        if _is_immutable_config(node, binding):
            continue
        out.append((kw, node.name))
    return out


def check_K():
    """Frozen-config gate: a class carrying `# <config_marker>` must be provably
    immutable (frozen dataclass / NamedTuple / attrs-frozen). Keyed on the
    author-written marker (declared intent), never a *Config name suffix (§18).
    A construct the recognizer can't prove (a frozen base class, a functional
    namedtuple) is waived with `# practice-ok: <reason>`."""
    practices = _load_practices()
    marker = (practices.get("tokens") or {}).get("config_marker")
    if not isinstance(marker, str) or not marker:
        return  # no declared marker -> nothing to gate
    for croot in J_ROOTS:
        base = os.path.join(ROOT, croot)
        if not os.path.isdir(base):
            continue
        for dirpath, _, filenames in walk(base):
            for f in filenames:
                if not f.endswith(".py"):
                    continue
                full = os.path.join(dirpath, f)
                try:
                    with open(full, encoding="utf-8-sig") as fh:
                        text = fh.read()
                    tree = ast.parse(text, filename=full)
                except UNPARSEABLE as e:
                    warn("%s: could not parse (%s)" % (rel(full), e))
                    continue
                pragma = _practice_ok_lines(text)
                for line, name in _frozen_config_violations(tree, text, marker, pragma):
                    err(
                        "%s:%d: class '%s' declares `# %s` but is not provably "
                        "immutable - use a frozen dataclass / NamedTuple / attrs "
                        "frozen, or add `# practice-ok: <reason>`"
                        % (rel(full), line, name, marker)
                    )


# --- check_L: naked-tensor domain gate (WARN, cuda profile only) --------------

# A shape comment: a bracket pair holding >= 2 comma-separated dim atoms
# (identifiers / ints / '*' / '...' / dotted names). A single-atom paren like
# `(deprecated)` or `TODO(x)` is NOT a shape, so it can never silently waive.
_SHAPE_COMMENT_RE = re.compile(
    r"[\(\[]\s*[\w.*]+(?:\s*,\s*(?:[\w.*]+|\.\.\.))+\s*[\)\]]"
)

_STR_T = getattr(ast, "Str", ())


def _shape_comment_lines(text):
    """Line numbers carrying a shape comment (via tokenize, so a shape-looking
    substring inside a string literal never waives)."""
    out = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT and _SHAPE_COMMENT_RE.search(tok.string):
                out.add(tok.start[0])
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        pass
    return out


def _func_header_span(fn):
    """(first_header_line, last_header_line) for a function: from its first
    decorator/def line down to the line before its first body statement, so a
    shape/waiver comment anywhere in a multi-line signature is honoured."""
    start = getattr(fn, "lineno", 0)
    decs = [getattr(d, "lineno", start) for d in getattr(fn, "decorator_list", [])]
    lo = min([start] + decs)
    body = getattr(fn, "body", [])
    hi = (getattr(body[0], "lineno", start) - 1) if body else start
    if hi < start:
        hi = start
    return (lo, hi)


def _annotation_base_name(ann, base_types):
    """The bare tensor type name of an annotation that is EXACTLY a member of
    base_types (a plain Name or a string annotation), else None. Exact membership,
    never a suffix/substring match."""
    if isinstance(ann, ast.Name) and ann.id in base_types:
        return ann.id
    if _STR_T and isinstance(ann, _STR_T):  # 3.6 string annotation: x: "Tensor"
        v = getattr(ann, "s", None)
        if isinstance(v, str) and v in base_types:
            return v
    if ann.__class__.__name__ == "Constant":  # 3.8+ string annotation
        v = getattr(ann, "value", None)
        if isinstance(v, str) and v in base_types:
            return v
    return None


def _naked_tensor_params(tree, text, base_types):
    """(lineno, param_name, type_name) for every parameter annotated with a bare
    tensor type and not covered by a shape comment or `# practice-ok` anywhere in
    its function's header span. Per-arg (so both of `a: Tensor, b: Tensor` show).
    Pure: no I/O."""
    if not base_types:
        return []
    shape_lines = _shape_comment_lines(text)
    pragma = _practice_ok_lines(text)
    out = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        lo, hi = _func_header_span(fn)
        lo -= 1  # also honour a leading comment line
        waived = any(lo <= ln <= hi for ln in shape_lines) or any(
            lo <= ln <= hi for ln in pragma
        )
        if waived:
            continue
        a = fn.args
        allargs = (
            list(getattr(a, "posonlyargs", [])) + list(a.args) + list(a.kwonlyargs)
        )
        for arg in allargs:
            ann = getattr(arg, "annotation", None)
            if ann is None:
                continue
            name = _annotation_base_name(ann, base_types)
            if name is not None:
                out.append(
                    (getattr(arg, "lineno", getattr(fn, "lineno", 0)), arg.arg, name)
                )
    return out


def check_L():
    """Naked-tensor domain gate (WARN): only when the cuda profile is enabled, a
    parameter annotated with a bare tensor base type (tokens.tensor_base_types)
    and no shape comment WARNs. Never errs: a token like `Array` may name a local
    non-tensor class, so this is an advisory heuristic, off by default."""
    if "cuda" not in _profiles_on():
        return
    practices = _load_practices()
    bt = (practices.get("tokens") or {}).get("tensor_base_types")
    base_types = set(bt) if isinstance(bt, list) and bt else set()
    if not base_types:  # no declared tokens -> silence (no fallback)
        return
    for croot in J_ROOTS:
        base = os.path.join(ROOT, croot)
        if not os.path.isdir(base):
            continue
        for dirpath, _, filenames in walk(base):
            for f in filenames:
                if not f.endswith(".py"):
                    continue
                full = os.path.join(dirpath, f)
                try:
                    with open(full, encoding="utf-8-sig") as fh:
                        text = fh.read()
                    tree = ast.parse(text, filename=full)
                except UNPARSEABLE as e:
                    warn("%s: could not parse (%s)" % (rel(full), e))
                    continue
                for line, arg, name in _naked_tensor_params(tree, text, base_types):
                    warn(
                        "%s:%d: parameter '%s' is a naked %s (bare tensor type, "
                        "no shape); annotate a shape (jaxtyping/alias) or add "
                        "`# practice-ok: <reason>` [cuda profile; advisory]"
                        % (rel(full), line, arg, name)
                    )


# --- check_M: ruleset parity (config/practices.json <-> pyproject.toml) --------
#
# Prove pyproject.toml cannot silently LOOSEN the policy declared as DATA in
# practices.json rulesets: every declared ruff extend_select family must be
# selected, every declared mypy flag must be enforced (= true), and no 'deferred'
# family may be silently selected. Stdlib only, no tomllib (runs on 3.6), so it
# ships a small quote/comment/multi-line-aware TOML scanner rather than parsing.

_FLAG_RE = re.compile(r"^(true|false)\b")

# Triple-quote delimiters used by the check_M TOML scan below. _TRI3 (three
# single-quote chars) is BUILT rather than written as a literal so this file never
# itself contains a triple-single-quote sequence.
_TRI_D = '"""'
_TRI3 = "'" * 3


def _toml_scan(text):
    """Per line: (comment_col, instr, bdelta). comment_col[ln] is the column where
    the line's real comment starts (or None); instr[ln] is True when the whole line
    lies inside a multi-line string; bdelta[ln] is the net '['-minus-']' count that
    lies OUTSIDE any string or comment — so a bracket inside a string value (e.g.
    `description = "wip [beta"`) never unbalances a multi-line-array accumulation.
    A single state machine tracks basic/literal and triple-quoted strings across
    lines, so a '#' inside a string is never a comment and a quote inside a comment
    never opens a string."""
    lines = text.split("\n")
    comment_col, instr, bdelta = {}, {}, {}
    st = None
    for i in range(len(lines)):
        ln = i + 1
        line = lines[i]
        instr[ln] = st in (_TRI_D, _TRI3)
        j, ccol, n, bd = 0, None, len(line), 0
        while j < n:
            c = line[j]
            three = line[j : j + 3]
            if st in (_TRI_D, _TRI3):
                if three == st:
                    st = None
                    j += 3
                    continue
                j += 1
                continue
            if st == '"':
                if c == "\\":
                    j += 2
                    continue
                if c == '"':
                    st = None
                j += 1
                continue
            if st == "'":
                if c == "'":
                    st = None
                j += 1
                continue
            if three in (_TRI_D, _TRI3):
                st = three
                j += 3
                continue
            if c in ('"', "'"):
                st = c
                j += 1
                continue
            if c == "#":
                ccol = j
                break
            if c == "[":
                bd += 1
            elif c == "]":
                bd -= 1
            j += 1
        comment_col[ln] = ccol
        bdelta[ln] = bd
    return comment_col, instr, bdelta


def _toml_practice_ok_lines(text):
    """Line numbers carrying a `# practice-ok` comment (dedicated TOML scanner —
    the Python tokenizer bails on TOML; an in-string pragma never waives)."""
    comment_col, instr, _ = _toml_scan(text)
    lines = text.split("\n")
    out = set()
    for ln in comment_col:
        if instr.get(ln) or comment_col[ln] is None:
            continue
        body = lines[ln - 1][comment_col[ln] :].lstrip("#").strip()
        if body.startswith("practice-ok"):
            out.add(ln)
    return out


def _toml_targets(text):
    """{fully-qualified dotted key: [(start_lineno, rhs_text, span_lines)]}. The
    current table header is prepended to each key, so `[tool.ruff.lint]` + bare
    `extend-select` and root `tool.ruff.lint.extend-select` normalise to the same
    key. A bracketed array value that spans lines is accumulated whole (comments
    stripped), so a multi-line `extend-select = [ ... ]` is one rhs_text. Array
    depth is counted OUTSIDE strings (via bdelta), so a '[' inside a string value
    cannot runaway-swallow the rest of the file."""
    comment_col, instr, bdelta = _toml_scan(text)
    lines = text.split("\n")
    cur_table = ""
    assigns = {}
    n = len(lines)
    i = 0
    while i < n:
        ln = i + 1
        if instr.get(ln):
            i += 1
            continue
        raw = lines[i]
        col = comment_col.get(ln)
        if col is not None:
            raw = raw[:col]
        s = raw.strip()
        if not s:
            i += 1
            continue
        if s.startswith("[") and s.endswith("]") and "=" not in s:
            cur_table = (
                s[1:-1].strip().strip("[]").strip()
            )  # [[x]] array-of-tables -> x
            i += 1
            continue
        if "=" not in s:
            i += 1
            continue
        key, rhs = s.split("=", 1)
        key, rhs = key.strip(), rhs.strip()
        full = (cur_table + "." + key) if cur_table else key
        span = {ln}
        depth = bdelta.get(ln, 0)
        j = i
        while depth > 0 and j + 1 < n:
            j += 1
            ln2 = j + 1
            if instr.get(ln2):
                continue
            raw2 = lines[j]
            col2 = comment_col.get(ln2)
            if col2 is not None:
                raw2 = raw2[:col2]
            rhs += " " + raw2.strip()
            span.add(ln2)
            depth += bdelta.get(ln2, 0)
        assigns.setdefault(full, []).append((ln, rhs, span))
        i = j + 1
    return assigns


def _rhs_has_family(rhs_text, fam):
    """True if `fam` appears as a QUOTED whole token, so "I" never matches inside
    "SIM"."""
    return ('"%s"' % fam) in rhs_text or ("'%s'" % fam) in rhs_text


def _deferred_active(rhs_text, fam):
    """True if a DEFERRED family is effectively selected. ruff selects a rule via
    ANY prefix of its code (`RUF` or `RUF0` selects `RUF022`) and `ALL` selects
    everything, so check the family, each of its category-or-longer prefixes, and
    `ALL` — not just the exact token (else `extend-select = ["RUF"]` would smuggle
    a deferred `RUF022` past the gate)."""
    if _rhs_has_family(rhs_text, "ALL"):
        return True
    cat = ""
    for ch in fam:
        if ch.isalpha():
            cat += ch
        else:
            break
    for k in range(len(cat), len(fam) + 1):
        if _rhs_has_family(rhs_text, fam[:k]):
            return True
    return False


def _flag_state(entries):
    """'on' | 'off' | 'absent' for a mypy flag, last-writer-wins (so `flag = true`
    then `flag = false` reads as off — a real loosening)."""
    if not entries:
        return "absent"
    rhs = entries[-1][1].strip()
    m = _FLAG_RE.match(rhs)
    if not m:
        return "absent"
    return "on" if m.group(1) == "true" else "off"


def _line_waived(target_lines, pragma):
    """A finding anchored to specific lines is waived by a `# practice-ok` on any
    of those lines or the line directly above the first."""
    return any(ln in pragma or (ln - 1) in pragma for ln in target_lines)


def _span_lines(entries):
    out = set()
    for _, _, span in entries:
        out |= span
    return out


_QUOTED_RE = re.compile(r'"([^"]*)"' + r"|'([^']*)'")


def _quoted_tokens(rhs_text):
    """Every quoted string in a TOML rhs, in order: `["A", "B"]` -> ['A', 'B']."""
    out = []
    for dq, sq in _QUOTED_RE.findall(rhs_text or ""):
        out.append(dq or sq)
    return out


def _toml_unquote(key):
    """`"src/app/**"` -> `src/app/**`; a bare key is returned unchanged."""
    k = key.strip()
    if len(k) >= 2 and k[0] == k[-1] and k[0] in ('"', "'"):
        return k[1:-1]
    return k


def _toml_table_blocks(text, name):
    """One dict per `[[name]]` array-of-tables block: {key: (lineno, rhs, span)}.

    _toml_targets deliberately flattens these — it prepends the table header, so
    every `[[tool.mypy.overrides]]` block collapses onto the single dotted key
    `tool.mypy.overrides.<flag>` and the blocks alias onto one another (the last
    one wins). That is exactly why per-module mypy relaxations were invisible to
    check_M. Here the block boundaries are kept, so each is judged on its own.

    Single-line values only, which is all a per-module override block uses; a
    bracketed value is captured whole via the same bdelta accounting as
    _toml_targets so a multi-line `module = [...]` list still reads correctly.
    """
    comment_col, instr, bdelta = _toml_scan(text)
    lines = text.split("\n")
    header = "[[" + name + "]]"
    blocks = []
    cur = None
    n = len(lines)
    i = 0
    while i < n:
        ln = i + 1
        if instr.get(ln):
            i += 1
            continue
        raw = lines[i]
        col = comment_col.get(ln)
        if col is not None:
            raw = raw[:col]
        s = raw.strip()
        if not s:
            i += 1
            continue
        if s.startswith("["):
            # Any table header closes the current block; only ours opens one.
            cur = {} if s == header else None
            if cur is not None:
                blocks.append(cur)
            i += 1
            continue
        if cur is None or "=" not in s:
            i += 1
            continue
        key, rhs = s.split("=", 1)
        span = {ln}
        depth = bdelta.get(ln, 0)
        j = i
        while depth > 0 and j + 1 < n:
            j += 1
            ln2 = j + 1
            if instr.get(ln2):
                continue
            raw2 = lines[j]
            col2 = comment_col.get(ln2)
            if col2 is not None:
                raw2 = raw2[:col2]
            rhs += " " + raw2.strip()
            span.add(ln2)
            depth += bdelta.get(ln2, 0)
        cur[_toml_unquote(key)] = (ln, rhs.strip(), span)
        i = j + 1
    return blocks


def _ruleset_parity_findings(practices, text):
    """(errors, warnings) proving pyproject `text` doesn't loosen the declared
    policy in `practices`. Pure: no I/O, so it is unit-testable directly."""
    errs, warns_ = [], []
    rules = practices.get("rulesets")
    if not isinstance(rules, dict):
        return errs, warns_
    ruff = rules.get("ruff") if isinstance(rules.get("ruff"), dict) else {}
    mypy = rules.get("mypy") if isinstance(rules.get("mypy"), dict) else {}
    extend = ruff.get("extend_select")
    deferred = ruff.get("deferred")
    flags = mypy.get("flags")
    dkeys = []
    if isinstance(deferred, dict):
        dkeys = [k for k in deferred if not str(k).startswith("_")]
    elif isinstance(deferred, list):
        dkeys = [x for x in deferred if isinstance(x, str)]

    assigns = _toml_targets(text)
    pragma = _toml_practice_ok_lines(text)
    file_waived = bool(pragma)

    es = assigns.get("tool.ruff.lint.extend-select", [])
    es_text = " ".join(r for (_, r, _) in es)
    es_lines = _span_lines(es)

    if isinstance(extend, list) and extend:
        if not es:
            if not file_waived:
                errs.append(
                    "pyproject.toml: [tool.ruff.lint] extend-select is "
                    "absent; declared ruff policy is unenforced "
                    "(config/practices.json rulesets.ruff.extend_select). "
                    "Add it or `# practice-ok`."
                )
        else:
            # The two `errs.append` calls below are PERF401-suppressed. This is
            # check_M's own body, the gate proving pyproject cannot silently
            # loosen the declared policy. Each guard is a backslash-continued
            # multi-term `and`; folding it into an extend+genexp risks a
            # transcription slip that makes check_M UNDER-report — precisely the
            # failure it exists to prevent. A ~20-family loop has nothing to win.
            for fam in extend:
                if (
                    isinstance(fam, str)
                    and not _rhs_has_family(es_text, fam)
                    and not _line_waived(es_lines, pragma)
                ):
                    errs.append(  # noqa: PERF401 — check_M's body; see above
                        "pyproject.toml: ruff family '%s' declared in "
                        "practices.json is not in extend-select (silent "
                        "loosening)" % fam
                    )
    for fam in dkeys:
        if es and _deferred_active(es_text, fam) and not _line_waived(es_lines, pragma):
            errs.append(  # noqa: PERF401 — check_M's body; see above
                "pyproject.toml: ruff family '%s' is DEFERRED in "
                "practices.json but selected in extend-select "
                "(directly or via a parent prefix / ALL)" % fam
            )

    if isinstance(flags, list):
        for flag in flags:
            if not isinstance(flag, str):
                continue
            entries = assigns.get("tool.mypy." + flag, [])
            state = _flag_state(entries)
            if state == "off" and not _line_waived(_span_lines(entries), pragma):
                errs.append(
                    "pyproject.toml: mypy flag '%s' is set false (declared "
                    "enforced in practices.json) - a silent loosening" % flag
                )
            elif state == "absent" and not file_waived:
                errs.append(
                    "pyproject.toml: mypy flag '%s' declared in "
                    "practices.json is not enforced (absent). Add "
                    "`%s = true` or `# practice-ok`." % (flag, flag)
                )

    errs.extend(_per_file_ignore_findings(ruff, assigns, pragma))
    errs.extend(_mypy_override_findings(mypy, flags, text, pragma))
    return errs, warns_


_PFI_PREFIX = "tool.ruff.lint.per-file-ignores."


def _declared_map(value):
    """A practices.json mapping with the `_comment` documentation keys dropped."""
    if not isinstance(value, dict):
        return None
    return {k: v for k, v in value.items() if not str(k).startswith("_")}


def _per_file_ignore_findings(ruff, assigns, pragma):
    """Every ruff per-file-ignore must be declared in practices.json.

    This closes the widest hole check_M had: `per_file_ignores` was declared as
    data and read by NOTHING (`grep -rn per_file_ignores scripts/` was empty), so
    a single `"**/*.py" = ["B904", "BLE001"]` line switched a family off across
    the whole corpus and the parity gate reported success. A carve-out is policy,
    so it lives in the same declaration as the rest of the policy; pyproject may
    only mirror it. Widening an EXISTING pattern's code list is the same
    loosening as inventing a pattern, so both are errors.
    """
    declared = _declared_map(ruff.get("per_file_ignores"))
    if declared is None:
        return []  # not declared at all -> nothing claimed, nothing proven
    out = []
    for full, entries in sorted(assigns.items()):
        if not full.startswith(_PFI_PREFIX):
            continue
        pattern = _toml_unquote(full[len(_PFI_PREFIX) :])
        for _, rhs, span in entries:
            if _line_waived(span, pragma):
                continue
            if pattern not in declared:
                out.append(
                    "pyproject.toml: per-file-ignore '%s' is not declared in "
                    "config/practices.json rulesets.ruff.per_file_ignores — an "
                    "undeclared carve-out silences the gate. Declare it or "
                    "`# practice-ok`." % pattern
                )
                continue
            allowed = set(declared[pattern] or [])
            extra = sorted(c for c in _quoted_tokens(rhs) if c not in allowed)
            if extra:
                out.append(
                    "pyproject.toml: per-file-ignore '%s' ignores %s, which "
                    "config/practices.json does not declare for it (declared: "
                    "%s)" % (pattern, extra, sorted(allowed))
                )
    return out


# `ignore_errors` is not one of the declared `flags` but is stronger than any of
# them — it drops the module from type-checking entirely — so an override that
# turns it ON is judged with the same rule as one that turns a declared flag off.
_OVERRIDE_KILL_SWITCH = "ignore_errors"

# Declaring `strict` and then relaxing its COMPONENTS per module is the same
# loosening by another name: mypy's --strict is exactly this set, and a block that
# switches these off has un-stricted the module without ever writing
# `strict = false`. Named here because it is a fixed property of mypy, in the same
# spirit as KINDS/LAYERS above — a vocabulary, not a policy. Source: mypy's
# `--strict` flag list.
_MYPY_STRICT_COMPONENTS = (
    "disallow_untyped_defs",
    "disallow_incomplete_defs",
    "disallow_untyped_calls",
    "disallow_untyped_decorators",
    "disallow_any_generics",
    "disallow_subclassing_any",
    "check_untyped_defs",
    "no_implicit_reexport",
    "warn_redundant_casts",
    "warn_unused_ignores",
    "warn_return_any",
    "strict_equality",
)


def _mypy_override_findings(mypy, flags, text, pragma):
    """Per-module `[[tool.mypy.overrides]]` relaxations must be declared too.

    The second hole: check_M only ever read `tool.mypy.<flag>`, while
    `_toml_targets` normalises every override block to `tool.mypy.overrides.<flag>`
    — so a per-module `strict = false`, or an `ignore_errors = true`, was invisible
    AND the blocks aliased onto one dotted key so only the last would have been
    seen anyway. Relaxations are legitimate (the type ratchet is built on them),
    which is the point: legitimate means *declared*, per module, in
    config/practices.json rulesets.mypy.overrides.
    """
    declared = _declared_map(mypy.get("overrides"))
    if declared is None:
        return []
    relaxable = {f for f in (flags or []) if isinstance(f, str)}
    relaxable.add(_OVERRIDE_KILL_SWITCH)
    if "strict" in relaxable:
        relaxable.update(_MYPY_STRICT_COMPONENTS)
    out = []
    for block in _toml_table_blocks(text, "tool.mypy.overrides"):
        modules = _quoted_tokens(block.get("module", (0, "", set()))[1]) or [
            "<unscoped>"
        ]
        for key in sorted(block):
            if key == "module" or key not in relaxable:
                continue
            (ln, rhs, span) = block[key]
            state = _flag_state([(ln, rhs, span)])
            loosens = (
                (state == "on") if key == _OVERRIDE_KILL_SWITCH else (state == "off")
            )
            if not loosens or _line_waived(span, pragma):
                continue
            out.extend(
                "pyproject.toml: [[tool.mypy.overrides]] for '%s' relaxes '%s', "
                "which config/practices.json rulesets.mypy.overrides does not "
                "declare for it — a per-module loosening the gate cannot see. "
                "Declare it (with its removal condition) or `# practice-ok`."
                % (mod, key)
                for mod in modules
                if key not in set(declared.get(mod) or [])
            )
    return out


_TWIN_SUFFIX = ".jinja"
_TWIN_KINDS = ("parity", "divergence", "generated")


def _is_templated(line):
    """A line the twin is licensed to differ on — an expression or control flow."""
    return "{{" in line or "{%" in line


def _twin_parity_findings(files, declared):
    """Errors proving keel's `*.jinja` twins have not silently drifted.

    `files` maps relpath -> text for the whole tree; `declared` is
    config/project.json `template.twins` (plain path -> kind). Pure, so it is
    unit-testable without a tree on disk.

    RENDER-FREE ON PURPOSE, and this bounds what it can claim. check_structure.py
    is stdlib-only and 3.6-safe because it runs in pre-commit on old hosts, so it
    cannot import jinja2 and cannot render a twin to byte-compare it. What it CAN
    prove, and does:

      * every twin is declared, so a sixth one cannot appear unnoticed — the drift
        class re-opening is the thing ADR-K-0005 was told to wait for;
      * the declaration matches reality (a parity/divergence twin has its plain
        sibling; a `generated` one must NOT, because keel is the template);
      * a `parity` twin carries no NON-TEMPLATED line the plain file has lost.
        That is the direction that actually bit: pass 3 widened the lint/type
        scope in `pyproject.toml` and the twin kept `files = ["src"]`, so every
        descendant inherited a weaker gate — silently, since a narrower mypy still
        exits 0;
      * a `divergence` twin actually diverges, so "restoring parity" to
        `.gitignore.jinja` (which would re-ignore `.copier-answers.yml` and kill
        every descendant's upgrade channel) fails loudly.

    The byte-exact rendered comparison stays in tests/integration, where jinja2
    exists. This is the half that runs everywhere, over every twin.
    """
    out = []
    twins = sorted(p for p in files if p.endswith(_TWIN_SUFFIX))
    if not twins:
        return out  # a generated project has none; it inherits the data only
    seen = set()
    for twin in twins:
        plain = twin[: -len(_TWIN_SUFFIX)]
        seen.add(plain)
        kind = declared.get(plain)
        if kind is None:
            out.append(
                "%s: undeclared template twin — add it to config/project.json "
                "template.twins as one of %s, so it cannot drift unnoticed"
                % (twin, list(_TWIN_KINDS))
            )
            continue
        if kind not in _TWIN_KINDS:
            out.append(
                "%s: unknown twin kind %r in config/project.json "
                "template.twins (expected one of %s)" % (plain, kind, list(_TWIN_KINDS))
            )
            continue
        has_plain = plain in files
        if kind == "generated":
            if has_plain:
                out.append(
                    "%s: declared `generated` (copier writes it into a NEW "
                    "project) but keel commits one of its own — keel is the "
                    "template, not a generated project" % plain
                )
            continue
        if not has_plain:
            out.append(
                "%s: declared `%s` but the plain file is missing, so the twin "
                "has nothing to be a twin OF" % (plain, kind)
            )
            continue
        plain_lines = set(files[plain].split("\n"))
        if kind == "divergence":
            if files[plain] == files[twin]:
                out.append(
                    "%s: declared a DIVERGENCE twin but %s reproduces it "
                    "exactly. The divergence is deliberate; restoring parity "
                    "silently removes what the twin exists to change." % (plain, twin)
                )
            continue
        stale = [
            ln
            for ln in files[twin].split("\n")
            if ln.strip() and not _is_templated(ln) and ln not in plain_lines
        ]
        out.extend(
            "%s: line is in the twin but not in %s, so a generated "
            "project would get a stale copy: %s" % (twin, plain, ln.strip())
            for ln in stale[:5]
        )
    for plain in sorted(declared):
        if str(plain).startswith("_") or plain in seen:
            continue
        out.append(
            "config/project.json template.twins declares '%s' but no '%s%s' "
            "exists — delete the declaration or restore the twin"
            % (plain, plain, _TWIN_SUFFIX)
        )
    return out


def check_N():
    """Template twin parity — see _twin_parity_findings for what this can and
    cannot prove without a jinja renderer. Silent in a generated project (no
    twins). Waivable with `# practice-ok`? No: a twin has no line to hang a
    pragma on that copier would not then render."""
    declared = _declared_twins()
    files = {}
    for dirpath, dirnames, filenames in walk(ROOT):
        del dirnames
        for name in filenames:
            full = os.path.join(dirpath, name)
            relp = rel(full).replace(os.sep, "/")
            # Only the twins and the plain files they are twins OF — the rest of
            # the tree is other checks' business and reading it all would be waste.
            if not (name.endswith(_TWIN_SUFFIX) or relp in declared):
                continue
            text = _read_text(full, err)
            if text is not None:
                files[relp] = text
    for m in _twin_parity_findings(files, declared):
        err(m)


def _declared_twins():
    """config/project.json `template.twins` (plain path -> kind), `_`-keys dropped."""
    manifest = _read_json_config(os.path.join("config", "project.json"))
    template = manifest.get("template") if isinstance(manifest, dict) else None
    twins = template.get("twins") if isinstance(template, dict) else None
    if not isinstance(twins, dict):
        return {}
    return {k: v for k, v in twins.items() if not str(k).startswith("_")}


def check_M():
    """Ruleset parity: pyproject.toml must not silently loosen the lint/type
    policy declared as DATA in config/practices.json rulesets. Errs on a declared
    ruff family missing from extend-select, a declared mypy flag off/absent, or a
    'deferred' family silently selected. Degrades to a WARN if pyproject is
    MISSING (a generated project may not carry one); a pyproject that is present
    but unreadable ERRs, because that is this gate going dark on a file that is
    right there. Waivable with `# practice-ok`."""
    practices = _load_practices()
    if not isinstance(practices.get("rulesets"), dict):
        return
    path = os.path.join(ROOT, "pyproject.toml")
    if not os.path.isfile(path):
        warn("pyproject.toml: not found; ruleset parity unenforced")
        return
    text = _read_text(path, err)  # present but unreadable -> parity unprovable
    if text is None:
        return
    errs, warns_ = _ruleset_parity_findings(practices, text)
    for m in errs:
        err(m)
    for m in warns_:
        warn(m)


def _module_meta(doc):
    """title:/summary: (etc.) lines of a module docstring, extracted with EXACTLY
    build_corpus._docstring_meta's grammar: strip the line, match a known key
    before the first colon, strip the value, last occurrence wins. Duplicated,
    not imported — scripts/jobs/build_corpus.py is $(PY)-only and this file runs
    under the 3.6 pre-commit interpreter, so a shared import would couple the
    interpreter floors. The two grammars are pinned to each other by
    tests/unit/scripts/test_check_o.py::test_grammar_matches_the_corpus_reader_exactly."""
    meta = {}
    for line in doc.splitlines():
        s = line.strip()
        if ":" in s and s.split(":", 1)[0] in (
            "title",
            "summary",
            "layer",
            "public_api",
            "owner",
            "visibility",
            "effect",
            "rerun",
            "rerun_proof",
        ):
            k, _, v = s.partition(":")
            meta[k.strip()] = v.strip()
    return meta


def _module_header_findings(files):
    """files: {relpath: source text} -> error strings. Pure; the walk is check_O's.

    Unparseable sources are skipped: check_D already warns on them over the same
    roots, and a second report here would be noise. (Corollary: on an OLD host
    interpreter a module using newer syntax parses as SyntaxError and is skipped
    — the project interpreter's run, in CI and `make check`, is the enforcing one.)
    """
    errs = []
    for relpath in sorted(files):
        try:
            tree = ast.parse(files[relpath], filename=relpath)
        except UNPARSEABLE:
            continue
        doc = ast.get_docstring(tree)
        if not doc:
            errs.append(
                "%s: module has no docstring -- build_corpus cannot index it, "
                "so it is invisible to every corpus query (ADR-K-0008; see "
                "docs/guides/python-style.md)" % relpath
            )
            continue
        missing = [k for k in ("title", "summary") if not _module_meta(doc).get(k)]
        if missing:
            errs.append(
                "%s: module docstring lacks explicit %s -- the corpus falls "
                "back to the filename / first prose line and labels the result "
                "authored (ADR-K-0008; see docs/guides/python-style.md)"
                % (relpath, " and ".join(m + ":" for m in missing))
            )
    return errs


def check_O():
    """ERROR when a CODE_ROOTS module lacks the machine-readable header the
    corpus reads (ADR-K-0008). A docstring that merely EXISTS is the trap this
    closes: build_corpus falls back to the filename and the first prose line
    and labels the result 'authored', and a module with no docstring at all is
    silently dropped from the corpus — an agent's map of the project is then
    confidently incomplete, at exit 0."""
    files = {}
    for croot in CODE_ROOTS:
        base = os.path.join(ROOT, croot)
        if not os.path.isdir(base):
            continue
        for dirpath, _, filenames in walk(base):
            for f in filenames:
                if not f.endswith(".py"):
                    continue
                full = os.path.join(dirpath, f)
                try:
                    # utf-8-sig, here and at every .py read that feeds ast (in
                    # build_corpus too): a BOM file is valid importable Python
                    # (the runtime strips the BOM), but read as plain utf-8 the
                    # U+FEFF makes ast.parse raise and the except-swallow turned
                    # exactly those files back into silent drops (ADR-K-0008
                    # review). utf-8-sig on a BOM-less file is byte-identical.
                    with open(full, encoding="utf-8-sig") as fh:
                        files[rel(full)] = fh.read()
                except UNREADABLE:
                    continue  # unreadable is reported by the checks keyed on it
    for e_ in _module_header_findings(files):
        err(e_)


# --- check_P: Makefile help parity --------------------------------------------
#
# A `## ` annotation on a target line is a promise that `make help` lists it.
# The help recipe keeps that promise with a grep pattern, and the pattern is
# the only place the promise can quietly break: `e2e` was annotated from the
# day it existed and never once listed, because `[a-zA-Z_-]` has no digits.
# So this check does not restate what a listable target looks like — it reads
# the recipe's own pattern out of the Makefile and applies it, which is the one
# design under which the check cannot agree with a wrong pattern. What it
# cannot model it says so: a grep without -E (basic-regex semantics Python's
# re does not have), a pattern held in a variable it cannot expand, a second
# selecting grep in the pipeline, an include it cannot resolve — each is a
# WARN that says 'unverified', never a pass.

# A target line as the ANNOTATION convention defines it: a name, a colon that
# is not part of `:=`, anything, then `## `. Deliberately wider than any help
# recipe's pattern — the gap between the two IS the finding. Excludes what no
# help output could list by name: a `$(VAR)`-named target and the dotted
# special targets (`.PHONY`, `.SUFFIXES`, ...). One line naming two targets
# (`a b: ## x`) is outside both patterns and so outside this check.
_ANNOTATED_TARGET = re.compile(r"^(?!\.[A-Z_]+\s*:)([^\s:#=$]+)\s*:(?!=)[^#\n]*##\s")
_INCLUDE_LINE = re.compile(r"^\s*(-?include|sinclude)\s+(.+?)\s*$", re.MULTILINE)
_HELP_TARGET = re.compile(r"^help\s*:(?!=)", re.MULTILINE)
# One grep in a pipeline: the command, its flags, its quoted pattern, and the
# operands up to the next pipe.
_GREP_CALL = re.compile(
    r"""(?P<cmd>\b[ef]?grep)\s+(?P<flags>(?:-[A-Za-z]+\s+)*)"""
    r"""(?:'(?P<sq>[^']*)'|"(?P<dq>[^"]*)")(?P<rest>[^|]*)"""
)
_MAKE_VAR = re.compile(r"\$[({]([A-Za-z_][A-Za-z0-9_]*)[)}]")
_MAKE_ASSIGN = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*[:?+]?=\s*(.*?)\s*$", re.MULTILINE
)
_MAKE_CONDITIONAL = re.compile(r"^(ifeq|ifneq|ifdef|ifndef|else|endif)\b")
_UNFOLD = re.compile(r"\\\n[ \t]*")
_MAKEFILE_LIST = "$(MAKEFILE_LIST)"
# POSIX bracket classes grep -E accepts and Python's re does not — translated so
# the widening a user is most likely to write does not turn the check dark.
_POSIX_CLASSES = (
    ("[:alnum:]", "A-Za-z0-9"),
    ("[:alpha:]", "A-Za-z"),
    ("[:digit:]", "0-9"),
    ("[:lower:]", "a-z"),
    ("[:upper:]", "A-Z"),
    ("[:space:]", r"\s"),
)


def _recipe_command(line):
    """A recipe line as the shell sees it: the tab and any `@`/`-`/`+` prefix
    dropped, a line that is a shell comment reduced to nothing, and a trailing
    unquoted ` #comment` cut off."""
    cmd = line.lstrip("\t ").lstrip("@-+").lstrip()
    if cmd.startswith("#"):
        return ""
    quote = None
    for i, ch in enumerate(cmd):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and i > 0 and cmd[i - 1] in " \t":
            return cmd[:i].rstrip()
    return cmd


def _help_recipe(text):
    """The `help` target's recipe as one string (continuations unfolded, blank
    and comment lines skipped as make skips them), or None without a `help:`."""
    m = _HELP_TARGET.search(text)
    if not m:
        return None
    recipe = []
    for line in _UNFOLD.sub(" ", text[m.end() :]).split("\n")[1:]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith("\t"):
            break
        recipe.append(line.strip())
    return " ".join(recipe)


def _expand_make_vars(pattern, makefiles):
    """`$(NAME)` / `${NAME}` replaced from a plain `NAME = value` assignment in
    any of the makefiles (one level, no functions). Unknown names stay put."""
    assigned = {}
    for _, text in makefiles:
        for name, value in _MAKE_ASSIGN.findall(text):
            assigned.setdefault(name, value)
    return _MAKE_VAR.sub(lambda m: assigned.get(m.group(1), m.group(0)), pattern)


def _compile_grep(pattern, flags):
    """A grep -E pattern as a Python regex, honouring -i; raises re.error."""
    for posix, python in _POSIX_CLASSES:
        pattern = pattern.replace(posix, python)
    return re.compile(pattern, re.IGNORECASE if "i" in flags else 0)


def _help_parity_findings(makefiles):
    """makefiles: ordered [(relpath, text)] — the root Makefile then its includes,
    i.e. what `$(MAKEFILE_LIST)` would hold. Returns (errs, warns). Pure; the
    walk and include resolution are check_P's.

    Silent when no makefile declares a `help` target (nothing lists the
    annotations, so nothing can hide one). WARNs, never errs, for every shape
    it cannot model — parity is then unverified and says so, rather than
    reporting a green it did not earn.
    """
    errs, warns = [], []
    if not makefiles:
        return errs, warns
    recipe, help_in = None, None
    for relpath, text in makefiles:
        recipe = _help_recipe(text)
        if recipe is not None:
            help_in = relpath
            break
    if recipe is None:
        return errs, warns
    unverified = "%s: help parity unverified -- " % help_in
    greps = [
        (
            m.group("cmd"),
            m.group("flags").replace("-", ""),
            m.group("sq") if m.group("sq") is not None else m.group("dq"),
            m.group("rest"),
        )
        for m in _GREP_CALL.finditer(recipe)
    ]
    if not greps:
        warns.append(
            unverified + "the 'help' recipe hands grep no quoted pattern this check "
            "can read, so an annotated target may be hidden from 'make help' "
            "without anything noticing"
        )
        return errs, warns
    cmd, flags, raw, rest = greps[0]
    if "F" in flags:
        warns.append(
            unverified
            + "the help recipe's grep -F matches fixed strings, which this check does not model"
        )
        return errs, warns
    if cmd != "egrep" and "E" not in flags and "P" not in flags:
        warns.append(
            unverified + "the help recipe's grep uses basic-regex semantics (no -E), "
            "under which '+' and '?' are literal and this check has no engine -- "
            "use grep -E"
        )
        return errs, warns
    if _MAKEFILE_LIST not in rest:
        warns.append(
            unverified + "the help recipe's grep reads '%s' rather than %s, so what "
            "it lists may not be what the makefiles annotate"
            % (rest.strip() or "(nothing)", _MAKEFILE_LIST)
        )
        return errs, warns
    pattern = _expand_make_vars(raw, makefiles)
    if _MAKE_VAR.search(pattern):
        warns.append(
            unverified + "the help recipe's pattern '%s' holds a make variable this "
            "check cannot expand (%s)"
            % (raw, ", ".join(sorted(set(_MAKE_VAR.findall(pattern)))))
        )
        return errs, warns
    excluded = []
    for later_cmd, later_flags, later_raw, _ in greps[1:]:
        if "v" not in later_flags:
            warns.append(
                unverified + "the help recipe pipes through a second selecting %s "
                "('%s'), a pipeline this check does not model" % (later_cmd, later_raw)
            )
            return errs, warns
        excluded.append((later_raw, later_flags))
    try:
        listed = _compile_grep(pattern, flags)
        hidden_on_purpose = [_compile_grep(p, f) for p, f in excluded]
    except re.error as e:
        warns.append(
            unverified + "the help recipe's pattern '%s' is not one this check can "
            "apply (%s)" % (raw, e)
        )
        return errs, warns
    for relpath, text in makefiles:
        where = "" if relpath == help_in else " (in %s)" % help_in
        for lineno, line in enumerate(text.split("\n"), 1):
            m = _ANNOTATED_TARGET.match(line)
            if not m or listed.search(line):
                continue
            if any(x.search(line) for x in hidden_on_purpose):
                continue  # the author's own `grep -v` hides it; that is a choice
            errs.append(
                "%s:%d: target '%s' carries a '## ' help annotation but the help "
                "recipe's pattern '%s'%s does not match it, so 'make help' hides "
                "it -- widen the pattern%s (or drop the annotation)"
                % (relpath, lineno, m.group(1), raw, where, where and " in " + help_in)
            )
    return errs, warns


def _includes(text):
    """[(directive, name)] for every include line, one entry per named file."""
    return [
        (directive, name)
        for directive, names in _INCLUDE_LINE.findall(text)
        for name in names.split()
    ]


def check_P():
    """ERROR when a `## `-annotated target is one the `help` recipe's own grep
    pattern cannot list. Reads `Makefile` and, recursively, every file an
    `include`/`-include`/`sinclude` line names (walk_makefiles: what
    `$(MAKEFILE_LIST)` holds), so an annotation in an included makefile is held
    to the same promise. An include named through a variable or a wildcard is
    not expanded here and is a WARN; an absent optional include is make's own
    'if present' and silent. Silent when there is no Makefile or no `help`
    target. check_W walks the same makefiles and leaves their reporting here."""
    makefiles = walk_makefiles(ROOT, warn, err)
    errs, warns_ = _help_parity_findings(makefiles)
    for m in errs:
        err(m)
    for m in warns_:
        warn(m)


# --- check_Q: cross-references resolve ----------------------------------------
#
# A document's outbound references are the edges of the knowledge graph the
# corpus is built from, and they rot silently: a renumbered CONVENTIONS section
# or a moved guide leaves every citation pointing at the wrong thing, at exit
# 0. Two reference forms are recognised, both closed:
#   - a relative Markdown link `[text](path#anchor)` in prose (fenced code,
#     inline code and HTML comments are illustrations, not references);
#   - a section citation `§N`, which cites CONVENTIONS.md unless a document is
#     named in front of it (`docs/guides/python-style.md §3`, the path in
#     backticks or not, a comma or a line break between them or not). Bare
#     `§N` never means "this document": that reading is ambiguous the moment a
#     guide numbers its own sections, so the house grammar names the document
#     instead. A `§N` inside code IS read (a quoted help string cites the same
#     section a sentence does); a link inside code is not.

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_INLINE_CODE = re.compile(r"(`+)(.+?)\1")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_MD_LINK = re.compile(
    r"!?\[[^\]]*\]\(\s*(?:<([^>]*)>|([^)\s]+))(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)"
)
_URL_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_ATX_HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*$")
_SETEXT_UNDERLINE = re.compile(r"^ {0,3}(=+|-+)\s*$")
_HTML_ANCHOR = re.compile(r"""<a\s+(?:id|name)=["']([^"']+)["']""")
_NUMBERED_HEADING = re.compile(r"^#{1,6}\s+(\d+)\.")
_SECTION_CITE = re.compile(r"(?:`?([A-Za-z0-9_./-]+\.md)`?,?\s+)?§\s*(\d+)")
_CONVENTIONS_DOC = "CONVENTIONS.md"
# Where a `§N` may appear: prose, and the code/config whose docstrings and help
# strings cite the conventions (check_structure's own header does).
_CITING_SUFFIXES = (".md", ".py", ".toml", ".yml", ".yaml", ".jinja", ".example")
_CITING_NAMES = ("Makefile",)


def _frontmatter_end(lines):
    """Index of the first body line: past a leading `---` block, else 0."""
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return i + 1
    return 0


def _unfenced_lines(text):
    """The document's lines with fenced code blocks and HTML comments blanked,
    numbering kept. A fence closes only on the same character, at least as
    long (CommonMark), so a ```` block may show a ``` fence as content."""
    out, fence = [], None
    text = _HTML_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    for line in text.split("\n"):
        m = _FENCE.match(line)
        closes = (
            m
            and fence is not None
            and m.group(1)[0] == fence[0]
            and len(m.group(1)) >= len(fence)
        )
        if m and (fence is None or closes):
            fence = m.group(1) if fence is None else None
            out.append("")
            continue
        out.append("" if fence is not None else line)
    return out


def _prose_lines(text):
    """_unfenced_lines with inline code spans blanked too — what a renderer
    would treat as prose, so a link written inside backticks is not a link."""
    return [_INLINE_CODE.sub("", line) for line in _unfenced_lines(text)]


def _heading_slug(heading):
    """GitHub's anchor for a heading: the heading as RENDERED (code spans kept
    verbatim, link markup reduced to its text, emphasis markers dropped),
    lowercased, everything but word characters, spaces and hyphens removed,
    spaces to hyphens. Leading `#`s and optional closing `#`s are markup."""
    t = re.sub(r"^#{1,6}\s*", "", heading.strip())
    t = re.sub(r"\s*#+\s*$", "", t)
    spans = []

    def keep(m):
        spans.append(m.group(2))
        return "\x00%d\x00" % (len(spans) - 1)

    t = _INLINE_CODE.sub(keep, t)
    t = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = t.replace("*", "")
    t = re.sub(r"(?<!\w)_+(\S(?:.*?\S)?)_+(?!\w)", r"\1", t)
    t = re.sub(r"\x00(\d+)\x00", lambda m: spans[int(m.group(1))], t)
    t = re.sub(r"[^\w\- ]", "", t.lower())
    return t.replace(" ", "-")


def _anchors(text):
    """Every anchor a renderer would emit for `text`: ATX and setext headings
    (repeats numbered -1, -2) plus explicit `<a id=...>` / `<a name=...>`."""
    counts, anchors = {}, set()
    lines = _unfenced_lines(text)
    body = lines[_frontmatter_end(lines) :]
    for i, line in enumerate(body):
        heading = None
        m = _ATX_HEADING.match(line)
        if m:
            heading = m.group(1)
        elif (
            line.strip()
            and not line.lstrip().startswith(("|", "#", "-", "=", ">", "*", "+"))
            and i + 1 < len(body)
            and _SETEXT_UNDERLINE.match(body[i + 1])
        ):
            heading = line.strip()
        if heading is not None:
            slug = _heading_slug(heading)
            n = counts.get(slug, 0)
            counts[slug] = n + 1
            anchors.add(slug if n == 0 else "%s-%d" % (slug, n))
        anchors.update(_HTML_ANCHOR.findall(line))
    return anchors


def _numbered_sections(text):
    """The N of every numbered heading (`N.` at any level) outside fenced code."""
    found = set()
    for line in _unfenced_lines(text):
        m = _NUMBERED_HEADING.match(line)
        if m:
            found.add(int(m.group(1)))
    return found


def _resolve_link(base, path):
    """`path` as written in a doc under directory `base` -> a root-relative path
    ('' is the root), or None when it climbs above the repository."""
    joined = path.lstrip("/") if path.startswith("/") else posixpath.join(base, path)
    resolved = posixpath.normpath(joined)
    if resolved == ".." or resolved.startswith("../"):
        return None
    return "" if resolved == "." else resolved


def _link_findings(relpath, text, files, tree):
    errs = []
    base = posixpath.dirname(relpath)
    for lineno, line in enumerate(_prose_lines(text), 1):
        for m in _MD_LINK.finditer(line):
            target = m.group(1) if m.group(1) is not None else m.group(2)
            if _URL_SCHEME.match(target):
                continue
            path, _, fragment = target.partition("#")
            doc = relpath
            if path:
                doc = _resolve_link(base, unquote(path))
                if doc is None:
                    errs.append(
                        "%s:%d: link target '%s' escapes the repository -- point it "
                        "at a file that ships" % (relpath, lineno, target)
                    )
                    continue
                if doc and doc not in tree:
                    errs.append(
                        "%s:%d: link target '%s' does not exist (resolves to '%s') -- "
                        "fix the path, restore the file, or unlink the text"
                        % (relpath, lineno, target, doc)
                    )
                    continue
            if fragment and doc.endswith(".md") and doc in files:
                anchors = _anchors(files[doc])
                if fragment not in anchors:
                    shown = sorted(anchors)
                    listed = ", ".join(shown[:8]) + (", ..." if len(shown) > 8 else "")
                    errs.append(
                        "%s:%d: link anchor '#%s' matches no heading of %s (its "
                        "anchors: %s) -- fix the fragment or add the heading"
                        % (relpath, lineno, fragment, doc, listed or "none")
                    )
    return errs


def _citation_findings(relpath, text, files, tree, sections_of):
    errs = []
    base = posixpath.dirname(relpath)
    for m in _SECTION_CITE.finditer(text):
        lineno = text.count("\n", 0, m.start(2)) + 1
        named, number = m.group(1), int(m.group(2))
        cite = " ".join(m.group(0).split())
        doc = _CONVENTIONS_DOC
        if named:
            # Root-relative first (the house spelling), then as the citing
            # document's neighbour.
            doc = (
                named
                if named in tree
                else posixpath.normpath(posixpath.join(base, named))
            )
            if doc not in tree:
                errs.append(
                    "%s:%d: '%s' cites %s, which exists neither at the root nor "
                    "relative to %s/ -- name the document as it sits in the tree, "
                    "or restore it" % (relpath, lineno, cite, named, base or ".")
                )
                continue
        elif doc not in tree:
            errs.append(
                "%s:%d: bare '%s' cites %s (the default for an unnamed §), which "
                "does not exist -- name the document in front of the §, or "
                "restore %s" % (relpath, lineno, cite, doc, doc)
            )
            continue
        present = sections_of(doc)
        if present is None:
            errs.append(
                "%s:%d: '%s' cites %s, which this check could not read"
                % (relpath, lineno, cite, doc)
            )
        elif not present:
            errs.append(
                "%s:%d: '%s' cites %s, which has no numbered heading at all -- "
                "number its sections or drop the §" % (relpath, lineno, cite, doc)
            )
        elif number not in present:
            errs.append(
                "%s:%d: '%s' names no numbered section of %s (present: %s) -- "
                "renumber the citation"
                % (
                    relpath,
                    lineno,
                    cite,
                    doc,
                    ", ".join(str(n) for n in sorted(present)),
                )
            )
    return errs


def _crossref_findings(files, tree, scan=None):
    """files: {relpath: text} for every citing file, under EVERY name it has (a
    symlinked twin is registered twice so a link to either name resolves);
    tree: every path (file or directory, root-relative, '/'-separated) the
    walk saw; scan: the names to read references FROM, one per real file
    (default: all). -> error strings. Pure; the walk is check_Q's. Links are
    read from `.md` files only (a `.jinja` twin's rendered links are the
    generation tests' business); citations from every citing suffix."""
    errs = []
    cache = {}

    def sections_of(doc):
        if doc not in cache:
            text = files.get(doc)
            cache[doc] = None if text is None else _numbered_sections(text)
        return cache[doc]

    for relpath in sorted(files if scan is None else scan):
        text = files[relpath]
        name = posixpath.basename(relpath)
        if name.endswith(".md"):
            errs.extend(_link_findings(relpath, text, files, tree))
        if name in _CITING_NAMES or name.endswith(_CITING_SUFFIXES):
            errs.extend(_citation_findings(relpath, text, files, tree, sections_of))
    return errs


def check_Q():
    """ERROR when a relative Markdown link or a `§N` citation names nothing.
    Walks every citing file, registers its text under every name it has
    (CLAUDE.md and the AGENT.md it links to both resolve), reads references
    from each real file once (under its alphabetically first name), and
    records every path the walk saw so a link to a directory or a non-text
    file resolves without reading it."""
    files, tree, first_name = {}, set(), {}
    for dirpath, _, filenames in walk(ROOT):
        reldir = rel(dirpath).replace(os.sep, "/")
        if reldir != ".":
            tree.add(reldir)
        for f in filenames:
            full = os.path.join(dirpath, f)
            relp = f if reldir == "." else reldir + "/" + f
            tree.add(relp)
            if not (f in _CITING_NAMES or f.endswith(_CITING_SUFFIXES)):
                continue
            text = _read_text(full, err)  # present but undecodable: a gate defect
            if text is None:
                continue
            files[relp] = text
            real = os.path.realpath(full)
            if real not in first_name or relp < first_name[real]:
                first_name[real] = relp
    for m in _crossref_findings(files, tree, scan=set(first_name.values())):
        err(m)


# --- check_R: check catalogue parity ------------------------------------------
#
# docs/guides/deterministic-checks.md is the roster of every deterministic
# check: what runs, at which tier, wired how. A roster is only worth reading if
# it agrees with the triggers, and nothing held the two together: the catalogue
# listed `cdmon_sync.py --check` at the error tier for as long as it existed
# while `make check-all` never ran it. Six directions, one membership:
#   - every catalogued script exists;
#   - an error-tier row is reachable from `make check-all` (a gate nobody runs
#     is a claim);
#   - a report row is run by SOME make target (a report nobody runs is the
#     `make advise` precedent: documented, invoked by nothing);
#   - every script `check-all` reaches is catalogued;
#   - the hooks table and .pre-commit-config.yaml declare the same hook ids,
#     and neither exists without the other.
# Catalogued checks are `.py` paths; a check in another language is reached
# through a `.py` adapter, as CONVENTIONS §9 asks anyway.

_CATALOGUE_DOC = "docs/guides/deterministic-checks.md"
_PRECOMMIT_CONFIG = ".pre-commit-config.yaml"
_CHECK_ALL = "check-all"
_GATE_TIERS = ("error", "error*", "report")
_BACKTICKED = re.compile(r"`([^`]+)`")
_PY_SCRIPT = re.compile(r"(?<![\w./-])([\w./-]+\.py)\b")
_MAKE_RULE = re.compile(r"^([^\s:#=$]+)\s*:(?!=)([^#\n]*?)\s*(?:##.*)?$")
_MAKE_RECURSION = re.compile(
    r"\$[({]MAKE[)}]\s+(?:-\S+\s+)*([A-Za-z0-9_][A-Za-z0-9_.-]*)"
)
_TABLE_RULE = re.compile(r"^\|\s*:?-+")
_HOOK_ID = re.compile(r"^\s*-\s*id:\s*(\S+)", re.MULTILINE)


def _pipe_table(text, required_columns):
    """The first pipe table (outside fenced code) whose header carries every
    required column -> (header cells, lowercased; row cell lists), else None."""
    lines = _unfenced_lines(text)
    for i, line in enumerate(lines):
        if not line.startswith("|") or i + 1 >= len(lines):
            continue
        header = [c.strip().lower() for c in line.strip().strip("|").split("|")]
        if not all(col.lower() in header for col in required_columns):
            continue
        if not _TABLE_RULE.match(lines[i + 1]):
            continue
        rows = []
        for row in lines[i + 2 :]:
            if not row.startswith("|"):
                break
            rows.append([c.strip() for c in row.strip().strip("|").split("|")])
        return header, rows
    return None


def _make_rules(text):
    """{target: ([prerequisites], [recipe commands])} as make would read it:
    `\\`-continuations unfolded, blank and comment lines skipped, conditional
    directives transparent, `$(MAKE) target` in a recipe counted as an edge,
    `$(...)` prerequisites and the dotted special targets dropped. Recipe
    lines are kept as the shell sees them (see _recipe_command)."""
    rules, current = {}, None
    for line in _UNFOLD.sub(" ", text).split("\n"):
        if line.startswith("\t"):
            if current is not None:
                cmd = _recipe_command(line)
                if cmd:
                    rules[current][1].append(cmd)
                    rules[current][0].extend(_MAKE_RECURSION.findall(cmd))
            continue
        if (
            not line.strip()
            or line.lstrip().startswith("#")
            or _MAKE_CONDITIONAL.match(line)
        ):
            continue
        m = _MAKE_RULE.match(line)
        if not m or re.match(r"^\.[A-Z_]+$", m.group(1)):
            current = None
            continue
        current = m.group(1)
        prereqs = [x for x in m.group(2).split() if not x.startswith("$")]
        rules.setdefault(current, ([], []))[0].extend(prereqs)
    return rules


def _scripts_reachable_from(rules, target):
    """Every `*.py` path a recipe command mentions, over `target` and its
    prerequisites transitively (a missing prerequisite is make's error, not
    this check's)."""
    seen, stack, scripts = set(), [target], set()
    while stack:
        t = stack.pop()
        if t in seen or t not in rules:
            continue
        seen.add(t)
        prereqs, recipe = rules[t]
        stack.extend(prereqs)
        for cmd in recipe:
            scripts.update(_PY_SCRIPT.findall(cmd))
    return scripts


def _catalogue_parity_findings(catalogue, makefile, precommit, tree):
    """catalogue / makefile / precommit: file text, or None when absent. tree:
    every file path (root-relative, '/'-separated). -> (errs, warns). Pure;
    the reads are check_R's. No catalogue is silent; a catalogue whose checks
    table cannot be read, no Makefile, or a Makefile with no `check-all`, is
    a stated WARN."""
    errs, warns = [], []
    if catalogue is None:
        return errs, warns
    table = _pipe_table(catalogue, ("Script", "Gate?"))
    if table is None:
        warns.append(
            "%s: catalogue parity unverified -- no checks table with 'Script' and "
            "'Gate?' columns this check can read" % _CATALOGUE_DOC
        )
        return errs, warns
    header, rows = table
    script_col, tier_col = header.index("script"), header.index("gate?")
    catalogued = {}
    for row in rows:
        if len(row) < len(header):
            errs.append(
                "%s: a checks-table row has %d cell(s) but the header has %d (row: "
                "%s) -- complete the row"
                % (_CATALOGUE_DOC, len(row), len(header), " | ".join(row))
            )
            continue
        m = _BACKTICKED.search(row[script_col])
        if not m:
            errs.append(
                "%s: a checks-table row names no script in backticks in its Script "
                "column (row: %s) -- name the script it catalogues"
                % (_CATALOGUE_DOC, " | ".join(row))
            )
            continue
        script, tier = m.group(1).split()[0], row[tier_col]
        if tier not in _GATE_TIERS:
            errs.append(
                "%s: the Gate? cell for %s is '%s', not one of %s -- pick the tier "
                "it actually runs at"
                % (_CATALOGUE_DOC, script, tier, ", ".join(_GATE_TIERS))
            )
        if script not in tree:
            errs.append(
                "%s: catalogue names %s, which does not exist -- drop the row or "
                "restore the script" % (_CATALOGUE_DOC, script)
            )
        catalogued[script] = tier
    if makefile is None:
        warns.append(
            "%s: catalogue parity unverified -- no Makefile, so which catalogued "
            "checks actually run cannot be known" % _CATALOGUE_DOC
        )
    else:
        rules = _make_rules(makefile)
        if _CHECK_ALL not in rules:
            warns.append(
                "Makefile: catalogue parity unverified -- no '%s' target, so which "
                "error-tier rows of %s run, and which scripts run uncatalogued, "
                "cannot be known" % (_CHECK_ALL, _CATALOGUE_DOC)
            )
        else:
            gated = _scripts_reachable_from(rules, _CHECK_ALL)
            anywhere = set()
            for target in rules:
                anywhere.update(_scripts_reachable_from(rules, target))
            for script in sorted(catalogued):
                tier = catalogued[script]
                if tier.startswith("error") and script not in gated:
                    errs.append(
                        "%s: catalogue claims %s gates at tier '%s' but 'make %s' "
                        "never runs it -- reach it from %s or change the row"
                        % (_CATALOGUE_DOC, script, tier, _CHECK_ALL, _CHECK_ALL)
                    )
                elif tier == "report" and script not in anywhere:
                    errs.append(
                        "%s: catalogue lists %s as a report but no make target runs "
                        "it -- wire it into a target or drop the row"
                        % (_CATALOGUE_DOC, script)
                    )
            errs.extend(
                "Makefile: 'make %s' runs %s, which the catalogue (%s) does not list "
                "-- add a row for it, or stop running it from %s"
                % (_CHECK_ALL, script, _CATALOGUE_DOC, _CHECK_ALL)
                for script in sorted(gated - set(catalogued))
            )
    hooks = _pipe_table(catalogue, ("Hook id", "Calls"))
    declared = set(_HOOK_ID.findall(precommit)) if precommit is not None else set()
    if hooks is None:
        if declared:
            errs.append(
                "%s: %s declares hook(s) %s but the catalogue has no hooks table "
                "('Hook id' / 'Calls') -- add one, so every trigger is catalogued"
                % (_CATALOGUE_DOC, _PRECOMMIT_CONFIG, ", ".join(sorted(declared)))
            )
        return errs, warns
    id_col = hooks[0].index("hook id")
    listed = set()
    for row in hooks[1]:
        if len(row) > id_col:
            listed.update(_BACKTICKED.findall(row[id_col]))
    if precommit is None:
        if listed:
            errs.append(
                "%s: the hooks table names %s but there is no %s -- restore the "
                "config or delete the table"
                % (
                    _CATALOGUE_DOC,
                    ", ".join("'%s'" % h for h in sorted(listed)),
                    _PRECOMMIT_CONFIG,
                )
            )
        return errs, warns
    errs.extend(
        "%s: hook '%s' is declared in %s but the hooks table omits it -- add a row for it"
        % (_CATALOGUE_DOC, hook, _PRECOMMIT_CONFIG)
        for hook in sorted(declared - listed)
    )
    errs.extend(
        "%s: the hooks table names '%s' but %s declares no such hook -- drop the "
        "row or declare the hook" % (_CATALOGUE_DOC, hook, _PRECOMMIT_CONFIG)
        for hook in sorted(listed - declared)
    )
    return errs, warns


def _optional_text(relpath):
    """A root file's text, None when absent; present-but-unreadable is an error
    (the check keyed on it would otherwise go dark)."""
    full = os.path.join(ROOT, relpath)
    return _read_text(full, err) if os.path.isfile(full) else None


def check_R():
    """ERROR when the catalogue of deterministic checks and the triggers that
    run them (Makefile, .pre-commit-config.yaml) disagree on one membership.
    Silent when there is no catalogue; the shapes it cannot read are WARNs."""
    catalogue = _optional_text(_CATALOGUE_DOC)
    if catalogue is None:
        return
    tree = set()
    for dirpath, _, filenames in walk(ROOT):
        reldir = rel(dirpath).replace(os.sep, "/")
        for f in filenames:
            tree.add(f if reldir == "." else reldir + "/" + f)
    errs, warns_ = _catalogue_parity_findings(
        catalogue, _optional_text("Makefile"), _optional_text(_PRECOMMIT_CONFIG), tree
    )
    for m in errs:
        err(m)
    for m in warns_:
        warn(m)


# --- check_S: roster parity ---------------------------------------------------
#
# A README that says "## What ships here" is making a claim about its
# directory, and the claim rots the day a file is added or removed. The roster
# is opt-in by that heading (no README is retro-failed); once declared it is
# held to the tree both ways, and every row must carry a `Not for` cell — what
# a reader must NOT reach for the member to do, naming the sibling that does.
# That cell is the discriminator a bare listing never states: the answer to
# "why are these two separate things?"

_ROSTER_HEADING = "What ships here"
_ROSTER_BOILERPLATE = {
    "README.md",
    "AGENT.md",
    "CLAUDE.md",
    "__init__.py",
    "__pycache__",
}
_EMPTY_CELLS = {"", "-", "—", "n/a", "none"}


def _roster_members(listing, isdir):
    """The members of a directory from its listing: everything but the labels,
    packaging, hidden entries, ignored dirs and `.jinja` template twins (keel-as-
    a-template metadata, check_N's business); a directory carries a slash."""
    members = set()
    for name in listing:
        if name in _ROSTER_BOILERPLATE or name in IGNORE_DIRS or name.startswith("."):
            continue
        if name.endswith((".pyc", _TWIN_SUFFIX)):
            continue
        members.add(name + "/" if isdir(name) else name)
    return members


def _roster_table(text):
    """The first pipe table under '## What ships here' and before the next
    `## ` heading -> (header, rows), or None when the heading is absent, or
    ([], []) when it is present with no table."""
    section = None
    for name, body in _sections(text):
        if name == _ROSTER_HEADING:
            section = body
            break
    if section is None:
        return None
    table = _pipe_table("\n".join(section), ())
    return table if table is not None else ([], [])


def _roster_findings(relpath, text, members):
    """relpath: the README; text: its text; members: the directory's members
    (dirs with a trailing slash). -> error strings. Silent without the heading."""
    table = _roster_table(text)
    if table is None:
        return []
    header, rows = table
    if not header:
        return [
            "%s: declares '## %s' but no table follows it -- list every member "
            "(CONVENTIONS §2)" % (relpath, _ROSTER_HEADING)
        ]
    errs = []
    if header[0] != "member":
        raw_header = [ln for ln in _sections(text) if ln[0] == _ROSTER_HEADING][0][1]
        raw_first = [ln for ln in raw_header if ln.startswith("|")][0]
        errs.append(
            "%s: the '## %s' table's first column must be 'Member' (got '%s') -- "
            "the roster reader keys on that name"
            % (
                relpath,
                _ROSTER_HEADING,
                raw_first.strip().strip("|").split("|")[0].strip(),
            )
        )
    not_for = header.index("not for") if "not for" in header else None
    if not_for is None:
        errs.append(
            "%s: the '## %s' table has no 'Not for' column -- every row must say "
            "what a reader must NOT reach for that member to do, naming the "
            "sibling that does" % (relpath, _ROSTER_HEADING)
        )
    named = {}
    plain = {m.rstrip("/") for m in members}
    for row in rows:
        if not row:
            continue
        m = _BACKTICKED.search(row[0])
        name = (m.group(1) if m else row[0]).strip().rstrip("/")
        if name in named:
            shown = name + "/" if name + "/" in members else name
            errs.append(
                "%s: '## %s' names '%s' twice -- one row per member"
                % (relpath, _ROSTER_HEADING, shown)
            )
            continue
        named[name] = row
        if name not in plain:
            errs.append(
                "%s: '## %s' names '%s', which is not a member of this directory "
                "-- drop the row, or check the spelling against the listing"
                % (relpath, _ROSTER_HEADING, (m.group(1) if m else row[0]).strip())
            )
        if not_for is not None:
            cell = row[not_for].strip() if len(row) > not_for else ""
            if cell.lower() in _EMPTY_CELLS:
                errs.append(
                    "%s: roster row '%s' has an empty 'Not for' cell -- say what a "
                    "reader must NOT reach for it to do, naming the sibling that "
                    "does" % (relpath, name)
                )
    for member in sorted(plain - set(named)):
        shown = member + "/" if member + "/" in members else member
        errs.append(
            "%s: '## %s' does not name %s -- add a row, or remove the member"
            % (relpath, _ROSTER_HEADING, shown)
        )
    return errs


def check_S():
    """ERROR when a README declaring '## What ships here' disagrees with its
    directory, or a row lacks its 'Not for' discriminator. Opt-in per README."""
    for dirpath, _, filenames in walk(ROOT):
        if "README.md" not in filenames:
            continue
        full = os.path.join(dirpath, "README.md")
        text = _read_text(full, err)
        if text is None or ("## " + _ROSTER_HEADING) not in text:
            continue
        members = _roster_members(
            os.listdir(dirpath), lambda n, d=dirpath: os.path.isdir(os.path.join(d, n))
        )
        for m in _roster_findings(rel(full), text, members):
            err(m)


# --- check_T: practice mechanisms resolve --------------------------------------
#
# config/practices.json says how each practice is enforced. `mechanism` is prose
# for a reader; `enforced_by` is the same claim in a closed grammar a check can
# resolve, so a practice cannot name a check letter, script, test, make target
# or guide section that does not exist — the cdmon lesson, applied to the
# practices registry. ruff and mypy references are external tools' vocabularies
# and are accepted as written (the tools themselves reject an unknown code).

_MECHANISM_RE = re.compile(r"^(check|script|test|make|doc|ruff|mypy):(.+)$")
_MECHANISM_FORMS = "check:<LETTER> | script:<path> | test:<path> | make:<target> | doc:<path>[ §N] | ruff:<CODE> | mypy:<flag>"


def _mechanism_reason(ref, check_letters, tree, make_targets, sections_of):
    """Why `ref` does not name a real mechanism, as the clause that follows the
    claimant -- or None when it resolves. Shared with check_V so that "name the
    thing that proves this" has ONE grammar wherever the claim is made: a
    practice's `enforced_by`, a writer's `rerun_proof:`. Split out of
    _mechanism_findings rather than duplicated, because two graders of the same
    grammar drift and the drift is invisible until one of them is wrong."""
    m = _MECHANISM_RE.match(str(ref))
    if not m:
        return "names '%s', which is not in the mechanism grammar (%s)" % (
            ref,
            _MECHANISM_FORMS,
        )
    form, value = m.group(1), m.group(2).strip()
    if form == "check":
        if value not in check_letters:
            return "claims check_%s, which check_structure.py does not define" % value
    elif form in ("script", "test"):
        if value not in tree:
            return "claims %s '%s', which does not exist" % (form, value)
    elif form == "make":
        if value not in make_targets:
            return "claims `make %s`, and the Makefile has no such target" % value
    elif form == "doc":
        path, _, section = value.partition(" §")
        if path not in tree:
            return "claims doc '%s', which does not exist" % path
        if section:
            present = sections_of(path)
            if present is None or int(section) not in present:
                return "claims %s §%s, and that document has no numbered section %s" % (
                    path,
                    section,
                    section,
                )
    return None


def _mechanism_findings(practices, check_letters, tree, make_targets, sections_of):
    """practices: the registry dict; check_letters: the letters check_structure
    defines; tree: every file path; make_targets: the Makefile's rule names;
    sections_of(path) -> set of numbered sections or None. -> error strings."""
    errs = []
    entries = practices.get("practices") if isinstance(practices, dict) else None
    if not isinstance(entries, list):
        return errs
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        pid = entry.get("id", "?")
        refs = entry.get("enforced_by")
        if not isinstance(refs, list) or not refs:
            errs.append(
                "config/practices.json: practice '%s' has no `enforced_by` list -- name "
                "the mechanism(s) that enforce it (%s)" % (pid, _MECHANISM_FORMS)
            )
            continue
        for ref in refs:
            reason = _mechanism_reason(
                ref, check_letters, tree, make_targets, sections_of
            )
            if reason:
                errs.append("config/practices.json: practice '%s' %s" % (pid, reason))
    return errs


def check_T():
    """ERROR when a practice's `enforced_by` names a mechanism that does not exist.
    Silent when there is no practices registry (a generated project may drop it)."""
    practices = _load_practices()
    if not practices:
        return
    letters = set(
        re.findall(
            r"^def check_([A-Z])\(",
            _read_text(os.path.abspath(__file__), err) or "",
            re.MULTILINE,
        )
    )
    tree = set()
    for dirpath, _, filenames in walk(ROOT):
        reldir = rel(dirpath).replace(os.sep, "/")
        for f in filenames:
            tree.add(f if reldir == "." else reldir + "/" + f)
    makefile = _optional_text("Makefile")
    targets = set(_make_rules(makefile)) if makefile else set()

    def sections_of(path):
        text = _read_text(os.path.join(ROOT, path), err)
        return None if text is None else _numbered_sections(text)

    for m in _mechanism_findings(practices, letters, tree, targets, sections_of):
        err(m)


# --- check_U: policy documents are reachable -----------------------------------
#
# A practice whose enforcement IS a document is only as real as the chance that
# somebody reads it. config/practices.json can name `doc:<path>` as a mechanism,
# and check_T proves that path exists -- but existing is not the same as being
# found. docs/guides/doc-style.md shipped as the canonical statement of how
# documentation is written here, cited by four practices, and was reachable from
# nothing an agent reads by default: not the root AGENT.md, not a document
# AGENT.md names, not a gate message. The rule was unenforceable in principle.
#
# So: every `doc:` mechanism must sit within ONE HOP of the root AGENT.md, the
# file always in an agent's context. Named there, or named in a document named
# there. One hop rather than direct, because AGENT.md is a rules file and not an
# index -- an agent told to open python-style.md is handed whatever it points at.
# Two hops is not discoverability, it is a treasure hunt.

_AGENT_RULES = "AGENT.md"
# A repository-relative markdown path as the house writes one, usually inside
# backticks. Bounded so `see foo.md.` and `a/b.md)` still yield the path.
_POLICY_PATH = re.compile(r"(?<![\w./-])([A-Za-z0-9_][\w./-]*\.md)(?![\w/])")


def _document_references(relpath, text, known):
    """Every path in `known` that this document names, by markdown link or by
    literal path, root-relative or relative to the document's own directory.

    Fenced code is an illustration and is not read. Inline code IS read: a
    backticked path is exactly how this repository names a document, so
    excluding it (as check_Q does for links) would miss every real reference.
    """
    base = posixpath.dirname(relpath)
    found = set()
    for line in _unfenced_lines(text):
        candidates = [
            m.group(1) if m.group(1) is not None else m.group(2)
            for m in _MD_LINK.finditer(line)
        ]
        candidates.extend(_POLICY_PATH.findall(line))
        for cand in candidates:
            if not cand or _URL_SCHEME.match(cand):
                continue
            path = cand.partition("#")[0]
            if not path:
                continue
            for resolved in (path.lstrip("/"), _resolve_link(base, path)):
                if resolved in known:
                    found.add(resolved)
    return found


def _policy_reachability_findings(practices, docs):
    """practices: the registry dict; docs: {relpath: text} for every markdown file.
    -> error strings, one per unreachable document (not one per citing practice:
    the fix is a single edit). Silent without a registry, without any `doc:`
    mechanism, or without a root AGENT.md to measure from. A `doc:` path that is
    not in the tree is check_T's finding, never reported twice here."""
    entries = practices.get("practices") if isinstance(practices, dict) else None
    if not isinstance(entries, list) or _AGENT_RULES not in docs:
        return []
    cited = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for ref in entry.get("enforced_by") or []:
            if not str(ref).startswith("doc:"):
                continue
            path = str(ref)[len("doc:") :].partition(" ")[0].strip()
            if path in docs:
                cited.setdefault(path, []).append(str(entry.get("id", "?")))
    if not cited:
        return []
    known = set(docs)
    hop0 = _document_references(_AGENT_RULES, docs[_AGENT_RULES], known)
    reachable = set(hop0)
    for doc in sorted(hop0):
        reachable |= _document_references(doc, docs[doc], known)
    errs = []
    for path in sorted(cited):
        if path in reachable:
            continue
        errs.append(
            "config/practices.json: %s name%s %s as their mechanism, but no agent "
            "reads it -- %s does not name it, nor does any document %s names. Name "
            "it in %s, or in one it already names, or the practice cannot reach the "
            "agent it governs"
            % (
                ", ".join(sorted(cited[path])),
                "" if len(cited[path]) > 1 else "s",
                path,
                _AGENT_RULES,
                _AGENT_RULES,
                _AGENT_RULES,
            )
        )
    return errs


def check_U():
    """ERROR when a practice's `doc:` mechanism is more than one hop from the
    root AGENT.md. Silent without a practices registry or without AGENT.md."""
    practices = _load_practices()
    if not practices:
        return
    docs = {}
    for dirpath, _, filenames in walk(ROOT):
        reldir = rel(dirpath).replace(os.sep, "/")
        for f in filenames:
            if not f.endswith(".md"):
                continue
            text = _read_text(os.path.join(dirpath, f), err)
            if text is not None:
                docs[f if reldir == "." else reldir + "/" + f] = text
    for m in _policy_reachability_findings(practices, docs):
        err(m)


# --- check_V: a writer says what a second run does -----------------------------
#
# Every doer in this repository reaches a fixed point today -- generation, the
# corpus, the schemas, the static snapshot were each measured running twice and
# landing byte-identical. Nothing held them there. The property was a habit, and
# a habit is exactly what a generated project does not inherit: the tenth writer
# somebody adds downstream, six months from now, appends instead of rewrites, and
# the first anyone knows is a corpus that grows every CI run.
#
# So the obligation is placed where the author already is -- in the module's own
# gated header, next to `title:` and `summary:`. A module that writes says
# `effect: writes` (the CONVENTIONS §10 tool_effect vocabulary, reused rather
# than re-invented), says what a second run does (`rerun:`), and, if it claims
# the strong property, names the proof in the SAME closed grammar check_T holds
# `enforced_by` to.
#
# This is a gate rather than an advisory because the detection is exact, which it
# only became once the call's BASE was resolved: a detector keyed on the method
# name alone reads `text.replace(...)` as `os.replace(...)` and flags a third of
# the tree, and a check that cries wolf gets waived, not obeyed. Measured on this
# repo: 10 writers found, 0 false positives.
#
# What it cannot see, it says so about: a module that shells out to write is
# invisible to an AST, so `effect: writes` with no visible write is a WARN that
# reads 'unverified' -- never a quiet pass, and never an error either, because
# the honest declaration must not be the one that fails the build.

# The tool_effect vocabulary of CONVENTIONS §10, unchanged: one word for what a
# unit of this repository does to the world, whether the unit is a tool spec or a
# module. `model-call` is neither read-only nor a filesystem write; it is here so
# the vocabularies cannot drift apart.
_EFFECTS = ("read-only", "writes", "model-call")
# What a SECOND run does. Three values, and the split that matters is between the
# claim and the two admissions: `fixed-point` asserts something provable and must
# name its proof; `append-only` and `unsafe` assert nothing, so demanding a proof
# of them would only push an honest author toward the flattering word.
_RERUNS = ("fixed-point", "append-only", "unsafe")
_RERUN_NEEDING_PROOF = "fixed-point"
# Filesystem mutation reached through a module: `os.rename`, never `str.replace`.
_OS_WRITES = frozenset(
    (
        "makedirs",
        "mkdir",
        "remove",
        "removedirs",
        "rmdir",
        "rename",
        "renames",
        "replace",
        "symlink",
        "link",
        "unlink",
        "truncate",
        "chmod",
        "mknod",
    )
)
_SHUTIL_WRITES = frozenset(
    (
        "rmtree",
        "copy",
        "copy2",
        "copyfile",
        "copytree",
        "copymode",
        "move",
        "make_archive",
    )
)
# Methods that exist on pathlib.Path and mutate. Counted only on a literal
# `Path(...)` receiver: `out.write_text(...)` could be anything, and a guess
# there is the same false positive the qualified rule exists to avoid.
_PATH_WRITES = frozenset(
    (
        "write_text",
        "write_bytes",
        "touch",
        "mkdir",
        "unlink",
        "rmdir",
        "rename",
        "replace",
        "symlink_to",
        "hardlink_to",
        "chmod",
    )
)
_QUALIFIED_WRITES = {"os": _OS_WRITES, "shutil": _SHUTIL_WRITES}


def _literal_str(node):
    """The str a literal node holds, else None. Handles BOTH ast.Str (the 3.6
    pre-commit interpreter, where this file must still run) and ast.Constant
    (3.8+); reading only one of them is how a detector silently finds nothing on
    the very interpreter the gate runs under."""
    if node.__class__.__name__ == "Str":  # 3.6/3.7; removed as a name in 3.12
        return node.s
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _call_base(func):
    """Dotted receiver of an attribute call: `os.path.join` -> 'os.path'. Empty
    when the receiver is not a plain dotted name (a call, a subscript, self)."""
    parts = []
    node = func.value
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        parts.reverse()
        return ".".join(parts)
    return ""


def _write_sites(tree):
    """Every filesystem write an AST proves, as sorted (lineno, what) pairs.

    Exact by construction: a call counts only when the thing being called is
    resolvable to a writing API -- builtin `open` in a mutating mode, a call on
    the `os`/`shutil` module, or a method on a literal `Path(...)`. An
    unresolvable receiver counts as nothing, which is the deliberate trade: this
    UNDER-reports (a write behind `subprocess`, or through an aliased import) and
    never over-reports, because a gate that fires on correct code is a gate that
    gets turned off.
    """
    sites = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "open":
            mode, given = "", False
            if len(node.args) > 1:
                given = True
                mode = _literal_str(node.args[1]) or ""
                if _literal_str(node.args[1]) is None:
                    sites.append((node.lineno, "open(<computed>)"))
                    continue
            for kw in node.keywords:
                if kw.arg != "mode":
                    continue
                given = True
                lit = _literal_str(kw.value)
                if lit is None:
                    sites.append((node.lineno, "open(<computed>)"))
                    mode = ""
                    break
                mode = lit
            else:
                if given and any(c in mode for c in "wax+"):
                    sites.append((node.lineno, "open(%r)" % mode))
            continue
        if not isinstance(func, ast.Attribute):
            continue
        base = _call_base(func)
        if base in _QUALIFIED_WRITES and func.attr in _QUALIFIED_WRITES[base]:
            sites.append((node.lineno, "%s.%s" % (base, func.attr)))
        elif (
            func.attr in _PATH_WRITES
            and isinstance(func.value, ast.Call)
            and isinstance(func.value.func, ast.Name)
            and func.value.func.id == "Path"
        ):
            sites.append((node.lineno, "Path().%s" % func.attr))
    sites.sort()
    return sites


def _effect_declaration_findings(
    modules, check_letters, tree, make_targets, sections_of
):
    """modules: {relpath: source}; the rest as _mechanism_reason takes them.
    -> (errors, warnings). Pure; the walk is check_V's.

    Unparseable sources and modules with no docstring are skipped -- check_D and
    check_O respectively already own those, and a second report is noise.
    """
    errs, warns_ = [], []
    for relpath in sorted(modules):
        try:
            parsed = ast.parse(modules[relpath], filename=relpath)
        except UNPARSEABLE:
            continue
        doc = ast.get_docstring(parsed)
        if not doc:
            continue
        meta = _module_meta(doc)
        effect = meta.get("effect", "")
        rerun = meta.get("rerun", "")
        proof = meta.get("rerun_proof", "")
        sites = _write_sites(parsed)
        if effect and effect not in _EFFECTS:
            errs.append(
                "%s: `effect: %s` is not one of %s -- the CONVENTIONS §10 "
                "tool_effect vocabulary, one word for what a unit does to the world"
                % (relpath, effect, "/".join(_EFFECTS))
            )
            continue
        if effect != "writes":
            if sites:
                lineno, what = sites[0]
                errs.append(
                    "%s:%d: writes to the filesystem (%s) but its header %s -- add "
                    "`effect: writes` and a `rerun:` saying what a second run does, "
                    "so nobody has to read the body to find out "
                    "(docs/guides/idempotency.md)"
                    % (
                        relpath,
                        lineno,
                        what,
                        "says `effect: %s`" % effect if effect else "does not say so",
                    )
                )
            elif rerun or proof:
                errs.append(
                    "%s: declares `rerun:`/`rerun_proof:` without `effect: writes` "
                    "-- a statement about a second run of something that never "
                    "claims to write the first time" % relpath
                )
            continue
        if not sites:
            warns_.append(
                "%s: declares `effect: writes`, and no write is visible in its "
                "source -- unverified, not disproven (a write behind subprocess "
                "reads this way; so does a header left behind by a removed write)"
                % relpath
            )
        if not rerun:
            errs.append(
                "%s: declares `effect: writes` with no `rerun:` -- say what a "
                "second run does (%s); an unstated one is the assumption every "
                "caller makes and nobody checked (docs/guides/idempotency.md)"
                % (relpath, "/".join(_RERUNS))
            )
            continue
        if rerun not in _RERUNS:
            errs.append(
                "%s: `rerun: %s` is not one of %s" % (relpath, rerun, "/".join(_RERUNS))
            )
            continue
        if rerun != _RERUN_NEEDING_PROOF:
            continue
        if not proof:
            errs.append(
                "%s: claims `rerun: %s` and names no `rerun_proof:` -- the strong "
                "claim is the one that needs evidence (%s)"
                % (relpath, _RERUN_NEEDING_PROOF, _MECHANISM_FORMS)
            )
            continue
        reason = _mechanism_reason(
            proof, check_letters, tree, make_targets, sections_of
        )
        if reason:
            errs.append("%s: its `rerun_proof:` %s" % (relpath, reason))
    return errs, warns_


def check_V():
    """ERROR when a module that writes to the filesystem does not declare it
    (`effect: writes`), does not say what a second run does (`rerun:`), or claims
    `rerun: fixed-point` without naming a proof that resolves. WARN when a module
    declares a write this check cannot see. Silent over `tests/`."""
    modules = {}
    for wroot in WRITER_ROOTS:
        base = os.path.join(ROOT, wroot)
        if not os.path.isdir(base):
            continue
        for dirpath, _, filenames in walk(base):
            for f in filenames:
                if not f.endswith(".py"):
                    continue
                try:
                    with open(os.path.join(dirpath, f), encoding="utf-8-sig") as fh:
                        modules[rel(os.path.join(dirpath, f))] = fh.read()
                except UNREADABLE:
                    continue  # unreadable is reported by the checks keyed on it
    letters = set(
        re.findall(
            r"^def check_([A-Z])\(",
            _read_text(os.path.abspath(__file__), err) or "",
            re.MULTILINE,
        )
    )
    tree = set()
    for dirpath, _, filenames in walk(ROOT):
        reldir = rel(dirpath).replace(os.sep, "/")
        for f in filenames:
            tree.add(f if reldir == "." else reldir + "/" + f)
    makefile = _optional_text("Makefile")
    targets = set(_make_rules(makefile)) if makefile else set()

    def sections_of(path):
        text = _read_text(os.path.join(ROOT, path), err)
        return None if text is None else _numbered_sections(text)

    errs, warns_ = _effect_declaration_findings(
        modules, letters, tree, targets, sections_of
    )
    for m in errs:
        err(m)
    for m in warns_:
        warn(m)


# --- check_W: every make target declares its effect ----------------------------
#
# A make target is a doer an agent runs by name, and nothing about the name says
# whether it reads, rewrites the tree, spends money or changes shared state. The
# label is that statement, written where `make help` shows it, in a closed
# vocabulary ordered by reach (docs/adr/keel/K-0011-make-target-effect-labels.md):
#   [local]  this machine only; writes nothing git would list
#   [tree]   rewrites files in the working tree
#   [read]   reads a remote service
#   [cost]   spends money
#   [write]  changes shared remote state; refused under CI and gate runs
# check_W holds the static half: the grammar, a composite's cover of what it
# reaches, the write guard, the policy, and (opt-in) area makefiles. The runtime
# half -- a label is a claim only running the target can test -- is
# tests/integration/test_make_target_effects.py, through scripts/run_make_target.py.

EFFECT_MEANINGS = (
    ("local", "this machine only; writes nothing git would list"),
    ("tree", "rewrites files in the working tree"),
    ("read", "reads a remote service"),
    ("cost", "spends money"),
    ("write", "changes shared remote state; refused under CI and gate runs"),
)
EFFECT_LABELS = tuple(word for word, _ in EFFECT_MEANINGS)

_POLICY_BLOCK = "make_targets"
_POLICY_KEYS = (
    "unattended_vars",
    "gate_runner_var",
    "gate_effects",
    "write_shapes",
    "area_dir",
    "effect_proof_skip",
    "gate_vars",
)
# make's own control variables and the guard: a gate run that let a caller set
# one could load a makefile nobody labelled (MAKEFILES), pass flags (MAKEFLAGS,
# MFLAGS), swap the shell or make itself, or empty the guard, so gate_vars may
# never name one. These are GNU make's names, not a project fact.
_RESERVED_MAKE_VARS = (
    "GNUMAKEFLAGS",
    "MAKE",
    "MAKECMDGOALS",
    "MAKEFILES",
    "MAKEFILE_LIST",
    "MAKEFLAGS",
    "MAKELEVEL",
    "MAKEOVERRIDES",
    "MAKESHELL",
    "MAKE_RESTARTS",
    "MFLAGS",
    "SHELL",
    "VPATH",
)
# A gate run proves read-only-ness, so it may never run what rewrites the tree or
# shared state, and it must be able to run a target that only reads locally.
_GATE_MUST_HOLD = "local"
_GATE_MUST_NOT_HOLD = ("tree", "write")
_MAKE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_WRITE_SHAPE = re.compile(r"^-[a-z0-9][a-z0-9-]*$")
_AREA_DIR_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
_KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
AREA_HEADER = re.compile(r"^##@\s+(\S+)(?:\s+(.*?))?\s*$")
# The guard's name is the contract between the Makefile and this check, as
# `help` is check_P's: the ADR names it, the Makefile defines it.
_GUARD_NAME = "WRITE_GUARD"
_GUARD_CALLS = ("$(WRITE_GUARD)", "${WRITE_GUARD}")
_GUARD_DEF = re.compile(
    r"^\s*(?:override\s+)?WRITE_GUARD\s*[:?]?=\s*(.*?)\s*$", re.MULTILINE
)
_GUARD_EXIT = re.compile(r"\bexit\s+1\b")
# make strips `@`, `-`, `+` and blanks from the front of a recipe line, after
# expansion; `-` makes it carry on past a failure, so a guard behind one refuses
# and the recipe runs anyway (measured: `Error 1 (ignored)`, rc 0).
_RECIPE_PREFIX = re.compile(r"^[@+\- \t]*")
# A variable reference in a shell condition: $(X), ${X}, $$X, $${X}.
_VAR_REF = re.compile(
    r"\$(?:\(([A-Za-z_][A-Za-z0-9_]*)\)|\{([A-Za-z_][A-Za-z0-9_]*)\}"
    r"|\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*))"
)
_GUARD_THEN = re.compile(r"\bthen\b")
_RULE_HEAD = re.compile(r"^([^:#=\t][^:#=]*?)\s*(::?)(?!=)(.*)$")
_TARGET_VAR = re.compile(
    r"^\s*(?:(?:export|override|private)\s+)*[A-Za-z_][A-Za-z0-9_.-]*\s*[:?+!]?="
)
_SPECIAL_TARGET = re.compile(r"^\.[A-Z_]+$")
_RECURSE = re.compile(r"\$[({]MAKE[)}]")
# make flags that consume the next word, and those that point make somewhere
# this check cannot follow (another directory or another makefile).
_FLAGS_WITH_ARG = ("-I", "-o", "-W", "--include-dir", "--old-file", "--what-if")
_FLAGS_ELSEWHERE = ("-C", "-f", "--file", "--directory", "--makefile")
_SHELL_STOP = re.compile(r";|&&|\|\||\|")

MakeRule = collections.namedtuple(
    "MakeRule",
    "target help prereqs recursions unresolved recipe first_recipe lineno first_prefix",
)


def parse_effect_labels(help_):
    """A `## ` help string -> (labels, text, None), or (None, help, problem).

    labels is the tuple of words in the opening `[...]`, text what follows it.
    The problem is one sentence fragment naming what is wrong, worded to follow
    a target name ("`check` has no effect label ...")."""
    vocab = ", ".join(EFFECT_LABELS)
    help_ = (help_ or "").strip()
    if not help_.startswith("["):
        return (
            None,
            help_,
            "has no effect label -- open its `## ` help with one of [%s] "
            "(comma-separated, in that order; docs/adr/keel/K-0011-make-target-effect-labels.md)"
            % vocab.replace(", ", "], ["),
        )
    close = help_.find("]")
    if close < 0:
        return (
            None,
            help_,
            "has no effect label -- the `[` opening its help is never closed",
        )
    inner, rest = help_[1:close], help_[close + 1 :].strip()
    if not inner:
        return (
            None,
            help_,
            "has an empty effect label `[]` -- name its effect from %s" % vocab,
        )
    words = inner.split(",")
    for word in words:
        if word not in EFFECT_LABELS:
            return (
                None,
                help_,
                "'%s' is not an effect label (the vocabulary is %s, comma-separated "
                "with no spaces)" % (word, vocab),
            )
    for word in words:
        if words.count(word) > 1:
            return None, help_, "effect label [%s] names `%s` twice" % (inner, word)
    if "local" in words and len(words) > 1:
        return (
            None,
            help_,
            "effect label [%s]: `local` stands alone -- it says nothing leaves this "
            "machine, so drop it beside a wider word" % inner,
        )
    ordered = sorted(words, key=EFFECT_LABELS.index)
    if words != ordered:
        return (
            None,
            help_,
            "effect label [%s] is not in canonical order -- write [%s]"
            % (inner, ",".join(ordered)),
        )
    if rest.startswith("["):
        end = rest.find("]")
        second = rest[1:end] if end > 0 else ""
        if second and all(w.strip() in EFFECT_LABELS for w in second.split(",")):
            return (
                None,
                help_,
                "carries a second effect label `[%s]` -- write one label holding "
                "every word, [%s]" % (second, ",".join(words + [second])),
            )
    return tuple(words), rest, None


def _make_words(text):
    """Whitespace-separated words, a `$(...)`/`${...}` reference kept whole."""
    words, cur, depth = [], "", 0
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "$" and i + 1 < len(text) and text[i + 1] in "({":
            depth += 1
            cur += text[i : i + 2]
            i += 2
            continue
        if depth and ch in ")}":
            depth -= 1
        if ch.isspace() and not depth:
            if cur:
                words.append(cur)
            cur = ""
        else:
            cur += ch
        i += 1
    if cur:
        words.append(cur)
    return words


def _recursions(cmd):
    """([targets], [unresolved]) for every `$(MAKE)` call in one recipe command.

    A flag or NAME=VALUE is skipped; a call that changes directory or makefile,
    or names its goal through a variable, is unresolved -- this check cannot see
    what it runs, so it says so rather than assume nothing."""
    targets, unresolved = [], []
    for m in _RECURSE.finditer(cmd):
        call = _SHELL_STOP.split(cmd[m.end() :], 1)[0]
        goals, skip_next, elsewhere = [], False, False
        for word in _make_words(call):
            word = word.strip("'\"")
            if "$(" not in word and "${" not in word:
                word = word.rstrip(")")
            if not word or word.isdigit():
                continue  # a `-j 4` count, or a subshell's closing parenthesis
            if skip_next:
                skip_next = False
                continue
            if word.startswith("-"):
                flag = word.split("=", 1)[0]
                if flag in _FLAGS_ELSEWHERE or (
                    word[:2] in ("-C", "-f") and not word.startswith("--")
                ):
                    elsewhere = True
                    break
                if flag in _FLAGS_WITH_ARG and "=" not in word:
                    skip_next = True
                continue
            if "=" in word.split("$", 1)[0]:
                continue
            goals.append(word)
        if elsewhere:
            unresolved.append((m.group(0) + call).strip())
            continue
        if not goals:
            unresolved.append("%s (its default goal)" % m.group(0))
        for goal in goals:
            (unresolved if goal.startswith("$") else targets).append(goal)
    return targets, unresolved


def make_target_rules(text):
    """Every explicit rule in one makefile's text, as MakeRule records in order.

    Reads what make reads: `\\`-continuations joined (lineno is the rule's first
    physical line), `define`...`endef` bodies, assignments, target-specific
    variables, pattern rules, `$`-named and dotted special targets skipped, one
    record per target on a multi-target line. help is the text after `## `
    (None without one); prereqs drops order-only `|` and moves `$`-references to
    unresolved; recursions are the goals of `$(MAKE)` calls in the recipe."""
    lines = text.split("\n")
    rules, current, define_depth, i = [], [], 0, 0
    while i < len(lines):
        start = i
        line = lines[i]
        while line.endswith("\\") and i + 1 < len(lines):
            i += 1
            line = line[:-1].rstrip(" \t") + " " + lines[i].lstrip(" \t")
        i += 1
        stripped = line.strip()
        if define_depth:
            if re.match(r"^\s*(?:override\s+|export\s+)?define\b", line):
                define_depth += 1
            elif re.match(r"^\s*endef\b", line):
                define_depth -= 1
            continue
        if line.startswith("\t"):
            if not current:
                continue
            cmd = _recipe_command(line)
            if not cmd:
                continue
            found, opaque = _recursions(cmd)
            prefix = _RECIPE_PREFIX.match(line.lstrip("\t ")).group(0)
            for rec in current:
                if not rec["recipe"]:
                    rec["first_prefix"] = prefix.replace(" ", "").replace("\t", "")
                rec["recipe"].append(cmd)
                rec["recursions"].extend(found)
                rec["unresolved"].extend(opaque)
            continue
        if (
            not stripped
            or stripped.startswith("#")
            or _MAKE_CONDITIONAL.match(stripped)
        ):
            continue
        if re.match(r"^\s*(?:override\s+|export\s+)?define\b", line):
            define_depth, current = 1, []
            continue
        m = _RULE_HEAD.match(line)
        if not m:
            current = []
            continue
        names, rest = _make_words(m.group(1)), m.group(3)
        hash_at = rest.find("#")
        body = rest if hash_at < 0 else rest[:hash_at]
        help_ = None
        if hash_at >= 0:
            hm = re.match(r"##(?:\s+(.*)|\s*$)", rest[hash_at:])
            if hm:
                help_ = (hm.group(1) or "").strip()
        if (
            _TARGET_VAR.match(body)
            or "%" in m.group(1)
            or ("%" in body and ":" in body)
        ):
            current = []
            continue
        prereqs, unresolved = [], []
        for word in _make_words(body):
            if word == "|":
                continue
            (unresolved if word.startswith("$") else prereqs).append(word)
        current = []
        for name in names:
            if name.startswith("$") or _SPECIAL_TARGET.match(name):
                continue
            rec = {
                "target": name,
                "help": help_,
                "prereqs": list(prereqs),
                "recursions": [],
                "unresolved": list(unresolved),
                "recipe": [],
                "lineno": start + 1,
                "first_prefix": "",
            }
            current.append(rec)
            rules.append(rec)
    return [
        MakeRule(
            r["target"],
            r["help"],
            r["prereqs"],
            r["recursions"],
            r["unresolved"],
            r["recipe"],
            r["recipe"][0] if r["recipe"] else None,
            r["lineno"],
            r["first_prefix"],
        )
        for r in rules
    ]


def walk_makefiles(root, warn_, err_=None):
    """[(relpath, text)]: `Makefile` under root, then every makefile an
    `include`/`-include`/`sinclude` line names, depth-first in the order make
    reads them (what `$(MAKEFILE_LIST)` holds). An include named through a
    variable or wildcard, and a required include naming no file, go to warn_;
    an unreadable makefile goes to err_ (default warn_). An absent optional
    include is make's own 'if present' and is silent. [] without a Makefile."""
    err_ = err_ or warn_
    out, seen = [], set()

    def visit(relpath):
        text = _read_text(os.path.join(root, relpath), err_)
        if text is None:
            return
        out.append((relpath, text))
        for directive, name in _includes(text):
            if _MAKE_VAR.search(name) or any(ch in name for ch in "*?["):
                warn_(
                    "%s: `%s %s` names its makefile through a variable or wildcard "
                    "this gate does not expand, so that makefile is unverified -- "
                    "its targets go unchecked" % (relpath, directive, name)
                )
                continue
            inc_rel = posixpath.normpath(name)
            if inc_rel in seen:
                continue
            seen.add(inc_rel)
            if not os.path.isfile(os.path.join(root, inc_rel)):
                if directive == "include":
                    warn_(
                        "%s: `include %s` names no file -- make itself would stop "
                        "here, and that makefile is unverified" % (relpath, name)
                    )
                continue
            visit(inc_rel)

    if not os.path.isfile(os.path.join(root, "Makefile")):
        return out
    seen.add("Makefile")
    visit("Makefile")
    return out


def _is_name_list(value):
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def make_targets_policy(manifest):
    """config/project.json's make_targets block -> (policy, errs). Pure.

    Every key is required and a key outside them is an error (`_comment` aside),
    so a typo cannot silently fall back to a default; each bad value is one
    error naming the key and what is wrong. policy is None when errs is not
    empty -- a consumer refuses rather than half-trusting it."""
    if not isinstance(manifest, dict) or _POLICY_BLOCK not in manifest:
        return None, [
            "%s is missing -- a project with a Makefile declares its make-target "
            "effect policy there (CONVENTIONS §15)" % _POLICY_BLOCK
        ]
    block = manifest[_POLICY_BLOCK]
    if not isinstance(block, dict):
        return None, [
            "%s must be an object, got %s" % (_POLICY_BLOCK, type(block).__name__)
        ]
    errs = [
        "%s is missing `%s`" % (_POLICY_BLOCK, key)
        for key in _POLICY_KEYS
        if key not in block
    ]
    errs.extend(
        "%s has an unknown key `%s` (the keys are %s)"
        % (_POLICY_BLOCK, key, ", ".join(_POLICY_KEYS))
        for key in sorted(block)
        if key not in _POLICY_KEYS and key != "_comment"
    )
    where = _POLICY_BLOCK + "."
    unattended = block.get("unattended_vars")
    unattended_ok = False
    if "unattended_vars" in block:
        if not _is_name_list(unattended) or not unattended:
            errs.append(
                where + "unattended_vars must be a non-empty list of make variable "
                "names (the variables CI and gate runs set)"
            )
        else:
            bad = [v for v in unattended if not _MAKE_NAME.match(v)]
            dup = sorted({v for v in unattended if unattended.count(v) > 1})
            if bad:
                errs.append(
                    where
                    + "unattended_vars: %s is not a make variable name"
                    % ", ".join("`%s`" % v for v in bad)
                )
            elif dup:
                errs.append(where + "unattended_vars names %s twice" % ", ".join(dup))
            else:
                unattended_ok = True
    if "gate_runner_var" in block:
        runner = block["gate_runner_var"]
        if not isinstance(runner, str) or not _MAKE_NAME.match(runner):
            errs.append(where + "gate_runner_var must be a make variable name")
        elif unattended_ok and runner not in unattended:
            errs.append(
                where + "gate_runner_var `%s` is not in unattended_vars (%s), so a "
                "gate run would not trip WRITE_GUARD" % (runner, ", ".join(unattended))
            )
    if "gate_effects" in block:
        gate = block["gate_effects"]
        if not _is_name_list(gate):
            errs.append(where + "gate_effects must be a list of effect labels")
        else:
            unknown = [g for g in gate if g not in EFFECT_LABELS]
            wide = [g for g in _GATE_MUST_NOT_HOLD if g in gate]
            if unknown:
                errs.append(
                    where
                    + "gate_effects: %s is not an effect label (%s)"
                    % (", ".join("`%s`" % g for g in unknown), ", ".join(EFFECT_LABELS))
                )
            elif _GATE_MUST_HOLD not in gate:
                errs.append(
                    where + "gate_effects must include `%s` -- a gate that cannot run "
                    "a local target runs nothing" % _GATE_MUST_HOLD
                )
            elif wide:
                errs.append(
                    where + "gate_effects may not hold %s -- a gate run proves the "
                    "tree and shared state unchanged"
                    % ", ".join("`%s`" % g for g in wide)
                )
    if "write_shapes" in block:
        shapes = block["write_shapes"]
        if not _is_name_list(shapes):
            errs.append(where + "write_shapes must be a list of name suffixes")
        else:
            bad = [s for s in shapes if not _WRITE_SHAPE.match(s)]
            if bad:
                errs.append(
                    where
                    + "write_shapes: %s is not a `-word` target-name suffix"
                    % ", ".join("`%s`" % s for s in bad)
                )
    if "area_dir" in block:
        area_dir = block["area_dir"]
        if area_dir is not None and not (
            isinstance(area_dir, str)
            and _AREA_DIR_NAME.match(area_dir)
            and area_dir not in (".", "..")
        ):
            errs.append(
                where + "area_dir must be null or one directory name at the root, "
                "got %s" % json.dumps(area_dir)
            )
    if "effect_proof_skip" in block:
        skip = block["effect_proof_skip"]
        if not isinstance(skip, dict):
            errs.append(
                where + "effect_proof_skip must be an object of target -> reason"
            )
        else:
            bad = sorted(
                k for k, v in skip.items() if not isinstance(v, str) or not v.strip()
            )
            if bad:
                errs.append(
                    where + "effect_proof_skip: %s carries no reason -- a skip says "
                    "why the target cannot run unattended"
                    % ", ".join("`%s`" % k for k in bad)
                )
    if "gate_vars" in block:
        gate_vars = block["gate_vars"]
        if not _is_name_list(gate_vars):
            errs.append(
                where + "gate_vars must be a list of make variable names (the "
                "NAME=VALUE variables a gate run may set, e.g. PY)"
            )
        else:
            bad = [v for v in gate_vars if not _MAKE_NAME.match(v)]
            owned = [
                v
                for v in gate_vars
                if v in _RESERVED_MAKE_VARS
                or v == _GUARD_NAME
                or (_is_name_list(unattended) and v in unattended)
            ]
            if bad:
                errs.append(
                    where
                    + "gate_vars: %s is not a make variable name"
                    % ", ".join("`%s`" % v for v in bad)
                )
            elif owned:
                errs.append(
                    where + "gate_vars may not name %s -- a caller who sets make's "
                    "control variables, the guard or an unattended variable can run "
                    "what no label declares" % ", ".join("`%s`" % v for v in owned)
                )
    if errs:
        return None, errs
    return {k: block[k] for k in _POLICY_KEYS}, []


def _rule_index(makefiles):
    """{target: MakeRule} over every makefile, a target's rules merged as make
    merges them: prerequisites, recursions and unresolved items unioned, the
    help and recipe from the first rule carrying one."""
    index = {}
    for _, text in makefiles:
        for r in make_target_rules(text):
            have = index.get(r.target)
            if have is None:
                index[r.target] = r
                continue
            index[r.target] = have._replace(
                help=have.help if have.help is not None else r.help,
                prereqs=have.prereqs + r.prereqs,
                recursions=have.recursions + r.recursions,
                unresolved=have.unresolved + r.unresolved,
                recipe=have.recipe or r.recipe,
                first_recipe=have.first_recipe or r.first_recipe,
                first_prefix=have.first_prefix if have.recipe else r.first_prefix,
            )
    return index


def _label_conflicts(makefiles):
    """{target: ((relpath, lineno, labels), (relpath, lineno, labels))} for each
    target whose `## ` annotations carry two different well-formed labels: the
    first annotation and the first that disagrees with it. make merges the rules
    into one target, so keeping either label alone would hide the other's
    effect; a malformed label is reported on its own and skipped here."""
    seen, out = {}, {}
    for relpath, text in makefiles:
        for rule in make_target_rules(text):
            if rule.help is None:
                continue
            labels, _, why = parse_effect_labels(rule.help)
            if why is not None:
                continue
            here = (relpath, rule.lineno, labels)
            first = seen.setdefault(rule.target, here)
            if first[2] != labels and rule.target not in out:
                out[rule.target] = (first, here)
    return out


def _conflict_text(name, pair):
    (path_a, line_a, labels_a), (path_b, line_b, labels_b) = pair
    return (
        "`%s` is annotated twice with different labels, [%s] at %s:%d and [%s] at "
        "%s:%d -- make merges the rules into one target, so annotate it once"
        % (
            name,
            ",".join(labels_a),
            path_a,
            line_a,
            ",".join(labels_b),
            path_b,
            line_b,
        )
    )


def _children(rule):
    return rule.prereqs + rule.recursions


def _normalise(words):
    """A set of effect words as a canonical label: `local` only when alone."""
    wider = [w for w in EFFECT_LABELS if w in words and w != "local"]
    return tuple(wider) if wider else ("local",)


def target_effects(root):
    """{target: (labels, None) or (None, reason)} for every rule under root.

    labels is the target's declared label closed over everything it reaches
    (prerequisites and `$(MAKE)` recursions, transitively), canonicalised. A
    target is unprovable -- None with the reason -- when it is unlabelled, its
    label is malformed, or what it reaches includes an unlabelled rule with a
    recipe, a malformed label, or a recursion this module cannot follow. A name
    no rule defines is a file prerequisite and reaches nothing."""
    makefiles = walk_makefiles(root, lambda _m: None)
    index = _rule_index(makefiles)
    conflicts = _label_conflicts(makefiles)
    parsed = {}
    for name, rule in index.items():
        if rule.help is None:
            parsed[name] = (None, "`%s` has no effect label" % name)
        elif name in conflicts:
            parsed[name] = (None, _conflict_text(name, conflicts[name]))
        else:
            labels, _, why = parse_effect_labels(rule.help)
            parsed[name] = (labels, None if why is None else "`%s` %s" % (name, why))
    out = {}
    for name in sorted(index):
        labels, why = parsed[name]
        if labels is None:
            out[name] = (None, why)
            continue
        words, stack, seen, problem = set(labels), [name], {name}, None
        while stack and problem is None:
            rule = index[stack.pop()]
            if rule.unresolved:
                problem = "`%s` runs `%s`, which this gate cannot follow" % (
                    rule.target,
                    rule.unresolved[0],
                )
                break
            for child in _children(rule):
                if child in seen or child not in index:
                    continue
                seen.add(child)
                child_labels, child_why = parsed[child]
                if child_labels is not None:
                    words.update(child_labels)
                elif index[child].help is not None:
                    problem = child_why
                    break
                elif index[child].recipe:
                    problem = (
                        "`%s` reaches `%s`, which has a recipe but no effect label"
                        % (name, child)
                    )
                    break
                stack.append(child)
        out[name] = (None, problem) if problem else (_normalise(words), None)
    return out


def _strip_make_comment(value):
    """An assignment's value as make stores it: an unescaped `#` starts a make
    comment there, even inside shell quotes."""
    m = re.search(r"(?<!\\)#", value)
    return value if m is None else value[: m.start()].rstrip()


def _guard_findings(makefiles, unattended):
    """(defined_in or None, errs) for the WRITE_GUARD definition.

    The guard must test every configured unattended variable and `exit 1`, must
    not open with a `-` (make would ignore its failure), and its condition --
    the text before `then`, or before `exit 1` without one -- may test no
    variable the config omits, so the Makefile and config/project.json name the
    same set in both directions."""
    for relpath, text in makefiles:
        m = _GUARD_DEF.search(_UNFOLD.sub(" ", text))
        if not m:
            continue
        body = _strip_make_comment(m.group(1))
        if "-" in _RECIPE_PREFIX.match(body).group(0):
            return relpath, [
                "%s: `%s` opens with a `-` prefix, so make ignores its `exit 1` and "
                "a [write] recipe runs under CI and gate runs anyway -- drop the `-`"
                % (relpath, _GUARD_NAME)
            ]
        cut = _GUARD_THEN.search(body) or _GUARD_EXIT.search(body)
        condition = body if cut is None else body[: cut.start()]
        tested = sorted(
            {next(g for g in ref.groups() if g) for ref in _VAR_REF.finditer(condition)}
        )
        extra = [v for v in tested if v not in unattended]
        if extra:
            return relpath, [
                "%s: `%s` tests %s, which make_targets.unattended_vars omits, so no "
                "gate run or test exercises it -- add it to config/project.json or "
                "drop it from the guard"
                % (relpath, _GUARD_NAME, ", ".join("`%s`" % v for v in extra))
            ]
        missing = []
        for var in unattended:
            spellings = (
                r"\$\(%s\)" % var,
                r"\$\{%s\}" % var,
                r"\$\$%s(?![A-Za-z0-9_])" % var,
                r"\$\$\{%s\}" % var,
            )
            if not any(re.search(s, body) for s in spellings):
                missing.append(var)
        if not _GUARD_EXIT.search(body):
            missing.append("exit 1")
        if missing:
            return relpath, [
                "%s: `%s` must test every make_targets.unattended_vars entry and "
                "`exit 1`, so a [write] target refuses under CI and gate runs; it "
                "misses %s" % (relpath, _GUARD_NAME, ", ".join(missing))
            ]
        return relpath, []
    return None, []


def _area_findings(makefiles, by_file, area_dir):
    """errs for the area-makefile rules; area_dir None means areas are off, and
    then a `##@` header is itself the error (it promises a grouping nothing
    checks)."""
    errs = []
    headers = {}
    for relpath, text in makefiles:
        for lineno, line in enumerate(text.split("\n"), 1):
            m = AREA_HEADER.match(line)
            if m:
                headers.setdefault(relpath, []).append((lineno, m.group(1)))
    if area_dir is None:
        for relpath, _ in makefiles:
            for lineno, name in headers.get(relpath, []):
                errs.append(
                    "%s:%d: `##@ %s` declares an area, but make_targets.area_dir "
                    "is null -- name the directory of <area>.mk files in "
                    "config/project.json, or drop the header" % (relpath, lineno, name)
                )
        return errs
    for relpath, _ in makefiles:
        found = headers.get(relpath, [])
        if len(found) > 1:
            errs.append(
                "%s: holds %d `##@` headers (%s) -- one makefile is one area"
                % (relpath, len(found), ", ".join(n for _, n in found))
            )
    base = os.path.join(ROOT, area_dir)
    if not os.path.isdir(base):
        errs.append(
            "config/project.json: make_targets.area_dir names `%s`, which is not a "
            "directory -- the declaration is stale" % area_dir
        )
        return errs
    walked = {relpath for relpath, _ in makefiles}
    for fname in sorted(os.listdir(base)):
        if not fname.endswith(".mk"):
            continue
        relpath, area = area_dir + "/" + fname, fname[: -len(".mk")]
        if not _KEBAB.match(area):
            errs.append(
                "%s: `%s` is not a kebab-case area name -- an area makefile is "
                "<area>.mk with a lower-case, hyphenated name" % (relpath, area)
            )
            continue
        if relpath not in walked:
            errs.append(
                "%s: an area makefile nothing includes, so make never reads it -- "
                "add `include %s` to the Makefile" % (relpath, relpath)
            )
            continue
        found = headers.get(relpath, [])
        if len(found) <= 1 and [n for _, n in found] != [area]:
            errs.append(
                "%s: an area makefile opens its targets with exactly one `##@ %s` "
                "header (found %s)"
                % (relpath, area, ", ".join("`##@ %s`" % n for _, n in found) or "none")
            )
        for rule in by_file.get(relpath, []):
            if rule.target.startswith("_"):
                continue
            if not rule.target.startswith(area + "-"):
                errs.append(
                    "%s:%d: `%s` is not prefixed `%s-` -- a public area target "
                    "carries its area's name (prefix a private helper with `_`)"
                    % (relpath, rule.lineno, rule.target, area)
                )
            elif rule.help is None:
                errs.append(
                    "%s:%d: `%s` carries no `## ` annotation -- a public area "
                    "target is listed by `make help` with its effect label"
                    % (relpath, rule.lineno, rule.target)
                )
    return errs


def _effect_findings(makefiles, policy):
    """(errs, warns) for check_W over [(relpath, text)] under one valid policy."""
    errs, warns, run_once = [], [], set()
    by_file, first = {}, {}
    for relpath, text in makefiles:
        for rule in make_target_rules(text):
            by_file.setdefault(relpath, []).append(rule)
            first.setdefault(rule.target, (relpath, rule))
    index = _rule_index(makefiles)
    labels_of = {}
    for relpath, _ in makefiles:
        for rule in by_file.get(relpath, []):
            if rule.help is None:
                continue
            labels, _, why = parse_effect_labels(rule.help)
            if why is not None:
                errs.append("%s:%d: `%s` %s" % (relpath, rule.lineno, rule.target, why))
            elif rule.target not in labels_of:
                labels_of[rule.target] = labels
    conflicts = _label_conflicts(makefiles)
    for name in sorted(conflicts):
        relpath, lineno, _ = conflicts[name][1]
        errs.append(
            "%s:%d: %s" % (relpath, lineno, _conflict_text(name, conflicts[name]))
        )
    # A composite's label covers what it reaches. A labelled child answers for
    # its own subtree (its label is checked in turn); an unlabelled one is
    # transparent, and with a recipe it is an effect nobody declared.
    for name in sorted(labels_of):
        relpath, rule = first[name]
        declared = set(labels_of[name])
        short = {}
        stack, seen = [name], {name}
        while stack:
            node = index[stack.pop()]
            for item in node.unresolved:
                msg = (
                    "%s:%d: `%s` runs `%s`, which this gate cannot follow, so its "
                    "effect label is unverified past it"
                    % (
                        first[node.target][0],
                        first[node.target][1].lineno,
                        node.target,
                        item,
                    )
                    if node.target == name
                    else "%s:%d: `%s` reaches `%s`, which runs `%s` this gate cannot "
                    "follow" % (relpath, rule.lineno, name, node.target, item)
                )
                if msg not in run_once:
                    run_once.add(msg)
                    warns.append(msg)
            for child in _children(node):
                if child in seen or child not in index:
                    continue
                seen.add(child)
                if child in labels_of:
                    gap = [
                        w
                        for w in labels_of[child]
                        if w != "local" and w not in declared
                    ]
                    if gap:
                        short[child] = gap
                    continue
                if index[child].help is not None:
                    continue  # malformed label: reported above
                if index[child].recipe:
                    warns.append(
                        "%s:%d: `%s` reaches `%s`, which has a recipe but no effect "
                        "label, so `%s`'s label cannot account for it -- annotate it"
                        % (relpath, rule.lineno, name, child, name)
                    )
                stack.append(child)
        if short:
            errs.append(
                "%s:%d: `%s` is labelled [%s] but reaches %s -- its label must cover "
                "what its prerequisites and `$(MAKE)` calls do"
                % (
                    relpath,
                    rule.lineno,
                    name,
                    ",".join(labels_of[name]),
                    ", ".join(
                        "`%s` [%s]" % (c, ",".join(short[c])) for c in sorted(short)
                    ),
                )
            )
    # The write guard: what changes shared state refuses to run unattended.
    shapes = policy["write_shapes"]
    guard_in, guard_errs = _guard_findings(makefiles, policy["unattended_vars"])
    errs.extend(guard_errs)
    needs_guard = []
    for name in sorted(first):
        relpath, at = first[name]
        rule = index[name]
        labels = labels_of.get(name)
        is_write = labels is not None and "write" in labels
        shaped = [s for s in shapes if name.endswith(s)]
        where = "%s:%d: `%s`" % (relpath, at.lineno, name)
        if shaped and not is_write and (rule.help is None or labels is not None):
            errs.append(
                "%s is named like a write (`%s`) but %s -- label it [write]"
                % (
                    where,
                    shaped[0],
                    "carries no effect label"
                    if rule.help is None
                    else "is labelled [%s]" % ",".join(labels),
                )
            )
        if is_write and shapes and not shaped:
            errs.append(
                "%s is labelled [write] but its name ends in none of the "
                "make_targets.write_shapes (%s)" % (where, ", ".join(shapes))
            )
        if (is_write or shaped) and rule.recipe:
            needs_guard.append(name)
            if rule.first_recipe not in _GUARD_CALLS:
                errs.append(
                    "%s: a [write] target opens its recipe with `$(%s)`, so CI and "
                    "gate runs refuse it before it acts (its recipe opens with `%s`)"
                    % (where, _GUARD_NAME, rule.first_recipe)
                )
            elif "-" in rule.first_prefix:
                errs.append(
                    "%s: its `$(%s)` line carries a `-` prefix, so make ignores the "
                    "guard's `exit 1` and runs the recipe under CI and gate runs "
                    "anyway -- drop the `-`" % (where, _GUARD_NAME)
                )
    if needs_guard and guard_in is None:
        errs.append(
            "Makefile: `%s` is never defined, but %s open their recipes with it -- "
            "define it (docs/adr/keel/K-0011-make-target-effect-labels.md)"
            % (_GUARD_NAME, ", ".join("`%s`" % n for n in needs_guard))
        )
    errs.extend(
        "config/project.json: make_targets.effect_proof_skip names `%s`, "
        "which no make target defines -- drop the stale entry" % key
        for key in sorted(policy["effect_proof_skip"])
        if key not in index
    )
    errs.extend(_area_findings(makefiles, by_file, policy["area_dir"]))
    return errs, warns


def check_W():
    """ERROR when an annotated make target has no well-formed effect label or
    two different ones, a composite's label misses what it reaches, a [write] or
    write-shaped target does not open with `$(WRITE_GUARD)` or opens with it
    behind a `-`, the guard misses a configured unattended variable, tests one
    the config omits, or ignores its own failure, the make_targets policy is malformed or stale, or (with
    areas on) an area makefile breaks its header, prefix or include. WARN where
    a recursion or an unlabelled recipe hides an effect. Silent without a
    Makefile; include problems are check_P's to report."""
    if not os.path.isfile(os.path.join(ROOT, "Makefile")):
        return
    manifest = _read_json_config("config/project.json")
    if manifest is _NO_DATA:
        if os.path.isfile(os.path.join(ROOT, "config", "project.json")):
            return  # unreadable: _read_json_config reported it, once
        manifest = None
    policy, perrs = make_targets_policy(manifest)
    for m in perrs:
        err("config/project.json: " + m)
    if policy is None:
        return
    makefiles = walk_makefiles(ROOT, lambda _m: None, lambda _m: None)
    errs, warns_ = _effect_findings(makefiles, policy)
    for m in errs:
        err(m)
    for m in warns_:
        warn(m)


# --- check_X: a child process gets an allowlisted environment --------------------
#
# A process keel's code starts inherits the environment it is given, and a bare
# subprocess call gives it every credential the parent holds: a model CLI, a hook
# tool or a nested make would see the cloud keys, the forge token and the API keys
# of whoever ran the gate. scripts/child_env.py builds the allowlisted environment
# from config/project.json; this check holds every spawn to it, statically
# (docs/adr/keel/K-0012-child-process-environment-allowlist.md). It resolves each call's
# base through the import that binds it in the scope Python would look in, so a
# receiver it cannot resolve (`self.runner(...)`, `sp = subprocess; sp.run`) is
# not seen, and it follows the parent's environment through names in one module
# but not across a parameter: it under-reports and never fires on correct code. There is no waiver -- a spawn that truly needs another variable
# declares it in config/project.json, where review sees it.

# module -> the calls on it that start a process and take env=.
_SPAWN_NEEDS_ENV = {
    "asyncio": ("create_subprocess_exec", "create_subprocess_shell"),
    "subprocess": ("Popen", "call", "check_call", "check_output", "run"),
}
# module -> the calls that start a process the helper cannot reach: they take no
# environment at all, or one this check could not tell from os.environ.
_SPAWN_NO_ENV = {
    "os": ("forkpty", "popen", "posix_spawn", "posix_spawnp", "system"),
    "pty": ("spawn",),
    "subprocess": ("getoutput", "getstatusoutput"),
}
_SPAWN_NO_ENV_PREFIXES = {"os": ("exec", "spawn")}
_HELPER = "build_child_env"
# The two names the helper is imported under: `child_env` from a script that has
# scripts/ on sys.path, `scripts.child_env` from models/, agents/ and mcp/.
_HELPER_MODULES = ("child_env", "scripts.child_env")
# What a use of the bound dict may do besides being a spawn's env=: read it. Any
# other use (a call argument, an alias, a mutating method) lets a value the check
# cannot follow reach the child, so it fails closed.
_READS = ("copy", "get", "items", "keys", "values")
_PARENT_ENV = ("os.environ", "os.environb", "os.getenv", "os.getenvb")
_ADR_0012 = "docs/adr/keel/K-0012-child-process-environment-allowlist.md"

# The nodes Python gives their own names: a def, a lambda, a class body and (in
# Python 3) a comprehension, whose loop variable does not leak.
_FUNCTION_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
_SCOPES = _FUNCTION_SCOPES + (ast.ClassDef,) + _COMPREHENSIONS
# `x := v` is 3.8+; the gate also parses under 3.6, where no such node exists.
_NAMED_EXPR = tuple(t for t in [getattr(ast, "NamedExpr", None)] if t)
# Pattern captures (3.10+) bind a plain-string name; read by type name for 3.6.
_MATCH_NAME = ("MatchAs", "MatchStar")


def _scope_nodes(scope):
    """Every node in scope's own body, not inside a nested scope (a def, lambda,
    class or comprehension); the nested scope's own node is included."""
    out = []
    todo = list(ast.iter_child_nodes(scope))
    while todo:
        node = todo.pop()
        out.append(node)
        if isinstance(node, _SCOPES):
            continue
        todo.extend(ast.iter_child_nodes(node))
    return out


class _Scope(object):
    """One Python scope: its node, the scope it nests in, its own nodes, and
    every name bound in it with the import origin of each binding ("" for a
    binding that is not an import: a def, an assignment, a parameter)."""

    def __init__(self, node, parent):
        self.node = node
        self.parent = parent
        self.nodes = _scope_nodes(node)
        self.declared_global = set()
        self.declared_nonlocal = set()
        self.origins = {}
        self.binds = {}


class _Module(object):
    """A parsed module whose names check_X resolves per scope, as Python does:
    a name bound anywhere in a function is that function's, a class body is
    skipped by the scopes nested in it, and `global`/`nonlocal` redirect a
    binding. A name bound by an import AND another way in one scope is
    ambiguous: the check cannot know which a call means."""

    def __init__(self, tree):
        self.tree = tree
        self.scopes = []
        self.owner = {}  # id(node) -> its innermost _Scope
        self.parents = {}  # id(node) -> the node that holds it
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                self.parents[id(child)] = node
        self.top = self._visit(tree, None)
        for scope in self.scopes:
            for node in scope.nodes:
                if isinstance(node, ast.Global):
                    scope.declared_global.update(node.names)
                elif isinstance(node, ast.Nonlocal):
                    scope.declared_nonlocal.update(node.names)
        for scope in self.scopes:
            self._collect(scope)
        self.tainted = set()  # (id(home scope), name) holding the parent's env
        self._taint()

    def _visit(self, node, parent):
        scope = _Scope(node, parent)
        self.scopes.append(scope)
        for child in scope.nodes:
            self.owner[id(child)] = scope
        for child in scope.nodes:
            if isinstance(child, _SCOPES):
                self._visit(child, scope)
        return scope

    def scope_of(self, node):
        return self.owner.get(id(node), self.top)

    def _enclosing(self, scope):
        """Where a nested scope's free names resolve: class bodies are skipped."""
        up = scope.parent
        while up is not None and isinstance(up.node, ast.ClassDef):
            up = up.parent
        return up

    @staticmethod
    def _binds_here(scope, name):
        for node in scope.nodes:
            if isinstance(node, ast.Name) and node.id == name:
                if not isinstance(node.ctx, ast.Load):
                    return True
            elif (isinstance(node, ast.arg) and node.arg == name) or (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and node.name == name
            ):
                return True
        return False

    def _bind(self, scope, name, origin, node):
        if name in scope.declared_global:
            scope = self.top
        elif name in scope.declared_nonlocal:
            home = self._enclosing(scope)
            up = home
            while up is not None and isinstance(up.node, _FUNCTION_SCOPES):
                if name not in up.declared_nonlocal and self._binds_here(up, name):
                    home = up
                    break
                up = self._enclosing(up)
            scope = home or self.top
        scope.origins.setdefault(name, set()).add(origin)
        scope.binds.setdefault(name, []).append(node)

    def _collect(self, scope):
        loop_vars = set()
        if isinstance(scope.node, _COMPREHENSIONS):
            for gen in scope.node.generators:
                loop_vars.update(id(n) for n in ast.walk(gen.target))
        for node in scope.nodes:
            if isinstance(node, ast.Import):
                for a in node.names:
                    head = a.name.split(".")[0]
                    origin = a.name if a.asname else head
                    self._bind(scope, a.asname or head, origin, node)
            elif isinstance(node, ast.ImportFrom):
                for a in node.names:
                    if a.name == "*":
                        continue
                    origin = ""  # a relative import is this project's own code
                    if node.module and not node.level:
                        origin = node.module + "." + a.name
                    self._bind(scope, a.asname or a.name, origin, node)
            elif isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                self._bind(scope, node.name, "", node)
            elif isinstance(node, ast.arg):
                self._bind(scope, node.arg, "", node)
            elif isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load):
                home = scope
                if (
                    isinstance(scope.node, _COMPREHENSIONS)
                    and id(node) not in loop_vars
                ):
                    # `x := v` inside a comprehension binds in the enclosing scope.
                    while isinstance(home.node, _COMPREHENSIONS):
                        home = home.parent
                self._bind(home, node.id, "", node)
            elif (isinstance(node, ast.ExceptHandler) and node.name) or (
                type(node).__name__ in _MATCH_NAME and getattr(node, "name", None)
            ):
                self._bind(scope, node.name, "", node)
            elif type(node).__name__ == "MatchMapping" and getattr(node, "rest", None):
                self._bind(scope, node.rest, "", node)

    def home(self, name, scope):
        """The scope whose binding of `name` a use in `scope` reads, else None."""
        s = scope
        while s is not None:
            if name in s.declared_global:
                return self.top if name in self.top.origins else None
            if name in s.origins:
                return s
            s = self._enclosing(s)
        return None

    def lookup(self, name, scope):
        """('origin', dotted) / ('ambiguous', (dotted, ...)) / (None, None)."""
        home = self.home(name, scope)
        if home is None:
            return None, None
        origins = home.origins[name]
        imports = tuple(sorted(o for o in origins if o))
        if not imports:
            return None, None
        if len(imports) == 1 and "" not in origins:
            return "origin", imports[0]
        return "ambiguous", imports

    def _chain(self, node):
        parts = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if not isinstance(node, ast.Name):
            return None, None, ""
        kind, value = self.lookup(node.id, self.scope_of(node))
        return kind, value, "".join("." + p for p in reversed(parts))

    def dotted(self, node):
        """The dotted origin of a Name/Attribute chain through the imports, else None."""
        kind, value, rest = self._chain(node)
        return value + rest if kind == "origin" else None

    def candidates(self, node):
        """Every dotted origin an ambiguous Name/Attribute chain may mean, else []."""
        kind, value, rest = self._chain(node)
        return [v + rest for v in value] if kind == "ambiguous" else []

    def spawn_api(self, call):
        origin = self.dotted(call.func)
        kind = _spawn_kind(origin)
        return (kind, origin) if kind else None

    def is_helper_call(self, node):
        """True when node is a call of build_child_env imported from the helper."""
        return isinstance(node, ast.Call) and self.dotted(node.func) in [
            m + "." + _HELPER for m in _HELPER_MODULES
        ]

    # --- the parent's environment, followed through names -------------------------

    def _key(self, node):
        """(id(home), name) for a Name that is not an import, else None."""
        if not isinstance(node, ast.Name):
            return None
        scope = self.scope_of(node)
        home = self.home(node.id, scope)
        if home is None or any(home.origins[node.id]):
            return None  # unbound here, or a module/import: never data
        return id(home), node.id

    def parent_env_in(self, expr):
        """Sorted descriptions of every read of the parent's environment in expr:
        a direct os.environ/os.getenv, or a name bound from one."""
        found = set()
        for sub in ast.walk(expr):
            d = self.dotted(sub)
            if d in _PARENT_ENV:
                found.add(d)
            elif (
                isinstance(sub, ast.Name)
                and isinstance(sub.ctx, ast.Load)
                and self._key(sub) in self.tainted
            ):
                found.add("`%s` (bound from the parent's environment)" % sub.id)
        return sorted(found)

    def _fed(self, node):
        """The targets a node writes a parent-environment value into."""
        pairs = []
        if isinstance(node, ast.Assign):
            pairs = [(t, node.value) for t in node.targets]
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign) + _NAMED_EXPR):
            if node.value is not None:
                pairs = [(node.target, node.value)]
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
            pairs = [(node.target, node.iter)]
        elif isinstance(node, ast.withitem) and node.optional_vars is not None:
            pairs = [(node.optional_vars, node.context_expr)]
        elif isinstance(node, ast.Call) and not self.is_helper_call(node):
            # A call handed the parent's environment may copy it into any name it
            # is also handed, or into its receiver (`d.update(os.environ)`,
            # `dict.update(d, os.environ)`).
            args = list(node.args) + [k.value for k in node.keywords]
            if any(self.parent_env_in(a) for a in args):
                outs = [a for a in args if isinstance(a, ast.Name)]
                if isinstance(node.func, ast.Attribute):
                    outs.append(node.func.value)
                return outs
        return [t for t, v in pairs if self.parent_env_in(v)]

    def _taint(self):
        grew = True
        while grew:
            grew = False
            for scope in self.scopes:
                for node in scope.nodes:
                    for target in self._fed(node):
                        for sub in _written_names(target):
                            key = self._key(sub)
                            if key is not None and key not in self.tainted:
                                self.tainted.add(key)
                                grew = True

    # --- a name bound to the helper's result -----------------------------------

    def _reads_only(self, node):
        """True when a Load of the bound name is a spawn's env= or a read."""
        up = self.parents.get(id(node))
        if isinstance(up, ast.keyword) and up.arg == "env":
            call = self.parents.get(id(up))
            api = self.spawn_api(call) if isinstance(call, ast.Call) else None
            return bool(api) and api[0] == "env"
        if isinstance(up, ast.Subscript) and up.value is node:
            return isinstance(up.ctx, ast.Load)
        if isinstance(up, ast.Attribute) and up.value is node:
            return up.attr in _READS
        return isinstance(up, ast.Compare)

    def name_is_helper_built(self, name, scope):
        """True when every binding of `name` in scope is `name = <helper call>`
        (a sole target, never a parameter, a loop variable or a `nonlocal`
        rebinding from a nested def) and every use of it, in scope and in the
        defs nested in it, is a spawn's env= or a read (`_READS`, `[k]`, `in`)."""
        if self.home(name, scope) is not scope:
            return False  # a free, global or unbound name: not built here
        for event in scope.binds.get(name, []):
            stmt = self.parents.get(id(event))
            if not (
                isinstance(event, ast.Name)
                and isinstance(event.ctx, ast.Store)
                and (
                    (isinstance(stmt, ast.Assign) and stmt.targets == [event])
                    or (isinstance(stmt, ast.AnnAssign) and stmt.target is event)
                )
                and self.is_helper_call(stmt.value)
            ):
                return False
        for other in self.scopes:
            for node in other.nodes:
                if (
                    isinstance(node, ast.Name)
                    and node.id == name
                    and isinstance(node.ctx, ast.Load)
                    and self.home(name, other) is scope
                    and not self._reads_only(node)
                ):
                    return False
        return True

    # --- a spawn API used as a value --------------------------------------------

    def _type_positions(self):
        """ids of every node in an annotation or an isinstance/issubclass call,
        where naming subprocess.Popen is a type, not a spawn."""
        out = set()
        roots = []
        for node in ast.walk(self.tree):
            if isinstance(node, ast.arg) and node.annotation is not None:
                roots.append(node.annotation)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.returns is not None:
                    roots.append(node.returns)
            elif isinstance(node, ast.AnnAssign):
                roots.append(node.annotation)
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in ("isinstance", "issubclass")
            ):
                roots.extend(node.args[1:])
        for root in roots:
            out.update(id(n) for n in ast.walk(root))
        return out

    def references(self):
        """[(lineno, origin)] for every spawn API named without being called."""
        typed = self._type_positions()
        out = []
        for node in ast.walk(self.tree):
            if not isinstance(node, (ast.Name, ast.Attribute)):
                continue
            if not isinstance(node.ctx, ast.Load) or id(node) in typed:
                continue
            up = self.parents.get(id(node))
            if isinstance(up, ast.Call) and up.func is node:
                continue
            if isinstance(up, ast.Attribute):
                continue  # the middle of a longer chain (`subprocess.run.__doc__`)
            origin = self.dotted(node)
            if _spawn_kind(origin):
                out.append((node.lineno, origin))
        return out


def _written_names(target):
    """The Names an assignment target writes into: each element of a tuple or
    list target, and the container of `d[k] = v` or `d.x = v` (never `k`)."""
    out = []
    todo = [target]
    while todo:
        node = todo.pop()
        if isinstance(node, ast.Name):
            out.append(node)
        elif isinstance(node, (ast.Tuple, ast.List)):
            todo.extend(node.elts)
        elif isinstance(node, (ast.Starred, ast.Subscript, ast.Attribute)):
            todo.append(node.value)
    return out


def _spawn_kind(origin):
    """'env' / 'no-env' for a dotted origin that starts a process, else None."""
    if not origin or "." not in origin:
        return None
    module, name = origin.rsplit(".", 1)
    if name in _SPAWN_NEEDS_ENV.get(module, ()):
        return "env"
    if name in _SPAWN_NO_ENV.get(module, ()) or any(
        name.startswith(p) for p in _SPAWN_NO_ENV_PREFIXES.get(module, ())
    ):
        return "no-env"
    return None


def _parse_module(source):
    try:
        return _Module(ast.parse(source))
    except (SyntaxError, ValueError):
        return None


def spawn_sites(source):
    """Sorted (lineno, origin) for every call in source that starts a process
    through an API check_X resolves. [] when the source does not parse."""
    mod = _parse_module(source)
    if mod is None:
        return []
    sites = []
    for node in ast.walk(mod.tree):
        if isinstance(node, ast.Call):
            api = mod.spawn_api(node)
            if api:
                sites.append((node.lineno, api[1]))
    return sorted(sites)


def spawn_findings(source, relpath):
    """check_X's errors for one module, sorted by line. Pure.

    A source that does not parse yields [] -- a syntax error is another check's
    to report."""
    mod = _parse_module(source)
    if mod is None:
        return []
    found = []
    for lineno, origin in mod.references():
        found.append(
            (
                lineno,
                "%s:%d: `%s` is referenced, not called, so the env= the child is "
                "eventually started with cannot be read -- call it directly with "
                "env=build_child_env() from scripts/child_env.py (%s)"
                % (relpath, lineno, origin, _ADR_0012),
            )
        )
    for node in ast.walk(mod.tree):
        if not isinstance(node, ast.Call):
            continue
        where = "%s:%d: " % (relpath, node.lineno)
        if mod.is_helper_call(node):
            leaks = sorted(
                {d for a in node.args + node.keywords for d in mod.parent_env_in(a)}
            )
            if leaks:
                found.append(
                    (
                        node.lineno,
                        where + "build_child_env is handed %s, which copies the "
                        "parent's environment past the allowlist -- declare the name "
                        "in config/project.json child_env.names, or an adapter's "
                        "credential in models.credential_env (%s)"
                        % (", ".join(leaks), _ADR_0012),
                    )
                )
            continue
        api = mod.spawn_api(node)
        if api is None:
            spawns = [c for c in mod.candidates(node.func) if _spawn_kind(c)]
            if spawns:
                found.append(
                    (
                        node.lineno,
                        where + "the name called here is bound both by an import "
                        "of `%s` and another way in one scope, so this check cannot "
                        "tell whether it starts a process -- rename one binding (%s)"
                        % ("`, `".join(spawns), _ADR_0012),
                    )
                )
            continue
        kind, origin = api
        if kind == "no-env":
            found.append(
                (
                    node.lineno,
                    where + "`%s` cannot take an allowlisted environment the gate "
                    "can verify -- start the child with subprocess.run(..., "
                    "env=build_child_env()) from scripts/child_env.py (%s)"
                    % (origin, _ADR_0012),
                )
            )
            continue
        if any(kw.arg is None for kw in node.keywords):
            found.append(
                (
                    node.lineno,
                    where + "`%s` is passed **kwargs, so the env= it starts the "
                    "child with cannot be read -- pass env=build_child_env() "
                    "explicitly (%s)" % (origin, _ADR_0012),
                )
            )
            continue
        env = [kw.value for kw in node.keywords if kw.arg == "env"]
        if not env:
            found.append(
                (
                    node.lineno,
                    where + "`%s` passes no env=, so the child inherits every "
                    "credential this process holds -- pass env=build_child_env() "
                    "from scripts/child_env.py (%s)" % (origin, _ADR_0012),
                )
            )
            continue
        value = env[0]
        ok = mod.is_helper_call(value) or (
            isinstance(value, ast.Name)
            and mod.name_is_helper_built(value.id, mod.scope_of(node))
        )
        if not ok:
            found.append(
                (
                    node.lineno,
                    where + "`%s` passes an env= that is not built by "
                    "scripts/child_env.py build_child_env (directly, or through a "
                    "name every assignment in this function binds to it and that "
                    "is only ever read, never mutated, aliased or handed on) -- the "
                    "child may inherit what the allowlist leaves out (%s)"
                    % (origin, _ADR_0012),
                )
            )
    return [m for _, m in sorted(found)]


def _spawn_roots():
    """check_X's scope: every top-level directory but tests/ -- the taxonomy's
    code homes, evals/ (the model and agent harness) and ops/ among them, a
    declared extra_toplevel name, and an undeclared one (check_B reds the gate
    over it too, and the author sees both at once). A hidden or ignored
    directory (CONVENTIONS section 5) and a symlinked one, which no check reads
    through (check_B warns), are skipped."""
    roots = []
    for name in sorted(os.listdir(ROOT)):
        full = os.path.join(ROOT, name)
        if name.startswith(".") or name in IGNORE_DIRS or name == "tests":
            continue
        if os.path.isdir(full) and not os.path.islink(full):
            roots.append(name)
    return roots


def check_X():
    """ERROR when a module at the top level or under a spawn root
    (`_spawn_roots`: every code home but tests/) starts a process
    without env= built by scripts/child_env.py build_child_env, through an API
    that cannot take one, passes **kwargs to a spawn, or hands the helper the
    parent's environment; and when config/project.json `child_env` (or the
    `make_targets` and `models.credential_env` names it reads) is malformed while
    a spawn exists or the block does, including a `credentialed_values` entry
    that no allowlist source copies. Silent when nothing spawns and no block
    exists; an unreadable manifest is reported once, by the reader."""
    modules = {}
    for name in sorted(os.listdir(ROOT)):
        if name.endswith(".py") and os.path.isfile(os.path.join(ROOT, name)):
            try:
                with open(os.path.join(ROOT, name), encoding="utf-8-sig") as fh:
                    modules[name] = fh.read()
            except UNREADABLE:
                continue  # unreadable is reported by the checks keyed on it
    for root in _spawn_roots():
        base = os.path.join(ROOT, root)
        for dirpath, _, filenames in walk(base):
            for f in filenames:
                if not f.endswith(".py"):
                    continue
                try:
                    with open(os.path.join(dirpath, f), encoding="utf-8-sig") as fh:
                        modules[rel(os.path.join(dirpath, f)).replace(os.sep, "/")] = (
                            fh.read()
                        )
                except UNREADABLE:
                    continue  # unreadable is reported by the checks keyed on it
    findings = []
    spawns = False
    for path in sorted(modules):
        spawns = spawns or bool(spawn_sites(modules[path]))
        findings.extend(spawn_findings(modules[path], path))
    manifest = _read_json_config("config/project.json")
    if manifest is _NO_DATA:
        if os.path.isfile(os.path.join(ROOT, "config", "project.json")):
            manifest = None  # unreadable: _read_json_config reported it, once
        else:
            manifest = {}
    has_block = isinstance(manifest, dict) and "child_env" in manifest
    if manifest is not None and (spawns or has_block):
        _, perrs = child_env.child_env_policy(manifest)
        for m in perrs:
            err(
                m
                if m.startswith("config/project.json")
                else "config/project.json: " + m
            )
    for m in findings:
        err(m)


# --- check_Y: ADR number spaces --------------------------------------------------
#
# A template ships its own ADRs into every project it generates, and a project
# writes its own. In one numbered directory the two collide: bedrock-platform's
# own 0010 sat beside keel's 0010-0012, and project-jarvis's 0005-0011 beside
# keel's 0005-0012 (measured; docs/adr/keel/K-0013-template-and-project-adr-number-spaces.md).
# config/project.json `adr` names two spaces: the project's (plain numbers) and
# the template's (numbers behind a prefix), each numbered on its own. check_Y
# holds every ADR file to the space it sits in, and every `kind: adr` document
# to one of the two directories. Which names the template owns is a fact the
# template ships with the block (`template_adrs`): a project's own decision
# written into the template space under a free K- number would meet the
# template's next ADR of that number on update, the original collision moved.
# Whether a project edited a template ADR is not decidable from one tree, so it
# is not judged here: scripts/jobs/keep_edited_retired.py guards it on update
# and scripts/audit_project.py's `retired` group reports it.
_ADR_BLOCK = "adr"
_ADR_KEYS = (
    "project_dir",
    "template_dir",
    "template_prefix",
    "number_digits",
    "template_adrs",
)
# The label files a directory carries (check_B's pair plus the README): never
# an ADR, whatever directory they label.
_ADR_LABELS = ("README.md", "AGENT.md", "CLAUDE.md")
# A slug is lower-case words joined by single hyphens: the grammar every ADR
# file name keel and its two measured downstream projects use already has.
_ADR_SLUG = r"[a-z0-9]+(?:-[a-z0-9]+)*"
_ADR_KIND = re.compile(r"^kind:[ \t]*['\"]?adr['\"]?[ \t]*$", re.MULTILINE)


def adr_policy(manifest):
    """config/project.json's `adr` block -> (policy, errs). Pure.

    policy is a dict of _ADR_KEYS (the directories as given, without a trailing
    slash) or None when errs is not empty: a consumer refuses rather than
    half-trusting it. Every key is required and an unknown key is an error
    (`_comment` aside), so a typo cannot fall back to a default."""
    if not isinstance(manifest, dict) or _ADR_BLOCK not in manifest:
        return None, [
            "%s is missing -- a project with ADRs (kind: adr) declares its ADR "
            "number spaces there (CONVENTIONS §19)" % _ADR_BLOCK
        ]
    block = manifest[_ADR_BLOCK]
    if not isinstance(block, dict):
        return None, [
            "%s must be an object, got %s" % (_ADR_BLOCK, type(block).__name__)
        ]
    errs = [
        "%s is missing `%s`" % (_ADR_BLOCK, key)
        for key in _ADR_KEYS
        if key not in block
    ]
    errs.extend(
        "%s has an unknown key `%s`" % (_ADR_BLOCK, key)
        for key in sorted(block)
        if key not in _ADR_KEYS and key != "_comment"
    )
    if errs:
        return None, errs
    policy = {}
    for key in ("project_dir", "template_dir", "template_prefix"):
        value = block[key]
        if not isinstance(value, str) or not value.strip():
            errs.append("%s.%s must be a non-empty string" % (_ADR_BLOCK, key))
            continue
        policy[key] = value.rstrip("/") if key.endswith("_dir") else value
    for key in ("project_dir", "template_dir"):
        value = policy.get(key)
        if value is None:
            continue
        parts = value.split("/")
        if value.startswith("/") or ".." in parts or "" in parts:
            errs.append(
                "%s.%s must be a relative path inside the project, got %r"
                % (_ADR_BLOCK, key, block[key])
            )
    project_dir = policy.get("project_dir")
    if project_dir is not None and project_dir == policy.get("template_dir"):
        errs.append(
            "%s.template_dir must differ from %s.project_dir: the two number "
            "spaces are two directories" % (_ADR_BLOCK, _ADR_BLOCK)
        )
    prefix = policy.get("template_prefix")
    if prefix is not None and prefix[:1].isdigit():
        errs.append(
            "%s.template_prefix must not start with a digit, or a template ADR's "
            "name would read as a project number" % _ADR_BLOCK
        )
    digits = block["number_digits"]
    if isinstance(digits, bool) or not isinstance(digits, int) or digits < 1:
        errs.append("%s.number_digits must be an integer >= 1" % _ADR_BLOCK)
    else:
        policy["number_digits"] = digits
    owned = block["template_adrs"]
    if not isinstance(owned, list) or not all(isinstance(n, str) for n in owned):
        errs.append(
            "%s.template_adrs must be a list of the file names the template "
            "ships in template_dir" % _ADR_BLOCK
        )
    elif not errs:
        template_re = _adr_grammars(policy)[1]
        shape = policy["template_prefix"] + "N" * policy["number_digits"]
        errs.extend(
            "%s.template_adrs names %r, not a %s-<slug>.md file name"
            % (_ADR_BLOCK, name, shape)
            for name in owned
            if not template_re.match(name)
        )
        errs.extend(
            "%s.template_adrs names %r twice" % (_ADR_BLOCK, name)
            for name in sorted({n for n in owned if owned.count(n) > 1})
        )
        policy["template_adrs"] = list(owned)
    return (None, errs) if errs else (policy, [])


def _adr_grammars(policy):
    """(project pattern, template pattern), each capturing the number."""
    number = r"([0-9]{%d})" % policy["number_digits"]
    tail = "-" + _ADR_SLUG + r"\.md"
    return (
        re.compile(number + tail + "$"),
        re.compile(re.escape(policy["template_prefix"]) + number + tail + "$"),
    )


def adr_inventory(policy):
    """{"project": [...], "template": [...]}: every ADR candidate directly in
    each space -- a Markdown file (`.md` in any case) that is not a label -- as
    (number, relpath), number None when the name is outside the space's
    grammar. Sorted by path. An absent directory is an empty space."""
    project_re, template_re = _adr_grammars(policy)
    out = {}
    for space, key, grammar in (
        ("project", "project_dir", project_re),
        ("template", "template_dir", template_re),
    ):
        base = os.path.join(ROOT, *policy[key].split("/"))
        names = []
        if os.path.isdir(base):
            names = sorted(
                n
                for n in os.listdir(base)
                if n.lower().endswith(".md")
                and n not in _ADR_LABELS
                and os.path.isfile(os.path.join(base, n))
            )
        found = []
        for name in names:
            m = grammar.match(name)
            found.append((m.group(1) if m else None, policy[key] + "/" + name))
        out[space] = found
    return out


def adr_documents():
    """Every Markdown document under ROOT whose frontmatter declares
    `kind: adr`, as sorted relpaths with `/` separators. A tree with one has
    ADRs, so it must say where they live; one outside both spaces is judged
    by check_Y."""
    found = []
    for dirpath, _, filenames in walk(ROOT):
        for f in filenames:
            if not f.lower().endswith(".md"):
                continue
            full = os.path.join(dirpath, f)
            try:
                with open(full, encoding="utf-8") as fh:
                    text = fh.read()
            except UNREADABLE:
                continue  # check_A reports an unreadable document
            if not text.startswith("---"):
                continue
            end = text.find("\n---", 3)
            if end > 0 and _ADR_KIND.search(text, 3, end):
                found.append(rel(full).replace(os.sep, "/"))
    return sorted(found)


def _unquote(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def check_Y():
    """ERROR when config/project.json `adr` is missing (in a tree with a
    `kind: adr` document) or malformed; when a project-space ADR carries the
    template prefix or is not NNNN-<slug>.md; when a template-space ADR is not
    <prefix>NNNN-<slug>.md (it names the project space as where an unprefixed
    one belongs) or is not a name `adr.template_adrs` lists, and when a listed
    name is not a file there; when a `kind: adr` document lives anywhere but
    directly in one of the two spaces; when two ADRs share a number within one space (the same
    number once in each space is the point); and when an ADR's frontmatter
    kind is not adr or its title does not begin ADR-<prefix?>NNNN: for its own
    file. WARN when both spaces hold no ADR. Silent with neither a block nor
    an ADR; an unreadable manifest is reported once, by the reader. A kept
    copy of a template ADR the project edited shares its id with the template's
    file, and check_A's duplicate-id error already names both."""
    manifest = _read_json_config(os.path.join("config", "project.json"))
    if manifest is _NO_DATA:
        if os.path.isfile(os.path.join(ROOT, "config", "project.json")):
            return  # unreadable: _read_json_config reported it, once
        manifest = {}
    documents = adr_documents()
    if isinstance(manifest, dict) and _ADR_BLOCK not in manifest and not documents:
        return
    policy, perrs = adr_policy(manifest)
    for m in perrs:
        err("config/project.json: " + m)
    if policy is None:
        return
    spaces = adr_inventory(policy)
    prefix = policy["template_prefix"]
    shape = "N" * policy["number_digits"]
    project_re, template_re = _adr_grammars(policy)
    for number, path in spaces["project"]:
        name = path.rsplit("/", 1)[1]
        if template_re.match(name) or name.startswith(prefix):
            err(
                "%s: an ADR named with the template prefix '%s' is a template "
                "ADR; it belongs in %s, not in the project space %s"
                % (path, prefix, policy["template_dir"], policy["project_dir"])
            )
        elif number is None:
            err(
                "%s: an ADR in %s is named %s-<slug>.md (a lower-case "
                "hyphenated slug)" % (path, policy["project_dir"], shape)
            )
    owned = policy["template_adrs"]
    for number, path in spaces["template"]:
        if number is None:
            err(
                "%s: the template space %s holds only %s%s-<slug>.md; a project "
                "ADR belongs in %s"
                % (path, policy["template_dir"], prefix, shape, policy["project_dir"])
            )
        elif path.rsplit("/", 1)[1] not in owned:
            err(
                "%s: the template does not ship this ADR (config/project.json "
                "adr.template_adrs), so the template's own next ADR of that "
                "number would meet it on update; a project's decision belongs in "
                "%s as %s-<slug>.md, and a template lists each ADR it ships"
                % (path, policy["project_dir"], shape)
            )
    present = {path.rsplit("/", 1)[1] for _n, path in spaces["template"]}
    for name in owned:
        if name not in present:
            err(
                "config/project.json: adr.template_adrs names %s, which %s "
                "lacks; the list names exactly the ADRs the template ships"
                % (name, policy["template_dir"])
            )
    homes = (policy["project_dir"], policy["template_dir"])
    for path in documents:
        parent = path.rsplit("/", 1)[0] if "/" in path else ""
        if parent not in homes:
            err(
                "%s: an ADR (kind: adr) lives directly in %s or %s, where it is "
                "numbered against the others in its space"
                % (path, policy["project_dir"], policy["template_dir"])
            )
    for space, label in (("project", ""), ("template", prefix)):
        by_number = {}
        for number, path in spaces[space]:
            if number is not None:
                by_number.setdefault(number, []).append(path)
        for number in sorted(by_number):
            paths = by_number[number]
            if len(paths) > 1:
                err(
                    "%s: ADR number %s%s is also taken by %s (a number is unique "
                    "within its space)"
                    % (paths[0], label, number, ", ".join(paths[1:]))
                )
        for number in sorted(by_number):
            for path in by_number[number]:
                full = os.path.join(ROOT, *path.split("/"))
                try:
                    with open(full, encoding="utf-8"):
                        pass
                except UNREADABLE:
                    continue  # check_A reports an unreadable document
                fm = parse_frontmatter(full) or {}
                kind = _unquote(fm.get("kind", ""))
                if kind != "adr":
                    err("%s: an ADR has frontmatter kind: adr, not '%s'" % (path, kind))
                want = "ADR-%s%s:" % (label, number)
                title = _unquote(fm.get("title", ""))
                if not title.startswith(want):
                    err(
                        "%s: an ADR's title begins '%s', naming its own file (got "
                        "'%s')" % (path, want, title)
                    )
    if not spaces["project"] and not spaces["template"]:
        warn(
            "ADR number spaces: %s and %s hold no ADR (config/project.json adr)"
            % (policy["project_dir"], policy["template_dir"])
        )


# Every check, in the order a run makes them. tests/unit/scripts/
# test_check_structure_root.py fails a check_<LETTER> defined but not listed.
CHECKS = (
    ("A", check_A),
    ("B", check_B),
    ("C", check_C),
    ("D", check_D),
    ("E", check_E),
    ("F", check_F),
    ("G", check_G),
    ("H", check_H),
    ("I", check_I),
    ("J", check_J),
    ("K", check_K),
    ("L", check_L),
    ("M", check_M),
    ("N", check_N),
    ("O", check_O),
    ("P", check_P),
    ("Q", check_Q),
    ("R", check_R),
    ("S", check_S),
    ("T", check_T),
    ("U", check_U),
    ("V", check_V),
    ("W", check_W),
    ("X", check_X),
    ("Y", check_Y),
)

# The JSON configs the checks read through _read_json_config, so a caller that
# reports on them (scripts/audit_project.py's config group) derives the set
# instead of re-typing it; the mirror test fails a third config read but not
# listed here.
JSON_CONFIGS = (
    os.path.join("config", "project.json"),
    os.path.join("config", "practices.json"),
)


def run_checks(root):
    """Every check in CHECKS against the tree at *root*, as a list of
    (letter, "error" | "warning", message) in emission order. Prints nothing.

    Resets the state a run accumulates (errors, warnings, GOVERNED, the config
    memo and the reported-unreadable set), so two runs in one process share
    nothing."""
    global ROOT, errors, warnings, GOVERNED, _CONFIG_READ, _READ_REPORTED
    ROOT = os.path.abspath(root)
    errors = []
    warnings = []
    GOVERNED = []
    _CONFIG_READ = {}
    _READ_REPORTED = set()
    found = []
    for letter, check in CHECKS:
        n_err, n_warn = len(errors), len(warnings)
        check()
        # Warnings first within a letter: a check emits both kinds interleaved,
        # but no consumer reads the order across tiers, only within one.
        found.extend((letter, "warning", m) for m in warnings[n_warn:])
        found.extend((letter, "error", m) for m in errors[n_err:])
    return found


def main(argv=None):
    """The gate's CLI. *argv* None means no arguments, never sys.argv: an
    importer calling main() gets the template's own judgement."""
    ap = argparse.ArgumentParser(
        description="Enforce the project conventions (checks A-Y); exit 1 on error."
    )
    ap.add_argument(
        "--root",
        default=_OWN_ROOT,
        help="the tree to judge (default: this checkout)",
    )
    args = ap.parse_args([] if argv is None else argv)
    if not os.path.isdir(args.root):
        ap.exit(2, "check_structure: --root %s is not a directory\n" % args.root)
    found = run_checks(args.root)
    for _letter, tier, m in found:
        if tier == "warning":
            print("WARN  " + m)
    for _letter, tier, m in found:
        if tier == "error":
            print("ERROR " + m)
    n_err = sum(1 for f in found if f[1] == "error")
    print()
    print("check_structure: %d error(s), %d warning(s)" % (n_err, len(found) - n_err))
    # The nudge, on the line everyone already reads: what this gate does not fail
    # on has its own doers, and they are one command away.
    print(
        "next: `make advise` reports what this gate does not fail on; "
        "`make doc-review` runs the doc reviewer (dry-run)"
    )
    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
