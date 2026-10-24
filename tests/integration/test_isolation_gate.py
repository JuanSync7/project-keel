"""
title: Integration — a test that reaches outside its tier fails, named
kind: tests
layer: n/a
summary: Runs the shipped conftest over the tests/fixtures/isolation case files in a scratch project of their own, with a scratch root and a basetemp of the run's own and a directory beside the project that neither contains. Each outside reach fails (a socket to a routable address under unit, a write, a sqlite database, a write whose refusal the test swallows; a mode change, a time change direct or through a link, a sendmsg to a routable address, an AF_UNIX bind, a file in a `__pycache__` that is not bytecode, a `file:` database name opened in the checkout) and each inside one passes, a tree copied with a link that points outside among them, and the count is exact, never zero. The failure names the test, its phase and tier, the event, the target and the fix. An exemption with a reason in config/project.json `tests.isolation.exempt.<axis>` turns its case green; an exemption whose test ran and reached nothing on that axis fails the run, one whose test did not run is not judged, and a blank reason is refused before any test runs. The closest tier marker wins, a reach under xfail fails rather than counting as the expected failure, and the store_copy fixture hands a test its own copy of a listed store, leaving the live one unchanged, while a direct open of the live store, before a copy, after one and after one that failed, and a request for an unlisted one fail naming the key. Under `-n auto` the worker count is config/project.json `tests.workers` and a count the loader refuses exits 4; the exemption check judges across workers, and a worker that dies leaves it unjudged and the run red; `--expiring-tier-record` is refused under workers, exit 4 with no record written, and runs when `-n auto` resolves to one process.
"""

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from test_empty_selection import _SHIPPED
from test_scratch_root_gate import child_timeout

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

from child_env import build_child_env  # noqa: E402

pytestmark = pytest.mark.integration

_CASES = _ROOT / "tests" / "fixtures" / "isolation"
_REACH = "tests/unit/test_reach.py::"
_TIERS = "tests/unit/test_tiers.py::"
_STORE = "tests/unit/test_store.py::"
_SEAMS = "tests/unit/test_seams.py::"
_OUTSIDE_SEAMS = {
    "test_outside_chmod": "os.chmod",
    "test_outside_touch": "os.utime",
    "test_outside_touch_through_a_link": "os.utime",
    "test_outside_sendmsg": "socket.sendmsg",
    "test_outside_unix_bind": "socket.bind",
    "test_outside_pycache_note": "open",
    "test_outside_sqlite_file_name": "sqlite3.connect",
}
_INSIDE_SEAMS = (
    "test_inside_chmod",
    "test_inside_copytree_keeps_an_outbound_link",
    "test_inside_sendmsg_on_a_socketpair",
    "test_inside_sqlite_file_name",
)
_OUTSIDE_CASES = {
    "test_outside_socket": "socket.connect",
    "test_outside_write": "open",
    "test_outside_sqlite": "sqlite3.connect",
    "test_swallowed_write": "open",
}
_INSIDE_CASES = ("test_inside_socket", "test_inside_write", "test_inside_sqlite")


def _project(tmp_path, cases, exempt=None, stores=None, workers=None):
    """A scratch project holding the shipped test harness and `cases` as unit
    test files; `exempt` and `stores` replace tests.isolation's own, and
    `workers` replaces tests.workers."""
    root = tmp_path / "proj"
    for rel in _SHIPPED:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(str(_ROOT / rel), str(root / rel))
    (root / "tests" / "unit").mkdir(parents=True)
    for case in cases:
        shutil.copy(
            str(_CASES / ("case_%s.py" % case)),
            str(root / "tests" / "unit" / ("test_%s.py" % case)),
        )
    (tmp_path / "outside").mkdir()
    path = root / "config" / "project.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    isolation = manifest["tests"]["isolation"]
    if exempt is not None:
        isolation["exempt"] = exempt
    if stores is not None:
        isolation["stores"] = stores
    if workers is not None:
        manifest["tests"]["workers"] = workers
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return root


def _run(tmp_path, root, *args):
    """(exit code, output, {nodeid: (outcome, message)}) of the scratch suite."""
    junit = tmp_path / "junit.xml"
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "--junitxml=%s" % junit,
            "--basetemp=%s" % (tmp_path / "inner-bt"),
        ]
        + list(args),
        cwd=str(root),
        # The run's scratch root is its own, not the one this suite writes
        # under, so the directory beside the project is outside every root it
        # has.
        env=build_child_env(
            extra={
                "PYTHONPATH": "src:.",
                "KEEL_TEST_SCRATCH": str(tmp_path / "inner-scratch"),
            }
        ),
        capture_output=True,
        text=True,
        timeout=child_timeout(),
    )
    out = r.stdout + r.stderr
    outcomes = {}
    if junit.is_file():
        for case in ET.parse(str(junit)).iter("testcase"):
            nodeid = "%s.py::%s" % (
                case.get("classname").replace(".", "/"),
                case.get("name"),
            )
            outcome, message = "passed", ""
            for kind in ("failure", "error", "skipped"):
                found = case.find(kind)
                if found is not None:
                    outcome = kind
                    message = (found.get("message") or "") + (found.text or "")
            outcomes[nodeid] = (outcome, message)
    return r.returncode, out, outcomes


def _red(outcomes):
    return {n for n, (o, _) in outcomes.items() if o in ("failure", "error")}


def test_each_outside_reach_fails_and_each_inside_one_passes(tmp_path):
    root = _project(tmp_path, ["reach"])
    code, out, outcomes = _run(tmp_path, root)
    assert len(outcomes) == len(_OUTSIDE_CASES) + len(_INSIDE_CASES), out[-3000:]
    assert _red(outcomes) == {_REACH + n for n in _OUTSIDE_CASES}, out[-3000:]
    assert code == 1, out[-3000:]
    for name, event in sorted(_OUTSIDE_CASES.items()):
        message = outcomes[_REACH + name][1]
        assert "IsolationError" in message and event in message, (name, message)
    # The guard refused the reach before it happened.
    assert sorted(p.name for p in (tmp_path / "outside").iterdir()) == []


def test_each_further_seam_outside_fails_and_inside_passes(tmp_path):
    root = _project(tmp_path, ["seams"])
    outside = tmp_path / "outside"
    kept = outside / "kept.txt"
    kept.write_text("kept", encoding="utf-8")
    os.chmod(str(kept), 0o644)
    (outside / "__pycache__").mkdir()
    before = os.stat(str(kept))
    code, out, outcomes = _run(tmp_path, root)
    assert len(outcomes) == len(_OUTSIDE_SEAMS) + len(_INSIDE_SEAMS), out[-3000:]
    assert _red(outcomes) == {_SEAMS + n for n in _OUTSIDE_SEAMS}, out[-3000:]
    assert code == 1, out[-3000:]
    for name, event in sorted(_OUTSIDE_SEAMS.items()):
        message = outcomes[_SEAMS + name][1]
        assert "IsolationError" in message and event in message, (name, message)
    # Each reach was refused before it happened.
    after = os.stat(str(kept))
    assert (after.st_mode, after.st_mtime_ns) == (before.st_mode, before.st_mtime_ns)
    assert sorted(p.name for p in outside.rglob("*")) == ["__pycache__", "kept.txt"]
    assert not [p.name for p in root.iterdir() if p.name.startswith("file:")]


def test_the_failure_names_the_test_the_reach_and_the_fix(tmp_path):
    root = _project(tmp_path, ["reach"])
    _, out, outcomes = _run(tmp_path, root, "-k", "outside_write")
    nodeid = _REACH + "test_outside_write"
    target = (tmp_path / "outside" / "written.txt").resolve()
    expected = (
        "%s [call] reached outside its tier 'unit': open %s (writes=temp). "
        "Use tmp_path or the store_copy fixture; or exempt it with a reason in "
        'config/project.json tests.isolation.exempt.writes."%s"'
        % (nodeid, target, nodeid)
    )
    assert expected in outcomes[nodeid][1], out[-3000:]


def test_an_exemption_with_a_reason_turns_its_case_green(tmp_path):
    exempt = {
        "network": {_REACH + "test_outside_socket": "the case proves an exemption"},
        "writes": {_REACH + "test_outside_write": "the case proves an exemption"},
        "stores": {_REACH + "test_outside_sqlite": "the case proves an exemption"},
    }
    root = _project(tmp_path, ["reach"], exempt=exempt)
    code, out, outcomes = _run(tmp_path, root)
    assert len(outcomes) == 7, out[-3000:]
    assert _red(outcomes) == {_REACH + "test_swallowed_write"}, out[-3000:]
    assert code == 1, out[-3000:]


def test_an_exemption_whose_test_reached_nothing_fails_the_run(tmp_path):
    nodeid = _REACH + "test_inside_write"
    root = _project(tmp_path, ["reach"], exempt={"writes": {nodeid: "stale"}})
    code, out, outcomes = _run(tmp_path, root, "-k", "inside")
    assert len(outcomes) == 3 and not _red(outcomes), out[-3000:]
    assert code == 1, out[-3000:]
    assert 'tests.isolation.exempt.writes."%s"' % nodeid in out, out[-3000:]


def test_an_exemption_whose_test_did_not_run_is_not_judged(tmp_path):
    nodeid = _REACH + "test_outside_write"
    root = _project(tmp_path, ["reach"], exempt={"writes": {nodeid: "a reason"}})
    code, out, outcomes = _run(tmp_path, root, "-k", "inside")
    assert len(outcomes) == 3 and not _red(outcomes), out[-3000:]
    assert code == 0, out[-3000:]


# `-n auto` is how `make test` asks for workers: the count is tests.workers,
# which the shipped conftest hands pytest-xdist.
_WORKERS = ("-n", "auto")


def _created(out):
    """The worker count pytest-xdist says it started; None for no worker."""
    found = re.findall(r"created: (\d+)/\1 workers", out)
    return int(found[-1]) if found else None


@pytest.mark.parametrize("workers", [0, 3])
def test_the_worker_count_is_tests_workers(tmp_path, workers):
    root = _project(tmp_path, ["reach"], workers=workers)
    code, out, outcomes = _run(tmp_path, root, *_WORKERS, "-k", "inside")
    assert len(outcomes) == 3 and not _red(outcomes), out[-3000:]
    assert code == 0, out[-3000:]
    assert _created(out) == (workers or None), out[-3000:]


def test_a_worker_count_the_loader_refuses_stops_pytest_naming_the_key(tmp_path):
    root = _project(tmp_path, ["reach"], workers=-1)
    code, out, outcomes = _run(tmp_path, root, *_WORKERS)
    assert code == 4 and not outcomes, out[-3000:]
    assert "tests.workers" in out, out[-3000:]


def test_under_workers_an_exemption_whose_test_reached_nothing_fails_the_run(
    tmp_path,
):
    stale = (_REACH + "test_inside_write", _REACH + "test_inside_socket")
    exempt = {"writes": {stale[0]: "stale"}, "network": {stale[1]: "stale"}}
    root = _project(tmp_path, ["reach"], exempt=exempt, workers=2)
    code, out, outcomes = _run(tmp_path, root, *_WORKERS, "-k", "inside")
    assert _created(out) == 2, out[-3000:]
    assert len(outcomes) == 3 and not _red(outcomes), out[-3000:]
    assert code == 1, out[-3000:]
    assert 'tests.isolation.exempt.writes."%s"' % stale[0] in out, out[-3000:]
    assert 'tests.isolation.exempt.network."%s"' % stale[1] in out, out[-3000:]


def test_under_workers_a_used_exemption_and_one_whose_test_did_not_run_hold(
    tmp_path,
):
    exempt = {
        "network": {_REACH + "test_outside_socket": "the case proves an exemption"},
        "writes": {_REACH + "test_outside_write": "the case proves an exemption"},
        "stores": {_REACH + "test_outside_sqlite": "the case proves an exemption"},
    }
    root = _project(tmp_path, ["reach"], exempt=exempt, workers=2)
    code, out, outcomes = _run(tmp_path, root, *_WORKERS, "-k", "not swallowed")
    assert _created(out) == 2, out[-3000:]
    assert len(outcomes) == 6 and not _red(outcomes), out[-3000:]
    assert code == 0, out[-3000:]
    code, out, outcomes = _run(tmp_path, root, *_WORKERS, "-k", "inside")
    assert len(outcomes) == 3 and not _red(outcomes), out[-3000:]
    assert code == 0, out[-3000:]


def test_a_worker_that_dies_leaves_the_exemption_check_unjudged_and_red(tmp_path):
    root = _project(tmp_path, ["reach"], workers=2)
    (root / "tests" / "unit" / "test_dies.py").write_text(
        "import os\n\nimport pytest\n\npytestmark = pytest.mark.unit\n\n\n"
        "def test_the_worker_dies():\n    os._exit(3)\n",
        encoding="utf-8",
    )
    code, out, _outcomes = _run(tmp_path, root, *_WORKERS, "-k", "inside or dies")
    assert code == 1, out[-3000:]
    assert "ended without its exemption record" in out, out[-3000:]


def _recording_project(tmp_path, workers):
    """A scratch project that can record the expiring tier's findings."""
    root = _project(tmp_path, ["reach"], workers=workers)
    for rel in ("scripts/expiring_tier.py", "scripts/expiring_tier_data.py"):
        shutil.copy(str(_ROOT / rel), str(root / rel))
    return root


@pytest.mark.parametrize("count", ["2", "auto"])
def test_the_expiring_tier_record_is_refused_under_workers(tmp_path, count):
    root = _recording_project(tmp_path, workers=2)
    record = tmp_path / "record.json"
    code, out, outcomes = _run(
        tmp_path, root, "-n", count, "--expiring-tier-record=%s" % record
    )
    assert code == 4 and not outcomes, out[-3000:]
    assert "run it without -n" in out, out[-3000:]
    assert not record.exists(), out[-3000:]


def test_the_expiring_tier_record_runs_when_auto_resolves_to_one_process(tmp_path):
    root = _recording_project(tmp_path, workers=0)
    record = tmp_path / "record.json"
    code, out, outcomes = _run(
        tmp_path, root, *_WORKERS, "-k", "inside", "--expiring-tier-record=%s" % record
    )
    assert len(outcomes) == 3 and not _red(outcomes), out[-3000:]
    assert code == 0, out[-3000:]
    assert json.loads(record.read_text(encoding="utf-8")) == {}, out[-3000:]


@pytest.mark.parametrize("reason", ["", "   "])
def test_a_blank_reason_is_refused_before_any_test_runs(tmp_path, reason):
    nodeid = _REACH + "test_outside_write"
    root = _project(tmp_path, ["reach"], exempt={"writes": {nodeid: reason}})
    code, out, outcomes = _run(tmp_path, root)
    assert code == 4 and not outcomes, out[-3000:]
    assert 'tests.isolation.exempt.writes."%s"' % nodeid in out, out[-3000:]


def test_the_closest_tier_marker_wins_and_xfail_hides_no_reach(tmp_path):
    root = _project(tmp_path, ["tiers"])
    code, out, outcomes = _run(tmp_path, root)
    assert len(outcomes) == 3, out[-3000:]
    assert outcomes[_TIERS + "test_loopback_marked_integration"][0] == "passed"
    assert _red(outcomes) == {
        _TIERS + "test_loopback_under_unit",
        _TIERS + "test_violation_under_xfail",
    }, out[-3000:]
    assert code == 1, out[-3000:]
    assert "(network=none)" in outcomes[_TIERS + "test_loopback_under_unit"][1]


def test_a_listed_store_is_reached_only_through_its_copy(tmp_path):
    root = _project(tmp_path, ["store"], stores=[str(tmp_path / "outside" / "live.db")])
    live = tmp_path / "outside" / "live.db"
    con = sqlite3.connect(str(live))
    con.execute("create table t (x)")
    con.execute("insert into t values ('live')")
    con.commit()
    con.close()
    before = live.read_bytes()
    code, out, outcomes = _run(tmp_path, root)
    refused = (
        "test_reading_the_live_store_is_refused",
        "test_reading_the_live_store_after_a_copy_is_refused",
        "test_reading_the_live_store_after_a_failed_copy_is_refused",
    )
    assert len(outcomes) == len(refused) + 2, out[-3000:]
    assert outcomes[_STORE + "test_store_copy_gives_the_test_its_own_copy"][0] == (
        "passed"
    ), out[-3000:]
    assert _red(outcomes) == {_STORE + n for n in refused} | {
        _STORE + "test_an_unlisted_store_is_named"
    }, out[-3000:]
    for name in refused:
        assert "(stores=temp)" in outcomes[_STORE + name][1], outcomes[_STORE + name]
    assert (
        "tests.isolation.stores"
        in outcomes[_STORE + "test_an_unlisted_store_is_named"][1]
    )
    assert code == 1, out[-3000:]
    assert live.read_bytes() == before
