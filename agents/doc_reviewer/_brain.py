"""
title: Doc reviewer brain
layer: backend
public_api: no
summary: Plan: gather the deterministic doc findings (review_docs) -> retrieve the style rules (query_corpus) -> gate a green baseline -> (propose -> apply+gate+rollback) one finding per step; on a durable Runtime. Judgment only where a rule cannot decide. An execute run needs its approved count of model calls: every call goes through one run's models.ModelMeter, and a resumed run is first checked against the approved model and count (models.approve_resume). Every tool child runs through scripts/resource_limits.py run_tool, held to the reviewed root's config/project.json `agents.tool_timeout_seconds` and `agents.tool_max_output_bytes`, the root whose make_targets gate keys the gate runner it starts reads, so the time limit is checked against that runner's own limit: past either its session is ended and the step raises ChildTimedOut or ChildOutputTooLarge naming the key. A finding on a file the corpus does not place at a corpus.served_visibilities level (config_loader.is_served), on a file that states a level outside it on disk now or none that can be read (config_loader.is_served_now over scripts/corpus_level.py stated_now), or on any file when the corpus cannot be read, is withheld: reported with why, never sent. A style-rule retrieval query_corpus refuses, or whose output is not JSON (empty output included), raises RulesRefused, a RuntimeError carrying report()'s three parts, before the baseline gate; so does one that finds no node at all on an execute run (`[]` from a checkout with no corpus, or a corpus with no node for the rule query), so no model is asked for edits with an empty rules section, while a dry run, which asks none, shows that empty section in its preview. review is given a root or a corpus, never both, and scripts/corpus_level.py checkout derives the other before any step (this checkout when neither; a relative path is the caller's directory's), raising NotACheckout for both, for an empty root, for a corpus that is not some checkout's wiki/corpus.json, or for a corpus that does not exist; every step keeps only the root and reads its wiki/corpus.json, so the withholding check and the style-rule retrieval, which hands query_corpus `--root` alone, read one corpus.
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
from scripts import config_loader, corpus_level
from scripts.resource_limits import run_tool

__all__ = ["review", "DocReviewReport", "RulesRefused"]


class RulesRefused(RuntimeError):
    """A style-rule retrieval that cannot give the rules, as report()'s
    three parts."""

    def __init__(self, what, on, next_step):
        super().__init__("%s: %s; %s" % (what, on, next_step))
        self.parts = (what, on, next_step)


_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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
    `skipped` are chunks the model declined or whose edit was rolled back;
    `withheld` are (chunk id, why) pairs for findings never sent to a model,
    because the corpus does not place their file at a served level.
    """

    baseline_green: bool
    stale: int
    unresolved: int
    rosters: int
    candidates: tuple  # tuple[str, ...] — chunk ids, e.g. "mention:docs/a.md:4"
    applied: tuple  # tuple[str, ...] — files whose edit passed the gate
    skipped: tuple  # tuple[str, ...] — chunk ids with no accepted edit
    withheld: tuple  # tuple[tuple[str, str], ...] — (chunk id, why), never sent
    preview: str  # the prompt the first chunk WOULD send (dry-run)
    dry_run: bool


def _run(args, stdin=None, *, root):
    """Invoke a repo script via its CLI (tools are consumed as CLIs, never imported),
    under the interpreter running this agent.
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


def _withhold(root):
    """A function giving, for a document's path, why a finding on it must
    not be sent to a model, or None when it may be.

    A file may be sent only when *root*'s corpus (its
    scripts/corpus_level.py CORPUS_PATH) has a node for
    it, config_loader.is_served keeps every such node at *root*'s
    `corpus.served_visibilities`, and config_loader.is_served_now keeps it at
    the level the file states on disk now (scripts/corpus_level.py
    stated_now), so a file reclassified after the corpus was built is
    withheld at its new level. Fail closed: a corpus or config that cannot
    be read withholds every finding, a file the corpus has no node for is
    withheld, its level unknown, and so is a file whose level on disk cannot
    be read."""
    try:
        served = config_loader.served_visibilities(root)
    except config_loader.ConfigError as exc:
        refused = "corpus.served_visibilities cannot be read (%s)" % (
            "; ".join(exc.lines) or exc.path or config_loader.CONFIG_FILE
        )
        return lambda path: refused
    corpus_path = os.path.join(root, corpus_level.CORPUS_PATH)
    try:
        with open(corpus_path, encoding="utf-8") as fh:
            corpus = json.load(fh)
        nodes = corpus.get("nodes", []) if isinstance(corpus, dict) else None
        if not isinstance(nodes, list):
            raise ValueError("it holds no list of nodes")
    except (OSError, ValueError) as exc:
        unread = "the corpus at %s cannot be read (%s), so no file's level is known" % (
            corpus_path,
            exc,
        )
        return lambda path: unread
    by_path: dict = {}
    for n in nodes:
        if isinstance(n, dict) and n.get("path"):
            by_path.setdefault(n["path"], []).append(n)

    def why(path):
        found = by_path.get(path)
        if not found:
            return "%s has no corpus node, so its level is unknown" % path
        if not all(config_loader.is_served(n, served) for n in found):
            return "%s is at a level outside corpus.served_visibilities" % path
        now = corpus_level.stated_now(root, path)
        if not all(config_loader.is_served_now(n, served, now) for n in found):
            return (
                "%s states a level outside corpus.served_visibilities on disk "
                "now, or none that can be read" % path
            )
        return None

    return why


def _chunks(report, root, max_chunks, withhold):
    """The ordered work list from a review_docs JSON report, unresolved
    mentions then roster rows to judge, as (chunks, withheld): the first
    *max_chunks* findings *withhold* clears, each with its file's text, and a
    (chunk id, why) pair for every finding it does not, whose text is never
    read. Stale stamps are counted (`stale`) but never a chunk: a rule
    decides them, so the deterministic writer clears them
    (`make restamp-docs`), and while one is outstanding `make check-docs` is
    red, so a gated edit could never land and the baseline stops the run."""
    findings = [
        {
            "id": "mention:%s:%d" % (m["path"], m["line"]),
            "kind": "mention",
            "path": m["path"],
            "line": m["line"],
            "finding": "`%s` resolves to nothing" % m["mention"],
            "around": 3,
        }
        for m in report.get("unresolved_mentions", [])
    ] + [
        {
            "id": "roster:%s:%s" % (r["path"], r["member"]),
            "kind": "roster",
            "path": r["path"],
            "line": r["line"],
            "finding": "Not for: %s" % r["not_for"],
            "around": 0,
        }
        for r in report.get("rosters", [])
    ]
    chunks: list = []
    withheld: list = []
    for f in findings:
        why = withhold(f["path"])
        if why is not None:
            withheld.append((f["id"], why))
            continue
        if len(chunks) < max_chunks:
            around = f.pop("around")
            f["text"] = _read_lines(root, f["path"], f["line"], around=around)
            chunks.append(f)
    return chunks, tuple(withheld)


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
        ["scripts/jobs/review_docs.py", "--json", "--root", state["root"]],
        root=state["root"],
    )
    if rc != 0:
        raise RuntimeError("review_docs failed (rc=%d): %s" % (rc, err.strip()))
    try:
        report = json.loads(out) if out.strip() else {}
    except ValueError:
        report = {}
    chunks, withheld = _chunks(
        report,
        state["root"],
        state["max_chunks"],
        _withhold(state["root"]),
    )
    return {
        "stale": len(report.get("findings", [])),
        "unresolved": len(report.get("unresolved_mentions", [])),
        "rosters": len(report.get("rosters", [])),
        "chunks": chunks,
        "candidates": tuple(c["id"] for c in chunks),
        "withheld": withheld,
        "cursor": 0,
        "applied": (),
        "skipped": (),
    }


def _retrieve(state):
    """Read-only: the style guide's rule nodes, from the corpus (query_corpus).
    A refusal, or output that is not JSON (empty output included), raises
    RulesRefused. So does no node at all, `[]` from a checkout with no corpus
    or a corpus with no node for the rule query, on an execute run, so no
    model is asked for edits with an empty rules section; a dry run, which
    asks none, keeps that empty section in its preview."""
    rc, out, err = _run(
        [
            "scripts/query_corpus.py",
            _RULE_QUERY,
            "--max-nodes",
            "6",
            "--root",
            state["root"],
        ],
        root=state["root"],
    )
    if rc != 0:
        raise RulesRefused(
            "the style rules cannot be retrieved",
            "query_corpus exited %d under %s: %s"
            % (rc, state["root"], err.strip() or "it wrote nothing to stderr"),
            "fix what query_corpus names, then rerun",
        )
    try:
        nodes = json.loads(out)
    except ValueError as exc:
        raise RulesRefused(
            "the style rules cannot be retrieved",
            "query_corpus exited 0 under %s with output that is not JSON (%s)"
            % (state["root"], exc),
            "run scripts/query_corpus.py --root on that checkout to see its "
            "output, then rerun",
        ) from exc
    if not nodes and state.get("execute"):
        raise RulesRefused(
            "no style rules were retrieved, so no model is asked for edits",
            "query_corpus found no node for the rule query in the corpus under "
            "%s" % state["root"],
            "run `make site-data` in that checkout so its corpus holds %s, "
            "then rerun" % _GUIDE,
        )
    rules = [
        n for n in nodes if str(n.get("path", "")).endswith(os.path.basename(_GUIDE))
    ] or nodes
    chunks = state.get("chunks", [])
    preview = _propose_prompt(rules, chunks[0]) if chunks else ""
    return {"rules": rules, "preview": preview}


def _baseline(state):
    """Read-only: the gate must be green BEFORE any edit (run_make_target)."""
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
    """Model-call: ONE bounded edit spec for the chunk at the cursor, or a decline,
    from the run's counted backend (*meter*). The chunk's level is asked of
    the corpus again, so a run resumed from a snapshot taken before its file
    left the served levels declines it with no model call."""
    chunk = state["chunks"][state["cursor"]]
    if _withhold(state["root"])(chunk["path"]) is not None:
        return {"spec": None}
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
            root=state["root"],
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

    ``root`` or ``corpus`` names the checkout reviewed, never both
    (scripts/corpus_level.py checkout): ``root`` is the checkout (``None`` =
    this one), ``corpus`` its ``wiki/corpus.json``, a relative one taken
    from the caller's directory. Every step reads that checkout's corpus and
    files; both given, a corpus that does not exist, or one that is not
    some checkout's ``wiki/corpus.json``, raises corpus_level.NotACheckout, a ValueError,
    before any step.
    """
    if execute and max_model_calls is None:
        raise ValueError(
            "review(execute=True) needs max_model_calls, the approved model-call count"
        )
    # Absolute, from the caller's directory: a tool child runs in this
    # checkout. Each step reads the root's corpus, so only the root is kept.
    root, _ = corpus_level.checkout(root, corpus, _REPO)
    if checkpointer is None and execute:
        checkpointer = FileCheckpointer(os.path.join(root, _CKPT_DIR))
    init = {
        "model": model,
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
        withheld=tuple(tuple(pair) for pair in st.get("withheld", ())),
        preview=st.get("preview", ""),
        dry_run=not execute,
    )
