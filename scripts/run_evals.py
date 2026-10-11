#!/usr/bin/env python3
"""
title: Run evals — replay the eval suites, or run them live under the spend cap, and write the report
kind: script
layer: n/a
summary: The command line `make eval` (--mode replay) and `make eval-live` (--mode live) run; it calls the evals package and holds no judging logic. It reads config/project.json `evals`, refuses a report_dir git does not ignore before writing anything, writes a red placeholder report first so a crash never leaves an earlier green one standing, and removes the earlier report (and, live, the earlier candidates) when the `evals` block is refused, since a refused block cannot say how to write one, then judges every suite and replaces `<evals.report_dir>/<mode>.json` whole with the canonical report. A live run first deletes `<evals.report_dir>/live-candidates/`, then writes one candidate file per suite there, one canonical case line per answered case; it never edits the tracked dataset. Exit 0 when every suite passed, 1 on any fail, 2 when the run was refused (config, dataset, the call cap, a null or unknown model, an unignored report_dir), and 3 when the live backend is absent. It starts no process itself; a model adapter does, through scripts/child_env.py.
effect: writes
rerun: fixed-point
rerun_proof: test:tests/integration/test_evals_gate.py
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections.abc import Sequence

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
sys.path.insert(0, _HERE)
sys.path.insert(0, _REPO)

import git_tree  # noqa: E402 — the one definition of what git ignores
from evals import (  # noqa: E402
    ConfigError,
    DatasetError,
    EvalConfig,
    Report,
    SpendCapExceeded,
    SuiteResult,
    aggregate,
    load_config,
    load_suites,
    render,
    replay,
    run_live,
)

# The live run's candidate lines go here, under evals.report_dir, so they share
# its ignore rule; the directory is rebuilt whole each live run.
_CANDIDATES = "live-candidates"


def _write(root: str, rel: str, text: str) -> None:
    # Written beside it, then renamed, so a reader never sees half a report.
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def _report(
    cfg: EvalConfig,
    mode: str,
    result: str,
    reasons: Sequence[str],
    *,
    calls: int = 0,
    detail: str | None = None,
    suites: Sequence[SuiteResult] = (),
) -> Report:
    return Report(
        schema=cfg.report_schema,
        schema_version=cfg.report_schema_version,
        mode=mode,
        model=cfg.live_model if mode == "live" else None,
        threshold=cfg.threshold,
        calls=calls,
        result=result,
        reasons=sorted(set(reasons)),
        detail=detail,
        suites=list(suites),
    )


def _unignored(root: str, paths: Sequence[str]) -> list[str]:
    try:
        return [p for p in paths if not git_tree.is_ignored(root, p)]
    except git_tree.NoGitError:
        # No git, no tracked tree to dirty: nothing for the guard to protect.
        return []


def _candidate_lines(lines: Sequence[dict[str, object]]) -> str:
    return "".join(
        json.dumps(c, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
        for c in lines
    )


def _summary(rel: str, report: Report) -> None:
    for s in sorted(report.suites, key=lambda s: s.name):
        reasons = " (%s)" % ", ".join(s.reasons) if s.reasons else ""
        print(
            "eval %s: %d/%d passed, %s%s"
            % (s.name, s.passed, s.total, s.result, reasons)
        )
    if report.detail:
        print("eval: %s" % report.detail)
    print("eval %s: %s -> %s" % (report.mode, report.result, rel))


def _remove_stale(root: str, report_dir: str | None, mode: str) -> None:
    # A refused evals block cannot say how to write a report (the schema and
    # its version are part of what was refused), so the earlier report goes
    # rather than stand green beside a refused run. Only an ignored path is
    # touched: git's ignore rule is what makes it ours to delete.
    if report_dir is None:
        print(
            "run_evals: `evals.report_dir` is unusable, so an earlier report "
            "may still stand; trust this exit code, not that file",
            file=sys.stderr,
        )
        return
    stale = ["%s/%s.json" % (report_dir, mode)]
    if mode == "live":
        stale.append("%s/%s" % (report_dir, _CANDIDATES))
    probes = [p if p.endswith(".json") else p + "/x.jsonl" for p in stale]
    if _unignored(root, probes):
        return
    for rel in stale:
        path = os.path.join(root, rel)
        if os.path.isdir(path):
            shutil.rmtree(path)
        elif os.path.exists(path):
            os.remove(path)
        else:
            continue
        print("run_evals: removed the earlier %s" % rel, file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the eval suites in the requested mode; the exit code is the verdict."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    parser.add_argument("--mode", choices=("replay", "live"), default="replay")
    parser.add_argument(
        "--root", default=None, help="project root (default: this file's repo)"
    )
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root or _REPO)
    mode = args.mode
    try:
        cfg = load_config(root)
    except ConfigError as exc:
        print("run_evals: %s" % exc, file=sys.stderr)
        _remove_stale(root, exc.report_dir, mode)
        return 2

    rel = "%s/%s.json" % (cfg.report_dir, mode)
    candidates_dir = "%s/%s" % (cfg.report_dir, _CANDIDATES)
    guarded = [rel, rel + ".tmp"]
    if mode == "live":
        guarded.append(candidates_dir + "/x.jsonl")
    loose = _unignored(root, guarded)
    if loose:
        print(
            "run_evals: config/project.json `evals.report_dir` %r is not git-ignored "
            "(%s); a report there would dirty the tree, so nothing was written"
            % (cfg.report_dir, ", ".join(loose)),
            file=sys.stderr,
        )
        return 2

    placeholder = _report(
        cfg, mode, "incomplete", ["incomplete"], detail="the run did not finish"
    )
    _write(root, rel, render(placeholder))
    if mode == "live" and os.path.isdir(os.path.join(root, candidates_dir)):
        # Candidates are one run's output: an earlier run's must not sit beside
        # this one's, or a refused run would leave old lines looking current.
        shutil.rmtree(os.path.join(root, candidates_dir))

    try:
        suites = load_suites(cfg, root)
    except DatasetError as exc:
        report = _report(cfg, mode, "refused", ["refused"], detail=str(exc))
        _write(root, rel, render(report))
        _summary(rel, report)
        return 2

    if mode == "replay":
        results = replay(suites, cfg.threshold)
        calls = 0
    else:
        try:
            run = run_live(suites, cfg)
        except ConfigError as exc:
            report = _report(cfg, mode, "refused", ["refused"], detail=str(exc))
            _write(root, rel, render(report))
            _summary(rel, report)
            return 2
        except SpendCapExceeded as exc:
            report = _report(
                cfg, mode, "refused", ["cap-exceeded"], calls=exc.calls, detail=str(exc)
            )
            _write(root, rel, render(report))
            _summary(rel, report)
            return 2
        results, calls = run.results, run.calls
        for suite_name, lines in run.candidates:
            _write(
                root,
                "%s/%s.jsonl" % (candidates_dir, suite_name),
                _candidate_lines(lines),
            )

    result, reasons = aggregate(results)
    report = _report(cfg, mode, result, reasons, calls=calls, suites=results)
    _write(root, rel, render(report))
    _summary(rel, report)
    if result == "pass":
        return 0
    if result == "fail":
        return 1
    if result == "absent":
        return 3
    return 2


if __name__ == "__main__":
    sys.exit(main())
