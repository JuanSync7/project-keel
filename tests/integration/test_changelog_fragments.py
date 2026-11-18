"""
title: Integration — independent changelog entries and lossless release rotation
kind: tests
layer: n/a
summary: Changelog sources preserve hand-written history, merge independently, rotate once and never leak into generated projects.
"""

import json
import re
import shutil
from pathlib import Path

import pytest
from test_copier_generation import clean_template as clean_template
from test_copier_generation import generate as generate
from test_copier_generation import renders as renders
from test_reference_fragments import _assemble, _tree
from test_work_trailers import _run as toy_git

import optional_deps

optional_deps.importorskip("copier", extra="template")
pytest_plugins = ("test_work_trailers",)
pytestmark = pytest.mark.integration
_ROOT = Path(__file__).resolve().parents[2]
# CHANGELOG.md as written by hand before CMP-11.S3, cut after its 0.3.0
# section, and the entry files its first assembly was converted into.
_MIGRATION = _ROOT / "tests/fixtures/changelog-migration"


def _entry(folder, order, identity, text):
    path = folder / f"{order:06d}-{identity:032x}.part"
    path.write_text(text)
    return path


def _changelog(root):
    manifest_path = root / "config/project.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["changelog"] = json.loads((_ROOT / "config/project.json").read_text())[
        "changelog"
    ]
    manifest["reference_fragments"] = {
        "root": "docs/reference",
        "folder_suffix": ".d",
        "suffix": ".part",
        "sets": [],
    }
    manifest["changelog_fragments"] = {
        "folder": "changelog.d",
        "categories": ["added", "changed", "fixed", "security"],
        "unsectioned": "general",
    }
    manifest_path.write_text(json.dumps(manifest))
    folder = root / "changelog.d"
    for name in ["general", *manifest["changelog_fragments"]["categories"]]:
        (folder / name).mkdir(parents=True)
    output = root / "CHANGELOG.md"
    output.write_text(
        "# Changelog\n\n- preamble stays.\n\n## [Unreleased]\n\n"
        "## [0.1.0] — 2020-01-01\n\n- dated stays.\n"
    )
    return folder, output


@pytest.mark.parametrize("side", ["ours", "theirs"])
def test_independent_entries_render_without_leaking_template_history(toy, side):
    """The initial hand-written Unreleased section survives assembly line for line."""
    assert (_ROOT / "changelog.d").is_dir()
    # The migration is judged on a frozen copy of both sides, so a later entry
    # or a release that empties changelog.d/ cannot turn this test red.
    original = (_MIGRATION / "CHANGELOG-before.txt").read_bytes()
    root, env, commit = toy
    shutil.copytree(_MIGRATION / "changelog.d", root / "changelog.d")
    manifest_path = root / "config/project.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["changelog"] = json.loads((_ROOT / "config/project.json").read_text())[
        "changelog"
    ]
    manifest["reference_fragments"] = {
        "root": "docs/reference",
        "folder_suffix": ".d",
        "suffix": ".part",
        "sets": [],
    }
    manifest["changelog_fragments"] = {
        "folder": "changelog.d",
        "categories": ["added", "changed", "fixed", "security"],
        "unsectioned": "general",
    }
    manifest_path.write_text(json.dumps(manifest))
    output = root / "CHANGELOG.md"
    output.write_bytes(original)
    assert _assemble(root).returncode == 0
    assert output.read_bytes().splitlines(keepends=True) == original.splitlines(
        keepends=True
    )
    toy_git(root, env, "add", "-A")
    baseline = commit("changelog baseline")
    folder = root / "changelog.d/added"
    order = 1 + max(int(p.name[:6]) for p in folder.glob("*.part"))
    for identity in (1, 2):
        toy_git(root, env, "checkout", "-q", "-b", f"lane-{identity}", baseline)
        _entry(folder, order, identity, f"- lane {identity}\n\n")
        assert _assemble(root).returncode == 0
        toy_git(root, env, "add", "-A")
        commit(f"lane {identity}")
    toy_git(root, env, "merge", "--no-edit", "-X", side, "lane-1")
    chosen = output.read_text()
    assert ("- lane 1" in chosen) != ("- lane 2" in chosen)
    assert _assemble(root).returncode == 0
    merged = output.read_bytes()
    assert b"- lane 1\n" in merged and b"- lane 2\n" in merged
    historical = original.split(b"## [0.3.0]", 1)[1]
    assert merged.split(b"## [0.3.0]", 1)[1] == historical
    assert _assemble(root, "--check").returncode == 0


def test_rotation_converges_and_next_entry_is_only_unreleased(toy):
    """Release publishes source text, deletes entries and leaves a fixed point."""
    root, env, _commit = toy
    folder, output = _changelog(root)
    _entry(folder / "added", 1, 1, "- released addition\n\n")
    _entry(folder / "general", 1, 2, "- released general\n\n")
    (folder / "added/README.md").write_text("ignored\n")
    (folder / "added/AGENT.md").write_text("ignored\n")
    (folder / "added/CLAUDE.md").symlink_to("AGENT.md")
    old = output.read_bytes().split(b"## [0.1.0]", 1)[1]
    release = _assemble(root, "--release", "0.2.0", "--date", "2030-02-03")
    assert release.returncode == 0, release.stderr
    assert not list(folder.rglob("*.part"))
    assert toy_git(root, env, "tag", "--list") == ""
    assert output.read_bytes().split(b"## [0.1.0]", 1)[1] == old
    assert "## [Unreleased]\n\n## [0.2.0] — 2030-02-03\n" in output.read_text()
    before = _tree(root)
    assert _assemble(root, "--check").returncode == 0
    assert _assemble(root).returncode == 0
    assert _assemble(root).returncode == 0
    assert _tree(root) == before
    _entry(folder / "fixed", 1, 3, "- next release only\n\n")
    stale = _assemble(root, "--check")
    assert stale.returncode != 0 and "CHANGELOG.md" in stale.stderr
    assert _assemble(root).returncode == 0
    unreleased, dated = output.read_text().split("## [0.2.0]", 1)
    assert "next release only" in unreleased and "next release only" not in dated
    assert "released addition" not in unreleased
    assert _assemble(root, "--check").returncode == 0


@pytest.mark.parametrize(
    "args", [(), ("--check",), ("--release", "0.3.0", "--date", "2030-03-04")]
)
def test_interrupted_release_refuses_restored_entries_without_writing(toy, args):
    """Every mode names all already published sources and preserves the tree."""
    root, _env, _commit = toy
    folder, _output = _changelog(root)
    consumed = [
        _entry(folder / "general", 1, 1, "- released general [link](target)\n\n"),
        _entry(folder / "fixed", 1, 2, "- released fix\n  with details\n\n"),
        _entry(folder / "added", 1, 3, "- fully consumed\n"),
    ]
    restored = {path: path.read_bytes() for path in consumed[:2]}
    released = _assemble(root, "--release", "0.2.0", "--date", "2030-02-03")
    assert released.returncode == 0, released.stderr
    assert all(not path.exists() for path in consumed)
    for path, content in restored.items():
        path.write_bytes(content)
    _entry(folder / "added", 2, 4, "- unpublished addition\n")
    before = _tree(root)
    refused = _assemble(root, *args)
    assert refused.returncode == 2, refused.stderr
    assert "0.2.0" in refused.stderr
    assert "already released" in refused.stderr and "delete" in refused.stderr
    for path in restored:
        assert str(path.relative_to(root)) in refused.stderr
    assert _tree(root) == before


@pytest.mark.parametrize(
    "history",
    [
        "## [0.2.0] — 2030-02-03\n\n- prefix extended\n- enclosing - inside tail\n",
        "",
        "## [0.2.0] — 2030-02-03\n\n- newest\n\n"
        "## [0.1.0] — 2020-01-01\n\n- prefix\n- inside\n",
    ],
    ids=["partial-lines", "no-dated-section", "older-section"],
)
def test_only_whole_line_runs_in_newest_dated_section_refuse(toy, history):
    """Partial lines, absent history and older releases allow ordinary assembly."""
    root, _env, _commit = toy
    folder, output = _changelog(root)
    output.write_text("# Changelog\n\n## [Unreleased]\n\n" + history)
    _entry(folder / "fixed", 1, 1, "- prefix\n\n")
    _entry(folder / "fixed", 2, 2, "- inside\n")
    assembled = _assemble(root)
    assert assembled.returncode == 0, assembled.stderr
    assert output.read_text().endswith(history)
    assert _assemble(root, "--check").returncode == 0


@pytest.mark.parametrize(
    "args, message",
    [
        (("--release", "0.1.0", "--date", "2030-02-03"), "already"),
        (("--release", "v0.2.0", "--date", "2030-02-03"), "version"),
        (("--release", "01.2.0", "--date", "2030-02-03"), "version"),
        (("--release", "0.2.0", "--date", "2030-02-30"), "date"),
        (("--release", "0.2.0", "--date", "2030-2-03"), "date"),
        (("--release", "0.2.0"), "date"),
        (("--date", "2030-02-03"), "release"),
        (("--release", "0.2.0", "--date", "2030-02-03", "--check"), "check"),
    ],
)
def test_release_refuses_before_any_write(toy, args, message):
    root, _env, _commit = toy
    folder, _output = _changelog(root)
    _entry(folder / "fixed", 1, 1, "- fix\n\n")
    before = _tree(root)
    refused = _assemble(root, *args)
    assert refused.returncode != 0 and message in refused.stderr, refused.stderr
    assert _tree(root) == before


def test_empty_release_and_missing_folder_refuse(toy):
    root, _env, _commit = toy
    folder, _output = _changelog(root)
    before = _tree(root)
    refused = _assemble(root, "--release", "0.2.0", "--date", "2030-02-03")
    assert refused.returncode != 0 and "no entries" in refused.stderr
    assert _tree(root) == before
    shutil.rmtree(folder)
    refused = _assemble(root, "--check")
    assert refused.returncode != 0 and "changelog.d" in refused.stderr


@pytest.mark.parametrize(
    "name, content",
    [
        ("wrong.part", "- valid bullet\n"),
        ("000001-" + "a" * 32 + ".part", "no bullet\n"),
        ("000001-" + "a" * 32 + ".part", "- one\n- two\n"),
    ],
)
def test_entry_contract_is_enforced(toy, name, content):
    root, _env, _commit = toy
    folder, _output = _changelog(root)
    (folder / "added" / name).write_text(content)
    before = _tree(root)
    for args in ((), ("--check",)):
        refused = _assemble(root, *args)
        assert refused.returncode != 0 and name in refused.stderr
        assert _tree(root) == before


def test_name_limits_and_case_collisions(toy):
    """Check byte length before touching a name the filesystem cannot create."""
    import assemble_fragments

    oversized = Path("changelog.d/added") / ("é" * 128 + ".part")
    with pytest.raises(assemble_fragments.FragmentError, match="255") as exc:
        assemble_fragments.validate_names([oversized])
    assert oversized.name in str(exc.value)
    root, _env, _commit = toy
    folder, _output = _changelog(root)
    first = _entry(folder / "added", 1, 10, "- addition\n\n")
    other = first.with_name(first.name.upper())
    other.write_text("- collision\n\n")
    refused = _assemble(root)
    assert refused.returncode != 0 and "case" in refused.stderr
    assert first.name in refused.stderr and other.name in refused.stderr


def test_generated_project_owns_its_changelog_before_any_write(tmp_path, generate):
    """The normal render cache excludes sources and keeps the Jinja changelog."""
    import check_structure

    dest = tmp_path / "generated"
    generate(dest, project_name="demo_proj")
    assert not (dest / "changelog.d").exists()
    assert not (dest / "tests/integration/test_changelog_fragments.py").exists()
    expected = (
        (_ROOT / "CHANGELOG.md.jinja")
        .read_text()
        .replace("{{ project_title }}", "Demo Proj")
    )
    # The project's normal generation test also judges this exact template.
    assert (dest / "CHANGELOG.md").read_text() == expected
    findings = check_structure.run_checks(str(dest))
    assert [finding for finding in findings if finding[:2] == ("Q", "error")] == []
    before = _tree(dest)
    assert _assemble(dest, "--check").returncode == 0
    assert _tree(dest) == before
    assert not re.search(r"KEEL-|CMP-", expected)
