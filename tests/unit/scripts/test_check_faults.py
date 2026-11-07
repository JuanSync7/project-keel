"""
title: Unit — structure checks reject planted faults through their entrypoints
summary: Small temporary-tree twins exercise check functions whose existing negative tests covered only helpers. Every case requires at least one error from its check.
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """Give each check its own tree and read/report state."""
    monkeypatch.setattr(cs, "ROOT", str(tmp_path))
    monkeypatch.setattr(cs, "errors", [])
    monkeypatch.setattr(cs, "warnings", [])
    monkeypatch.setattr(cs, "_CONFIG_READ", {})
    monkeypatch.setattr(cs, "_READ_REPORTED", set())
    return tmp_path


def _write(root, path, text):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def test_missing_package_boundary_fails(repo):
    _write(repo, "src/pkg/mod.py", "value = 1\n")
    cs.check_C()
    assert len(cs.errors) == 1 and "no __init__.py" in cs.errors[0], cs.errors


def test_copied_agent_rules_fail(repo):
    _write(repo, "AGENT.md", "# Rules\n")
    _write(repo, "CLAUDE.md", "# Copied rules\n")
    cs.check_I()
    assert len(cs.errors) == 1 and "must be a symlink" in cs.errors[0], cs.errors


def test_undeclared_template_twin_fails(repo):
    _write(repo, "README.md.jinja", "# Twin\n")
    cs.check_N()
    assert cs.errors and any("undeclared" in e for e in cs.errors), cs.errors


def test_dead_document_link_fails(repo):
    _write(repo, "docs/a.md", "See [missing](missing.md).\n")
    cs.check_Q()
    assert len(cs.errors) == 1 and "missing.md" in cs.errors[0], cs.errors


def test_catalogue_of_absent_script_fails(repo):
    _write(
        repo,
        "docs/guides/deterministic-checks.md",
        "## The checks\n\n| Check | Script | Gate? |\n|---|---|---|\n"
        "| Missing | `scripts/absent.py` | error |\n",
    )
    _write(repo, "Makefile", "check-all:\n\t@true\n")
    cs.check_R()
    assert cs.errors and any("does not exist" in e for e in cs.errors), cs.errors


def test_absent_practice_mechanism_fails(repo):
    _write(
        repo,
        "config/practices.json",
        json.dumps(
            {
                "practices": [
                    {"id": "fault", "enforced_by": ["script:scripts/absent.py"]}
                ]
            }
        ),
    )
    cs.check_T()
    assert len(cs.errors) == 1 and "absent.py" in cs.errors[0], cs.errors


def test_unreachable_policy_fails(repo):
    _write(
        repo,
        "config/practices.json",
        json.dumps(
            {"practices": [{"id": "fault", "enforced_by": ["doc:docs/policy.md"]}]}
        ),
    )
    _write(repo, "AGENT.md", "# Rules\n")
    _write(repo, "docs/policy.md", "# Unreachable policy\n")
    cs.check_U()
    assert len(cs.errors) == 1 and "docs/policy.md" in cs.errors[0], cs.errors
