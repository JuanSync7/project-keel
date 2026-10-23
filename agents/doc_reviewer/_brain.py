"""
title: Doc reviewer brain
layer: backend
public_api: no
summary: Plan: gather the deterministic doc findings (review_docs) -> retrieve the style rules (query_corpus) -> gate a green baseline -> (propose -> apply+gate+rollback) one finding per step; on a durable Runtime. Judgment only where a rule cannot decide. An execute run needs its approved count of model calls: every call goes through one run's models.ModelMeter, and a resumed run is first checked against the approved model and count (models.approve_resume). Every tool child runs through scripts/resource_limits.py run_tool, held to config/project.json `agents.tool_timeout_seconds` and `agents.tool_max_output_bytes`: past either its process group is ended and the step raises ChildTimedOut or ChildOutputTooLarge naming the key.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass

from models import ModelMeter, approve_resume, get_model
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
from scripts.resource_limits import run_tool

__all__ = ["review", "DocReviewReport"]

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CORPUS = os.path.join("wiki", "corpus.json")
_CKPT_DIR = os.path.join("wiki", ".runtime")  # gitignored; durable review snapshots
_GUIDE = os.path.join("docs", "guides", "doc-style.md")
# The rules the model applies, retrieved from the corpus by these words so the
# prompt carries the guide's own text, not a paraphrase of it.
_RULE_QUERY = "documentation style roster discriminator Not for citation mention freshness updated"


@dataclass(frozen=True)
class DocReviewReport:
    """What a documentation review found, judged, applied and skipped.

    `stale`, `unresolved` and `rosters` are the deterministic facts
    (`review_docs.py`); `candidates` are the chunks the model was (or would be)
    asked about, in order; `applied` are files whose edit kept the gate green;
    `skipped` are chunks the model declined or whose edit was rolled back.
    """

    baseline_green: bool
    stale: int
    unresolved: int
    rosters: int
    candidates: tuple  # tuple[str, ...] — chunk ids, e.g. "mention:docs/a.md:4"
    applied: tuple  # tuple[str, ...] — files whose edit passed the gate
    skipped: tuple  # tuple[str, ...] — chunk ids with no accepted edit
    preview: str  # the prompt the first chunk WOULD send (dry-run)
    dry_run: bool


def _run(args, stdin=None):
    """Invoke a repo script via its CLI (tools are consumed as CLIs, never imported),
    under the interpreter running this agent.
    Bounded by scripts/resource_limits.py run_tool: past config/project.json
    agents.tool_timeout_seconds or agents.tool_max_output_bytes the child's
    process group is ended and ChildTimedOut or ChildOutputTooLarge names the key.
    """
    proc = run_tool([sys.executable] + args, cwd=_REPO, stdin_text=stdin)
    return proc.returncode, proc.stdout, proc.stderr


def _system_prompt():
    with open(
        os.path.join(os.path.dirname(__file__), "prompt.md"), encoding="utf-8"
    ) as fh:
        return fh.read()


def _read_lines(root, relpath, lineno, around=3):
    """The lines around `lineno` of a document, numbered — the chunk's own text,
    read by path as data (never imported), so the model edits what is there."""
    try:
        with open(os.path.join(root, relpath), encoding="utf-8") as fh:
            lines = fh.read().split("\n")
    except (OSError, ValueError):
        return ""
    lo, hi = max(0, lineno - 1 - around), min(len(lines), lineno + around)
    return "\n".join("%d: %s" % (i + 1, lines[i]) for i in range(lo, hi))


def _chunks(report, root, max_chunks):
    """The ordered work list from a review_docs JSON report: unresolved mentions,
    then roster rows to judge. Stale stamps are counted (`stale`) but never a
    chunk: a rule decides them, so the deterministic writer clears them
    (`make restamp-docs`), and while one is outstanding `make check-docs` is red,
    so a gated edit could never land and the baseline stops the run."""
    mentions = [
        {
            "id": "mention:%s:%d" % (m["path"], m["line"]),
            "kind": "mention",
            "path": m["path"],
            "line": m["line"],
            "finding": "`%s` resolves to nothing" % m["mention"],
            "text": _read_lines(root, m["path"], m["line"]),
        }
        for m in report.get("unresolved_mentions", [])
    ]
    rosters = [
        {
            "id": "roster:%s:%s" % (r["path"], r["member"]),
            "kind": "roster",
            "path": r["path"],
            "line": r["line"],
            "finding": "Not for: %s" % r["not_for"],
            "text": _read_lines(root, r["path"], r["line"], around=0),
        }
        for r in report.get("rosters", [])
    ]
    return (mentions + rosters)[:max_chunks]


def _propose_prompt(rules, chunk):
    """The per-chunk prompt: the guide's rules + one finding + the text it is about."""
    rule_text = "\n\n".join(
        "## %s\n%s"
        % (n.get("title", ""), n.get("text_excerpt") or n.get("summary") or "")
        for n in rules
    )
    return (
        _system_prompt()
        + "\n\n# Rules (from docs/guides/doc-style.md, via the corpus)\n%s"
        "\n\n# Chunk to review\nkind: %s\npath: %s\nline: %d\nfinding: %s\n---\n%s\n"
        % (
            rule_text,
            chunk["kind"],
            chunk["path"],
            chunk["line"],
            chunk["finding"],
            chunk["text"],
        )
    )


def _parse_spec(reply):
    """A bounded edit spec from the model reply, or None to decline the chunk."""
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
    return data


# --- plan steps ---------------------------------------------------------------


def _review(state):
    """Read-only: the deterministic facts, from the review_docs doer's JSON."""
    rc, out, err = _run(
        ["scripts/jobs/review_docs.py", "--json", "--root", state["root"]]
    )
    if rc != 0:
        raise RuntimeError("review_docs failed (rc=%d): %s" % (rc, err.strip()))
    try:
        report = json.loads(out) if out.strip() else {}
    except ValueError:
        report = {}
    chunks = _chunks(report, state["root"], state["max_chunks"])
    return {
        "stale": len(report.get("findings", [])),
        "unresolved": len(report.get("unresolved_mentions", [])),
        "rosters": len(report.get("rosters", [])),
        "chunks": chunks,
        "candidates": tuple(c["id"] for c in chunks),
        "cursor": 0,
        "applied": (),
        "skipped": (),
    }


def _retrieve(state):
    """Read-only: the style guide's rule nodes, from the corpus (query_corpus)."""
    _, out, _ = _run(
        [
            "scripts/query_corpus.py",
            _RULE_QUERY,
            "--corpus",
            state["corpus"],
            "--max-nodes",
            "6",
        ]
    )
    try:
        nodes = json.loads(out) if out.strip() else []
    except ValueError:
        nodes = []
    rules = [
        n for n in nodes if str(n.get("path", "")).endswith(os.path.basename(_GUIDE))
    ] or nodes
    chunks = state.get("chunks", [])
    preview = _propose_prompt(rules, chunks[0]) if chunks else ""
    return {"rules": rules, "preview": preview}


def _baseline(state):
    """Read-only: the gate must be green BEFORE any edit (run_make_target)."""
    _, out, _ = _run(
        ["scripts/run_make_target.py", state["gate"], "--json", "--dir", state["root"]]
    )
    try:
        res = json.loads(out) if out.strip() else {}
    except ValueError:
        res = {}
    return {"baseline_green": bool(res.get("ok"))}


def _propose(state, meter):
    """Model-call: ONE bounded edit spec for the chunk at the cursor, or a decline,
    from the run's counted backend (*meter*)."""
    chunk = state["chunks"][state["cursor"]]
    reply = meter.backend().run(_propose_prompt(state.get("rules", []), chunk))
    return {"spec": _parse_spec(reply)}


def _apply(state):
    """Writes: apply the spec through the gated doer (rolled back unless the gate
    stays green), advance the cursor."""
    chunk = state["chunks"][state["cursor"]]
    applied = list(state.get("applied", ()))
    skipped = list(state.get("skipped", ()))
    spec = state.get("spec")
    if spec:
        # --allow binds the apply to the chunk the model was shown, so the
        # reply's edits[].file cannot reach any other file.
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
                chunk["path"],
                "--json",
            ],
            stdin=json.dumps(spec),
        )
        try:
            res = json.loads(out) if out.strip() else {}
        except ValueError:
            res = {}
        if res.get("applied"):
            applied.extend(res.get("files", []))
        else:
            skipped.append(chunk["id"])
    else:
        skipped.append(chunk["id"])
    return {
        "cursor": state["cursor"] + 1,
        "spec": None,
        "applied": tuple(applied),
        "skipped": tuple(skipped),
    }


def _remaining(state):
    return state.get("cursor", 0) < len(state.get("chunks", []))


def _wants_edits(state):
    return (
        bool(state.get("execute"))
        and bool(state.get("baseline_green"))
        and _remaining(state)
    )


def _more(state):
    return bool(state.get("execute")) and _remaining(state)


def _plan(meter):
    """The review plan, its model step bound to this run's counted backend:
    the backend is the run's own, never one a step builds from saved state."""
    return Plan(
        name="doc_reviewer",
        entry="review",
        steps=(
            Step("review", READ_ONLY, _review),
            Step("retrieve", READ_ONLY, _retrieve),
            Step("baseline", READ_ONLY, _baseline),
            Step("propose", MODEL_CALL, lambda state: _propose(state, meter)),
            Step("apply", WRITES, _apply),
        ),
        edges=(
            Edge("review", "retrieve"),
            Edge("retrieve", "baseline"),
            Edge("baseline", "propose", when=_wants_edits),
            Edge("baseline", END),
            Edge("propose", "apply"),
            Edge("apply", "propose", when=_more),
            Edge("apply", END),
        ),
    )


def review(
    *,
    execute=False,
    model=None,
    corpus=None,
    root=None,
    max_chunks=8,
    gate="check-docs",
    runtime=None,
    checkpointer=None,
    run_key="doc_reviewer",
    max_model_calls=None,
):
    """Review the documentation: gather what the deterministic doer found (stale
    stamps, unresolved mentions, every roster row), retrieve the style guide's
    rules from the corpus, and — only with ``execute=True`` — ask the model for
    one bounded edit per chunk and apply it through the gated ``apply_refactor``
    doer, which rolls back unless ``make <gate>`` (default ``check-docs``: the
    structure gate plus strict freshness) stays green.

    Dry-run is the default and never calls a model: the report is real (counts,
    candidates, the prompt the first chunk would get) and nothing is written.
    The loop is durable (one chunk per step, ``FileCheckpointer`` under
    ``wiki/.runtime``); a crash resumes at the cursor. The model comes from
    ``models.get_model(model)`` — never a provider.

    An execute run needs ``max_model_calls``, the approved count, or raises
    ValueError: every model call goes through one ``models.CountedModel`` of
    that count, so the call past it raises ``models.CallCapReached``. A saved
    run is resumed only on the same model and with no more chunks left than
    that count; otherwise ``models.RunNotApproved`` is raised before any step.
    """
    if execute and max_model_calls is None:
        raise ValueError(
            "review(execute=True) needs max_model_calls, the approved model-call count"
        )
    root = root or _REPO
    corpus = corpus or os.path.join(root, _CORPUS)
    if checkpointer is None and execute:
        checkpointer = FileCheckpointer(os.path.join(root, _CKPT_DIR))
    init = {
        "model": model,
        "corpus": corpus,
        "root": root,
        "max_chunks": max_chunks,
        "gate": gate,
        "execute": execute,
    }
    kwargs = {"execute": execute}
    if checkpointer is not None:
        kwargs["checkpointer"] = checkpointer
        kwargs["run_key"] = run_key
        saved = checkpointer.load(run_key)
        if saved is not None:
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
    return DocReviewReport(
        baseline_green=bool(st.get("baseline_green", False)),
        stale=int(st.get("stale", 0)),
        unresolved=int(st.get("unresolved", 0)),
        rosters=int(st.get("rosters", 0)),
        candidates=tuple(st.get("candidates", ())),
        applied=tuple(st.get("applied", ())),
        skipped=tuple(st.get("skipped", ())),
        preview=st.get("preview", ""),
        dry_run=not execute,
    )
