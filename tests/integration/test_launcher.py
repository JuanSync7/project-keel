"""
title: Integration — the launcher and the search script, as real processes in a scratch repository
kind: tests
layer: n/a
summary: A scratch git repository holding scripts/launch.py, scripts/long_scripts.py, the siblings they import, keel's config/project.json and keel's .gitignore runs the launcher as a real process, with a fake farm program on PATH where a farm is configured. With the shipped config and no own-hosts file a dry run prints exactly one line, `run here limited` at the configured niceness, writes nothing and runs nothing, and a real run prints the same one line, runs the command and records it as a shared-host run. An own-hosts pattern makes the host own, a recorded success within the threshold makes the script short, an argv adapter chosen in a copy of the config submits unless a variable its inside_env names is set, and a local-only script stays here. A farm that never allocates falls back to a limited run, under nice, when the host is spare, and stops with exit 12, running nothing and recording no-capacity, when it is busy or its load is unknown; a farm that refuses ends with exit 2. Neither a busy farm nor the entry the file holds while a command runs, what a killed launch leaves, replaces a measured run over the threshold, so the search script still proposes it. A farm job receives exactly the allowlisted environment plus the adapter's rendered variables, never a planted secret, and a credential reaches it only when launcher.credentials names it for that launch key; otherwise the launch is refused before anything runs. The durations file is git-ignored, whole canonical JSON with one entry per key, and records a failure with its status and an interruption as 130. A state path reached through a symlink, a state path git would list and a git that runs and fails are refused with exit 2 before anything runs. The search script is read-only and ends on each verdict: no recorded runs is exit 13 (ExitCode.NOTHING_JUDGED), a short record exit 0, an unlisted long record exit 1 with a `propose:` line, and a linked durations file exit 2. Not a writer: it writes only under pytest's tmp_path.
@covers scripts/launch.py
@covers scripts/long_scripts.py
"""

import functools
import itertools
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import types
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "tests"))

import git_tree  # noqa: E402
import launch  # noqa: E402
from exit_codes import ExitCode  # noqa: E402

import hermetic_git  # noqa: E402

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("git") is None, reason="git not installed"),
]

_MANIFEST = json.loads((_ROOT / "config" / "project.json").read_text("utf-8"))
_LAUNCHER = _MANIFEST["launcher"]
# The launcher, the search script and the stdlib siblings they import, git_tree's
# own included: what a generated project runs.
_SCRIPTS = (
    "launch.py",
    "long_scripts.py",
    "exit_codes.py",
    "git_tree.py",
    "child_env.py",
    "config_loader.py",
)
_COMMAND = ("python3", "-c", "pass")
_KEY = " ".join(_COMMAND)


def _inside_names():
    return {
        name
        for adapter in _LAUNCHER["farm"]["adapters"].values()
        for name in adapter.get("inside_env", [])
    }


def _build(base):
    """A committed scratch repository holding the launcher; (repo, env)."""
    work = base / "work"
    work.mkdir()
    env = hermetic_git.git_env(work)
    # A run inside a farm job would otherwise decide `in-farm-job` for every case.
    for name in _inside_names():
        env.pop(name, None)
    repo = base / "repo"
    (repo / "scripts").mkdir(parents=True)
    for name in _SCRIPTS:
        shutil.copy(str(_ROOT / "scripts" / name), str(repo / "scripts" / name))
    (repo / "config").mkdir()
    _write_manifest(repo, _MANIFEST)
    shutil.copy(str(_ROOT / ".gitignore"), str(repo / ".gitignore"))
    for argv in (
        ["init", "-q"],
        ["add", "-A"],
        ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "s"],
    ):
        subprocess.run(["git"] + argv, cwd=str(repo), env=env, check=True)
    return repo, env


def _digest(repo):
    return git_tree.snapshot_digest(git_tree.tree_snapshot(str(repo)))


def _write_manifest(repo, manifest):
    (repo / "config" / "project.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def _edited(edit, manifest=None):
    manifest = json.loads(json.dumps(manifest or _MANIFEST))
    edit(manifest["launcher"])
    return manifest


def _launch(repo, env, *args, command=_COMMAND):
    return subprocess.run(
        [sys.executable, "scripts/launch.py"] + list(args) + ["--"] + list(command),
        cwd=str(repo),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )


def _long(repo, env):
    return subprocess.run(
        [sys.executable, "scripts/long_scripts.py"],
        cwd=str(repo),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )


def _line(run):
    lines = run.stderr.splitlines()
    assert len(lines) == 1, run.stderr
    return lines[0]


def _argv_adapter():
    names = [
        n
        for n, a in sorted(_LAUNCHER["farm"]["adapters"].items())
        if a["kind"] == "argv"
    ]
    assert names, "the shipped config holds no argv adapter -- zero items"
    return names[0]


def _durations(repo):
    path = repo / _LAUNCHER["durations_file"]
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    assert text == json.dumps(data, indent=2, sort_keys=True) + "\n", text
    return data


def _executable(path, text):
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _fake_farm(base, mode):
    """(bin dir, dump path): a stand-in for the argv adapter's submit program.
    `never` exits with the not-allocated status the adapter's env names, `refuse`
    with the farm-error status, and `run` writes its argv and environment to the
    dump path, then runs the command after `--` and exits with its status."""
    bin_dir = base / ("farm-" + mode)
    bin_dir.mkdir()
    dump = base / ("farm-" + mode + ".json")
    program = _LAUNCHER["farm"]["adapters"][_argv_adapter()]["submit"][0]
    env_names = sorted(_LAUNCHER["farm"]["adapters"][_argv_adapter()]["env"])
    _executable(
        bin_dir / program,
        "#!%s\n"
        "import json, os, subprocess, sys\n"
        "MODE, DUMP, NAMES = %r, %r, %r\n"
        "values = {n: os.environ[n] for n in NAMES}\n"
        "if MODE == 'never':\n"
        "    sys.exit(int(%r %% values))\n"
        "if MODE == 'refuse':\n"
        "    sys.exit(int(%r %% values))\n"
        "with open(DUMP, 'w') as fh:\n"
        "    json.dump({'argv': sys.argv[1:], 'env': dict(os.environ)}, fh)\n"
        "cut = sys.argv.index('--')\n"
        "sys.exit(subprocess.call(sys.argv[cut + 1:]))\n"
        % (
            sys.executable,
            mode,
            str(dump),
            env_names,
            _status_lookup("not_allocated_status"),
            _status_lookup("farm_error_status"),
        ),
    )
    return bin_dir, dump


def _status_lookup(field):
    """A `%(VAR)s` lookup of the adapter env variable whose template carries
    *field*'s placeholder: the fake reads its status where the real farm does."""
    env = _LAUNCHER["farm"]["adapters"][_argv_adapter()]["env"]
    (name,) = [n for n, t in env.items() if t == "{%s}" % field]
    return "%%(%s)s" % name


def _on_path(env, bin_dir):
    return dict(env, PATH=str(bin_dir) + os.pathsep + env.get("PATH", ""))


def _farm(block):
    block["farm"]["adapter"] = _argv_adapter()


def _refused(run, *phrases):
    assert run.returncode == 2, run
    for phrase in phrases:
        assert phrase in run.stderr, (phrase, run.stderr)


def _in_process(monkeypatch, repo):
    """Point this process at *repo* for an in-process main: its cwd, and no
    inside_env variable a farm-run pytest carries."""
    monkeypatch.chdir(str(repo))
    for name in _inside_names():
        monkeypatch.delenv(name, raising=False)


def _rendered_submit(command):
    adapter = _LAUNCHER["farm"]["adapters"][_argv_adapter()]
    cfg = launch.load_launcher_config(_edited(_farm))
    return launch.make_farm(cfg).submit_argv(
        launch.size_for(launch.script_key(command, "/"), cfg), cfg
    ), adapter


# --- the decision line ------------------------------------------------------


def test_the_shipped_default_dry_run_says_why_and_writes_nothing(tmp_path):
    repo, env = _build(tmp_path)
    before = _digest(repo)
    marker = tmp_path / "ran"
    command = ("python3", "-c", "open(%r, 'w').close()" % str(marker))
    first = _launch(repo, env, "--dry-run", command=_COMMAND)
    second = _launch(repo, env, "--dry-run", command=_COMMAND)
    assert (first.returncode, second.returncode) == (0, 0), (first, second)
    assert first.stdout == "" and first.stderr == second.stderr, (first, second)
    assert _line(first) == (
        "launch: run here limited (nice %d): host shared (no own-hosts file); "
        'script "python3 -c pass" unknown (never recorded); '
        "farm none (no farm configured)" % _LAUNCHER["limited"]["niceness"]
    )
    host = socket.gethostname().strip()
    assert not host or host not in first.stderr, "the line names the host"
    assert str(tmp_path) not in first.stderr, "the line names an absolute path"
    dry = _launch(repo, env, "--dry-run", command=command)
    assert dry.returncode == 0 and not marker.exists(), "a dry run ran the command"
    assert _digest(repo) == before
    assert not (repo / _LAUNCHER["durations_file"]).parent.exists()


def test_the_shipped_default_runs_here_limited_through_the_none_adapter(tmp_path):
    repo, env = _build(tmp_path)
    marker = tmp_path / "nice"
    command = (
        "python3",
        "-c",
        "import os, sys; open(sys.argv[1], 'w').write(str(os.nice(0)))",
        str(marker),
    )
    run = _launch(repo, env, command=command)
    assert run.returncode == 0, run
    assert _line(run).startswith(
        "launch: run here limited (nice %d): host shared (no own-hosts file); "
        % _LAUNCHER["limited"]["niceness"]
    ), run.stderr
    assert _line(run).endswith("farm none (no farm configured)"), run.stderr
    expected = min(19, os.nice(0) + _LAUNCHER["limited"]["niceness"])
    assert int(marker.read_text()) == expected, "the command did not run under nice"
    (key,) = _durations(repo)
    record = _durations(repo)[key]
    assert key == launch.script_key(list(command), str(repo)), key
    assert (record["outcome"], record["status"], record["where"]) == (
        "succeeded",
        0,
        "shared-host",
    ), record
    assert type(record["seconds"]) is int and record["seconds"] >= 0, record


def test_an_own_host_and_a_recorded_short_script_run_here(tmp_path):
    repo, env = _build(tmp_path)
    own = repo / _LAUNCHER["own_hosts_file"]
    # `*` matches every host, so no host name is written to make this host own.
    own.write_text(json.dumps({"own_hosts": ["*"]}), encoding="utf-8")
    run = _launch(repo, env, "--dry-run")
    assert run.returncode == 0, run
    assert _line(run).startswith(
        "launch: run here: host own (an own_hosts pattern matches this host); "
    ), run.stderr
    run = _launch(repo, env)
    assert run.returncode == 0, run
    assert _durations(repo)[_KEY]["where"] == "own-host"
    own.unlink()

    durations = repo / _LAUNCHER["durations_file"]
    limit = _LAUNCHER["long_after_seconds"]
    record = {"outcome": "succeeded", "seconds": limit, "status": 0}
    record["where"] = "shared-host"
    durations.write_text(json.dumps({_KEY: record}), encoding="utf-8")
    run = _launch(repo, env, "--dry-run")
    assert run.returncode == 0, run
    assert (
        'script "python3 -c pass" short (last run succeeded in %d s <= %d s)'
        % (limit, limit)
    ) in _line(run), run.stderr


def test_a_farm_in_config_submits_unless_inside_a_job_or_local_only(tmp_path):
    repo, env = _build(tmp_path)
    name = _argv_adapter()
    inside = _LAUNCHER["farm"]["adapters"][name]["inside_env"]
    assert inside, "the argv adapter names no inside_env variable -- zero items"

    _write_manifest(repo, _edited(_farm))
    run = _launch(repo, env, "--dry-run")
    assert run.returncode == 0, run
    assert _line(run).startswith("launch: submit to farm %s: host shared" % name)
    assert _line(run).endswith(
        "farm %s (submitting, wait up to %d s)"
        % (name, _LAUNCHER["farm"]["wait_seconds"])
    ), run.stderr

    inside_env = dict(env, **{inside[0]: "1"})
    run = _launch(repo, inside_env, "--dry-run")
    assert _line(run).startswith(
        "launch: run here: host in-farm-job (already inside a farm job)"
    ), run.stderr

    def local(block):
        _farm(block)
        block["local_only"] = {_KEY: "needs a file on this disk"}

    _write_manifest(repo, _edited(local))
    run = _launch(repo, env, "--dry-run")
    assert _line(run).endswith(
        "farm %s (not used: local-only, needs a file on this disk)" % name
    ), run.stderr


# --- the farm ---------------------------------------------------------------


def test_a_full_farm_with_an_idle_host_runs_here_limited_and_a_busy_host_stops_with_no_capacity(
    tmp_path, monkeypatch, capsys
):
    repo, env = _build(tmp_path)
    name = _argv_adapter()
    wait = _LAUNCHER["farm"]["wait_seconds"]
    bin_dir, _dump = _fake_farm(tmp_path, "never")
    marker = tmp_path / "nice"
    command = (
        "python3",
        "-c",
        "import os, sys; open(sys.argv[1], 'w').write(str(os.nice(0))); sys.exit(4)",
        str(marker),
    )
    key = launch.script_key(list(command), str(repo))

    def idle(block):
        _farm(block)
        # 64 per cpu is the most the loader accepts: a load no real host reaches,
        # so the child-process run sees this host as spare.
        block["spare"]["max_load_per_cpu"] = 64

    _write_manifest(repo, _edited(idle))
    run = _launch(repo, _on_path(env, bin_dir), command=command)
    assert run.returncode == 4, run
    lines = run.stderr.splitlines()
    assert len(lines) == 2 and all(ln.startswith("launch: ") for ln in lines), lines
    assert lines[0].startswith("launch: submit to farm %s: " % name), lines
    assert lines[1].startswith(
        "launch: run here limited (nice %d): host shared"
        % _LAUNCHER["limited"]["niceness"]
    ), lines
    assert (
        "farm %s (did not allocate within %d s; host spare (load " % (name, wait)
    ) in lines[1]
    expected = min(19, os.nice(0) + _LAUNCHER["limited"]["niceness"])
    assert int(marker.read_text()) == expected, "the fallback did not run under nice"
    record = _durations(repo)[key]
    assert (record["outcome"], record["status"], record["where"]) == (
        "failed",
        4,
        "shared-host",
    ), record
    marker.unlink()

    # Busy and unknown load, in-process with the load injected, so the verdict
    # does not depend on what else this host is running.
    _write_manifest(repo, _edited(_farm))
    _in_process(monkeypatch, repo)
    submit, adapter = _rendered_submit(command)
    for load in ((1e6, 1e6, 1e6), None):
        handed = []

        def never(argv, cwd, env, handed=handed):
            handed.append(argv)
            return types.SimpleNamespace(returncode=adapter["not_allocated_status"])

        capsys.readouterr()
        rc = launch.main(
            ["--root", str(repo), "--"] + list(command),
            runner=never,
            loadavg=lambda load=load: load,
            nicer=lambda n: pytest.fail("a stopped launch lowered its priority"),
        )
        err = capsys.readouterr().err
        assert rc == ExitCode.NO_CAPACITY == 12, err
        assert handed == [submit + list(command)], handed
        assert type(handed[0]) is list
        last = err.splitlines()[-1]
        assert last.startswith("launch: "), last
        what, rest = last[len("launch: ") :].split(": ", 1)
        on, next_step = rest.rsplit("; ", 1)
        assert "did not start" in what and "launcher.farm.wait_seconds" in what, last
        assert on == json.dumps(key) and "wait_seconds" in next_step, last
        assert not marker.exists(), "a stopped launch ran the command"
        record = _durations(repo)[key]
        assert record == {
            "outcome": "no-capacity",
            "seconds": None,
            "status": None,
            "where": "farm",
        }, record

    refusing, _ = _fake_farm(tmp_path, "refuse")
    run = _launch(repo, _on_path(env, refusing), command=command)
    _refused(run, "refused the submission")
    assert not marker.exists(), "a refused submission ran the command"
    # The command never started, so the entry it replaced is put back.
    assert _durations(repo)[key] == record, _durations(repo)[key]


def test_a_full_farm_or_a_killed_run_keeps_a_measured_long_record_for_long_scripts(
    tmp_path, monkeypatch, capsys
):
    repo, env = _build(tmp_path)
    _write_manifest(repo, _edited(_farm))
    _in_process(monkeypatch, repo)
    key = launch.script_key(list(_COMMAND), str(repo))
    limit = _LAUNCHER["long_after_seconds"]
    adapter = _LAUNCHER["farm"]["adapters"][_argv_adapter()]
    long_run = {
        "outcome": "succeeded",
        "seconds": limit + 100,
        "status": 0,
        "where": "farm",
    }
    path = repo / _LAUNCHER["durations_file"]
    path.parent.mkdir()
    path.write_text(json.dumps({key: long_run}), encoding="utf-8")

    def proposes():
        run = _long(repo, env)
        assert run.returncode == 1, run
        return [ln for ln in run.stdout.splitlines() if ln.startswith("propose: ")]

    assert proposes() == [
        "propose: %s ran %d s on its last recorded run (outcome succeeded), "
        "over launcher.long_after_seconds (%d); add it to config/project.json "
        "launcher.long_scripts" % (json.dumps(key), limit + 100, limit)
    ]
    before = proposes()

    # A farm that never starts the command, on a busy host: no run happened, so
    # the measured duration is still the last recorded run.
    rc = launch.main(
        ["--root", str(repo), "--"] + list(_COMMAND),
        runner=lambda argv, cwd, env: types.SimpleNamespace(
            returncode=adapter["not_allocated_status"]
        ),
        loadavg=lambda: (1e6, 1e6, 1e6),
    )
    assert rc == ExitCode.NO_CAPACITY, capsys.readouterr().err
    assert _durations(repo) == {key: long_run}
    assert proposes() == before

    # What a SIGKILL during the run would leave: the file as it is while the
    # command runs, read by the stand-in for the farm.
    seen = []

    def killed(argv, cwd, env):
        seen.append(_durations(repo))
        return types.SimpleNamespace(returncode=adapter["not_allocated_status"])

    launch.main(
        ["--root", str(repo), "--"] + list(_COMMAND),
        runner=killed,
        loadavg=lambda: (1e6, 1e6, 1e6),
    )
    assert seen == [{key: long_run}], seen
    capsys.readouterr()


class _HeldStderr(object):
    """A stderr that keeps what it was given until flush, as a block-buffered
    pipe does under a Python older than 3.9, the host python3 the shebang may
    run."""

    def __init__(self):
        self.held, self.flushed = "", ""

    def write(self, text):
        self.held += text

    def flush(self):
        self.flushed, self.held = self.flushed + self.held, ""


def test_each_decision_line_is_flushed_before_the_command_it_names_starts(
    tmp_path, monkeypatch
):
    repo, _env = _build(tmp_path)
    _write_manifest(repo, _edited(_farm))
    _in_process(monkeypatch, repo)
    submit, adapter = _rendered_submit(list(_COMMAND))
    err = _HeldStderr()
    monkeypatch.setattr(sys, "stderr", err)
    seen = []

    def farm_then_here(argv, cwd, env):
        seen.append(err.flushed.count("launch: "))
        status = adapter["not_allocated_status"] if len(seen) == 1 else 0
        return types.SimpleNamespace(returncode=status)

    rc = launch.main(
        ["--root", str(repo), "--"] + list(_COMMAND),
        runner=farm_then_here,
        loadavg=lambda: (0.0, 0.0, 0.0),
        nicer=lambda n: None,
    )
    assert rc == ExitCode.SUCCESS, err.flushed + err.held
    # The farm attempt starts after the first line is out, the fallback after
    # the second, so a reader of the pipe sees each reason before the output.
    assert seen == [1, 2], (seen, err.flushed, err.held)


def _child_env_keys(repo, env):
    """The names build_child_env gives a child of *repo* under *env*, read by a
    child of the same interpreter, as the launcher reads them."""
    code = (
        "import json, sys; sys.path.insert(0, 'scripts'); import child_env; "
        "print(json.dumps(sorted(child_env.build_child_env(root='.'))))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(repo),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    assert out.returncode == 0, out.stderr
    return set(json.loads(out.stdout))


def test_a_farm_job_receives_only_the_allowlisted_environment(tmp_path):
    repo, env = _build(tmp_path)
    bin_dir, dump = _fake_farm(tmp_path, "run")
    env = dict(_on_path(env, bin_dir), PLANTED_SECRET="x", OPENAI_API_KEY="sk-test")
    submit, adapter = _rendered_submit(list(_COMMAND))
    rendered = launch.make_farm(
        launch.load_launcher_config(_edited(_farm))
    ).submit_env_extra(
        launch.size_for(_KEY, launch.load_launcher_config(_edited(_farm))),
        launch.load_launcher_config(_edited(_farm)),
    )
    assert set(rendered) == set(adapter["env"]) and rendered, rendered

    _write_manifest(repo, _edited(_farm))
    run = _launch(repo, env)
    assert run.returncode == 0, run
    got = json.loads(dump.read_text())
    assert got["argv"] == submit[1:] + list(_COMMAND), got["argv"]
    baseline = _child_env_keys(repo, env)
    assert set(got["env"]) == baseline | set(rendered), sorted(
        set(got["env"]) ^ (baseline | set(rendered))
    )
    assert {k: got["env"][k] for k in rendered} == rendered
    assert "PLANTED_SECRET" not in got["env"] and "OPENAI_API_KEY" not in got["env"]
    first = set(got["env"])
    dump.unlink()

    # The allowlist now copies the credential: no launch key names it, so the
    # launch is refused before the farm is asked.
    allowed = json.loads(json.dumps(_edited(_farm)))
    allowed["child_env"]["names"].append("OPENAI_API_KEY")
    allowed["child_env"].setdefault("credentialed_values", {})["OPENAI_API_KEY"] = (
        "a test planting a model key"
    )
    _write_manifest(repo, allowed)
    run = _launch(repo, env)
    _refused(run, "OPENAI_API_KEY", "launcher.credentials")
    assert not dump.exists(), "a refused launch reached the farm"
    assert "sk-test" not in run.stderr

    def named(block):
        block["credentials"] = {
            _KEY: {"model_adapter": "openai-compatible", "names": ["OPENAI_API_KEY"]}
        }

    _write_manifest(repo, _edited(named, allowed))
    # The first run's record proves the command short, which would keep it here.
    (repo / _LAUNCHER["durations_file"]).unlink()
    run = _launch(repo, env)
    assert run.returncode == 0, run
    got = json.loads(dump.read_text())
    assert set(got["env"]) - first == {"OPENAI_API_KEY"}, sorted(
        set(got["env"]) ^ first
    )
    assert got["env"]["OPENAI_API_KEY"] == "sk-test"
    assert "PLANTED_SECRET" not in got["env"]
    assert _durations(repo)[_KEY]["where"] == "farm"


# --- the record ---------------------------------------------------------------


def _git(repo, env, *argv):
    return subprocess.run(
        ["git"] + list(argv),
        cwd=str(repo),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )


def test_the_durations_file_is_ignored_whole_canonical_and_records_failure_and_interruption(
    tmp_path, monkeypatch
):
    repo, env = _build(tmp_path)
    run = _launch(repo, env)
    assert run.returncode == 0, run
    assert (
        _git(repo, env, "check-ignore", "-q", _LAUNCHER["durations_file"]).returncode
        == 0
    )
    assert _git(repo, env, "status", "--porcelain").stdout == ""
    assert _durations(repo)[_KEY]["outcome"] == "succeeded"

    failing = ("python3", "-c", "import sys; sys.exit(3)")
    run = _launch(repo, env, command=failing)
    assert run.returncode == 3, run
    record = _durations(repo)[" ".join(failing)]
    assert (record["outcome"], record["status"]) == ("failed", 3), record

    killed = (
        "python3",
        "-c",
        "import os, signal; signal.signal(signal.SIGINT, signal.SIG_DFL); "
        "os.kill(os.getpid(), signal.SIGINT)",
    )
    run = _launch(repo, env, command=killed)
    assert run.returncode == 130, run
    record = _durations(repo)[" ".join(killed)]
    assert (record["outcome"], record["status"]) == ("interrupted", 130), record
    assert type(record["seconds"]) is int, record

    def interrupt(argv, cwd, env):
        raise KeyboardInterrupt

    _in_process(monkeypatch, repo)
    rc = launch.main(
        ["--root", str(repo), "--", "make", "x"],
        runner=interrupt,
        clock=functools.partial(next, itertools.count(10.0, 2.4)),
        nicer=lambda n: None,
    )
    assert rc == ExitCode.INTERRUPTED == 130
    assert _durations(repo)["make x"] == {
        "outcome": "interrupted",
        "seconds": 2,
        "status": 130,
        "where": "shared-host",
    }
    data = _durations(repo)
    assert sorted(data) == sorted([_KEY, " ".join(failing), " ".join(killed), "make x"])
    text = (repo / _LAUNCHER["durations_file"]).read_text(encoding="utf-8")
    assert str(tmp_path) not in text, "the record holds an absolute path"
    host = socket.gethostname().strip()
    assert not host or host not in text, "the record names the host"
    assert _git(repo, env, "status", "--porcelain").stdout == ""


def test_a_symlinked_or_tracked_state_path_is_refused_before_anything_runs(tmp_path):
    repo, env = _build(tmp_path)
    marker = tmp_path / "ran"
    command = ("python3", "-c", "open(%r, 'w').close()" % str(marker))
    outside = tmp_path / "outside"
    outside.mkdir()
    state_dir = (repo / _LAUNCHER["durations_file"]).parent
    os.symlink(str(outside), str(state_dir))
    _refused(_launch(repo, env, command=command), "through a symlink")
    assert list(outside.iterdir()) == [] and not marker.exists()
    state_dir.unlink()

    def tracked(block):
        block["durations_file"] = "config/durations.json"

    _write_manifest(repo, _edited(tracked))
    _refused(_launch(repo, env, command=command), "git would list", "durations")
    assert not marker.exists() and not (repo / "config" / "durations.json").exists()
    _write_manifest(repo, _MANIFEST)

    own = repo / _LAUNCHER["own_hosts_file"]
    target = tmp_path / "own.json"
    target.write_text(json.dumps({"own_hosts": ["*"]}), encoding="utf-8")
    os.symlink(str(target), str(own))
    _refused(_launch(repo, env, command=command), "through a symlink")
    assert not marker.exists()
    own.unlink()

    # A git that runs and fails is unknown, never the no-git path.
    git_bin = tmp_path / "broken-git"
    git_bin.mkdir()
    _executable(
        git_bin / "git",
        "#!%s\nimport sys\nsys.stderr.write('fatal: broken\\n')\nsys.exit(128)\n"
        % sys.executable,
    )
    _refused(
        _launch(repo, _on_path(env, git_bin), command=command), "git could not say"
    )
    assert not marker.exists()


def test_a_bad_block_and_a_missing_command_are_refused(tmp_path):
    repo, env = _build(tmp_path)
    _refused(_launch(repo, env, "--dry-run", command=()), "no command after `--`")
    _refused(_launch(repo, env, command=()), "no command after `--`")

    def nice(block):
        block["limited"]["niceness"] = 0

    _write_manifest(repo, _edited(nice))
    _refused(_launch(repo, env), "launcher.limited.niceness")
    assert not (repo / _LAUNCHER["durations_file"]).exists()

    help_run = subprocess.run(
        [sys.executable, "scripts/launch.py", "--help"],
        cwd=str(repo),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    assert help_run.returncode == 0 and "--dry-run" in help_run.stdout, help_run


# --- the search script ----------------------------------------------------------


def test_long_scripts_is_read_only_and_ends_on_each_verdict(tmp_path):
    repo, env = _build(tmp_path)
    path = repo / _LAUNCHER["durations_file"]
    limit = _LAUNCHER["long_after_seconds"]

    def state():
        launched = path.parent
        files = (
            {p.name: p.read_bytes() for p in sorted(launched.iterdir())}
            if launched.is_dir()
            else None
        )
        return _digest(repo), files

    def judged(records):
        if records is not None:
            path.parent.mkdir(exist_ok=True)
            path.write_text(json.dumps(records), encoding="utf-8")
        before = state()
        run = _long(repo, env)
        assert state() == before, "long_scripts changed the tree"
        return run

    def rec(outcome, seconds):
        return {"outcome": outcome, "seconds": seconds, "status": 0, "where": "farm"}

    run = judged(None)
    assert run.returncode == 13 and "no recorded runs" in run.stderr, run
    run = judged({"make a": rec("incomplete", None)})
    assert run.returncode == 13 and "no recorded runs" in run.stderr, run
    assert 'unjudged: "make a"' in run.stdout, run
    run = judged({"make lint": rec("succeeded", 30)})
    assert run.returncode == 0, run
    assert (
        "judged 1 recorded run(s); none over %d s is unlisted" % limit in run.stdout
    ), run
    run = judged(
        {"make lint": rec("succeeded", 30), "make x": rec("succeeded", limit + 1)}
    )
    assert run.returncode == 1, run
    proposals = [ln for ln in run.stdout.splitlines() if ln.startswith("propose: ")]
    assert proposals == [
        'propose: "make x" ran %d s on its last recorded run (outcome succeeded), '
        "over launcher.long_after_seconds (%d); add it to config/project.json "
        "launcher.long_scripts" % (limit + 1, limit)
    ], run.stdout
    assert "1 script(s) over the threshold are not listed" in run.stderr, run

    path.write_text("{", encoding="utf-8")
    _refused(_long(repo, env), "durations")
    path.unlink()
    outside = tmp_path / "elsewhere.json"
    outside.write_text(
        json.dumps({"make lint": rec("succeeded", 30)}), encoding="utf-8"
    )
    os.symlink(str(outside), str(path))
    _refused(_long(repo, env), "through a symlink")
