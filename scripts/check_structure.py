#!/usr/bin/env python3
"""
check_structure.py - enforce the project conventions (see CONVENTIONS.md).

Checks:
  A. Frontmatter validity on README.md / AGENT.md / CLAUDE.md, docs/**,
     test-docs/** *.md, and agents/**/*.tool.md
  B. Each taxonomy directory that exists has README.md + CLAUDE.md
  C. Each src/ directory containing *.py is a package: __init__.py with __all__
  D. The __init__ boundary: no absolute import of another package's _private module
  E. Authored coverage (WARN): every __all__-exported symbol has a docstring
  F. Tool specs governed (ERR) + accountability (WARN): tool/agent docs are owned
  G. Tool<->agent binding (ERR): tools.md <-> '## Used by' agree; tool_command invokes public_api
  H. Project facts in config/project.json agree with the tree (ERR); an
     undeclared leftover stack/transport dir WARNs (CONVENTIONS section 15).
     An optional 'runtimes' block is validated the same way (section 16)
  I. Agent-rules symlink (ERR): every CLAUDE.md is a symlink to its sibling
     AGENT.md, and every AGENT.md has that sibling (CONVENTIONS section 5)
  J. No third-party exception leaks across a library boundary (ERR): a raise of
     an exception TYPE imported from a foreign (non-local, non-stdlib) module
     (coding-practices; owned-exception-boundary in config/practices.json)

Exit 0 = clean, 1 = errors. Warnings never fail the build. Stdlib only; 3.6+.
"""
import ast
import io
import json
import os
import re
import sys
import tokenize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

IGNORE_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build",
    ".astro", ".mypy_cache", ".pytest_cache", ".ruff_cache",
}

KINDS = {
    "readme", "rules", "package", "module", "tests", "test-doc", "doc", "spec",
    "design", "adr", "config", "script", "agent", "mcp", "api", "wiki", "demo",
    "model", "eval", "container", "ops",
    "tool",                      # agents/tools/*.tool.md adapters
}
TOOL_EFFECTS = {"read-only", "writes", "model-call"}
LAYERS = {"frontend", "backend", "shared", "app", "cross-cutting", "n/a"}
STATUSES = {
    "draft", "stable", "deprecated", "template",   # general lifecycle
    "proposed", "accepted", "superseded",          # ADR lifecycle
}
VISIBILITIES = {"public", "internal", "confidential", "restricted"}
REQUIRED_KEYS = ("title", "kind", "layer", "status", "summary",
                 "id", "created", "updated", "visibility", "canonical")

TAXONOMY = [
    "src", "tests", "test-docs", "docs", "agents", "mcp", "api", "wiki",
    "scripts", "config", "demo", "containers", "evals", "ops", "models",
    "runtimes",
]
REQUIRED_TOPLEVEL = ["src", "tests", "docs"]
CODE_ROOTS = ["src", "tests", "api", "models", "mcp", "agents", "demo",
              "scripts", "runtimes"]

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


def parse_frontmatter(path):
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except Exception as e:
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
    if can and can not in ("true", "false", "self"):
        if ("/" in can or can.endswith(".md")) and \
                not os.path.exists(os.path.join(ROOT, can)):
            err("%s: canonical target '%s' does not exist" % (rel(path), can))
    # Corpus: deprecated content must point at its successor.
    if fm.get("status") == "deprecated" and not fm.get("superseded_by"):
        err("%s: status is 'deprecated' but no 'superseded_by' is set" % rel(path))
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
            if f in ("README.md", "AGENT.md", "CLAUDE.md") \
                    or (in_docs and f.endswith(".md")) or is_tool:
                full = os.path.join(dirpath, f)
                real = os.path.realpath(full)
                if real in seen_real:
                    continue
                seen_real.add(real)
                check_frontmatter(full, seen_ids)
                fm = parse_frontmatter(full)   # cheap re-parse for the roll-up
                if fm:
                    GOVERNED.append((rel(full), fm.get("kind"), fm.get("owner")))


def check_B():
    for d in REQUIRED_TOPLEVEL:
        if not os.path.isdir(os.path.join(ROOT, d)):
            err("required top-level dir '%s/' is missing" % d)
    for d in TAXONOMY:
        full = os.path.join(ROOT, d)
        if os.path.isdir(full):
            for need in ("README.md", "CLAUDE.md"):
                if not os.path.isfile(os.path.join(full, need)):
                    err("%s/: missing %s" % (d, need))


def check_C():
    srcroot = os.path.join(ROOT, "src")
    if not os.path.isdir(srcroot):
        return
    for dirpath, _, filenames in walk(srcroot):
        if not any(f.endswith(".py") for f in filenames):
            continue
        if "__init__.py" not in filenames:
            err("%s/: has .py files but no __init__.py (package boundary)"
                % rel(dirpath))
            continue
        init = os.path.join(dirpath, "__init__.py")
        try:
            with open(init, encoding="utf-8") as fh:
                if "__all__" not in fh.read():
                    err("%s: __init__.py defines no __all__ (public API surface)"
                        % rel(init))
        except Exception as e:
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
                    with open(full, encoding="utf-8") as fh:
                        tree = ast.parse(fh.read(), filename=full)
                except Exception as e:
                    warn("%s: could not parse (%s)" % (rel(full), e))
                    continue
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        if node.level == 0 and _private_segment(node.module):
                            err("%s:%d: absolute import of private module '%s' "
                                "crosses a package boundary - import from the "
                                "package public API instead"
                                % (rel(full), node.lineno, node.module))
                    elif isinstance(node, ast.Import):
                        for alias in node.names:
                            if _private_segment(alias.name):
                                err("%s:%d: import of private module '%s' "
                                    "crosses a package boundary"
                                    % (rel(full), node.lineno, alias.name))


def _exported_names(tree):
    """Return the string elements of a top-level __all__ literal, or []."""
    out = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "__all__" \
                        and isinstance(node.value, (ast.List, ast.Tuple)):
                    for elt in node.value.elts:
                        val = getattr(elt, "s", None)          # 3.6 ast.Str
                        if val is None and isinstance(elt, ast.Constant):
                            val = elt.value                     # 3.8+ ast.Constant
                        if isinstance(val, str):
                            out.append(val)
    return out


def check_E():
    """WARN when an __all__-exported symbol defined in-file has no docstring.
    Authored docstrings are the canonical corpus summaries; flag the gaps."""
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
                    with open(full, encoding="utf-8") as fh:
                        tree = ast.parse(fh.read(), filename=full)
                except Exception:
                    continue  # check_D already warns on parse failure
                exported = _exported_names(tree)
                if not exported:
                    continue
                defs = {}
                for node in tree.body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                         ast.ClassDef)):
                        defs[node.name] = node
                for name in sorted(exported):
                    nd = defs.get(name)   # only names DEFINED here (skip re-exports)
                    if nd is not None and not ast.get_docstring(nd):
                        warn("%s: exported symbol '%s' has no docstring "
                             "(authored summary missing)" % (rel(full), name))


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
                    err("%s: tool spec missing 'public_api' (the wrapped script)"
                        % rel(full))
                elif not os.path.exists(os.path.join(ROOT, inv)):
                    err("%s: public_api target '%s' does not exist" % (rel(full), inv))
                eff = fm.get("tool_effect")
                if eff not in TOOL_EFFECTS:
                    err("%s: tool_effect must be one of %s"
                        % (rel(full), sorted(TOOL_EFFECTS)))
                cmd = fm.get("tool_command") or ""
                if inv and inv != "none" and inv not in cmd:
                    err("%s: tool_command does not invoke public_api '%s'"
                        % (rel(full), inv))
    # accountability roll-up (warning): tools/agents must name a real owner
    for path, kind, owner in GOVERNED:
        if kind in ("tool", "agent") and (not owner or owner == "TBD"):
            warn("accountability: %s (%s) has no real owner (missing or 'TBD')"
                 % (path, kind))


def _tool_used_by(path):
    """Agent dirs (agents/<name>) listed under a tool spec's '## Used by'."""
    out = []
    in_section = False
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                s = line.strip()
                if s.startswith("## "):
                    in_section = s.lower() == "## used by"
                    continue
                if in_section and s.startswith("- "):
                    ref = s[2:].strip().rstrip("/")
                    if ref.startswith("agents/"):
                        out.append(ref)
    except Exception:
        pass
    return out


def _manifest_specs(path):
    """Tool-spec basenames referenced in an agent's tools.md (../tools/X.tool.md)."""
    out = []
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except Exception:
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
        out.append(text[j + len(marker):k])
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
                existing.add(f[:-len(".tool.md")])
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
                err("%s/tools.md: references unknown tool spec "
                    "'../tools/%s.tool.md'" % (agent, s))
            elif agent not in spec_to_agents.get(s, set()):
                err("%s/tools.md: uses '%s' but agents/tools/%s.tool.md "
                    "'## Used by' omits %s" % (agent, s, s, agent))
    for s in sorted(spec_to_agents):
        for agent in spec_to_agents[s]:
            if s not in agent_to_specs.get(agent, set()):
                err("agents/tools/%s.tool.md: '## Used by' names %s but its "
                    "tools.md omits '%s'" % (s, agent, s))


def _requires_python():
    """Return pyproject.toml's requires-python value, or None if absent."""
    try:
        with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as fh:
            text = fh.read()
    except Exception:
        return None
    m = re.search(r'requires-python\s*=\s*(["\'])([^"\']+)\1', text)
    return m.group(2).strip() if m else None


def _subdirs(relpath):
    """Immediate sub-directory names under ROOT/relpath, minus IGNORE_DIRS."""
    base = os.path.join(ROOT, relpath)
    out = []
    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            if name not in IGNORE_DIRS and os.path.isdir(os.path.join(base, name)):
                out.append(name)
    return out


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
    try:
        with open(path, encoding="utf-8") as fh:
            manifest = json.load(fh)
    except Exception as e:
        err("config/project.json: invalid JSON (%s)" % e)
        return
    if not isinstance(manifest, dict):
        err("config/project.json: top level must be a JSON object")
        return
    layers = _expect(manifest.get("layers"), dict, "layers", {})

    backend = _expect(layers.get("backend"), dict, "layers.backend", {})
    bpath = backend.get("path")
    if isinstance(bpath, str) and bpath and not os.path.isdir(os.path.join(ROOT, bpath)):
        err("config/project.json: layers.backend.path '%s' does not exist" % bpath)
    bpy = backend.get("python")
    if isinstance(bpy, str) and bpy:
        have = _requires_python()
        if have is not None and have != bpy:
            err("config/project.json: layers.backend.python '%s' != pyproject "
                "requires-python '%s'" % (bpy, have))

    frontend = _expect(layers.get("frontend"), dict, "layers.frontend", {})
    froot = frontend.get("root")
    if isinstance(froot, str) and froot:
        available = _expect(frontend.get("available"), list,
                            "layers.frontend.available", [])
        stack = frontend.get("stack")
        if isinstance(stack, str) and stack \
                and not os.path.isdir(os.path.join(ROOT, froot, stack)):
            err("config/project.json: layers.frontend.stack '%s' has no dir "
                "under %s/" % (stack, froot))
        for a in available:
            if isinstance(a, str) and not os.path.isdir(os.path.join(ROOT, froot, a)):
                warn("config/project.json: declared frontend stack '%s' is "
                     "missing (%s/%s)" % (a, froot, a))
        for d in _subdirs(froot):
            if d not in available:
                warn("%s/%s: present but not in config/project.json "
                     "layers.frontend.available (undeclared stack)" % (froot, d))

    transports = _expect(manifest.get("transports"), dict, "transports", {})
    enabled = _expect(transports.get("enabled"), list, "transports.enabled", [])
    avail = _expect(transports.get("available"), dict, "transports.available", {})
    for t in enabled:
        if t not in avail:
            err("config/project.json: transports.enabled '%s' not in "
                "transports.available" % t)
        elif isinstance(avail[t], str) \
                and not os.path.isdir(os.path.join(ROOT, avail[t])):
            err("config/project.json: enabled transport '%s' -> '%s' does not "
                "exist" % (t, avail[t]))
    declared = set(v for v in avail.values() if isinstance(v, str))
    for d in _subdirs("api"):
        if os.path.join("api", d) not in declared:
            warn("api/%s: present but not in config/project.json "
                 "transports.available (undeclared transport)" % d)

    # Agent runtimes (optional block): the default must be an available engine
    # and each engine's dir must exist (CONVENTIONS section 16).
    runtimes = manifest.get("runtimes")
    if runtimes is not None:
        runtimes = _expect(runtimes, dict, "runtimes", {})
        r_avail = _expect(runtimes.get("available"), dict, "runtimes.available", {})
        r_default = runtimes.get("default")
        if r_default is not None and r_default not in r_avail:
            err("config/project.json: runtimes.default '%s' not in "
                "runtimes.available" % r_default)
        for nm in sorted(r_avail):
            d = r_avail[nm]
            if isinstance(d, str) and not os.path.isdir(os.path.join(ROOT, d)):
                err("config/project.json: runtime '%s' -> '%s' does not exist"
                    % (nm, d))

    # Model adapters (optional block): the default must be an available adapter
    # and each adapter's dir must exist. models/registry.py is the code source of
    # truth; this manifest is the project's curated list, surfaced by the showcase.
    models = manifest.get("models")
    if models is not None:
        models = _expect(models, dict, "models", {})
        m_avail = _expect(models.get("available"), dict, "models.available", {})
        m_default = models.get("default")
        if m_default is not None and m_default not in m_avail:
            err("config/project.json: models.default '%s' not in "
                "models.available" % m_default)
        for nm in sorted(m_avail):
            d = m_avail[nm]
            if isinstance(d, str) and not os.path.isdir(os.path.join(ROOT, d)):
                err("config/project.json: model '%s' -> '%s' does not exist"
                    % (nm, d))


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
                err("%s: must be a symlink to the sibling AGENT.md, not a "
                    "regular file (CONVENTIONS section 5)" % rel(claude))
            elif os.readlink(claude) != "AGENT.md":
                err("%s: symlink target '%s' must be exactly 'AGENT.md' "
                    "(a relative sibling link)" % (rel(claude), os.readlink(claude)))
            elif not os.path.isfile(os.path.join(dirpath, "AGENT.md")):
                err("%s: symlink target AGENT.md does not exist" % rel(claude))
        elif has_agent:
            err("%s/AGENT.md: has no sibling CLAUDE.md symlink "
                "(CONVENTIONS section 5)" % rel(dirpath))


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
    "json", "urllib", "http", "socket", "ssl", "subprocess", "asyncio",
    "sqlite3", "struct", "pickle", "xml", "configparser", "argparse",
    "queue", "threading", "multiprocessing", "concurrent", "decimal",
    "os", "io", "re", "hashlib", "csv", "zlib", "gzip", "tarfile", "zipfile",
]


def _practice_ok_lines(text):
    """Line numbers carrying a `# practice-ok` suppression pragma (tokenize, so a
    `#` inside a string literal is never mistaken for a comment)."""
    out = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT and _PRACTICE_OK_RE.match(tok.string.strip()):
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
    path = os.path.join(ROOT, "config", "practices.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        mods = (data.get("tokens") or {}).get("stdlib_exception_modules")
        if isinstance(mods, list) and mods:
            return set(mods)
    except Exception:
        pass
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
                    with open(full, encoding="utf-8") as fh:
                        text = fh.read()
                    tree = ast.parse(text, filename=full)
                except Exception as e:
                    warn("%s: could not parse (%s)" % (rel(full), e))
                    continue
                pragma = _practice_ok_lines(text)
                for line, name in _foreign_exception_raises(
                        tree, local_tops, stdlib_mods, pragma):
                    err("%s:%d: raises third-party exception '%s' across a package "
                        "boundary - wrap it in an owned error "
                        "(or add `# practice-ok: <reason>`)" % (rel(full), line, name))


def main():
    check_A()
    check_B()
    check_C()
    check_D()
    check_E()
    check_F()
    check_G()
    check_H()
    check_I()
    check_J()
    for w_ in warnings:
        print("WARN  " + w_)
    for e_ in errors:
        print("ERROR " + e_)
    print("")
    print("check_structure: %d error(s), %d warning(s)"
          % (len(errors), len(warnings)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
