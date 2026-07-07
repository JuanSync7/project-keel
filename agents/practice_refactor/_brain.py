"""
title: Practice refactor brain
layer: backend
public_api: no
summary: Plan: walk the corpus KG -> gate a green baseline -> (propose -> apply+gate+rollback) one chunk per step; on a durable Runtime.
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

__all__ = ["refactor", "RefactorReport"]

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CORPUS = os.path.join("wiki", "corpus.json")
_PRACTICES = os.path.join("config", "practices.json")
_CKPT_DIR = os.path.join("wiki", ".runtime")   # gitignored; durable refactor snapshots


@dataclass(frozen=True)
class RefactorReport:
    """What a practice-refactor pass walked, applied, and skipped — with provenance.

    Every accepted chunk (`refactored`) passed the gate; every `skipped` chunk
    either drew no bounded edit or would have turned the gate red (so it was
    rolled back). `baseline_green` records whether the tree was green *before*
    refactoring — a red baseline means nothing was attempted.
    """
    practice: str
    baseline_green: bool
    candidates: tuple      # tuple[str, ...] — node_ids in the walked neighbourhood
    refactored: tuple      # tuple[str, ...] — files whose edit passed the gate
    skipped: tuple         # tuple[str, ...] — node_ids no accepted edit was made for
    preview: str           # the prompt the first chunk WOULD send (dry-run)
    dry_run: bool


def _run(args, stdin=None):
    """Invoke a repo script via its CLI (tools are consumed as CLIs, never imported).

    Uses the SAME interpreter running this agent (sys.executable), so the tools
    run under a compatible Python rather than a hardcoded 'python3' on PATH.
    ``stdin`` (when given) is piped to the child — the refactor spec goes to
    apply_refactor this way.
    """
    proc = subprocess.run([sys.executable] + args, cwd=_REPO,
                          capture_output=True, text=True, input=stdin)
    return proc.returncode, proc.stdout, proc.stderr


def _system_prompt():
    with open(os.path.join(os.path.dirname(__file__), "prompt.md"), encoding="utf-8") as fh:
        return fh.read()


def _load_practice(corpus_root, practice):
    """Return the named practice's registry row (or None if unknown/unreadable).

    config/practices.json is DATA read by path (json.load), never imported —
    the same way check_H reads project.json and the doers read this file.
    """
    path = os.path.join(corpus_root, _PRACTICES)
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    for row in data.get("practices", []):
        if row.get("id") == practice:
            return row
    return None


def _practice_query(practice, pdef):
    """The retrieval query for the KG walk: the practice's own words when known.

    A practice's tags/title scope its checks to corpus nodes carrying those tags
    (the graph tells us where the rule is even relevant); fall back to the raw id
    when the practice is not in the registry.
    """
    if not pdef:
        return practice
    parts = [practice, pdef.get("id") or "", pdef.get("title") or pdef.get("name") or "",
             pdef.get("summary") or ""]
    parts.extend(pdef.get("tags") or [])
    return " ".join(p for p in parts if p)


def _propose_prompt(practice, pdef, node):
    """The per-chunk prompt: the named practice + one chunk to refactor toward it."""
    rule = ""
    if pdef:
        rule = "%s (%s): %s" % (pdef.get("title") or pdef.get("name") or practice,
                                pdef.get("tier") or "", pdef.get("summary") or "")
    return (_system_prompt()
            + "\n\n# Practice to apply\n%s\n%s\n\n# Chunk to refactor\n"
              "node_id: %s\npath: %s\ntags: %s\n---\n%s\n"
            % (practice, rule, node.get("node_id", ""), node.get("path", ""),
               ", ".join(node.get("tags") or []),
               node.get("text_excerpt") or node.get("summary") or ""))


def _parse_spec(reply, practice, gate):
    """Extract a bounded edit spec from the model reply, or None to decline.

    Tolerates a ```json ...``` fence. Returns None on unparseable text or an
    empty edit list, so a chunk the model can't safely edit is simply skipped —
    never a half-formed write.
    """
    text = reply.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:] if lines and lines[0].startswith("```") else lines
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    edits = data.get("edits")
    if not isinstance(edits, list) or not edits:
        return None
    data.setdefault("practice", practice)
    data.setdefault("gate", gate)
    return data


# --- plan steps: each returns a dict merged into the run state -----------------
# Deterministic logic stays in pure-stdlib scripts/ doers invoked as CLIs; these
# steps orchestrate them. The model is reached only in `propose` (MODEL_CALL) and
# the tree is touched only in `apply` (WRITES), so the runtime skips BOTH unless
# execute=True — a dry-run walks the graph and gates the baseline, nothing more.

def _walk(state):
    """Read-only: walk the corpus KG for the practice's neighbourhood (query_corpus)."""
    pdef = _load_practice(state["root"], state["practice"])
    query = _practice_query(state["practice"], pdef)
    rc, out, err = _run(["scripts/query_corpus.py", query,
                         "--corpus", state["corpus"],
                         "--max-nodes", str(state["max_nodes"])])
    if rc != 0:
        raise RuntimeError("query_corpus failed (rc=%d): %s" % (rc, err.strip()))
    try:
        hits = json.loads(out) if out.strip() else []
    except ValueError:
        hits = []
    preview = _propose_prompt(state["practice"], pdef, hits[0]) if hits else ""
    return {"practice_def": pdef,
            "candidates": tuple(h.get("node_id", "") for h in hits),
            "chunks": hits, "preview": preview,
            "cursor": 0, "refactored": (), "skipped": ()}


def _baseline(state):
    """Read-only: gate the tree green BEFORE refactoring (run_make_target).

    A dirty tree yields a dirty refactor, so if the gate is already red the loop
    predicate (`_wants_refactor`) short-circuits to END and nothing is attempted.
    """
    _, out, _ = _run(["scripts/run_make_target.py", state["gate"], "--json",
                      "--dir", state["root"]])
    try:
        res = json.loads(out) if out.strip() else {}
    except ValueError:
        res = {}
    return {"baseline_green": bool(res.get("ok"))}


def _propose(state):
    """Model-call: draft ONE bounded edit spec for the chunk at the cursor.

    One chunk per step (not the whole loop) so the runtime checkpoints after each
    apply — a crash mid-refactor resumes at the cursor and accepted chunks are not
    re-proposed.
    """
    node = state["chunks"][state["cursor"]]
    reply = get_model(state.get("model")).run(
        _propose_prompt(state["practice"], state.get("practice_def"), node))
    return {"spec": _parse_spec(reply, state["practice"], state["gate"])}


def _apply(state):
    """Writes: apply the proposed spec through the gated doer, advance the cursor.

    apply_refactor applies atomically and ROLLS BACK unless the gate stays green,
    so a chunk lands in `refactored` only when the tree is still green; anything
    else (no spec, unparseable, or gate-red) lands in `skipped`. The agent thus
    cannot mark a chunk done unless it satisfies the very `make verify` it gates on.
    """
    node = state["chunks"][state["cursor"]]
    refactored = list(state.get("refactored", ()))
    skipped = list(state.get("skipped", ()))
    spec = state.get("spec")
    if spec:
        _, out, _ = _run(["scripts/apply_refactor.py", "--spec", "-",
                          "--root", state["root"], "--gate", state["gate"], "--json"],
                         stdin=json.dumps(spec))
        try:
            res = json.loads(out) if out.strip() else {}
        except ValueError:
            res = {}
        if res.get("applied"):
            refactored.extend(res.get("files", []))
        else:
            skipped.append(node.get("node_id", ""))
    else:
        skipped.append(node.get("node_id", ""))
    return {"cursor": state["cursor"] + 1, "spec": None,
            "refactored": tuple(refactored), "skipped": tuple(skipped)}


# --- the plan: control flow as data, with a durable per-chunk refactor loop -----

def _remaining(state):
    """True while a chunk in the walked neighbourhood is still unrefactored."""
    return state.get("cursor", 0) < len(state.get("chunks", []))


def _wants_refactor(state):
    """True when authorized to refactor a green tree that has chunks to touch."""
    return bool(state.get("execute")) and bool(state.get("baseline_green")) \
        and _remaining(state)


def _more(state):
    """Loop guard: authorized and at least one chunk remains (one per step)."""
    return bool(state.get("execute")) and _remaining(state)


_PLAN = Plan(
    name="practice_refactor",
    entry="walk",
    steps=(
        Step("walk", READ_ONLY, _walk),
        Step("baseline", READ_ONLY, _baseline),
        Step("propose", MODEL_CALL, _propose),
        Step("apply", WRITES, _apply),
    ),
    edges=(
        Edge("walk", "baseline"),
        Edge("baseline", "propose", when=_wants_refactor),  # green tree + work -> refactor
        Edge("baseline", END),                              # dry-run / red / nothing to do
        Edge("propose", "apply"),
        Edge("apply", "propose", when=_more),               # durable loop: one chunk/step
        Edge("apply", END),
    ),
)


def refactor(practice, *, execute=False, model=None, corpus=None, root=None,
             max_nodes=8, gate="verify", runtime=None, checkpointer=None,
             run_key="practice_refactor"):
    """Walk the corpus KG for a NAMED practice and refactor each chunk toward it,
    gating every applied edit on ``make <gate>`` (default ``verify``).

    The pipeline is a neutral ``Plan`` executed by a ``Runtime`` (default the
    pure-stdlib ``inprocess`` engine; ``runtime="langgraph"`` runs the same plan
    on LangGraph). The model-backed ``propose`` and the tree-touching ``apply``
    run only when ``execute=True`` (dry-run default): a dry run walks the graph
    (so ``candidates`` and ``preview`` are populated) and gates the read-only
    baseline, but proposes and writes nothing.

    When actually refactoring, the loop is **durable**: each chunk is its own
    step, so the runtime snapshots after every apply and a crash mid-refactor
    **resumes** at the cursor instead of re-proposing accepted chunks. By default
    a ``FileCheckpointer`` under ``wiki/.runtime`` is used and a leftover snapshot
    (from a prior crash) is auto-resumed; pass your own ``checkpointer`` to
    override. The model comes via ``models.get_model(model)`` — never a provider;
    edits land only through the gated ``apply_refactor`` doer, never a raw write.
    """
    root = root or _REPO
    corpus = corpus or os.path.join(root, _CORPUS)
    if checkpointer is None and execute:
        checkpointer = FileCheckpointer(os.path.join(root, _CKPT_DIR))
    init = {"practice": practice, "model": model, "corpus": corpus, "root": root,
            "max_nodes": max_nodes, "gate": gate, "execute": execute}
    kwargs = {"execute": execute}
    if checkpointer is not None:
        kwargs["checkpointer"] = checkpointer
        kwargs["run_key"] = run_key
        if checkpointer.load(run_key) is not None:   # a prior run crashed -> resume
            kwargs["resume"] = None
    st = get_runtime(runtime).run(_PLAN, init, **kwargs).state
    return RefactorReport(
        practice=practice,
        baseline_green=bool(st.get("baseline_green", False)),
        candidates=tuple(st.get("candidates", ())),
        refactored=tuple(st.get("refactored", ())),
        skipped=tuple(st.get("skipped", ())),
        preview=st.get("preview", ""),
        dry_run=not execute,
    )
