"""
title: Wiki navigator brain
layer: backend
public_api: no
summary: Plan: deterministic retrieval (query_corpus) -> synthesize a cited answer; on a Runtime. answer is given a root or a corpus, never both, and scripts/corpus_level.py checkout derives the other (this checkout when neither; a relative path is the caller's directory's), raising NotACheckout for both, for a corpus that is not some checkout's wiki/corpus.json, or for a corpus that does not exist, so a mistyped corpus is not answered from an empty context. Retrieval hands query_corpus that root alone as `--root`, so it reads the root's own corpus and files, and a node is retrieved, sent and cited only when its file there may be served as it stands on disk now (config_loader.is_served_now): a file reclassified after the corpus was built is neither sent nor named in a served node's links. A root query_corpus refuses (one that does not exist) fails retrieval, so answer raises before any model call. An execute run needs its approved count of model calls and makes its one call through a models.ModelMeter of that count, whose backend the caller's backend_factory builds when it gives one (models.get_model otherwise), so a caller can count calls across answers. Every tool child runs through scripts/resource_limits.py run_tool, held to config/project.json `agents.tool_timeout_seconds` and `agents.tool_max_output_bytes` of the checkout answer's limits_root names (this one when None): past either its session is ended and the step raises ChildTimedOut or ChildOutputTooLarge naming the key.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Collection
from dataclasses import dataclass

from models import ModelBackend, ModelMeter, get_model
from runtimes import END, MODEL_CALL, READ_ONLY, Edge, Plan, Step, get_runtime
from scripts import config_loader, corpus_level
from scripts.resource_limits import run_tool

__all__ = ["answer", "synthesize", "Answer", "Citation"]

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@dataclass(frozen=True)
class Citation:
    """One traceable source behind an answer."""

    node_id: str
    path: str
    summary_source: str  # "authored" | "generated" — caller can weight authored higher
    owner: str  # resolved owner ("" if unowned)
    # "marker" | "frontmatter" | "inherited" | "default" | "none", or None
    # when the node names no source: unknown, distinct from `none`.
    owner_source: str | None


@dataclass(frozen=True)
class Answer:
    """An answer plus full provenance."""

    text: str  # the answer; in dry-run, the prompt that WOULD be sent
    citations: tuple  # tuple[Citation, ...] — every source is traceable
    dry_run: bool


def _run(args, *, root):
    """Invoke a repo script via its CLI with the SAME interpreter running us.
    Bounded by scripts/resource_limits.py run_tool: past config/project.json
    agents.tool_timeout_seconds or agents.tool_max_output_bytes the child's
    session is ended and ChildTimedOut or ChildOutputTooLarge names the key.
    Both keys are read from *root*'s config (this checkout when None).
    """
    proc = run_tool([sys.executable] + args, cwd=_REPO, root=root)
    return proc.returncode, proc.stdout, proc.stderr


def _system_prompt():
    with open(
        os.path.join(os.path.dirname(__file__), "prompt.md"), encoding="utf-8"
    ) as fh:
        return fh.read()


def _visible(nodes, served=None):
    """The members of *nodes* at a level in *served*, or in this repository's
    ``corpus.served_visibilities`` when None. A node that states no level, or a
    level outside the vocabulary, is dropped: absent, never assumed open, by
    config_loader.is_served, the decision every corpus reader shares."""
    if served is None:
        served = config_loader.served_visibilities(_REPO)
    return [n for n in nodes if config_loader.is_served(n, served)]


def _answer_prompt(question, nodes):
    ctx = "\n".join(
        "- [%s] %s (%s): %s"
        % (
            n.get("summary_source") or "gap",
            n.get("node_id"),
            n.get("path"),
            n.get("summary") or n.get("text_excerpt", ""),
        )
        for n in nodes
    )
    return (
        _system_prompt()
        + "\n\n# Question\n%s\n\n# Retrieved context (cite by node_id)\n%s\n"
        % (question, ctx or "(nothing retrieved)")
    )


# --- plan steps ----------------------------------------------------------------
# Retrieval is deterministic and read-only, so it ALWAYS runs (even in dry-run)
# and `citations` is populated regardless. Only the synthesis is a model call,
# so the runtime gates it on execute=True. A failed retrieval fails closed
# (raises) rather than handing the model an empty, hallucination-prone context.


def _retrieve(state):
    """Read-only: query_corpus, fail closed on error, filter by visibility, cite."""
    rc, out, err = _run(
        [
            "scripts/query_corpus.py",
            state["question"],
            "--max-nodes",
            str(state["max_nodes"]),
            "--root",
            state["root"],
        ],
        root=state["limits_root"],
    )
    if rc != 0:
        raise RuntimeError("query_corpus failed (rc=%d): %s" % (rc, err.strip()))
    try:
        hits = json.loads(out) if out.strip() else []
    except ValueError:
        hits = []
    visible = _visible(hits)
    citations = tuple(
        Citation(
            node_id=h.get("node_id", ""),
            path=h.get("path", ""),
            summary_source=h.get("summary_source") or "",
            owner=h.get("owner") or "",
            owner_source=h.get("owner_source") or None,
        )
        for h in visible
    )
    return {
        "citations": citations,
        "nodes": visible,
        "prompt": _answer_prompt(state["question"], visible),
    }


def synthesize(
    question: str,
    nodes: list[dict],
    *,
    backend: ModelBackend,
    served: Collection[str] | None = None,
) -> str:
    """The agent's one model call: answer *question* from the visible members of
    *nodes* (retrieved corpus nodes) on *backend*, citing each by node_id, and
    return the reply stripped. A node at a level outside *served* (None reads
    ``corpus.served_visibilities``) is dropped here as well as at retrieval, so
    no caller can send one. The plan's synthesize step and the eval harness
    (evals/_doers.py) both call it."""
    return backend.run(_answer_prompt(question, _visible(nodes, served))).strip()


def _synthesize(state, meter):
    """Model-call: synthesize the answer over the retrieved, visible nodes, on
    the run's counted backend (*meter*)."""
    return {
        "answer_text": synthesize(
            state["question"], state["nodes"], backend=meter.backend()
        )
    }


def _plan(meter):
    """The answer plan, its model step bound to this run's counted backend."""
    return Plan(
        name="wiki_answer",
        entry="retrieve",
        steps=(
            Step("retrieve", READ_ONLY, _retrieve),
            Step("synthesize", MODEL_CALL, lambda state: _synthesize(state, meter)),
        ),
        edges=(
            Edge("retrieve", "synthesize"),
            Edge("synthesize", END),
        ),
    )


def answer(
    question,
    *,
    execute=False,
    model=None,
    corpus=None,
    max_nodes=8,
    runtime=None,
    max_model_calls=None,
    backend_factory=None,
    limits_root=None,
    root=None,
):
    """Deterministically retrieve candidate nodes (tree+links, via query_corpus),
    then synthesize an answer over them. The pipeline is a neutral ``Plan`` run
    on a ``Runtime`` (default the stdlib ``inprocess`` engine; ``runtime``
    selects another). Retrieval always runs, so ``citations`` is populated even
    in dry-run; only the model call is gated by ``execute``. Honors node
    ``visibility``. Model via ``models.get_model(model)`` -- never a provider name.

    An execute run needs ``max_model_calls``, the approved count, or raises
    ValueError; the answer's one call goes through a ``models.CountedModel``
    of that count, so a count of 0 raises ``models.CallCapReached`` with no
    call made. ``backend_factory`` builds that backend from the model name
    (``None`` = ``models.get_model``); a caller that counts calls across
    answers, such as ``models.SessionBudget.counted``, passes its own.
    ``limits_root`` is the checkout whose config/project.json
    ``agents.tool_timeout_seconds`` and ``agents.tool_max_output_bytes`` bound
    the retrieval child (``None`` = this one). ``root`` or ``corpus`` names
    the checkout to answer from, never both (scripts/corpus_level.py
    checkout): ``root`` is the checkout (``None`` = this one), ``corpus`` its
    ``wiki/corpus.json``, a relative one taken from the caller's directory.
    query_corpus reads that checkout's corpus and each node's file there
    again, and retrieves a node only at the level its file states now. Both
    given, a corpus that is not some checkout's ``wiki/corpus.json``, or a
    corpus that does not exist,
    raises corpus_level.NotACheckout, a ValueError, before any step; a root
    that does not exist fails retrieval, so this raises RuntimeError before
    any model call, dry run included.
    """
    if execute and max_model_calls is None:
        raise ValueError(
            "answer(execute=True) needs max_model_calls, the approved model-call count"
        )
    # Absolute, from the caller's directory: the retrieval child runs in this
    # checkout, and is handed the root alone, so it reads that root's corpus.
    root, _ = corpus_level.checkout(root, corpus, _REPO)
    init = {
        "question": question,
        "model": model,
        "max_nodes": max_nodes,
        "limits_root": limits_root,
        "root": root,
    }
    meter = ModelMeter(model, max_model_calls or 0, backend_factory or get_model)
    st = get_runtime(runtime).run(_plan(meter), init, execute=execute).state
    citations = st.get("citations", ())
    if execute:
        return Answer(text=st["answer_text"], citations=citations, dry_run=False)
    return Answer(text=st.get("prompt", ""), citations=citations, dry_run=True)
