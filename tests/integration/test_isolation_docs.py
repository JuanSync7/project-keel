"""
title: Integration — the docs state the isolation guard as the code holds it
kind: tests
layer: n/a
summary: The documents a reader meets the isolation guard in are held to the guard. The rules and the README of the guard's own directory, and the guide the feature catalogue's guard row links as its deep doc, each name as a code span the guard module, every config key it reads (each scripts/config_loader.py `KEYS` row under the scratch root's top-level key), each axis it judges, and each conftest fixture that calls into it. The symptom table of config/project.json `doc_drift.limits_guide` shows, as code spans, the guard's failure line and its unused-exemption line, each rendered from the guard with `<field>` placeholders, and quotes the words of each scratch-root refusal the guard raises. Every expected item is derived from the guard, the loader, the conftest or the catalogue, never typed here; a derived set of zero items fails, and each rule has a fault-injection twin that removes one item and asserts exactly one finding. Not a writer: it reads the tree.
"""

import ast
import re
import sys
from pathlib import Path

import pytest

import isolation_guard

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402
import config_loader  # noqa: E402
from test_doc_drift import _backticked, entry_policy, load_manifest  # noqa: E402
from test_reference_drift import feature_rows  # noqa: E402

pytestmark = pytest.mark.integration

_GUARD = Path(isolation_guard.__file__).resolve()
_CONFTEST = _GUARD.parent / "conftest.py"
# The guard directory's own documents, by the names check_B requires of a
# labelled directory.
_DIR_DOCS = ("AGENT.md", "README.md")
_SYMPTOM_HEADER = "| Symptom |"
# A markdown link's target: the deep-doc cell of a catalogue row is one link.
_LINK = re.compile(r"\]\(([^)#\s]+)")
# The edges a quoted chunk is cut at: the separators the refusal line puts
# between its value, its reason and what it accepts.
_EDGES = " :;,()'\"/."


def _rel(path):
    return Path(path).resolve().relative_to(_ROOT).as_posix()


def required_spans():
    """Every code span a document that states the guard must hold: the guard
    module's path, each loader key under the scratch root's top-level key,
    each axis, and each conftest fixture whose body calls into the guard."""
    top = isolation_guard.SCRATCH_KEY[0]
    keys = sorted(".".join(k.path) for k in config_loader.KEYS if k.path[0] == top)
    tree = ast.parse(_CONFTEST.read_text(encoding="utf-8"))
    fixtures = sorted(
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and any("fixture" in ast.dump(d) for d in node.decorator_list)
        and any(
            isinstance(n, ast.Attribute)
            and isinstance(n.value, ast.Name)
            and n.value.id == isolation_guard.__name__
            for n in ast.walk(node)
        )
    )
    assert keys, "no %s key in config_loader.KEYS -- zero items" % top
    assert fixtures, "no conftest fixture calls into the guard -- zero items"
    return [_rel(_GUARD)] + keys + list(isolation_guard.AXES) + fixtures


def span_findings(doc, text, required):
    named = _backticked(text)
    return [
        "%s: does not name `%s`, which the isolation guard holds" % (doc, item)
        for item in required
        if item not in named
    ]


def reach_docs():
    """{relpath: text} for the guard directory's rules and README and for the
    guide the catalogue's guard row names as its deep doc."""
    docs = [_GUARD.parent / name for name in _DIR_DOCS]
    catalogue = _ROOT / entry_policy(load_manifest(_ROOT))["features_reference"]
    rows, findings = feature_rows(
        _rel(catalogue), catalogue.read_text(encoding="utf-8")
    )
    assert not findings, findings
    matches = [r for r in rows if r["key"] == isolation_guard.__name__]
    assert len(matches) == 1, "%s: %d rows are keyed `%s`" % (
        _rel(catalogue),
        len(matches),
        isolation_guard.__name__,
    )
    targets = _LINK.findall(matches[0]["Deep doc"])
    assert len(targets) == 1, matches[0]["Deep doc"]
    target = targets[0]
    docs.append(catalogue.parent / target)
    return {_rel(d): d.read_text(encoding="utf-8") for d in docs}


def symptom_section(text):
    found = [
        "\n".join(body)
        for _, body in cs._sections(text)
        if any(line.startswith(_SYMPTOM_HEADER) for line in body)
    ]
    assert len(found) == 1, "%d sections hold a symptom table" % len(found)
    return found[0]


def failure_lines():
    """The guard's failure line and its unused-exemption line, with a
    `<field>` placeholder for each field."""
    fields = ("event", "target", "axis", "value", "nodeid", "phase", "tier")
    violation = isolation_guard.Violation(*("<%s>" % f for f in fields))
    return [violation.message(), isolation_guard.unused_line("<axis>", "<nodeid>")]


def refusal_chunks():
    """The words of each scratch-root refusal: each refused root is passed in
    the variable the key's row names, and every run of two or more words
    between the value, the directories and the separators is a chunk."""
    (key,) = config_loader.rows(isolation_guard.SCRATCH_KEY)
    systemp = "/<system temp>"
    checkout = str(_ROOT)
    values = ("<value>", systemp + "/<value>", checkout + "/<value>")
    chunks = []
    for value in values:
        with pytest.raises(config_loader.ConfigError) as refused:
            isolation_guard.scratch_root(checkout, {key.env: value}, systemp)
        cuts = sorted((repr(value), systemp, checkout), key=len, reverse=True)
        edges = re.compile("|".join(re.escape(c) for c in cuts) + "|; ")
        for line in refused.value.lines:
            for chunk in edges.split(line):
                chunk = chunk.strip(_EDGES)
                if len(chunk.split()) >= 2 and chunk not in chunks:
                    chunks.append(chunk)
    # A refusal that said nothing would make the symptom rule vacuous.
    assert len(chunks) >= 4, chunks
    assert any(".".join(isolation_guard.SCRATCH_KEY) in c for c in chunks), chunks
    return chunks


def symptom_findings(guide, section):
    named = _backticked(section)
    findings = [
        "%s: the symptom table does not show `%s`" % (guide, line)
        for line in failure_lines()
        if line not in named
    ]
    findings.extend(
        "%s: the symptom table does not quote %r" % (guide, chunk)
        for chunk in refusal_chunks()
        if chunk not in section
    )
    return findings


def test_each_document_that_states_the_guard_names_what_it_holds():
    required = required_spans()
    docs = reach_docs()
    assert len(docs) == len(_DIR_DOCS) + 1, sorted(docs)
    findings = [
        f for doc, text in docs.items() for f in span_findings(doc, text, required)
    ]
    assert not findings, "\n".join(findings)


@pytest.mark.parametrize("which", range(len(_DIR_DOCS) + 1))
def test_dropping_the_guard_module_from_a_document_reds_it(which):
    required = required_spans()
    doc, text = sorted(reach_docs().items())[which]
    item = required[0]
    assert span_findings(doc, text, required) == [], "the unplanted doc must be clean"
    planted = text.replace("`%s`" % item, item)
    assert planted != text
    findings = span_findings(doc, planted, required)
    assert len(findings) == 1 and item in findings[0], findings


def test_the_troubleshooting_guide_shows_each_failure_the_guard_writes():
    guide = entry_policy(load_manifest(_ROOT))["limits_guide"]
    section = symptom_section((_ROOT / guide).read_text(encoding="utf-8"))
    findings = symptom_findings(guide, section)
    assert not findings, "\n".join(findings)


@pytest.mark.parametrize("fault", ["violation", "unused", "refusal"])
def test_dropping_a_failure_from_the_troubleshooting_guide_reds_it(fault):
    guide = entry_policy(load_manifest(_ROOT))["limits_guide"]
    section = symptom_section((_ROOT / guide).read_text(encoding="utf-8"))
    assert symptom_findings(guide, section) == [], "the unplanted guide must be clean"
    violation, unused = failure_lines()
    planted = {
        "violation": lambda s: s.replace("`%s`" % violation, ""),
        "unused": lambda s: s.replace("`%s`" % unused, ""),
        "refusal": lambda s: s.replace(refusal_chunks()[-1], ""),
    }[fault](section)
    assert planted != section
    findings = symptom_findings(guide, planted)
    assert len(findings) == 1, findings
