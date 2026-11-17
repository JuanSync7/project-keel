"""
title: Integration — independent reference entries survive merge and restamping
kind: tests
layer: n/a
summary: Synthetic fragment sets prove branch-union assembly, fixed points, read-only checks and stamp ownership on a later pinned deletion date.
"""

import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from scripts.child_env import build_child_env
from test_copier_generation import clean_template as clean_template
from test_copier_generation import generate as generate
from test_copier_generation import renders as renders
from test_work_trailers import _run as toy_git

import optional_deps

pytest_plugins = ("test_work_trailers",)
pytestmark = pytest.mark.integration
_ROOT = Path(__file__).resolve().parents[2]


def _assemble(root, *args):
    return subprocess.run(
        [
            sys.executable,
            "-B",
            str(_ROOT / "scripts/assemble_fragments.py"),
            "--root",
            str(root),
            *args,
        ],
        env=build_child_env(),
        capture_output=True,
        text=True,
        timeout=60,
    )


def _tree(root):
    return {
        p.relative_to(root): (
            p.read_bytes() if p.is_file() else None,
            p.stat().st_mtime_ns,
        )
        for p in root.rglob("*")
    }


def _fragment_set(root):
    manifest_path = root / "config/project.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["reference_fragments"] = {
        "root": "docs/reference",
        "folder_suffix": ".d",
        "suffix": ".part",
        "sets": [
            {
                "output": "docs/reference/example.md",
                "head": "docs/reference/example.d/head.part",
                "folder": "docs/reference/example.d",
            }
        ],
    }
    manifest_path.write_text(json.dumps(manifest))
    folder = root / "docs/reference/example.d"
    table = folder / "01-entries"
    table.mkdir(parents=True)
    (folder / "head.part").write_text(
        "---\ntitle: Example\nupdated: 2020-01-01\n---\n\n# Example\n\n"
    )
    (folder / "tail.part").write_text("\nFixed footer.\n")
    (table / "head.part").write_text("## Entries\n\n| Key | Meaning |\n|---|---|\n")
    (table / "base.part").write_text("| `base` | baseline |\n")
    # Prefix order disagrees with key order, so a key sort would reorder rows.
    ordered = folder / "02-ordered"
    ordered.mkdir()
    (ordered / "head.part").write_text("\n## Ordered\n\n| Key | Meaning |\n|---|---|\n")
    (ordered / "000001-zeta.part").write_text("| `zeta` | first by prefix |\n")
    (ordered / "000002-alpha%20one.part").write_text("| `alpha one` | second |\n")
    assert _assemble(root).returncode == 0
    return folder, table, root / "docs/reference/example.md"


@pytest.mark.parametrize("case", ["merge-ours", "merge-theirs", "restamp"])
def test_two_independent_entries_survive_assembly(case, toy):
    """Either merge side recovers the union; deletion followed by restamp converges."""
    assert (_ROOT / "scripts/assemble_fragments.py").is_file()
    root, env, commit = toy
    folder, table, output = _fragment_set(root)
    toy_git(root, env, "add", "-A")
    baseline = commit("reference baseline")
    if case.startswith("merge"):
        for key in ("lane-one", "lane-two"):
            toy_git(root, env, "checkout", "-q", "-b", key, baseline)
            (table / f"{key}.part").write_text(f"| `{key}` | independent |\n")
            assert _assemble(root).returncode == 0
            toy_git(root, env, "add", "-A")
            commit(key)
        # Resolve only the derived file; both branches' independent sources merge.
        toy_git(root, env, "merge", "--no-edit", "-X", case.split("-")[1], "lane-one")
        chosen = output.read_text()
        assert ("`lane-one`" in chosen) != ("`lane-two`" in chosen)
        assert _assemble(root).returncode == 0
        text = output.read_text()
        assert "`lane-one`" in text and "`lane-two`" in text
    else:
        (table / "newest.part").write_text("| `newest` | later entry |\n")
        assert _assemble(root).returncode == 0
        toy_git(root, env, "add", "-A")
        commit("newest entry")
        (table / "newest.part").unlink()
        assert _assemble(root).returncode == 0
        assert "`newest`" not in output.read_text()
        import review_docs
        from scripts.jobs import restamp_docs

        run = subprocess.run(
            [
                sys.executable,
                "-B",
                str(_ROOT / "scripts/jobs/restamp_docs.py"),
                "--root",
                str(root),
                "--today",
                "2030-02-03",
            ],
            env=build_child_env(),
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert run.returncode == 0, run.stderr
        assert "updated: 2030-02-03" in output.read_text()
        records = review_docs.collect(str(root))
        assert not review_docs.stale_findings(records, "2030-02-03")
        assert (
            restamp_docs.restamp_text(output.read_text(), datetime.date(2030, 2, 3))
            is None
        )
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.rglob("*.part")}
    stamp = output.stat().st_mtime_ns
    assert _assemble(root, "--check").returncode == 0
    assert _assemble(root).returncode == 0
    assert output.stat().st_mtime_ns == stamp
    assert before == {
        p: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.rglob("*.part")
    }
    output.write_text(output.read_text() + "stale\n")
    stale = _assemble(root, "--check")
    assert stale.returncode != 0 and "example.md" in stale.stderr
    assert output.read_text().endswith("stale\n")
    malformed = table / "malformed.part"
    malformed.write_text("| `broken` |\n")
    refused = _assemble(root)
    assert refused.returncode != 0 and "cells" in refused.stderr
    assert output.read_text().endswith("stale\n")
    malformed.write_text("| `base` | duplicate |\n")
    refused = _assemble(root)
    assert refused.returncode != 0 and "duplicate" in refused.stderr


def test_check_catches_a_hand_added_row_and_assembly_overwrites_it(toy):
    """Configured fragments own the body, including removal of unsourced rows."""
    root, _env, _commit = toy
    _folder, _table, output = _fragment_set(root)
    assembled = output.read_text()
    output.write_text(
        assembled.replace(
            "\nFixed footer.", "| `manual` | no fragment |\n\nFixed footer."
        )
    )
    before = _tree(root)
    stale = _assemble(root, "--check")
    assert stale.returncode != 0 and "example.md" in stale.stderr
    assert _tree(root) == before
    assert _assemble(root).returncode == 0
    assert output.read_text() == assembled
    assert _assemble(root, "--check").returncode == 0


def test_entry_file_names_follow_their_keys(toy):
    """A name is the encoded key, or a prefix plus it, one form per table."""
    root, _env, _commit = toy
    folder, table, output = _fragment_set(root)
    text = output.read_text()
    assert 0 < text.index("`zeta`") < text.index("`alpha one`")
    ordered = folder / "02-ordered"
    misnamed = [
        (table / "wrong.part", "| `right` | key-named table |\n"),
        (table / "000003-gamma.part", "| `gamma` | prefix in a key-named table |\n"),
        (ordered / "000003-wrong.part", "| `right` | prefixed table |\n"),
        (ordered / "gamma.part", "| `gamma` | no prefix in a prefixed table |\n"),
        (ordered / "000003-a b.part", "| `a b` | unencoded key |\n"),
    ]
    for path, row in misnamed:
        path.write_text(row)
        before = _tree(root)
        for args in (("--check",), ()):
            refused = _assemble(root, *args)
            assert refused.returncode != 0, path.name
            assert path.name in refused.stderr, refused.stderr
            assert _tree(root) == before
        path.unlink()
    (ordered / "000003-a%2Fb.part").write_text("| `a/b` | encoded |\n")
    assert _assemble(root).returncode == 0
    assert "`a/b`" in output.read_text()


def test_empty_sets_refuse_unregistered_folders_and_allow_hand_edits(toy):
    """Opting out permits hand edits only when no fragment folder remains."""
    root, _env, _commit = toy
    path = root / "config/project.json"
    manifest = json.loads(path.read_text())
    manifest["reference_fragments"] = {
        "root": "docs/reference",
        "folder_suffix": ".d",
        "suffix": ".part",
        "sets": [],
    }
    path.write_text(json.dumps(manifest))
    folder = root / "docs/reference/stray.d"
    folder.mkdir(parents=True)
    before = _tree(root)
    for args in (("--check",), ()):
        refused = _assemble(root, *args)
        assert refused.returncode != 0 and "docs/reference/stray.d" in refused.stderr
        # The refusal names the project-relative path, never a Path repr.
        assert "PosixPath(" not in refused.stderr
        assert _tree(root) == before
    folder.rmdir()
    reference = folder.parent / "manual.md"
    reference.write_text("hand-edited reference\n")
    before = _tree(root)
    for args in (("--check",), ()):
        assert _assemble(root, *args).returncode == 0
        assert _tree(root) == before


@pytest.mark.skipif(
    not (_ROOT / "copier.yml").is_file(),
    reason="not a copier template — this is a generated project",
)
@pytest.mark.parametrize(
    "answers",
    [
        {},
        {"frontend_stack": "none", "showcase": False, "transports": []},
        {
            "frontend_stack": "astro",
            "showcase": True,
            "transports": ["grpc", "edge_nginx"],
        },
    ],
    ids=["defaults", "minimal", "astro-all-transports"],
)
def test_generated_references_ship_without_fragments_after_restamp(
    tmp_path, generate, answers
):
    """Render through the shared clean-template and answer-set cache fixtures."""
    optional_deps.importorskip("copier", extra="template")
    dest = tmp_path / "generated"
    generate(dest, **answers)
    for name in ("settings", "features"):
        assert not (dest / f"docs/reference/{name}.d").exists()
        before = (dest / f"docs/reference/{name}.md").read_text()
        original = (_ROOT / f"docs/reference/{name}.md").read_text()
        # The task owns only the date; no answer removes reference rows.
        assert re.sub(r"(?m)^updated: .*", "updated:", before) == re.sub(
            r"(?m)^updated: .*", "updated:", original
        )
    assert (dest / "scripts/assemble_fragments.py").is_file()
    assert not (dest / "tests/integration/test_reference_fragments.py").exists()
    manifest = json.loads((dest / "config/project.json").read_text())
    assert manifest["reference_fragments"]["sets"] == []
    roster = (dest / "docs/reference/README.md").read_text()
    members = set(re.findall(r"^\| `([^`]+)` \|", roster, re.MULTILINE))
    assert {"settings.md", "features.md"} <= members
    assert members <= {"README.md", "settings.md", "features.md"}
    assert "## Authoring entries" not in roster
    for script, args in (
        ("scripts/assemble_fragments.py", ["--check"]),
        ("scripts/jobs/restamp_docs.py", ["--today", "2030-02-03"]),
        ("scripts/assemble_fragments.py", ["--check"]),
    ):
        run = subprocess.run(
            [sys.executable, "-B", str(dest / script), *args],
            cwd=dest,
            env=build_child_env(),
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert run.returncode == 0, run.stdout + run.stderr
    for name in ("settings", "features"):
        after = (dest / f"docs/reference/{name}.md").read_text()
        original = (_ROOT / f"docs/reference/{name}.md").read_text()
        assert re.sub(r"(?m)^updated: .*", "updated:", after) == re.sub(
            r"(?m)^updated: .*", "updated:", original
        )
