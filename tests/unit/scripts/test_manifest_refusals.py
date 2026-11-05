"""
title: Unit — refused manifests and actionable launcher errors
kind: tests
layer: n/a
summary: Empty, null and non-UTF-8 manifests stop the slice's readers as CONFIG with one stderr line before any work. A triggered event hook ends a conflict hunk as CONFIG too, never with exit 2, which a trigger may read as blocking its event. Imported readers raise, and launcher template errors require an explicit remedy that names the edit.
"""

import io
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts/jobs"))
sys.path.insert(0, str(_ROOT / "scripts/hooks"))

import config_loader  # noqa: E402
import declare_no_app  # noqa: E402
import exit_code_table  # noqa: E402
import launch  # noqa: E402
import long_scripts  # noqa: E402
import on_stop_doc_review  # noqa: E402
import on_stop_triage  # noqa: E402
import run_evals  # noqa: E402
import trace_requirements  # noqa: E402
from exit_codes import ExitCode  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "reader", [declare_no_app, launch, long_scripts, trace_requirements]
)
def test_an_absent_manifest_keeps_the_readers_previous_path(tmp_path, capsys, reader):
    argv = ["--root", str(tmp_path)]
    if reader is launch:
        argv += ["--", "true"]
    result = reader.main(argv)
    captured = capsys.readouterr()
    if reader is declare_no_app:
        assert result is ExitCode.SUCCESS
        assert captured.err == ""
    else:
        assert result is ExitCode.USAGE
        assert len(captured.err.splitlines()) == 1
        assert "config/project.json" in captured.err
    assert captured.out == ""


def test_an_absent_manifest_declares_no_frontend(tmp_path):
    if not (_ROOT / "scripts/jobs/export_showcase_static.py").is_file():
        pytest.skip("this project declined the showcase exporter")
    import export_showcase_static

    assert export_showcase_static._declared_frontend_public(str(tmp_path)) is None


@pytest.mark.parametrize("payload", [b"", b"null", b"\xff\xfe"])
@pytest.mark.parametrize(
    "reader",
    [
        exit_code_table,
        declare_no_app,
        launch,
        long_scripts,
        run_evals,
        trace_requirements,
    ],
)
def test_a_refused_manifest_is_one_config_line(tmp_path, capsys, reader, payload):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/project.json").write_bytes(payload)
    if reader is exit_code_table:
        result = reader.main([], root=str(tmp_path))
    else:
        argv = ["--root", str(tmp_path)]
        if reader is launch:
            argv += ["--", "true"]
        result = reader.main(argv)
    captured = capsys.readouterr()
    assert result is ExitCode.CONFIG
    assert len(captured.err.splitlines()) == 1
    assert "config/project.json" in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""


@pytest.mark.parametrize("template", ["{unknown}", "{cpus}", "{cpus"])
def test_render_requires_an_edit_that_clears_the_refusal(template):
    with pytest.raises(launch.LauncherConfigError) as caught:
        launch.render(template, {})
    assert "placeholder" in caught.value.fix
    assert caught.value.fix not in str(caught.value)


def test_launcher_errors_have_no_default_remedy():
    with pytest.raises(TypeError):
        launch.LauncherConfigError("problem")


def test_an_imported_reader_raises_without_reporting(tmp_path, capsys):
    if not (_ROOT / "scripts/jobs/export_showcase_static.py").is_file():
        pytest.skip("this project declined the showcase exporter")
    import export_showcase_static

    (tmp_path / "config").mkdir()
    (tmp_path / "config/project.json").write_bytes(b"null")
    with pytest.raises(config_loader.ConfigUnreadable):
        export_showcase_static._declared_frontend_public(str(tmp_path))
    assert capsys.readouterr().err == ""


def _hunk_refusal(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/project.json").write_text(
        "{\n"
        + "<" * 7
        + ' ours\n"a": 1\n'
        + "=" * 7
        + '\n"a": 2\n'
        + ">" * 7
        + " theirs\n}\n",
        encoding="utf-8",
    )
    with pytest.raises(config_loader.ConfigUnreadable) as caught:
        config_loader.read(str(tmp_path))
    assert config_loader.is_conflict(caught.value)
    return caught.value


@pytest.mark.parametrize(
    "hook, agent", [(on_stop_doc_review, "review"), (on_stop_triage, "triage")]
)
def test_a_triggered_hook_ends_a_conflict_hunk_as_config_not_2(
    tmp_path, capsys, monkeypatch, hook, agent
):
    refusal = _hunk_refusal(tmp_path)

    def refused(*_args, **_kwargs):
        raise refusal

    monkeypatch.setattr(hook, agent, refused)
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    result = hook.main(["-"])
    err = capsys.readouterr().err
    assert result is ExitCode.CONFIG
    assert len(err.splitlines()) == 1
    assert "config/project.json" in err and "hunk" in err
