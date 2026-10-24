"""
title: Integration — every agent tool child and the MCP action doer is bounded
kind: tests
layer: backend
summary: Each tool runner an agent or MCP server starts a child through — `_run` in agents/doc_reviewer, agents/index_enforcer, agents/practice_refactor and agents/wiki_navigator `_brain.py`, and `_run_doer` in mcp/action_server.py — goes through scripts/resource_limits.py run_tool, so a real child that outlives config/project.json `agents.tool_timeout_seconds` has its session ended and is refused as ChildTimedOut naming that key, one that writes past `agents.tool_max_output_bytes` is refused as ChildOutputTooLarge naming that key, and one within both returns its status, stdout and stderr, with the given stdin where the runner takes one. The limits are handed in through a patched tool_limits so a child runs one second, not the shipped 15000. At the least `agents.tool_timeout_seconds` tool_limits accepts for a tree's gate keys, run_tool around scripts/run_make_target.py on a make that ignores SIGTERM and leaves a setsid process holding its output returns the runner's own result, timed_out and escaped, not ChildTimedOut: that run waits its grace twice. The class is held too: no Python file under agents/ or mcp/ imports subprocess, so a new tool runner cannot start an unbounded child beside these; a scan over zero files fails. Every child runs under this interpreter: a short one-liner, or for the reproduction the gate runner and a stand-in make.
"""

import ast
import contextlib
import importlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "mcp"))

from scripts import config_loader, resource_limits  # noqa: E402

pytestmark = pytest.mark.integration

_PY = sys.executable
_BRAINS = (
    "agents.doc_reviewer._brain",
    "agents.index_enforcer._brain",
    "agents.practice_refactor._brain",
    "agents.wiki_navigator._brain",
)
_TAKES_STDIN = {"agents.doc_reviewer._brain", "agents.practice_refactor._brain"}
# Runners that take, by keyword, the root whose config supplies the limits.
_TAKES_ROOT = _TAKES_STDIN | {"agents.wiki_navigator._brain"}
_SITES = _BRAINS + ("action_server",)


def _runner(site, tmp_path, monkeypatch):
    """A function running `python -c <code>` through *site*'s tool runner, and
    returning what that runner returns."""
    module = importlib.import_module(site)
    if site != "action_server":
        # Each brain prefixes the interpreter, so `-c` runs the code.
        # None is this checkout; the patched tool_limits ignores it anyway.
        rooted = {"root": None} if site in _TAKES_ROOT else {}
        return lambda code, stdin=None: (
            module._run(["-c", code], stdin=stdin, **rooted)
            if stdin is not None
            else module._run(["-c", code], **rooted)
        )
    # The doer runs `<python> <doer> --root <root> <args>`: a doer file of
    # the test's own stands in for scripts/jobs/rebuild_index.py.
    counter = [0]

    def run(code, stdin=None):
        assert stdin is None, "the action doer takes no stdin"
        counter[0] += 1
        doer = tmp_path / ("doer_%d.py" % counter[0])
        doer.write_text(code, encoding="utf-8")
        monkeypatch.setattr(module, "_REBUILD_DOER", str(doer))
        return module._run_doer(str(tmp_path), [])

    return run


@pytest.fixture
def short_limits(monkeypatch):
    monkeypatch.setattr(resource_limits, "tool_limits", lambda root=None: (1, 4096))


@pytest.mark.parametrize("site", _SITES)
def test_a_tool_child_past_its_time_limit_is_ended_and_names_the_key(
    site, tmp_path, monkeypatch, short_limits
):
    run = _runner(site, tmp_path, monkeypatch)
    started = time.monotonic()
    with pytest.raises(resource_limits.ChildTimedOut) as caught:
        run("import time; time.sleep(20)")
    assert time.monotonic() - started < 10
    assert "agents.tool_timeout_seconds" in str(caught.value)


@pytest.mark.parametrize("site", _SITES)
def test_a_tool_child_past_its_output_cap_is_ended_and_names_the_key(
    site, tmp_path, monkeypatch, short_limits
):
    run = _runner(site, tmp_path, monkeypatch)
    with pytest.raises(resource_limits.ChildOutputTooLarge) as caught:
        run("import sys; sys.stdout.write('x' * 10000)")
    assert "agents.tool_max_output_bytes" in str(caught.value)


@pytest.mark.parametrize("site", _SITES)
def test_a_tool_child_within_its_limits_returns_status_and_output(
    site, tmp_path, monkeypatch, short_limits
):
    run = _runner(site, tmp_path, monkeypatch)
    done = run("import sys; print('out'); sys.stderr.write('err'); sys.exit(3)")
    assert tuple(done) == (3, "out\n", "err")


@pytest.mark.parametrize("site", sorted(_TAKES_STDIN))
def test_a_tool_child_gets_the_stdin_its_runner_is_given(
    site, tmp_path, monkeypatch, short_limits
):
    run = _runner(site, tmp_path, monkeypatch)
    done = run("import sys; print(sys.stdin.read())", stdin="spec")
    assert done[1] == "spec\n"


# A make that ignores SIGTERM, so the gate runner's stop waits out its whole
# grace, and starts a grandchild that leaves make's session (setsid) holding
# make's output, so the runner's read of that output waits out its grace too.
_STUBBORN_MAKE = """#!%(py)s
import os, pathlib, signal, subprocess, sys, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
marks = pathlib.Path(%(marks)r)
child = subprocess.Popen([sys.executable, '-c', %(escapee)r])
deadline = time.monotonic() + 30
while not (marks / 'ready').exists() and time.monotonic() < deadline:
    time.sleep(0.05)
(marks / 'pids').write_text('%%d %%d' %% (os.getpid(), child.pid))
print('make started its child', flush=True)
time.sleep(600)
"""
_ESCAPEE = (
    "import os, pathlib, time\n"
    "os.setsid()\n"
    "pathlib.Path(%r, 'ready').write_text('1')\n"
    "time.sleep(600)\n"
)


def _least_accepted(root):
    """The smallest agents.tool_timeout_seconds tool_limits accepts for
    *root*'s gate keys, found by asking it, so the case runs at the bound
    the code enforces rather than at one the test restates."""
    path = Path(root) / "config" / "project.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    for seconds in range(1, 600):
        manifest["agents"]["tool_timeout_seconds"] = seconds
        path.write_text(json.dumps(manifest), encoding="utf-8")
        try:
            resource_limits.tool_limits(root)
        except config_loader.WrongValue:
            continue
        return seconds
    raise AssertionError("tool_limits accepted no time limit under 600 s")


def test_a_gate_run_at_the_least_accepted_tool_limit_returns_the_runners_result(
    tmp_path, monkeypatch, capsys
):
    """The reviewer's reproduction: run_tool around scripts/run_make_target.py
    on a make that ignores SIGTERM and leaves a setsid process holding its
    output. On its timeout the runner spends its grace once ending make's
    session and once more waiting on make's output, then snapshots the tree;
    at the least time limit tool_limits accepts, the runner still returns its
    own structured result (timed_out, escaped) rather than being ended as
    ChildTimedOut. The grace is the larger share of the bound on purpose, so a
    bound that counts it once falls short by more than the margin covers."""
    tree = tmp_path / "tree"
    marks = tmp_path / "marks"
    bin_dir = tmp_path / "bin"
    for where in (tree / "config", marks, bin_dir):
        where.mkdir(parents=True)
    manifest = config_loader.read(str(_ROOT))
    manifest["make_targets"]["gate_timeout_seconds"] = 1
    manifest["make_targets"]["gate_stop_grace_seconds"] = 8
    manifest["agents"]["tool_gate_margin_seconds"] = 5
    (tree / "config" / "project.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    (tree / "Makefile").write_text(
        "check: ## [local] Validate\n\tc\n", encoding="utf-8"
    )
    r = subprocess.run(["git", "init", "-q"], cwd=str(tree), capture_output=True)
    assert r.returncode == 0, r.stderr
    make = bin_dir / "make"
    make.write_text(
        _STUBBORN_MAKE
        % {"py": sys.executable, "marks": str(marks), "escapee": _ESCAPEE % str(marks)},
        encoding="utf-8",
    )
    make.chmod(0o755)
    monkeypatch.setenv("PATH", "%s%s%s" % (bin_dir, os.pathsep, os.environ["PATH"]))
    monkeypatch.delenv("PY", raising=False)
    least = _least_accepted(str(tree))
    capsys.readouterr()
    runner = str(_ROOT / "scripts" / "run_make_target.py")
    try:
        done = resource_limits.run_tool(
            [_PY, runner, "check", "--json", "--dir", str(tree)],
            cwd=str(tree),
            root=str(tree),
        )
    finally:
        pids_file = marks / "pids"
        pids = (
            [int(p) for p in pids_file.read_text(encoding="utf-8").split()]
            if pids_file.exists()
            else []
        )
        for pid in pids:
            # The escapee is outside every session anything here ends.
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)
    assert len(pids) == 2, "the stubborn make never started its escapee"
    result = json.loads(done.stdout)
    assert done.returncode == 1, (least, done.stderr)
    assert result["timed_out"] is True and result["ok"] is False, result
    assert [p.split()[0] for p in result["escaped"]] == [str(pids[1])], result


def _imports_subprocess(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        if any(name.split(".")[0] == "subprocess" for name in names):
            return True
    return False


def test_no_agent_or_mcp_module_starts_a_child_outside_the_bounded_runner():
    files = sorted(
        p
        for top in ("agents", "mcp")
        if (_ROOT / top).is_dir()
        for p in (_ROOT / top).rglob("*.py")
    )
    assert files, "no Python file under agents/ or mcp/: the scan judged nothing"
    offenders = [str(p.relative_to(_ROOT)) for p in files if _imports_subprocess(p)]
    assert offenders == [], (
        "these import subprocess; start a tool child through "
        "scripts/resource_limits.py run_tool so agents.tool_timeout_seconds "
        "bounds it: %s" % offenders
    )
