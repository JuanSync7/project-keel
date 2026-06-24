"""
title: Index enforcer brain
layer: backend
public_api: no
summary: Plan: gate -> build -> link -> report -> (durable fill loop) -> commit; run on a neutral Runtime.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass

from models import get_model
from runtimes import (
    END,
    MODEL_CALL,
    READ_ONLY,
    WRITES,
    Edge,
    FileCheckpointer,
    Plan,
    Step,
    get_runtime,
)

__all__ = ["enforce", "EnforceReport"]

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CORPUS = os.path.join("wiki", "corpus.json")
_CKPT_DIR = os.path.join("wiki", ".runtime")   # gitignored; durable fill snapshots


@dataclass(frozen=True)
class EnforceReport:
    """Convention + coverage + accountability gaps found while indexing."""
    structure_errors: tuple
    structure_warnings: tuple
    corpus_path: str
    nodes: int
    summary_gaps: tuple
    owner_gaps: tuple
    gaps_filled: int
    dry_run: bool


def _run(args):
    """Invoke a repo script via its CLI (tools are consumed as CLIs, never imported).

    Uses the SAME interpreter running this agent (sys.executable), so the tools
    run under a compatible Python rather than a hardcoded 'python3' on PATH.
    """
    proc = subprocess.run([sys.executable] + args, cwd=_REPO,
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def _load_corpus(root):
    path = os.path.join(root, _CORPUS)
    if not os.path.exists(path):
        return {"nodes": []}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _system_prompt():
    with open(os.path.join(os.path.dirname(__file__), "prompt.md"), encoding="utf-8") as fh:
        return fh.read()


def _gap_prompt(node):
    return (_system_prompt()
            + "\n\n# Task\nWrite ONE plain sentence summarizing the node below, "
            "using only its own text. Output the sentence and nothing else.\n\n"
            "title: %s\npath: %s\n---\n%s\n"
            % (node.get("title", ""), node.get("path", ""), node.get("text_excerpt", "")))


def _ungapped(corpus):
    """Nodes still missing a summary_source, in corpus order (the fill work-list)."""
    return [n for n in corpus.get("nodes", []) if not n.get("summary_source")]


# --- plan steps: each returns a dict merged into the run state -----------------
# Deterministic logic stays in pure-stdlib scripts/ doers invoked as CLIs; these
# steps orchestrate them. The model is reached only in the one MODEL_CALL step,
# so the runtime skips it (and the WRITES steps) unless execute=True.

def _gate(state):
    """Read-only: run check_structure and capture its errors/warnings."""
    _, out, _ = _run(["scripts/check_structure.py"])
    return {
        "s_errors": tuple(ln[6:] for ln in out.splitlines() if ln.startswith("ERROR ")),
        "s_warnings": tuple(ln[6:].strip() for ln in out.splitlines() if ln.startswith("WARN  ")),
    }


def _build(state):
    """Writes: (re)build the wiki corpus tree."""
    _run(["scripts/jobs/build_corpus.py", "--out", _CORPUS])
    return None


def _link(state):
    """Writes: add deterministic entity/keyword link edges to the corpus."""
    _run(["scripts/jobs/link_corpus.py", "--corpus", _CORPUS])
    return None


def _report(state):
    """Read-only: enumerate summary gaps (no authored summary) and owner gaps."""
    corpus = _load_corpus(state["root"])
    nodes = corpus.get("nodes", [])
    summary_gaps = tuple(n["node_id"] for n in _ungapped(corpus))
    # Owner gaps come from the declared accountability_report tool (its CLI),
    # not a re-implemented predicate here -- read-only, so safe in dry-run too.
    _, ar_out, _ = _run(["scripts/accountability_report.py", "--corpus", _CORPUS, "--json"])
    try:
        owner_gaps = tuple(n["node_id"] for n in json.loads(ar_out)) if ar_out.strip() else ()
    except ValueError:
        owner_gaps = ()   # no corpus yet (tool prints a notice, not JSON)
    return {"corpus": corpus, "nodes": nodes,
            "summary_gaps": summary_gaps, "owner_gaps": owner_gaps, "gaps_filled": 0}


def _fill_one(state):
    """Model-call: fill the NEXT single missing summary, in memory.

    One gap per step (not the whole loop) so the runtime checkpoints after each
    fill -- a crash mid-fill (e.g. an EDR SIGKILL) resumes at the cursor and the
    already-filled gaps are not recomputed. The work-list is recomputed from the
    corpus each call, so it is idempotent and resume-safe. Authored summaries are
    never touched (only nodes lacking summary_source are filled).
    """
    corpus = state["corpus"]
    todo = _ungapped(corpus)
    if not todo:
        return {}
    node = todo[0]
    node["summary"] = get_model(state.get("model")).run(_gap_prompt(node)).strip()
    node["summary_source"] = "generated"   # never "authored"
    return {"corpus": corpus, "gaps_filled": state.get("gaps_filled", 0) + 1}


def _commit(state):
    """Writes: persist the corpus once, deterministically (sorted keys)."""
    with open(os.path.join(state["root"], _CORPUS), "w", encoding="utf-8") as fh:
        json.dump(state["corpus"], fh, indent=2, sort_keys=True)
        fh.write("\n")
    return None


# --- the plan: control flow as data, with a durable fill loop ------------------
# The clauses that used to be inline `if execute and ... and not s_errors` are
# now named edge predicates. `execute` is the runtime's job for the dry-run guard
# AND a domain-state key so the loop predicate is engine-neutral (the runtime's
# internal flag isn't visible to edge predicates).

def _clean(state):
    """True when the structure gate found no errors."""
    return not state.get("s_errors")


def _wants_fill(state):
    """True when gap-fill is requested and there is a clean tree with gaps."""
    return bool(state.get("fix_gaps")) and bool(_ungapped(state.get("corpus", {}))) \
        and not state.get("s_errors")


def _more_to_fill(state):
    """True when authorized to fill and at least one gap remains (loop guard)."""
    return bool(state.get("execute")) and bool(_ungapped(state.get("corpus", {})))


_PLAN = Plan(
    name="index_enforce",
    entry="gate",
    steps=(
        Step("gate", READ_ONLY, _gate),
        Step("build", WRITES, _build),
        Step("link", WRITES, _link),
        Step("report", READ_ONLY, _report),
        Step("fill", MODEL_CALL, _fill_one),
        Step("commit", WRITES, _commit),
    ),
    edges=(
        Edge("gate", "build", when=_clean),    # clean tree -> rebuild
        Edge("gate", "report"),                # dirty tree -> straight to report
        Edge("build", "link"),
        Edge("link", "report"),
        Edge("report", "fill", when=_wants_fill),
        Edge("report", END),
        Edge("fill", "fill", when=_more_to_fill),   # durable loop: one gap per step
        Edge("fill", "commit"),
        Edge("commit", END),
    ),
)


def enforce(*, execute=False, fix_gaps=False, model=None, root=None, runtime=None,
            checkpointer=None, run_key="index_enforce"):
    """Gate -> build_corpus -> link_corpus -> report -> durable fill loop -> commit.

    The pipeline is a neutral ``Plan`` executed by a ``Runtime`` (default the
    pure-stdlib ``inprocess`` engine; ``runtime="langgraph"`` runs the same plan
    on LangGraph). WRITES and the model-backed fill run only when ``execute=True``
    (dry-run default); the fill additionally needs ``fix_gaps=True``.

    When actually filling, the fill loop is made **durable**: each gap is its own
    step, so the runtime snapshots after every fill and a crash mid-fill (an EDR
    SIGKILL, say) **resumes** instead of re-running model calls. By default a
    ``FileCheckpointer`` is used under ``wiki/.runtime`` and a leftover snapshot
    (from a prior crash) is auto-resumed; pass your own ``checkpointer`` to
    override. The model comes via ``models.get_model(model)`` -- never a provider.
    """
    root = root or _REPO
    if checkpointer is None and execute and fix_gaps:
        checkpointer = FileCheckpointer(os.path.join(root, _CKPT_DIR))
    init = {"root": root, "model": model, "fix_gaps": fix_gaps, "execute": execute}
    kwargs = {"execute": execute}
    if checkpointer is not None:
        kwargs["checkpointer"] = checkpointer
        kwargs["run_key"] = run_key
        if checkpointer.load(run_key) is not None:   # a prior run crashed -> resume
            kwargs["resume"] = None
    st = get_runtime(runtime).run(_PLAN, init, **kwargs).state
    return EnforceReport(
        structure_errors=st.get("s_errors", ()),
        structure_warnings=st.get("s_warnings", ()),
        corpus_path=_CORPUS,
        nodes=len(st.get("nodes", [])),
        summary_gaps=st.get("summary_gaps", ()),
        owner_gaps=st.get("owner_gaps", ()),
        gaps_filled=st.get("gaps_filled", 0),
        dry_run=not execute,
    )
