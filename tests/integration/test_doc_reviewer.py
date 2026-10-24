"""
title: Integration — the doc reviewer agent (dry-run, execute, decline, rollback)
kind: tests
layer: backend
summary: agents.doc_reviewer.review over patched tool and model seams (no subprocess, no model): a dry-run gathers findings, retrieves rules, gates the baseline and writes nothing; execute proposes one edit per chunk and applies through the gated doer; a declined chunk or a red gate lands in skipped; a red baseline attempts nothing; a reply that names a gate is declined, the prompt never states the gate, and every apply is bound to its chunk's own file with `--allow`. Every tool call hands the reviewed root to the runner, so run_tool reads the tool limits, and checks them against the gate keys, of the tree the gate runner reads. The report the CLI and hook print is this report. A finding on a file the corpus places outside corpus.served_visibilities, or has no node for, or on any file when the corpus or config cannot be read, is withheld: reported with why (one CLI line each, a count in the hook's line), its text never read, and no prompt or apply made, dry run and execute alike, while a served finding beside it still goes; a chunk queued before its file left the served levels is declined at propose with no model call.
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from agents.doc_reviewer import DocReviewReport, review  # noqa: E402
from models import ModelMeter  # noqa: E402

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


def _project(root, nodes=None):
    """A scratch project at *root*: an empty config/project.json, so the
    served levels are the shipped default, and a corpus whose doc nodes are
    *nodes* (path -> visibility), by default each file _REVIEW names at
    `internal`."""
    if nodes is None:
        nodes = {"docs/b.md": "internal", "scripts/README.md": "internal"}
    (root / "config").mkdir(exist_ok=True)
    (root / "config" / "project.json").write_text("{}")
    (root / "wiki").mkdir(exist_ok=True)
    corpus = {
        "nodes": [
            {"node_id": path, "path": path, "kind": "doc", "visibility": level}
            for path, level in nodes.items()
        ]
    }
    (root / "wiki" / "corpus.json").write_text(json.dumps(corpus))


class _Runner:
    def __init__(self, baseline_ok=True, gate_ok=True, review=None):
        self.baseline_ok, self.gate_ok, self.calls = baseline_ok, gate_ok, []
        self.review = _REVIEW if review is None else review
        self.argvs = {}
        self.roots = []

    def __call__(self, args, stdin=None, *, root):
        self.roots.append(root)
        joined = " ".join(args)
        tool = next((a for a in args if a.endswith(".py")), "")
        self.argvs.setdefault(tool.rsplit("/", 1)[-1], []).append(list(args))
        if "review_docs.py" in joined:
            self.calls.append("review_docs")
            return 0, json.dumps(self.review), ""
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
    name = "model"

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
    _project(tmp_path)
    return runner, model, tmp_path


def test_dry_run_gathers_retrieves_gates_and_writes_nothing(seams):
    runner, model, root = seams
    r = review(root=str(root))
    assert r.dry_run and r.baseline_green
    assert (r.stale, r.unresolved, r.rosters) == (1, 1, 1)
    # A stale stamp is counted but never a chunk: the writer clears it
    # deterministically (`make restamp-docs`), and while one is outstanding
    # `make check-docs` is red, so no gated edit could ever land anyway.
    assert r.candidates == ("mention:docs/b.md:4", "roster:scripts/README.md:x.py")
    assert "Name the sibling." in r.preview and "kind: mention" in r.preview
    assert model.prompts == [] and "apply_refactor" not in runner.calls
    assert runner.calls == ["review_docs", "query_corpus", "run_make_target"]


def test_execute_applies_each_accepted_chunk_through_the_gated_doer(seams):
    runner, model, root = seams
    r = review(execute=True, max_model_calls=8, root=str(root), checkpointer=None)
    assert not r.dry_run
    assert len(model.prompts) == 2 and runner.calls.count("apply_refactor") == 2
    assert r.applied == ("docs/a.md",) * 2 and r.skipped == ()


def test_every_tool_child_is_bounded_by_the_reviewed_roots_limits(seams):
    """The gate runner reads its limit from the reviewed root, so each tool
    call hands that root to run_tool, whose time limit is checked against it."""
    runner, _, root = seams
    review(execute=True, max_model_calls=8, root=str(root), checkpointer=None)
    assert runner.calls.count("apply_refactor") == 2, runner.calls
    assert runner.roots == [str(root)] * len(runner.calls)


def test_a_declined_chunk_is_skipped_without_touching_apply(seams, monkeypatch):
    runner, model, root = seams
    model.reply = '{"edits": []}'
    r = review(execute=True, max_model_calls=8, root=str(root), max_chunks=1)
    assert r.skipped == ("mention:docs/b.md:4",) and r.applied == ()
    assert "apply_refactor" not in runner.calls


def _flag(argv, name):
    assert argv.count(name) == 1, argv
    return argv[argv.index(name) + 1]


def test_a_reply_that_names_a_gate_is_declined_and_each_apply_is_bound_to_its_chunk(
    seams,
):
    """The gate is the run's: a reply naming one is declined before apply, the
    prompt never tells the model the gate, and an accepted chunk's apply may
    edit only that chunk's own file."""
    runner, model, root = seams
    gated = json.loads(_SPEC)
    gated["gate"] = "none"
    replies = iter([json.dumps(gated), _SPEC])
    model.run = lambda prompt, **opts: (model.prompts.append(prompt), next(replies))[1]
    r = review(execute=True, max_model_calls=8, root=str(root), checkpointer=None)
    assert r.skipped == ("mention:docs/b.md:4",)
    applies = runner.argvs["apply_refactor.py"]
    assert [_flag(a, "--allow") for a in applies] == ["scripts/README.md"]
    assert [_flag(a, "--gate") for a in applies] == ["check-docs"]
    assert [argv[1] for argv in runner.argvs["run_make_target.py"]] == ["check-docs"]
    assert len(model.prompts) == 2
    assert not any(
        line.startswith("gate:") for p in model.prompts for line in p.splitlines()
    )
    assert "gate:" not in r.preview


def test_a_red_gate_rolls_back_so_the_chunk_is_skipped(monkeypatch, tmp_path):
    runner = _Runner(gate_ok=False)
    monkeypatch.setattr(_BRAIN + "._run", runner)
    monkeypatch.setattr(_BRAIN + ".get_model", lambda name=None: _Model(_SPEC))
    monkeypatch.setattr(_BRAIN + "._read_lines", lambda *a, **k: "")
    _project(tmp_path)
    r = review(execute=True, max_model_calls=8, root=str(tmp_path), max_chunks=1)
    assert r.applied == () and r.skipped == ("mention:docs/b.md:4",)


def test_a_red_baseline_attempts_nothing(monkeypatch, tmp_path):
    runner = _Runner(baseline_ok=False)
    model = _Model(_SPEC)
    monkeypatch.setattr(_BRAIN + "._run", runner)
    monkeypatch.setattr(_BRAIN + ".get_model", lambda name=None: model)
    monkeypatch.setattr(_BRAIN + "._read_lines", lambda *a, **k: "")
    r = review(execute=True, max_model_calls=8, root=str(tmp_path))
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
    import model_budget  # noqa: E402
    import on_stop_doc_review as hook  # noqa: E402
    from models import ModelUnavailable

    # Approved, so the absent model is what this case reaches; the cap itself
    # is tests/unit/scripts/test_agent_spend_cap.py.
    monkeypatch.setattr(model_budget, "cap", lambda root: 8)

    def no_model(**kwargs):
        raise ModelUnavailable("claude binary 'claude' is not on PATH")

    monkeypatch.setattr(cli, "review", no_model)
    monkeypatch.setattr(hook, "review", no_model)
    assert cli.main(["--execute"]) == 0 and "skipping" in capsys.readouterr().out
    assert (
        hook.main(["payload", "--execute"]) == 0
        and "skipping" in capsys.readouterr().out
    )


def test_a_stale_stamp_is_never_sent_to_the_model(monkeypatch, tmp_path):
    """A report with only stale stamps gives the model nothing to do: the count
    is reported, the remedy is the deterministic writer, and no prompt is spent
    on a date a rule already knows."""
    only_stale = dict(_REVIEW, unresolved_mentions=[], rosters=[])
    runner = _Runner()
    model = _Model(_SPEC)

    def run(args, stdin=None, *, root):
        if "review_docs.py" in " ".join(args):
            runner.calls.append("review_docs")
            return 0, json.dumps(only_stale), ""
        return runner(args, stdin, root=root)

    monkeypatch.setattr(_BRAIN + "._run", run)
    monkeypatch.setattr(_BRAIN + ".get_model", lambda name=None: model)
    monkeypatch.setattr(_BRAIN + "._read_lines", lambda *a, **k: "")
    r = review(execute=True, max_model_calls=8, root=str(tmp_path))
    assert r.stale == 1 and r.candidates == ()
    assert model.prompts == [] and "apply_refactor" not in runner.calls


_CODEWORD = "CODEWORD-ZEBRA"
_SECRET_MENTION = dict(
    _REVIEW,
    unresolved_mentions=[
        {"path": "docs/secret/README.md", "line": 4, "mention": "scripts/gone.py"}
    ],
    rosters=[],
)


def _withholding(monkeypatch, tmp_path, review_report):
    """The seams with *review_report* as review_docs' answer and every
    chunk's text the codeword, so a prompt that carries one is seen."""
    runner = _Runner(review=review_report)
    model = _Model(_SPEC)
    monkeypatch.setattr(_BRAIN + "._run", runner)
    monkeypatch.setattr(_BRAIN + ".get_model", lambda name=None: model)
    read = []

    def read_lines(root, relpath, lineno, around=3):
        read.append(relpath)
        return _CODEWORD

    monkeypatch.setattr(_BRAIN + "._read_lines", read_lines)
    return runner, model, read


def test_a_finding_on_a_confidential_doc_is_reported_and_never_sent(
    monkeypatch, tmp_path
):
    """The finding stays in the deterministic report with one line saying
    why, and no prompt, preview or apply carries its file or text."""
    runner, model, read = _withholding(monkeypatch, tmp_path, _SECRET_MENTION)
    _project(tmp_path, {"docs/secret/README.md": "confidential"})
    for execute in (False, True):
        r = review(execute=execute, max_model_calls=8, root=str(tmp_path))
        assert r.unresolved == 1 and r.candidates == ()
        ((chunk, why),) = r.withheld
        assert chunk == "mention:docs/secret/README.md:4"
        assert "corpus.served_visibilities" in why and _CODEWORD not in why
        assert r.preview == "" and model.prompts == []
    assert "apply_refactor" not in runner.calls and read == []


@pytest.mark.parametrize(
    "corpus", ["absent", "not-json", "not-in-it", "no-config"], ids=lambda c: c
)
def test_a_finding_whose_level_the_corpus_cannot_give_is_never_sent(
    monkeypatch, tmp_path, corpus
):
    """Fail closed: with no readable corpus, no node for the file, or no
    config to give the served levels, the finding is withheld and no prompt
    is sent."""
    runner, model, _ = _withholding(monkeypatch, tmp_path, _SECRET_MENTION)
    _project(tmp_path, {"docs/other.md": "internal"})
    if corpus == "absent":
        (tmp_path / "wiki" / "corpus.json").unlink()
    elif corpus == "not-json":
        (tmp_path / "wiki" / "corpus.json").write_text("{not json")
    elif corpus == "no-config":
        _project(tmp_path, {"docs/secret/README.md": "public"})
        (tmp_path / "config" / "project.json").unlink()
    r = review(execute=True, max_model_calls=8, root=str(tmp_path))
    assert r.candidates == () and model.prompts == []
    assert [chunk for chunk, _ in r.withheld] == ["mention:docs/secret/README.md:4"]
    assert "apply_refactor" not in runner.calls


def test_a_served_finding_still_goes_beside_a_withheld_one(monkeypatch, tmp_path):
    both = dict(
        _SECRET_MENTION,
        unresolved_mentions=_SECRET_MENTION["unresolved_mentions"]
        + _REVIEW["unresolved_mentions"],
    )
    runner, model, read = _withholding(monkeypatch, tmp_path, both)
    _project(tmp_path, {"docs/secret/README.md": "restricted", "docs/b.md": "public"})
    r = review(execute=True, max_model_calls=8, root=str(tmp_path))
    assert r.candidates == ("mention:docs/b.md:4",) and len(model.prompts) == 1
    assert "docs/secret" not in model.prompts[0] and "docs/secret/README.md" not in read
    assert [chunk for chunk, _ in r.withheld] == ["mention:docs/secret/README.md:4"]


def test_a_chunk_whose_file_left_the_served_levels_is_declined_at_propose(
    monkeypatch, tmp_path
):
    """A run resumed from a snapshot queued before the file's level changed
    asks the corpus again at propose, so the chunk gets no model call."""
    # By its module name, as the seams patch it: check_D keeps the private
    # submodule out of an import statement.
    brain = sys.modules[_BRAIN]

    _project(tmp_path, {"docs/secret/README.md": "confidential"})
    model = _Model(_SPEC)
    meter = ModelMeter(None, 8, lambda name: model)
    chunk = {
        "id": "mention:docs/secret/README.md:4",
        "kind": "mention",
        "path": "docs/secret/README.md",
        "line": 4,
        "finding": "`x` resolves to nothing",
        "text": _CODEWORD,
    }
    state = {
        "root": str(tmp_path),
        "corpus": str(tmp_path / "wiki" / "corpus.json"),
        "chunks": [chunk],
        "cursor": 0,
    }
    assert brain._propose(state, meter) == {"spec": None}
    assert model.prompts == []


def test_the_cli_prints_one_line_per_withheld_finding_and_the_hook_counts_them(
    monkeypatch, capsys
):
    sys.path.insert(0, str(_ROOT / "scripts"))
    sys.path.insert(0, str(_ROOT / "scripts" / "hooks"))
    import doc_review as cli  # noqa: E402
    import on_stop_doc_review as hook  # noqa: E402

    why = "docs/secret/README.md is at a level outside corpus.served_visibilities"
    report = DocReviewReport(
        True, 0, 1, 0, (), (), (), (("mention:docs/secret/README.md:4", why),), "", True
    )
    monkeypatch.setattr(cli, "review", lambda **kwargs: report)
    assert cli.main([]) == 0
    assert "  withheld mention:docs/secret/README.md:4: %s\n" % why in (
        capsys.readouterr().out
    )
    assert cli.main(["--json"]) == 0
    assert json.loads(capsys.readouterr().out)["withheld"] == [
        {"id": "mention:docs/secret/README.md:4", "why": why}
    ]
    monkeypatch.setattr(hook, "review", lambda **kwargs: report)
    assert hook.main(["payload"]) == 0
    assert "0 chunk(s) queued, 1 withheld from the model" in capsys.readouterr().out
