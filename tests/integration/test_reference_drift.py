"""
title: Integration — the settings reference and the feature catalogue list what the code holds
kind: tests
layer: n/a
summary: The reference-drift gate. config/project.json `doc_drift.settings_reference` names the settings reference; each of its keyed sections holds one table with the columns Key, Type, Default, Valid values, Read by, What changing it does, Not for and Ships, and each row is derived-equal to the code; a key listed twice is a finding. The JSON sections are exactly the files check_structure's JSON_CONFIGS reads, each heading naming its file, and every key path of that file (`_comment` dropped at any depth, `[]` for a list-of-object element, `<name>` for one segment of an open-keyed map) matches exactly one row; in the template each literal-path JSON row's Default states the value the file holds, or its twin renders under copier's default answers; the rendered project.json twin is judged under every answer set copier.yml's validators allow, rendered with StrictUndefined; the copier question rows equal copier.yml's questions and name what each prunes; the make variable rows equal what the makefiles assign and reference; the environment variable rows cover every literal read in code, recipes, workflows and the manifest; the command-line flag rows equal every `add_argument` in the code roots, with each literal default stated verbatim; the `models.default` and `runtimes.default` rows state the registry constant that decides. Every expected set is derived, never typed here; a missing or malformed `doc_drift` key fails, a section over zero items fails, and only the copier.yml-derived tests skip, with a stated reason, in a generated project. `doc_drift.features_reference` names the feature catalogue; every `## ` section table with the columns Feature, What it does and why, How to run, Settings, Limits / not for, Deep doc and Ships is keyed by its Feature cell's first code span, and the keys of the derived shapes equal what the tree declares: each check letter, each `## `-annotated make target with its effect label, each script `make check-all` reaches or the catalogue of deterministic checks lists, each copier job (a script beside conflict_guard's finish command that runs its guard), each gate test (a `test_*_gate.py` file directly in tests/integration), each shared script module (a scripts module that a module outside tests/ imports, read from the import graph tests/source_tree.py `import_edges` resolves through config/project.json `import_layers.search_roots`), each agent directory, each MCP server with a `__main__` guard, each registry model and runtime, each workflow and each agent skill. In a generated project the rows need only cover the derived set, and a derived-shaped row the project lacks must say in Ships which answer brings it. Every row states its limits, every Ships cell is `always`, `keel maintainers only` or `when <question>[=<value>]`, naming a question copier.yml asks and a value it offers, every Settings cell links to a heading of the settings reference, and in the template each derived row's Ships matches copier.yml's excludes under the answers it names and under those it leaves out, and no link lands on an excluded path. The CONVENTIONS section 2 scripts note names `derived_features`, this file and the catalogue's `Shared script modules` section, and states no count, in words or as the derived size, so the note cannot drift from the set. Each rule has a fault-injection twin that plants one fault and asserts exactly one more finding than the document had before. Not a writer: it reads the tree and writes nothing.
"""

import ast
import fnmatch
import functools
import importlib
import itertools
import json
import posixpath
import re
import sys
from pathlib import Path

import pytest

import optional_deps

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(_ROOT / "tests"))

import check_structure as cs  # noqa: E402
from test_doc_drift import (  # noqa: E402
    _TEMPLATE_ONLY,
    _TWIN_SUFFIX,
    DocDriftConfigError,
    _span_names,
    copier_inventory,
    entry_policy,
    load_manifest,
)

import source_tree as st  # noqa: E402

pytestmark = pytest.mark.integration

# The settings reference owns these: its keyed sections' table columns, the
# headings that are not a JSON file's path, and the words its cells use.
_COLUMNS = (
    "Key",
    "Type",
    "Default",
    "Valid values",
    "Read by",
    "What changing it does",
    "Not for",
    "Ships",
)
_COPIER_HEADING = "copier questions"
_MAKE_HEADING = "Make variables"
_ENV_HEADING = "Environment variables"
_CLI_HEADING = "Command-line flags"
_JSON_SUFFIX = ".json"
_MAINTAINERS = "keel maintainers only"
_ALWAYS = "always"
_WHEN = "when "
_DYNAMIC = "dynamic"
# A JSON key path's segments: `<name>` is one segment of an open-keyed map and
# `[]` one element of a list of objects.
_LIST_ELEMENT = "[]"
_WILDCARD = re.compile(r"^<[^<>]+>$")
_COMMENT_KEY = "_comment"
# A make assignment opens a line (a tab-led line is a recipe); a reference is
# `$(NAME)` or `${NAME}` that is not the shell's `$$`.
_MAKE_ASSIGN = re.compile(r"^([A-Za-z_.][A-Za-z0-9_.]*)\s*(\?=|::=|:=|\+=|=)\s*(.*)$")
_MAKE_REF = re.compile(r"(?<!\$)\$[({]([A-Z_][A-Z0-9_]*)[)}]")
# A recipe's shell parameter expansion: `$${NAME` (make's escape of `${NAME`).
_SHELL_PARAM = re.compile(r"\$\$\{([A-Z_][A-Z0-9_]*)")
# A frontend's reads of its build environment.
_JS_ENV = re.compile(r"\b(?:process\.env|import\.meta\.env)\.([A-Z_][A-Z0-9_]*)")
_JS_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".astro")
_WORKFLOW_DIR = ".github/workflows"
_WORKFLOW_SUFFIXES = (".yml", ".yaml")
_YAML_ENV = re.compile(r"^(\s*)env:\s*$")
_YAML_KEY = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*):")
# A Python read of the environment: the mapping and the calls on it.
_ENVIRON = "environ"
_ENV_CALLS = ("get", "pop", "setdefault")
_GETENV = "getenv"
# A test module reads the harness's environment (HOME, PATH), not a setting.
_TEST_MODULE = re.compile(r"^(?:test_.*|conftest)\.py$")
_ADD_ARGUMENT = "add_argument"
# The copier.yml question defaults that are jinja are computed, not literal.
_JINJA_EXPR = "{{"
# The registry constants the manifest's declarative defaults stand beside.
_REGISTRIES = (
    ("models", "models.registry", "DEFAULT_MODEL"),
    ("runtimes", "runtimes.registry", "DEFAULT_RUNTIME"),
)
_DEFAULT_KEY = "default"
# The copier.yml question keys the answer sets read.
_CHOICES_KEY = "choices"
_WHEN_KEY = "when"
_TYPE_KEY = "type"
_BOOL_TYPE = "bool"
_MULTISELECT_KEY = "multiselect"
_VALIDATOR_KEY = "validator"
_MANIFEST_TWIN = "config/project.json.jinja"
_MISSING = object()


# --- the document ---------------------------------------------------------


def settings_sections(text):
    """{heading: section text} for every `## ` heading outside fenced code."""
    return {name: "\n".join(body) for name, body in cs._sections(text)}


def _first_span(cell):
    m = cs._BACKTICKED.search(cell)
    return m.group(1).strip() if m else None


def section_rows(doc, sections, heading):
    """(rows, findings): each row of the section's keyed table as {column:
    cell}, keyed by its Key cell's first code span. A section that is absent,
    holds no table with every column, holds a row with no code-span key, or
    lists a key twice is a finding."""
    if heading not in sections:
        return [], ["%s: has no `## %s` section" % (doc, heading)]
    table = cs._pipe_table(sections[heading], _COLUMNS)
    if table is None:
        return [], [
            "%s: `## %s` holds no table with the columns %s"
            % (doc, heading, ", ".join(_COLUMNS))
        ]
    header, cells = table
    rows, findings = [], []
    for raw in cells:
        row = {
            col: (
                raw[header.index(col.lower())]
                if header.index(col.lower()) < len(raw)
                else ""
            )
            for col in _COLUMNS
        }
        key = _first_span(row["Key"])
        if key is None:
            findings.append(
                "%s: `## %s` has a row whose Key cell names no code span: %r"
                % (doc, heading, row["Key"])
            )
            continue
        if any(r["key"] == key for r in rows):
            # A dict keyed by the Key cell keeps one of two rows, so the other's
            # Default would go unjudged: a key is listed once.
            findings.append(
                "%s: `## %s` lists `%s` twice; list it once" % (doc, heading, key)
            )
            continue
        row["key"] = key
        rows.append(row)
    if not rows and not findings:
        findings.append("%s: `## %s` lists no row -- zero items" % (doc, heading))
    return rows, findings


def _ships(row):
    return row["Ships"].strip().lower()


def _default_span(row):
    return _first_span(row["Default"])


# --- JSON key paths -------------------------------------------------------


def json_key_paths(data):
    """Every leaf key path of *data* as a tuple of segments: `_comment`
    dropped at any depth, a list whose elements are all objects walked with a
    `[]` segment, and an empty object kept as a leaf of its own."""
    paths = set()

    def walk(node, prefix):
        if isinstance(node, dict):
            keys = [k for k in node if k != _COMMENT_KEY]
            if not keys:
                if prefix:
                    paths.add(prefix)
                return
            for key in keys:
                walk(node[key], prefix + (key,))
        elif isinstance(node, list) and node and all(isinstance(e, dict) for e in node):
            for element in node:
                walk(element, prefix + (_LIST_ELEMENT,))
        else:
            paths.add(prefix)

    walk(data, ())
    return paths


def row_segments(key):
    """A row key's segments: dotted, with a `[]` suffix split off as its own
    segment (`practices[].status` -> practices, [], status)."""
    segments = []
    for part in key.split("."):
        if part.endswith(_LIST_ELEMENT):
            segments.extend([part[: -len(_LIST_ELEMENT)], _LIST_ELEMENT])
        else:
            segments.append(part)
    return tuple(segments)


def _segment_matches(row_seg, seg):
    return row_seg == seg or (bool(_WILDCARD.match(row_seg)) and seg != _LIST_ELEMENT)


def row_matches(segments, path):
    """A row matches a path segment by segment; a row whose last segment is a
    `<name>` also matches its map's own path, which is a leaf when the map is
    empty."""
    if len(segments) == len(path):
        return all(_segment_matches(r, p) for r, p in zip(segments, path, strict=False))
    if len(segments) == len(path) + 1 and _WILDCARD.match(segments[-1]):
        return all(_segment_matches(r, p) for r, p in zip(segments, path, strict=False))
    return False


def row_covers(segments, path):
    """A row covers a path it matches or one inside the object it names, so a
    row for a block that may be null (`layers.app`) stands beside the rows for
    its fields."""
    if row_matches(segments, path):
        return True
    return len(path) > len(segments) and all(
        _segment_matches(r, p) for r, p in zip(segments, path, strict=False)
    )


def json_row_findings(doc, heading, rows, paths, exhaustive):
    """Each path matches exactly one row. With *exhaustive* (the template,
    where every key ships somewhere) each row matches a path unless it ships
    to keel maintainers only; without it (a generated project, whose answers
    left some keys out) the rows need only cover the paths."""
    findings = []
    if not paths:
        return ["%s: `## %s` is judged over zero key paths" % (doc, heading)]
    parsed = [(row, row_segments(row["key"])) for row in rows]
    for path in sorted(paths):
        hits = [row["key"] for row, segs in parsed if row_matches(segs, path)]
        if len(hits) != 1:
            findings.append(
                "%s: `## %s` key path %s matches %d rows (%s); it must match exactly one"
                % (doc, heading, ".".join(path), len(hits), ", ".join(hits) or "none")
            )
    if exhaustive:
        for row, segs in parsed:
            if _ships(row) == _MAINTAINERS:
                continue
            if not any(row_covers(segs, p) for p in paths):
                findings.append(
                    "%s: `## %s` row `%s` matches no key path of the file"
                    % (doc, heading, row["key"])
                )
    return findings


def json_configs():
    """The JSON files the structure gate reads as configuration, each of which
    the settings reference describes in a section headed by its path. The set
    is check_structure's, never this document's: a section the document drops
    would otherwise drop its file from the judgement."""
    return sorted(posixpath.join(*Path(p).parts) for p in cs.JSON_CONFIGS)


def json_heading_findings(doc, sections, configs):
    """Each JSON config file has a `## <path>` section, and each section
    headed by a JSON file's path is one of them."""
    if not configs:
        return ["%s: the structure gate reads zero JSON configs -- zero items" % doc]
    headed = {h for h in sections if h.endswith(_JSON_SUFFIX)}
    findings = [
        "%s: has no `## %s` section for a JSON config the structure gate reads"
        % (doc, path)
        for path in configs
        if path not in headed
    ]
    findings += [
        "%s: `## %s` names a JSON file the structure gate does not read as config"
        % (doc, heading)
        for heading in sorted(headed - set(configs))
    ]
    return findings


# --- ships: which answers a source file arrives under ---------------------


def _covers(entry, path):
    return (
        path == entry
        or path.startswith(entry + "/")
        or fnmatch.fnmatchcase(path, entry)
    )


def ships_for_paths(paths, exclude_conditions, questions):
    """What a setting read in *paths* ships as: "always" when any reader
    ships unconditionally, "when" plus the questions whose answers prune the
    rest when every reader is answer-driven, else "keel maintainers only"
    (every reader is excluded outright). -> (kind, sorted questions)."""
    kinds, named = set(), set()
    for path in paths:
        covering = [c for e, c in exclude_conditions.items() if _covers(e, path)]
        if any(c == "" for c in covering):
            kinds.add(_MAINTAINERS)
        elif covering:
            kinds.add(_WHEN)
            for condition in covering:
                named.update(
                    q
                    for q in questions
                    if re.search(r"\b%s\b" % re.escape(q), condition)
                )
        else:
            kinds.add(_ALWAYS)
    if not kinds:
        raise DocDriftConfigError("a setting with no reader cannot be placed")
    if _ALWAYS in kinds:
        return _ALWAYS, []
    if _WHEN in kinds:
        return _WHEN, sorted(named)
    return _MAINTAINERS, []


def ships_findings(doc, heading, rows, readers, exclude_conditions, questions):
    """Each row's Ships cell states what `ships_for_paths` derives from the
    files that read it: `always`, `keel maintainers only`, or `when ...`
    naming each question that prunes it, with an answer that ships one of
    those files and no answer it excludes (`ships_value_findings`)."""
    findings, claimed = [], []
    for row in rows:
        if row["key"] not in readers:
            continue
        kind, named = ships_for_paths(
            readers[row["key"]], exclude_conditions, questions
        )
        cell = _ships(row)
        ok = (
            cell == kind
            if kind != _WHEN
            else (cell.startswith(_WHEN) and all(q in row["Ships"] for q in named))
        )
        if not ok:
            findings.append(
                "%s: `## %s` row `%s` says Ships %r; its readers ship %s"
                % (
                    doc,
                    heading,
                    row["key"],
                    row["Ships"],
                    kind.strip() + (" " + ", ".join(named) if named else ""),
                )
            )
        elif kind == _WHEN:
            claimed.append(row)

    def ships_under(row, answers):
        return any(
            not excluded(path, exclude_conditions, answers)
            for path in readers[row["key"]]
        )

    return findings + ships_value_findings(
        doc, heading, claimed, questions, ships_under
    )


# --- copier answers: every combination the questions allow ----------------


@functools.lru_cache(maxsize=1)
def _jinja():
    """A jinja environment that fails on a name no answer defines, so a
    template gated on a question the answer sets leave out raises instead of
    rendering the gate as false."""
    jinja2 = optional_deps.importorskip("jinja2", extra="template")
    return jinja2.Environment(
        keep_trailing_newline=True, undefined=jinja2.StrictUndefined
    )


def _choice_values(spec):
    choices = spec.get(_CHOICES_KEY) if isinstance(spec, dict) else None
    if isinstance(choices, dict):
        return list(choices.values())
    return list(choices or [])


def _is_computed(spec):
    return isinstance(spec, dict) and spec.get(_WHEN_KEY) is False


def _is_bool(spec):
    return isinstance(spec, dict) and spec.get(_TYPE_KEY) == _BOOL_TYPE


def _is_multiselect(spec):
    return isinstance(spec, dict) and bool(spec.get(_MULTISELECT_KEY))


def question_domain(spec):
    """The answers to try for one question, one per effect a gate can see:
    both values of a yes/no question, each choice of a select, and for a
    multiselect no choice, each choice alone and every choice; a free-text
    question keeps its default."""
    choices = _choice_values(spec)
    if _is_bool(spec):
        return [True, False]
    if _is_multiselect(spec):
        every = [list(choices)] if len(choices) > 1 else []
        return [[]] + [[c] for c in choices] + every
    if choices:
        return list(choices)
    return [spec.get(_DEFAULT_KEY) if isinstance(spec, dict) else spec]


def complete_answers(questions, partial):
    """*partial* over copier.yml's defaults, in its order, each default that
    is jinja rendered from the answers before it (a computed question)."""
    answers = {}
    for name, spec in questions.items():
        if name in partial:
            answers[name] = partial[name]
            continue
        default = spec.get(_DEFAULT_KEY) if isinstance(spec, dict) else spec
        if isinstance(default, str) and _JINJA_EXPR in default:
            default = _jinja().from_string(default).render(**answers)
        answers[name] = default
    return answers


def answers_valid(questions, answers):
    """True when every question's `validator` renders empty for *answers*."""
    for spec in questions.values():
        validator = spec.get(_VALIDATOR_KEY) if isinstance(spec, dict) else None
        if validator and _jinja().from_string(validator).render(**answers).strip():
            return False
    return True


def answer_sets(questions):
    """Every combination of the asked questions' domains that copier.yml's
    validators accept, each completed over the defaults: the answers a
    generated project can hold, read from copier.yml, never typed here."""
    asked = [
        (name, question_domain(spec))
        for name, spec in questions.items()
        if not _is_computed(spec)
    ]
    names = [name for name, _domain in asked]
    found = []
    for combo in itertools.product(*[domain for _name, domain in asked]):
        answers = complete_answers(questions, dict(zip(names, combo, strict=True)))
        if answers_valid(questions, answers):
            found.append(answers)
    if not found:
        raise DocDriftConfigError(
            "copier.yml: no combination of its answers passes its validators"
        )
    return found


def excluded(path, exclude_conditions, answers):
    """True when an `_exclude` entry covering *path* holds under *answers*
    (an entry with no condition always holds)."""
    for entry, condition in exclude_conditions.items():
        if not _covers(entry, path):
            continue
        if not condition or _jinja().compile_expression(condition)(**answers):
            return True
    return False


# A `when` Ships cell, its code spans dropped: `when <question>`, `when
# <question>=<value>`, `when <question>!=<value>`, `when <question> is
# <value>` or `when <question> is not <value>`.
_SHIPS_CLAUSE = re.compile(
    r"^when ([a-z_]+)(?:(?:\s*(=|!=)\s*|\s+is\s+(not\s+)?)([\w-]+))?$"
)
_TRUE, _FALSE = "true", "false"


def ships_claim(cell, questions):
    """(question, [answers it ships under], [answers it does not]) that a
    `when` Ships cell claims, each answer one question's; or a string saying
    why the cell names no answer copier.yml offers. A bare `when <question>`
    claims a yes/no question's yes, or a multiselect's every choice."""
    m = _SHIPS_CLAUSE.match(cell.replace("`", "").strip().lower())
    if m is None:
        return (
            "is not `when <question>[=<value>]` or `when <question> is [not] <value>`"
        )
    name, negate, value = m.group(1), bool(m.group(2) == "!=" or m.group(3)), m.group(4)
    spec = questions.get(name)
    if spec is None:
        return "copier.yml asks no question `%s`" % name
    choices = _choice_values(spec)
    if _is_bool(spec):
        value = value or _TRUE
        if value not in (_TRUE, _FALSE):
            return "`%s` is a yes/no question; `%s` is neither %s nor %s" % (
                name,
                value,
                _TRUE,
                _FALSE,
            )
        ships, other = [{name: value == _TRUE}], [{name: value != _TRUE}]
    elif not choices:
        return "`%s` offers no choices to name" % name
    elif value is None:
        if not _is_multiselect(spec):
            return "name the `%s` choice that ships it" % name
        ships, other = [{name: list(choices)}], [{name: []}]
    else:
        match = [c for c in choices if str(c).lower() == value]
        if not match:
            return "`%s` is not a choice of `%s` (%s)" % (
                value,
                name,
                ", ".join(str(c) for c in choices),
            )
        if _is_multiselect(spec):
            ships = [{name: [match[0]]}]
            other = [{name: [c for c in choices if c != match[0]]}]
        else:
            ships = [{name: match[0]}]
            other = [{name: c} for c in choices if c != match[0]]
    if negate:
        ships, other = other, ships
    return name, ships, other


def ships_value_findings(doc, heading, rows, questions, ships_under):
    """Each `when` row's claim holds: under each answer it names, every other
    answer at copier.yml's default, *ships_under(row, answers)* is true, and
    under each answer it excludes it is false. An answer copier.yml's
    validators refuse is not judged."""
    findings = []
    for row in rows:
        if not _ships(row).startswith(_WHEN):
            continue
        claim = ships_claim(row["Ships"], questions)
        if isinstance(claim, str):
            findings.append(
                "%s: `## %s` row `%s` says Ships %r: %s"
                % (doc, heading, row["key"], row["Ships"], claim)
            )
            continue
        _name, ships, other = claim
        wrong = []
        for partial, want in [(a, True) for a in ships] + [(a, False) for a in other]:
            answers = complete_answers(questions, partial)
            if answers_valid(questions, answers) and ships_under(row, answers) != want:
                wrong.append(
                    "%s under %s"
                    % ("does not ship" if want else "ships", json.dumps(partial))
                )
        if wrong:
            findings.append(
                "%s: `## %s` row `%s` says Ships %r, yet it %s"
                % (doc, heading, row["key"], row["Ships"], "; ".join(wrong))
            )
    return findings


# --- copier questions -----------------------------------------------------


def _literal_text(value):
    return value if isinstance(value, str) else json.dumps(value)


def copier_questions(root):
    """{question: its copier.yml mapping}, or None outside the template."""
    path = Path(root) / "copier.yml"
    if not path.is_file():
        return None
    yaml = optional_deps.importorskip("yaml", extra="template")
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(cfg, dict):
        raise DocDriftConfigError("copier.yml: top level is not a mapping")
    return {k: v for k, v in cfg.items() if not k.startswith("_")}


def _names(question, condition):
    return bool(re.search(r"\b%s\b" % re.escape(question), condition))


def question_prunes(name, inventory):
    """Every path `_exclude` prunes, or a `_migrations` entry removes, under a
    condition that names the question *name*."""
    prunes = {
        p for p, c in inventory["exclude_conditions"].items() if c and _names(name, c)
    }
    prunes |= {
        p for p, c in inventory["migration_conditions"].items() if _names(name, c)
    }
    return prunes


def copier_findings(doc, rows, questions, inventory):
    """The rows are copier.yml's questions; a literal default is the Default
    cell's code span; each row names, as a code span, every path `_exclude`
    prunes and every path a `_migrations` entry removes under a condition on
    that question."""
    findings = []
    if not questions:
        return ["%s: copier.yml asks zero questions" % doc]
    keyed = {row["key"]: row for row in rows}
    findings += [
        "%s: `## %s` has no row for the question `%s`" % (doc, _COPIER_HEADING, name)
        for name in sorted(set(questions) - set(keyed))
    ]
    findings += [
        "%s: `## %s` row `%s` is not a copier.yml question"
        % (doc, _COPIER_HEADING, name)
        for name in sorted(set(keyed) - set(questions))
    ]
    for name in sorted(set(keyed) & set(questions)):
        row, spec = keyed[name], questions[name]
        default = spec.get(_DEFAULT_KEY) if isinstance(spec, dict) else None
        if not (isinstance(default, str) and _JINJA_EXPR in default):
            want = _literal_text(default)
            if _default_span(row) != want:
                findings.append(
                    "%s: `## %s` row `%s` states Default %r; copier.yml's is `%s`"
                    % (doc, _COPIER_HEADING, name, row["Default"], want)
                )
        named = set()
        for cell in row.values():
            named |= _span_names(cell)
        findings += [
            "%s: `## %s` row `%s` does not name `%s`, which its answer prunes"
            % (doc, _COPIER_HEADING, name, path)
            for path in sorted(question_prunes(name, inventory) - named)
        ]
    return findings


# --- make variables -------------------------------------------------------


def make_variables(root):
    """({name: [(operator, right-hand side)]}, {referenced names}) over every
    makefile make reads."""
    assigned, referenced = {}, set()
    makefiles = cs.walk_makefiles(str(root), lambda _m: None)
    if not makefiles:
        raise DocDriftConfigError("no Makefile to read")
    for _rel, text in makefiles:
        for line in text.split("\n"):
            if line.lstrip().startswith("#"):
                continue
            if not line.startswith("\t"):
                m = _MAKE_ASSIGN.match(line)
                if m:
                    assigned.setdefault(m.group(1), []).append(
                        (m.group(2), m.group(3).strip())
                    )
            referenced.update(_MAKE_REF.findall(line))
    return assigned, referenced


def make_findings(doc, rows, assigned, referenced, exhaustive):
    """The rows are every assigned name and every upper-case reference; a
    `?=` default is the Default cell's code span, verbatim."""
    findings = []
    names = set(assigned) | referenced
    if not names:
        return ["%s: the makefiles assign and reference zero variables" % doc]
    keyed = {row["key"]: row for row in rows}
    findings += [
        "%s: `## %s` has no row for `%s`" % (doc, _MAKE_HEADING, name)
        for name in sorted(names - set(keyed))
    ]
    findings += [
        "%s: `## %s` row `%s` is in no makefile" % (doc, _MAKE_HEADING, name)
        for name in sorted(set(keyed) - names)
        if exhaustive or _ships(keyed[name]) == _ALWAYS
    ]
    for name in sorted(set(keyed) & set(assigned)):
        for op, rhs in assigned[name]:
            if op == "?=" and _default_span(keyed[name]) != rhs:
                findings.append(
                    "%s: `## %s` row `%s` states Default %r; the makefile's is `%s`"
                    % (doc, _MAKE_HEADING, name, keyed[name]["Default"], rhs)
                )
    return findings


# --- environment variables ------------------------------------------------


def _py_files(root, roots):
    for top in roots:
        base = Path(root) / top
        if not base.is_dir():
            continue
        for dirpath, _dirs, files in cs.walk(str(base)):
            for name in sorted(files):
                if name.endswith(".py"):
                    yield Path(dirpath) / name


def _module_strings(tree):
    """{NAME: value} for every module-level `NAME = "literal"`."""
    out = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = node.value.value
    return out


def _is_environ(node):
    return (isinstance(node, ast.Attribute) and node.attr == _ENVIRON) or (
        isinstance(node, ast.Name) and node.id == _ENVIRON
    )


def _string_of(node, constants):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    return None


def python_env_reads(path):
    """Every environment variable *path* reads by a name it spells: through
    `environ[...]`, `environ.get/pop/setdefault(...)`, `... in environ`, or
    `getenv(...)`, the name a literal or a module-level string constant."""
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    constants = _module_strings(tree)
    found = set()
    for node in ast.walk(tree):
        name = None
        if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load):
            if _is_environ(node.value):
                name = _string_of(node.slice, constants)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.args
        ):
            func = node.func
            if (
                func.attr in _ENV_CALLS and _is_environ(func.value)
            ) or func.attr == _GETENV:
                name = _string_of(node.args[0], constants)
        elif (
            isinstance(node, ast.Compare)
            and len(node.ops) == 1
            and isinstance(node.ops[0], ast.In)
            and _is_environ(node.comparators[0])
        ):
            name = _string_of(node.left, constants)
        if name:
            found.add(name)
    return found


def _workflow_env_keys(text):
    """The keys of every `env:` mapping in a workflow, at its first indent."""
    keys, lines = set(), text.split("\n")
    for i, line in enumerate(lines):
        m = _YAML_ENV.match(line)
        if not m:
            continue
        indent, child = len(m.group(1)), None
        for nxt in lines[i + 1 :]:
            if not nxt.strip() or nxt.lstrip().startswith("#"):
                continue
            k = _YAML_KEY.match(nxt)
            depth = len(nxt) - len(nxt.lstrip())
            if depth <= indent:
                break
            if child is None:
                child = depth
            if k and depth == child:
                keys.add(k.group(2))
    return keys


def env_readers(root, manifest):
    """{variable: {files that read it}} over the code roots' non-test Python,
    the frontends' sources, the makefiles' recipes, the workflows' `env:`
    blocks, `make_targets.unattended_vars` (what WRITE_GUARD reads) and
    `models.credential_env` (what an adapter's child is given)."""
    readers = {}

    def add(name, path):
        readers.setdefault(name, set()).add(path)

    roots = [r for r in cs.CODE_ROOTS if (Path(root) / r).is_dir()]
    for path in _py_files(root, roots):
        if _TEST_MODULE.match(path.name):
            continue
        rel = path.relative_to(root).as_posix()
        for name in python_env_reads(path):
            add(name, rel)
    for dirpath, _dirs, files in cs.walk(str(Path(root) / "src")):
        for fname in sorted(files):
            if fname.endswith(_JS_SUFFIXES):
                full = Path(dirpath) / fname
                rel = full.relative_to(root).as_posix()
                for name in _JS_ENV.findall(full.read_text(encoding="utf-8")):
                    add(name, rel)
    for rel, text in cs.walk_makefiles(str(root), lambda _m: None):
        for name in _SHELL_PARAM.findall(text):
            add(name, rel)
    workflows = Path(root) / _WORKFLOW_DIR
    if workflows.is_dir():
        for wf in sorted(workflows.iterdir()):
            if wf.suffix in _WORKFLOW_SUFFIXES:
                for name in _workflow_env_keys(wf.read_text(encoding="utf-8")):
                    add(name, wf.relative_to(root).as_posix())
    for name in (manifest.get("make_targets") or {}).get("unattended_vars") or []:
        add(name, "Makefile")
    for names in ((manifest.get("models") or {}).get("credential_env") or {}).values():
        for name in names:
            add(name, "models")
    return readers


def env_findings(doc, rows, readers, exhaustive):
    """Every variable read has a row; a row no reader names is marked
    `dynamic` in its Type cell (a name the code builds), or, in a generated
    project, does not ship always."""
    if not readers:
        return ["%s: the code reads zero environment variables" % doc]
    keyed = {row["key"]: row for row in rows}
    findings = [
        "%s: `## %s` has no row for `%s`, which %s reads"
        % (doc, _ENV_HEADING, name, ", ".join(sorted(readers[name])))
        for name in sorted(set(readers) - set(keyed))
    ]
    for name in sorted(set(keyed) - set(readers)):
        row = keyed[name]
        if _DYNAMIC in row["Type"].lower():
            continue
        if exhaustive or _ships(row) == _ALWAYS:
            findings.append(
                "%s: `## %s` row `%s` is read nowhere and is not marked `%s`"
                % (doc, _ENV_HEADING, name, _DYNAMIC)
            )
    return findings


# --- command-line flags ---------------------------------------------------


def _resolve_flag(node, constants, path, root):
    """A flag spelled as a literal, a module constant, or `module.CONSTANT`
    of a sibling module; None when it is none of those."""
    text = _string_of(node, constants)
    if text is not None:
        return text
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        for base in (
            path.parent,
            Path(root) / "scripts",
            Path(root) / "scripts" / "jobs",
        ):
            module = base / (node.value.id + ".py")
            if module.is_file():
                tree = ast.parse(module.read_text(encoding="utf-8"), str(module))
                return _module_strings(tree).get(node.attr)
    return None


def cli_flags(root):
    """({"<script> <flag or dest>": default node or None}, findings) for every
    `add_argument` call in the code roots."""
    flags, findings = {}, []
    roots = [r for r in cs.CODE_ROOTS if (Path(root) / r).is_dir()]
    for path in _py_files(root, roots):
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        constants = _module_strings(tree)
        rel = path.relative_to(root).as_posix()
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == _ADD_ARGUMENT
            ):
                continue
            if not node.args:
                findings.append(
                    "%s:%d: an add_argument with no name" % (rel, node.lineno)
                )
                continue
            flag = _resolve_flag(node.args[0], constants, path, root)
            if flag is None:
                findings.append(
                    "%s:%d: an add_argument whose name this gate cannot read"
                    % (rel, node.lineno)
                )
                continue
            default = next(
                (k.value for k in node.keywords if k.arg == _DEFAULT_KEY), None
            )
            flags["%s %s" % (rel, flag)] = default
    return flags, findings


def _expected_default(node):
    """The Default cell a flag's `default=` stands for: its source when it is
    a literal, "" when it is computed, None when there is none."""
    if node is None:
        return None
    try:
        ast.literal_eval(node)
    except ValueError:
        return ""
    return ast.unparse(node)


def cli_findings(doc, rows, flags, exhaustive):
    """The rows are every flag; a literal default is the Default cell's code
    span, verbatim; a flag with no `default=` has an empty Default cell; a
    computed one names something."""
    if not flags:
        return ["%s: the code roots declare zero command-line flags" % doc]
    keyed = {row["key"]: row for row in rows}
    findings = [
        "%s: `## %s` has no row for `%s`" % (doc, _CLI_HEADING, key)
        for key in sorted(set(flags) - set(keyed))
    ]
    findings += [
        "%s: `## %s` row `%s` is declared nowhere" % (doc, _CLI_HEADING, key)
        for key in sorted(set(keyed) - set(flags))
        if exhaustive or _ships(keyed[key]) == _ALWAYS
    ]
    for key in sorted(set(keyed) & set(flags)):
        want, cell = _expected_default(flags[key]), keyed[key]["Default"].strip()
        if want is None and cell.lower() not in cs._EMPTY_CELLS:
            findings.append(
                "%s: `## %s` row `%s` states Default %r; it has none (write —)"
                % (doc, _CLI_HEADING, key, cell)
            )
        elif want == "" and cell.lower() in cs._EMPTY_CELLS:
            findings.append(
                "%s: `## %s` row `%s` has a computed default; say what it is"
                % (doc, _CLI_HEADING, key)
            )
        elif want and _first_span(cell) != want:
            findings.append(
                "%s: `## %s` row `%s` states Default %r; the code's is `%s`"
                % (doc, _CLI_HEADING, key, cell, want)
            )
    return findings


def cli_readers(flags):
    return {key: {key.split(" ", 1)[0]} for key in flags}


# --- registry defaults ----------------------------------------------------


def registry_findings(doc, rows, manifest):
    """`models.default` and `runtimes.default` state the manifest's value as
    their Default and name the registry constant that decides, with its
    value."""
    findings = []
    keyed = {row["key"]: row for row in rows}
    for block, module, constant in _REGISTRIES:
        key = "%s.%s" % (block, _DEFAULT_KEY)
        row = keyed.get(key)
        if row is None:
            findings.append("%s: has no `%s` row" % (doc, key))
            continue
        declared = (manifest.get(block) or {}).get(_DEFAULT_KEY)
        if _default_span(row) != declared:
            findings.append(
                "%s: row `%s` states Default %r; the manifest's is `%s`"
                % (doc, key, row["Default"], declared)
            )
        value = getattr(importlib.import_module(module), constant)
        text = " ".join(row[c] for c in _COLUMNS)
        if "%s.%s" % (module, constant) not in text or value not in text:
            findings.append(
                "%s: row `%s` does not name `%s.%s` (`%s`), which decides"
                % (doc, key, module, constant, value)
            )
    return findings


# --- the feature catalogue ------------------------------------------------

# The feature catalogue owns these: its tables' columns, the Ships grammar its
# cells use, and the shapes a key derived from the tree takes. The directory
# names are CONVENTIONS §2 rows; the copier-job directory is conflict_guard's.
_FEATURE_COLUMNS = (
    "Feature",
    "What it does and why",
    "How to run",
    "Settings",
    "Limits / not for",
    "Deep doc",
    "Ships",
)
_FEATURE_KEY = "Feature"
_LIMITS = "Limits / not for"
_SETTINGS_CELL = "Settings"
_CHECK_KEY = "check_%s"
_MAKE_KEY = "make %s"
_EFFECT_SPAN = re.compile(r"^\[[a-z]+(?:,[a-z]+)*\]$")
_SHIPS_WHEN = re.compile(r"^when ([a-z_]+)(?:=([\w-]+))?$")
_CATALOGUE_COLUMNS = ("Script", "Gate?")
_REGISTRY_LISTS = (
    ("model", "models.registry", "list_models"),
    ("runtime", "runtimes.registry", "list_runtimes"),
)
_AGENTS_DIR = "agents"
_MCP_DIR = "mcp"
# A gate test is a file of this name directly in the integration directory; a
# shared script module is a file under the scripts directory that a module
# outside the tests directory imports. The two groups' names, and the section
# of the catalogue and the CONVENTIONS section 2 note that point at them.
_GATE_TEST_DIR = "tests/integration"
_GATE_TEST_NAME = "test_*_gate.py"
_SCRIPTS_DIR = "scripts/"
_TESTS_DIR = "tests/"
_GATE_TEST_GROUP = "gate test"
_SHARED_GROUP = "shared script module"
_SHARED_SECTION = "Shared script modules"
_SCRIPTS_NOTE = "Note: `scripts/`"
_SKILLS_DIR = ".claude/skills"
_GUARD_CALL = "exit_if_conflicted"
_MAIN = "__main__"
# A key of one of these shapes names something the tree derives; any other key
# (a discipline, a placeholder, a product row) is the author's.
_DERIVED_SHAPES = (
    re.compile(r"^check_[A-Z]$"),
    re.compile(r"^make [A-Za-z0-9_][A-Za-z0-9_.-]*$"),
    re.compile(r"^(?:model|runtime):\S+$"),
    re.compile(r"^%s/[^/\s]+/$" % re.escape(_AGENTS_DIR)),
    re.compile(r"^%s/[^/\s]+/$" % re.escape(_SKILLS_DIR)),
    re.compile(r"^%s/[^/\s]+\.ya?ml$" % re.escape(_WORKFLOW_DIR)),
    re.compile(r"^[\w./-]+\.py$"),
)


def feature_rows(doc, text):
    """(rows, findings): every row of every `## ` section's feature table as
    {column: cell}, keyed by its Feature cell's first code span and tagged
    with its section. A row with no code-span key, a key listed twice, and a
    document with no row are findings."""
    rows, findings, seen = [], [], {}
    for heading, body in cs._sections(text):
        table = cs._pipe_table("\n".join(body), _FEATURE_COLUMNS)
        if table is None:
            continue
        header, cells = table
        for raw in cells:
            row = {}
            for col in _FEATURE_COLUMNS:
                at = header.index(col.lower())
                row[col] = raw[at] if at < len(raw) else ""
            key = _first_span(row[_FEATURE_KEY])
            if key is None:
                findings.append(
                    "%s: `## %s` has a row whose Feature cell names no code span: %r"
                    % (doc, heading, row[_FEATURE_KEY])
                )
                continue
            if key in seen:
                findings.append(
                    "%s: `%s` has a row in `## %s` and in `## %s`; list it once"
                    % (doc, key, seen[key], heading)
                )
                continue
            seen[key] = heading
            row["key"], row["section"] = key, heading
            rows.append(row)
    if not rows and not findings:
        findings.append(
            "%s: holds no table with the columns %s -- zero items"
            % (doc, ", ".join(_FEATURE_COLUMNS))
        )
    return rows, findings


def _is_derived_shape(key):
    return any(shape.match(key) for shape in _DERIVED_SHAPES)


def _rel(root, path):
    return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()


def _has_main_guard(tree):
    for node in tree.body:
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
            names = [node.test.left, *node.test.comparators]
            if any(
                isinstance(n, ast.Name) and n.id == "__name__" for n in names
            ) and any(isinstance(n, ast.Constant) and n.value == _MAIN for n in names):
                return True
    return False


def _calls(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if (isinstance(func, ast.Attribute) and func.attr == name) or (
                isinstance(func, ast.Name) and func.id == name
            ):
                return True
    return False


def _parse(path):
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def copier_jobs(root):
    """Each script in conflict_guard's job directory that runs its guard: the
    copier jobs, found where copier.yml is absent too."""
    import conflict_guard  # noqa: PLC0415 -- stdlib-only; its import runs nothing

    jobs_dir = Path(root) / Path(conflict_guard.FINISH_SCRIPT).parent
    if not jobs_dir.is_dir():
        return set()
    return {
        _rel(root, path)
        for path in sorted(jobs_dir.glob("*.py"))
        if _calls(_parse(path), _GUARD_CALL)
    }


def checker_scripts(root, makefiles):
    """Every script `make check-all` reaches, and every script the catalogue
    of deterministic checks lists in its Script column."""
    rules = {}
    for _rel_path, text in makefiles:
        for target, (prereqs, recipe) in cs._make_rules(text).items():
            got = rules.setdefault(target, ([], []))
            got[0].extend(prereqs)
            got[1].extend(recipe)
    scripts = set(cs._scripts_reachable_from(rules, cs._CHECK_ALL))
    catalogue = Path(root) / cs._CATALOGUE_DOC
    if catalogue.is_file():
        table = cs._pipe_table(
            catalogue.read_text(encoding="utf-8"), _CATALOGUE_COLUMNS
        )
        if table is not None:
            header, cells = table
            at = header.index(_CATALOGUE_COLUMNS[0].lower())
            for raw in cells:
                if at < len(raw):
                    scripts.update(cs._PY_SCRIPT.findall(raw[at]))
    return {s for s in scripts if (Path(root) / s).is_file()}


def gate_tests(root):
    """Every gate test: each `test_*_gate.py` directly in the integration
    directory, among the files tests/source_tree.py `python_files` lists."""
    return {
        rel
        for rel in st.python_files(root)
        if posixpath.dirname(rel) == _GATE_TEST_DIR
        and fnmatch.fnmatch(posixpath.basename(rel), _GATE_TEST_NAME)
    }


def shared_script_modules(root):
    """Every scripts module another module imports, from the import graph
    tests/source_tree.py `import_edges` resolves through config/project.json
    `import_layers.search_roots`. An import from the tests directory does not
    make a module shared: a test imports what it judges."""
    files = st.python_files(root)
    search_roots = st.import_layers(root)["search_roots"]
    return {
        imported
        for importer, _line, imported in st.import_edges(root, files, search_roots)
        if imported.startswith(_SCRIPTS_DIR) and not importer.startswith(_TESTS_DIR)
    }


def derived_features(root):
    """({key: [reader paths]}, {make key: effect span}, {group: count}): every
    feature the tree itself declares, keyed the way the catalogue keys it --
    each check letter, each `## `-annotated make target with the label its
    help opens with, each checker and copier job, each gate test, each scripts
    module another module imports, each agent directory, each MCP server with
    a `__main__` guard, each model and runtime the registries list, each
    workflow and each agent skill."""
    root = Path(root)
    readers, labels, counts = {}, {}, {}

    def add(group, found):
        counts[group] = len(found)
        readers.update(found)

    checker = _rel(root, cs.__file__)
    add("check", {_CHECK_KEY % letter: [checker] for letter, _ in cs.CHECKS})
    warnings = []
    makefiles = cs.walk_makefiles(str(root), warnings.append)
    make = {}
    for rel_path, text in makefiles:
        for rule in cs.make_target_rules(text):
            if rule.help is None:
                continue
            key = _MAKE_KEY % rule.target
            make[key] = [rel_path]
            found = cs.parse_effect_labels(rule.help)[0]
            labels[key] = "[%s]" % ",".join(found) if found else None
    add("make target", make)
    add("checker", {s: [s] for s in checker_scripts(root, makefiles)})
    add("copier job", {s: [s] for s in copier_jobs(root)})
    add(_GATE_TEST_GROUP, {s: [s] for s in gate_tests(root)})
    add(_SHARED_GROUP, {s: [s] for s in shared_script_modules(root)})
    agents = root / _AGENTS_DIR
    add(
        "agent",
        {
            "%s/%s/" % (_AGENTS_DIR, d.name): ["%s/%s" % (_AGENTS_DIR, d.name)]
            for d in (sorted(agents.iterdir()) if agents.is_dir() else [])
            if d.is_dir() and not d.name.startswith(("_", "."))
        },
    )
    mcp = root / _MCP_DIR
    add(
        "MCP server",
        {
            _rel(root, p): [_rel(root, p)]
            for p in (sorted(mcp.glob("*.py")) if mcp.is_dir() else [])
            if _has_main_guard(_parse(p))
        },
    )
    for prefix, module, lister in _REGISTRY_LISTS:
        mod = importlib.import_module(module)
        reader = _rel(root, mod.__file__)
        add(prefix, {"%s:%s" % (prefix, n): [reader] for n in getattr(mod, lister)()})
    flows = root / _WORKFLOW_DIR
    add(
        "workflow",
        {
            _rel(root, p): [_rel(root, p)]
            for p in (sorted(flows.iterdir()) if flows.is_dir() else [])
            if p.suffix in _WORKFLOW_SUFFIXES
        },
    )
    skills = root / _SKILLS_DIR
    add(
        "skill",
        {
            "%s/%s/" % (_SKILLS_DIR, d.name): ["%s/%s" % (_SKILLS_DIR, d.name)]
            for d in (sorted(skills.iterdir()) if skills.is_dir() else [])
            if d.is_dir()
        },
    )
    return readers, labels, counts


def feature_findings(doc, rows, readers, labels, exhaustive):
    """Every derived feature has a row, and each make target's row states the
    effect label its help opens with. A derived-shaped row the tree does not
    derive is a finding in the template (*exhaustive*); in a generated
    project it is one only when its Ships says `always`, because a row whose
    feature this project's answers pruned says so in Ships."""
    keyed = {row["key"]: row for row in rows}
    findings = [
        "%s: lists no row for `%s`" % (doc, key)
        for key in sorted(readers)
        if key not in keyed
    ]
    for row in rows:
        key = row["key"]
        if key in readers or not _is_derived_shape(key):
            continue
        if exhaustive:
            findings.append(
                "%s: `## %s` row `%s` names nothing the tree has"
                % (doc, row["section"], key)
            )
        elif _ships(row) == _ALWAYS:
            findings.append(
                "%s: `## %s` row `%s` names nothing this project has, yet Ships "
                "says always; say which answer ships it" % (doc, row["section"], key)
            )
    for key, label in sorted(labels.items()):
        row = keyed.get(key)
        if row is None:
            continue
        spans = [
            s
            for s in cs._BACKTICKED.findall(row[_FEATURE_KEY])
            if _EFFECT_SPAN.match(s)
        ]
        if spans != [label]:
            findings.append(
                "%s: row `%s` states the effect label %s; its `## ` help opens with %s"
                % (doc, key, ", ".join(spans) or "none", label)
            )
    return findings


def limits_findings(doc, rows):
    """Every row says where the feature stops or what it is not for."""
    return [
        "%s: `## %s` row `%s` has an empty `%s` cell"
        % (doc, row["section"], row["key"], _LIMITS)
        for row in rows
        if row[_LIMITS].strip().lower() in cs._EMPTY_CELLS
    ]


def ships_grammar_findings(doc, rows, questions):
    """Each Ships cell is `always`, `keel maintainers only` or `when
    <question>[=<value>]`; where copier.yml is readable (*questions* not None)
    the question is one it asks and the value one it offers (`ships_claim`)."""
    findings = []
    for row in rows:
        cell = _ships(row)
        if cell in (_ALWAYS, _MAINTAINERS):
            continue
        m = _SHIPS_WHEN.match(cell)
        if m is None:
            findings.append(
                "%s: row `%s` says Ships %r; write always, %s or when <question>[=<value>]"
                % (doc, row["key"], row["Ships"], _MAINTAINERS)
            )
        elif questions is not None:
            claim = ships_claim(cell, questions)
            if isinstance(claim, str):
                findings.append(
                    "%s: row `%s` says Ships %r: %s"
                    % (doc, row["key"], row["Ships"], claim)
                )
    return findings


def _relative_links(text):
    for line in cs._prose_lines(text):
        for m in cs._MD_LINK.finditer(line):
            target = (m.group(1) or m.group(2) or "").strip()
            if (
                target
                and not cs._URL_SCHEME.match(target)
                and not target.startswith("#")
            ):
                yield target


def excluded_link_findings(doc, text, exclude_conditions):
    """No relative link lands on a path copier.yml `_exclude`s under any
    answer: the catalogue ships to every project, and such a link would not
    resolve in the projects that lack the path (cite it as a code span)."""
    findings = []
    for target in _relative_links(text):
        rel_path = posixpath.normpath(
            posixpath.join(posixpath.dirname(doc), target.split("#", 1)[0])
        )
        covering = sorted(e for e in exclude_conditions if _covers(e, rel_path))
        if covering:
            findings.append(
                "%s: links to %s, which copier.yml excludes (%s); cite it as a code span"
                % (doc, target, ", ".join(covering))
            )
    return findings


def settings_link_findings(doc, rows, settings_rel, anchors):
    """A Settings cell that is not empty links into the settings reference,
    and every link it holds lands on one of that document's headings."""
    findings = []
    target = posixpath.relpath(settings_rel, posixpath.dirname(doc) or ".")
    for row in rows:
        cell = row[_SETTINGS_CELL]
        if cell.strip().lower() in cs._EMPTY_CELLS:
            continue
        links = [
            (m.group(1) or m.group(2) or "").strip() for m in cs._MD_LINK.finditer(cell)
        ]
        if not links:
            findings.append(
                "%s: row `%s` names settings without linking to %s"
                % (doc, row["key"], settings_rel)
            )
        for link in links:
            path, _, frag = link.partition("#")
            if path != target or frag not in anchors:
                findings.append(
                    "%s: row `%s` links %s, which is no heading of %s"
                    % (doc, row["key"], link, settings_rel)
                )
    return findings


# --- fixtures -------------------------------------------------------------


@pytest.fixture(scope="module")
def manifest():
    return load_manifest(_ROOT)


@pytest.fixture(scope="module")
def settings(manifest):
    """(relpath, text) of the settings reference the manifest names."""
    rel = entry_policy(manifest)["settings_reference"]
    path = _ROOT / rel
    if not path.is_file():
        raise DocDriftConfigError(
            "doc_drift.settings_reference names %s, which does not exist" % rel
        )
    return rel, path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sections(settings):
    return settings_sections(settings[1])


@pytest.fixture(scope="module")
def inventory():
    return copier_inventory(_ROOT)


def _is_template(inventory):
    return inventory is not None


def _all_rows(doc, sections):
    rows, findings = [], []
    for heading in json_configs():
        got, errs = section_rows(doc, sections, heading)
        rows += got
        findings += errs
    return rows, findings


# --- JSON keys ------------------------------------------------------------


def test_settings_rows_cover_every_json_key_path(settings, sections, inventory):
    doc, _text = settings
    headings = json_configs()
    findings = json_heading_findings(doc, sections, headings)
    for heading in headings:
        if heading not in sections:
            continue
        rows, errs = section_rows(doc, sections, heading)
        findings += errs
        source = _ROOT / heading
        if not source.is_file():
            findings.append(
                "%s: `## %s` names a file that does not exist" % (doc, heading)
            )
            continue
        paths = json_key_paths(json.loads(source.read_text(encoding="utf-8")))
        findings += json_row_findings(
            doc, heading, rows, paths, _is_template(inventory)
        )
    assert not findings, "\n".join(findings)


def test_a_json_config_without_its_section_is_one_finding(settings, sections):
    doc, _text = settings
    configs = json_configs()
    # Measured from the findings already there, so a real drift fails the
    # coverage test alone.
    base = len(json_heading_findings(doc, sections, configs))
    victim = next(c for c in reversed(configs) if c in sections)
    dropped = {h: b for h, b in sections.items() if h != victim}
    assert len(json_heading_findings(doc, dropped, configs)) == base + 1
    extra = dict(sections, **{"config/unread%s" % _JSON_SUFFIX: ""})
    assert len(json_heading_findings(doc, extra, configs)) == base + 1


def test_a_settings_key_listed_twice_is_one_finding(settings, sections):
    doc, _text = settings
    body = sections[_MAKE_HEADING]
    rows, findings = section_rows(doc, sections, _MAKE_HEADING)
    assert rows, findings
    line = _row_line(body, rows[-1]["key"])
    # The copy goes first, so a dict that kept the last row would keep the
    # real one and judge nothing wrong.
    copy = line.replace(rows[-1]["Default"], " `changed` ", 1)
    planted = body.replace(line, copy + "\n" + line, 1)
    got, found = section_rows(doc, {_MAKE_HEADING: planted}, _MAKE_HEADING)
    assert len(found) == len(findings) + 1, found
    assert [r["key"] for r in got] == [r["key"] for r in rows]


def _row_line(text, key):
    return next(
        ln
        for ln in text.split("\n")
        if ln.startswith("|") and _first_span(ln.split("|")[1]) == key
    )


def _single_leaf_path(paths, keys):
    """A path of two or more segments, listed by a row of its own literal key,
    that is its parent's only child of that depth, so a `<name>` row beside it
    overlaps it and nothing else."""
    for path in sorted(paths):
        if len(path) < 2 or _LIST_ELEMENT in path or ".".join(path) not in keys:
            continue
        siblings = [p for p in paths if len(p) == len(path) and p[:-1] == path[:-1]]
        if siblings == [path]:
            return path
    return None


def test_an_unlisted_or_doubly_listed_key_is_one_finding(settings, sections):
    doc, _text = settings
    candidates = []
    for heading in json_configs():
        if (_ROOT / heading).is_file():
            paths = json_key_paths(
                json.loads((_ROOT / heading).read_text(encoding="utf-8"))
            )
            rows, _ = section_rows(doc, sections, heading)
            victim = _single_leaf_path(paths, {row["key"] for row in rows})
            if victim:
                candidates.append((heading, paths, victim))
    assert candidates, "no key path to plant against -- zero items"
    heading, paths, victim = candidates[0]
    rows, _ = section_rows(doc, sections, heading)
    assert json_row_findings(doc, heading, rows, paths, True) == []
    key = ".".join(victim)
    line = _row_line(sections[heading], key)
    planted = {
        "dropped": sections[heading].replace(line + "\n", ""),
        "overlapped": sections[heading].replace(
            line,
            line
            + "\n"
            + line.replace("`%s`" % key, "`%s.<name>`" % ".".join(victim[:-1]), 1),
        ),
        "unknown": sections[heading].replace(
            line, line + "\n" + line.replace("`%s`" % key, "`%s.nope`" % victim[0], 1)
        ),
    }
    for label, section in planted.items():
        got, errs = section_rows(doc, {heading: section}, heading)
        findings = errs + json_row_findings(doc, heading, got, paths, True)
        assert len(findings) == 1, (label, findings)


def _render_manifest(answers, source):
    """*source*, the manifest's jinja twin, rendered under *answers* and
    parsed; a name the answers do not define raises (StrictUndefined)."""
    return json.loads(_jinja().from_string(source).render(**answers))


def _twin_source():
    return (_ROOT / _MANIFEST_TWIN).read_text(encoding="utf-8")


def manifest_renders(questions, source):
    """[(answers, key paths)] of *source* rendered under every answer set
    copier.yml allows (`answer_sets`)."""
    return [
        (answers, json_key_paths(_render_manifest(answers, source)))
        for answers in answer_sets(questions)
    ]


def rendered_findings(doc, heading, rows, questions, source):
    """Against *source* rendered under every answer set copier.yml allows:
    each path some render holds matches exactly one row; a row matching no
    rendered path ships to keel maintainers only, and a row that does not
    says so; a row matching a path of every render (not necessarily the same
    path: an open map may be empty in one and keyed in another) ships always;
    any other ships `when ...`, with a claim that holds for the render under each answer
    it names and excludes (`ships_value_findings`)."""
    renders = manifest_renders(questions, source)
    full = set().union(*(paths for _answers, paths in renders))
    minimal = set.intersection(*(set(paths) for _answers, paths in renders))
    if not minimal < full:
        return [
            "%s: `## %s`: no answer renders a key of its own -- zero items"
            % (doc, heading)
        ]
    findings = json_row_findings(doc, heading, rows, full, False)
    claimed = []
    for row in rows:
        segs = row_segments(row["key"])
        in_full = any(row_covers(segs, p) for p in full)
        # Per render, not over the intersection: an open map empty under one
        # answer (`e2e.exempt`) and keyed under another holds no path common
        # to both, yet its `<name>` row matches a path of every render.
        in_minimal = all(
            any(row_covers(segs, p) for p in paths) for _answers, paths in renders
        )
        want = _ALWAYS if in_minimal else (_WHEN if in_full else _MAINTAINERS)
        cell = _ships(row)
        if (want == _WHEN and not cell.startswith(_WHEN)) or (
            want != _WHEN and cell != want
        ):
            findings.append(
                "%s: `## %s` row `%s` says Ships %r; the rendered twin ships it %s"
                % (doc, heading, row["key"], row["Ships"], want.strip())
            )
        elif want == _WHEN:
            claimed.append(row)

    def ships_under(row, answers):
        paths = json_key_paths(_render_manifest(answers, source))
        return any(row_covers(row_segments(row["key"]), p) for p in paths)

    return findings + ships_value_findings(
        doc, heading, claimed, questions, ships_under
    )


def _gated_plant(source, questions):
    """*source* with one key no row names, gated on a choice added to the
    last multiselect question of *questions*: (planted source, questions with
    that choice)."""
    name = [n for n, spec in questions.items() if _is_multiselect(spec)][-1]
    choice = "%s_planted" % _choice_values(questions[name])[-1]
    planted = dict(questions)
    planted[name] = dict(
        questions[name], **{_CHOICES_KEY: [*_choice_values(questions[name]), choice]}
    )
    gate = '{%% if "%s" in %s %%}"%s_undocumented": 1,{%% endif %%}' % (
        choice,
        name,
        choice,
    )
    # After the opening brace's line: straight after the brace, `{{%` would
    # open a jinja expression.
    opening = source.index("\n", source.index("{")) + 1
    return source[:opening] + gate + source[opening:], planted


def test_settings_rows_cover_the_rendered_project_json(settings, sections, inventory):
    questions = copier_questions(_ROOT)
    if questions is None or not _is_template(inventory):
        pytest.skip(_TEMPLATE_ONLY)
    doc, _text = settings
    heading = _MANIFEST_TWIN[: -len(_TWIN_SUFFIX)]
    source = _twin_source()
    rows, findings = section_rows(doc, sections, heading)
    findings += rendered_findings(doc, heading, rows, questions, source)
    assert not findings, "\n".join(findings)
    # Twins: one row each of `when`, `always` and maintainers-only, given the
    # wrong Ships word.
    for word, wrong in (
        (_WHEN, _ALWAYS),
        (_ALWAYS, _WHEN + "x"),
        (_MAINTAINERS, _ALWAYS),
    ):
        victim = next(r for r in rows if _ships(r).startswith(word))
        flipped = [dict(r, Ships=wrong) if r is victim else r for r in rows]
        found = rendered_findings(doc, heading, flipped, questions, source)
        assert len(found) == 1, (word, found)
    # Twin: a `when` row whose claim names the excluded answer instead.
    victim = next(r for r in rows if _ships(r).startswith(_WHEN))
    name, _ships_under, other = ships_claim(victim["Ships"], questions)
    value = other[0][name]
    wrong = "when `%s` is `%s`" % (name, value) if isinstance(value, str) else None
    if wrong is None:
        wrong = "when `%s` is %s" % (name, json.dumps(value))
    flipped = [dict(r, Ships=wrong) if r is victim else r for r in rows]
    found = rendered_findings(doc, heading, flipped, questions, source)
    assert len(found) == 1, found
    # Twin: a key gated on a choice copier.yml newly offers is judged, because
    # the answer sets come from copier.yml; a name no answer defines raises.
    planted, more = _gated_plant(source, questions)
    found = rendered_findings(doc, heading, rows, more, planted)
    assert len(found) == 1, found
    jinja2 = optional_deps.importorskip("jinja2", extra="template")
    with pytest.raises(jinja2.UndefinedError):
        rendered_findings(
            doc, heading, rows, questions, "{% if unasked %}{% endif %}" + source
        )


def _leaf(sources, segments):
    """The value at *segments* in the first of *sources* that holds it, or
    _MISSING."""
    for data in sources:
        node = data
        for seg in segments:
            if not isinstance(node, dict) or seg not in node:
                node = _MISSING
                break
            node = node[seg]
        if node is not _MISSING:
            return node
    return _MISSING


def _json_span(span):
    """*span* parsed as a JSON list or object, else None."""
    try:
        value = json.loads(span)
    except ValueError:
        return None
    return value if isinstance(value, (dict, list)) else None


def json_default_findings(doc, heading, rows, sources):
    """Each row naming one literal key path states the value the first of
    *sources* holding that path has there: a scalar as one of the Default
    cell's code spans (a string bare, anything else as JSON), and a list or
    object as the cell's first code span when that span is JSON. A row with a
    `<name>` or `[]` segment names many values and is not judged; a section
    with no judged row is a finding (zero items)."""
    findings, judged = [], 0
    for row in rows:
        segs = row_segments(row["key"])
        if any(_WILDCARD.match(s) or s == _LIST_ELEMENT for s in segs):
            continue
        value = _leaf(sources, segs)
        if value is _MISSING:
            continue
        if isinstance(value, (dict, list)):
            stated = _json_span(_default_span(row) or "")
            if stated is None:
                continue
            judged += 1
            if stated != value:
                findings.append(
                    "%s: `## %s` row `%s` states Default %r; the file holds `%s`"
                    % (doc, heading, row["key"], row["Default"], json.dumps(value))
                )
            continue
        judged += 1
        want = value if isinstance(value, str) else json.dumps(value)
        if want not in _span_names(row["Default"]):
            findings.append(
                "%s: `## %s` row `%s` states Default %r; the file holds `%s`"
                % (doc, heading, row["key"], row["Default"], want)
            )
    if not judged:
        findings.append(
            "%s: `## %s` judges no Default against the file -- zero items"
            % (doc, heading)
        )
    return findings


def default_sources(heading, questions):
    """What a JSON config holds by default: its jinja twin rendered with
    copier.yml's default answers when it has one, then the file itself (a
    key only another answer renders keeps keel's value)."""
    sources = []
    twin = _ROOT / (heading + _TWIN_SUFFIX)
    if twin.is_file():
        sources.append(
            _render_manifest(
                complete_answers(questions, {}), twin.read_text(encoding="utf-8")
            )
        )
    sources.append(json.loads((_ROOT / heading).read_text(encoding="utf-8")))
    return sources


def test_json_rows_state_the_default_value(settings, sections, inventory):
    questions = copier_questions(_ROOT)
    if questions is None or not _is_template(inventory):
        # A project's own values are its choices; the reference states keel's
        # defaults, which only the template's files and copier.yml hold.
        pytest.skip(_TEMPLATE_ONLY)
    doc, _text = settings
    findings, scalar, compound = [], None, None
    for heading in json_configs():
        rows, errs = section_rows(doc, sections, heading)
        sources = default_sources(heading, questions)
        findings += errs + json_default_findings(doc, heading, rows, sources)
        for row in rows:
            segs = row_segments(row["key"])
            value = _leaf(sources, segs)
            if any(_WILDCARD.match(s) or s == _LIST_ELEMENT for s in segs):
                continue
            if scalar is None and isinstance(value, (int, str)):
                scalar = (heading, rows, sources, row)
            if compound is None and _json_span(_default_span(row) or "") is not None:
                compound = (heading, rows, sources, row)
    assert not findings, "\n".join(findings)
    assert scalar and compound, "no scalar or JSON Default to plant -- zero items"
    # Twins: a scalar Default and a JSON Default each stating another value.
    for (heading, rows, sources, victim), wrong in (
        (scalar, "`%s_changed`" % _default_span(scalar[3])),
        (compound, "`%s`" % json.dumps([_default_span(compound[3])])),
    ):
        broken = [dict(r, Default=wrong) if r is victim else r for r in rows]
        found = json_default_findings(doc, heading, broken, sources)
        assert len(found) == 1, found


# --- copier questions -----------------------------------------------------


def test_settings_rows_list_every_copier_question(settings, sections, inventory):
    questions = copier_questions(_ROOT)
    if questions is None or not _is_template(inventory):
        pytest.skip(_TEMPLATE_ONLY)
    doc, _text = settings
    rows, findings = section_rows(doc, sections, _COPIER_HEADING)
    findings += copier_findings(doc, rows, questions, inventory)
    assert not findings, "\n".join(findings)
    dropped = [r for r in rows if r["key"] != sorted(questions)[-1]]
    assert len(copier_findings(doc, dropped, questions, inventory)) == 1
    unasked = "%s_unasked" % sorted(questions)[0]
    assert unasked not in questions
    extra = dict(rows[0], key=unasked)
    assert len(copier_findings(doc, [*rows, extra], questions, inventory)) == 1
    # Twin: a row that stops naming one path its answer prunes.
    pruning = [q for q in sorted(questions) if question_prunes(q, inventory)]
    assert pruning, "no question prunes a path -- zero items"
    name = pruning[0]
    span = "`%s`" % sorted(question_prunes(name, inventory))[0]
    unnamed = [
        {c: v.replace(span, "") for c, v in r.items()} if r["key"] == name else r
        for r in rows
    ]
    assert len(copier_findings(doc, unnamed, questions, inventory)) == 1


# --- make variables -------------------------------------------------------


def test_settings_rows_list_every_make_variable(settings, sections, inventory):
    doc, _text = settings
    assigned, referenced = make_variables(_ROOT)
    rows, findings = section_rows(doc, sections, _MAKE_HEADING)
    exhaustive = _is_template(inventory)
    findings += make_findings(doc, rows, assigned, referenced, exhaustive)
    assert not findings, "\n".join(findings)
    victim = sorted(referenced - set(assigned))[0]
    dropped = [r for r in rows if r["key"] != victim]
    assert len(make_findings(doc, dropped, assigned, referenced, exhaustive)) == 1
    unknown = "%s_UNSET" % victim
    assert unknown not in set(assigned) | referenced
    extra = dict(
        next(r for r in rows if r["key"] == victim), key=unknown, Ships=_ALWAYS
    )
    assert (
        len(make_findings(doc, [*rows, extra], assigned, referenced, exhaustive)) == 1
    )
    soft = sorted(n for n, ops in assigned.items() if any(op == "?=" for op, _ in ops))[
        0
    ]
    broken = [dict(r, Default="`changed`") if r["key"] == soft else r for r in rows]
    assert len(make_findings(doc, broken, assigned, referenced, exhaustive)) == 1


# --- environment variables ------------------------------------------------


def _assert_ships_twin(doc, heading, rows, readers, inventory):
    """Twin: the first row whose readers do not all ship, claimed always."""
    questions = copier_questions(_ROOT)
    conditions = inventory["exclude_conditions"]
    victim = next(
        r
        for r in rows
        if r["key"] in readers
        and ships_for_paths(readers[r["key"]], conditions, questions)[0] != _ALWAYS
    )
    flipped = [dict(r, Ships=_ALWAYS) if r is victim else r for r in rows]
    found = ships_findings(doc, heading, flipped, readers, conditions, questions)
    assert len(found) == 1, found


def test_settings_rows_list_every_environment_variable(
    settings, sections, inventory, manifest
):
    doc, _text = settings
    readers = env_readers(_ROOT, manifest)
    rows, findings = section_rows(doc, sections, _ENV_HEADING)
    exhaustive = _is_template(inventory)
    findings += env_findings(doc, rows, readers, exhaustive)
    if _is_template(inventory):
        findings += ships_findings(
            doc,
            _ENV_HEADING,
            rows,
            readers,
            inventory["exclude_conditions"],
            copier_questions(_ROOT),
        )
    assert not findings, "\n".join(findings)
    victim = sorted(readers)[0]
    dropped = [r for r in rows if r["key"] != victim]
    assert len(env_findings(doc, dropped, readers, exhaustive)) == 1
    # Twin: a row no reader names is a finding until its Type says `dynamic`.
    unread = "%s_UNREAD" % victim
    assert unread not in readers
    extra = dict(
        next(r for r in rows if r["key"] == victim),
        key=unread,
        Type="string",
        Ships=_ALWAYS,
    )
    assert len(env_findings(doc, [*rows, extra], readers, exhaustive)) == 1
    extra["Type"] = "string; %s" % _DYNAMIC
    assert env_findings(doc, [*rows, extra], readers, exhaustive) == []
    if _is_template(inventory):
        _assert_ships_twin(doc, _ENV_HEADING, rows, readers, inventory)


# --- command-line flags ---------------------------------------------------


def test_settings_rows_list_every_cli_flag(settings, sections, inventory):
    doc, _text = settings
    flags, findings = cli_flags(_ROOT)
    rows, errs = section_rows(doc, sections, _CLI_HEADING)
    exhaustive = _is_template(inventory)
    findings += errs + cli_findings(doc, rows, flags, exhaustive)
    if _is_template(inventory):
        findings += ships_findings(
            doc,
            _CLI_HEADING,
            rows,
            cli_readers(flags),
            inventory["exclude_conditions"],
            copier_questions(_ROOT),
        )
    assert not findings, "\n".join(findings)
    victim = sorted(flags)[0]
    dropped = [r for r in rows if r["key"] != victim]
    assert len(cli_findings(doc, dropped, flags, exhaustive)) == 1
    if _is_template(inventory):
        _assert_ships_twin(doc, _CLI_HEADING, rows, cli_readers(flags), inventory)
    unknown = "%s-undeclared" % victim
    assert unknown not in flags
    extra = dict(
        next(r for r in rows if r["key"] == victim), key=unknown, Ships=_ALWAYS
    )
    assert len(cli_findings(doc, [*rows, extra], flags, exhaustive)) == 1
    computed = sorted(k for k, v in flags.items() if _expected_default(v) == "")[0]
    blank = [dict(r, Default="—") if r["key"] == computed else r for r in rows]
    assert len(cli_findings(doc, blank, flags, exhaustive)) == 1
    bare = sorted(k for k, v in flags.items() if v is None)[0]
    claimed = [dict(r, Default="`x`") if r["key"] == bare else r for r in rows]
    assert len(cli_findings(doc, claimed, flags, exhaustive)) == 1
    literal = sorted(k for k, v in flags.items() if _expected_default(v))[0]
    broken = [dict(r, Default="`changed`") if r["key"] == literal else r for r in rows]
    assert len(cli_findings(doc, broken, flags, exhaustive)) == 1


# --- registry defaults ----------------------------------------------------


def test_registry_defaults_are_stated_against_the_manifest(
    settings, sections, manifest
):
    doc, _text = settings
    rows, findings = _all_rows(doc, sections)
    findings += registry_findings(doc, rows, manifest)
    assert not findings, "\n".join(findings)
    key = "%s.%s" % (_REGISTRIES[0][0], _DEFAULT_KEY)
    broken = [dict(r, Default="`changed`") if r["key"] == key else r for r in rows]
    assert len(registry_findings(doc, broken, manifest)) == 1
    # Twin: the row stops naming the registry constant that decides.
    constant = "%s.%s" % _REGISTRIES[0][1:]
    unnamed = [
        {c: v.replace(constant, "") for c, v in r.items()} if r["key"] == key else r
        for r in rows
    ]
    assert len(registry_findings(doc, unnamed, manifest)) == 1


# --- the feature catalogue ------------------------------------------------


@pytest.fixture(scope="module")
def features(manifest):
    """(relpath, text) of the feature catalogue the manifest names."""
    rel = entry_policy(manifest)["features_reference"]
    path = _ROOT / rel
    if not path.is_file():
        raise DocDriftConfigError(
            "doc_drift.features_reference names %s, which does not exist" % rel
        )
    return rel, path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def derived():
    return derived_features(_ROOT)


def _feature_rows(features):
    rows, findings = feature_rows(*features)
    assert rows, "\n".join(findings) or "no feature row -- zero items"
    return rows, findings


def test_the_feature_catalogue_lists_every_derived_feature(
    features, derived, manifest, inventory
):
    doc, _text = features
    readers, labels, counts = derived
    assert readers, "no feature derived from the tree -- zero items"
    rows, findings = _feature_rows(features)
    exhaustive = _is_template(inventory)
    if exhaustive:
        findings += [
            "%s: no %s derived from the template -- zero items" % (doc, group)
            for group, count in sorted(counts.items())
            if not count
        ]
        import conflict_guard  # noqa: PLC0415

        jobs = copier_jobs(_ROOT)
        expected = set(inventory["scripts"]) | {conflict_guard.FINISH_SCRIPT}
        if jobs != expected:
            findings.append(
                "the scripts that run %s (%s) are not copier.yml's jobs plus %s (%s)"
                % (
                    _GUARD_CALL,
                    ", ".join(sorted(jobs)),
                    conflict_guard.FINISH_SCRIPT,
                    ", ".join(sorted(expected)),
                )
            )
    findings += feature_findings(doc, rows, readers, labels, exhaustive)
    assert not findings, "\n".join(findings)


def test_a_feature_dropped_invented_or_mislabelled_is_one_finding(
    features, derived, manifest, inventory
):
    doc, _text = features
    readers, labels, _counts = derived
    rows, _ = _feature_rows(features)
    exhaustive = _is_template(inventory)
    # Each twin is measured from the findings the catalogue already has, so a
    # project's own drift fails the catalogue test alone, not this one too.
    base = len(feature_findings(doc, rows, readers, labels, exhaustive))
    victim = _MAKE_KEY % entry_policy(manifest)["gate_target"]
    assert victim in readers, "the gate target %s is no annotated target" % victim
    dropped = [r for r in rows if r["key"] != victim]
    assert len(feature_findings(doc, dropped, readers, labels, exhaustive)) == base + 1
    row = next(r for r in rows if r["key"] == victim)
    invented = _MAKE_KEY % ("%s-undeclared" % entry_policy(manifest)["gate_target"])
    assert invented not in readers
    extra = dict(row, key=invented, Ships=_ALWAYS)
    assert (
        len(feature_findings(doc, [*rows, extra], readers, labels, exhaustive))
        == base + 1
    )
    # Twin: in a generated project a row Ships prunes is not a finding; in the
    # template every derived-shaped row must name something. The strict judge is
    # measured as a delta: a generated project already holds rows its answers
    # pruned, which the strict judge counts and the project's own judge does not.
    pruned = dict(extra, Ships="when x")
    assert feature_findings(doc, [*rows, pruned], readers, labels, False) == []
    strict = len(feature_findings(doc, rows, readers, labels, True))
    assert (
        len(feature_findings(doc, [*rows, pruned], readers, labels, True)) == strict + 1
    )
    label = labels[victim]
    other = "[local]" if label != "[local]" else "[tree]"
    flipped = [
        dict(r, Feature=r[_FEATURE_KEY].replace("`%s`" % label, "`%s`" % other))
        if r is row
        else r
        for r in rows
    ]
    assert len(feature_findings(doc, flipped, readers, labels, exhaustive)) == base + 1


def _write(root, relpath, text):
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_gate_tests_and_shared_script_modules_are_derived(tmp_path):
    # A planted tree: one module a script imports, one a non-script module
    # imports by its dotted name, one only a test imports, one nobody imports,
    # and gate-shaped test files inside and outside the gate directory.
    _write(
        tmp_path,
        st.CONFIG,
        json.dumps(
            {
                st.LAYERS_BLOCK: {
                    "search_roots": ["", "scripts/", "tests/"],
                    "order": [["scripts"], ["models"], ["tests"]],
                }
            }
        ),
    )
    _write(tmp_path, "scripts/lib.py", "X = 1\n")
    _write(tmp_path, "scripts/user.py", "import lib\n")
    _write(tmp_path, "scripts/kernel.py", "Y = 1\n")
    _write(tmp_path, "models/adapter.py", "from scripts import kernel\n")
    _write(tmp_path, "scripts/test_only.py", "Z = 1\n")
    _write(tmp_path, "tests/unit/test_x.py", "import test_only\n")
    _write(tmp_path, "scripts/alone.py", "W = 1\n")
    _write(tmp_path, "tests/integration/test_a_gate.py", "\n")
    _write(tmp_path, "tests/integration/test_b.py", "\n")
    _write(tmp_path, "tests/integration/sub/test_c_gate.py", "\n")
    _write(tmp_path, "tests/unit/test_d_gate.py", "\n")
    assert gate_tests(tmp_path) == {"tests/integration/test_a_gate.py"}
    assert shared_script_modules(tmp_path) == {"scripts/lib.py", "scripts/kernel.py"}


def test_every_gate_test_and_shared_script_module_has_a_row(
    features, derived, inventory
):
    doc, _text = features
    readers, labels, counts = derived
    rows, _ = _feature_rows(features)
    exhaustive = _is_template(inventory)
    groups = {_GATE_TEST_GROUP: gate_tests(_ROOT)}
    groups[_SHARED_GROUP] = shared_script_modules(_ROOT)
    base = len(feature_findings(doc, rows, readers, labels, exhaustive))
    for group, members in sorted(groups.items()):
        assert members, "no %s derived from the tree -- zero items" % group
        assert counts.get(group) == len(members), (group, counts.get(group))
        assert members <= set(readers), sorted(members - set(readers))
        # Twin: a member whose row is dropped is exactly one more finding.
        victim = sorted(members)[0]
        dropped = [r for r in rows if r["key"] != victim]
        assert len(dropped) == len(rows) - 1, "%s has no row to drop" % victim
        found = feature_findings(doc, dropped, readers, labels, exhaustive)
        assert len(found) == base + 1, found


def _note_paragraph(text, opening):
    """The paragraph of *text* that opens with *opening*, as one line."""
    lines = text.splitlines()
    for at, line in enumerate(lines):
        if line.startswith(opening):
            para = []
            for rest in lines[at:]:
                if not rest.strip():
                    break
                para.append(rest.strip())
            return " ".join(para)
    return None


# A cardinal written in words: the note says where the set is derived, so a
# count in it, in words or as the derived size, is a second, unchecked copy of
# the derivation. Digits in general are not refused, since the note cites an
# ADR number.
_COUNT_WORDS = [
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
    "twenty",
]


def test_the_scripts_note_cites_its_derivation(features, derived):
    doc, _text = features
    _readers, _labels, counts = derived
    text = (_ROOT / cs._CONVENTIONS_DOC).read_text(encoding="utf-8")
    note = _note_paragraph(text, _SCRIPTS_NOTE)
    assert note is not None, "%s has no paragraph opening %r" % (
        cs._CONVENTIONS_DOC,
        _SCRIPTS_NOTE,
    )
    me = _rel(_ROOT, __file__)
    for needed in (me, derived_features.__name__, doc, _SHARED_SECTION):
        assert needed in note, "the scripts note does not name %r: %s" % (
            needed,
            note,
        )
    words = "".join(c if c.isalnum() else " " for c in note.lower()).split()
    size = str(counts[_SHARED_GROUP])
    counted = sorted({w for w in words if w in _COUNT_WORDS or w == size})
    assert not counted, "the scripts note states a count %s: %s" % (counted, note)
    sections = {heading for heading, _body in cs._sections(_text)}
    assert _SHARED_SECTION in sections, "%s has no `## %s` section" % (
        doc,
        _SHARED_SECTION,
    )


def test_every_feature_row_states_its_limits(features):
    doc, _text = features
    rows, findings = _feature_rows(features)
    findings += limits_findings(doc, rows)
    assert not findings, "\n".join(findings)
    victim = rows[0]["key"]
    blank = [dict(r, **{_LIMITS: " — "}) if r["key"] == victim else r for r in rows]
    assert len(limits_findings(doc, blank)) == 1


def test_every_ships_cell_is_well_formed(features):
    doc, _text = features
    rows, findings = _feature_rows(features)
    questions = copier_questions(_ROOT)
    findings += ships_grammar_findings(doc, rows, questions)
    assert not findings, "\n".join(findings)
    victim = rows[0]["key"]
    broken = [dict(r, Ships="sometimes") if r["key"] == victim else r for r in rows]
    assert len(ships_grammar_findings(doc, broken, questions)) == 1
    if questions is not None:
        unasked = sorted(questions)[0] + "_unasked"
        assert unasked not in questions
        wrong = [
            dict(r, Ships=_WHEN + unasked) if r["key"] == victim else r for r in rows
        ]
        assert len(ships_grammar_findings(doc, wrong, questions)) == 1
        # Twin: a value the question does not offer.
        offered = next(
            n for n, spec in sorted(questions.items()) if _choice_values(spec)
        )
        unoffered = "%s-unoffered" % _choice_values(questions[offered])[0]
        wrong = [
            dict(r, Ships="%s%s=%s" % (_WHEN, offered, unoffered))
            if r["key"] == victim
            else r
            for r in rows
        ]
        assert len(ships_grammar_findings(doc, wrong, questions)) == 1


def test_feature_ships_match_copier_excludes(features, derived, inventory):
    if not _is_template(inventory):
        pytest.skip(_TEMPLATE_ONLY)
    doc, text = features
    readers, _labels, _counts = derived
    rows, findings = _feature_rows(features)
    conditions = inventory["exclude_conditions"]
    questions = copier_questions(_ROOT)
    for section in sorted({r["section"] for r in rows}):
        findings += ships_findings(
            doc,
            section,
            [r for r in rows if r["section"] == section],
            readers,
            conditions,
            questions,
        )
    findings += excluded_link_findings(doc, text, conditions)
    assert not findings, "\n".join(findings)
    _assert_ships_twin(doc, rows[0]["section"], rows, readers, inventory)
    # Twin: a derived row whose `when` names another answer than the one that
    # ships it, which the question does offer.
    victim = next(
        r
        for r in rows
        if r["key"] in readers
        and _ships(r).startswith(_WHEN)
        and _SHIPS_CLAUSE.match(_ships(r)).group(4)
    )
    name, _yes, other = ships_claim(victim["Ships"], questions)
    value = other[0][name]
    named = value[0] if isinstance(value, list) else value
    wrong = [
        dict(r, Ships="%s%s=%s" % (_WHEN, name, str(named).lower()))
        if r is victim
        else r
        for r in rows
    ]
    found = ships_findings(
        doc, victim["section"], wrong, readers, conditions, questions
    )
    assert len(found) == 1, found
    pruned = sorted(e for e in conditions if (_ROOT / e).is_file())[0]
    planted = text + "\n[pruned](%s)\n" % posixpath.relpath(
        pruned, posixpath.dirname(doc)
    )
    assert len(excluded_link_findings(doc, planted, conditions)) == 1


def test_every_settings_link_lands_on_a_heading(features, settings):
    doc, _text = features
    settings_rel, settings_text = settings
    anchors = cs._anchors(settings_text)
    assert anchors, "%s has no heading -- zero items" % settings_rel
    rows, findings = _feature_rows(features)
    linked = [
        r for r in rows if r[_SETTINGS_CELL].strip().lower() not in cs._EMPTY_CELLS
    ]
    assert linked, "%s: no row names a setting -- zero items" % doc
    findings += settings_link_findings(doc, rows, settings_rel, anchors)
    assert not findings, "\n".join(findings)
    victim = linked[0]["key"]
    target = posixpath.relpath(settings_rel, posixpath.dirname(doc))
    broken = [
        dict(r, Settings="[x](%s#no-such-heading)" % target)
        if r["key"] == victim
        else r
        for r in rows
    ]
    assert len(settings_link_findings(doc, broken, settings_rel, anchors)) == 1
    unlinked = [
        dict(r, Settings="`some.key`") if r["key"] == victim else r for r in rows
    ]
    assert len(settings_link_findings(doc, unlinked, settings_rel, anchors)) == 1
