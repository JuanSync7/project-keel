"""
title: Integration — index_enforcer durable gap-fill
kind: tests
layer: backend
summary: A crash mid-fill resumes via the checkpointer; already-filled gaps are not re-filled and authored summaries are untouched. A filling run is held to its approved count of model calls the way the other agents are: enforce(execute=True, fix_gaps=True) with no max_model_calls is a ValueError before any step, every fill goes through one run's models.ModelMeter so the call past the count raises models.CallCapReached and never reaches the model, and a saved run is resumed only on the model the run names and with no more gaps left than its count, else models.RunNotApproved before any call with the snapshot kept. The model is a fake patched in for the brain's get_model and every tool the brain runs as a child process is a stub, so no billed model and no real tree is reached. A confidential gap, or one that states no level, is never sent: no prompt names it or carries its text, and it stays unfilled.
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from agents.index_enforcer import enforce  # noqa: E402
from models import CallCapReached, RunNotApproved  # noqa: E402

pytestmark = pytest.mark.integration

# The model + CLI subprocess seams live in the brain module; patch them by
# dotted path (no import of the private module, so the package boundary holds).
_BRAIN = "agents.index_enforcer._brain"


def _corpus():
    return {
        "nodes": [
            {
                "node_id": "n1",
                "title": "a",
                "path": "p",
                "text_excerpt": "x",
                "visibility": "internal",
            },
            {
                "node_id": "n2",
                "title": "b",
                "path": "p",
                "text_excerpt": "x",
                "visibility": "internal",
            },
            {
                "node_id": "n3",
                "title": "c",
                "path": "p",
                "text_excerpt": "x",
                "visibility": "internal",
            },
            {
                "node_id": "keep",
                "title": "k",
                "path": "p",
                "summary": "AUTHORED",
                "summary_source": "authored",
                "visibility": "internal",
            },
        ]
    }


def _project(root, corpus):
    """A scratch project at *root*: an empty config/project.json, so the
    served levels are the shipped default, and *corpus* as its corpus."""
    (root / "config").mkdir()
    (root / "config" / "project.json").write_text("{}")
    (root / "wiki").mkdir()
    (root / "wiki" / "corpus.json").write_text(json.dumps(corpus))


def _fake_run(args):
    # clean gate + no-op build/link; accountability returns no owner gaps
    return (
        (0, "[]", "") if "accountability_report.py" in " ".join(args) else (0, "", "")
    )


@pytest.mark.parametrize("engine", ["inprocess", "langgraph"])
def test_crash_mid_fill_resumes_without_refilling(engine, tmp_path, monkeypatch):
    if engine == "langgraph":
        pytest.importorskip("langgraph")
    _project(tmp_path, _corpus())

    calls = {"n": 0}

    class FakeModel:
        name = "fake"

        def run(self, prompt):
            calls["n"] += 1
            if calls["n"] == 2:  # SIGKILL-ish on the 2nd fill
                raise RuntimeError("crash mid-fill")
            return "GEN-%d" % calls["n"]

    monkeypatch.setattr(_BRAIN + ".get_model", lambda name=None: FakeModel())
    monkeypatch.setattr(_BRAIN + "._run", _fake_run)

    # First attempt crashes after filling exactly one gap.
    with pytest.raises(RuntimeError):
        enforce(
            execute=True,
            fix_gaps=True,
            root=str(tmp_path),
            runtime=engine,
            run_key="job",
            max_model_calls=3,
        )
    assert calls["n"] == 2  # n1 filled, n2 in flight when it crashed

    # Re-running auto-resumes from the checkpoint and finishes.
    rep = enforce(
        execute=True,
        fix_gaps=True,
        root=str(tmp_path),
        runtime=engine,
        run_key="job",
        max_model_calls=2,  # n2 and n3 are left: the count the resume needs
    )
    assert rep.gaps_filled == 3

    final = json.loads((tmp_path / "wiki" / "corpus.json").read_text())
    by_id = {n["node_id"]: n for n in final["nodes"]}
    # n1 was NOT re-filled (still its original generated summary); all 3 gaps done
    assert by_id["n1"]["summary"] == "GEN-1"
    assert all(by_id[g]["summary_source"] == "generated" for g in ("n1", "n2", "n3"))
    # only the in-flight gap (n2) was retried: 3 gaps + 1 retry == 4 model calls
    assert calls["n"] == 4
    # the authored summary is never touched
    assert by_id["keep"]["summary"] == "AUTHORED"
    assert by_id["keep"]["summary_source"] == "authored"


@pytest.fixture
def counted(tmp_path, monkeypatch):
    """A corpus of three gaps under *tmp_path*, every tool a stub, and the
    model a fake that records each prompt it is sent and can be told to crash
    on a given call; returns (prompts, crash_on)."""
    _project(tmp_path, _corpus())
    prompts = []
    crash_on = {"call": None}

    class Recording:
        name = "fake"

        def run(self, prompt):
            prompts.append(prompt)
            if len(prompts) == crash_on["call"]:
                raise RuntimeError("crash mid-fill")
            return "GEN"

    monkeypatch.setattr(_BRAIN + ".get_model", lambda name=None: Recording())
    monkeypatch.setattr(_BRAIN + "._run", _fake_run)
    return prompts, crash_on


def _fill(root, **kwargs):
    return enforce(execute=True, fix_gaps=True, root=str(root), run_key="job", **kwargs)


def _snapshot(root):
    return root / "wiki" / ".runtime" / "job.json"


def test_a_filling_run_with_no_approved_count_is_refused_before_any_call(
    tmp_path, counted
):
    prompts, _ = counted
    with pytest.raises(ValueError, match="max_model_calls"):
        _fill(tmp_path, model="fake")
    assert prompts == []


def test_a_fill_whose_gaps_outgrow_its_count_stops_at_it(tmp_path, counted):
    prompts, _ = counted
    with pytest.raises(CallCapReached):
        _fill(tmp_path, model="fake", max_model_calls=2)
    assert len(prompts) == 2  # the third gap's call is never made


def test_a_saved_run_with_more_gaps_left_than_approved_is_refused(tmp_path, counted):
    prompts, crash_on = counted
    crash_on["call"] = 1  # the first fill crashes: all three gaps are left
    with pytest.raises(RuntimeError):
        _fill(tmp_path, model="fake", max_model_calls=3)
    assert _snapshot(tmp_path).is_file()
    with pytest.raises(RunNotApproved) as exc:
        _fill(tmp_path, model="fake", max_model_calls=2)
    what, on, _next = exc.value.parts
    assert "3 model call(s) left" in what and on == str(_snapshot(tmp_path))
    assert len(prompts) == 1 and _snapshot(tmp_path).is_file()


def test_a_saved_run_on_another_model_is_refused(tmp_path, counted):
    prompts, crash_on = counted
    crash_on["call"] = 1
    with pytest.raises(RuntimeError):
        _fill(tmp_path, model="fake", max_model_calls=3)
    with pytest.raises(RunNotApproved, match="'fake'"):
        _fill(tmp_path, model=None, max_model_calls=3)  # the registry default
    assert len(prompts) == 1 and _snapshot(tmp_path).is_file()


_CODEWORD = "CODEWORD-ZEBRA"


def test_a_hidden_gap_is_never_sent_to_the_model(tmp_path, monkeypatch):
    """A confidential gap and one that states no level are never filled: no
    prompt names either node or carries its text, and the served gap is."""
    corpus = {
        "nodes": [
            {
                "node_id": "open",
                "title": "open",
                "path": "docs/open.md",
                "text_excerpt": "x",
                "visibility": "internal",
            },
            {
                "node_id": "secret-doc",
                "title": "secret-doc",
                "path": "docs/secret/README.md",
                "text_excerpt": _CODEWORD,
                "visibility": "confidential",
            },
            {
                "node_id": "unstated-doc",
                "title": "unstated-doc",
                "path": "docs/unstated.md",
                "text_excerpt": _CODEWORD,
            },
        ]
    }
    _project(tmp_path, corpus)
    prompts = []

    class Recording:
        name = "fake"

        def run(self, prompt):
            prompts.append(prompt)
            return "GEN"

    monkeypatch.setattr(_BRAIN + ".get_model", lambda name=None: Recording())
    monkeypatch.setattr(_BRAIN + "._run", _fake_run)
    rep = _fill(tmp_path, model="fake", max_model_calls=3)
    assert rep.gaps_filled == 1 and len(prompts) == 1
    for prompt in prompts:
        assert _CODEWORD not in prompt
        assert "secret" not in prompt and "unstated" not in prompt
    by_id = {
        n["node_id"]: n
        for n in json.loads((tmp_path / "wiki" / "corpus.json").read_text())["nodes"]
    }
    assert by_id["open"]["summary_source"] == "generated"
    assert "summary_source" not in by_id["secret-doc"]
    assert "summary_source" not in by_id["unstated-doc"]
