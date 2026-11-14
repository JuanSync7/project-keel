"""
title: Index enforcer brain
layer: backend
public_api: no
summary: Plan: gate -> build -> link -> report -> (durable fill loop) -> commit; run on a neutral Runtime. A filling run needs its approved count of model calls: every fill goes through one run's models.ModelMeter, and a resumed run is first checked against the approved model and count (models.approve_resume). Every tool child runs through scripts/resource_limits.py run_tool, held to config/project.json `agents.tool_timeout_seconds` and `agents.tool_max_output_bytes`: past either its session is ended and the step raises ChildTimedOut or ChildOutputTooLarge naming the key. The fill sends only gaps at a level in config/project.json corpus.served_visibilities as the file under the run's root states it on disk now (scripts/config_loader.py is_served_now over scripts/corpus_level.py stated_now, read once per path), on a fresh run and on a resumed one, so a hidden gap, a file made stricter since the corpus was built and a file whose level cannot be read are reported and never filled, and a resumed run's approved count (models.approve_resume) counts only the gaps it would fill. A saved run is resumed only with the execute and fix_gaps it was started with, else models.RunNotApproved before any step with the snapshot kept: a resume routes by the snapshot's flags and serves this call's levels. A nonzero build_corpus.py or link_corpus.py status raises the same ToolReportUnreadable before report and fill. The commit writes into the corpus under the run's root as it is on disk at commit time, never over it: each summary the run generated is copied onto the node with the same node_id only while that node is still a served gap with the same path and text_excerpt, so a corpus built after a crash survives a resume, an authored summary is never touched, a node or edge is never added or removed, and the report's gaps_filled counts only the summaries written. A corpus absent at commit raises ToolReportUnreadable before any write, so the snapshot is kept for a resume after a rebuild. A failed owner status or an unreadable owner list raises scripts/tool_reports.py ToolReportUnreadable before fill or commit; a nonzero structure status without ERROR lines raises the same error before build. An absent corpus gives a readable empty owner list.
effect: writes
rerun: fixed-point
rerun_proof: test:tests/integration/test_index_enforcer_durability.py
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass

from models import ModelBackend, ModelMeter, RunNotApproved, approve_resume, get_model
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
from scripts import config_loader, corpus_level, tool_reports
from scripts.resource_limits import run_tool

__all__ = ["enforce", "summarize_gap", "EnforceReport"]

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CORPUS = os.path.join("wiki", "corpus.json")
_CKPT_DIR = os.path.join("wiki", ".runtime")  # gitignored; durable fill snapshots


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
    Bounded by scripts/resource_limits.py run_tool: past config/project.json
    agents.tool_timeout_seconds or agents.tool_max_output_bytes the child's
    session is ended and ChildTimedOut or ChildOutputTooLarge names the key.
    """
    proc = run_tool([sys.executable] + args, cwd=_REPO)
    return proc.returncode, proc.stdout, proc.stderr


def _load_corpus(root):
    path = os.path.join(root, _CORPUS)
    if not os.path.exists(path):
        return {"nodes": []}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _system_prompt():
    with open(
        os.path.join(os.path.dirname(__file__), "prompt.md"), encoding="utf-8"
    ) as fh:
        return fh.read()


def _gap_prompt(node):
    return (
        _system_prompt()
        + "\n\n# Task\nWrite ONE plain sentence summarizing the node below, "
        "using only its own text. Output the sentence and nothing else.\n\n"
        "title: %s\npath: %s\n---\n%s\n"
        % (node.get("title", ""), node.get("path", ""), node.get("text_excerpt", ""))
    )


def summarize_gap(node: dict, *, backend: ModelBackend) -> str:
    """The agent's one model call: a one-sentence summary of a corpus *node*
    (its title, path and text excerpt) from *backend*, stripped. The plan's
    fill step and the eval harness (evals/_doers.py) both call it."""
    return backend.run(_gap_prompt(node)).strip()


def _ungapped(corpus):
    """Nodes still missing a summary_source, in corpus order (the gaps the
    report lists)."""
    return [n for n in corpus.get("nodes", []) if not n.get("summary_source")]


def _fillable(corpus, served, root):
    """The gaps at a level in *served*, in corpus order: the fill work-list.
    A gap is kept only when config_loader.is_served_now holds over the level
    its file under *root* states on disk now (scripts/corpus_level.py
    stated_now, read once per path), so a hidden gap, a corpus row with no
    `visibility` field, a file made stricter since the corpus was built and a
    file whose level cannot be read never reach summarize_gap: their text is
    in no prompt, and each stays a reported gap for its owner to author."""
    stated = {}
    fillable = []
    for node in _ungapped(corpus):
        path = node.get("path")
        if path not in stated:
            stated[path] = corpus_level.stated_now(root, path)
        if config_loader.is_served_now(node, served, stated[path]):
            fillable.append(node)
    return fillable


# --- plan steps: each returns a dict merged into the run state -----------------
# Deterministic logic stays in pure-stdlib scripts/ doers invoked as CLIs; these
# steps orchestrate them. The model is reached only in the one MODEL_CALL step,
# so the runtime skips it (and the WRITES steps) unless execute=True.


def _gate(state):
    """Read-only: capture structure findings; a crash without errors is unreadable."""
    rc, out, err = _run(["scripts/check_structure.py", "--root", state["root"]])
    errors = tuple(ln[6:] for ln in out.splitlines() if ln.startswith("ERROR "))
    if rc != 0 and not errors:
        raise tool_reports.ToolReportUnreadable(
            "scripts/check_structure.py gave the agent no readable report",
            "scripts/check_structure.py exited %d under %s without ERROR lines; its stderr: %s"
            % (rc, state["root"], err.strip() or "(empty)"),
            "run scripts/check_structure.py on that checkout to see its output, then rerun",
        )
    return {
        "s_errors": errors,
        "s_warnings": tuple(
            ln[6:].strip() for ln in out.splitlines() if ln.startswith("WARN  ")
        ),
    }


def _require_ok(tool, rc, err, root):
    """Raise ToolReportUnreadable when the write tool *tool* exited nonzero
    (*rc*), so no step after it reads or fills a corpus it failed to write."""
    if rc != 0:
        raise tool_reports.ToolReportUnreadable(
            "%s failed" % tool,
            "%s exited %d under %s; its stderr: %s"
            % (tool, rc, root, err.strip() or "(empty)"),
            "fix what %s names, then rerun" % tool,
        )


def _build(state):
    """Writes: (re)build the wiki corpus tree; a failed build raises
    ToolReportUnreadable before report and fill."""
    rc, _, err = _run(
        [
            "scripts/jobs/build_corpus.py",
            "--root",
            state["root"],
            "--out",
            os.path.join(state["root"], _CORPUS),
        ]
    )
    _require_ok("scripts/jobs/build_corpus.py", rc, err, state["root"])
    return {}  # no state update -- same empty-update form as _fill_one


def _link(state):
    """Writes: add deterministic entity/keyword link edges to the corpus; a
    failed link raises ToolReportUnreadable before report and fill."""
    rc, _, err = _run(
        [
            "scripts/jobs/link_corpus.py",
            "--corpus",
            os.path.join(state["root"], _CORPUS),
        ]
    )
    _require_ok("scripts/jobs/link_corpus.py", rc, err, state["root"])
    return {}  # no state update -- same empty-update form as _fill_one


def _report(state):
    """Read-only: enumerate gaps; failed or unreadable owner reports raise
    ToolReportUnreadable before any fill or commit."""
    corpus = _load_corpus(state["root"])
    nodes = corpus.get("nodes", [])
    summary_gaps = tuple(n["node_id"] for n in _ungapped(corpus))
    # Owner gaps come from the declared accountability_report tool (its CLI),
    # not a re-implemented predicate here -- read-only, so safe in dry-run too.
    corpus_path = os.path.join(state["root"], _CORPUS)
    rc, ar_out, err = _run(
        ["scripts/accountability_report.py", "--corpus", corpus_path, "--json"]
    )
    if rc != 0:
        raise tool_reports.ToolReportUnreadable(
            "scripts/accountability_report.py failed",
            "scripts/accountability_report.py exited %d under %s; its stderr: %s"
            % (rc, state["root"], err.strip() or "(empty)"),
            "fix what scripts/accountability_report.py names, then rerun",
        )
    owners = tool_reports.read_report(
        "scripts/accountability_report.py",
        rc,
        ar_out,
        err,
        state["root"],
        container=list,
    )
    owner_gaps = tuple(n["node_id"] for n in owners)
    return {
        "corpus": corpus,
        "nodes": nodes,
        "summary_gaps": summary_gaps,
        "owner_gaps": owner_gaps,
        "gaps_filled": 0,
    }


def _fill_one(state, meter, served):
    """Model-call: fill the NEXT single missing summary at a level in
    *served*, in memory, from the run's counted backend (*meter*).

    One gap per step (not the whole loop) so the runtime checkpoints after each
    fill -- a crash mid-fill (e.g. an EDR SIGKILL) resumes at the cursor and the
    already-filled gaps are not recomputed. The work-list is recomputed from the
    corpus each call, so it is idempotent and resume-safe. Authored summaries are
    never touched (only nodes lacking summary_source are filled).
    """
    corpus = state["corpus"]
    todo = _fillable(corpus, served, state["root"])
    if not todo:
        return {}
    node = todo[0]
    node["summary"] = summarize_gap(node, backend=meter.backend())
    node["summary_source"] = "generated"  # never "authored"
    return {"corpus": corpus, "gaps_filled": state.get("gaps_filled", 0) + 1}


def _filled_onto(disk, run, served, root):
    """Copy the summaries *run* generated onto the nodes of the corpus *disk*
    (mutated), and return how many were copied. A summary is copied only when
    the disk node with the same node_id is still a served gap
    (`_fillable` over *disk*) whose path and text_excerpt are the ones the
    summary was made from; any other filled summary describes text or a level
    the corpus on disk no longer has, and is dropped."""
    fillable = {id(n) for n in _fillable(disk, served, root)}
    by_id = {n.get("node_id"): n for n in disk.get("nodes", [])}
    written = 0
    for node in run.get("nodes", []):
        if node.get("summary_source") != "generated":
            continue
        target = by_id.get(node.get("node_id"))
        if (
            target is None
            or id(target) not in fillable
            or target.get("path") != node.get("path")
            or target.get("text_excerpt") != node.get("text_excerpt")
        ):
            continue
        target["summary"] = node["summary"]
        target["summary_source"] = "generated"
        written += 1
    return written


def _commit(state, served):
    """Writes: merge the run's filled summaries into the corpus on disk now,
    never over it. The corpus under the run's root is read at commit time and
    each summary the run generated is copied onto the node with the same
    node_id only while that node is still a served gap with the same path and
    text_excerpt (`_filled_onto`); an authored summary is never touched and no
    node or edge is added or removed, so a corpus built after a crash survives
    a resume. The file is written deterministically (sorted keys), so a second
    commit of the same inputs writes the same bytes. Returns `gaps_filled`,
    the count of summaries written. A corpus absent at commit raises
    ToolReportUnreadable before any write, so the runtime keeps the snapshot
    and the paid summaries in it resume after a rebuild."""
    path = os.path.join(state["root"], _CORPUS)
    if not os.path.exists(path):
        raise tool_reports.ToolReportUnreadable(
            "the corpus to commit into is missing",
            "%s is absent under %s at commit" % (_CORPUS, state["root"]),
            "rebuild it with scripts/jobs/build_corpus.py, then rerun to resume"
            " from the kept snapshot",
        )
    disk = _load_corpus(state["root"])
    written = _filled_onto(disk, state["corpus"], served, state["root"])
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(disk, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return {"gaps_filled": written}


# --- the plan: control flow as data, with a durable fill loop ------------------
# Each clause of the route is a named edge predicate rather than one inline
# `if execute and ... and not s_errors`, so the runtime reads the plan as data.
# `execute` is the runtime's job for the dry-run guard
# AND a domain-state key so the loop predicate is engine-neutral (the runtime's
# internal flag isn't visible to edge predicates).


def _clean(state):
    """True when the structure gate found no errors."""
    return not state.get("s_errors")


def _wants_fill(state, served):
    """True when gap-fill is requested and there is a clean tree with gaps
    at a level in *served*."""
    return (
        bool(state.get("fix_gaps"))
        and bool(_fillable(state.get("corpus", {}), served, state["root"]))
        and not state.get("s_errors")
    )


def _more_to_fill(state, served):
    """True when authorized to fill and at least one gap at a level in
    *served* remains (loop guard)."""
    return bool(state.get("execute")) and bool(
        _fillable(state.get("corpus", {}), served, state["root"])
    )


def _plan(meter, served):
    """The enforce plan, its fill step bound to this run's counted backend
    and the levels *served* it may send: both are the run's own, never values
    a step builds from saved state."""
    return Plan(
        name="index_enforce",
        entry="gate",
        steps=(
            Step("gate", READ_ONLY, _gate),
            Step("build", WRITES, _build),
            Step("link", WRITES, _link),
            Step("report", READ_ONLY, _report),
            Step("fill", MODEL_CALL, lambda state: _fill_one(state, meter, served)),
            Step("commit", WRITES, lambda state: _commit(state, served)),
        ),
        edges=(
            Edge("gate", "build", when=_clean),  # clean tree -> rebuild
            Edge("gate", "report"),  # dirty tree -> straight to report
            Edge("build", "link"),
            Edge("link", "report"),
            Edge("report", "fill", when=lambda state: _wants_fill(state, served)),
            Edge("report", END),
            # durable loop: one gap per step
            Edge("fill", "fill", when=lambda state: _more_to_fill(state, served)),
            Edge("fill", "commit"),
            Edge("commit", END),
        ),
    )


def _same_flags(saved, execute, fix_gaps, where):
    """Pass a saved run, at *where*, whose *saved* state was started with this
    call's *execute* and *fix_gaps*. Raises models.RunNotApproved otherwise: a
    resume routes by the snapshot's flags but sends the levels this call
    serves, so it would clear the snapshot over summaries it never wrote."""
    was = (saved.get("execute"), saved.get("fix_gaps"))
    if was != (execute, fix_gaps):
        raise RunNotApproved(
            "the saved run was started with execute=%r, fix_gaps=%r, not the"
            " execute=%r, fix_gaps=%r this run asks" % (was + (execute, fix_gaps)),
            where,
            "run again with execute=%r and fix_gaps=%r to resume, or remove %s to"
            " start afresh" % (was + (where,)),
        )


def enforce(
    *,
    execute=False,
    fix_gaps=False,
    model=None,
    root=None,
    runtime=None,
    checkpointer=None,
    run_key="index_enforce",
    max_model_calls=None,
):
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

    A filling run (``execute=True`` and ``fix_gaps=True``, the only run that
    reaches the model) needs ``max_model_calls``, the approved count, or
    raises ValueError: every fill goes through one ``models.CountedModel`` of
    that count, so the call past it raises ``models.CallCapReached``. A saved
    run is resumed only with the execute and fix_gaps it was started with
    (any call that passes a checkpointer), on the same model and with no
    more fills left than that count, a fill being a gap whose file under *root* states a served
    level now; otherwise ``models.RunNotApproved`` is raised before any step.
    A nonzero build or link status raises ``ToolReportUnreadable`` before the
    report step.
    """
    if execute and fix_gaps and max_model_calls is None:
        raise ValueError(
            "enforce(execute=True, fix_gaps=True) needs max_model_calls, "
            "the approved model-call count"
        )
    root = os.path.abspath(root or _REPO)
    # Read only when a fill is asked for: a run without fix_gaps never reaches
    # the fill step, so it needs no levels and fills nothing. A refused or
    # unreadable config raises config_loader.ConfigError before any step.
    served = config_loader.served_visibilities(root) if fix_gaps else frozenset()
    if checkpointer is None and execute and fix_gaps:
        checkpointer = FileCheckpointer(os.path.join(root, _CKPT_DIR))
    init = {"root": root, "model": model, "fix_gaps": fix_gaps, "execute": execute}
    kwargs = {"execute": execute}
    if checkpointer is not None:
        kwargs["checkpointer"] = checkpointer
        kwargs["run_key"] = run_key
        saved = checkpointer.load(run_key)
        if saved is not None:  # a prior run crashed -> resume
            _same_flags(saved["state"], execute, fix_gaps, checkpointer.where(run_key))
            if execute and fix_gaps:
                left = saved["state"]
                approve_resume(
                    where=checkpointer.where(run_key),
                    saved_model=left.get("model"),
                    model=model,
                    # One fill per gap the run would still make from the saved
                    # corpus, the one in flight at the crash included; a gap
                    # whose file is now stricter or unreadable is no fill.
                    # Levels are read under the saved root, the one the fill
                    # steps read, so the count and the fills cannot disagree.
                    left=len(_fillable(left.get("corpus", {}), served, left["root"])),
                    cap=max_model_calls,
                )
            kwargs["resume"] = None
    meter = ModelMeter(model, max_model_calls or 0, get_model)
    st = get_runtime(runtime).run(_plan(meter, served), init, **kwargs).state
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
