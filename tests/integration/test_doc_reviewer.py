"""
title: Integration — the doc reviewer agent (dry-run, execute, decline, rollback)
kind: tests
layer: backend
summary: agents.doc_reviewer.review over patched tool and model seams (no subprocess, no model, but for one style-rule retrieval over the real query_corpus, which retrieves the guide while its file under the reviewed root is public and not once it states confidential, so a retrieval that drops `--root` is red): a dry-run gathers findings, retrieves rules, gates the baseline and writes nothing; execute proposes one edit per chunk and applies through the gated doer; a declined chunk or a red gate lands in skipped; a red baseline attempts nothing; a reply that names a gate is declined, the prompt never states the gate, and every apply is bound to its chunk's own file with `--allow`. A style-rule retrieval query_corpus refuses, or whose output is not JSON or empty, raises RulesRefused naming the exit status, dry run and execute alike, with no model call, and scripts/doc_review.py reports it as exit USAGE through the exit helper, as scripts/hooks/on_stop_doc_review.py does with --execute while its dry run writes that one line and exits 0, the real query_corpus refusing a corpus that is not JSON; one that finds no node refuses an execute run the same way, and a dry run shows the empty rules section in its preview. A relative root reaches the corpus query as one absolute `--root`, with no `--corpus` beside it; a corpus given alone names its checkout, whose corpus both the withholding check and the query read; a root beside a corpus, a corpus outside some checkout's wiki/corpus.json, or one named that does not exist, is corpus_level.NotACheckout before any tool runs. Every tool call hands the reviewed root to the runner, so run_tool reads the tool limits, and checks them against the gate keys, of the tree the gate runner reads. The report the CLI and hook print is this report. A finding on a file the corpus places outside corpus.served_visibilities, or has no node for, or on any file when the corpus or config cannot be read, is withheld: reported with why (one CLI line each, a count in the hook's line), its text never read, and no prompt or apply made, dry run and execute alike, while a served finding beside it still goes; a chunk queued before its file left the served levels is declined at propose with no model call; a document reclassified on disk after the corpus was built, or made unreadable, is withheld the same way, its text in no prompt.
"""

import json
import os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from agents.doc_reviewer import DocReviewReport, RulesRefused, review  # noqa: E402
from models import ModelMeter  # noqa: E402
from scripts import corpus_level  # noqa: E402

import reclassify  # noqa: E402

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
    `internal`. Each file is written stating its level too, since a reader
    that checks a node's file now serves a file only on the level it states
    there now."""
    if nodes is None:
        nodes = {"docs/b.md": "internal", "scripts/README.md": "internal"}
    (root / "config").mkdir(exist_ok=True)
    (root / "config" / "project.json").write_text("{}")
    for path, level in nodes.items():
        f = root / path
        f.parent.mkdir(parents=True, exist_ok=True)
        if not f.exists():
            f.write_text("---\ntitle: T\nvisibility: %s\n---\n# T\n" % level)
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


def test_a_relative_root_reaches_the_corpus_query_as_one_absolute_checkout(
    seams, monkeypatch
):
    """query_corpus reads the corpus of the root it is handed, so a relative
    root is made absolute first, from the caller's directory, and handed
    alone: a `--corpus` beside it could name another checkout's corpus."""
    runner, _, root = seams
    monkeypatch.chdir(root.parent)
    review(root=root.name)
    (argv,) = runner.argvs["query_corpus.py"]
    assert os.path.isabs(_flag(argv, "--root"))
    assert os.path.realpath(_flag(argv, "--root")) == os.path.realpath(str(root))
    assert "--corpus" not in argv


def test_a_corpus_names_the_checkout_both_readers_read(seams, monkeypatch):
    """The reviewer's repro: a relative corpus was opened from the caller's
    directory by the withholding check and under the root by query_corpus.
    Now the corpus names its checkout, the directory that keeps its
    wiki/corpus.json, and both read there: the findings the root's corpus
    serves are candidates, and the query is handed that root."""
    runner, _, root = seams
    monkeypatch.chdir(root.parent)
    r = review(corpus=os.path.join(root.name, "wiki", "corpus.json"))
    assert r.withheld == ()
    assert r.candidates == ("mention:docs/b.md:4", "roster:scripts/README.md:x.py")
    (argv,) = runner.argvs["query_corpus.py"]
    assert os.path.realpath(_flag(argv, "--root")) == os.path.realpath(str(root))


@pytest.mark.parametrize("given", ["both", "outside-wiki", "missing"])
def test_a_corpus_that_is_not_its_roots_own_is_refused_before_any_step(seams, given):
    """A root beside a corpus, or a corpus outside some checkout's
    wiki/corpus.json, could pair one checkout's corpus with another's files,
    and a corpus named in a folder that keeps none would review with no
    rules, so review() raises corpus_level.NotACheckout and runs no tool."""
    runner, model, root = seams
    corpus = root / "wiki" / "corpus.json"
    if given == "both":
        kwargs = {"root": str(root), "corpus": str(corpus)}
    elif given == "missing":
        (root / "d").mkdir()
        kwargs = {"corpus": str(root / "d" / "wiki" / "corpus.json")}
    else:
        corpus.rename(root / "corpus.json")
        kwargs = {"corpus": str(root / "corpus.json")}
    with pytest.raises(corpus_level.NotACheckout):
        review(execute=True, max_model_calls=8, **kwargs)
    assert runner.calls == [] and model.prompts == []


class _RefusedQuery(_Runner):
    """A runner whose query_corpus answers *answer*, (rc, stdout, stderr)."""

    def __init__(self, answer):
        super().__init__()
        self.answer = answer

    def __call__(self, args, stdin=None, *, root):
        if any(a.endswith("query_corpus.py") for a in args):
            self.calls.append("query_corpus")
            return self.answer
        return super().__call__(args, stdin, root=root)


@pytest.mark.parametrize(
    "answer",
    [
        (2, "", "query_corpus: the checkout does not exist"),
        (0, "not json", ""),
        (0, "", ""),
    ],
    ids=["refused", "unreadable", "empty"],
)
def test_a_failed_rule_retrieval_fails_the_run_before_any_model_call(
    monkeypatch, tmp_path, answer
):
    """The reviewer's repro: query_corpus exited 2 and _retrieve went on with
    no rules, so the model could be asked for edits with an empty rules
    section. A refusal, or output that is not JSON (empty output included,
    which is not `[]`), now raises RulesRefused, a RuntimeError naming the
    exit status, before the baseline gate and any model call."""
    runner, model = _RefusedQuery(answer), _Model(_SPEC)
    monkeypatch.setattr(_BRAIN + "._run", runner)
    monkeypatch.setattr(_BRAIN + ".get_model", lambda name=None: model)
    _project(tmp_path)
    for execute in (False, True):
        with pytest.raises(RulesRefused, match="query_corpus exited %d" % answer[0]):
            review(execute=execute, max_model_calls=8, root=str(tmp_path))
    assert model.prompts == []
    assert runner.calls == ["review_docs", "query_corpus"] * 2
    assert issubclass(RulesRefused, RuntimeError)


@pytest.mark.parametrize(
    "answer",
    [(2, "", "query_corpus: the corpus cannot be read"), (0, "not json", "")],
    ids=["refused", "unreadable"],
)
def test_the_cli_reports_a_failed_rule_retrieval_through_the_exit_helper(
    monkeypatch, capsys, tmp_path, answer
):
    """The reviewer's repro: `doc_review.py --root a2`, a2's corpus not JSON,
    ended with a traceback at exit 1. The refusal is exit USAGE through
    report(): one `doc_review:` line naming the root, and no model call."""
    sys.path.insert(0, str(_ROOT / "scripts"))
    import doc_review as cli  # noqa: E402

    runner, model = _RefusedQuery(answer), _Model(_SPEC)
    monkeypatch.setattr(_BRAIN + "._run", runner)
    monkeypatch.setattr(_BRAIN + ".get_model", lambda name=None: model)
    _project(tmp_path)
    assert cli.main(["--root", str(tmp_path)]) == cli.exit_codes.ExitCode.USAGE
    err = capsys.readouterr().err.strip().splitlines()[-1]
    assert err.startswith("doc_review: ") and str(tmp_path) in err
    assert model.prompts == []


@pytest.mark.parametrize("execute", [False, True], ids=["dry-run", "execute"])
def test_the_hook_reports_a_refused_rule_retrieval_and_a_dry_run_never_blocks(
    monkeypatch, capsys, tmp_path, execute
):
    """The reviewer's finding: on_stop_doc_review did not catch RulesRefused,
    so every session stop over a refused corpus ended with a traceback. A dry
    run, which never blocks the event, writes one `on_stop_doc_review:` line
    naming the root and exits 0; an execute run exits USAGE through report(),
    as scripts/doc_review.py does. The hook reviews its own checkout, so its
    review is pointed at the scratch root here."""
    sys.path.insert(0, str(_ROOT / "scripts"))
    sys.path.insert(0, str(_ROOT / "scripts" / "hooks"))
    import model_budget  # noqa: E402
    import on_stop_doc_review as hook  # noqa: E402

    refused = (2, "", "query_corpus: the corpus cannot be read")
    runner, model = _RefusedQuery(refused), _Model(_SPEC)
    monkeypatch.setattr(_BRAIN + "._run", runner)
    monkeypatch.setattr(_BRAIN + ".get_model", lambda name=None: model)
    monkeypatch.setattr(model_budget, "cap", lambda root: 8)
    monkeypatch.setattr(
        hook, "review", lambda **kwargs: review(root=str(tmp_path), **kwargs)
    )
    _project(tmp_path)
    capsys.readouterr()
    rc = hook.main(["payload"] + (["--execute"] if execute else []))
    out, err = capsys.readouterr()
    # An execute run also names the registry default above the refusal.
    lines = [x for x in err.splitlines() if "query_corpus exited 2" in x]
    assert rc == (hook.exit_codes.ExitCode.USAGE if execute else 0)
    assert len(lines) == 1 and lines[0] == err.strip().splitlines()[-1]
    assert lines[0].startswith("on_stop_doc_review: ")
    assert str(tmp_path) in lines[0] and "then rerun" in lines[0]
    assert out == "" and model.prompts == []
    assert runner.calls == ["review_docs", "query_corpus"]


def test_no_rules_refuse_an_execute_run_and_show_in_a_dry_runs_preview(
    monkeypatch, tmp_path
):
    """The reviewer's finding 3: query_corpus answered `[]` at exit 0, from a
    checkout with no corpus or a corpus with no node for the rule query, and
    the prompt read `# Rules (...)` over nothing. An execute run raises
    RulesRefused before the baseline gate, so no model is asked for edits
    with an empty rules section; a dry run calls no model and shows that
    section in its preview."""
    no_rules = (0, "[]\n", "query_corpus: no corpus at x; `make site-data`")
    runner, model = _RefusedQuery(no_rules), _Model(_SPEC)
    monkeypatch.setattr(_BRAIN + "._run", runner)
    monkeypatch.setattr(_BRAIN + ".get_model", lambda name=None: model)
    _project(tmp_path)
    with pytest.raises(RulesRefused, match="no style rules") as raised:
        review(execute=True, max_model_calls=8, root=str(tmp_path))
    assert str(tmp_path) in str(raised.value)
    assert runner.calls == ["review_docs", "query_corpus"]
    report = review(root=str(tmp_path))
    assert report.dry_run and "# Rules" in report.preview
    assert model.prompts == []


def test_an_unreadable_corpus_refuses_the_real_rule_retrieval(tmp_path):
    """End to end with the real query_corpus: a corpus that is not JSON is
    refused there with USAGE, and _retrieve raises RulesRefused naming that
    exit status and the corpus, never a traceback's exit 1."""
    _project(tmp_path)
    corpus = tmp_path / "wiki" / "corpus.json"
    corpus.write_text("{not json")
    brain = sys.modules[_BRAIN]
    with pytest.raises(RulesRefused, match="query_corpus exited 2") as raised:
        brain._retrieve({"root": str(tmp_path), "chunks": [], "execute": False})
    assert str(corpus) in str(raised.value)


@pytest.mark.parametrize("execute", [False, True])
def test_an_empty_root_is_refused_before_any_tool(seams, monkeypatch, capsys, execute):
    """`root=""` and `--root ""` would review this checkout as if no root
    were given: review() raises corpus_level.NotACheckout and the CLI exits
    USAGE through the exit helper, before any tool or model call."""
    sys.path.insert(0, str(_ROOT / "scripts"))
    import doc_review as cli  # noqa: E402
    import model_budget  # noqa: E402

    monkeypatch.setattr(model_budget, "cap", lambda root: 8)
    runner, model, _ = seams
    with pytest.raises(corpus_level.NotACheckout):
        review(execute=execute, max_model_calls=8, root="")
    argv = ["--root", ""] + (["--execute"] if execute else [])
    assert cli.main(argv) == cli.exit_codes.ExitCode.USAGE
    assert capsys.readouterr().err.strip().splitlines()[-1].startswith("doc_review: ")
    assert runner.calls == [] and model.prompts == []


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


@pytest.mark.parametrize("hidden_first", [True, False])
def test_a_file_with_one_hidden_node_is_withheld_beside_a_served_one(
    monkeypatch, tmp_path, hidden_first
):
    """Every node a file carries must be served, not one: a file whose corpus
    holds a public node and a confidential one for it is withheld, though the
    file states a served level on disk and one of its nodes is served. The
    hidden node comes first and last, so a check that keeps only one node per
    path is caught in either order."""
    runner, model, read = _withholding(monkeypatch, tmp_path, _SECRET_MENTION)
    _project(tmp_path, {"docs/secret/README.md": "public"})
    path = "docs/secret/README.md"
    served = {"node_id": "doc", "path": path, "kind": "doc", "visibility": "public"}
    hidden = {
        "node_id": "doc#part",
        "path": path,
        "kind": "section",
        "visibility": "confidential",
    }
    corpus = {"nodes": [hidden, served] if hidden_first else [served, hidden]}
    (tmp_path / "wiki" / "corpus.json").write_text(json.dumps(corpus))
    r = review(execute=True, max_model_calls=8, root=str(tmp_path))
    assert r.candidates == () and model.prompts == [] and read == []
    ((chunk, why),) = r.withheld
    assert chunk == "mention:docs/secret/README.md:4"
    # The corpus check refuses it, not the on-disk one: the file states public.
    assert "is at a level outside corpus.served_visibilities" in why
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


_GUIDE_MENTION = dict(
    _REVIEW,
    findings=[],
    unresolved_mentions=[
        {"path": reclassify.GUIDE, "line": 13, "mention": "scripts/gone.py"}
    ],
    rosters=[],
)


@pytest.mark.parametrize("how", reclassify.HOWS)
def test_a_doc_reclassified_after_the_build_is_never_sent(monkeypatch, tmp_path, how):
    """The corpus says `docs/pubguide.md` is public; the file then states a
    stricter level, or none that can be read. Its text is read from disk, so
    the level it states there now decides: the finding is withheld with why,
    no prompt carries the text, and a chunk queued before the change is
    declined at propose with no model call."""
    runner = _Runner(review=_GUIDE_MENTION)
    model = _Model(_SPEC)
    monkeypatch.setattr(_BRAIN + "._run", runner)
    monkeypatch.setattr(_BRAIN + ".get_model", lambda name=None: model)
    reclassify.public_project(tmp_path, _CODEWORD)
    before = review(execute=True, max_model_calls=8, root=str(tmp_path))
    # The text reaches a prompt while the file is public, so a leak is seen.
    assert before.withheld == () and any(_CODEWORD in p for p in model.prompts)
    queued = review(execute=False, max_model_calls=8, root=str(tmp_path))
    assert _CODEWORD in queued.preview
    reclassify.reclassify(tmp_path / reclassify.GUIDE, how)
    model.prompts.clear()
    for execute in (False, True):
        r = review(execute=execute, max_model_calls=8, root=str(tmp_path))
        assert r.candidates == () and r.preview == "" and model.prompts == []
        ((chunk, why),) = r.withheld
        assert chunk == "mention:%s:13" % reclassify.GUIDE
        assert "on disk now" in why and _CODEWORD not in why
    brain = sys.modules[_BRAIN]
    state = {
        "root": str(tmp_path),
        "corpus": str(tmp_path / "wiki" / "corpus.json"),
        "chunks": [
            {
                "id": "mention:%s:13" % reclassify.GUIDE,
                "kind": "mention",
                "path": reclassify.GUIDE,
                "line": 13,
                "finding": "`x` resolves to nothing",
                "text": _CODEWORD,
            }
        ],
        "cursor": 0,
    }
    assert brain._propose(state, ModelMeter(None, 8, lambda name: model)) == {
        "spec": None
    }
    assert model.prompts == []


def test_the_style_rules_are_retrieved_on_the_level_each_file_states_under_the_root(
    tmp_path,
):
    """The style-rule retrieval hands query_corpus the reviewed root as
    `--root`, over the real tool: the guide, whose body carries the rule
    query's words, is a retrieved rule while it is public, and is not once
    the file under that root states confidential. This checkout holds no
    such file, so a retrieval that drops `--root` retrieves no guide at all."""
    reclassify.public_project(
        tmp_path, "Documentation style: a roster row names its discriminator."
    )
    brain = sys.modules[_BRAIN]
    state = {
        "root": str(tmp_path),
        "corpus": str(tmp_path / "wiki" / "corpus.json"),
        "chunks": [],
    }
    guide = {"pubguide", "pubguide#part"}

    def retrieved():
        return {n["node_id"] for n in brain._retrieve(state)["rules"]} & guide

    assert retrieved() == guide
    reclassify.reclassify(tmp_path / reclassify.GUIDE, "own")
    assert retrieved() == set()
