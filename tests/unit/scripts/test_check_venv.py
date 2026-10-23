"""
title: Unit — check_venv (the venv holds what pyproject.toml declares)
kind: tests
layer: n/a
summary: scripts/check_venv.py driven with a scratch pyproject.toml, an injected config object and an injected view of the installed distributions, so no case reads this checkout's config or venv. Every requirement of the core dependencies, of config/project.json `venv.extras` and of the extra each enabled transport names in `transports.extras` is judged, an extra that names its own project is followed, an extra a requirement asks of another distribution judges that extra's own requirements, and a requirement whose marker excludes this interpreter is not judged; an absent distribution, a version outside the specifier or an unparsable version is FAILURE naming the package, the interpreter and the exact pip command, whose extras are the fewest that reach every judged one; an extra the config names and pyproject.toml lacks is CONFIG, an unreadable pyproject.toml is USAGE, and nothing to judge is NOTHING_JUDGED. The pip command carries `--index-url <url>` when config/project.json `install_sources.python_index` sets one and no flag when it is null, and an index with a URL user part is CONFIG that never shows it. The transport extra and api/rest_fastapi/requirements.txt are held equal.
@covers scripts/check_venv.py
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_venv  # noqa: E402
from exit_codes import ExitCode  # noqa: E402

pytestmark = pytest.mark.unit

_PY = "/opt/venv/bin/python"

_PYPROJECT = """\
[project]
name = "demo_proj"
dependencies = ["corelib>=1.0"]

[project.optional-dependencies]
dev = [
  "pytest>=7.3",
  "ruff==0.15.18",
  "tomli; python_version < '3'",
  "demo-proj[transport]",
]
transport = ["fastapi>=0.115", "uvicorn[standard]>=0.32"]
solo = ["lonely>=1"]
empty = []
"""

_INSTALLED = {
    "corelib": "1.2",
    "pytest": "8.0.0",
    "ruff": "0.15.18",
    "fastapi": "0.120.0",
    "uvicorn": "0.35.0",
    "uvloop": "0.21.0",
    "lonely": "1.0",
}

_UVICORN_REQUIRES = [
    "click>=7.0",
    'uvloop>=0.15; extra == "standard"',
    'pywin32; extra == "standard" and sys_platform == "nonexistent-os"',
]


def _config(extras=("dev",), enabled=("rest",), transport_extras=None, index=None):
    return {
        "install_sources": {"python_index": index},
        "venv": {"extras": list(extras)},
        "transports": {
            "enabled": list(enabled),
            "available": {"rest": "api/rest_fastapi", "mcp": "mcp"},
            "extras": {} if transport_extras is None else dict(transport_extras),
        },
    }


def _root(tmp_path, text=_PYPROJECT):
    (tmp_path / "pyproject.toml").write_text(text, encoding="utf-8")
    return str(tmp_path)


def _run(tmp_path, config=None, installed=None, text=_PYPROJECT, requires=None):
    have = dict(_INSTALLED if installed is None else installed)
    deps = {"uvicorn": _UVICORN_REQUIRES} if requires is None else requires
    return check_venv.main(
        root=_root(tmp_path, text),
        loaded=_config() if config is None else config,
        version_of=have.get,
        requires_of=lambda name: list(deps.get(name, [])),
        executable=_PY,
    )


def test_a_venv_holding_every_declared_requirement_passes(tmp_path, capsys):
    assert _run(tmp_path) is ExitCode.SUCCESS
    out = capsys.readouterr().out
    # corelib, pytest, ruff, fastapi, uvicorn and uvloop: the marker-excluded
    # tomli and pywin32, and uvicorn's unconditional click, are not judged.
    assert "6 requirements" in out, out
    assert _PY in out


def test_an_absent_core_dependency_fails_with_the_pip_command(tmp_path, capsys):
    installed = dict(_INSTALLED)
    del installed["corelib"]
    assert _run(tmp_path, installed=installed) is ExitCode.FAILURE
    err = capsys.readouterr().err
    assert "corelib" in err and "not installed" in err, err
    assert "pyproject.toml" in err and _PY in err, err
    assert '%s -m pip install -e ".[dev]"' % _PY in err, err


def test_a_configured_index_is_in_the_pip_command(tmp_path, capsys):
    index = "https://pypi.mirror.example.invalid/simple/"
    installed = dict(_INSTALLED)
    del installed["corelib"]
    config = _config(index=index)
    assert _run(tmp_path, config=config, installed=installed) is ExitCode.FAILURE
    err = capsys.readouterr().err
    assert '%s -m pip install -e ".[dev]" --index-url %s' % (_PY, index) in err, err


def test_a_null_index_leaves_the_pip_command_to_pips_own_config(tmp_path, capsys):
    installed = dict(_INSTALLED)
    del installed["corelib"]
    assert _run(tmp_path, installed=installed) is ExitCode.FAILURE
    err = capsys.readouterr().err
    assert "--index-url" not in err and "[using default]" not in err, err


def test_an_index_with_a_user_part_is_config_and_never_shown(tmp_path, capsys):
    config = _config(index="https://u:tok-SENTINEL@pypi.mirror.example.invalid/")
    assert _run(tmp_path, config=config) is ExitCode.CONFIG
    err = capsys.readouterr().err
    assert "install_sources.python_index" in err and "SENTINEL" not in err, err


def test_a_version_outside_the_specifier_fails_naming_both(tmp_path, capsys):
    installed = dict(_INSTALLED, ruff="0.15.0")
    assert _run(tmp_path, installed=installed) is ExitCode.FAILURE
    err = capsys.readouterr().err
    assert "ruff 0.15.0" in err and "==0.15.18" in err, err


def test_an_unparsable_installed_version_fails_rather_than_passes(tmp_path, capsys):
    installed = dict(_INSTALLED, pytest="not-a-version")
    assert _run(tmp_path, installed=installed) is ExitCode.FAILURE
    err = capsys.readouterr().err
    assert "pytest" in err and "not-a-version" in err, err


def test_an_extra_that_names_its_own_project_is_followed(tmp_path, capsys):
    """`dev` reaches the transport packages only through `demo-proj[transport]`:
    a checker that stopped at the self-reference would pass a venv without
    FastAPI, which is the silent skip this check exists to end."""
    installed = dict(_INSTALLED)
    del installed["fastapi"]
    assert _run(tmp_path, installed=installed) is ExitCode.FAILURE
    err = capsys.readouterr().err
    assert "fastapi" in err, err
    # dev already reaches transport, so the command names dev alone.
    assert '-m pip install -e ".[dev]"' in err, err


def test_an_extra_asked_of_a_dependency_judges_that_extras_requirements(
    tmp_path, capsys
):
    installed = dict(_INSTALLED)
    del installed["uvloop"]
    assert _run(tmp_path, installed=installed) is ExitCode.FAILURE
    err = capsys.readouterr().err
    assert "uvloop" in err and "uvicorn[standard]" in err, err


def test_an_enabled_transports_extra_is_judged_and_named_in_the_command(
    tmp_path, capsys
):
    """`solo` is no part of `dev`, so it is judged only because the enabled
    transport names it, and the command must name it beside `dev`."""
    installed = dict(_INSTALLED)
    del installed["lonely"]
    config = _config(transport_extras={"rest": "solo"})
    assert _run(tmp_path, config=config, installed=installed) is ExitCode.FAILURE
    err = capsys.readouterr().err
    assert "lonely" in err, err
    assert '-m pip install -e ".[dev,solo]"' in err, err


def test_a_disabled_transports_extra_is_not_judged(tmp_path):
    installed = dict(_INSTALLED)
    del installed["lonely"]
    config = _config(enabled=("mcp",), transport_extras={"rest": "solo"})
    assert _run(tmp_path, config=config, installed=installed) is ExitCode.SUCCESS


def test_an_extra_pyproject_does_not_declare_is_a_config_refusal(tmp_path, capsys):
    for config in (
        _config(extras=("dev", "nosuch")),
        _config(transport_extras={"rest": "nosuch"}),
    ):
        assert _run(tmp_path, config=config) is ExitCode.CONFIG
        err = capsys.readouterr().err
        assert "nosuch" in err and "pyproject.toml" in err, err


def test_a_wrongly_typed_config_value_is_a_config_refusal(tmp_path, capsys):
    config = _config()
    config["venv"]["extras"] = "dev"
    assert _run(tmp_path, config=config) is ExitCode.CONFIG
    assert "venv.extras" in capsys.readouterr().err


def test_an_unreadable_pyproject_is_a_usage_refusal(tmp_path, capsys):
    for text in ("[project\nname =", '[tool.other]\nx = "y"\n'):
        assert _run(tmp_path, text=text) is ExitCode.USAGE
        assert "pyproject.toml" in capsys.readouterr().err


def test_nothing_to_judge_is_not_a_pass(tmp_path, capsys):
    text = (
        '[project]\nname = "demo_proj"\n\n[project.optional-dependencies]\nempty = []\n'
    )
    config = _config(extras=("empty",))
    assert _run(tmp_path, config=config, text=text) is ExitCode.NOTHING_JUDGED
    assert "empty" in capsys.readouterr().err


def test_the_transport_extra_and_the_rest_requirements_file_agree():
    """api/rest_fastapi/requirements.txt serves an install outside the project;
    the `transport` extra serves the gate. Two lists of the same packages drift
    unless something holds them equal."""
    project = check_venv.read_project(str(_ROOT))
    listed = (_ROOT / "api" / "rest_fastapi" / "requirements.txt").read_text()
    lines = [
        ln.strip()
        for ln in listed.splitlines()
        if ln.strip() and not ln.startswith("#")
    ]
    assert sorted(project["optional-dependencies"]["transport"]) == sorted(lines)


def test_this_checkouts_config_names_extras_its_pyproject_declares():
    """The real pair: every extra config/project.json asks the gate for exists,
    so the verify prerequisite cannot refuse a fresh checkout over a typo."""
    import config_loader

    loaded = config_loader.read(str(_ROOT))
    project = check_venv.read_project(str(_ROOT))
    wanted = check_venv.wanted_extras(loaded)
    declared = project["optional-dependencies"]
    assert wanted and all(extra in declared for extra in wanted), (wanted, declared)
    assert "transport" in check_venv.reachable(project, wanted), wanted


def test_a_keel_venv_without_copier_fails_naming_the_template_extra(capsys):
    """Keel's own gate renders projects with copier, so keel's config names the
    `template` extra: a keel venv holding everything but copier must fail with
    the command that installs it, rather than skip every copier test. Real
    pyproject.toml and config/project.json; the installed view is injected."""
    import config_loader

    loaded = config_loader.read(str(_ROOT))
    if not (_ROOT / "copier.yml").is_file():
        pytest.skip("a generated project is not a template; its venv.extras is dev")

    from packaging.requirements import Requirement

    # The distribution is read off the template extra, not spelled here:
    # tests/integration/test_copier_generator_contract.py holds every test
    # module that names the renderer to an optional_deps import guard, and
    # this case imports nothing of it.
    project = check_venv.read_project(str(_ROOT))
    hidden = Requirement(project["optional-dependencies"]["template"][0]).name

    def version_of(name):
        if check_venv._canonical(name) == check_venv._canonical(hidden):
            return None
        return check_venv._installed_version(name)

    code = check_venv.main(
        root=str(_ROOT), loaded=loaded, version_of=version_of, executable=_PY
    )
    err = capsys.readouterr().err
    assert code is ExitCode.FAILURE, err
    assert hidden in err and "extra template" in err, err
    assert '%s -m pip install -e ".[dev,template]"' % _PY in err, err


def _with_dev(entry):
    """_PYPROJECT with its self-reference line replaced by *entry*."""
    return _PYPROJECT.replace('  "demo-proj[transport]",\n', "  %s,\n" % entry)


def test_a_self_reference_is_matched_to_its_extra_whatever_the_case(tmp_path, capsys):
    """PEP 685 compares extra names canonicalised, so `[Transport]` is the
    `transport` extra and must be followed, not a KeyError."""
    installed = dict(_INSTALLED)
    del installed["fastapi"]
    text = _with_dev('"demo-proj[Transport]"')
    assert _run(tmp_path, installed=installed, text=text) is ExitCode.FAILURE
    assert "fastapi" in capsys.readouterr().err


def test_a_self_reference_to_an_undeclared_extra_is_a_config_refusal(tmp_path, capsys):
    text = _with_dev('"demo-proj[transprt]"')
    assert _run(tmp_path, text=text) is ExitCode.CONFIG
    err = capsys.readouterr().err
    assert "transprt" in err and "pyproject.toml" in err, err


def test_an_unparsable_requirement_is_a_config_refusal(tmp_path, capsys):
    text = _with_dev('"fastapi >= = 1"')
    assert _run(tmp_path, text=text) is ExitCode.CONFIG
    err = capsys.readouterr().err
    assert "fastapi >= = 1" in err and "pyproject.toml" in err, err


def test_a_self_reference_whose_marker_excludes_this_interpreter_is_not_followed(
    tmp_path,
):
    """`solo` is reached only through a self-reference whose marker no
    interpreter meets, so its absent `lonely` is not owed."""
    installed = dict(_INSTALLED)
    del installed["lonely"]
    text = _with_dev(
        '"demo-proj[transport]",\n  "demo-proj[solo]; python_version < \'3\'"'
    )
    assert _run(tmp_path, installed=installed, text=text) is ExitCode.SUCCESS


def test_an_extra_a_later_one_reaches_is_left_out_of_the_command():
    """Order does not decide the command: `dev` reaches `transport`, so
    asking for transport first still installs `.[dev]` alone."""
    project = {
        "name": "demo_proj",
        "dependencies": [],
        "optional-dependencies": {
            "dev": ["demo-proj[transport]"],
            "transport": ["fastapi>=0.115"],
        },
    }
    assert check_venv.install_extras(project, ["transport", "dev"]) == ["dev"]


def test_extras_that_reach_each_other_still_name_one_in_the_command(tmp_path, capsys):
    """dev reaches transport and transport reaches dev: dropping every extra
    some other one reaches would leave `pip install -e ".[]"`."""
    text = _PYPROJECT.replace(
        'transport = ["fastapi>=0.115",',
        'transport = ["demo-proj[dev]", "fastapi>=0.115",',
    )
    project = {
        "name": "demo_proj",
        "dependencies": [],
        "optional-dependencies": {
            "dev": ["demo-proj[transport]"],
            "transport": ["demo-proj[dev]"],
        },
    }
    assert check_venv.install_extras(project, ["dev", "transport"]) == ["dev"]
    installed = dict(_INSTALLED)
    del installed["fastapi"]
    config = _config(transport_extras={"rest": "transport"})
    assert (
        _run(tmp_path, config=config, installed=installed, text=text)
        is ExitCode.FAILURE
    )
    assert '-m pip install -e ".[dev]"' in capsys.readouterr().err


def test_a_missing_toml_reader_fails_with_the_pip_command(
    tmp_path, capsys, monkeypatch
):
    """Under 3.10 tomllib is absent and tomli comes from the dev extra: a venv
    without it is the stale venv this check names, not a traceback."""
    monkeypatch.setitem(sys.modules, "tomllib", None)
    monkeypatch.setitem(sys.modules, "tomli", None)
    assert _run(tmp_path) is ExitCode.FAILURE
    err = capsys.readouterr().err
    assert "tomli" in err and '%s -m pip install -e ".[dev]"' % _PY in err, err
