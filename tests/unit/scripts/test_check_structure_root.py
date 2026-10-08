"""
title: Unit — check_structure judges a root it is given
kind: tests
layer: n/a
summary: The gate's root override, pinned. `run_checks(root)` judges the tree at *root*, never keel's own; it resets every piece of module state a run accumulates (the unreadable-file memo included), so a second run in one process sees nothing of the first; and it attributes each message to the check letter that emitted it. `CHECKS` lists every `check_<LETTER>` the module defines, in order, so a check that is defined but not registered fails here. `main(['--root', path])` prints today's report shape and exit code for that root, refuses a root that is not a directory with exit 2, and `main()` with no argv still judges the template whatever `sys.argv` holds.
"""

import json
import os
import re
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit

_FM = (
    "---\ntitle: %s\nkind: %s\nlayer: n/a\nstatus: stable\nsummary: s\nid: %s\n"
    "created: 2026-01-01\nupdated: 2026-01-01\nvisibility: internal\n"
    "canonical: true\nowner: me\n---\n\n# t\n"
)
_POLICY = {
    "unattended_vars": ["CI", "RALPH"],
    "gate_runner_var": "RALPH",
    "gate_effects": ["local", "read"],
    "write_shapes": [],
    "area_dir": None,
    "effect_proof_skip": {},
    "empty_test_selections": {},
    "gate_vars": ["PY"],
}
_GUARD = (
    'WRITE_GUARD = @if [ -n "$(CI)$(RALPH)" ]; then echo "refusing $@" >&2; '
    "exit 1; fi\n"
)


def _label(root, name):
    """A directory with the README.md / AGENT.md / CLAUDE.md -> AGENT.md trio,
    each with the full frontmatter check_A requires."""
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    slug = name.replace("/", "-")
    (d / "README.md").write_text(_FM % (name, "readme", slug + "-readme"))
    (d / "AGENT.md").write_text(_FM % (name, "rules", slug + "-rules"))
    if not (d / "CLAUDE.md").is_symlink():
        os.symlink("AGENT.md", str(d / "CLAUDE.md"))
    return d


def _tree(root, manifest=None):
    """The smallest tree every check passes: the required top-level rows,
    labelled, and a config/project.json (default `{}`)."""
    for name in ("src", "tests", "docs", "config"):
        _label(root, name)
    (root / "config" / "project.json").write_text(
        json.dumps({} if manifest is None else manifest), encoding="utf-8"
    )
    return root


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    """run_checks rebinds module state; monkeypatch restores keel's afterwards
    so no other test module sees a tmp root or a stale memo."""
    for name in ("ROOT", "errors", "warnings", "GOVERNED"):
        monkeypatch.setattr(cs, name, getattr(cs, name))
    monkeypatch.setattr(cs, "_CONFIG_READ", dict(cs._CONFIG_READ))
    monkeypatch.setattr(cs, "_READ_REPORTED", set(cs._READ_REPORTED))


def _keel_paths():
    """Top-level names in keel that a tmp tree does not have."""
    return sorted(
        n for n in os.listdir(str(_ROOT)) if n not in ("src", "tests", "docs", "config")
    )


def test_a_clean_tree_is_clean(tmp_path):
    """The vacuity control: every negative case below starts from this tree."""
    assert cs.run_checks(str(_tree(tmp_path))) == []


def test_run_checks_judges_the_given_root_not_the_template(tmp_path):
    root = _tree(tmp_path / "proj")
    (root / "zzz").mkdir()
    (root / "zzz" / "data.txt").write_text("x\n")
    found = cs.run_checks(str(root))
    b_errors = [m for letter, tier, m in found if (letter, tier) == ("B", "error")]
    assert len(b_errors) == 1 and "zzz" in b_errors[0], found
    others = [m for _l, _t, m in found if "zzz" not in m]
    assert others == [], others
    # Nothing from keel's own tree leaks into a judgement of another root.
    for _letter, _tier, message in found:
        for name in _keel_paths():
            assert not message.startswith(name + "/"), message
    assert str(root) == cs.ROOT


def test_run_checks_resets_state_between_runs(tmp_path):
    bad = _tree(
        tmp_path / "bad",
        manifest={"make_targets": dict(_POLICY, gate_effects="local")},
    )
    (bad / "Makefile").write_text(_GUARD + "x: ## [local] X\n\t@true\n")
    (bad / "zzz").mkdir()
    first = cs.run_checks(str(bad))
    assert {letter for letter, tier, _m in first if tier == "error"} >= {"B", "W"}

    clean = _tree(tmp_path / "clean", manifest={"make_targets": _POLICY})
    (clean / "Makefile").write_text(_GUARD + "x: ## [local] X\n\t@true\n")
    assert cs.run_checks(str(clean)) == []
    assert cs.errors == [] and cs.warnings == []


def test_each_message_is_attributed_to_the_check_that_emitted_it(tmp_path, capsys):
    root = _tree(tmp_path / "proj", manifest={"make_targets": _POLICY})
    (root / "zzz").mkdir()
    (root / "Makefile").write_text(_GUARD + "planted: ## Does a thing\n\t@true\n")
    found = cs.run_checks(str(root))
    assert {(letter, tier) for letter, tier, _m in found} == {
        ("B", "error"),
        ("W", "error"),
    }, found
    assert cs.main(["--root", str(root)]) == 1
    printed = [
        line[len("ERROR ") :]
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("ERROR ")
    ]
    assert printed == [m for _l, tier, m in found if tier == "error"]


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root reads a 000 file"
)
def test_an_unreadable_file_is_reported_by_every_run(tmp_path):
    """The report-once memo is per run: a second run over the same tree in one
    process reports the unreadable file again rather than going quiet."""
    root = _tree(tmp_path / "proj")
    manifest = root / "config" / "project.json"
    manifest.chmod(0)
    try:
        first = cs.run_checks(str(root))
        second = cs.run_checks(str(root))
    finally:
        manifest.chmod(0o644)
    unreadable = [m for _l, t, m in first if t == "error" and "unreadable" in m]
    assert unreadable and "config/project.json" in unreadable[0], first
    assert second == first


def test_checks_registry_lists_every_check_function_in_order():
    source = (_ROOT / "scripts" / "check_structure.py").read_text(encoding="utf-8")
    defined = sorted(re.findall(r"^def check_([A-Z])\(", source, re.MULTILINE))
    assert [letter for letter, _fn in cs.CHECKS] == defined
    for letter, fn in cs.CHECKS:
        assert fn is getattr(cs, "check_" + letter)


def test_json_configs_names_every_config_a_check_reads():
    """The audit's config group derives the configs it classifies from this
    tuple, so a check reading a third JSON config without listing it here would
    leave that config's update unreported."""
    source = (_ROOT / "scripts" / "check_structure.py").read_text(encoding="utf-8")
    read = set(re.findall(r'_read_json_config\(\s*"([^"]+)"', source))
    read |= {
        "/".join(parts)
        for parts in re.findall(
            r'_read_json_config\(os\.path\.join\("([^"]+)", "([^"]+)"\)\)', source
        )
    }
    assert read == {p.replace(os.sep, "/") for p in cs.JSON_CONFIGS}


def test_main_root_flag_prints_the_same_report_shape_and_exit_code(
    tmp_path, capsys, monkeypatch
):
    bad = _tree(tmp_path / "bad")
    (bad / "zzz").mkdir()
    assert cs.main(["--root", str(bad)]) == 1
    out = capsys.readouterr().out
    assert any(line.startswith("ERROR zzz/") for line in out.splitlines()), out
    assert re.search(
        r"^check_structure: 1 error\(s\), 0 warning\(s\)$", out, re.MULTILINE
    )
    assert "next: `make advise`" in out

    clean = _tree(tmp_path / "clean")
    assert cs.main(["--root", str(clean)]) == 0
    assert "check_structure: 0 error(s), 0 warning(s)" in capsys.readouterr().out

    with pytest.raises(SystemExit) as exc:
        cs.main(["--root", str(tmp_path / "nonexistent")])
    assert exc.value.code == 2
    assert "nonexistent" in capsys.readouterr().err


def test_main_without_argv_judges_the_template_whatever_sys_argv_holds(
    monkeypatch, capsys
):
    """agents/index_enforcer/_brain.py and other importers call main() with no
    argument; it must not parse the importer's own command line."""
    seen = []
    monkeypatch.setattr(cs, "run_checks", lambda root: seen.append(root) or [])
    monkeypatch.setattr(sys, "argv", ["x", "--bogus"])
    assert cs.main() == 0
    assert seen == [str(_ROOT)]
    assert "check_structure: 0 error(s)" in capsys.readouterr().out
