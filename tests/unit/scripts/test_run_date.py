"""
title: Unit — the one date a gate run calls today
kind: tests
layer: n/a
summary: scripts/run_date.py pinned with an injected clock, so no case depends on the day it runs. A date a caller supplies is accepted only when it is written YYYY-MM-DD, is a calendar date, is not later than the clock and is not more than config/project.json `evidence.run_date.max_age_days` days before it; every boundary is computed from the injected clock. An absent `evidence.run_date` switches the channel off and is no error, an absent config/project.json likewise, and each malformed shape of the block is refused naming its key, as is an `env` that `child_env.names` does not list. The driver's and the reader's views agree: `for_run` and `today` give the same date for the same environment. The block keel ships parses and its variable is on the allowlist.
@covers scripts/run_date.py
"""

import datetime
import json
import re
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import config_loader  # noqa: E402
import run_date  # noqa: E402

pytestmark = pytest.mark.unit

_NAME = "A_RUN_DATE"
_CLOCK = datetime.date(2031, 3, 1)  # the day after a February with 28 days
_DAY = datetime.timedelta(days=1)


def _clock():
    return _CLOCK


def _policy(max_age_days=1):
    return run_date.RunDatePolicy(env=_NAME, max_age_days=max_age_days)


def _manifest(block, names=(_NAME,)):
    return {"evidence": {"run_date": block}, "child_env": {"names": list(names)}}


def _block(**override):
    block = {"env": _NAME, "max_age_days": 1}
    block.update(override)
    return block


# --- a caller's date ----------------------------------------------------------


@pytest.mark.parametrize("bound", [0, 1, 3])
def test_a_run_date_is_a_calendar_date_not_after_the_clock_and_within_the_bound(bound):
    policy = _policy(bound)
    accepted = [_CLOCK - _DAY * age for age in range(bound + 1)]
    assert accepted[0] == _CLOCK and len(accepted) == bound + 1
    for day in accepted:
        assert run_date.checked(day.isoformat(), policy, _CLOCK) == day
    too_old = _CLOCK - _DAY * (bound + 1)
    with pytest.raises(run_date.RunDateError) as caught:
        run_date.checked(too_old.isoformat(), policy, _CLOCK)
    message = str(caught.value)
    assert _NAME in message and "evidence.run_date.max_age_days" in message
    assert "(%d)" % bound in message, message
    with pytest.raises(run_date.RunDateError) as caught:
        run_date.checked((_CLOCK + _DAY).isoformat(), policy, _CLOCK)
    assert _NAME in str(caught.value) and "later" in str(caught.value)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        " ",
        "not-a-date",
        "2031-13-01",
        "2031-02-29",
        "2031-2-3",
        "20310301",
        "2031-03-01T00:00:00",
        "2031-03-01 ",
        " 2031-03-01",
        "2031-03-01\n",
        "31-03-01",
    ],
)
def test_a_value_that_is_not_a_written_out_calendar_date_is_refused(raw):
    with pytest.raises(run_date.RunDateError) as caught:
        run_date.checked(raw, _policy(), _CLOCK)
    assert _NAME in str(caught.value)


def test_a_refusal_never_quotes_a_long_value():
    """The variable is one config names, and a wrong name there could point at
    anything: a value too long to be a date is counted, not printed."""
    secret = "s3cret-" * 20
    with pytest.raises(run_date.RunDateError) as caught:
        run_date.checked(secret, _policy(), _CLOCK)
    assert "s3cret" not in str(caught.value)
    assert str(len(secret)) in str(caught.value)


# --- the driver and the reader ------------------------------------------------


def test_the_driver_and_the_reader_agree_on_the_date():
    policy = _policy()
    yesterday = _CLOCK - _DAY
    assert run_date.for_run({}, policy, _clock) == (_NAME, _CLOCK.isoformat())
    assert run_date.today({}, policy, _clock) == _CLOCK
    env = {_NAME: yesterday.isoformat()}
    assert run_date.for_run(env, policy, _clock) == (_NAME, yesterday.isoformat())
    assert run_date.today(env, policy, _clock) == yesterday
    # What the driver hands on is what a reader below it accepts, a day later.
    name, value = run_date.for_run({}, policy, _clock)
    assert run_date.today({name: value}, policy, lambda: _CLOCK + _DAY) == _CLOCK
    for bad in ((_CLOCK - 2 * _DAY).isoformat(), (_CLOCK + _DAY).isoformat(), ""):
        with pytest.raises(run_date.RunDateError):
            run_date.for_run({_NAME: bad}, policy, _clock)
        with pytest.raises(run_date.RunDateError):
            run_date.today({_NAME: bad}, policy, _clock)


def test_the_clock_is_read_once_per_answer():
    reads = []

    def clock():
        reads.append(1)
        return _CLOCK

    run_date.for_run({}, _policy(), clock)
    assert len(reads) == 1
    run_date.for_run({_NAME: _CLOCK.isoformat()}, _policy(), clock)
    assert len(reads) == 2
    run_date.today({_NAME: _CLOCK.isoformat()}, _policy(), clock)
    assert len(reads) == 3


def test_without_a_policy_a_reader_reads_the_clock_and_no_variable():
    """No `evidence.run_date`: the channel is off, and nothing in the
    environment is a run date."""
    assert run_date.today({_NAME: "not-a-date"}, None, _clock) == _CLOCK


# --- a commit made inside the run --------------------------------------------

_GIT_DATES = ("GIT_AUTHOR_DATE", "GIT_COMMITTER_DATE")
_OFFSET = re.compile(r"^[+-][0-9]{4}$")


def _moment(day, hour, minute, second, microsecond=0):
    return datetime.datetime.combine(
        day, datetime.time(hour, minute, second, microsecond)
    )


def _dated(dates, expected):
    """Assert both git variables hold *expected* (a 'YYYY-MM-DD HH:MM:SS'
    local time) followed by a UTC offset, the one value for both."""
    assert sorted(dates) == list(_GIT_DATES), dates
    assert dates["GIT_AUTHOR_DATE"] == dates["GIT_COMMITTER_DATE"], dates
    when, offset = dates["GIT_COMMITTER_DATE"].rsplit(" ", 1)
    assert when == expected, dates
    assert _OFFSET.match(offset), dates


def test_a_commit_made_after_midnight_in_a_run_begun_before_it_is_dated_the_run_date():
    """The judge reads a committed document's date from git, so a commit the
    run makes after midnight must not carry the clock's new day: it is held to
    the last second of the day the run began (three goals of one `make verify`
    went red on exactly this, measured)."""
    yesterday = _CLOCK - _DAY
    after_midnight = _moment(_CLOCK, 0, 30, 5)
    dates = run_date.git_dates(
        {_NAME: yesterday.isoformat()}, _policy(), lambda: after_midnight
    )
    _dated(dates, "2031-02-28 23:59:59")


def test_a_commit_made_on_the_run_date_is_dated_now():
    """Before midnight the moment is the clock's own, to the second, so a
    commit is never dated later than it was made."""
    now = _moment(_CLOCK, 14, 0, 5, 123456)
    dates = run_date.git_dates({_NAME: _CLOCK.isoformat()}, _policy(), lambda: now)
    _dated(dates, "2031-03-01 14:00:05")


def test_outside_a_run_a_commit_keeps_git_s_own_clock():
    now = _moment(_CLOCK, 9, 0, 0)
    assert run_date.git_dates({}, _policy(), lambda: now) == {}
    assert run_date.git_dates({_NAME: "not-a-date"}, None, lambda: now) == {}


def test_a_commit_date_is_refused_for_a_run_date_the_run_could_not_have():
    now = _moment(_CLOCK, 9, 0, 0)
    for bad in ((_CLOCK - 2 * _DAY).isoformat(), (_CLOCK + _DAY).isoformat(), ""):
        with pytest.raises(run_date.RunDateError):
            run_date.git_dates({_NAME: bad}, _policy(), lambda: now)


# --- the config block ---------------------------------------------------------


def test_an_absent_block_switches_the_channel_off():
    assert run_date.policy({}) is None
    assert run_date.policy({"evidence": {"dir": ".evidence"}}) is None
    assert run_date.policy(_manifest(_block())) == _policy()
    assert run_date.policy(_manifest(_block(max_age_days=0))) == _policy(0)


@pytest.mark.parametrize(
    "manifest, names",
    [
        ([], "config/project.json"),
        ({"evidence": []}, "evidence"),
        (_manifest([]), "evidence.run_date"),
        (_manifest({}), "evidence.run_date.env"),
        (_manifest(_block(env=3)), "evidence.run_date.env"),
        (_manifest(_block(env="")), "evidence.run_date.env"),
        (_manifest(_block(env="1X")), "evidence.run_date.env"),
        (_manifest(_block(env="A-B")), "evidence.run_date.env"),
        (_manifest({"env": _NAME}), "evidence.run_date.max_age_days"),
        (_manifest(_block(max_age_days=True)), "evidence.run_date.max_age_days"),
        (_manifest(_block(max_age_days=-1)), "evidence.run_date.max_age_days"),
        (_manifest(_block(max_age_days=1.0)), "evidence.run_date.max_age_days"),
        (_manifest(_block(max_age_days="1")), "evidence.run_date.max_age_days"),
        (_manifest(_block(grace=1)), "evidence.run_date.grace"),
        (_manifest(_block(), names=()), "child_env.names"),
        (_manifest(_block(), names=("OTHER",)), "child_env.names"),
        ({"evidence": {"run_date": _block()}}, "child_env.names"),
        (
            {"evidence": {"run_date": _block()}, "child_env": {"names": _NAME}},
            "child_env.names",
        ),
    ],
)
def test_a_malformed_block_is_refused_naming_its_key(manifest, names):
    with pytest.raises(run_date.RunDateError) as caught:
        run_date.policy(manifest)
    assert names in str(caught.value), str(caught.value)


@pytest.fixture
def fresh_defaults():
    """A fresh process's announced set: no default line written yet."""
    config_loader._ANNOUNCED.clear()
    yield
    config_loader._ANNOUNCED.clear()


def test_an_absent_or_null_block_is_the_declared_default_and_says_so(
    capsys, fresh_defaults
):
    """`evidence.run_date` is a scripts/config_loader.py KEYS row whose default
    is null, the channel off: an absent block takes it and writes the one
    default line, and an explicit null is that same declared off."""
    assert run_date.policy({"evidence": {"dir": ".evidence"}}) is None
    err = capsys.readouterr().err
    assert "[using default] evidence.run_date = null" in err, err
    assert run_date.policy(_manifest(None)) is None
    assert run_date.policy(_manifest(_block())) == _policy()
    assert capsys.readouterr().err == ""


def test_a_missing_allowlist_names_the_loader_line_and_the_key(capsys):
    with pytest.raises(run_date.RunDateConfigError) as caught:
        run_date.policy({"evidence": {"run_date": _block()}})
    message = str(caught.value)
    assert "[not set] child_env" in message and "child_env.names" in message
    assert "[not set] child_env" in capsys.readouterr().err


def test_load_refuses_a_key_written_twice(tmp_path):
    """load reads through scripts/config_loader.py `read`, so a key written
    twice is refused naming it, not decided by whichever came last."""
    (tmp_path / "config").mkdir()
    text = json.dumps(_manifest(_block()))
    (tmp_path / "config" / "project.json").write_text(
        text[:-1] + ', "evidence": {}}', encoding="utf-8"
    )
    with pytest.raises(run_date.RunDateConfigError) as caught:
        run_date.load(str(tmp_path))
    assert '"evidence" appears twice' in str(caught.value), str(caught.value)
    assert "config/project.json" in caught.value.remedy, caught.value.remedy


def test_a_variable_the_allowlist_would_drop_names_both_keys():
    """A run date no child receives would switch the fix off without a word."""
    with pytest.raises(run_date.RunDateError) as caught:
        run_date.policy(_manifest(_block(), names=("PATH",)))
    message = str(caught.value)
    assert "evidence.run_date.env" in message and "child_env.names" in message
    assert _NAME in message


def test_a_config_fault_is_its_own_error_and_says_how_to_fix_the_config():
    """A fault in the config is answered by editing the config, not by
    choosing another date, so it carries the next step a caller reports."""
    with pytest.raises(run_date.RunDateConfigError) as caught:
        run_date.policy(_manifest(_block(), names=("PATH",)))
    remedy = caught.value.remedy
    assert "child_env.names" in remedy and _NAME in remedy, remedy
    assert "evidence.run_date" in remedy, remedy
    assert "--today" not in remedy, remedy
    with pytest.raises(run_date.RunDateConfigError) as caught:
        run_date.policy(_manifest(_block(max_age_days=-1)))
    assert "evidence.run_date" in caught.value.remedy, caught.value.remedy


def test_a_date_a_caller_supplies_is_not_a_config_fault():
    with pytest.raises(run_date.RunDateError) as caught:
        run_date.checked("not-a-date", _policy(), _CLOCK)
    assert not isinstance(caught.value, run_date.RunDateConfigError)


def test_load_reads_the_manifest_and_an_absent_one_is_off(tmp_path):
    assert run_date.load(str(tmp_path)) is None
    (tmp_path / "config").mkdir()
    path = tmp_path / "config" / "project.json"
    path.write_text(json.dumps(_manifest(_block())), encoding="utf-8")
    assert run_date.load(str(tmp_path)) == _policy()
    path.write_text("{ not json", encoding="utf-8")
    with pytest.raises(run_date.RunDateError) as caught:
        run_date.load(str(tmp_path))
    assert "config/project.json" in str(caught.value)


def test_a_manifest_an_update_left_conflicted_is_named_as_that_conflict(tmp_path):
    """A conflicted manifest is refused as the conflict it is, with the hunk's
    line, never as the JSON error the markers cause."""
    (tmp_path / "config").mkdir()
    path = tmp_path / "config" / "project.json"
    text = json.dumps(_manifest(_block()), indent=2).split("\n")
    hunk = ["<" * 7 + " ours", "=" * 7, ">" * 7 + " theirs"]
    path.write_text("\n".join(text[:2] + hunk + text[2:]), encoding="utf-8")
    with pytest.raises(run_date.RunDateError) as caught:
        run_date.load(str(tmp_path))
    message = str(caught.value)
    assert "merge-conflict hunk at line 3" in message, message
    assert "Expecting" not in message, message


def test_the_block_this_manifest_ships_parses_and_its_variable_is_allowlisted():
    # Runs in keel and in every generated project; that the rendered block
    # equals keel's is held by tests/integration/test_copier_generation.py.
    manifest = json.loads((_ROOT / "config" / "project.json").read_text("utf-8"))
    shipped = run_date.load(str(_ROOT))
    assert shipped is not None, "config/project.json ships no evidence.run_date"
    assert shipped.env == manifest["evidence"]["run_date"]["env"]
    assert shipped.max_age_days == manifest["evidence"]["run_date"]["max_age_days"]
    assert shipped.env in manifest["child_env"]["names"]


def test_the_public_surface_is_declared():
    assert sorted(run_date.__all__) == [
        "RunDateConfigError",
        "RunDateError",
        "RunDatePolicy",
        "checked",
        "for_run",
        "git_dates",
        "load",
        "policy",
        "today",
    ]
    assert issubclass(run_date.RunDateError, ValueError)
    assert run_date.PROJECT_READS == ("config/project.json",)
