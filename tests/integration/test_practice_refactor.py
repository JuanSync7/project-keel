"""
title: Integration — practice_refactor gated KG-walking loop
kind: tests
layer: backend
summary: Dry-run walks the graph + gates the read-only baseline but proposes/writes nothing; execute proposes one bounded edit per chunk and a chunk is `refactored` only when the gated apply_refactor keeps make verify green (else rolled back -> `skipped`); a crash mid-refactor resumes at the cursor without re-applying accepted chunks.
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from agents.practice_refactor import refactor  # noqa: E402

pytestmark = pytest.mark.integration

# Patch the model + CLI-subprocess seams by dotted path (no import of the private
# module symbols, so the package boundary holds — tests are callers too).
_BRAIN = "agents.practice_refactor._brain"

_NODES = [
    {
        "node_id": "n1",
        "path": "src/backend/a.py",
        "tags": ["backend"],
        "text_excerpt": "x1",
    },
    {
        "node_id": "n2",
        "path": "src/backend/b.py",
        "tags": ["backend"],
        "text_excerpt": "x2",
    },
]


class _Runner:
    """A fake `_run` that answers each tool CLI from data — no real subprocess.

    query_corpus -> the neighbourhood; run_make_target -> a green gate;
    apply_refactor -> accept (echoing the spec's files) or reject per `gate_ok`.
    Records the tool of every call so a test can assert what did and didn't run.
    """

    def __init__(self, nodes=_NODES, baseline_ok=True, gate_ok=True):
        self.nodes = nodes
        self.baseline_ok = baseline_ok
        self.gate_ok = gate_ok
        self.calls = []
        self.applied_files = []

    def __call__(self, args, stdin=None):
        joined = " ".join(args)
        if "query_corpus.py" in joined:
            self.calls.append("query_corpus")
            return 0, json.dumps(self.nodes), ""
        if "run_make_target.py" in joined:
            self.calls.append("run_make_target")
            return (
                0,
                json.dumps(
                    {
                        "target": "verify",
                        "ok": self.baseline_ok,
                        "returncode": 0 if self.baseline_ok else 1,
                        "output": "",
                    }
                ),
                "",
            )
        if "apply_refactor.py" in joined:
            self.calls.append("apply_refactor")
            spec = json.loads(stdin)
            files = [e["file"] for e in spec.get("edits", [])]
            if self.gate_ok:
                self.applied_files.extend(files)
            return (
                0 if self.gate_ok else 1,
                json.dumps(
                    {
                        "practice": spec.get("practice", ""),
                        "gate": "verify",
                        "applied": self.gate_ok,
                        "rolled_back": not self.gate_ok,
                        "files": files,
                        "gate_output": "ok" if self.gate_ok else "RED",
                    }
                ),
                "",
            )
        self.calls.append("other")
        return 0, "", ""


class _Model:
    """A model that returns one bounded edit spec per chunk (or a scripted reply)."""

    def __init__(self, replies=None):
        self.replies = replies
        self.n = 0

    def run(self, prompt):
        self.n += 1
        if self.replies is not None:
            return self.replies[self.n - 1]
        return json.dumps(
            {
                "edits": [
                    {
                        "file": "src/backend/f%d.py" % self.n,
                        "find": "old",
                        "replace": "new",
                    }
                ]
            }
        )


def _patch(monkeypatch, runner, model):
    monkeypatch.setattr(_BRAIN + "._run", runner)
    monkeypatch.setattr(_BRAIN + ".get_model", lambda name=None: model)


def test_dry_run_walks_and_previews_but_never_proposes_or_writes(monkeypatch):
    runner, model = _Runner(), _Model()
    _patch(monkeypatch, runner, model)

    rep = refactor("precise-container-types")  # execute defaults to False

    assert rep.dry_run is True
    assert rep.candidates == ("n1", "n2")  # the graph was walked
    assert rep.baseline_green is True  # the read-only baseline gate ran
    assert rep.refactored == () and rep.skipped == ()
    assert (
        "precise-container-types" in rep.preview and "src/backend/a.py" in rep.preview
    )
    assert model.n == 0  # MODEL_CALL step skipped in dry-run
    assert "apply_refactor" not in runner.calls  # WRITES step skipped in dry-run
    assert runner.calls == ["query_corpus", "run_make_target"]


def test_red_baseline_attempts_no_refactor(monkeypatch):
    runner, model = _Runner(baseline_ok=False), _Model()
    _patch(monkeypatch, runner, model)

    rep = refactor("precise-container-types", execute=True, root=str(_ROOT))

    assert rep.baseline_green is False
    assert rep.refactored == () and rep.skipped == ()
    assert model.n == 0  # never proposed on a red tree
    assert "apply_refactor" not in runner.calls


def test_execute_applies_each_accepted_chunk_and_the_gate_keeps_it(monkeypatch):
    runner, model = _Runner(gate_ok=True), _Model()
    _patch(monkeypatch, runner, model)

    rep = refactor("precise-container-types", execute=True, root=str(_ROOT))

    assert rep.dry_run is False and rep.baseline_green is True
    assert rep.refactored == ("src/backend/f1.py", "src/backend/f2.py")
    assert rep.skipped == ()
    assert runner.calls.count("apply_refactor") == 2  # one gated apply per chunk
    assert model.n == 2


def test_gate_red_rolls_back_so_the_chunk_is_skipped_not_refactored(monkeypatch):
    runner, model = _Runner(gate_ok=False), _Model()
    _patch(monkeypatch, runner, model)

    rep = refactor("precise-container-types", execute=True, root=str(_ROOT))

    assert rep.refactored == ()  # nothing kept — the gate went red
    assert rep.skipped == ("n1", "n2")  # both chunks rolled back
    assert runner.applied_files == []


def test_model_declining_a_chunk_skips_it_without_touching_apply(monkeypatch):
    # Non-JSON and empty-edits replies both mean "decline this chunk".
    runner = _Runner()
    model = _Model(replies=["I cannot safely edit this.", json.dumps({"edits": []})])
    _patch(monkeypatch, runner, model)

    rep = refactor("precise-container-types", execute=True, root=str(_ROOT))

    assert rep.refactored == () and rep.skipped == ("n1", "n2")
    assert (
        "apply_refactor" not in runner.calls
    )  # declined -> the gated doer is never called


def test_no_matching_nodes_reports_empty_candidates(monkeypatch):
    runner, model = _Runner(nodes=[]), _Model()
    _patch(monkeypatch, runner, model)

    rep = refactor("no-such-practice-id")

    assert rep.candidates == () and rep.preview == ""
    assert rep.baseline_green is True  # baseline still gated honestly


@pytest.mark.parametrize("engine", ["inprocess", "langgraph"])
def test_crash_mid_refactor_resumes_without_reapplying(engine, tmp_path, monkeypatch):
    if engine == "langgraph":
        pytest.importorskip("langgraph")
    (tmp_path / "wiki").mkdir()

    runner = _Runner()
    calls = {"n": 0}

    class _Crashy:
        def run(self, prompt):
            calls["n"] += 1
            if calls["n"] == 2:  # SIGKILL-ish on the 2nd chunk's propose
                raise RuntimeError("crash mid-refactor")
            return json.dumps(
                {
                    "edits": [
                        {
                            "file": "src/backend/f%d.py" % calls["n"],
                            "find": "old",
                            "replace": "new",
                        }
                    ]
                }
            )

    monkeypatch.setattr(_BRAIN + "._run", runner)
    monkeypatch.setattr(_BRAIN + ".get_model", lambda name=None: _Crashy())

    with pytest.raises(RuntimeError):
        refactor(
            "precise-container-types",
            execute=True,
            root=str(tmp_path),
            runtime=engine,
            run_key="job",
        )
    assert calls["n"] == 2  # chunk0 applied, chunk1 in flight

    rep = refactor(
        "precise-container-types",
        execute=True,
        root=str(tmp_path),
        runtime=engine,
        run_key="job",
    )
    assert rep.refactored == (
        "src/backend/f1.py",
        "src/backend/f3.py",
    )  # both chunks done
    assert calls["n"] == 3  # only the in-flight chunk retried
    # chunk0 was NOT re-applied: 1 apply on the first run + 1 on resume == 2 total
    assert runner.calls.count("apply_refactor") == 2


def test_cli_entrypoint_dry_run_reports_candidates_as_json(monkeypatch, capsys):
    # The thin scripts/ doer behind the practice-refactor skill: it must drive the
    # agent and stay a pass-through (no logic of its own).
    sys.path.insert(0, str(_ROOT / "scripts"))
    import refactor_practice as rp  # noqa: E402

    _patch(monkeypatch, _Runner(), _Model())
    rc = rp.main(["precise-container-types", "--json"])  # dry-run by default

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["practice"] == "precise-container-types"
    assert out["candidates"] == ["n1", "n2"] and out["dry_run"] is True
    assert out["refactored"] == [] and out["baseline_green"] is True


def test_cli_entrypoint_reports_an_unavailable_model_as_a_skip(monkeypatch, capsys):
    """The model-absent path (documentation-quality plan, phase 6): a doer that
    cannot run its model says so and exits 0, writing nothing."""
    sys.path.insert(0, str(_ROOT / "scripts"))
    import refactor_practice as rp  # noqa: E402
    from models import ModelUnavailable

    def no_model(*args, **kwargs):
        raise ModelUnavailable("claude binary 'claude' is not on PATH")

    monkeypatch.setattr(rp, "refactor", no_model)
    assert rp.main(["precise-container-types", "--execute"]) == 0
    assert "skipping" in capsys.readouterr().out
