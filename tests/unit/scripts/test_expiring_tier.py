"""
title: Unit — a project's own finding warns until a hard date, from a record that only shrinks
kind: tests
layer: n/a
summary: scripts/expiring_tier.py pinned on fixture projects under tmp_path, with the day handed in, so no case depends on the day it runs. In the template repository (copier.yml present) every finding is red and nothing warns, and a date past the ceiling or a missing manifest is refused there too. In a generated project a finding the baseline records warns the day before config/project.json `expiring_tier.expires` and is red on that day; a finding with no entry left for it is red and names `make gate-baseline`, a second copy over the recorded count included; an entry no finding matches is red; a line outside the `<file>:<line>: ` grammar is red; with no baseline file every finding is red and names the target. A date later than scripts/expiring_tier_data.py `CEILING`, or not a calendar date, is refused; the ceiling itself and an earlier date are accepted. The recorder keeps what each check was handed as a multiset: two identical lines are two entries, and a check judged twice over the same lines is not counted twice. A baseline naming a check `CHECKS` does not register is red.
@covers scripts/expiring_tier.py
"""

import datetime
import json
import sys
import warnings
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import expiring_tier as tier  # noqa: E402
import expiring_tier_data  # noqa: E402

pytestmark = pytest.mark.unit

_DAY = datetime.timedelta(days=1)
_CEILING = datetime.date.fromisoformat(expiring_tier_data.CEILING)
_CHECK = sorted(expiring_tier_data.CHECKS)[0]
_BASELINE = "config/gate-baseline.json"
_A = "src/a.py:3: opens config/project.json directly — read it through the loader"
_A_MOVED = "src/a.py:9: opens config/project.json directly — read it through the loader"
_A_ID = "src/a.py: opens config/project.json directly — read it through the loader"
_B = "src/b.py:7: reads the declared variable X directly — read it through env"


def _project(tmp_path, expires=None, baseline=None, template=False):
    root = tmp_path / "proj"
    (root / "config").mkdir(parents=True)
    block = {"baseline": _BASELINE, "expires": expires or _CEILING.isoformat()}
    (root / "config" / "project.json").write_text(
        json.dumps({"expiring_tier": block}), encoding="utf-8"
    )
    if baseline is not None:
        (root / _BASELINE).write_text(json.dumps(baseline), encoding="utf-8")
    if template:
        (root / tier.TEMPLATE_MARK).write_text("_subdirectory: .\n", encoding="utf-8")
    return root


def _recorded(entries, check=_CHECK, commit="v0.1.0"):
    checks = {c: [] for c in expiring_tier_data.CHECKS}
    checks[check] = list(entries)
    return {"checks": checks, "commit": commit}


def test_identity_drops_the_line_number_and_refuses_a_line_with_no_file():
    assert tier.identity(_A) == _A_ID
    assert tier.identity(_A_MOVED) == _A_ID
    assert tier.identity("config/project.json: names `x`; delete it") is None
    assert tier.identity("src/a.py:x3: no number") is None
    assert tier.identity(":3: no file") is None
    assert tier.identity("src/a.py:3:no space") is None


def test_in_the_template_every_finding_is_red_and_nothing_warns(tmp_path):
    root = _project(tmp_path, baseline=_recorded([_A_ID]), template=True)
    verdict = tier.judge(_CHECK, [_A], str(root), today=_CEILING - _DAY)
    assert verdict.red == [_A]
    assert verdict.warned == []
    assert verdict.note is None


def test_a_recorded_finding_warns_before_the_date_and_is_red_on_it(tmp_path):
    root = _project(tmp_path, baseline=_recorded([_A_ID]))
    before = tier.judge(_CHECK, [_A_MOVED], str(root), today=_CEILING - _DAY)
    assert before.red == []
    assert before.warned == [_A_MOVED]
    assert _CEILING.isoformat() in before.note
    assert "expiring_tier.expires" in before.note
    assert _BASELINE in before.note
    on = tier.judge(_CHECK, [_A_MOVED], str(root), today=_CEILING)
    assert on.warned == []
    assert len(on.red) == 1 and on.red[0].startswith(_A_MOVED), on.red
    assert "ended on %s" % _CEILING.isoformat() in on.red[0]
    after = tier.judge(_CHECK, [_A_MOVED], str(root), today=_CEILING + _DAY)
    assert len(after.red) == 1 and after.warned == []


def test_an_earlier_configured_date_ends_the_grace_on_that_date(tmp_path):
    earlier = _CEILING - 10 * _DAY
    root = _project(tmp_path, expires=earlier.isoformat(), baseline=_recorded([_A_ID]))
    assert tier.judge(_CHECK, [_A], str(root), today=earlier - _DAY).red == []
    assert len(tier.judge(_CHECK, [_A], str(root), today=earlier).red) == 1


def test_an_unrecorded_finding_is_red_at_once_and_names_the_target(tmp_path):
    root = _project(tmp_path, baseline=_recorded([_A_ID]))
    verdict = tier.judge(_CHECK, [_A, _B], str(root), today=_CEILING - _DAY)
    assert verdict.warned == [_A]
    assert len(verdict.red) == 1 and verdict.red[0].startswith(_B), verdict.red
    assert "make %s" % tier.RECORD_TARGET in verdict.red[0]
    assert "_commit" in verdict.red[0]


def test_a_copy_over_the_recorded_count_is_red(tmp_path):
    root = _project(tmp_path, baseline=_recorded([_A_ID]))
    verdict = tier.judge(_CHECK, [_A, _A_MOVED], str(root), today=_CEILING - _DAY)
    assert verdict.warned == [_A]
    assert len(verdict.red) == 1 and verdict.red[0].startswith(_A_MOVED)
    twice = _project(tmp_path / "two", baseline=_recorded([_A_ID, _A_ID]))
    both = tier.judge(_CHECK, [_A, _A_MOVED], str(twice), today=_CEILING - _DAY)
    assert both.red == [] and both.warned == [_A, _A_MOVED]


def test_an_entry_no_finding_matches_is_red_so_the_record_only_shrinks(tmp_path):
    root = _project(tmp_path, baseline=_recorded([_A_ID, _A_ID]))
    verdict = tier.judge(_CHECK, [_A], str(root), today=_CEILING - _DAY)
    assert verdict.warned == [_A]
    assert len(verdict.red) == 1, verdict.red
    assert verdict.red[0].startswith(_BASELINE + ": "), verdict.red
    assert _A_ID in verdict.red[0] and "delete" in verdict.red[0]


def test_a_line_with_no_file_is_red_whatever_the_record_says(tmp_path):
    line = "config/project.json: import_layers.may_end_the_process names `x`"
    root = _project(tmp_path, baseline=_recorded([]))
    verdict = tier.judge(_CHECK, [line], str(root), today=_CEILING - _DAY)
    assert verdict.warned == []
    assert len(verdict.red) == 1 and verdict.red[0].startswith(line)


def test_with_no_baseline_every_finding_is_red_and_names_the_target(tmp_path):
    root = _project(tmp_path)
    verdict = tier.judge(_CHECK, [_A], str(root), today=_CEILING - _DAY)
    assert verdict.warned == []
    assert len(verdict.red) == 1 and verdict.red[0].startswith(_A)
    assert "make %s" % tier.RECORD_TARGET in verdict.red[0]
    assert "no %s" % _BASELINE in verdict.red[0]


def test_no_finding_is_green_with_no_note(tmp_path):
    root = _project(tmp_path)
    verdict = tier.judge(_CHECK, [], str(root), today=_CEILING - _DAY)
    assert verdict == tier.Verdict(red=[], warned=[], note=None)


def test_a_date_later_than_the_ceiling_is_refused_and_the_ceiling_is_accepted(
    tmp_path,
):
    later = _project(tmp_path / "later", expires=(_CEILING + _DAY).isoformat())
    with pytest.raises(tier.TierError, match="later than the ceiling %s" % _CEILING):
        tier.load_policy(str(later))
    with pytest.raises(tier.TierError, match="expiring_tier_data.py"):
        tier.judge(_CHECK, [], str(later), today=_CEILING - _DAY)
    same = tier.load_policy(str(_project(tmp_path / "same")))
    assert same.expires == _CEILING
    assert same.baseline == _BASELINE
    earlier = _project(tmp_path / "early", expires=(_CEILING - _DAY).isoformat())
    assert tier.load_policy(str(earlier)).expires == _CEILING - _DAY


@pytest.mark.parametrize("value", ["2027-1-31", "2027-02-30", "soon", ""])
def test_a_date_that_is_not_a_calendar_date_is_refused_by_key(tmp_path, value):
    root = _project(tmp_path)
    manifest = json.loads((root / "config" / "project.json").read_text("utf-8"))
    manifest["expiring_tier"]["expires"] = value
    (root / "config" / "project.json").write_text(json.dumps(manifest), "utf-8")
    with pytest.raises(tier.TierError, match=r"expiring_tier\.expires"):
        tier.load_policy(str(root))


def test_a_template_with_a_bad_tier_config_is_refused_too(tmp_path):
    """The policy is checked before the template's early return, so a date
    past the ceiling fails closed in every gate that adopts the tier."""
    later = (_CEILING + _DAY).isoformat()
    root = _project(tmp_path, expires=later, template=True)
    with pytest.raises(tier.TierError, match="ceiling"):
        tier.judge(_CHECK, [_A], str(root))
    bare = tmp_path / "bare"
    bare.mkdir()
    (bare / tier.TEMPLATE_MARK).write_text("_subdirectory: .\n", encoding="utf-8")
    with pytest.raises(tier.TierError, match="config/project.json"):
        tier.judge(_CHECK, [_A], str(bare))


def test_an_unregistered_check_is_refused(tmp_path):
    root = _project(tmp_path)
    with pytest.raises(tier.TierError, match="not a check"):
        tier.judge("no-such-check", [], str(root), today=_CEILING - _DAY)


def test_a_malformed_baseline_is_refused_by_name(tmp_path):
    for bad in ([], {"checks": [], "commit": "v"}, {"checks": {_CHECK: [1]}}):
        root = _project(tmp_path / str(len(str(bad))), baseline=bad)
        with pytest.raises(tier.TierError, match=_BASELINE):
            tier.judge(_CHECK, [_A], str(root), today=_CEILING - _DAY)


def test_a_baseline_naming_an_unregistered_check_is_red(tmp_path):
    record = _recorded([_A_ID])
    record["checks"]["retired-check"] = []
    root = _project(tmp_path, baseline=record)
    found = tier.baseline_findings(str(root))
    assert len(found) == 1 and "retired-check" in found[0], found
    assert (
        tier.baseline_findings(str(_project(tmp_path / "ok", baseline=_recorded([]))))
        == []
    )
    assert tier.baseline_findings(str(_project(tmp_path / "none"))) == []


def test_apply_warns_once_with_the_note_and_returns_the_red_lines(tmp_path):
    root = _project(tmp_path, baseline=_recorded([_A_ID]))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        red = tier.apply(_CHECK, [_A, _B], str(root), today=_CEILING - _DAY)
    assert len(red) == 1 and red[0].startswith(_B)
    assert len(caught) == 1
    assert issubclass(caught[0].category, tier.ExpiringTierWarning)
    assert _A in str(caught[0].message)
    empty = _project(tmp_path / "empty", baseline=_recorded([]))
    with warnings.catch_warnings(record=True) as quiet:
        warnings.simplefilter("always")
        assert tier.apply(_CHECK, [], str(empty), today=_CEILING - _DAY) == []
    assert quiet == []


def test_the_recorder_keeps_what_each_check_was_handed(tmp_path):
    root = _project(tmp_path)
    assert tier.recorded() is None
    tier.start_recording()
    try:
        tier.judge(_CHECK, [_B, _A], str(root), today=_CEILING - _DAY)
        tier.judge(_CHECK, [_B, _A], str(root), today=_CEILING - _DAY)
        assert tier.recorded() == {_CHECK: sorted([_A, _B])}
    finally:
        tier.stop_recording()
    assert tier.recorded() is None


def test_the_recorder_keeps_every_copy_of_an_identical_finding(tmp_path):
    """Two byte-identical findings are two entries, and a check judged twice
    over the same lines is not counted twice."""
    root = _project(tmp_path)
    tier.start_recording()
    try:
        tier.judge(_CHECK, [_A, _A, _B], str(root), today=_CEILING - _DAY)
        tier.judge(_CHECK, [_A, _A, _B], str(root), today=_CEILING - _DAY)
        tier.judge(_CHECK, [_A], str(root), today=_CEILING - _DAY)
        assert tier.recorded() == {_CHECK: sorted([_A, _A, _B])}
    finally:
        tier.stop_recording()


def test_the_run_date_is_today_when_none_is_handed_in(tmp_path, monkeypatch):
    root = _project(tmp_path, baseline=_recorded([_A_ID]))
    monkeypatch.setattr(tier, "run_today", lambda _root: _CEILING)
    assert len(tier.judge(_CHECK, [_A], str(root)).red) == 1
    monkeypatch.setattr(tier, "run_today", lambda _root: _CEILING - _DAY)
    assert tier.judge(_CHECK, [_A], str(root)).red == []
