"""
title: Wiki navigator brain
layer: backend
public_api: no
summary: Plan: deterministic retrieval (query_corpus) -> synthesize a cited answer; on a Runtime.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass

from models import get_model
from runtimes import END, MODEL_CALL, READ_ONLY, Edge, Plan, Step, get_runtime

__all__ = ["answer", "Answer", "Citation"]

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CORPUS = os.path.join("wiki", "corpus.json")
_VISIBLE = ("public", "internal")   # confidential/restricted are not surfaced


@dataclass(frozen=True)
class Citation:
    """One traceable source behind an answer."""
    node_id: str
    path: str
    summary_source: str    # "authored" | "generated" — caller can weight authored higher
    owner: str             # resolved owner ("" if unowned)
    owner_source: str      # "marker" | "frontmatter" | "inherited" | "none"


@dataclass(frozen=True)
class Answer:
    """An answer plus full provenance."""
    text: str              # the answer; in dry-run, the prompt that WOULD be sent
    citations: tuple       # tuple[Citation, ...] — every source is traceable
    dry_run: bool


def _run(args):
    """Invoke a repo script via its CLI with the SAME interpreter running us."""
    proc = subprocess.run([sys.executable] + args, cwd=_REPO,
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def _system_prompt():
    with open(os.path.join(os.path.dirname(__file__), "prompt.md"), encoding="utf-8") as fh:
        return fh.read()


def _answer_prompt(question, nodes):
    ctx = "\n".join(
        "- [%s] %s (%s): %s" % (n.get("summary_source") or "gap", n.get("node_id"),
                                n.get("path"), n.get("summary") or n.get("text_excerpt", ""))
        for n in nodes)
    return (_system_prompt()
            + "\n\n# Question\n%s\n\n# Retrieved context (cite by node_id)\n%s\n"
            % (question, ctx or "(nothing retrieved)"))


# --- plan steps ----------------------------------------------------------------
# Retrieval is deterministic and read-only, so it ALWAYS runs (even in dry-run)
# and `citations` is populated regardless. Only the synthesis is a model call,
# so the runtime gates it on execute=True. A failed retrieval fails closed
# (raises) rather than handing the model an empty, hallucination-prone context.

def _retrieve(state):
    """Read-only: query_corpus, fail closed on error, filter by visibility, cite."""
    rc, out, err = _run(["scripts/query_corpus.py", state["question"],
                         "--corpus", state["corpus"],
                         "--max-nodes", str(state["max_nodes"])])
    if rc != 0:
        raise RuntimeError("query_corpus failed (rc=%d): %s" % (rc, err.strip()))
    try:
        hits = json.loads(out) if out.strip() else []
    except ValueError:
        hits = []
    visible = [h for h in hits if (h.get("visibility") or "internal") in _VISIBLE]
    citations = tuple(
        Citation(node_id=h.get("node_id", ""), path=h.get("path", ""),
                 summary_source=h.get("summary_source") or "",
                 owner=h.get("owner") or "",
                 owner_source=h.get("owner_source") or "none")
        for h in visible)
    return {"citations": citations, "prompt": _answer_prompt(state["question"], visible)}


def _synthesize(state):
    """Model-call: synthesize the answer over the retrieved, visible nodes."""
    return {"answer_text": get_model(state.get("model")).run(state["prompt"]).strip()}


_PLAN = Plan(
    name="wiki_answer",
    entry="retrieve",
    steps=(
        Step("retrieve", READ_ONLY, _retrieve),
        Step("synthesize", MODEL_CALL, _synthesize),
    ),
    edges=(
        Edge("retrieve", "synthesize"),
        Edge("synthesize", END),
    ),
)


def answer(question, *, execute=False, model=None, corpus=None, max_nodes=8, runtime=None):
    """Deterministically retrieve candidate nodes (tree+links, via query_corpus),
    then synthesize an answer over them. The pipeline is a neutral ``Plan`` run
    on a ``Runtime`` (default the stdlib ``inprocess`` engine; ``runtime``
    selects another). Retrieval always runs, so ``citations`` is populated even
    in dry-run; only the model call is gated by ``execute``. Honors node
    ``visibility``. Model via ``models.get_model(model)`` -- never a provider name.
    """
    init = {"question": question, "model": model,
            "corpus": corpus or _CORPUS, "max_nodes": max_nodes}
    st = get_runtime(runtime).run(_PLAN, init, execute=execute).state
    citations = st.get("citations", ())
    if execute:
        return Answer(text=st["answer_text"], citations=citations, dry_run=False)
    return Answer(text=st.get("prompt", ""), citations=citations, dry_run=True)
