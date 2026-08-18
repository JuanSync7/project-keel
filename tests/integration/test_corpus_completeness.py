"""
title: Integration — every CODE_ROOTS module is corpus-visible with an authored header
kind: tests
layer: n/a
summary: The completeness theorem check_O and the single-sourced walk buy together, proved over the REAL tree: a fresh corpus build indexes EVERY .py under check_structure.CODE_ROOTS as a module node whose title and summary are explicit and authored — no silently dropped modules (build_corpus skips undocumented ones), no filename-fallback titles mislabeled authored, and no second scope list to drift (runtimes/ was invisible to every agent for exactly that reason, from 906a42b until ADR-0008).
"""

import os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "jobs"))

import build_corpus as bc  # noqa: E402
import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def fresh_nodes():
    """One fresh build for the whole module — the corpus is deterministic
    (check_corpus proves that), so sharing it loses nothing."""
    return bc.build_corpus(str(_ROOT))["nodes"]


def _disk_modules():
    out = set()
    for croot in cs.CODE_ROOTS:
        base = _ROOT / croot
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(str(base)):
            dirnames[:] = [d for d in dirnames if d not in cs.IGNORE_DIRS]
            for f in filenames:
                if f.endswith(".py"):
                    out.add(os.path.relpath(os.path.join(dirpath, f), str(_ROOT)))
    return out


def test_the_corpus_scope_is_the_gates_scope():
    """build_corpus must not keep a private copy of the walk: its re-typed
    CODE_ROOTS omitted runtimes/ and six modules vanished from every corpus
    query while make verify stayed green. One list, imported."""
    assert list(bc.CODE_ROOTS) == list(cs.CODE_ROOTS)
    assert set(bc.IGNORE_DIRS) == set(cs.IGNORE_DIRS)


def test_every_module_on_disk_is_a_corpus_node(fresh_nodes):
    mods = {n["path"] for n in fresh_nodes if n["kind"] == "module"}
    missing = sorted(_disk_modules() - mods)
    assert not missing, "modules invisible to agents: %s" % missing


def test_every_module_node_has_an_explicit_authored_header(fresh_nodes):
    """No fallback titles, no accidental first-line summaries: what the agent
    reads as 'authored' was actually written by someone."""
    for n in fresh_nodes:
        if n["kind"] != "module":
            continue
        assert n["summary"] and n["summary_source"] == "authored", n["path"]
        assert n["title"] and not n["title"].endswith(".py"), (
            "filename-fallback title on %s" % n["path"]
        )


def test_every_exported_symbol_node_has_an_authored_summary(fresh_nodes):
    """check_E's promotion, observed from the artifact side: a symbol node with
    an empty summary means an agent gets a name with no meaning attached."""
    bad = [
        "%s::%s" % (n["path"], n["title"])
        for n in fresh_nodes
        if n["kind"] == "symbol" and not n["summary"]
    ]
    assert not bad, bad
