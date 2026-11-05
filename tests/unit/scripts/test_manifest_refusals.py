"""
title: Unit — refused manifests and actionable launcher errors
kind: tests
layer: n/a
summary: AST discovery holds every manifest-refusal reporter to cases for empty, null, non-UTF-8, duplicate-key and conflicted manifests: one stderr line naming the file, unchanged bytes, and exit 14 or 2 for a hunk (14 for triggered Stop hooks). Separate job handlers are exercised, absent manifests keep their previous paths, imported readers raise, and launcher errors require an explicit remedy.
"""

import ast
import importlib
import io
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts/jobs"))
sys.path.insert(0, str(_ROOT / "scripts/hooks"))

import config_loader  # noqa: E402
import declare_no_app  # noqa: E402
import launch  # noqa: E402
import long_scripts  # noqa: E402
import on_stop_doc_review  # noqa: E402
import on_stop_triage  # noqa: E402
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


# Each row names the module whose refusal handler is exercised. The eval
# wrapper has no CLI: its public caller, run_evals, reports its refusal.
_READERS = (
    ("scripts/apply_refactor.py", "edits", ("--dry-run",)),
    ("scripts/audit_dependencies.py", "settings", ()),
    ("scripts/audit_project.py", "date", (".",)),
    ("scripts/canary.py", "settings", ()),
    ("scripts/cdmon_sync.py", "environment", ()),
    ("scripts/check_practices.py", "profiles", ()),
    ("scripts/check_toolchain.py", "settings", ("versions",)),
    ("scripts/check_venv.py", "settings", ()),
    ("scripts/child_exec.py", "environment", ("probe.sh",)),
    ("scripts/config_get.py", "value", ("tests.child_timeout_seconds",)),
    ("scripts/doc_review.py", "cap", ("--execute",)),
    ("scripts/doc_review.py", "agent", ()),
    ("scripts/exit_code_table.py", "policy", ()),
    ("scripts/gate_evidence.py", "policy", ("--gate", "probe", "--", "make", "lint")),
    ("scripts/hooks/on_stop_doc_review.py", "cap", ("--execute",)),
    ("scripts/hooks/on_stop_doc_review.py", "agent", ()),
    ("scripts/hooks/on_stop_triage.py", "cap", ("--execute",)),
    ("scripts/hooks/on_stop_triage.py", "agent", ()),
    ("scripts/install_scanner.py", "settings", ()),
    ("scripts/install_sources.py", "source", ("python_index",)),
    ("scripts/jobs/build_corpus.py", "build", ()),
    ("scripts/jobs/check_corpus.py", "build", ()),
    ("scripts/jobs/declare_no_app.py", "manifest", ()),
    ("scripts/jobs/export_showcase_static.py", "frontend", ()),
    ("scripts/jobs/export_showcase_static.py", "levels", ("--out-dir", "public")),
    ("scripts/jobs/finish_update.py", "environment", ("--dry-run",)),
    (
        "scripts/jobs/keep_edited_retired.py",
        "environment",
        ("--template", ".", "--from", "HEAD"),
    ),
    ("scripts/jobs/resolve_stamp_conflicts.py", "environment", ()),
    ("scripts/jobs/restamp_docs.py", "date", ()),
    ("scripts/jobs/restamp_docs.py", "check", ("--today", "2026-11-05", "--check")),
    ("scripts/jobs/restamp_docs.py", "worklist", ("--today", "2026-11-05")),
    ("scripts/jobs/review_docs.py", "date", ()),
    ("scripts/launch.py", "manifest", ("--root", ".", "--", "true")),
    ("scripts/long_scripts.py", "manifest", ("--root", ".")),
    ("scripts/query_corpus.py", "levels", ("what",)),
    ("scripts/record_gate_baseline.py", "policy", ()),
    ("scripts/record_gate_baseline.py", "timeout", ()),
    ("scripts/refactor_practice.py", "cap", ("x", "--execute")),
    ("scripts/refactor_practice.py", "agent", ("x",)),
    ("scripts/run_app.py", "manifest", ()),
    ("scripts/run_evals.py", "config", ("--root", ".")),
    ("evals/_config.py", "public-caller", ("--root", ".")),
    ("scripts/run_make_target.py", "limits", ("lint",)),
    ("scripts/scan_secrets.py", "settings", ("--staged",)),
    ("scripts/shell_gate.py", "settings", ("lint",)),
    ("scripts/trace_requirements.py", "policy", ("--root", ".")),
)
_HUNK = (
    "{\n"
    + "<" * 7
    + ' ours\n"a": 1\n'
    + "=" * 7
    + '\n"a": 2\n'
    + ">" * 7
    + " theirs\n}\n"
).encode("utf-8")
_REFUSALS = (
    pytest.param(b"", ExitCode.CONFIG, id="empty"),
    pytest.param(b"null", ExitCode.CONFIG, id="null"),
    pytest.param(b"\xff\xfe", ExitCode.CONFIG, id="non-utf8"),
    pytest.param(b'{"a": 1, "a": 2}', ExitCode.CONFIG, id="duplicate"),
    pytest.param(_HUNK, ExitCode.USAGE, id="hunk"),
)


def test_every_manifest_refusal_reporter_has_cases():
    found = set()
    for directory in ("scripts", "evals"):
        for path in (_ROOT / directory).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            if any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "config_loader"
                and node.func.attr in {"is_conflict", "refusal_cause"}
                for node in ast.walk(tree)
            ):
                found.add(path.relative_to(_ROOT).as_posix())
    assert found, "discovered zero manifest refusal reporters"
    covered = {module for module, _route, _argv in _READERS}
    assert not found - covered, "add refusal cases for: %s" % sorted(found - covered)


def _prepare_reader(tmp_path, monkeypatch, module, route):
    if not (_ROOT / module).is_file():
        pytest.skip("this generated project does not ship %s" % module)
    name = Path(module).stem
    reader = importlib.import_module(
        "run_evals" if module == "evals/_config.py" else name
    )
    import child_env
    import review_docs

    # Relocate checkout defaults, including the allowlist's file-derived root;
    # leave the loader and its real parsing/classification code intact.
    monkeypatch.chdir(tmp_path)
    for attr in ("ROOT", "_ROOT", "_REPO", "_DEFAULT_ROOT"):
        if hasattr(reader, attr):
            monkeypatch.setattr(reader, attr, str(tmp_path))
    if hasattr(reader, "_SCRIPTS"):
        monkeypatch.setattr(reader, "_SCRIPTS", str(tmp_path / "scripts"))
    monkeypatch.setattr(review_docs, "ROOT", str(tmp_path))
    monkeypatch.setattr(child_env, "__file__", str(tmp_path / "scripts/child_env.py"))
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    monkeypatch.setattr(
        sys, "stdin", io.StringIO('{"practice":"p","edits":[{"file":"README.md"}]}')
    )

    def read_at_agent_boundary(*_args, **_kwargs):
        return config_loader.read(str(tmp_path))

    if route == "agent":
        # No model runs: exercise the entry point's handler for a loader
        # refusal raised inside the imported agent, as the runtime would.
        agent = (
            "triage"
            if name == "on_stop_triage"
            else "refactor"
            if name == "refactor_practice"
            else "review"
        )
        monkeypatch.setattr(reader, agent, read_at_agent_boundary)
    if name == "cdmon_sync":
        # Pass the optional-tool checks so the environment read is reached.
        monkeypatch.setattr(reader.shutil, "which", lambda _name: "/unused/cdmon")
        config = tmp_path / reader.DEFAULT_CONFIG
        config.parent.mkdir(parents=True)
        config.write_text("# probe\n", encoding="utf-8")
    if name == "child_exec":
        (tmp_path / "probe.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    if name == "check_practices":
        (tmp_path / "config/practices.json").write_text("{}", encoding="utf-8")
    if name == "record_gate_baseline":
        (tmp_path / ".copier-answers.yml").write_text(
            "_commit: probe\n", encoding="utf-8"
        )
        if route == "timeout":
            # The timeout has its own handler after policy/baseline loading;
            # retain the real run_checks, which reads before spawning pytest.
            monkeypatch.setattr(
                reader.expiring_tier,
                "load_policy",
                lambda _root: SimpleNamespace(baseline="baseline.json"),
            )
            monkeypatch.setattr(
                reader.expiring_tier, "read_baseline", lambda *_args: {}
            )
    return reader


@pytest.mark.parametrize("payload, expected", _REFUSALS)
@pytest.mark.parametrize(
    "module, route, argv",
    [
        pytest.param(module, route, argv, id=module + ":" + route)
        for module, route, argv in _READERS
    ],
)
def test_a_refused_manifest_is_one_config_line(
    tmp_path, capsys, monkeypatch, module, route, argv, payload, expected
):
    (tmp_path / "config").mkdir()
    manifest = tmp_path / "config/project.json"
    manifest.write_bytes(payload)
    reader = _prepare_reader(tmp_path, monkeypatch, module, route)
    if module == "scripts/check_venv.py":
        result = reader.main(root=str(tmp_path))
    else:
        result = reader.main(list(argv))
    captured = capsys.readouterr()
    if module.startswith("scripts/hooks/") and "--execute" not in argv:
        expected = ExitCode.CONFIG
    assert result is expected
    assert len(captured.err.splitlines()) == 1
    assert "config/project.json" in captured.err
    assert "Traceback" not in captured.out + captured.err
    assert captured.out == ""
    assert manifest.read_bytes() == payload


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
