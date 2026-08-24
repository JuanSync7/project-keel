"""
title: Integration — the generator's own entry points stay wired up
kind: tests
layer: n/a
summary: Pins on the ways keel's generator rots silently, read off the real `make -n new` recipe and the real CI workflow. (1) `make new` must hand copier a RESOLVABLE template path — copier records the CLI argument verbatim as `_src_path`, so a literal `.` resolves to the generated project itself and `copier update` dies there on an unhandled traceback. (2) It must refuse a dirty template, whose `_commit` would exist only in copier's throwaway clone. (3) CI must install the optional `template` extra AND declare it required, or every copier test importorskips and the template's own generation/update gates never run. Imports nothing optional on purpose — this pin must never itself skip, or the fix it guards is circular.
"""

import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_CI = _ROOT / ".github" / "workflows" / "ci.yml"

# Self-neutralising downstream. `_exclude` prunes these modules at GENERATION, but
# copier's `_exclude` can never retire a file on `copier update` — it renders the old
# template copy with the UNION of the old and new excludes precisely so nothing is
# deleted (copier/_main.py). So a project generated BEFORE the prune landed still ships
# them, and `copier update` hands it the newer ci.yml that installs the `template`
# extra and declares it required — turning its CI red via the very update meant
# to fix CI (measured: 6 of 8 failed). A meta-test only means anything where a
# `copier.yml` exists, so say so here rather than relying on pruning alone.
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (_ROOT / "copier.yml").is_file(),
        reason="not a copier template — this is a generated project",
    ),
]


def _make_n_new(**overrides):
    """The `new` recipe as make would run it — expanded, but not executed."""
    argv = ["make", "-n", "new", "DEST=probe-dest-never-created"]
    argv += ["%s=%s" % kv for kv in overrides.items()]
    r = subprocess.run(argv, cwd=str(_ROOT), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def _recipe_line(stdout, needle):
    """One expanded recipe line (backslash continuations rejoined) containing needle."""
    lines = stdout.splitlines()
    hits = [i for i, ln in enumerate(lines) if needle in ln]
    assert len(hits) == 1, "expected exactly one %r line in:\n%s" % (needle, stdout)
    i = hits[0]
    block = [lines[i]]
    while block[-1].rstrip().endswith("\\"):
        i += 1
        block.append(lines[i])
    return "\n".join(block)


@pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
def test_make_new_hands_copier_a_resolvable_template_path():
    """`make new` is keel's advertised generator entry point, and copier stores the
    source argument verbatim in the generated project's `.copier-answers.yml`. With
    a relative argument the recorded origin is re-resolved against the *project's*
    cwd on update: copier clones the project as if it were the template and git dies
    with `pathspec '<keel sha>' did not match any file(s) known to git` — a raw
    plumbum traceback, no diagnostic. So the argument must be absolute and must
    actually be this template (`copier.yml` present)."""
    argv = shlex.split(_recipe_line(_make_n_new(), "copier copy"))
    # `copier copy [options] SRC DEST` — take SRC positionally from the end rather
    # than as "the word after `copy`", which broke the moment --vcs-ref was added.
    assert argv[-1] == "probe-dest-never-created", (
        "DEST is not the last argument of the copy recipe: %r" % argv
    )
    src = Path(argv[-2])

    assert src.is_absolute(), (
        "`make new` passes copier the relative template path %r; copier records it "
        "verbatim as _src_path, so `copier update` in the generated project resolves "
        "it against the project and fails" % str(src)
    )
    assert src.resolve() == _ROOT.resolve()
    assert (src / "copier.yml").is_file(), (
        "%s is not a copier template root (no copier.yml)" % src
    )


@pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
def test_make_new_pins_the_template_revision_it_generates_from():
    """With no `--vcs-ref`, copier does not use HEAD — `Template.ref` is None and it
    resolves `self.ref or get_latest_tag(...)` (copier/_template.py), i.e. the newest
    TAG. Harmless only while keel has no tags; the moment `v0.1.0` is cut (the
    outstanding pass-1 item) `make new` starts generating from the tag, so a
    maintainer smoke-testing a template change gets a project that silently does not
    contain it. Every automated copier test already pins `vcs_ref="HEAD"`; the shipped
    recipe must be explicit too, and overridable for a release smoke-test."""
    line = _recipe_line(_make_n_new(), "copier copy")
    argv = shlex.split(line)

    assert "--vcs-ref" in argv, (
        "`make new` passes copier no --vcs-ref, so once keel is tagged it generates "
        "from the newest tag instead of the working checkout:\n" + line
    )
    assert argv[argv.index("--vcs-ref") + 1] == "HEAD", (
        "the default template revision must be HEAD (the checkout the user is "
        "looking at), not %r" % argv[argv.index("--vcs-ref") + 1]
    )

    # ...and overridable, so cutting a release can smoke-test the tag itself.
    pinned = shlex.split(_recipe_line(_make_n_new(VCS_REF="v9.9.9"), "copier copy"))
    assert pinned[pinned.index("--vcs-ref") + 1] == "v9.9.9", (
        "VCS_REF= does not override the default revision"
    )


@pytest.mark.skipif(
    shutil.which("make") is None or shutil.which("git") is None,
    reason="needs make and git",
)
def test_make_new_refuses_a_template_that_is_not_a_git_checkout(tmp_path):
    """`git status --porcelain 2>/dev/null` prints nothing AND discards rc=128 outside
    a repository, so the dirty-tree guard read a ZIP download or an
    `rsync --exclude=.git` copy as *clean* and generated happily. copier then records
    no `_commit` at all and the project can never `copier update` — the exact harm the
    guard exists to prevent, waved through by the guard itself. Being repo-less is not
    a dirtiness question, so ALLOW_DIRTY must NOT override it."""
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    guard = _recipe_line(_make_n_new(), "rev-parse")

    r = subprocess.run(
        ["sh", "-c", guard], cwd=str(plain), capture_output=True, text=True
    )
    assert r.returncode == 2, (
        "`make new` does not refuse a non-git template, so it hands the user a "
        "project with no recorded `_commit` and no way to update:\n"
        + r.stdout
        + r.stderr
    )
    assert "git" in r.stdout.lower(), "the refusal must say what is wrong"

    forced = subprocess.run(
        ["sh", "-c", _recipe_line(_make_n_new(ALLOW_DIRTY="1"), "rev-parse")],
        cwd=str(plain),
        capture_output=True,
        text=True,
    )
    assert forced.returncode == 2, (
        "ALLOW_DIRTY=1 overrode the not-a-git-checkout refusal; it is an escape hatch "
        "for uncommitted work, and no amount of it can produce a `_commit`"
    )


@pytest.mark.skipif(
    shutil.which("make") is None or shutil.which("git") is None,
    reason="needs make and git",
)
def test_make_new_refuses_a_dirty_template(tmp_path):
    """The other half of the resolvable-origin contract. From a dirty template copier
    commits the working changes into its own throwaway clone and records THAT sha as
    `_commit` — a commit no clone of keel has ever seen, so the generated project dies
    on the same `pathspec ... did not match` as the relative-path bug. `make new` must
    refuse, with an `ALLOW_DIRTY=1` escape hatch for template authors iterating.

    Drives the real recipe text against real git repos rather than pinning a string."""

    def run_guard(stdout, cwd):
        return subprocess.run(
            ["sh", "-c", _recipe_line(stdout, "git status --porcelain")],
            cwd=str(cwd),
            capture_output=True,
            text=True,
        )

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=str(repo), capture_output=True, text=True)

    clean = run_guard(_make_n_new(), repo)
    assert clean.returncode == 0, "the guard rejects a CLEAN tree:\n" + clean.stdout

    (repo / "wip.txt").write_text("uncommitted work\n")
    dirty = run_guard(_make_n_new(), repo)
    assert dirty.returncode == 2, (
        "`make new` does not refuse a dirty template, so it can hand the user a project "
        "whose `_commit` exists only in copier's throwaway clone:\n" + dirty.stdout
    )
    assert "ALLOW_DIRTY" in dirty.stdout, "the refusal must name its escape hatch"

    allowed = run_guard(_make_n_new(ALLOW_DIRTY="1"), repo)
    assert allowed.returncode == 0, "ALLOW_DIRTY=1 must override the refusal"


def test_ci_installs_the_optional_template_extra():
    """`template = ["copier>=9"]` is an optional extra. Until CI installs it, every
    copier test skips and the generation/update gates are decorative."""
    installs = [ln for ln in _CI.read_text().splitlines() if "pip install -e" in ln]
    assert installs, "CI no longer does an editable install of the project"
    assert any("template" in ln for ln in installs), (
        "no CI step installs the `template` extra, so copier is absent and every "
        "tests/integration/test_copier_*.py silently skips:\n" + "\n".join(installs)
    )


def test_ci_declares_the_template_surface_required_for_the_suite():
    """Installing the extra is not enough: a broken install would degrade back to a
    silent skip. The suite step must declare the `template` surface required so a
    missing copier is a hard collection error in CI (a bare local clone leaves the
    declaration unset and still skips gracefully).

    Named surface, not just "the variable is present": declaring `dev,transport` and
    quietly dropping `template` would satisfy a mere-presence check while putting the
    generation and update gates straight back to sleep."""
    lines = _CI.read_text().splitlines()
    starts = [i for i, ln in enumerate(lines) if ln.strip() == "- run: make test"]
    assert len(starts) == 1, "expected exactly one `- run: make test` step in CI"
    step = "\n".join(lines[starts[0] : starts[0] + 4])
    assert "KEEL_REQUIRED_EXTRAS" in step, (
        "the CI step that runs the suite declares no required surfaces, so a missing "
        "`template` extra would skip the copier tests instead of failing:\n" + step
    )
    assert "template" in step.split("KEEL_REQUIRED_EXTRAS", 1)[1], (
        "the suite step declares required surfaces but not `template`, so the copier "
        "generation/update gates can silently skip in CI again:\n" + step
    )


def test_copier_test_modules_hard_fail_when_the_surface_is_required():
    """Both halves of the guard live in the test modules themselves: whatever guards
    the `copier` import must route through `optional_deps`, or CI's declaration
    reaches a module that ignores it and the skip comes back.

    (The general "no module may silently skip a dependency CI installs" scan is in
    test_gate_scope.py, which ships downstream; this pins the two modules whose skip
    would specifically decommission the template's own gates.)"""
    guarded = []
    for path in sorted((_ROOT / "tests").rglob("test_*.py")):
        # Skip THIS file. It contains the searched-for literal as its own filter
        # string, so it always matched itself — which made `guarded` permanently
        # non-empty and the backstop below unfireable. Deleting every real copier
        # test module left this test green (measured: `1 passed`).
        if path.resolve() == Path(__file__).resolve():
            continue
        text = path.read_text()
        if '"copier"' not in text:
            continue
        guarded.append(path.name)
        assert 'optional_deps.importorskip("copier", extra="template")' in text, (
            "%s guards the copier import without routing through optional_deps, so "
            "CI's required-surface declaration cannot reach it and it would still "
            "skip silently" % path.name
        )
    # Named explicitly, not just "something was found": a rename or a rewrite that
    # drops the guard must be a failure, not a quietly smaller set.
    missing = {"test_copier_generation.py", "test_copier_update.py"} - set(guarded)
    assert not missing, (
        "these copier test modules no longer guard copier through optional_deps, so "
        "they can silently skip in CI again: %s (found: %s)"
        % (sorted(missing), guarded)
    )


# copier's `multiselect:` question type landed in 9.1.0. `_min_copier_version` exists
# to convert "your copier is too old" into copier's own clear message; declaring a
# floor BELOW the oldest release that can actually render this template turns the
# gate into a lie — 9.0.1 passes it and then dies with the exact mystery error the
# gate advertises preventing (`ValueError: Could not convert [] to string`).
_FEATURE_FLOORS = [
    ("9.1.0", "multiselect:", "multiselect questions"),
    # The `command:`/`when:` migration form landed in copier 9.3.0 ("add simpler
    # migrations configuration syntax", #1510). Measured in 9.2.0's source rather
    # than assumed: `migration_tasks` does `parse(migration["version"])` with no
    # guard, so an entry that carries `command:` instead of `version:` is a raw
    # KeyError mid-update — the unhandled-traceback shape this floor converts into
    # copier's own clear message. 9.3.0 branches on the format instead.
    ("9.3.0", "_stage ==", "new-format _migrations (command:/when:)"),
]


def test_declared_copier_floor_covers_every_feature_the_template_uses():
    """`_min_copier_version` must be >= the newest copier feature copier.yml relies
    on. A floor that admits a copier which then crashes is worse than no floor: the
    user is told the version was checked."""
    text = (_ROOT / "copier.yml").read_text()
    declared = None
    for line in text.splitlines():
        if line.startswith("_min_copier_version:"):
            declared = line.split(":", 1)[1].strip().strip("\"'")
    assert declared, "copier.yml declares no _min_copier_version"
    as_tuple = tuple(int(p) for p in declared.split("."))

    for floor, marker, why in _FEATURE_FLOORS:
        if marker not in text:
            continue
        need = tuple(int(p) for p in floor.split("."))
        assert as_tuple >= need, (
            "copier.yml uses %s (needs copier >= %s) but declares "
            "_min_copier_version: %r — that version passes the gate and then fails "
            "to render" % (why, floor, declared)
        )
