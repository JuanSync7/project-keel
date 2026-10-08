"""
title: Integration — every [local] make target leaves the tree as it found it
kind: tests
layer: n/a
summary: The runtime half of check_W. A label is a claim, and only running the target can test it, so this runs every make target whose label (closed over its prerequisites) is exactly [local] through scripts/run_make_target.py, in a hermetic clone of the working tree, and fails any that is red, changes what git sees, or writes the fresh empty HOME it runs under; writes under the kept XDG dirs are not seen. Each target gets its own empty HOME in the test's scratch, outside the swept tree, so a verdict cannot depend on the dotfiles of the host or user that runs it; config/project.json `make_targets.effect_proof_kept_dirs` names the XDG base-dir variables kept beside it (the caller's absolute value, else HOME/<path> under the caller's HOME, else unset), so a tool's cache survives between targets. Before the first target the sweep checks that scripts/child_env.py hands the sandbox HOME and every kept value to the child, and raises if it does not. A target that cannot run unattended is skipped only by name and reason in config/project.json `make_targets.effect_proof_skip`, every skip is printed, a skip naming no [local] target is stale, and a sweep that ran nothing fails. Planted targets prove the sweep can fail: one edits a tracked file, one writes an untracked one, one writes its HOME, and one leaves a FIFO and one a socket there, which the HOME snapshot records by type without opening, so neither hangs nor crashes the sweep.
"""

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import pytest

import hermetic_git

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402
import child_env  # noqa: E402
import run_make_target as rmt  # noqa: E402

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("make") is None, reason="make not installed"),
]

# A whole-suite target in the sweep runs for minutes; one that runs for longer is
# a hang, and a hang must fail rather than stall the suite.
_TARGET_TIMEOUT = 1800
_LOCAL = ("local",)


def _policy(root):
    with open(
        os.path.join(str(root), "config", "project.json"), encoding="utf-8"
    ) as fh:
        policy, errs = cs.make_targets_policy(json.load(fh))
    assert errs == [], errs
    return policy


def _local_targets(root):
    return sorted(
        t for t, (labels, _) in cs.target_effects(str(root)).items() if labels == _LOCAL
    )


def _home_snapshot(home):
    """relpath -> ('f', bytes) | ('l', link target) | ('d',) | ('o', mode
    type) for everything under *home*, byte for byte. A link is recorded, never
    followed, so a target that plants one pointing outside HOME is still seen.
    Only a regular file is opened: a FIFO, socket or device is recorded by its
    type, because opening a FIFO blocks with no timeout and a socket cannot be
    opened. An entry it cannot read raises: an unreadable file would otherwise
    compare equal to nothing."""

    def _raise(exc):
        raise exc

    snap = {}
    for dirpath, dirnames, filenames in os.walk(home, onerror=_raise):
        for name in sorted(dirnames + filenames):
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, home)
            mode = os.lstat(path).st_mode
            if stat.S_ISLNK(mode):
                snap[rel] = ("l", os.readlink(path))
            elif stat.S_ISDIR(mode):
                snap[rel] = ("d",)
            elif stat.S_ISREG(mode):
                with open(path, "rb") as fh:
                    snap[rel] = ("f", fh.read())
            else:
                snap[rel] = ("o", stat.S_IFMT(mode))
    return snap


def _home_changes(before, after):
    return sorted(
        rel for rel in set(before) | set(after) if before.get(rel) != after.get(rel)
    )


def _kept_dirs(kept):
    """The value each kept variable takes beside the sandbox HOME.

    -> {name: (value or None, source)}: the caller's own value when it is a
    non-empty absolute path, else HOME/<path> under the caller's HOME, else
    None (the variable is unset, and a tool falls back to the sandbox HOME)."""
    caller_home = os.environ.get("HOME", "")
    out = {}
    for name in sorted(kept):
        own = os.environ.get(name, "")
        if own and os.path.isabs(own):
            out[name] = (own, "caller")
        elif caller_home and os.path.isabs(caller_home):
            out[name] = (os.path.join(caller_home, *kept[name].split("/")), "derived")
        else:
            out[name] = (None, "unset")
    return out


def _child_carries(home, kept):
    """Raise unless scripts/child_env.py hands make the sandbox HOME and each
    kept value: the sandbox is evidence only if the child runs under it."""
    if "HOME" not in child_env.load_policy().names:
        raise AssertionError(
            "config/project.json child_env.names lacks HOME, so make would run "
            "without the sandbox HOME the effect proof sets"
        )
    env = child_env.build_child_env()
    if env.get("HOME") != home:
        raise AssertionError("the child's HOME is not the sandbox HOME %s" % home)
    for name, (value, _source) in sorted(kept.items()):
        if env.get(name) != value:
            raise AssertionError(
                "make_targets.effect_proof_kept_dirs keeps %s, but the child "
                "receives %r for it, not %r -- name it in child_env"
                % (name, env.get(name), value)
            )


def _sweep(root, py, sandbox_base):
    """Run every [local] target not skipped through the gate runner, each
    under a fresh empty HOME made in *sandbox_base*.

    -> (ran, failures, skipped). A failure is red, refused, changed the tree,
    or changed its HOME; each carries what a reader needs to act on it."""
    root, sandbox_base = (
        os.path.realpath(str(root)),
        os.path.realpath(str(sandbox_base)),
    )
    if os.path.commonpath([root, sandbox_base]) == root:
        raise AssertionError(
            "the sandbox base %s lies inside the swept tree %s" % (sandbox_base, root)
        )
    if not os.path.isdir(sandbox_base):
        os.makedirs(sandbox_base)
    policy = _policy(root)
    skip = policy["effect_proof_skip"]
    kept = _kept_dirs(policy["effect_proof_kept_dirs"])
    # stdout, not a logger: shown under -s and on a failure, beside the skips.
    sys.stdout.write(
        "effect proof runs each target under a fresh empty HOME; kept: %s\n"
        % ", ".join(
            "%s (%s)" % (name, source) for name, (_, source) in sorted(kept.items())
        )
    )
    ran, failures, skipped = [], [], []
    for target in _local_targets(root):
        if target in skip:
            skipped.append((target, skip[target]))
            continue
        home = tempfile.mkdtemp(prefix="home-", dir=sandbox_base)
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("HOME", home)
            for name, (value, _source) in kept.items():
                if value is None:
                    mp.delenv(name, raising=False)
                else:
                    mp.setenv(name, value)
            _child_carries(home, kept)
            before = _home_snapshot(home)
            res = rmt.run_target(
                target, cwd=root, timeout=_TARGET_TIMEOUT, extra=["PY=" + py]
            )
            home_changed = _home_changes(before, _home_snapshot(home))
        ran.append(target)
        if not res["ok"] or home_changed:
            failures.append(
                {
                    "target": target,
                    "returncode": res["returncode"],
                    "refused": res["refused"],
                    "changed": res["changed"],
                    "home_changed": home_changed,
                    "output": str(res["output"])[-1500:],
                }
            )
    return ran, failures, skipped


def _in_git(root):
    probe = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    return probe.returncode == 0 and probe.stdout.strip() == "true"


@pytest.fixture(scope="module")
def clone(tmp_path_factory):
    if shutil.which("git") is None or not _in_git(_ROOT):
        pytest.skip("cannot prove a read-only run without git")
    work = tmp_path_factory.mktemp("effects")
    return hermetic_git.clone_including_worktree(_ROOT, work / "repo", work)


def test_every_local_target_leaves_the_tree_as_it_found_it(clone, tmp_path_factory):
    ran, failures, skipped = _sweep(
        clone, sys.executable, tmp_path_factory.mktemp("homes")
    )
    # stdout, not a logger: pytest shows it under -s and on a failure, which is
    # where a reader needs to see what the proof did not cover.
    for target, reason in skipped:
        sys.stdout.write("effect proof skipped `make %s`: %s\n" % (target, reason))
    sys.stdout.write("effect proof ran %d target(s): %s\n" % (len(ran), ", ".join(ran)))
    assert ran, "the sweep ran no target -- a pass over nothing proves nothing"
    assert failures == [], json.dumps(failures, indent=2)


def test_every_skip_names_a_local_target():
    """A skip outlives its reason silently: the target is renamed, relabelled or
    removed and the entry keeps a [local] claim out of the proof for nothing."""
    skip = _policy(_ROOT)["effect_proof_skip"]
    stale = sorted(set(skip) - set(_local_targets(_ROOT)))
    assert stale == [], "effect_proof_skip names no [local] target: %s" % stale


def _git(root, *argv):
    r = subprocess.run(
        ("git",) + argv,
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    assert r.returncode == 0, r.stdout


def _fixture_repo(tmp_path, makefile, kept=None):
    """A git repo at tmp_path/repo with keel's config (no skips, *kept* as
    effect_proof_kept_dirs when given), a tracked file and *makefile*."""
    repo = tmp_path / "repo"
    (repo / "config").mkdir(parents=True)
    data = json.loads((_ROOT / "config" / "project.json").read_text("utf-8"))
    data["make_targets"]["effect_proof_skip"] = {}
    if kept is not None:
        data["make_targets"]["effect_proof_kept_dirs"] = kept
    (repo / "config" / "project.json").write_text(json.dumps(data), "utf-8")
    (repo / "tracked.txt").write_text("before\n", encoding="utf-8")
    (repo / "Makefile").write_text(makefile, encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "fixture")
    return repo


def test_a_poisoned_local_target_fails_the_sweep(tmp_path, monkeypatch):
    """Fault injection: the sweep above is only evidence if it can go red --
    on the tree, and on the HOME a target runs under, where a link is recorded
    rather than followed (this one leads nowhere). The caller's own HOME is
    never the one written."""
    repo = _fixture_repo(
        tmp_path,
        "clean-check: ## [local] Reads only\n\t@cat tracked.txt >/dev/null\n"
        "poison: ## [local] Claims local, writes a file\n\t@echo x > poisoned.txt\n"
        "edits: ## [local] Claims local, edits a tracked file\n"
        "\t@echo after > tracked.txt\n"
        "home-writer: ## [local] Claims local, writes its HOME\n"
        '\t@echo x > "$$HOME/written.txt"\n'
        "link-planter: ## [local] Claims local, links in its HOME to nothing\n"
        '\t@ln -s does-not-exist "$$HOME/dangling"\n',
    )
    caller_home = tmp_path / "caller-home"
    (caller_home / ".config").mkdir(parents=True)
    (caller_home / "marker").write_text("mine\n", encoding="utf-8")
    (caller_home / ".config" / "marker").write_text("mine\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(caller_home))
    caller_before = _home_snapshot(str(caller_home))
    ran, failures, _ = _sweep(repo, sys.executable, tmp_path / "homes-base")
    assert ran == ["clean-check", "edits", "home-writer", "link-planter", "poison"]
    assert [(f["target"], f["changed"], f["home_changed"]) for f in failures] == [
        ("edits", ["tracked.txt"], []),
        ("home-writer", [], ["written.txt"]),
        ("link-planter", [], ["dangling"]),
        ("poison", ["poisoned.txt"], []),
    ]
    assert _home_snapshot(str(caller_home)) == caller_before


def test_a_fifo_or_socket_left_in_home_fails_the_target_and_never_hangs(tmp_path):
    """The snapshot reads only regular files: opening a FIFO blocks until a
    writer comes and a socket cannot be opened at all, so either would stall or
    crash the sweep instead of failing the target that left it. The sweep runs
    in a thread so a regression is a red test, not a hung suite."""
    repo = _fixture_repo(
        tmp_path,
        "fifo-maker: ## [local] Claims local, leaves a FIFO in its HOME\n"
        '\t@mkfifo "$$HOME/pipe"\n'
        "socket-maker: ## [local] Claims local, leaves a socket in its HOME\n"
        '\t@cd "$$HOME" && $(PY) -c "import socket; '
        "socket.socket(socket.AF_UNIX).bind('sock')\"\n",
    )
    base = tmp_path / "homes-base"
    result = {}

    def run():
        try:
            result["out"] = _sweep(repo, sys.executable, base)
        except (AssertionError, OSError) as exc:  # asserted on below
            result["err"] = exc

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(120)
    hung = worker.is_alive()
    if hung:
        # Free the blocked reader so the thread ends with the test.
        for fifo in base.glob("home-*/pipe"):
            os.close(os.open(str(fifo), os.O_WRONLY | os.O_NONBLOCK))
        worker.join(30)
    assert not hung, "the HOME snapshot blocked on a FIFO a target left"
    assert "err" not in result, repr(result.get("err"))
    ran, failures, _ = result["out"]
    assert ran == ["fifo-maker", "socket-maker"]
    assert [(f["target"], f["returncode"], f["home_changed"]) for f in failures] == [
        ("fifo-maker", 0, ["pipe"]),
        ("socket-maker", 0, ["sock"]),
    ]


def test_each_target_runs_under_a_fresh_empty_home(tmp_path):
    """A HOME shared between targets would let one target's leftovers decide
    the next one's verdict, so each is red unless its HOME starts empty."""
    log = tmp_path / "homes.log"
    recipe = (
        '\t@test -z "$$(ls -A "$$HOME")"\n'
        '\t@echo "$$HOME" >> %s\n'
        '\t@echo x > "$$HOME/left.txt"\n' % log
    )
    repo = _fixture_repo(
        tmp_path,
        "home-a: ## [local] Needs an empty HOME\n"
        + recipe
        + "home-b: ## [local] Needs an empty HOME\n"
        + recipe,
    )
    base = tmp_path / "homes-base"
    base.mkdir()
    ran, failures, _ = _sweep(repo, sys.executable, base)
    assert ran == ["home-a", "home-b"]
    assert [(f["target"], f["returncode"], f["home_changed"]) for f in failures] == [
        ("home-a", 0, ["left.txt"]),
        ("home-b", 0, ["left.txt"]),
    ]
    homes = log.read_text("utf-8").split()
    assert len(set(homes)) == 2, homes
    for home in homes:
        assert os.path.dirname(home) == os.path.realpath(str(base)), home


@pytest.mark.parametrize("source", ["derived", "explicit", "unset"])
def test_the_sweep_keeps_the_callers_xdg_dirs(tmp_path, monkeypatch, source):
    """A kept dir is the caller's own value, else its path under the caller's
    HOME, else unset; a target writing under it is not failed for that."""
    log = tmp_path / "xdg.log"
    repo = _fixture_repo(
        tmp_path,
        "cache-user: ## [local] Writes a tool cache under a kept dir\n"
        '\t@echo "[$${KEEL_TEST_KEPT_HOME-unset}]" > %s\n'
        '\t@if [ -n "$${KEEL_TEST_KEPT_HOME-}" ]; then mkdir -p "$$KEEL_TEST_KEPT_HOME" '
        '&& echo x > "$$KEEL_TEST_KEPT_HOME/cache.txt"; fi\n' % log,
        kept={"KEEL_TEST_KEPT_HOME": "kept/dir"},
    )
    caller_home = tmp_path / "caller-home"
    caller_home.mkdir()
    monkeypatch.setenv("HOME", str(caller_home))
    monkeypatch.delenv("KEEL_TEST_KEPT_HOME", raising=False)
    expected = {
        "derived": str(caller_home / "kept" / "dir"),
        "explicit": str(tmp_path / "explicit"),
        "unset": None,
    }[source]
    if source == "explicit":
        monkeypatch.setenv("KEEL_TEST_KEPT_HOME", expected)
    if source == "unset":
        monkeypatch.delenv("HOME")
    real = child_env.load_policy()
    monkeypatch.setattr(
        child_env,
        "load_policy",
        lambda root=None: real._replace(
            names=tuple(real.names) + ("KEEL_TEST_KEPT_HOME",)
        ),
    )
    ran, failures, _ = _sweep(repo, sys.executable, tmp_path / "homes-base")
    assert ran == ["cache-user"]
    assert failures == [], json.dumps(failures, indent=2)
    assert log.read_text("utf-8") == "[%s]\n" % (
        "unset" if expected is None else expected
    )
    if expected is not None:
        assert (Path(expected) / "cache.txt").read_text("utf-8") == "x\n"


@pytest.mark.parametrize("dropped", ["HOME", "kept"])
def test_the_sweep_refuses_a_sandbox_the_child_never_sees(
    tmp_path, monkeypatch, dropped
):
    """The cross-check fails closed: an allowlist that does not carry HOME, or
    a kept variable, to make would run every target under the caller's own
    dirs and prove nothing about them."""
    log = tmp_path / "ran.log"
    repo = _fixture_repo(
        tmp_path,
        "any: ## [local] Records that it ran\n\t@echo ran > %s\n" % log,
        kept={"KEEL_TEST_KEPT_HOME": "kept/dir"},
    )
    monkeypatch.setenv("HOME", str(tmp_path / "caller-home"))
    real = child_env.load_policy()
    names = tuple(n for n in real.names if n != "HOME")
    if dropped == "kept":
        names = tuple(real.names)
    monkeypatch.setattr(
        child_env, "load_policy", lambda root=None: real._replace(names=names)
    )
    match = "lacks HOME" if dropped == "HOME" else "keeps KEEL_TEST_KEPT_HOME"
    with pytest.raises(AssertionError, match=match):
        _sweep(repo, sys.executable, tmp_path / "homes-base")
    assert not log.exists(), "a target ran before the sandbox was checked"
