"""
title: Unit — the index enforcer's model step runs on an injected backend
kind: tests
layer: n/a
summary: index_enforcer.summarize_gap(node, backend=b) sends b the agent's real gap prompt (its prompt.md preamble, the one-sentence task and the node's title, path and text excerpt) and returns b's reply stripped; the plan's fill step calls the same function, so the eval harness judges the code enforce() runs.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from agents.index_enforcer import enforce, summarize_gap  # noqa: E402
from models import ModelBackend  # noqa: E402
from scripts.tool_reports import ToolReportUnreadable  # noqa: E402

pytestmark = pytest.mark.unit


class _Seen(ModelBackend):
    name = "seen"

    def __init__(self, reply):
        self.reply = reply
        self.prompts = []

    def run(self, prompt, **opts):
        self.prompts.append(prompt)
        return self.reply


def test_summarize_gap_sends_the_real_prompt_and_strips_the_reply():
    node = {
        "title": "Ingest",
        "path": "src/ingest.py",
        "text_excerpt": "def ingest(): ...",
    }
    seen = _Seen("\n Reads events into the queue.  \n")
    assert summarize_gap(node, backend=seen) == "Reads events into the queue."
    (prompt,) = seen.prompts
    preamble = (_ROOT / "agents" / "index_enforcer" / "prompt.md").read_text("utf-8")
    assert prompt.startswith(preamble)
    assert "Write ONE plain sentence" in prompt
    assert "title: Ingest\npath: src/ingest.py\n---\ndef ingest(): ..." in prompt


def test_owner_report_uses_the_corpus_under_the_agent_root(tmp_path, monkeypatch):
    corpus = tmp_path / "wiki" / "corpus.json"
    corpus.parent.mkdir()
    corpus.write_text('{"nodes": []}', "utf-8")
    calls = []

    def run(args):
        calls.append(args)
        return (
            (0, "[]", "")
            if args[0] == "scripts/accountability_report.py"
            else (0, "", "")
        )

    monkeypatch.setattr("agents.index_enforcer._brain._run", run)
    enforce(root=str(tmp_path))
    owner_calls = [
        args for args in calls if args[0] == "scripts/accountability_report.py"
    ]
    assert owner_calls == [
        ["scripts/accountability_report.py", "--corpus", str(corpus), "--json"]
    ]


@pytest.mark.parametrize("relative", [False, True], ids=["absolute", "relative"])
def test_every_tool_uses_the_absolute_agent_root(tmp_path, monkeypatch, relative):
    root = tmp_path / "rel"
    corpus = root / "wiki" / "corpus.json"
    corpus.parent.mkdir(parents=True)
    corpus.write_text('{"nodes": []}', "utf-8")
    monkeypatch.chdir(tmp_path)
    calls = []

    def run(args):
        calls.append(args)
        return (
            (0, "[]", "")
            if args[0] == "scripts/accountability_report.py"
            else (0, "", "")
        )

    monkeypatch.setattr("agents.index_enforcer._brain._run", run)
    report = enforce(root="rel" if relative else str(root), execute=True)
    assert calls == [
        ["scripts/check_structure.py", "--root", str(root)],
        [
            "scripts/jobs/build_corpus.py",
            "--root",
            str(root),
            "--out",
            str(corpus),
        ],
        ["scripts/jobs/link_corpus.py", "--corpus", str(corpus)],
        ["scripts/accountability_report.py", "--corpus", str(corpus), "--json"],
    ]
    assert report.corpus_path == "wiki/corpus.json"


@pytest.mark.parametrize("execute", [False, True], ids=["dry-run", "execute"])
@pytest.mark.parametrize(
    "out",
    ["not JSON", "", "{}", "[1]", "no corpus at wiki/corpus.json; unexpected"],
    ids=["non-JSON", "blank", "object", "non-object-member", "other-notice"],
)
def test_unreadable_owner_report_fails_the_run(tmp_path, monkeypatch, execute, out):
    """A broken tool raises the shared refusal, never a clean owner-gap report."""
    corpus = tmp_path / "wiki" / "corpus.json"
    corpus.parent.mkdir()
    corpus.write_text('{"nodes": []}', "utf-8")

    def run(args):
        if args[0] == "scripts/accountability_report.py":
            return 0, out, "owner report diagnostic"
        return 0, "", ""

    monkeypatch.setattr("agents.index_enforcer._brain._run", run)
    with pytest.raises(ToolReportUnreadable, match="accountability_report") as raised:
        enforce(root=str(tmp_path), execute=execute)
    assert str(tmp_path) in raised.value.parts[1]
    assert "exited 0" in raised.value.parts[1]
    assert "owner report diagnostic" in raised.value.parts[1]
    assert all(part.strip() for part in raised.value.parts)


@pytest.mark.parametrize("execute", [False, True], ids=["dry-run", "execute"])
def test_absent_corpus_skips_the_owner_tool(tmp_path, monkeypatch, execute):
    calls = []

    def run(args):
        calls.append(args)
        return (
            (0, "[]", "")
            if args[0] == "scripts/accountability_report.py"
            else (0, "", "")
        )

    monkeypatch.setattr("agents.index_enforcer._brain._run", run)
    report = enforce(root=str(tmp_path), execute=execute)
    assert not any(args[0] == "scripts/accountability_report.py" for args in calls)
    assert report.nodes == 0 and report.owner_gaps == ()
    assert report.dry_run is not execute


@pytest.mark.parametrize("execute", [False, True], ids=["dry-run", "execute"])
def test_existing_corpus_rejects_a_no_corpus_notice(tmp_path, monkeypatch, execute):
    corpus = tmp_path / "wiki" / "corpus.json"
    corpus.parent.mkdir()
    corpus.write_text('{"nodes": []}', "utf-8")

    def run(args):
        if args[0] == "scripts/accountability_report.py":
            return 0, "no corpus at wiki/corpus.json; run build_corpus.py first.\n", ""
        return 0, "", ""

    monkeypatch.setattr("agents.index_enforcer._brain._run", run)
    with pytest.raises(ToolReportUnreadable, match="accountability_report"):
        enforce(root=str(tmp_path), execute=execute)


def test_unreadable_owner_report_with_failed_status_fails_the_run(
    tmp_path, monkeypatch
):
    corpus = tmp_path / "wiki" / "corpus.json"
    corpus.parent.mkdir()
    corpus.write_text('{"nodes": []}', "utf-8")

    def run(args):
        if args[0] == "scripts/accountability_report.py":
            return 1, "not JSON", "owner report diagnostic"
        return 0, "", ""

    monkeypatch.setattr("agents.index_enforcer._brain._run", run)
    with pytest.raises(ToolReportUnreadable, match="exited 1"):
        enforce(root=str(tmp_path))
