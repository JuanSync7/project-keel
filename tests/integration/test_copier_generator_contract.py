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

pytestmark = pytest.mark.integration


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
    src = Path(argv[argv.index("copy") + 1])

    assert src.is_absolute(), (
        "`make new` passes copier the relative template path %r; copier records it "
        "verbatim as _src_path, so `copier update` in the generated project resolves "
        "it against the project and fails" % str(src))
    assert src.resolve() == _ROOT.resolve()
    assert (src / "copier.yml").is_file(), (
        "%s is not a copier template root (no copier.yml)" % src)


@pytest.mark.skipif(shutil.which("make") is None or shutil.which("git") is None,
                    reason="needs make and git")
def test_make_new_refuses_a_dirty_template(tmp_path):
    """The other half of the resolvable-origin contract. From a dirty template copier
    commits the working changes into its own throwaway clone and records THAT sha as
    `_commit` — a commit no clone of keel has ever seen, so the generated project dies
    on the same `pathspec ... did not match` as the relative-path bug. `make new` must
    refuse, with an `ALLOW_DIRTY=1` escape hatch for template authors iterating.

    Drives the real recipe text against real git repos rather than pinning a string."""
    def run_guard(stdout, cwd):
        return subprocess.run(["sh", "-c", _recipe_line(stdout, "git status --porcelain")],
                              cwd=str(cwd), capture_output=True, text=True)

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=str(repo), capture_output=True, text=True)

    clean = run_guard(_make_n_new(), repo)
    assert clean.returncode == 0, "the guard rejects a CLEAN tree:\n" + clean.stdout

    (repo / "wip.txt").write_text("uncommitted work\n")
    dirty = run_guard(_make_n_new(), repo)
    assert dirty.returncode == 2, (
        "`make new` does not refuse a dirty template, so it can hand the user a project "
        "whose `_commit` exists only in copier's throwaway clone:\n" + dirty.stdout)
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
        "tests/integration/test_copier_*.py silently skips:\n" + "\n".join(installs))


def test_ci_declares_the_template_extra_required_for_the_suite():
    """Installing the extra is not enough: a broken install would degrade back to a
    silent skip. The suite step must declare KEEL_REQUIRE_TEMPLATE so a missing
    copier is a hard collection error in CI (a bare local clone leaves it unset and
    still skips gracefully)."""
    lines = _CI.read_text().splitlines()
    starts = [i for i, ln in enumerate(lines) if ln.strip() == "- run: make test"]
    assert len(starts) == 1, "expected exactly one `- run: make test` step in CI"
    step = "\n".join(lines[starts[0]:starts[0] + 4])
    assert "KEEL_REQUIRE_TEMPLATE" in step, (
        "the CI step that runs the suite does not declare KEEL_REQUIRE_TEMPLATE, so "
        "a missing `template` extra would skip the copier tests instead of failing:\n"
        + step)


def test_copier_test_modules_hard_fail_when_the_extra_is_required():
    """Both halves of the guard live in the test modules themselves: whatever
    importorskips `copier` must also honour KEEL_REQUIRE_TEMPLATE, or CI's flag
    reaches a module that ignores it and the skip comes back."""
    guarded = []
    for path in sorted((_ROOT / "tests").rglob("test_*.py")):
        text = path.read_text()
        if 'importorskip("copier")' not in text:
            continue
        guarded.append(path.name)
        assert "KEEL_REQUIRE_TEMPLATE" in text, (
            "%s importorskips copier but ignores KEEL_REQUIRE_TEMPLATE, so it would "
            "still skip silently in CI" % path.name)
    assert guarded, "no test module importorskips copier — did the guard move?"


# copier's `multiselect:` question type landed in 9.1.0. `_min_copier_version` exists
# to convert "your copier is too old" into copier's own clear message; declaring a
# floor BELOW the oldest release that can actually render this template turns the
# gate into a lie — 9.0.1 passes it and then dies with the exact mystery error the
# gate advertises preventing (`ValueError: Could not convert [] to string`).
_FEATURE_FLOORS = [("9.1.0", "multiselect:", "multiselect questions")]


def test_declared_copier_floor_covers_every_feature_the_template_uses():
    """`_min_copier_version` must be >= the newest copier feature copier.yml relies
    on. A floor that admits a copier which then crashes is worse than no floor: the
    user is told the version was checked."""
    text = (_ROOT / "copier.yml").read_text()
    declared = None
    for line in text.splitlines():
        if line.startswith("_min_copier_version:"):
            declared = line.split(":", 1)[1].strip().strip('"\'')
    assert declared, "copier.yml declares no _min_copier_version"
    as_tuple = tuple(int(p) for p in declared.split("."))

    for floor, marker, why in _FEATURE_FLOORS:
        if marker not in text:
            continue
        need = tuple(int(p) for p in floor.split("."))
        assert as_tuple >= need, (
            "copier.yml uses %s (needs copier >= %s) but declares "
            "_min_copier_version: %r — that version passes the gate and then fails "
            "to render" % (why, floor, declared))
