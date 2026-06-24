"""
title: Integration — durable runs via the file checkpointer
kind: tests
layer: backend
summary: FileCheckpointer survives a crash on disk; a resumed run continues from the cursor.
"""
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from runtimes import (  # noqa: E402
    COMPLETED,
    END,
    WRITES,
    Edge,
    FileCheckpointer,
    Plan,
    Step,
    get_runtime,
)

pytestmark = pytest.mark.integration


def _plan(spy, fail_once):
    def s1(s):
        spy.append("s1")
        return {"a": 1}

    def s2(s):
        spy.append("s2")
        if fail_once and spy.count("s2") == 1:
            raise RuntimeError("crash before s2 commits")
        return {"b": 2}

    def s3(s):
        spy.append("s3")
        return {"c": 3}

    return Plan("d", "s1",
                (Step("s1", WRITES, s1), Step("s2", WRITES, s2), Step("s3", WRITES, s3)),
                (Edge("s1", "s2"), Edge("s2", "s3"), Edge("s3", END)))


def test_file_checkpointer_survives_a_crash_and_resumes(tmp_path):
    cp = FileCheckpointer(str(tmp_path / "ckpt"))
    spy = []
    # First attempt crashes inside s2; the snapshot from after s1 is on disk.
    with pytest.raises(RuntimeError):
        get_runtime("inprocess").run(_plan(spy, fail_once=True), {}, execute=True,
                                     checkpointer=cp, run_key="job")
    snap = cp.load("job")
    assert snap is not None and snap["cursor"] == "s2"
    assert snap["state"] == {"a": 1}              # JSON-persisted partial state

    # A brand-new checkpointer over the same dir = "another process" resuming.
    cp2 = FileCheckpointer(str(tmp_path / "ckpt"))
    spy2 = []
    res = get_runtime("inprocess").run(_plan(spy2, fail_once=False), {}, execute=True,
                                       checkpointer=cp2, run_key="job", resume=None)
    assert res.state == {"a": 1, "b": 2, "c": 3} and res.status == COMPLETED
    assert spy2 == ["s2", "s3"]                   # s1 not re-run; resumed at the cursor
    assert cp2.load("job") is None                # cleared on completion
