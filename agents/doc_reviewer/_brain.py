"""
title: Doc reviewer brain
layer: backend
public_api: no
summary: Plan: gather the deterministic doc findings (review_docs) -> retrieve the style rules (query_corpus) -> gate a green baseline -> (propose -> apply+gate+rollback) one finding per step; on a durable Runtime. Judgment only where a rule cannot decide.
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
    candidates: tuple  # tuple[str, ...] — chunk ids, e.g. "stale:docs/a.md"
    applied: tuple  # tuple[str, ...] — files whose edit passed the gate
    skipped: tuple  # tuple[str, ...] — chunk ids with no accepted edit
    preview: str  # the prompt the first chunk WOULD send (dry-run)
    dry_run: bool


def _run(args, stdin=None):
    """Invoke a repo script via its CLI (tools are consumed as CLIs, never imported),
    under the interpreter running this agent."""
    proc = subprocess.run(
        [sys.executable] + args, cwd=_REPO, capture_output=True, text=True, input=stdin
    )
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
    """The ordered work list from a review_docs JSON report: stale stamps first
    (mechanical), then unresolved mentions, then roster rows to judge."""
    stale = [
        {
            "id": "stale:%s" % f["path"],
            "kind": "stale",
            "path": f["path"],
            "line": 1,
            "finding": f["reason"],
            "text": _read_lines(root, f["path"], 1, around=14),
        }
        for f in report.get("findings", [])
    ]
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
    return (stale + mentions + rosters)[:max_chunks]


def _propose_prompt(rules, chunk, gate):
    """The per-chunk prompt: the guide's rules + one finding + the text it is about."""
    rule_text = "\n\n".join(
        "## %s\n%s"
        % (n.get("title", ""), n.get("text_excerpt") or n.get("summary") or "")
        for n in rules
    )
    return (
        _system_prompt()
        + "\n\n# Rules (from docs/guides/doc-style.md, via the corpus)\n%s"
        "\n\n# Chunk to review\nkind: %s\npath: %s\nline: %d\nfinding: %s\ngate: %s\n---\n%s\n"
        % (
            rule_text,
            chunk["kind"],
            chunk["path"],
            chunk["line"],
            chunk["finding"],
            gate,
            chunk["text"],
        )
    )


def _parse_spec(reply, gate):
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
    data.setdefault("gate", gate)
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
    preview = _propose_prompt(rules, chunks[0], state["gate"]) if chunks else ""
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


def _propose(state):
    """Model-call: ONE bounded edit spec for the chunk at the cursor, or a decline."""
    chunk = state["chunks"][state["cursor"]]
    reply = get_model(state.get("model")).run(
        _propose_prompt(state.get("rules", []), chunk, state["gate"])
    )
    return {"spec": _parse_spec(reply, state["gate"])}


def _apply(state):
    """Writes: apply the spec through the gated doer (rolled back unless the gate
    stays green), advance the cursor."""
    chunk = state["chunks"][state["cursor"]]
    applied = list(state.get("applied", ()))
    skipped = list(state.get("skipped", ()))
    spec = state.get("spec")
    if spec:
        _, out, _ = _run(
            [
                "scripts/apply_refactor.py",
                "--spec",
                "-",
                "--root",
                state["root"],
                "--gate",
                state["gate"],
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


_PLAN = Plan(
    name="doc_reviewer",
    entry="review",
    steps=(
        Step("review", READ_ONLY, _review),
        Step("retrieve", READ_ONLY, _retrieve),
        Step("baseline", READ_ONLY, _baseline),
        Step("propose", MODEL_CALL, _propose),
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
    """
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
        if checkpointer.load(run_key) is not None:
            kwargs["resume"] = None
    st = get_runtime(runtime).run(_PLAN, init, **kwargs).state
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
