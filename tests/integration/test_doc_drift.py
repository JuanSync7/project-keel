"""
title: Integration — shipped documents say nothing true of one host or one moment
kind: tests
layer: n/a
summary: The shipped-doc drift gate. A shipped document is any Markdown file (or its `.md.jinja` twin) outside config/project.json `doc_drift.history_paths`; in its prose it names no concrete campaign or slice id (the `work_naming` mention grammar, any prefix), matches no `doc_drift.forbidden_phrases` pattern, names no loopback port that no non-Markdown file declares, and cites no document copier.yml `_exclude`s unconditionally. Code spans and fences are illustrations and are exempt from the prose rules, as check_Z treats them. Every expected set is derived from the thing it describes, never typed here; a missing or malformed `doc_drift` or `work_naming` block fails, a scan over zero documents fails, and only the copier.yml-derived test skips, with a stated reason, in a generated project. Each rule has a fault-injection twin that plants one item and asserts exactly one finding. Not a writer: it reads the tree and writes only under pytest's tmp_path.
"""

import ast
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import optional_deps

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))

import check_structure as cs  # noqa: E402
import review_docs  # noqa: E402
from child_env import build_child_env  # noqa: E402

pytestmark = pytest.mark.integration

_BLOCK = "doc_drift"
_TEMPLATE_ONLY = "not a copier template — this is a generated project"
_TWIN_SUFFIX = ".jinja"
_DOC_SUFFIXES = (".md", ".md" + _TWIN_SUFFIX)
# A loopback URL's port. Raw text is scanned, fences and code spans included:
# a port a reader is told to open is a claim wherever it is written.
_LOOPBACK_PORT = re.compile(r"\b(?:localhost|127\.0\.0\.1):([0-9]{2,5})\b")
# copier.yml's `_exclude` entries carry jinja conditionals; an entry with one
# is answer-driven, an entry without one never ships.
_JINJA_TAG = re.compile(r"\{%.*?%\}")
# One entry of the README's layout tree: a box-drawing branch, then a name
# with a trailing slash (a directory; files carry none).
_TREE_DIR = re.compile(r"^[├└]── (\S+)/")
# A waiver pragma as a checker's own module-level `re.compile` spells it in
# source: `#\s*<word>-ok`. Read over source text, so the `\s*` is literal.
_PRAGMA = re.compile(r"#\\s\*([a-z]+(?:-[a-z]+)*-ok)")
# The checkers whose module-level regexes may declare a pragma.
_CHECKER_GLOB = "scripts/check_*.py"
# check_practices.py runs a practice whose status starts with this; any other
# status is a way to switch one off, so it is a waiver.
_ACTIVE_STATUS = "on"
# The tables the two guides are read through, found by their columns so a
# heading can be reworded without blinding the gate.
_EXIT_TABLE = ("Script", "Exit")
_CHECKLIST_TABLE = ("Step", "Exit", "Recovery")
_EXCLUSION_TABLE = ("Path", "Arrives")
_PASSES_THROUGH = "passes through"
# The key whose prefixes exempt a document from this gate: a waiver too.
_HISTORY_KEY = "history_paths"
# The child-process allowlist module and the names of its config block and of
# the tuple of keys it reads; every key there widens or narrows what a child
# inherits, so each is a lever the limits guide names.
_CHILD_ENV = "scripts/child_env.py"
_CHILD_ENV_NAMES = ("_BLOCK", "_BLOCK_KEYS")
# A checklist Step cell opening with this is a `_tasks` entry; any other row is
# a `_migrations` entry.
_TASK_MARK = "task:"


class DocDriftConfigError(AssertionError):
    """The gate cannot judge: the manifest or a block it reads is missing or
    malformed. Raised, never skipped."""


# --- config ---------------------------------------------------------------


def load_manifest(root):
    path = Path(root) / "config" / "project.json"
    if not path.is_file():
        raise DocDriftConfigError("config/project.json is missing")
    with path.open(encoding="utf-8") as fh:
        manifest = json.load(fh)
    if not isinstance(manifest, dict):
        raise DocDriftConfigError("config/project.json: top level is not an object")
    return manifest


def drift_policy(manifest):
    """The `doc_drift` keys this file reads, validated. Raises
    DocDriftConfigError naming the key, so a typo cannot fall back to nothing."""
    block = manifest.get(_BLOCK)
    if not isinstance(block, dict):
        raise DocDriftConfigError(
            "config/project.json: `%s` is missing or not an object" % _BLOCK
        )
    history = block.get(_HISTORY_KEY)
    if (
        not isinstance(history, list)
        or not history
        or not all(isinstance(p, str) and p.strip() for p in history)
    ):
        raise DocDriftConfigError(
            "config/project.json: `%s.%s` must be a non-empty list of "
            "path prefixes" % (_BLOCK, _HISTORY_KEY)
        )
    phrases = block.get("forbidden_phrases")
    if not isinstance(phrases, dict) or not phrases:
        raise DocDriftConfigError(
            "config/project.json: `%s.forbidden_phrases` must be a non-empty map "
            "from regex to reason" % _BLOCK
        )
    compiled = []
    for pattern, reason in sorted(phrases.items()):
        if not isinstance(reason, str) or not reason.strip():
            raise DocDriftConfigError(
                "config/project.json: `%s.forbidden_phrases` %r has no reason"
                % (_BLOCK, pattern)
            )
        try:
            compiled.append((re.compile(pattern), reason))
        except re.error as e:
            raise DocDriftConfigError(
                "config/project.json: `%s.forbidden_phrases` %r is not a regex (%s)"
                % (_BLOCK, pattern, e)
            ) from e
    return {_HISTORY_KEY: tuple(history), "forbidden_phrases": compiled}


def work_mention(manifest):
    """The `work_naming` mention regex: finds any campaign or slice id in prose,
    with or without a `<project>:` prefix."""
    policy, errs = cs.work_naming_policy(manifest)
    if policy is None:
        raise DocDriftConfigError("config/project.json: " + "; ".join(errs))
    return cs.id_grammar(policy)["mention"]


def _nonempty_str(block, key):
    value = block.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DocDriftConfigError(
            "config/project.json: `%s.%s` must be a non-empty string" % (_BLOCK, key)
        )
    return value


def entry_policy(manifest):
    """The `doc_drift` keys the entry-document, guide-audience, limits-guide
    and upgrade-guide rules read, validated the way `drift_policy` validates
    its own: a missing or mistyped key raises naming it."""
    block = manifest.get(_BLOCK)
    if not isinstance(block, dict):
        raise DocDriftConfigError(
            "config/project.json: `%s` is missing or not an object" % _BLOCK
        )
    one_hop = block.get("one_hop")
    if (
        not isinstance(one_hop, dict)
        or not one_hop
        or not all(
            isinstance(doc, str)
            and doc.strip()
            and isinstance(targets, list)
            and targets
            and all(isinstance(t, str) and t.strip() for t in targets)
            for doc, targets in one_hop.items()
        )
    ):
        raise DocDriftConfigError(
            "config/project.json: `%s.one_hop` must map each entry document to a "
            "non-empty list of the documents it links to" % _BLOCK
        )
    audiences = block.get("audiences")
    if (
        not isinstance(audiences, list)
        or not audiences
        or not all(isinstance(a, str) and a.strip() for a in audiences)
        or len(set(audiences)) != len(audiences)
    ):
        raise DocDriftConfigError(
            "config/project.json: `%s.audiences` must be a non-empty list of "
            "distinct names, in the order a cell lists them" % _BLOCK
        )
    policy = {"one_hop": {d: tuple(t) for d, t in sorted(one_hop.items())}}
    policy["audiences"] = tuple(audiences)
    for key in ("layout_heading", "roster", "limits_guide", "upgrade_guide"):
        policy[key] = _nonempty_str(block, key)
    policy["gate_target"] = _nonempty_str(block, "gate_target")
    return policy


# --- the documents --------------------------------------------------------


def _untwinned(relpath):
    return relpath.removesuffix(_TWIN_SUFFIX)


def shipped_docs(root, history_paths):
    """[(relpath, text)] for every shipped Markdown document under *root* and
    every `.md.jinja` twin, sorted. A path (twin suffix stripped) under a
    history prefix is history and is left out; a symlink is read under its
    target's name, as `cs._markdown_texts` does."""
    out = []
    for dirpath, _dirs, files in cs.walk(str(root)):
        for name in files:
            full = os.path.join(dirpath, name)
            if not name.endswith(_DOC_SUFFIXES) or os.path.islink(full):
                continue
            relpath = os.path.relpath(full, str(root)).replace(os.sep, "/")
            if _untwinned(relpath).startswith(history_paths):
                continue
            with open(full, encoding="utf-8") as fh:
                out.append((relpath, fh.read()))
    return sorted(out)


def _git_listed(root, untracked=True):
    """Files git would hand a commit: tracked plus, with *untracked*,
    untracked-and-unignored. None when *root* is not a git work tree. Ignored
    files are generated views (wiki/corpus.json, llms-full.txt) that copy
    Markdown text verbatim, so reading them would let a doc declare its own
    port."""
    if shutil.which("git") is None:
        return None
    env = build_child_env()
    probe = subprocess.run(
        review_docs.git_argv(str(root), "rev-parse", "--is-inside-work-tree"),
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        env=env,
    )
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        return None
    which = (
        ["--cached", "--others", "--exclude-standard"] if untracked else ["--cached"]
    )
    listed = subprocess.run(
        review_docs.git_argv(str(root), "ls-files", "-z", *which),
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=True,
    )
    return sorted(p for p in listed.stdout.decode("utf-8").split("\0") if p)


def _non_markdown_files(root):
    listed = _git_listed(root)
    if listed is None:
        listed = []
        for dirpath, _dirs, files in cs.walk(str(root)):
            for name in files:
                full = os.path.join(dirpath, name)
                listed.append(os.path.relpath(full, str(root)).replace(os.sep, "/"))
    return [p for p in listed if not p.endswith(_DOC_SUFFIXES)]


def declared_ports(root, wanted):
    """The subset of *wanted* port strings that some non-Markdown file under
    *root* names as a whole word."""
    found = set()
    if not wanted:
        return found
    pattern = re.compile(
        r"(?<![0-9])(%s)(?![0-9])" % "|".join(sorted(map(re.escape, wanted)))
    )
    for relpath in _non_markdown_files(root):
        full = Path(root) / relpath
        if full.is_symlink() or not full.is_file():
            continue
        try:
            text = full.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        found.update(pattern.findall(text))
        if found >= set(wanted):
            break
    return found


# --- the rules ------------------------------------------------------------


def moment_and_host_findings(docs, policy, mention, port_root):
    """Findings for rule (a) over *docs*: a concrete work id or a forbidden
    phrase in prose, or a loopback port in raw text that no non-Markdown file
    under *port_root* declares. Each finding is `relpath:line: message`."""
    findings = []
    ports = {}
    for relpath, text in docs:
        for i, line in enumerate(cs._prose_lines(text), 1):
            findings.extend(
                "%s:%d: names the work id %r in prose -- a slice id is history; "
                "say what is true now, or move the text under doc_drift."
                "history_paths" % (relpath, i, m.group(0))
                for m in mention.finditer(line)
            )
            for regex, reason in policy["forbidden_phrases"]:
                m = regex.search(line)
                if m:
                    findings.append(
                        "%s:%d: %r -- %s" % (relpath, i, m.group(0).strip(), reason)
                    )
        for i, line in enumerate(text.split("\n"), 1):
            for m in _LOOPBACK_PORT.finditer(line):
                ports.setdefault(m.group(1), []).append((relpath, i, m.group(0)))
    declared = declared_ports(port_root, set(ports))
    for port in sorted(set(ports) - declared):
        for relpath, i, url in ports[port]:
            findings.append(
                "%s:%d: names %s, but no non-Markdown file declares port %s -- "
                "a port from one machine" % (relpath, i, url, port)
            )
    return sorted(findings)


def never_shipped_docs(root):
    """The `.md` paths copier.yml `_exclude`s unconditionally -- documents no
    generated project ever has. None when *root* is not the template."""
    copier_yml = Path(root) / "copier.yml"
    if not copier_yml.is_file():
        return None
    yaml = optional_deps.importorskip("yaml", extra="template")
    cfg = yaml.safe_load(copier_yml.read_text(encoding="utf-8"))
    entries = cfg.get("_exclude") if isinstance(cfg, dict) else None
    if not isinstance(entries, list):
        raise DocDriftConfigError("copier.yml: `_exclude` is missing or not a list")
    return sorted(
        e for e in entries if isinstance(e, str) and "{%" not in e and e.endswith(".md")
    )


def _without_tables(text, column_sets):
    """*text* with the body rows of each pipe table whose header carries one
    of *column_sets* blanked, so line numbers are kept."""
    lines = text.split("\n")
    for columns in column_sets:
        wanted = [c.lower() for c in columns]
        for i, line in enumerate(lines):
            header = [c.strip().lower() for c in line.strip().strip("|").split("|")]
            if line.startswith("|") and all(c in header for c in wanted):
                j = i + 2
                while j < len(lines) and lines[j].startswith("|"):
                    lines[j] = ""
                    j += 1
                break
    return "\n".join(lines)


def citable_docs(docs, entry):
    """*docs* as the never-shipped citation rule reads them: the upgrade
    guide's exclusion and checklist tables name what never arrives, true in
    every generated project, so their rows are left out; its prose is read
    like any other document's."""
    return [
        (
            p,
            _without_tables(t, (_EXCLUSION_TABLE, _CHECKLIST_TABLE))
            if _untwinned(p) == entry["upgrade_guide"]
            else t,
        )
        for p, t in docs
    ]


def excluded_citation_findings(docs, excluded):
    """A shipped doc that names a never-shipped document, by link or by path,
    dangles in every generated project."""
    known = set(excluded)
    findings = []
    for relpath, text in docs:
        findings.extend(
            "%s: cites %s, which copier.yml `_exclude`s, so the citation "
            "dangles in every generated project" % (relpath, target)
            for target in sorted(
                cs._document_references(_untwinned(relpath), text, known)
            )
        )
    return findings


# --- rule (b): a newcomer reaches every guide, and the tree is true --------


def one_hop_findings(one_hop, texts, known):
    """*one_hop*: {entry doc: [targets]}; *texts*: {relpath: text} for every
    Markdown file; *known*: every Markdown path. An entry doc that is absent,
    a target that does not exist, or a target the doc does not name by link or
    path, is one finding each."""
    findings = []
    for doc, targets in sorted(one_hop.items()):
        if doc not in texts:
            findings.append("%s: the entry document does not exist" % doc)
            continue
        if not targets:
            findings.append("%s: names no one-hop target -- zero items" % doc)
        reached = cs._document_references(doc, texts[doc], known)
        for target in targets:
            if target not in known:
                findings.append("%s: one-hop target %s does not exist" % (doc, target))
            elif target not in reached:
                findings.append(
                    "%s: does not link to %s, so a newcomer cannot reach it in one "
                    "hop" % (doc, target)
                )
    return findings


def roster_reach_findings(roster, texts, known):
    """Every Markdown document beside *roster* (its directory's members) must be
    named from it, so the README's hop to the roster reaches each guide."""
    if roster not in texts:
        return ["%s: the roster does not exist" % roster]
    base = posixpath.dirname(roster)
    members = sorted(p for p in known if posixpath.dirname(p) == base and p != roster)
    if not members:
        return ["%s: its directory holds no other document -- zero items" % roster]
    reached = cs._document_references(roster, texts[roster], known)
    return [
        "%s: does not name %s, so no entry document reaches it" % (roster, m)
        for m in members
        if m not in reached
    ]


def layout_tree(text, heading):
    """The directory names in the first fenced block under `## <heading>`, or
    None when there is no such heading or no fence under it."""
    lines = text.split("\n")
    target = "## " + heading
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == target)
    except StopIteration:
        return None
    names, fenced = [], False
    for line in lines[start + 1 :]:
        if line.startswith("```"):
            if fenced:
                return names
            fenced = True
            continue
        if not fenced and line.startswith("## "):
            return None
        if fenced:
            m = _TREE_DIR.match(line)
            if m:
                names.append(m.group(1))
    return names if fenced else None


def shipping_toplevel_dirs(root, manifest):
    """The top-level directories a reader of this tree meets: every taxonomy
    directory present, every `structure.extra_toplevel` name, and every
    top-level dot-directory git tracks (without a git work tree: every one
    present outside IGNORE_DIRS). An untracked dot-directory, such as an
    editor's settings, is local state and ships nowhere."""
    root = Path(root)
    extra = (manifest.get("structure") or {}).get("extra_toplevel")
    if not isinstance(extra, list):
        raise DocDriftConfigError(
            "config/project.json: `structure.extra_toplevel` is missing or not a list"
        )
    expected = {d for d in cs.TAXONOMY if (root / d).is_dir()} | set(extra)
    listed = _git_listed(root, untracked=False)
    if listed is None:
        dots = {
            p.name
            for p in root.iterdir()
            if p.name.startswith(".") and p.is_dir() and p.name not in cs.IGNORE_DIRS
        }
    else:
        dots = {p.split("/", 1)[0] for p in listed if p.startswith(".") and "/" in p}
    return expected | dots


def layout_findings(doc, text, heading, expected, root):
    """The layout tree under `## <heading>` in *doc* lists every *expected*
    directory, and every directory it lists exists under *root*."""
    listed = layout_tree(text, heading)
    if listed is None:
        return ["%s: no fenced tree under `## %s`" % (doc, heading)]
    if not listed:
        return ["%s: the tree under `## %s` lists no directory" % (doc, heading)]
    if not expected:
        return ["no shipping top-level directory derived -- zero items"]
    findings = [
        "%s: the layout tree omits %s/, which ships at the top level" % (doc, d)
        for d in sorted(set(expected) - set(listed))
    ]
    findings.extend(
        "%s: the layout tree lists %s/, which does not exist" % (doc, d)
        for d in listed
        if not (Path(root) / d).is_dir()
    )
    return findings


def audience_findings(roster, text, audiences):
    """The roster's `## What ships here` table carries an Audience column, and
    each row's cell is a non-empty comma-joined subset of *audiences*, in
    their order."""
    table = cs._roster_table(text)
    if not table or not table[0]:
        return ["%s: no `## What ships here` table" % roster]
    header, rows = table
    if "audience" not in header:
        return ["%s: the roster has no Audience column" % roster]
    col = header.index("audience")
    if not rows:
        return ["%s: the roster has no rows -- zero items" % roster]
    findings = []
    for row in rows:
        member = row[0] if row else "?"
        cell = row[col] if col < len(row) else ""
        names = [a.strip() for a in cell.split(",")] if cell.strip() else []
        order = [audiences.index(a) for a in names if a in audiences]
        if not names:
            findings.append("%s: %s names no audience" % (roster, member))
        elif len(order) != len(names) or order != sorted(set(order)):
            findings.append(
                "%s: %s names %r -- each audience must be one of %s, listed once "
                "and in that order" % (roster, member, cell, ", ".join(audiences))
            )
    return findings


# --- rule (c): the limits guide names every waiver and every exit code ------


def derived_waivers(root):
    """Every way this tree lets a project switch a rule off, read from the
    code and registry that grant it: a pragma a checker compiles at module
    level, a gate-runner policy key, the mypy kill switch, a dict-valued
    ruleset key in config/practices.json, a practice status that is not the
    active one, every key of the child-process allowlist's block, and the
    history prefixes this gate exempts."""
    root = Path(root)
    found = set()
    checkers = sorted(root.glob(_CHECKER_GLOB))
    if not checkers:
        raise DocDriftConfigError("no %s found -- zero items" % _CHECKER_GLOB)
    for path in checkers:
        source = path.read_text(encoding="utf-8")
        for node in ast.parse(source).body:
            if (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Attribute)
                and node.value.func.attr == "compile"
            ):
                found.update(
                    _PRAGMA.findall(ast.get_source_segment(source, node) or "")
                )
    found.update(cs._POLICY_KEYS)
    found.add(cs._OVERRIDE_KILL_SWITCH)
    found.update(child_env_keys(root))
    found.add("%s.%s" % (_BLOCK, _HISTORY_KEY))
    registry_path = root / "config" / "practices.json"
    if not registry_path.is_file():
        raise DocDriftConfigError("config/practices.json is missing")
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    rulesets = registry.get("rulesets")
    practices = registry.get("practices")
    if not isinstance(rulesets, dict) or not isinstance(practices, list):
        raise DocDriftConfigError(
            "config/practices.json: `rulesets` or `practices` is missing or mistyped"
        )
    for tool, rules in sorted(rulesets.items()):
        if not isinstance(rules, dict):
            continue  # `_comment`: a string, not a tool
        found.update(
            "rulesets.%s.%s" % (tool, key)
            for key, value in rules.items()
            if isinstance(value, dict)
        )
    found.update(
        p["status"]
        for p in practices
        if isinstance(p, dict)
        and isinstance(p.get("status"), str)
        and not p["status"].startswith(_ACTIVE_STATUS)
    )
    return sorted(found)


def child_env_keys(root):
    """`<block>.<key>` for every key the child-process allowlist reads, from
    the module's own `_BLOCK` and `_BLOCK_KEYS` literals. A module without
    them is a finding, never an empty set."""
    path = Path(root) / _CHILD_ENV
    if not path.is_file():
        raise DocDriftConfigError("%s is missing" % _CHILD_ENV)
    values = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id in _CHILD_ENV_NAMES:
                values[target.id] = ast.literal_eval(node.value)
    block, keys = (values.get(n) for n in _CHILD_ENV_NAMES)
    if not isinstance(block, str) or not isinstance(keys, tuple) or not keys:
        raise DocDriftConfigError(
            "%s: no %s literal -- zero items"
            % (_CHILD_ENV, " or ".join(_CHILD_ENV_NAMES))
        )
    return sorted("%s.%s" % (block, k) for k in keys if not k.startswith("_"))


def _backticked(text):
    """Every inline-code span outside fenced code, whole and split on
    whitespace, so `rm -rf src/frontend` names `src/frontend`."""
    spans = set()
    for line in cs._unfenced_lines(text):
        for span in cs._BACKTICKED.findall(line):
            spans.add(span.strip())
            spans.update(span.split())
    return spans


def waiver_findings(guide, text, waivers):
    if not waivers:
        return ["no waiver derived -- zero items"]
    named = _backticked(text)
    return [
        "%s: does not name the waiver `%s`" % (guide, w)
        for w in waivers
        if w not in named
    ]


def _int_constants(node):
    """The int literals *node* can evaluate to: a literal, or either branch
    of a conditional expression. Anything else yields none."""
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return {node.value}
    if isinstance(node, ast.IfExp):
        return _int_constants(node.body) | _int_constants(node.orelse)
    return set()


def _own_nodes(func):
    """Every node of *func*'s body, not descending into a nested function."""
    stack = list(func.body)
    while stack:
        node = stack.pop()
        yield node
        stack.extend(
            child
            for child in ast.iter_child_nodes(node)
            if not isinstance(
                child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
            )
        )


def _is_exit(func):
    return (isinstance(func, ast.Name) and func.id == "SystemExit") or (
        isinstance(func, ast.Attribute) and func.attr == "exit"
    )


def exit_codes(path):
    """(codes, passes_through) for the script at *path*: the int literals its
    `main` returns (through a name, the literals assigned to that name in
    `main`) and every int literal handed to `sys.exit`, `SystemExit` or an
    argparse `.exit`. A `main` that returns a call's or an attribute's value
    passes a child's code through."""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    codes, passes = set(), False
    main = next(
        (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main"),
        None,
    )
    if main is not None:
        assigned = {}
        nodes = list(_own_nodes(main))
        for node in nodes:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        assigned.setdefault(target.id, set()).update(
                            _int_constants(node.value)
                        )
        for node in nodes:
            if not isinstance(node, ast.Return) or node.value is None:
                continue
            if isinstance(node.value, ast.Name):
                codes |= assigned.get(node.value.id, set())
            elif isinstance(node.value, (ast.Call, ast.Attribute)):
                passes = True
            else:
                codes |= _int_constants(node.value)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_exit(node.func) and node.args:
            codes |= _int_constants(node.args[0])
    return codes, passes


def gate_scripts(root, target):
    """Every `*.py` a recipe reachable from make *target* runs. A makefile
    this gate cannot read fully is a finding, never a smaller set."""
    warns = []
    makefiles = cs.walk_makefiles(str(root), warns.append)
    if warns:
        raise DocDriftConfigError("; ".join(warns))
    if not makefiles:
        raise DocDriftConfigError("no Makefile -- zero items")
    rules = cs._make_rules("\n".join(text for _path, text in makefiles))
    if target not in rules:
        raise DocDriftConfigError("the Makefile has no `%s` target" % target)
    return sorted(cs._scripts_reachable_from(rules, target))


def _code_cell_findings(guide, cell, script, codes, passes):
    missing = [
        str(c) for c in sorted(codes) if not re.search(r"(?<!\d)%d(?!\d)" % c, cell)
    ]
    findings = []
    if missing:
        findings.append(
            "%s: the row for `%s` omits exit code(s) %s"
            % (guide, script, ", ".join(missing))
        )
    if passes and _PASSES_THROUGH not in cell.lower():
        findings.append(
            "%s: the row for `%s` does not say it %s a child's code"
            % (guide, script, _PASSES_THROUGH)
        )
    return findings


def _rows_naming(table, column, item):
    header, rows = table
    col = header.index(column.lower())
    return [
        row
        for row in rows
        if col < len(row)
        and item in {s.strip() for s in cs._BACKTICKED.findall(row[col])}
    ]


def exit_code_findings(guide, text, root, scripts):
    """Each gate script has a row in the guide's Script/Exit table whose Exit
    cell names every code the script can exit with."""
    if not scripts:
        return ["no gate script derived -- zero items"]
    table = cs._pipe_table(text, _EXIT_TABLE)
    if table is None:
        return ["%s: no table with the columns %s" % (guide, ", ".join(_EXIT_TABLE))]
    exit_col = table[0].index("exit")
    findings = []
    for script in scripts:
        path = Path(root) / script
        if not path.is_file():
            findings.append(
                "%s: the gate runs %s, which does not exist" % (guide, script)
            )
            continue
        codes, passes = exit_codes(path)
        if not codes and not passes:
            findings.append("%s: no exit code derived -- zero items" % script)
            continue
        rows = _rows_naming(table, "Script", script)
        if not rows:
            findings.append("%s: no exit-code row names `%s`" % (guide, script))
        for row in rows:
            cell = row[exit_col] if exit_col < len(row) else ""
            findings.extend(_code_cell_findings(guide, cell, script, codes, passes))
    return findings


# --- rule (d): the upgrade guide names what copier does to a project --------


def _command_items(command):
    """(scripts, removed paths) one `_tasks`/`_migrations` command names: a
    list command runs its `.py`; a string command is `rm` over the paths after
    its flags (yaml folds a multi-line string, so whitespace splits it)."""
    if isinstance(command, dict):
        command = command.get("command")
    if isinstance(command, list):
        scripts = [c for c in command if isinstance(c, str) and c.endswith(".py")]
        if scripts:
            return scripts, []
    if isinstance(command, str):
        words = command.split()
        if words and words[0] == "rm":
            return [], [w for w in words[1:] if not w.startswith("-")]
    raise DocDriftConfigError(
        "copier.yml: a task or migration this gate cannot read: %r" % (command,)
    )


def copier_inventory(root):
    """{"scripts", "checklist", "steps", "exclusions", "min_copier_version"}
    read from copier.yml, or None when *root* is not the template: the
    scripts the tasks and migrations run, those plus every path a migration
    removes, every task then every migration as (kind, items) in the order
    copier runs them, every `_exclude` entry with its jinja stripped, and the
    copier version floor."""
    copier_yml = Path(root) / "copier.yml"
    if not copier_yml.is_file():
        return None
    yaml = optional_deps.importorskip("yaml", extra="template")
    cfg = yaml.safe_load(copier_yml.read_text(encoding="utf-8"))
    if not isinstance(cfg, dict):
        raise DocDriftConfigError("copier.yml: top level is not a mapping")
    scripts, removed, steps = [], [], []
    # Every migration here is an `after` one, and copier runs `_tasks` while
    # it renders, before them: so tasks first, then migrations in file order.
    for key, kind in (("_tasks", "task"), ("_migrations", "migration")):
        entries = cfg.get(key)
        if not isinstance(entries, list) or not entries:
            raise DocDriftConfigError("copier.yml: `%s` is missing or empty" % key)
        for entry in entries:
            ran, gone = _command_items(entry)
            scripts.extend(ran)
            removed.extend(gone)
            steps.append((kind, tuple(ran + gone)))
    excludes = cfg.get("_exclude")
    if not isinstance(excludes, list) or not excludes:
        raise DocDriftConfigError("copier.yml: `_exclude` is missing or empty")
    exclusions = [_JINJA_TAG.sub("", e).strip() for e in excludes if isinstance(e, str)]
    floor = cfg.get("_min_copier_version")
    if not isinstance(floor, str) or not floor.strip():
        raise DocDriftConfigError("copier.yml: `_min_copier_version` is missing")
    return {
        "scripts": scripts,
        "checklist": scripts + removed,
        "steps": steps,
        "exclusions": [e for e in exclusions if e],
        "min_copier_version": floor.strip(),
    }


def _span_names(cell):
    """Every inline-code span in *cell*, whole and split on whitespace."""
    named = set()
    for span in cs._BACKTICKED.findall(cell):
        named.add(span.strip())
        named.update(span.split())
    return named


def checklist_findings(guide, table, root, inventory):
    """Each task and each migration has a row of its own kind (a task row's
    Step cell opens with `task:`) whose Step cell names every item it runs or
    removes, the rows follow copier's order, and a script's row carries its
    exit codes. A row stands for one entry only, so a script that is both a
    task and a migration needs two rows."""
    header, rows = table
    step_col = header.index(_CHECKLIST_TABLE[0].lower())
    exit_col = header.index("exit")
    parsed = [
        (
            _TASK_MARK if row[step_col].lower().startswith(_TASK_MARK) else "",
            _span_names(row[step_col]),
            row,
        )
        for row in rows
        if step_col < len(row)
    ]
    findings, used, previous = [], set(), -1
    for kind, items in inventory["steps"]:
        mark = _TASK_MARK if kind == "task" else ""
        match = next(
            (
                i
                for i, (m, named, _row) in enumerate(parsed)
                if i not in used and m == mark and set(items) <= named
            ),
            None,
        )
        label = " ".join("`%s`" % i for i in items)
        if match is None:
            findings.append("%s: no %s row names %s" % (guide, kind, label))
            continue
        used.add(match)
        # Against the step copier runs just before, not every earlier one, so
        # one misplaced row is one finding.
        if match < previous:
            findings.append(
                "%s: the %s row for %s is out of copier's order -- it sits above "
                "the row of the step copier runs just before it" % (guide, kind, label)
            )
        previous = match
        row = parsed[match][2]
        cell = row[exit_col] if exit_col < len(row) else ""
        for item in items:
            if item not in inventory["scripts"]:
                continue
            codes, passes = exit_codes(Path(root) / item)
            if not codes and not passes:
                findings.append("%s: no exit code derived -- zero items" % item)
            findings.extend(_code_cell_findings(guide, cell, item, codes, passes))
    return findings


def upgrade_findings(guide, text, root, inventory):
    """Every task and migration has its own row, in copier's order, in the
    guide's checklist table (see checklist_findings); every `_exclude` entry
    has a row in its exclusion table; the guide states the copier version
    floor."""
    findings = []
    floor = inventory["min_copier_version"]
    if not re.search(r"(?<![\d.])%s(?![\d.])" % re.escape(floor), text):
        findings.append(
            "%s: does not state the copier version floor %s that copier.yml "
            "`_min_copier_version` sets" % (guide, floor)
        )
    for columns, items, kind in (
        (_CHECKLIST_TABLE, inventory["checklist"], "task or migration"),
        (_EXCLUSION_TABLE, inventory["exclusions"], "exclusion"),
    ):
        if not items:
            findings.append("copier.yml: no %s derived -- zero items" % kind)
            continue
        table = cs._pipe_table(text, columns)
        if table is None:
            findings.append(
                "%s: no table with the columns %s" % (guide, ", ".join(columns))
            )
            continue
        if columns is _CHECKLIST_TABLE:
            findings.extend(checklist_findings(guide, table, root, inventory))
            continue
        named = set()
        for row in table[1]:
            for cell in row:
                named |= _span_names(cell)
        findings.extend(
            "%s: no %s row names `%s`" % (guide, kind, item)
            for item in sorted(set(items))
            if item not in named
        )
    return findings


# --- fixtures -------------------------------------------------------------


@pytest.fixture(scope="module")
def manifest():
    return load_manifest(_ROOT)


@pytest.fixture(scope="module")
def policy(manifest):
    return drift_policy(manifest)


@pytest.fixture(scope="module")
def entry(manifest):
    return entry_policy(manifest)


@pytest.fixture(scope="module")
def markdown():
    """{relpath: text} for every Markdown file, history included: an entry
    document may link into docs/adr/."""
    found = dict(cs._markdown_texts(str(_ROOT)))
    assert found, "no Markdown file found -- a scan over zero docs"
    return found


@pytest.fixture(scope="module")
def docs(policy):
    found = shipped_docs(_ROOT, policy["history_paths"])
    assert found, "no shipped Markdown document found -- a scan over zero docs"
    return found


# --- rule (a): no moment, no host ------------------------------------------


def test_no_shipped_doc_cites_a_work_id_or_a_host_specific_string(
    manifest, policy, docs
):
    findings = moment_and_host_findings(docs, policy, work_mention(manifest), _ROOT)
    assert not findings, "\n".join(findings)


@pytest.mark.parametrize(
    "planted, exempt",
    [
        ("Delivered by CMP-1.S1 last week.", "Delivered by `CMP-1.S1` last week."),
        ("This works on this host only.", "```\nThis works on this host only.\n```"),
        # A port is read in raw text, so a fence does not exempt it; a
        # non-Markdown file that declares it does.
        ("Open http://127.0.0.1:59999 to see it.", None),
    ],
    ids=["work-id", "host-phrase", "undeclared-port"],
)
def test_a_planted_work_id_host_phrase_or_undeclared_port_reds_the_scan(
    tmp_path, manifest, policy, docs, planted, exempt
):
    mention = work_mention(manifest)
    source = dict(docs)["CONTRIBUTING.md"]
    doc = tmp_path / "CONTRIBUTING.md"

    def scan(text):
        # The copy is judged on its own tree: tmp_path holds no git work tree
        # and no non-Markdown file, so the port lookup walks it and finds none.
        doc.write_text(text, encoding="utf-8")
        found = shipped_docs(tmp_path, policy["history_paths"])
        return moment_and_host_findings(found, policy, mention, tmp_path)

    assert scan(source) == [], "the unplanted copy must be clean"
    findings = scan(source + "\n" + planted + "\n")
    assert len(findings) == 1, findings
    assert findings[0].startswith("CONTRIBUTING.md:"), findings
    if exempt is not None:
        assert scan(source + "\n" + exempt + "\n") == []
    else:
        port = _LOOPBACK_PORT.search(planted).group(1)
        (tmp_path / "serve.py").write_text("PORT = %s\n" % port, encoding="utf-8")
        assert scan(source + "\n" + planted + "\n") == []


def test_no_shipped_doc_cites_a_document_the_template_never_ships(policy, entry, docs):
    excluded = never_shipped_docs(_ROOT)
    if excluded is None:
        pytest.skip(_TEMPLATE_ONLY)
    assert excluded, "copier.yml `_exclude` names no unconditional .md -- zero items"
    # The upgrade guide's inventory tables name what never arrives, as rule
    # (d) demands; citable_docs leaves those rows out and reads its prose.
    assert any(_untwinned(p) == entry["upgrade_guide"] for p, _t in docs), (
        "the upgrade guide is not a shipped doc"
    )
    findings = excluded_citation_findings(citable_docs(docs, entry), excluded)
    assert not findings, "\n".join(findings)


def test_a_planted_citation_of_a_never_shipped_document_reds_the_scan(
    tmp_path, policy, docs
):
    excluded = never_shipped_docs(_ROOT)
    if excluded is None:
        pytest.skip(_TEMPLATE_ONLY)
    assert excluded
    doc = tmp_path / "CONTRIBUTING.md"
    doc.write_text(
        dict(docs)["CONTRIBUTING.md"] + "\nSee `%s` for why.\n" % excluded[0],
        encoding="utf-8",
    )
    findings = excluded_citation_findings(
        shipped_docs(tmp_path, policy["history_paths"]), excluded
    )
    assert len(findings) == 1 and excluded[0] in findings[0], findings


def test_a_missing_or_malformed_doc_drift_block_fails_closed(manifest):
    broken = dict(manifest)
    broken.pop(_BLOCK, None)
    with pytest.raises(DocDriftConfigError, match="doc_drift"):
        drift_policy(broken)
    bad = dict(manifest, doc_drift={"history_paths": [], "forbidden_phrases": {}})
    with pytest.raises(DocDriftConfigError, match="history_paths"):
        drift_policy(bad)
    for key in ("one_hop", "audiences", "limits_guide", "gate_target"):
        missing = dict(manifest, doc_drift=dict(manifest.get(_BLOCK) or {}))
        missing[_BLOCK].pop(key, None)
        with pytest.raises(DocDriftConfigError, match=key):
            entry_policy(missing)
    no_naming = dict(manifest)
    no_naming.pop("work_naming", None)
    with pytest.raises(DocDriftConfigError, match="work_naming"):
        work_mention(no_naming)


# --- rule (b): entry documents, the layout tree, guide audiences -----------


def test_the_entry_docs_reach_their_one_hop_targets(entry, markdown):
    known = set(markdown)
    findings = one_hop_findings(entry["one_hop"], markdown, known)
    findings += roster_reach_findings(entry["roster"], markdown, known)
    assert not findings, "\n".join(findings)


def test_the_readme_layout_tree_lists_every_shipping_top_level_directory(
    manifest, entry, markdown
):
    expected = shipping_toplevel_dirs(_ROOT, manifest)
    assert expected, "no shipping top-level directory derived -- zero items"
    findings = layout_findings(
        "README.md", markdown["README.md"], entry["layout_heading"], expected, _ROOT
    )
    assert not findings, "\n".join(findings)


def test_every_guide_roster_row_names_its_audience(entry, markdown):
    roster = entry["roster"]
    assert roster in markdown, "%s does not exist" % roster
    findings = audience_findings(roster, markdown[roster], entry["audiences"])
    assert not findings, "\n".join(findings)


def _blank_first_audience(text):
    """*text* with the first roster row's Audience cell emptied, and that
    row's member."""
    header, rows = cs._roster_table(text)
    col = header.index("audience")
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("| " + rows[0][0] + " |"):
            cells = line.split("|")
            cells[col + 1] = " "
            lines[i] = "|".join(cells)
            return "\n".join(lines), rows[0][0]
    raise AssertionError("the first roster row was not found")


@pytest.mark.parametrize("fault", ["hop", "tree", "audience"])
def test_dropping_a_hop_a_tree_entry_or_an_audience_reds_the_entry_checks(
    manifest, entry, markdown, fault
):
    known = set(markdown)
    texts = dict(markdown)
    readme, roster = "README.md", entry["roster"]
    expected = shipping_toplevel_dirs(_ROOT, manifest)

    def judge(t):
        if fault == "hop":
            return one_hop_findings(entry["one_hop"], t, known)
        if fault == "tree":
            return layout_findings(
                readme, t[readme], entry["layout_heading"], expected, _ROOT
            )
        return audience_findings(roster, t[roster], entry["audiences"])

    assert judge(texts) == [], "the unplanted tree must be clean"
    if fault == "hop":
        target = "CONTRIBUTING.md"
        assert target in entry["one_hop"][readme]
        texts[readme] = texts[readme].replace(target, "CONTRIBUTING")
    elif fault == "tree":
        target = "runtimes/"
        kept = [
            ln
            for ln in texts[readme].split("\n")
            if not re.match(r"^[├└]── runtimes/", ln)
        ]
        assert len(kept) == texts[readme].count("\n"), "no single runtimes/ line"
        texts[readme] = "\n".join(kept)
    else:
        texts[roster], target = _blank_first_audience(texts[roster])
    findings = judge(texts)
    assert len(findings) == 1, findings
    assert target in findings[0], findings


# --- rule (c): the limits guide ------------------------------------------------


def test_the_limits_guide_names_every_waiver(entry, markdown):
    guide = entry["limits_guide"]
    assert guide in markdown, "%s does not exist" % guide
    waivers = derived_waivers(_ROOT)
    assert waivers, "no waiver derived -- zero items"
    findings = waiver_findings(guide, markdown[guide], waivers)
    assert not findings, "\n".join(findings)


def test_the_limits_guide_names_every_gate_exit_code(entry, markdown):
    guide = entry["limits_guide"]
    assert guide in markdown, "%s does not exist" % guide
    scripts = gate_scripts(_ROOT, entry["gate_target"])
    assert scripts, "make %s runs no script -- zero items" % entry["gate_target"]
    findings = exit_code_findings(guide, markdown[guide], _ROOT, scripts)
    assert not findings, "\n".join(findings)


@pytest.mark.parametrize(
    "fault",
    [
        "generic-ok",
        "child_env.credentialed_values",
        "doc_drift.history_paths",
        "exit-code",
    ],
)
def test_removing_a_waiver_or_an_exit_code_from_the_limits_guide_reds_it(
    entry, markdown, fault
):
    # The three waivers come from three sources derived_waivers reads: a
    # checker's pragma, the child-process allowlist's keys, and this gate's
    # own history exemption.
    guide = entry["limits_guide"]
    text = markdown[guide]
    if fault != "exit-code":
        waivers = derived_waivers(_ROOT)
        assert fault in waivers, waivers

        def judge(t):
            return waiver_findings(guide, t, waivers)

        planted = text.replace("`%s`" % fault, fault)
        target = fault
    else:
        scripts = gate_scripts(_ROOT, entry["gate_target"])
        target = "scripts/check_structure.py"
        assert target in scripts

        def judge(t):
            return exit_code_findings(guide, t, _ROOT, scripts)

        lines = text.split("\n")
        rows = [i for i, ln in enumerate(lines) if ln.startswith("| `%s` |" % target)]
        assert len(rows) == 1, rows
        cells = lines[rows[0]].split("|")
        cells[2] = re.sub(r",?\s*\b2\b", "", cells[2])
        lines[rows[0]] = "|".join(cells)
        planted = "\n".join(lines)
    assert judge(text) == [], "the unplanted guide must be clean"
    assert planted != text
    findings = judge(planted)
    assert len(findings) == 1, findings
    assert target in findings[0], findings


# --- rule (d): the upgrade guide (template only) ----------------------------------


def test_the_upgrade_guide_names_every_copier_migration_task_and_exclusion(
    entry, markdown
):
    inventory = copier_inventory(_ROOT)
    if inventory is None:
        pytest.skip(_TEMPLATE_ONLY)
    guide = entry["upgrade_guide"]
    assert guide in markdown, "%s does not exist" % guide
    findings = upgrade_findings(guide, markdown[guide], _ROOT, inventory)
    assert not findings, "\n".join(findings)


@pytest.mark.parametrize(
    "target", ["docs/design/keel-hardening-plan.md", "wiki/.runtime"]
)
def test_removing_a_migration_or_an_exclusion_from_the_upgrade_guide_reds_it(
    entry, markdown, target
):
    inventory = copier_inventory(_ROOT)
    if inventory is None:
        pytest.skip(_TEMPLATE_ONLY)
    guide = entry["upgrade_guide"]
    text = markdown[guide]
    assert upgrade_findings(guide, text, _ROOT, inventory) == []
    lines = text.split("\n")
    # The row that names *target* in the table rule (d) reads it from: the
    # checklist for a removed path, the exclusion table for an `_exclude`.
    is_step = target in inventory["checklist"]
    columns = _CHECKLIST_TABLE if is_step else _EXCLUSION_TABLE
    header, _rows = cs._pipe_table(text, columns)
    start = next(
        i
        for i, ln in enumerate(lines)
        if ln.startswith("|")
        and [c.strip().lower() for c in ln.strip().strip("|").split("|")] == header
    )
    end = next(
        (i for i in range(start, len(lines)) if not lines[i].startswith("|")),
        len(lines),
    )
    hits = [i for i in range(start + 2, end) if target in _backticked(lines[i])]
    assert len(hits) == 1, hits
    del lines[hits[0]]
    findings = upgrade_findings(guide, "\n".join(lines), _ROOT, inventory)
    assert len(findings) == 1, findings
    assert target in findings[0], findings


def _table_line_numbers(lines, columns):
    """The line indexes of the body rows of the first pipe table whose header
    carries every one of *columns*."""
    wanted = [c.lower() for c in columns]
    for i, ln in enumerate(lines):
        header = [c.strip().lower() for c in ln.strip().strip("|").split("|")]
        if ln.startswith("|") and all(c in header for c in wanted):
            end = next(
                (j for j in range(i + 2, len(lines)) if not lines[j].startswith("|")),
                len(lines),
            )
            return list(range(i + 2, end))
    raise AssertionError("no table with the columns %s" % ", ".join(columns))


@pytest.mark.parametrize(
    "fault", ["drop-task-row", "drop-last-migration-row", "swap-two-rows"]
)
def test_each_task_and_migration_has_its_own_row_in_the_order_copier_runs_it(
    entry, markdown, fault
):
    # restamp_docs.py is both the `_tasks` entry and the last `_migrations`
    # entry: one row must not stand in for the other, and the rows must keep
    # copier's order (the task while it renders, then each after-migration in
    # copier.yml's order).
    inventory = copier_inventory(_ROOT)
    if inventory is None:
        pytest.skip(_TEMPLATE_ONLY)
    guide = entry["upgrade_guide"]
    text = markdown[guide]
    assert upgrade_findings(guide, text, _ROOT, inventory) == []
    lines = text.split("\n")
    body = _table_line_numbers(lines, _CHECKLIST_TABLE)
    if fault == "drop-task-row":
        hits = [i for i in body if lines[i].startswith("| task:")]
        assert len(hits) == 1, hits
        target = "restamp_docs.py"
        del lines[hits[0]]
    elif fault == "drop-last-migration-row":
        target = "restamp_docs.py"
        assert target in lines[body[-1]]
        del lines[body[-1]]
    else:
        first, second = body[-2], body[-1]
        target = "restamp_docs.py"
        assert "resolve_stamp_conflicts.py" in lines[first]
        assert target in lines[second]
        lines[first], lines[second] = lines[second], lines[first]
    findings = upgrade_findings(guide, "\n".join(lines), _ROOT, inventory)
    assert len(findings) == 1, findings
    assert target in findings[0], findings


def test_removing_the_copier_version_floor_from_the_upgrade_guide_reds_it(
    entry, markdown
):
    inventory = copier_inventory(_ROOT)
    if inventory is None:
        pytest.skip(_TEMPLATE_ONLY)
    guide = entry["upgrade_guide"]
    text = markdown[guide]
    floor = inventory["min_copier_version"]
    assert upgrade_findings(guide, text, _ROOT, inventory) == []
    planted = text.replace(floor, "the floor")
    assert planted != text
    findings = upgrade_findings(guide, planted, _ROOT, inventory)
    assert len(findings) == 1 and floor in findings[0], findings


def test_a_planted_prose_citation_in_the_upgrade_guide_reds_the_scan(
    tmp_path, policy, entry, docs
):
    # The upgrade guide's inventory tables may name a never-shipped document;
    # its prose may not, because there the citation dangles downstream.
    excluded = never_shipped_docs(_ROOT)
    if excluded is None:
        pytest.skip(_TEMPLATE_ONLY)
    assert excluded
    guide = entry["upgrade_guide"]
    source = dict(docs)[guide]
    assert (
        excluded_citation_findings(citable_docs([(guide, source)], entry), excluded)
        == []
    )
    planted = source + "\nSee `%s` for why.\n" % excluded[0]
    findings = excluded_citation_findings(
        citable_docs([(guide, planted)], entry), excluded
    )
    assert len(findings) == 1 and excluded[0] in findings[0], findings


def test_an_untracked_dot_directory_is_not_a_shipping_directory(tmp_path, manifest):
    # An editor's settings directory that git does not track ships nowhere;
    # only a dot-directory git tracks is part of the layout.
    if shutil.which("git") is None:
        pytest.skip("git is not installed -- the tracked set cannot be read")
    env = build_child_env()
    for args in (("init", "-q"),):
        subprocess.run(
            review_docs.git_argv(str(tmp_path), *args),
            cwd=str(tmp_path),
            env=env,
            check=True,
        )
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "w.yml").write_text("x\n", encoding="utf-8")
    (tmp_path / ".editor").mkdir()
    (tmp_path / ".editor" / "settings.json").write_text("{}\n", encoding="utf-8")
    subprocess.run(
        review_docs.git_argv(str(tmp_path), "add", ".github"),
        cwd=str(tmp_path),
        env=env,
        check=True,
    )
    found = shipping_toplevel_dirs(tmp_path, {"structure": {"extra_toplevel": []}})
    assert ".github" in found, found
    assert ".editor" not in found, found
