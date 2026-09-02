"""
title: Integration — the doc reviewer agent (dry-run, execute, decline, rollback)
kind: tests
layer: backend
summary: agents.doc_reviewer.review over patched tool and model seams (no subprocess, no model): a dry-run gathers findings, retrieves rules, gates the baseline and writes nothing; execute proposes one edit per chunk and applies through the gated doer; a declined chunk or a red gate lands in skipped; a red baseline attempts nothing. The report the CLI and hook print is this report.
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from agents.doc_reviewer import review  # noqa: E402

pytestmark = pytest.mark.integration

_BRAIN = "agents.doc_reviewer._brain"

_REVIEW = {
    "checked": 3,
    "findings": [
        {
            "path": "docs/a.md",
            "updated": "2026-01-01",
            "expected": "2026-09-02",
            "reason": "stale",
        }
    ],
    "unresolved_mentions": [
        {"path": "docs/b.md", "line": 4, "mention": "scripts/gone.py"}
    ],
    "rosters": [
        {"path": "scripts/README.md", "member": "x.py", "line": 9, "not_for": "n/a"}
    ],
}
_RULES = [
    {
        "node_id": "docs-guides-doc-style#2",
        "path": "docs/guides/doc-style.md",
        "title": "2. Rosters",
        "text_excerpt": "Name the sibling.",
    }
]


class _Runner:
    def __init__(self, baseline_ok=True, gate_ok=True):
        self.baseline_ok, self.gate_ok, self.calls = baseline_ok, gate_ok, []

    def __call__(self, args, stdin=None):
        joined = " ".join(args)
        if "review_docs.py" in joined:
            self.calls.append("review_docs")
            return 0, json.dumps(_REVIEW), ""
        if "query_corpus.py" in joined:
            self.calls.append("query_corpus")
            return 0, json.dumps(_RULES), ""
        if "run_make_target.py" in joined:
            self.calls.append("run_make_target")
            return 0, json.dumps({"ok": self.baseline_ok}), ""
        if "apply_refactor.py" in joined:
            self.calls.append("apply_refactor")
            spec = json.loads(stdin)
            files = [e["file"] for e in spec["edits"]]
            return (
                0,
                json.dumps(
                    {"applied": self.gate_ok, "files": files if self.gate_ok else []}
                ),
                "",
            )
        raise AssertionError("unexpected tool: %s" % joined)


class _Model:
    def __init__(self, reply):
        self.reply, self.prompts = reply, []

    def run(self, prompt, **opts):
        self.prompts.append(prompt)
        return self.reply


_SPEC = json.dumps(
    {
        "edits": [
            {
                "file": "docs/a.md",
                "find": "updated: 2026-01-01",
                "replace": "updated: 2026-09-02",
            }
        ]
    }
)


@pytest.fixture
def seams(monkeypatch, tmp_path):
    runner = _Runner()
    model = _Model(_SPEC)
    monkeypatch.setattr(_BRAIN + "._run", runner)
    monkeypatch.setattr(_BRAIN + ".get_model", lambda name=None: model)
    monkeypatch.setattr(
        _BRAIN + "._read_lines",
        lambda root, relpath, lineno, around=3: "1: ---\n2: updated: 2026-01-01",
    )
    return runner, model, tmp_path


def test_dry_run_gathers_retrieves_gates_and_writes_nothing(seams):
    runner, model, root = seams
    r = review(root=str(root))
    assert r.dry_run and r.baseline_green
    assert (r.stale, r.unresolved, r.rosters) == (1, 1, 1)
    assert r.candidates == (
        "stale:docs/a.md",
        "mention:docs/b.md:4",
        "roster:scripts/README.md:x.py",
    )
    assert (
        "Name the sibling." in r.preview
        and "stale:" not in r.preview
        and "kind: stale" in r.preview
    )
    assert model.prompts == [] and "apply_refactor" not in runner.calls
    assert runner.calls == ["review_docs", "query_corpus", "run_make_target"]


def test_execute_applies_each_accepted_chunk_through_the_gated_doer(seams):
    runner, model, root = seams
    r = review(execute=True, root=str(root), checkpointer=None)
    assert not r.dry_run
    assert len(model.prompts) == 3 and runner.calls.count("apply_refactor") == 3
    assert r.applied == ("docs/a.md",) * 3 and r.skipped == ()


def test_a_declined_chunk_is_skipped_without_touching_apply(seams, monkeypatch):
    runner, model, root = seams
    model.reply = '{"edits": []}'
    r = review(execute=True, root=str(root), max_chunks=1)
    assert r.skipped == ("stale:docs/a.md",) and r.applied == ()
    assert "apply_refactor" not in runner.calls


def test_a_red_gate_rolls_back_so_the_chunk_is_skipped(monkeypatch, tmp_path):
    runner = _Runner(gate_ok=False)
    monkeypatch.setattr(_BRAIN + "._run", runner)
    monkeypatch.setattr(_BRAIN + ".get_model", lambda name=None: _Model(_SPEC))
    monkeypatch.setattr(_BRAIN + "._read_lines", lambda *a, **k: "")
    r = review(execute=True, root=str(tmp_path), max_chunks=1)
    assert r.applied == () and r.skipped == ("stale:docs/a.md",)


def test_a_red_baseline_attempts_nothing(monkeypatch, tmp_path):
    runner = _Runner(baseline_ok=False)
    model = _Model(_SPEC)
    monkeypatch.setattr(_BRAIN + "._run", runner)
    monkeypatch.setattr(_BRAIN + ".get_model", lambda name=None: model)
    monkeypatch.setattr(_BRAIN + "._read_lines", lambda *a, **k: "")
    r = review(execute=True, root=str(tmp_path))
    assert (
        not r.baseline_green
        and model.prompts == []
        and "apply_refactor" not in runner.calls
    )


def test_the_cli_and_hook_report_the_review_and_skip_an_absent_model(
    monkeypatch, capsys, tmp_path
):
    sys.path.insert(0, str(_ROOT / "scripts"))
    sys.path.insert(0, str(_ROOT / "scripts" / "hooks"))
    import doc_review as cli  # noqa: E402
    import on_stop_doc_review as hook  # noqa: E402
    from models import ModelUnavailable

    def no_model(**kwargs):
        raise ModelUnavailable("claude binary 'claude' is not on PATH")

    monkeypatch.setattr(cli, "review", no_model)
    monkeypatch.setattr(hook, "review", no_model)
    assert cli.main(["--execute"]) == 0 and "skipping" in capsys.readouterr().out
    assert (
        hook.main(["payload", "--execute"]) == 0
        and "skipping" in capsys.readouterr().out
    )
