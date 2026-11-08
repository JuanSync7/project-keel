"""
title: Integration — verify refuses missing local installs before expensive goals
summary: Drives the real preflight recipe on isolated projects with one missing install at a time, proves later work never starts, and checks the fully installed and backend-only cases without running verify.
"""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import makefile_copy

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402
import config_loader  # noqa: E402

pytestmark = pytest.mark.integration


@pytest.fixture
def project(tmp_path):
    makefile_copy.copy_makefiles(tmp_path, _ROOT)
    shutil.copytree(_ROOT / "scripts", tmp_path / "scripts")
    (tmp_path / "config").mkdir()
    cfg = config_loader.read(str(_ROOT))
    cfg["venv"]["extras"] = ["dev"]
    cfg["transports"]["enabled"] = []
    cfg["shell"]["enabled"] = False
    cfg["layers"].setdefault("frontend", {}).setdefault("journey", {})[
        "browser_executable"
    ] = None
    (tmp_path / "config/project.json").write_text(json.dumps(cfg))
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "probe"\nrequires-python = ">=3.10"\ndependencies = ["packaging"]\n[project.optional-dependencies]\ndev=[]\n'
    )
    scanner = Path(shutil.which("true"))
    record = tmp_path / cfg["secrets"]["scanner"]["record_file"]
    record.parent.mkdir(parents=True)
    record.write_text(
        json.dumps(
            {
                "name": cfg["secrets"]["scanner"]["name"],
                "rev": cfg["secrets"]["scanner"]["rev"],
                "path": str(scanner),
                "sha256": hashlib.sha256(scanner.read_bytes()).hexdigest(),
            }
        )
    )
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for tool in ("npm", "shellcheck", "shfmt", "bats"):
        (bindir / tool).symlink_to(scanner)
    # Refusal cases need only tool presence; browser controls require real Node.
    (bindir / "node").symlink_to(shutil.which("node") or "/bin/sh")
    browser = tmp_path / "browser"
    browser.symlink_to(scanner)
    for name in ("one", "two"):
        app = tmp_path / "src/frontend" / name
        registry = app / "node_modules/playwright-core/lib"
        registry.mkdir(parents=True)
        (app / "node_modules/.package-lock.json").write_text("{}")
        (app / "package.json").write_text("{}")
        (app / "node_modules/playwright-core/package.json").write_text("{}")
        (registry / "coreBundle.js").write_text(
            "exports.registry = { registry: { findExecutable: name => {\n"
            'if (name !== "chromium-headless-shell") throw Error(name);\n'
            "return {executablePath: () => " + json.dumps(str(browser)) + "}; }}};\n"
        )
    with (tmp_path / "Makefile").open("a") as stream:
        stream.write("\nexpensive:\n\t@echo started > expensive-started\n")
    return tmp_path, cfg, record, bindir, browser


def _save(root, cfg):
    (root / "config/project.json").write_text(json.dumps(cfg))


def _run(project, *goals):
    root, _cfg, _record, bindir, _browser = project
    return subprocess.run(
        [
            shutil.which("make"),
            "--no-print-directory",
            *goals,
            "PY=" + sys.executable + " -B",
        ],
        cwd=root,
        env={"PATH": str(bindir), "HOME": str(root), "TMPDIR": str(root)},
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.parametrize(
    "target", ["preflight", "test-fe-unit", "test-fe-e2e", "fe-browsers"]
)
@pytest.mark.parametrize("app", ["one", "two"])
def test_incomplete_install_refuses_before_later_work(project, target, app):
    root, _cfg, _record, _bindir, _browser = project
    modules = root / "src/frontend" / app / "node_modules"
    (modules / ".package-lock.json").unlink()
    assert any(modules.iterdir())

    result = _run(project, target, "expensive")

    assert result.returncode == 2, result.stdout + result.stderr
    assert "src/frontend/" + app + "/" in result.stderr, result.stderr
    assert "install is missing or incomplete" in result.stderr, result.stderr
    assert "run 'make fe-install'" in result.stderr, result.stderr
    assert not (root / "expensive-started").exists()


@pytest.mark.parametrize(
    "stderr,expected,omitted",
    [
        (
            "\nnode:internal/modules/cjs/loader:1228\n"
            "  throw err;\n\nError: Cannot find module 'x'\n"
            "    at Function._resolveFilename (node:internal/modules/cjs/loader:1225:15)\n",
            "Error: Cannot find module 'x'",
            "node:internal/modules/cjs/loader:1228",
        ),
        (
            "\n \t\n  registry unavailable  \nsecond line must be omitted\n",
            "registry unavailable",
            "second line must be omitted",
        ),
        (
            "node:internal/modules/cjs/loader:1228\nerror: registry unavailable\n",
            "error: registry unavailable",
            "node:internal/modules/cjs/loader:1228",
        ),
        (
            "Error: " + "x" * 1000 + "TAIL_MUST_BE_OMITTED\n",
            ("Error: " + "x" * 1000)[:237] + "...",
            "TAIL_MUST_BE_OMITTED",
        ),
    ],
    ids=["loader-stack", "fallback", "lowercase-error", "bounded-error"],
)
def test_browser_probe_stderr_detail(project, stderr, expected, omitted, capsys):
    import preflight

    root, _cfg, _record, _bindir, _browser = project

    status = preflight._probe_refused(
        str(root / "src/frontend/one"), "one", stderr, 240
    )

    captured = capsys.readouterr()
    assert status == 2
    assert captured.out == ""
    assert len(captured.err.splitlines()) == 1
    assert expected + "): one;" in captured.err
    assert omitted not in captured.err
    assert "update the probe in scripts/preflight.py" in captured.err


@pytest.mark.parametrize("limit", ["timeout_seconds", "stderr_max_chars"])
def test_browser_probe_configured_limit(project, limit, monkeypatch, capsys):
    import preflight

    root, cfg, _record, bindir, _browser = project
    cfg["layers"]["frontend"]["browser_probe"][limit] = 37
    _save(root, cfg)
    real_run = subprocess.run
    calls = []

    def probe(command, **kwargs):
        if command[0] != "node":
            return real_run(command, **kwargs)
        calls.append(kwargs)
        if limit == "timeout_seconds":
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        return subprocess.CompletedProcess(command, 1, "", "Error: " + "x" * 1000)

    monkeypatch.setenv("PATH", str(bindir))
    monkeypatch.setattr(preflight.subprocess, "run", probe)
    status = preflight.main(argv=["src/frontend/one"], root=str(root))
    captured = capsys.readouterr()
    assert status == 2
    assert len(calls) == 1
    if limit == "timeout_seconds":
        assert calls[0]["timeout"] == 37
        assert "37 seconds" in captured.err
    else:
        detail = captured.err.split("; Error: ", 1)[1].split("): ", 1)[0]
        assert len("Error: " + detail) == 37
        assert "x" * 38 not in captured.err


@pytest.mark.parametrize("limit", ["timeout_seconds", "stderr_max_chars"])
def test_browser_probe_default_limit(project, limit, monkeypatch, capsys):
    import preflight

    root, cfg, _record, bindir, _browser = project
    browser_probe = cfg["layers"]["frontend"]["browser_probe"]
    del browser_probe[limit]
    _save(root, cfg)
    path = ("layers", "frontend", "browser_probe", limit)
    default = next(row.default for row in config_loader.KEYS if row.path == path)
    real_run = subprocess.run
    calls = []

    def probe(command, **kwargs):
        if command[0] != "node":
            return real_run(command, **kwargs)
        calls.append(kwargs)
        if limit == "timeout_seconds":
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        return subprocess.CompletedProcess(
            command, 1, "", "Error: " + "x" * (default * 2)
        )

    monkeypatch.setenv("PATH", str(bindir))
    monkeypatch.setattr(preflight.subprocess, "run", probe)

    status = preflight.main(argv=["src/frontend/one"], root=str(root))

    captured = capsys.readouterr()
    assert status == 2
    assert captured.out == ""
    assert len(calls) == 1
    key = ".".join(path)
    default_line = (
        "[using default] %s = %s  (not set; to change it, set %s in config/project.json)"
        % (key, json.dumps(default), key)
    )
    assert [
        line for line in captured.err.splitlines() if "[using default]" in line
    ] == [default_line]
    if limit == "timeout_seconds":
        assert calls[0]["timeout"] == default
        assert "%s seconds" % default in captured.err
    else:
        detail = captured.err.split("; Error: ", 1)[1].split("): ", 1)[0]
        assert len("Error: " + detail) == default
        assert detail.endswith("...")


@pytest.mark.parametrize("limit", ["timeout_seconds", "stderr_max_chars"])
@pytest.mark.parametrize("value", ["37", True, 0, -1, 1.5, None])
def test_browser_probe_wrong_limit_is_config(
    project, limit, value, monkeypatch, capsys
):
    import preflight

    root, cfg, _record, bindir, _browser = project
    cfg["layers"]["frontend"]["browser_probe"][limit] = value
    _save(root, cfg)
    monkeypatch.setenv("PATH", str(bindir))

    status = preflight.main(argv=["src/frontend/one"], root=str(root))

    captured = capsys.readouterr()
    assert status == 14
    assert "layers.frontend.browser_probe." + limit in captured.err
    assert "accepted:" in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.parametrize(
    "prefix,cause",
    [
        ("throw new Error(\n    ^\n", "Error: Cannot find module 'x'"),
        (
            "    at new NodeError (node:internal/errors:1:2)\n",
            "TypeError [ERR_TEST]: failed",
        ),
        ("throw new Error(\n    ^\n", "ERROR: registry unavailable"),
        # Holds `Error:` mid-line, so only the line-start anchor rejects it.
        (
            "Uncaught Error: thrown from a loader hook\n",
            "Error: Cannot find module 'x'",
        ),
    ],
    ids=["source-excerpt", "node-error-frame", "uppercase-error", "mid-line-error"],
)
def test_browser_probe_cause_beats_source(project, prefix, cause, capsys):
    import preflight

    root, _cfg, _record, _bindir, _browser = project
    status = preflight._probe_refused(
        str(root / "src/frontend/one"), "one", prefix + cause, 240
    )
    captured = capsys.readouterr()
    assert status == 2
    assert cause + "): one;" in captured.err
    assert prefix.splitlines()[0].strip() not in captured.err


@pytest.mark.parametrize("length,marked", [(240, False), (241, True)])
def test_browser_probe_cut_mark(project, length, marked, capsys):
    import preflight

    root, _cfg, _record, _bindir, _browser = project
    status = preflight._probe_refused(
        str(root / "src/frontend/one"), "one", "x" * length, 240
    )
    captured = capsys.readouterr()
    assert status == 2
    detail = captured.err.split("; ", 1)[1].split("): one;", 1)[0]
    assert len(detail) == 240
    assert detail.endswith("...") is marked


@pytest.mark.parametrize(
    "bound,expected", [(1, "."), (2, ".."), (3, "..."), (7, "Erro...")]
)
def test_browser_probe_small_bound(project, bound, expected, capsys):
    import preflight

    root, _cfg, _record, _bindir, _browser = project
    status = preflight._probe_refused(
        str(root / "src/frontend/one"), "one", "Error: unavailable", bound
    )
    captured = capsys.readouterr()
    assert status == 2
    assert "; " + expected + "): one;" in captured.err


@pytest.mark.parametrize(
    "package,version",
    [
        ('{"version": "9.8.7"}', "installed Playwright version 9.8.7"),
        (None, "installed Playwright version is unreadable"),
        ("broken json", "installed Playwright version is unreadable"),
        ("{}", "installed Playwright version is unreadable"),
        ('{"version": null}', "installed Playwright version is unreadable"),
    ],
)
def test_broken_browser_probe_refuses_before_later_work(project, package, version):
    if shutil.which("node") is None:
        pytest.skip("browser probe failure needs Node.js")
    root, _cfg, _record, _bindir, _browser = project
    modules = root / "src/frontend/two/node_modules"
    assert (modules / ".package-lock.json").is_file()
    (modules / "playwright-core/lib/coreBundle.js").unlink()
    if package is not None:
        metadata = modules / "@playwright/test/package.json"
        metadata.parent.mkdir(parents=True)
        metadata.write_text(package)

    result = _run(project, "preflight", "expensive")

    assert result.returncode == 2, result.stdout + result.stderr
    assert "src/frontend/two/" in result.stderr, result.stderr
    assert "scripts/preflight.py _BROWSER_PATH probe failed" in result.stderr
    assert version in result.stderr, result.stderr
    assert "update the probe in scripts/preflight.py" in result.stderr
    assert "layers.frontend.journey.browser_executable" in result.stderr
    assert "make fe-install" not in result.stderr
    assert "make fe-browsers" not in result.stderr
    assert not (root / "expensive-started").exists()


@pytest.mark.parametrize(
    "failure,diagnostic,detail,remedy",
    [
        (
            "timeout",
            "node did not answer within the limit",
            "10 seconds",
            "check the node on PATH",
        ),
        (
            "oserror",
            "node could not be started",
            "Permission denied",
            "check the node on PATH",
        ),
        (
            "empty",
            "scripts/preflight.py _BROWSER_PATH probe failed",
            "registry returned no executable",
            "update the probe in scripts/preflight.py",
        ),
        (
            "nonzero",
            "scripts/preflight.py _BROWSER_PATH probe failed",
            "registry module unavailable",
            "update the probe in scripts/preflight.py",
        ),
    ],
)
def test_probe_failure_refuses_before_later_work(
    project, failure, diagnostic, detail, remedy, monkeypatch, capsys
):
    import preflight

    root, _cfg, _record, bindir, _browser = project
    probed = []
    real_run = subprocess.run

    def probe(command, **kwargs):
        if command[0] != "node":
            return real_run(command, **kwargs)
        probed.append(kwargs["cwd"])
        assert kwargs["timeout"] == 10
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        if failure == "oserror":
            raise PermissionError(13, "Permission denied", "node")
        return subprocess.CompletedProcess(
            command,
            1 if failure == "nonzero" else 0,
            str(root / "browser") if failure == "nonzero" else " \n\t",
            "\n \t\n" + detail + "\nsecond stderr line must be omitted\n",
        )

    with monkeypatch.context() as patch:
        patch.setenv("PATH", str(bindir))
        patch.setattr(preflight.subprocess, "run", probe)
        status = preflight.main(
            argv=["src/frontend/one", "src/frontend/two"], root=str(root)
        )
    captured = capsys.readouterr()
    if status == 0:
        _run(project, "expensive")

    assert status == 2, captured.err
    assert diagnostic in captured.err, captured.err
    assert detail in captured.err, captured.err
    assert remedy in captured.err, captured.err
    assert "src/frontend/one" in captured.err
    if failure == "timeout":
        refusal = captured.err.splitlines()
        assert len(refusal) == 2  # One probe refusal, then main's install summary.
        assert diagnostic in refusal[0]
        assert "10 seconds" in refusal[0]
        assert preflight._BROWSER_PATH not in captured.err
        assert "const bundle" not in captured.err
        assert "require.resolve" not in captured.err
        assert "['node', '-e'" not in captured.err
    if failure in ("timeout", "oserror"):
        assert "update the probe" not in captured.err
        assert "browser_executable" not in captured.err
    else:
        assert "layers.frontend.journey.browser_executable" in captured.err
        assert "second stderr line must be omitted" not in captured.err
    assert probed == [str(root / "src/frontend/one")]
    assert not (root / "expensive-started").exists()


@pytest.mark.parametrize(
    "missing,diagnostic,remedy",
    [
        ("npm", "npm is not on PATH", "make fe-install"),
        ("node", "node is not on PATH", "make fe-install"),
        ("node-override", "node is not on PATH", "make fe-install"),
        ("one", "one/ install is missing or incomplete", "make fe-install"),
        ("two", "two/ install is missing or incomplete", "make fe-install"),
        ("python", "keel-preflight-absent", "pip install -e"),
        ("record", "no scanner record", "make secrets-install"),
        ("scanner", "recorded scanner", "make secrets-install"),
        ("digest", "changed after it was recorded", "make secrets-install"),
        ("browser", "browser", "make fe-browsers"),
        ("override", "custom-browser", "make fe-browsers"),
        ("shellcheck", "shellcheck", "shellcheck-py wheel"),
        ("shfmt", "shfmt", "shfmt-py wheel"),
        ("bats", "bats", "install bats-core"),
    ],
)
def test_missing_install_refuses_before_later_work(
    project, missing, diagnostic, remedy, monkeypatch, capsys
):
    root, cfg, record, bindir, browser = project
    if missing == "node-override":
        (bindir / "node").unlink(missing_ok=True)
        cfg["layers"]["frontend"]["journey"]["browser_executable"] = str(browser)
        _save(root, cfg)
    elif missing in ("npm", "node"):
        (bindir / missing).unlink(missing_ok=True)
    elif missing in ("one", "two"):
        shutil.rmtree(root / "src/frontend" / missing / "node_modules")
    elif missing == "python":
        (root / "pyproject.toml").write_text(
            '[project]\nname="probe"\ndependencies=["keel-preflight-absent"]\n[project.optional-dependencies]\ndev=[]\n'
        )
    elif missing == "record":
        record.unlink()
    elif missing in ("scanner", "digest"):
        data = json.loads(record.read_text())
        data["path" if missing == "scanner" else "sha256"] = (
            "/absent/scanner" if missing == "scanner" else "wrong"
        )
        record.write_text(json.dumps(data))
    elif missing == "browser":
        if shutil.which("node") is None:
            pytest.skip("cache-path discovery needs Node.js")
        browser.unlink()
    elif missing == "override":
        cfg["layers"]["frontend"]["journey"]["browser_executable"] = str(
            root / "custom-browser"
        )
        _save(root, cfg)
    else:
        cfg["shell"]["enabled"] = True
        cfg["shell"]["no_scripts"] = None
        _save(root, cfg)
        (bindir / missing).unlink(missing_ok=True)
        # A git listing is independent of a local tool's presence.
        (root / "sample.sh").write_text("#!/bin/sh\ntrue\n")
        (root / "sample.bats").write_text('@test "sample" { true; }\n')
    if missing in ("shellcheck", "shfmt", "bats"):
        import preflight
        import shell_gate

        monkeypatch.setattr(
            shell_gate,
            "classify",
            lambda *_args: shell_gate.Classified(["sample.sh"], ["sample.bats"], []),
        )
        monkeypatch.setattr(shell_gate, "_interpreter_dir", lambda: str(bindir))
        monkeypatch.setenv("PATH", str(bindir))
        status = preflight.main(argv=[], root=str(root))
        captured = capsys.readouterr()
        result = subprocess.CompletedProcess([], status, captured.out, captured.err)
    else:
        result = _run(project, "preflight", "expensive")
    assert result.returncode == 2, result.stdout + result.stderr
    assert diagnostic in result.stderr, result.stderr
    assert remedy in result.stderr, result.stderr
    assert not (root / "expensive-started").exists()


@pytest.mark.parametrize("frontend", [True, False])
def test_preflight_passes_when_every_required_install_exists(project, frontend):
    root, cfg, _record, bindir, _browser = project
    if frontend and shutil.which("node") is None:
        pytest.skip(
            "the frontend control needs Node.js; the backend-only control still runs"
        )
    if not frontend:
        shutil.rmtree(root / "src/frontend")
        (bindir / "npm").unlink()
        (bindir / "node").unlink(missing_ok=True)
        del cfg["layers"]["frontend"]["journey"]
        _save(root, cfg)
    before = {
        str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mode)
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    result = _run(project, "preflight")
    after = {
        str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mode)
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    assert after == before
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == result.stderr == ""


def test_verify_checks_installs_first():
    rules = cs.make_target_rules((_ROOT / "Makefile").read_text())
    verify = next(rule for rule in rules if rule.target == "verify")
    assert verify.recursions[0] == "preflight", verify.recursions
    assert cs.target_effects(str(_ROOT))["preflight"] == (("local",), None)
