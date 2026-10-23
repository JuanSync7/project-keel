"""
title: Integration — an agent run resumed from a saved snapshot is held to the approved model and count
kind: tests
layer: n/a
summary: scripts/doc_review.py and scripts/refactor_practice.py `--execute` with a snapshot under <root>/wiki/.runtime left by an earlier run refuse (USAGE, no model call, snapshot kept) when the snapshot has more chunks left than the bound the run approves, or was saved on another model than the run names, the registry default included, naming the snapshot to remove; a snapshot the approval covers resumes and calls the model once per chunk left. The brains hold every call to one counted backend: a run whose work outgrows its approved count stops at it with models.CallCapReached, and an execute run with no count is a ValueError before any call. The model is a FakeModel subclass patched into models.registry._REGISTRY under its own name and under the registry default's, so no billed model is reachable, and every tool the brains run as a child process is a stub.
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts"))

import doc_review  # noqa: E402
import model_budget  # noqa: E402
import refactor_practice  # noqa: E402
from agents.doc_reviewer import review  # noqa: E402
from agents.practice_refactor import refactor  # noqa: E402
from exit_codes import ExitCode  # noqa: E402
from models import CallCapReached, registry  # noqa: E402
from models.fake import FakeModel  # noqa: E402
from runtimes import FileCheckpointer  # noqa: E402

pytestmark = pytest.mark.integration

_DOC_BRAIN = "agents.doc_reviewer._brain"
_REF_BRAIN = "agents.practice_refactor._brain"
_PRACTICE = "precise-container-types"


def _edit(path):
    return json.dumps({"edits": [{"file": path, "find": "a", "replace": "b"}]})


def _tools(args, stdin=None):
    """Every tool the brains run, answered from data: a green gate, an apply
    that lands, and no findings or nodes for a fresh run to walk."""
    joined = " ".join(args)
    if "run_make_target.py" in joined:
        return 0, json.dumps({"ok": True}), ""
    if "apply_refactor.py" in joined:
        files = [e["file"] for e in json.loads(stdin)["edits"]]
        return 0, json.dumps({"applied": True, "files": files}), ""
    if "review_docs.py" in joined:
        return 0, json.dumps(_FRESH_REVIEW), ""
    if "query_corpus.py" in joined:
        return 0, json.dumps(_FRESH_NODES), ""
    raise AssertionError("unexpected tool: %s" % joined)


_FRESH_REVIEW = {
    "findings": [],
    "unresolved_mentions": [
        {"path": "docs/d%d.md" % i, "line": 1, "mention": "gone.py"} for i in range(5)
    ],
    "rosters": [],
}
_FRESH_NODES = [
    {"node_id": "n%d" % i, "path": "src/backend/m%d.py" % i, "tags": []}
    for i in range(5)
]


@pytest.fixture
def models(monkeypatch):
    """Every backend built, by registry name; the fake and the registry default
    both resolve to a counting FakeModel, so a call to either is counted."""
    built = {}

    def counting(name):
        class _Counted(FakeModel):
            def __init__(self, **kwargs):
                super().__init__(reply=_edit("docs/d0.md"))
                self.prompts = []
                built.setdefault(name, []).append(self)

            def run(self, prompt, **opts):
                self.prompts.append(prompt)
                return super().run(prompt, **opts)

        return _Counted

    monkeypatch.setitem(registry._REGISTRY, "fake", counting("fake"))
    monkeypatch.setitem(
        registry._REGISTRY, registry.DEFAULT_MODEL, counting(registry.DEFAULT_MODEL)
    )
    for brain in (_DOC_BRAIN, _REF_BRAIN):
        monkeypatch.setattr(brain + "._run", _tools)
    monkeypatch.setattr(
        _DOC_BRAIN + "._read_lines", lambda root, relpath, lineno, around=3: "1: x"
    )
    return built


def _calls(built):
    return sum(len(b.prompts) for backends in built.values() for b in backends)


def _save_doc_run(root, chunks, model):
    state = {
        "model": model,
        "root": str(root),
        "corpus": str(root / "wiki" / "corpus.json"),
        "max_chunks": chunks,
        "gate": "check-docs",
        "execute": True,
        "baseline_green": True,
        "rules": [],
        "chunks": [
            {
                "id": "mention:docs/d%d.md:1" % i,
                "kind": "mention",
                "path": "docs/d%d.md" % i,
                "line": 1,
                "finding": "`gone.py` resolves to nothing",
                "text": "1: x",
            }
            for i in range(chunks)
        ],
        "candidates": [],
        "cursor": 0,
        "applied": [],
        "skipped": [],
    }
    return _save(root, "doc_reviewer", state)


def _save_refactor_run(root, chunks, model):
    state = {
        "practice": _PRACTICE,
        "practice_def": None,
        "model": model,
        "root": str(root),
        "corpus": str(root / "wiki" / "corpus.json"),
        "max_nodes": chunks,
        "gate": "verify",
        "execute": True,
        "baseline_green": True,
        "chunks": [
            {"node_id": "n%d" % i, "path": "src/backend/m%d.py" % i, "tags": []}
            for i in range(chunks)
        ],
        "candidates": [],
        "cursor": 0,
        "refactored": [],
        "skipped": [],
    }
    return _save(root, "practice_refactor", state)


def _save(root, key, state):
    store = FileCheckpointer(str(root / "wiki" / ".runtime"))
    store.save(key, {"cursor": "propose", "state": state, "trace": []})
    return store.where(key)


# name -> (CLI module, argv before flags, its bound flag, the snapshot writer)
_CLIS = {
    "doc_review": (doc_review, [], "--max-chunks", _save_doc_run),
    "refactor_practice": (
        refactor_practice,
        [_PRACTICE],
        "--max-nodes",
        _save_refactor_run,
    ),
}


def _main(name, root, *flags):
    module, argv, _flag, _save_run = _CLIS[name]
    return module.main(argv + ["--execute", "--root", str(root)] + list(flags))


@pytest.mark.parametrize("name", sorted(_CLIS))
def test_a_saved_run_with_more_left_than_approved_is_refused(
    name, tmp_path, models, monkeypatch, capsys
):
    _module, _argv, flag, save_run = _CLIS[name]
    snapshot = save_run(tmp_path, 5, "fake")
    monkeypatch.setattr(model_budget, "cap", lambda root: 1)
    assert _main(name, tmp_path, "--model", "fake", flag, "1") is ExitCode.USAGE
    assert _calls(models) == 0 and Path(snapshot).is_file()
    err = capsys.readouterr().err
    assert "5 model call(s) left" in err and snapshot in err


@pytest.mark.parametrize("name", sorted(_CLIS))
def test_a_saved_run_on_another_model_is_refused_the_default_included(
    name, tmp_path, models, monkeypatch, capsys
):
    _module, _argv, flag, save_run = _CLIS[name]
    snapshot = save_run(tmp_path, 3, None)
    monkeypatch.setattr(model_budget, "cap", lambda root: 5)
    assert _main(name, tmp_path, "--model", "fake", flag, "5") is ExitCode.USAGE
    assert _calls(models) == 0 and Path(snapshot).is_file()
    err = capsys.readouterr().err
    assert repr(registry.DEFAULT_MODEL) in err and "'fake'" in err
    # And the other way: saved on a named model, resumed with none named.
    save_run(tmp_path, 3, "fake")
    assert _main(name, tmp_path, flag, "5") is ExitCode.USAGE
    assert _calls(models) == 0


@pytest.mark.parametrize("name", sorted(_CLIS))
def test_a_saved_run_the_approval_covers_resumes_one_call_per_chunk_left(
    name, tmp_path, models, monkeypatch
):
    _module, _argv, flag, save_run = _CLIS[name]
    snapshot = save_run(tmp_path, 2, "fake")
    monkeypatch.setattr(model_budget, "cap", lambda root: 2)
    assert _main(name, tmp_path, "--model", "fake", flag, "2") is ExitCode.SUCCESS
    assert _calls(models) == 2 and list(models) == ["fake"]
    assert not Path(snapshot).exists()


def test_a_review_whose_work_outgrows_its_count_stops_at_it(tmp_path, models):
    with pytest.raises(CallCapReached):
        review(
            execute=True,
            model="fake",
            root=str(tmp_path),
            max_chunks=5,
            max_model_calls=2,
        )
    assert _calls(models) == 2


def test_a_refactor_whose_work_outgrows_its_count_stops_at_it(tmp_path, models):
    with pytest.raises(CallCapReached):
        refactor(
            _PRACTICE,
            execute=True,
            model="fake",
            root=str(tmp_path),
            max_nodes=5,
            max_model_calls=2,
        )
    assert _calls(models) == 2


def test_an_execute_run_with_no_approved_count_is_refused_before_any_call(
    tmp_path, models
):
    with pytest.raises(ValueError, match="max_model_calls"):
        review(execute=True, model="fake", root=str(tmp_path))
    with pytest.raises(ValueError, match="max_model_calls"):
        refactor(_PRACTICE, execute=True, model="fake", root=str(tmp_path))
    assert _calls(models) == 0
