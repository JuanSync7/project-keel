"""
title: Practice refactor brain
layer: backend
public_api: no
summary: Plan: walk the corpus KG -> gate a green baseline -> (propose -> apply+gate+rollback) one chunk per step; on a durable Runtime. An execute run needs its approved count of model calls: every call goes through one run's models.ModelMeter, and a resumed run is first checked against the approved model and count (models.approve_resume). Every tool child runs through scripts/resource_limits.py run_tool, held to the refactored root's config/project.json `agents.tool_timeout_seconds` and `agents.tool_max_output_bytes`, the root whose make_targets gate keys the gate runner it starts reads, so the time limit is checked against that runner's own limit: past either its session is ended and the step raises ChildTimedOut or ChildOutputTooLarge naming the key. The walk keeps a chunk only when config_loader.is_served keeps its corpus node and config_loader.is_served_now keeps the level its file states on disk now (scripts/corpus_level.py stated_now), and the propose step asks that level again, so a file reclassified after the corpus was built, or one whose level cannot be read, never reaches a prompt.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Collection
from dataclasses import dataclass

from models import ModelBackend, ModelMeter, approve_resume, get_model
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
from scripts import config_loader, corpus_level
from scripts.resource_limits import run_tool

__all__ = ["refactor", "propose", "RefactorReport"]

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CORPUS = os.path.join("wiki", "corpus.json")
_PRACTICES = os.path.join("config", "practices.json")
_CKPT_DIR = os.path.join("wiki", ".runtime")  # gitignored; durable refactor snapshots


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
    candidates: tuple  # tuple[str, ...] — node_ids in the walked neighbourhood
    refactored: tuple  # tuple[str, ...] — files whose edit passed the gate
    skipped: tuple  # tuple[str, ...] — node_ids no accepted edit was made for
    preview: str  # the prompt the first chunk WOULD send (dry-run)
    dry_run: bool


def _run(args, stdin=None, *, root):
    """Invoke a repo script via its CLI (tools are consumed as CLIs, never imported).

    Uses the SAME interpreter running this agent (sys.executable), so the tools
    run under a compatible Python rather than a hardcoded 'python3' on PATH.
    ``stdin`` (when given) is piped to the child — the refactor spec goes to
    apply_refactor this way.
    Bounded by scripts/resource_limits.py run_tool: past config/project.json
    agents.tool_timeout_seconds or agents.tool_max_output_bytes the child's
    session is ended and ChildTimedOut or ChildOutputTooLarge names the key.
    Both keys are read from *root*, the tree the tool acts on: the gate runner
    reads its make_targets limit there, so the time limit is checked against
    the limit that runner really uses, never this checkout's.
    """
    proc = run_tool([sys.executable] + args, cwd=_REPO, stdin_text=stdin, root=root)
    return proc.returncode, proc.stdout, proc.stderr


def _system_prompt():
    with open(
        os.path.join(os.path.dirname(__file__), "prompt.md"), encoding="utf-8"
    ) as fh:
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
    parts = [
        practice,
        pdef.get("id") or "",
        pdef.get("title") or pdef.get("name") or "",
        pdef.get("summary") or "",
    ]
    parts.extend(pdef.get("tags") or [])
    return " ".join(p for p in parts if p)


def _propose_prompt(practice, pdef, node):
    """The per-chunk prompt: the named practice + one chunk to refactor toward it."""
    rule = ""
    if pdef:
        rule = "%s (%s): %s" % (
            pdef.get("title") or pdef.get("name") or practice,
            pdef.get("tier") or "",
            pdef.get("summary") or "",
        )
    return (
        _system_prompt() + "\n\n# Practice to apply\n%s\n%s\n\n# Chunk to refactor\n"
        "node_id: %s\npath: %s\ntags: %s\n---\n%s\n"
        % (
            practice,
            rule,
            node.get("node_id", ""),
            node.get("path", ""),
            ", ".join(node.get("tags") or []),
            node.get("text_excerpt") or node.get("summary") or "",
        )
    )


def _parse_spec(reply, practice):
    """Extract a bounded edit spec from the model reply, or None to decline.

    Tolerates a ```json ...``` fence. Returns None on unparseable text, an
    empty edit list or a reply that names a gate, so a chunk the model can't
    safely edit is simply skipped — never a half-formed write.
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
    # The gate is the run's (--gate), never the reply's: a reply that names one
    # is trying to choose its own judge, so it is declined, fail-closed, rather
    # than stripped and applied.
    if "gate" in data:
        return None
    data.setdefault("practice", practice)
    return data


def _served(nodes, served=None):
    """The members of *nodes* at a level in *served*, or in this repository's
    ``corpus.served_visibilities`` when None. A node that states no level, or a
    level outside the vocabulary, is dropped: absent, never assumed open, by
    config_loader.is_served, the decision every corpus reader shares."""
    if served is None:
        served = config_loader.served_visibilities(_REPO)
    return [n for n in nodes if config_loader.is_served(n, served)]


def _served_now(nodes, root):
    """The members of *nodes* whose files under *root* may be sent as they are
    on disk now: config_loader.is_served_now over scripts/corpus_level.py
    stated_now, at *root*'s ``corpus.served_visibilities``. A file
    reclassified after the corpus was built, or one whose level cannot be
    read now, is dropped, so its text never reaches a prompt."""
    served = config_loader.served_visibilities(root)
    return [
        n
        for n in nodes
        if config_loader.is_served_now(
            n, served, corpus_level.stated_now(root, n.get("path"))
        )
    ]


def propose(
    practice: str,
    practice_def: dict | None,
    node: dict,
    *,
    backend: ModelBackend,
    served: Collection[str] | None = None,
) -> dict | None:
    """The agent's one model call: ONE bounded edit spec moving the corpus
    *node* toward *practice* (its config/practices.json row *practice_def*, or
    None when the registry has none), from *backend*; None when the model
    declines, the reply does not parse, or it names its own gate. A node at a
    level outside *served* (None reads ``corpus.served_visibilities``) is None
    with no model call, so its text never reaches a prompt. The plan's propose
    step and the eval harness (evals/_doers.py) both call it; the step first
    asks the level the chunk's file states on disk now."""
    if not _served([node], served):
        return None
    if not node.get("path"):
        # An apply is bound to the chunk's own file (--allow), so a chunk with
        # no path can never be applied; declining here spends no model call.
        return None
    reply = backend.run(_propose_prompt(practice, practice_def, node))
    spec: dict | None = _parse_spec(reply, practice)
    return spec


# --- plan steps: each returns a dict merged into the run state -----------------
# Deterministic logic stays in pure-stdlib scripts/ doers invoked as CLIs; these
# steps orchestrate them. The model is reached only in `propose` (MODEL_CALL) and
# the tree is touched only in `apply` (WRITES), so the runtime skips BOTH unless
# execute=True — a dry-run walks the graph and gates the baseline, nothing more.


def _walk(state):
    """Read-only: walk the corpus KG for the practice's neighbourhood (query_corpus)."""
    pdef = _load_practice(state["root"], state["practice"])
    query = _practice_query(state["practice"], pdef)
    rc, out, err = _run(
        [
            "scripts/query_corpus.py",
            query,
            "--corpus",
            state["corpus"],
            "--max-nodes",
            str(state["max_nodes"]),
            "--root",
            state["root"],
        ],
        root=state["root"],
    )
    if rc != 0:
        raise RuntimeError("query_corpus failed (rc=%d): %s" % (rc, err.strip()))
    try:
        hits = json.loads(out) if out.strip() else []
    except ValueError:
        hits = []
    # The preview prompt carries a chunk's text too, so the cut comes first.
    hits = _served_now(_served(hits), state["root"])
    preview = _propose_prompt(state["practice"], pdef, hits[0]) if hits else ""
    return {
        "practice_def": pdef,
        "candidates": tuple(h.get("node_id", "") for h in hits),
        "chunks": hits,
        "preview": preview,
        "cursor": 0,
        "refactored": (),
        "skipped": (),
    }


def _baseline(state):
    """Read-only: gate the tree green BEFORE refactoring (run_make_target).

    A dirty tree yields a dirty refactor, so if the gate is already red the loop
    predicate (`_wants_refactor`) short-circuits to END and nothing is attempted.
    """
    _, out, _ = _run(
        ["scripts/run_make_target.py", state["gate"], "--json", "--dir", state["root"]],
        root=state["root"],
    )
    try:
        res = json.loads(out) if out.strip() else {}
    except ValueError:
        res = {}
    return {"baseline_green": bool(res.get("ok"))}


def _propose(state, meter):
    """Model-call: draft ONE bounded edit spec for the chunk at the cursor, on
    the run's counted backend (*meter*).

    One chunk per step (not the whole loop) so the runtime checkpoints after each
    apply — a crash mid-refactor resumes at the cursor and accepted chunks are not
    re-proposed.
    """
    node = state["chunks"][state["cursor"]]
    if not node.get("path"):
        # Checked here as well as in propose, so a pathless chunk never builds
        # a backend.
        return {"spec": None}
    if not _served_now([node], state["root"]):
        # Asked again here, not only at the walk: a run resumed from a
        # snapshot may hold a chunk whose file was reclassified since.
        return {"spec": None}
    return {
        "spec": propose(
            state["practice"], state.get("practice_def"), node, backend=meter.backend()
        )
    }


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
        # --allow binds the apply to the chunk the model was shown, so the
        # reply's edits[].file cannot reach any other file; `propose` already
        # declined a chunk with no path, and an empty one binds to no file.
        _, out, _ = _run(
            [
                "scripts/apply_refactor.py",
                "--spec",
                "-",
                "--root",
                state["root"],
                "--gate",
                state["gate"],
                "--allow",
                node.get("path", ""),
                "--json",
            ],
            stdin=json.dumps(spec),
            root=state["root"],
        )
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
    return {
        "cursor": state["cursor"] + 1,
        "spec": None,
        "refactored": tuple(refactored),
        "skipped": tuple(skipped),
    }


# --- the plan: control flow as data, with a durable per-chunk refactor loop -----


def _remaining(state):
    """True while a chunk in the walked neighbourhood is still unrefactored."""
    return state.get("cursor", 0) < len(state.get("chunks", []))


def _wants_refactor(state):
    """True when authorized to refactor a green tree that has chunks to touch."""
    return (
        bool(state.get("execute"))
        and bool(state.get("baseline_green"))
        and _remaining(state)
    )


def _more(state):
    """Loop guard: authorized and at least one chunk remains (one per step)."""
    return bool(state.get("execute")) and _remaining(state)


def _plan(meter):
    """The refactor plan, its model step bound to this run's counted backend:
    the backend is the run's own, never one a step builds from saved state."""
    return Plan(
        name="practice_refactor",
        entry="walk",
        steps=(
            Step("walk", READ_ONLY, _walk),
            Step("baseline", READ_ONLY, _baseline),
            Step("propose", MODEL_CALL, lambda state: _propose(state, meter)),
            Step("apply", WRITES, _apply),
        ),
        edges=(
            Edge("walk", "baseline"),
            Edge(
                "baseline", "propose", when=_wants_refactor
            ),  # green tree + work -> refactor
            Edge("baseline", END),  # dry-run / red / nothing to do
            Edge("propose", "apply"),
            Edge("apply", "propose", when=_more),  # durable loop: one chunk/step
            Edge("apply", END),
        ),
    )


def refactor(
    practice,
    *,
    execute=False,
    model=None,
    corpus=None,
    root=None,
    max_nodes=8,
    gate="verify",
    runtime=None,
    checkpointer=None,
    run_key="practice_refactor",
    max_model_calls=None,
):
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

    An execute run needs ``max_model_calls``, the approved count, or raises
    ValueError: every model call goes through one ``models.CountedModel`` of
    that count, so the call past it raises ``models.CallCapReached``. A saved
    run is resumed only on the same model and with no more chunks left than
    that count; otherwise ``models.RunNotApproved`` is raised before any step.
    """
    if execute and max_model_calls is None:
        raise ValueError(
            "refactor(execute=True) needs max_model_calls, the approved model-call count"
        )
    root = root or _REPO
    corpus = corpus or os.path.join(root, _CORPUS)
    if checkpointer is None and execute:
        checkpointer = FileCheckpointer(os.path.join(root, _CKPT_DIR))
    init = {
        "practice": practice,
        "model": model,
        "corpus": corpus,
        "root": root,
        "max_nodes": max_nodes,
        "gate": gate,
        "execute": execute,
    }
    kwargs = {"execute": execute}
    if checkpointer is not None:
        kwargs["checkpointer"] = checkpointer
        kwargs["run_key"] = run_key
        saved = checkpointer.load(run_key)
        if saved is not None:  # a prior run crashed -> resume
            if execute:
                left = saved["state"]
                approve_resume(
                    where=checkpointer.where(run_key),
                    saved_model=left.get("model"),
                    model=model,
                    left=len(left.get("chunks", ())) - left.get("cursor", 0),
                    cap=max_model_calls,
                )
            kwargs["resume"] = None
    meter = ModelMeter(model, max_model_calls or 0, get_model)
    st = get_runtime(runtime).run(_plan(meter), init, **kwargs).state
    return RefactorReport(
        practice=practice,
        baseline_green=bool(st.get("baseline_green", False)),
        candidates=tuple(st.get("candidates", ())),
        refactored=tuple(st.get("refactored", ())),
        skipped=tuple(st.get("skipped", ())),
        preview=st.get("preview", ""),
        dry_run=not execute,
    )
