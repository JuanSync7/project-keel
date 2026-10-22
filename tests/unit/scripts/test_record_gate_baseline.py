"""
title: Unit — the gate baseline is recorded from what the checks see, and grows only when the update moved
kind: tests
layer: n/a
summary: scripts/record_gate_baseline.py pinned on fixture projects under tmp_path, with the pytest run replaced by a runner that writes a chosen record, so no case starts a process. `answers_commit` reads the one top-level `_commit` line of .copier-answers.yml, quoted or not, and refuses a file with none, two or an empty one. `next_baseline` turns each recorded line into its identity, keeps every registered check and drops a retired one; with no old file, or an old one stamped with another commit, it may grow; stamped with the same commit it refuses each entry over the old count and names `_commit`, and it may shrink. `render` is canonical JSON, so a second run writes the same bytes. `main` refuses the template repository and a missing answers file (USAGE), a bad `expiring_tier` (CONFIG), a record that lacks a registered check (NOTHING_JUDGED), refused growth (FAILURE, file untouched), and hands a pytest status other than 0 or 1 through.
@covers scripts/record_gate_baseline.py
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import expiring_tier_data  # noqa: E402
import record_gate_baseline as rgb  # noqa: E402
from exit_codes import ExitCode  # noqa: E402

pytestmark = pytest.mark.unit

_BASELINE = "config/gate-baseline.json"
_CHECKS = sorted(expiring_tier_data.CHECKS)
_CHECK = _CHECKS[0]
_A = "src/a.py:3: opens config/project.json directly — read it through the loader"
_A2 = "src/a.py:8: opens config/project.json directly — read it through the loader"
_A_ID = "src/a.py: opens config/project.json directly — read it through the loader"
_B = "src/b.py:7: reads the declared variable X directly — read it through env"
_B_ID = "src/b.py: reads the declared variable X directly — read it through env"


def _record(lines=(), check=_CHECK):
    record = {c: [] for c in _CHECKS}
    record[check] = sorted(lines)
    return record


def _project(tmp_path, commit="v0.2.0", template=False, expires=None):
    root = tmp_path / "proj"
    (root / "config").mkdir(parents=True)
    block = {"baseline": _BASELINE, "expires": expires or expiring_tier_data.CEILING}
    (root / "config" / "project.json").write_text(
        json.dumps({"expiring_tier": block}), encoding="utf-8"
    )
    if commit is not None:
        (root / ".copier-answers.yml").write_text(
            "# Changes here will be overwritten by Copier\n_commit: %s\n"
            "_src_path: gh:keel\n" % commit,
            encoding="utf-8",
        )
    if template:
        (root / "copier.yml").write_text("_subdirectory: .\n", encoding="utf-8")
    return root


def _runner(record, status=1):
    def run(root, record_path):
        Path(record_path).write_text(json.dumps(record), encoding="utf-8")
        return status

    return run


def test_answers_commit_reads_the_one_commit_line(tmp_path):
    root = tmp_path
    answers = root / ".copier-answers.yml"
    for text, want in (
        ("_commit: v0.1.0\n", "v0.1.0"),
        ("_commit: 'v0.1.0-3-gabc'\n", "v0.1.0-3-gabc"),
        ('a: 1\n_commit: "abc123"\n', "abc123"),
    ):
        answers.write_text(text, encoding="utf-8")
        assert rgb.answers_commit(str(root)) == want
    for text in ("a: 1\n", "_commit: a\n_commit: b\n", "_commit:\n", "_commit: ''\n"):
        answers.write_text(text, encoding="utf-8")
        with pytest.raises(rgb.BaselineError, match="_commit"):
            rgb.answers_commit(str(root))
    answers.unlink()
    with pytest.raises(rgb.BaselineError, match=".copier-answers.yml"):
        rgb.answers_commit(str(root))


def test_a_first_baseline_records_every_identity_of_every_check():
    doc, refused = rgb.next_baseline(None, "v1", _record([_B, _A, _A2, "no grammar"]))
    assert refused == []
    assert doc["commit"] == "v1"
    assert sorted(doc["checks"]) == _CHECKS
    assert doc["checks"][_CHECK] == [_A_ID, _A_ID, _B_ID]
    assert all(doc["checks"][c] == [] for c in _CHECKS if c != _CHECK)


def test_the_same_commit_may_shrink_and_never_grow():
    old = {"checks": {_CHECK: [_A_ID]}, "commit": "v1"}
    doc, refused = rgb.next_baseline(old, "v1", _record([]))
    assert refused == [] and doc["checks"][_CHECK] == []
    doc, refused = rgb.next_baseline(old, "v1", _record([_A, _A2, _B]))
    assert doc is None
    assert len(refused) == 2, refused
    assert any(_B_ID in r for r in refused) and any(_A_ID in r for r in refused)
    assert all("_commit" in r and _CHECK in r for r in refused)


def test_a_moved_commit_may_grow_and_a_retired_check_is_dropped():
    old = {"checks": {_CHECK: [_A_ID], "retired": ["x.py: y"]}, "commit": "v1"}
    doc, refused = rgb.next_baseline(old, "v2", _record([_A, _B]))
    assert refused == []
    assert doc == {
        "checks": _record([_A_ID, _B_ID]),
        "commit": "v2",
    }


def test_render_is_canonical():
    doc, _ = rgb.next_baseline(None, "v1", _record([_B, _A]))
    text = rgb.render(doc)
    assert text.endswith("\n")
    assert json.loads(text) == doc
    assert text == rgb.render(json.loads(text))
    assert text.index('"checks"') < text.index('"commit"')


def test_main_writes_the_baseline_and_a_second_run_writes_the_same_bytes(tmp_path):
    root = _project(tmp_path)
    runner = _runner(_record([_A]))
    assert rgb.main([], root=str(root), runner=runner) == ExitCode.SUCCESS
    first = (root / _BASELINE).read_bytes()
    assert json.loads(first)["checks"][_CHECK] == [_A_ID]
    assert json.loads(first)["commit"] == "v0.2.0"
    assert rgb.main([], root=str(root), runner=runner) == ExitCode.SUCCESS
    assert (root / _BASELINE).read_bytes() == first


def test_main_refuses_growth_at_the_same_commit_and_leaves_the_file(tmp_path):
    root = _project(tmp_path)
    assert rgb.main([], root=str(root), runner=_runner(_record([_A]))) == 0
    before = (root / _BASELINE).read_bytes()
    code = rgb.main([], root=str(root), runner=_runner(_record([_A, _B])))
    assert code == ExitCode.FAILURE
    assert (root / _BASELINE).read_bytes() == before


def test_main_refuses_the_template_and_a_project_with_no_answers(tmp_path):
    template = _project(tmp_path / "t", template=True)
    assert rgb.main([], root=str(template), runner=_runner(_record())) == ExitCode.USAGE
    bare = _project(tmp_path / "b", commit=None)
    assert rgb.main([], root=str(bare), runner=_runner(_record())) == ExitCode.USAGE
    assert not (template / _BASELINE).exists()
    assert not (bare / _BASELINE).exists()


def test_main_refuses_a_bad_tier_config(tmp_path):
    root = _project(tmp_path, expires="2999-01-01")
    assert rgb.main([], root=str(root), runner=_runner(_record())) == ExitCode.CONFIG


def test_a_check_the_run_never_judged_writes_nothing(tmp_path):
    root = _project(tmp_path)
    record = _record([_A])
    del record[_CHECKS[-1]]
    code = rgb.main([], root=str(root), runner=_runner(record))
    assert code == ExitCode.NOTHING_JUDGED
    assert not (root / _BASELINE).exists()


def test_a_run_that_wrote_no_record_writes_nothing(tmp_path):
    root = _project(tmp_path)
    code = rgb.main([], root=str(root), runner=lambda _root, _path: 0)
    assert code == ExitCode.NOTHING_JUDGED
    assert not (root / _BASELINE).exists()


@pytest.mark.parametrize("status", [2, 4, 130])
def test_a_pytest_status_other_than_pass_or_fail_is_handed_through(tmp_path, status):
    root = _project(tmp_path)
    code = rgb.main([], root=str(root), runner=_runner(_record([_A]), status))
    assert int(code) == status
    assert not (root / _BASELINE).exists()
