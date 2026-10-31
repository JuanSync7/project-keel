"""
title: Unit — scripts hide configured text that holds an @
kind: tests
layer: n/a
summary: No message a script under scripts/, models/ or tests/isolation_guard.py, or the evals config, builds from configured text shows that text when it holds an `@`, at any depth: a value, a list member, a nested member, a key name, a path segment or a piece of a joined value, and an exception's own text that embeds it. Each row plants a sentinel in one position (keel's own config served in memory, or a variable set for the test; the tree untouched), runs the one reader that turns it into a message, and asserts the reader still refuses, the sentinel never shows and the line says it is hidden; the rows run over script families and mutation kinds. Beside them, a joined line still shows its harmless members and a value of the wrong type still reads as that type. In a generated project a row that plants into a block keel's own config has and the project's lacks is skipped naming the block.
"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import config_loader  # noqa: E402
import exit_code_table  # noqa: E402
import gate_evidence  # noqa: E402
import git_tree  # noqa: E402
import install_scanner  # noqa: E402
import launch  # noqa: E402
import run_date  # noqa: E402
import run_evals  # noqa: E402
import scan_secrets  # noqa: E402
import shell_gate  # noqa: E402
from evals import ConfigError, parse_config, run_live  # noqa: E402
from models import openai_compatible  # noqa: E402

pytestmark = pytest.mark.unit

# Not credential-shaped: the `@` alone is what the rule keys on.
_STEM = "SENTINEL"
_AT = "tok-SENTINEL@h.invalid"
_HIDDEN = "<hidden: it holds an @>"


def _load(relpath="config/project.json"):
    with open(_ROOT / relpath, encoding="utf-8") as fh:
        return json.load(fh)


def _node(doc, path):
    for seg in path:
        doc = doc[seg]
    return doc


def _mutate(doc, path, kind, value=_AT):
    """One planted fault: V sets the value at *path*, K renames its last key,
    A adds a key to the object at *path*, M appends a member to the list at
    *path*, D appends a nested list holding the member, N replaces the value
    with a nested object, P inserts the value as a path segment, S joins it
    to the value with separators."""
    if kind == "V":
        _node(doc, path[:-1])[path[-1]] = value
    elif kind == "K":
        parent = _node(doc, path[:-1])
        items = list(parent.items())
        parent.clear()
        for k, v in items:
            parent[value if k == path[-1] else k] = v
    elif kind == "A":
        _node(doc, path)[value] = "x"
    elif kind == "M":
        _node(doc, path).append(value)
    elif kind == "D":
        _node(doc, path).append([value])
    elif kind == "N":
        _node(doc, path[:-1])[path[-1]] = {value: [value]}
    elif kind == "P":
        parent = _node(doc, path[:-1])
        parent[path[-1]] = value + "/" + parent[path[-1]]
    elif kind == "S":
        parent = _node(doc, path[:-1])
        parent[path[-1]] = parent[path[-1]] + "," + value + ".x"
    else:
        raise ValueError(kind)


def _planted(path, kind, value=_AT):
    """keel's config/project.json with one fault planted; in a generated
    project a block it lacks skips the row, in the template it fails."""
    doc = _load()
    try:
        _mutate(doc, path, kind, value)
    except KeyError as missing:
        if (_ROOT / "copier.yml").is_file():
            raise
        pytest.skip("this project's config has no %s: a block keel's own has" % missing)
    return doc


def _hides(text, *neighbours):
    """The sentinel never shows, the line says it is hidden, and each harmless
    *neighbour* on the same line still shows."""
    assert text.strip(), "the reader refused with no message"
    assert _STEM not in text, text
    assert _HIDDEN in text, text
    for shown in neighbours:
        assert shown in text, (shown, text)


# --- scripts/launch.py -----------------------------------------------------

_L = ("launcher",)
_SLURM = _L + ("farm", "adapters", "slurm")
_LAUNCH_ROWS = [
    ("cpus-value", _L + ("default_size", "cpus"), "V", ()),
    ("long-script-size", _L + ("long_scripts", "make verify", "minutes"), "V", ()),
    ("unknown-top-key", _L, "A", ("launcher.",)),
    ("unknown-size-key", _L + ("default_size",), "A", ("launcher.default_size.",)),
    ("renamed-key", _L + ("_comment",), "K", ("launcher.",)),
    ("credentials-entry", _L + ("credentials",), "A", ("launcher.credentials.",)),
    ("long-scripts-entry", _L + ("long_scripts",), "A", ("launcher.long_scripts.",)),
    ("farm-adapter-value", _L + ("farm", "adapter"), "V", ("none", "slurm")),
    ("farm-adapter-segment", _L + ("farm", "adapter"), "P", ()),
    ("farm-adapter-joined", _L + ("farm", "adapter"), "S", ()),
    ("adapter-name", _L + ("farm", "adapters"), "A", ("launcher.farm.adapters.",)),
    ("adapter-kind", _SLURM + ("kind",), "V", ("launcher.farm.adapters.slurm.kind",)),
    ("env-name", _SLURM + ("env",), "A", ("launcher.farm.adapters.slurm.env.",)),
    ("env-template", _SLURM + ("env", "SLURM_EXIT_ERROR"), "V", ()),
    ("submit-word", _SLURM + ("submit",), "D", ("submit[7]",)),
    ("submit-template", _SLURM + ("submit", 0), "S", ()),
    ("inside-env-value", _SLURM + ("inside_env",), "V", ()),
    ("inside-env-member", _SLURM + ("inside_env",), "M", ("'SLURM_JOB_ID'",)),
    ("inside-env-nested", _SLURM + ("inside_env",), "D", ("'SLURM_JOB_ID'",)),
    ("inside-env-object", _SLURM + ("inside_env",), "N", ()),
    ("status", _SLURM + ("farm_error_status",), "V", ()),
    ("load-per-cpu", _L + ("spare", "max_load_per_cpu"), "V", ()),
    ("state-path", _L + ("own_hosts_file",), "P", ()),
]


@pytest.mark.parametrize(
    "path, kind, neighbours",
    [r[1:] for r in _LAUNCH_ROWS],
    ids=[r[0] for r in _LAUNCH_ROWS],
)
def test_launch_hides_configured_text_holding_an_at(path, kind, neighbours):
    value = _AT
    if kind == "V" and path[-1] == "own_hosts_file":
        value = "/" + _AT
    if path[-1:] == (0,) or path[-1] == "SLURM_EXIT_ERROR":
        # A template refusal: a placeholder outside the closed set.
        value = "{" + _AT + "}"
    manifest = _planted(path, kind, value)
    if path[-1] == "SLURM_EXIT_ERROR":
        _node(manifest, path[:-1])[path[-1]] = value
    if path[-1:] == (0,):
        _node(manifest, path[:-1])[0] = value
    if path[-1] == "own_hosts_file":
        _node(manifest, path[:-1])[path[-1]] = "/" + _AT
    with pytest.raises(launch.LauncherConfigError) as refused:
        launch.load_launcher_config(manifest)
    _hides(str(refused.value), *neighbours)


def test_launch_shows_a_value_of_the_wrong_type_as_itself():
    manifest = _planted(_L + ("default_size", "cpus"), "V", [True, "a"])
    with pytest.raises(launch.LauncherConfigError) as refused:
        launch.load_launcher_config(manifest)
    assert "is [true, 'a'], not a whole number" in str(refused.value)


def test_launch_hides_a_state_path_and_a_credential_name_holding_an_at(
    monkeypatch, capsys
):
    class Cfg:
        durations_file = ".launch/" + _AT
        own_hosts_file = "config/own-hosts.local.json"

    # Both paths reported as linked: the refusal names each configured path.
    monkeypatch.setattr(launch.git_tree, "through_symlink", lambda _root, paths: paths)
    found = launch._unsafe_state(str(_ROOT), Cfg())
    _hides(found[0], "config/own-hosts.local.json")
    launch._stopped(("credential", ["LC_" + _AT, "OTHER_NAME"]), ["make"], False, None)
    _hides(capsys.readouterr().err, "OTHER_NAME")


# --- evals config, evals live run, scripts/run_evals.py ---------------------

_E = ("evals",)


def _schema(rel):
    """A read_schema that reads the real schema, so only the planted fault
    refuses: a path holding the sentinel fails as a missing file would, with
    the path in its text."""
    if _STEM in rel:
        raise OSError(2, "No such file or directory", rel)
    return {"properties": {"schema_version": {"const": 1}}}


_EVALS_ROWS = [
    ("unknown-key", _E, "A", ("unknown key `evals.",)),
    ("renamed-key", _E + ("_comment",), "K", ("unknown key `evals.",)),
    ("unknown-live-key", _E + ("live",), "A", ("unknown key `evals.live.",)),
    ("case-schema-value", _E + ("case_schema",), "V", ("`evals.case_schema`",)),
    ("case-schema-segment", _E + ("case_schema",), "P", ("unreadable",)),
    ("report-schema-joined", _E + ("report_schema",), "S", ("unreadable",)),
]


@pytest.mark.parametrize(
    "path, kind, neighbours",
    [r[1:] for r in _EVALS_ROWS],
    ids=[r[0] for r in _EVALS_ROWS],
)
def test_evals_config_hides_configured_text_holding_an_at(path, kind, neighbours):
    with pytest.raises(ConfigError) as refused:
        parse_config(_planted(path, kind), _schema)
    _hides(str(refused.value), *neighbours)


def test_evals_config_hides_a_schema_path_without_a_version():
    manifest = _planted(_E + ("case_schema",), "V")
    with pytest.raises(ConfigError) as refused:
        parse_config(manifest, lambda _rel: {})
    _hides(str(refused.value), "must be a positive integer")


@pytest.mark.parametrize("error", [KeyError, TypeError], ids=["unknown", "misfit"])
def test_evals_live_run_hides_a_model_name_holding_an_at(error):
    manifest = _planted(_E + ("live", "model"), "V")
    cfg = parse_config(manifest, _schema)

    def factory(model, **_options):
        raise error(model)

    with pytest.raises(ConfigError) as refused:
        run_live([], cfg, backend_factory=factory, secrets=())
    _hides(str(refused.value), "`evals.live.model")


def _report_dir_cfg():
    return parse_config(_planted(_E + ("report_dir",), "P"), _schema)


def test_run_evals_hides_a_report_dir_reached_through_a_symlink(monkeypatch, capsys):
    cfg = _report_dir_cfg()
    monkeypatch.setattr(run_evals, "load_config", lambda _root: cfg)
    monkeypatch.setattr(git_tree, "through_symlink", lambda _root, paths: paths)
    run_evals.main(["--root", str(_ROOT)])
    _hides(capsys.readouterr().err, "evals.report_dir")
    run_evals._remove_stale(str(_ROOT), cfg.report_dir, "live")
    _hides(capsys.readouterr().err, "evals.report_dir")


@pytest.mark.parametrize("answer", ["loose", "git-failed"])
def test_run_evals_hides_a_report_dir_git_would_not_ignore(monkeypatch, capsys, answer):
    cfg = _report_dir_cfg()
    monkeypatch.setattr(run_evals, "load_config", lambda _root: cfg)
    monkeypatch.setattr(git_tree, "through_symlink", lambda _root, _paths: [])

    def unignored(_root, paths):
        if answer == "loose":
            return list(paths)
        raise git_tree.GitFailedError(128, "fatal: bad path %s" % paths[0])

    monkeypatch.setattr(run_evals, "_unignored", unignored)
    run_evals.main(["--root", str(_ROOT)])
    _hides(capsys.readouterr().err, "evals.report_dir")
    run_evals._remove_stale(str(_ROOT), cfg.report_dir, "replay")
    if answer == "git-failed":
        _hides(capsys.readouterr().err, "evals.report_dir")


# --- scripts/exit_code_table.py ---------------------------------------------

_D = ("doc_drift",)
_TABLE_ROWS = [
    ("guide-value", _D + ("limits_guide",), "V", ("cannot read the guide",)),
    ("guide-segment", _D + ("limits_guide",), "P", ("cannot read the guide",)),
    ("guide-joined", _D + ("limits_guide",), "S", ("cannot read the guide",)),
    ("target-value", _D + ("gate_target",), "V", ("no such target",)),
    ("target-joined", _D + ("gate_target",), "S", ("no such target",)),
]


@pytest.mark.parametrize(
    "path, kind, neighbours",
    [r[1:] for r in _TABLE_ROWS],
    ids=[r[0] for r in _TABLE_ROWS],
)
def test_exit_code_table_hides_configured_text_holding_an_at(
    monkeypatch, capsys, path, kind, neighbours
):
    manifest = _planted(path, kind)
    monkeypatch.setattr(config_loader, "read", lambda _root: manifest)
    with pytest.raises(exit_code_table.TableError) as refused:
        exit_code_table.wanted_text(str(_ROOT))
    _hides(str(refused.value), *neighbours)
    exit_code_table.main(["--check"], root=_ROOT)
    _hides(capsys.readouterr().err, *neighbours)


_GUIDE = "docs/" + _AT + "/limits.md"
_REGION = "%s\n%%s\n%s\n" % (exit_code_table.BEGIN, exit_code_table.END)


def test_exit_code_table_hides_the_guide_in_every_line_that_names_it(
    monkeypatch, capsys
):
    with pytest.raises(exit_code_table.TableError) as refused:
        exit_code_table.split_region("no markers", _GUIDE)
    _hides(str(refused.value), "exactly one")
    monkeypatch.setattr(git_tree, "through_symlink", lambda _root, paths: paths)
    monkeypatch.setattr(
        config_loader,
        "read",
        lambda _root: _planted(_D + ("limits_guide",), "V", _GUIDE),
    )
    with pytest.raises(exit_code_table.TableError) as refused:
        exit_code_table.wanted_text(str(_ROOT))
    _hides(str(refused.value), "symlink")
    now = {"text": _REGION % "old"}
    monkeypatch.setattr(
        exit_code_table,
        "wanted_text",
        lambda _root: (_GUIDE, now["text"], _REGION % "new"),
    )
    for finding in exit_code_table.table_findings(_ROOT):
        _hides(finding, "no table with the columns")
    exit_code_table.main(["--check"], root=_ROOT)
    _hides(capsys.readouterr().err, "the exit-code table is stale")

    def unwritable(_root, guide, _text):
        raise OSError(13, "Permission denied", guide)

    monkeypatch.setattr(exit_code_table, "_write", unwritable)
    exit_code_table.main([], root=_ROOT)
    _hides(capsys.readouterr().err, "cannot write the guide")
    monkeypatch.setattr(exit_code_table, "_write", lambda *_args: None)
    exit_code_table.main([], root=_ROOT)
    _hides(capsys.readouterr().out, "wrote the exit-code table")
    now["text"] = _REGION % "new"
    exit_code_table.main(["--check"], root=_ROOT)
    _hides(capsys.readouterr().out, "up to date")
    exit_code_table.main([], root=_ROOT)
    _hides(capsys.readouterr().out, "unchanged")


# --- scripts/gate_evidence.py -----------------------------------------------

_EV = ("evidence",)
_SCHEMA_ROWS = [
    ("schema-value", _EV + ("schema",), "V", ("evidence.schema",)),
    ("schema-segment", _EV + ("schema",), "P", ("not a readable JSON file",)),
    ("schema-joined", _EV + ("schema",), "S", ("not a readable JSON file",)),
]


@pytest.mark.parametrize(
    "path, kind, neighbours",
    [r[1:] for r in _SCHEMA_ROWS],
    ids=[r[0] for r in _SCHEMA_ROWS],
)
def test_gate_evidence_hides_a_schema_path_holding_an_at(
    monkeypatch, path, kind, neighbours
):
    manifest = _planted(path, kind)
    monkeypatch.setattr(config_loader, "read", lambda _root: manifest)
    with pytest.raises(gate_evidence.EvidenceSchemaError) as refused:
        gate_evidence.load_policy(str(_ROOT))
    _hides(str(refused.value), *neighbours)


def test_gate_evidence_hides_a_schema_path_without_a_version(monkeypatch):
    manifest = _planted(_EV + ("schema",), "V", "config/" + _AT)
    monkeypatch.setattr(config_loader, "read", lambda _root: manifest)
    real_open = open

    def opened(path, *args, **kwargs):
        if _STEM in str(path):
            return real_open(_ROOT / "config" / "project.json", *args, **kwargs)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", opened)
    with pytest.raises(gate_evidence.EvidenceSchemaError) as refused:
        gate_evidence.load_policy(str(_ROOT))
    _hides(str(refused.value), "schema_version.const")


@pytest.fixture
def evidence_dir(monkeypatch):
    """gate_evidence run over keel's config with `evidence.dir` holding the
    sentinel as a path segment, no make flags and no goal run."""
    manifest = _planted(_EV + ("dir",), "P")
    monkeypatch.setattr(config_loader, "read", lambda _root: manifest)
    monkeypatch.delenv("MAKEFLAGS", raising=False)
    monkeypatch.setattr(git_tree, "through_symlink", lambda _root, _paths: [])
    monkeypatch.setattr(gate_evidence, "_unignored", lambda _root, _paths: [])
    monkeypatch.setattr(gate_evidence, "_source", lambda _root: (None, {}))
    return lambda: gate_evidence.main(
        ["--gate", "probe", "--", "make", "check"], runner=None
    )


def test_gate_evidence_hides_an_evidence_dir_refused_before_any_goal(
    monkeypatch, capsys, evidence_dir
):
    monkeypatch.setattr(git_tree, "through_symlink", lambda _root, paths: paths)
    evidence_dir()
    _hides(capsys.readouterr().err, "evidence.dir")
    monkeypatch.setattr(git_tree, "through_symlink", lambda _root, _paths: [])
    monkeypatch.setattr(gate_evidence, "_unignored", lambda _root, paths: paths)
    evidence_dir()
    _hides(capsys.readouterr().err, "git would list", "to .gitignore")

    def failed(_root, paths):
        raise git_tree.GitFailedError(128, "fatal: bad path %s" % paths[0])

    monkeypatch.setattr(gate_evidence, "_unignored", failed)
    evidence_dir()
    _hides(capsys.readouterr().err, "git could not say")


def test_gate_evidence_hides_an_evidence_dir_in_a_red_record_line(
    monkeypatch, capsys, evidence_dir
):
    monkeypatch.setattr(gate_evidence, "write_record", lambda *_args: None)
    monkeypatch.setattr(gate_evidence, "run_goals", lambda *_a, **_k: [])
    monkeypatch.setattr(gate_evidence, "check_findings", lambda _root: [])
    monkeypatch.setattr(gate_evidence, "_changed", lambda _root, _before: None)
    evidence_dir()
    _hides(capsys.readouterr().err, "/probe.json is red: ", "/probe.json (")
    for raised in (KeyboardInterrupt, RuntimeError):

        def broken(*_args, raised=raised):
            raise raised()

        monkeypatch.setattr(gate_evidence, "write_record", broken)
        evidence_dir()
        _hides(capsys.readouterr().err, "/probe.json")


# --- scripts/shell_gate.py, scan_secrets.py, install_scanner.py -------------

_SH = ("shell",)


@pytest.mark.parametrize("role", ["linter", "formatter", "test_runner"])
def test_shell_gate_hides_a_tool_name_holding_an_at(monkeypatch, capsys, role):
    manifest = _planted(_SH + (role,), "V")
    monkeypatch.setattr(config_loader, "read", lambda _root: manifest)
    shell_gate.main(["lint"], root=_ROOT)
    _hides(capsys.readouterr().err, "shell.%s is" % role)


def test_shell_gate_hides_a_reason_and_an_excluded_path_holding_an_at(
    monkeypatch, capsys
):
    manifest = _planted(_SH + ("no_scripts",), "V")
    monkeypatch.setattr(config_loader, "read", lambda _root: manifest)
    monkeypatch.setattr(shell_gate, "classify", lambda _root, _cfg: ([], [], []))
    shell_gate.main(["lint"], root=_ROOT)
    _hides(capsys.readouterr().out, "shell.no_scripts says why")
    manifest = _planted(_SH + ("excluded_paths",), "A")
    _node(manifest, _SH + ("excluded_paths",))["vendor/run.sh"] = "vendored"
    monkeypatch.setattr(
        shell_gate,
        "classify",
        lambda _root, cfg: ([], [], sorted(cfg["excluded_paths"])),
    )
    shell_gate.main(["lint"], root=_ROOT)
    _hides(capsys.readouterr().err, "vendor/run.sh")


_SCANNER = ("secrets", "scanner")


def _scanner(monkeypatch, path, kind, value=_AT):
    manifest = _planted(_SCANNER + path, kind, value)
    monkeypatch.setattr(config_loader, "read", lambda _root: manifest)
    return scan_secrets.settings(str(_ROOT))


def test_scan_secrets_hides_a_scanner_name_holding_an_at():
    why = scan_secrets.other_adapter({"name": "x/" + _AT})
    _hides(why, "secrets.scanner.name is '", "adapts gitleaks only")


def test_scan_secrets_hides_a_record_and_what_it_names_holding_an_at(tmp_path):
    cfg = {"record_file": "rec/" + _AT, "name": "gitleaks", "rev": "8"}
    _hides(scan_secrets._recorded(str(tmp_path), cfg)[1], "no scanner record at")
    (tmp_path / "rec.json").write_text('{"name": "gitleaks"}', encoding="utf-8")
    cfg = {"record_file": "rec.json", "name": "gitleaks", "rev": _AT}
    _hides(scan_secrets._recorded(str(tmp_path), cfg)[1], "rec.json")
    record = '{"name": "gitleaks", "rev": "%s", "path": "/nowhere/%s"}' % (_AT, _AT)
    (tmp_path / "rec.json").write_text(record, encoding="utf-8")
    _hides(scan_secrets._recorded(str(tmp_path), cfg)[1], "is gone")
    (tmp_path / "rec.json").write_text("{", encoding="utf-8")
    cfg["record_file"] = "rec.json/" + _AT
    _hides(scan_secrets._recorded(str(tmp_path), cfg)[1], "cannot be read")


@pytest.fixture
def history_scan(monkeypatch):
    """scan_secrets' history scan with git and the scanner stood in for."""
    monkeypatch.setattr(scan_secrets, "_refused", lambda _root, _cfg: [])
    monkeypatch.setattr(scan_secrets, "_recorded", lambda _r, _c: ("/bin/x", None))
    monkeypatch.setattr(git_tree, "head_commit", lambda _root: "c0ffee")
    monkeypatch.setattr(git_tree, "log_commits", lambda _root, _opts: ["c0ffee"])
    monkeypatch.setattr(scan_secrets, "_run_scanner", lambda *_args: (0, "", ""))
    monkeypatch.setattr(scan_secrets, "_verdict", lambda *_args: ([], None))
    return lambda cfg: scan_secrets._scan(str(_ROOT), cfg, scan_secrets._HISTORY)


def test_scan_secrets_hides_a_log_option_an_exclusion_and_a_rev_holding_an_at(
    monkeypatch, capsys, history_scan
):
    cfg = _scanner(monkeypatch, ("history_log_opts",), "M")
    monkeypatch.setattr(git_tree, "log_commits", lambda _root, _opts: [])
    history_scan(cfg)
    _hides(capsys.readouterr().err, "`git log --all ")
    monkeypatch.setattr(git_tree, "log_commits", lambda _root, _opts: ["c0ffee"])

    def unrunnable(_root, _cfg, program, _staged):
        raise OSError(2, "No such file or directory", program)

    monkeypatch.setattr(scan_secrets, "_run_scanner", unrunnable)
    monkeypatch.setattr(scan_secrets, "_recorded", lambda _r, _c: ("/" + _AT, None))
    history_scan(cfg)
    _hides(capsys.readouterr().err, "cannot be run", "`git log --all ")
    monkeypatch.setattr(scan_secrets, "_run_scanner", lambda *_args: (0, "", ""))
    cfg = _scanner(
        monkeypatch, ("exclusions",), "V", {"docs/" + _AT: {"rule-id": "a sample"}}
    )
    history_scan(cfg)
    _hides(capsys.readouterr().err, "did not use")
    cfg = _scanner(monkeypatch, ("rev",), "V", "8.0." + _AT)
    history_scan(cfg)
    _hides(capsys.readouterr().out, "scan clean (gitleaks ")
    monkeypatch.setattr(scan_secrets, "_recorded", lambda _r, _c: (None, "absent"))
    history_scan(cfg)
    _hides(capsys.readouterr().err, "absent", "gitleaks ")


@pytest.fixture
def install(monkeypatch):
    """install_scanner's run over keel's scanner settings, nothing fetched."""
    cfg = scan_secrets.settings(str(_ROOT))
    inst = install_scanner._settings(str(_ROOT))
    monkeypatch.setattr(scan_secrets, "record_is_ignored", lambda _root, _cfg: True)
    monkeypatch.setattr(install_scanner, "_installed", lambda *_args: True)
    monkeypatch.setattr(scan_secrets, "write_record", lambda *_args: False)
    return cfg, inst, lambda: install_scanner._run(str(_ROOT), cfg, inst)


def test_install_scanner_hides_configured_text_holding_an_at(
    monkeypatch, capsys, install
):
    cfg, inst, run = install
    key = install_scanner._platform_key()
    monkeypatch.setattr(install_scanner, "_platform_key", lambda: "none-" + key)
    inst["release_assets"] = dict(inst["release_assets"], **{_AT: {}})
    run()
    _hides(capsys.readouterr().err, "which lists", "linux-x86_64")
    monkeypatch.setattr(install_scanner, "_platform_key", lambda: key)
    inst["release_assets"] = {key: {"file": _AT, "sha256": "0" * 64}}
    inst["install_root"] = str(_ROOT / _AT)
    run()
    _hides(capsys.readouterr().err, "resolves inside the checkout")
    inst["install_root"] = "/nonexistent/keel-probe"
    monkeypatch.setattr(scan_secrets, "record_is_ignored", lambda _root, _cfg: False)
    cfg["record_file"] = ".secret-scan/" + _AT
    run()
    _hides(capsys.readouterr().err, "git would commit the scanner record")
    monkeypatch.setattr(scan_secrets, "record_is_ignored", lambda _root, _cfg: True)
    cfg["rev"] = _AT
    run()
    _hides(capsys.readouterr().out, "already installed", "gitleaks")


@pytest.mark.parametrize("fault", ["unfetched", "local", "mismatch"])
def test_install_scanner_hides_a_url_and_a_path_holding_an_at(
    monkeypatch, capsys, tmp_path, install, fault
):
    cfg, inst, run = install
    key = install_scanner._platform_key()
    inst["release_assets"] = {key: {"file": "v/" + _AT, "sha256": "0" * 64}}
    inst["install_root"] = str(tmp_path / "tools")
    monkeypatch.setattr(install_scanner, "_installed", lambda *_args: False)
    monkeypatch.setattr(install_scanner.tempfile, "tempdir", str(tmp_path))
    if fault == "unfetched":

        def fetched(url, _dest, _inst):
            raise install_scanner._Unfetched(OSError("cannot open %s" % url))

    elif fault == "local":

        def fetched(_url, dest, _inst):
            raise install_scanner._Local(dest, OSError("cannot write %s" % dest))

    else:

        def fetched(_url, _dest, _inst):
            return "f" * 64

    monkeypatch.setattr(install_scanner, "_fetch", fetched)
    run()
    _hides(capsys.readouterr().err)


# --- scripts/run_date.py ----------------------------------------------------


def test_run_date_hides_a_value_holding_an_at():
    policy = run_date.policy(_load())
    if policy is None:
        pytest.skip("this project's config has no evidence.run_date")
    with pytest.raises(run_date.RunDateError) as refused:
        # Short enough to be quoted rather than measured.
        run_date.today({policy.env: _STEM + "@h"}, policy)
    _hides(str(refused.value), policy.env)


# --- models/openai_compatible.py --------------------------------------------


@pytest.mark.parametrize(
    "key_env, declared, neighbours",
    [
        (_AT, ("KEY_A",), ("KEY_A",)),
        ("KEY_Z", ("KEY_A", _AT), ("'KEY_Z'", "KEY_A, ")),
    ],
    ids=["undeclared-name", "declared-member"],
)
def test_openai_compatible_hides_a_credential_name_holding_an_at(
    key_env, declared, neighbours
):
    with pytest.raises(ValueError) as refused:
        openai_compatible._checked_key_env("openai-compatible", key_env, declared)
    _hides(str(refused.value), *neighbours)
