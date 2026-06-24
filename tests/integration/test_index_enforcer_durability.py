"""
title: Integration — index_enforcer durable gap-fill
kind: tests
layer: backend
summary: A crash mid-fill resumes via the checkpointer; already-filled gaps are not re-filled and authored summaries are untouched.
"""
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from agents.index_enforcer import enforce      # noqa: E402

pytestmark = pytest.mark.integration

# The model + CLI subprocess seams live in the brain module; patch them by
# dotted path (no import of the private module, so the package boundary holds).
_BRAIN = "agents.index_enforcer._brain"


def _corpus():
    return {"nodes": [
        {"node_id": "n1", "title": "a", "path": "p", "text_excerpt": "x"},
        {"node_id": "n2", "title": "b", "path": "p", "text_excerpt": "x"},
        {"node_id": "n3", "title": "c", "path": "p", "text_excerpt": "x"},
        {"node_id": "keep", "title": "k", "path": "p",
         "summary": "AUTHORED", "summary_source": "authored"},
    ]}


def _fake_run(args):
    # clean gate + no-op build/link; accountability returns no owner gaps
    return (0, "[]", "") if "accountability_report.py" in " ".join(args) else (0, "", "")


@pytest.mark.parametrize("engine", ["inprocess", "langgraph"])
def test_crash_mid_fill_resumes_without_refilling(engine, tmp_path, monkeypatch):
    if engine == "langgraph":
        pytest.importorskip("langgraph")
    (tmp_path / "wiki").mkdir()
    (tmp_path / "wiki" / "corpus.json").write_text(json.dumps(_corpus()))

    calls = {"n": 0}

    class FakeModel:
        def run(self, prompt):
            calls["n"] += 1
            if calls["n"] == 2:          # SIGKILL-ish on the 2nd fill
                raise RuntimeError("crash mid-fill")
            return "GEN-%d" % calls["n"]

    monkeypatch.setattr(_BRAIN + ".get_model", lambda name=None: FakeModel())
    monkeypatch.setattr(_BRAIN + "._run", _fake_run)

    # First attempt crashes after filling exactly one gap.
    with pytest.raises(RuntimeError):
        enforce(execute=True, fix_gaps=True, root=str(tmp_path),
                runtime=engine, run_key="job")
    assert calls["n"] == 2               # n1 filled, n2 in flight when it crashed

    # Re-running auto-resumes from the checkpoint and finishes.
    rep = enforce(execute=True, fix_gaps=True, root=str(tmp_path),
                  runtime=engine, run_key="job")
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
