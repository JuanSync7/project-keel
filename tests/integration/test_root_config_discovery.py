"""
title: Integration — derive checkout-config CLI coverage from Python syntax
kind: tests
layer: n/a
summary: Scratch scripts prove root/config discovery, import and assignment aliases, helper calls and loud refusal of root expressions the rule cannot follow. Coverage comparisons fail missing, stale and empty cases.
"""

import ast
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "tests"))

pytestmark = pytest.mark.integration


def _script(tmp_path, text, name="cli.py"):
    path = tmp_path / "scripts" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


_DECLARATION = """
import argparse
import config_loader
parser = argparse.ArgumentParser()
parser.add_argument("--root")
args = parser.parse_args()
"""


def test_root_and_checkout_config_read_are_derived(tmp_path):
    import root_config_cli

    _script(tmp_path, _DECLARATION + "config_loader.read(args.root)\n")
    assert root_config_cli.derive_scripts(tmp_path, ["scripts/"]) == {"cli.py"}


def test_root_without_config_read_is_not_derived(tmp_path):
    import root_config_cli

    _script(tmp_path, _DECLARATION + "print(args.root)\n")
    assert root_config_cli.derive_scripts(tmp_path, ["scripts/"]) == set()


def _cli_module_tree(tmp_path):
    """The real CLI test module over synthetic listed scripts and a manifest."""
    source = _ROOT / "tests/integration/test_exit_codes_cli.py"
    module = tmp_path / "tests/integration" / source.name
    module.parent.mkdir(parents=True)
    module.write_bytes(source.read_bytes())
    # Load the tree reader before synthetic entry scripts can shadow its imports.
    (tmp_path / "conftest.py").write_text("import source_tree\n", encoding="utf-8")
    (tmp_path / "pytest.ini").write_text(
        "[pytest]\nmarkers = integration\n", encoding="utf-8"
    )
    (tmp_path / "config").mkdir()
    (tmp_path / "config/project.json").write_bytes(
        (_ROOT / "config/project.json").read_bytes()
    )
    (tmp_path / "copier.yml").write_text("", encoding="utf-8")
    tree = ast.parse(source.read_text("utf-8"))
    listed = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "_ROOT_CONFIG_FIRST"
            for target in node.targets
        )
    )
    exemptions = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "_ROOT_CONFIG_EXEMPTIONS"
            for target in node.targets
        )
    )
    for script, _extra in listed:
        _script(
            tmp_path,
            _DECLARATION.replace(
                "import config_loader", "if False:\n    import config_loader"
            ).replace(
                "args = parser.parse_args()",
                "import sys\nsys.argv = sys.argv[:3]\nargs = parser.parse_args()",
            )
            + (
                "if False:\n    config_loader.read(args.root)\n"
                if script not in exemptions
                else ""
            )
            + "import sys\n"
            + "sys.stderr.write('invalid-checkout directory\\n')\n"
            + "raise SystemExit(2)\n",
            script,
        )
    return module, listed


def _run_cli_module(root, module, *args):
    from child_env import build_child_env
    from test_scratch_root_gate import child_timeout

    return subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            str(module),
            *args,
        ],
        cwd=root,
        env=build_child_env(
            extra={
                "PYTHONPATH": os.pathsep.join(
                    str(_ROOT / path)
                    for path in ("src", "scripts", "tests", "tests/integration", ".")
                ),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        ),
        capture_output=True,
        text=True,
        timeout=child_timeout(),
    )


@pytest.mark.parametrize("missing_script", ["query_corpus.py", "jobs/build_corpus.py"])
def test_missing_template_script_fails_only_its_case_after_collection(
    tmp_path, missing_script
):
    module, listed = _cli_module_tree(tmp_path)
    (tmp_path / "scripts" / missing_script).unlink()
    collected = _run_cli_module(tmp_path, module, "--collect-only")
    assert collected.returncode == 0, collected.stdout + collected.stderr
    report = tmp_path / "results.xml"
    run = _run_cli_module(
        tmp_path,
        module,
        "-k",
        "test_the_cases_cover_every_script_at_every_end or "
        "(test_config_first_cli_refuses_a_root_that_is_not_a_directory and missing)",
        "--junitxml=" + str(report),
    )
    assert run.returncode == pytest.ExitCode.TESTS_FAILED, run.stdout + run.stderr
    results = ET.parse(report).findall(".//testcase")
    failures = [case for case in results if case.find("failure") is not None]
    assert len(failures) == 1, run.stdout
    assert missing_script in failures[0].get("name"), run.stdout
    message = failures[0].find("failure").get("message")
    assert "scripts/" + missing_script in message
    assert "listed script missing from copier template" in message
    assert all(case.find("error") is None for case in results), run.stdout
    passed = [case for case in results if not list(case)]
    assert len(passed) == len(listed), run.stdout
    assert any(
        case.get("name") == "test_the_cases_cover_every_script_at_every_end"
        for case in passed
    )


def test_template_selection_retains_missing_rows_for_both_consumers(tmp_path):
    import root_config_cli

    (tmp_path / "copier.yml").write_text("", encoding="utf-8")
    _script(tmp_path, _DECLARATION + "config_loader.read(args.root)\n")
    listed = [("cli.py", []), ("jobs/missing.py", ["probe"])]
    included, excluded = root_config_cli.select_cases(tmp_path, listed)
    assert included == listed
    assert excluded == {}
    with pytest.raises(AssertionError, match=r"scripts/jobs/missing\.py.*not derived"):
        root_config_cli.check_cases(
            root_config_cli.derive_scripts(tmp_path, ["scripts/"]),
            {script for script, _extra in included},
        )


def test_generated_project_keeps_a_reasoned_skip_and_runs_other_cases(tmp_path):
    module, listed = _cli_module_tree(tmp_path)
    (tmp_path / "copier.yml").unlink()
    (tmp_path / "scripts/jobs/build_corpus.py").unlink()
    run = _run_cli_module(
        tmp_path,
        module,
        "-rs",
        "-k",
        "test_the_cases_cover_every_script_at_every_end or "
        "test_config_first_cases_match_the_scripts_derived_from_root_config_reads or "
        "(test_config_first_cli_refuses_a_root_that_is_not_a_directory and missing)",
    )
    assert run.returncode == 0, run.stdout + run.stderr
    assert "%d passed, 1 skipped" % (len(listed) + 1) in run.stdout
    assert "scripts/jobs/build_corpus.py: absent in generated project" in run.stdout


@pytest.mark.parametrize(
    "fault", ["syntax", "loader-root", "exemption", "server-config"]
)
def test_tree_validation_is_deferred_until_execution(tmp_path, fault):
    module, _listed = _cli_module_tree(tmp_path)
    if fault == "syntax":
        _script(tmp_path, "not python !", "query_corpus.py")
        fragment = "scripts/query_corpus.py: cannot be parsed"
    elif fault == "loader-root":
        _script(
            tmp_path,
            _DECLARATION + "config_loader.read(unknown_root)\n",
            "query_corpus.py",
        )
        fragment = "cannot resolve config loader root unknown_root"
    elif fault == "exemption":
        module.write_text(
            module.read_text("utf-8")
            + "\n_ROOT_CONFIG_EXEMPTIONS = dict.fromkeys(_ROOT_CONFIG_EXEMPTIONS, '')\n",
            encoding="utf-8",
        )
        fragment = "exemption needs a reason"
    else:
        import json

        path = tmp_path / "config/project.json"
        manifest = json.loads(path.read_text("utf-8"))
        manifest["e2e"]["server"] = None
        path.write_text(json.dumps(manifest), encoding="utf-8")
    collected = _run_cli_module(tmp_path, module, "--collect-only")
    assert collected.returncode == 0, collected.stdout + collected.stderr
    run = _run_cli_module(
        tmp_path,
        module,
        "-k",
        "test_config_first_cases_match_the_scripts_derived_from_root_config_reads or "
        "test_the_cases_cover_every_script_at_every_end",
    )
    if fault == "server-config":
        assert run.returncode == 0, run.stdout + run.stderr
        assert "2 passed" in run.stdout
    else:
        assert run.returncode == pytest.ExitCode.TESTS_FAILED, run.stdout + run.stderr
        assert fragment in run.stdout
        assert "1 failed, 1 passed" in run.stdout


def test_missing_listed_script_is_excluded_in_a_generated_project(tmp_path):
    import root_config_cli

    _script(tmp_path, _DECLARATION + "config_loader.read(args.root)\n")
    cases = [("cli.py", []), ("jobs/missing.py", ["probe"])]
    included, excluded = root_config_cli.select_cases(tmp_path, cases)
    assert included == [("cli.py", [])]
    assert "scripts/jobs/missing.py" in excluded["jobs/missing.py"]
    assert "generated project" in excluded["jobs/missing.py"]
    assert "template" in excluded["jobs/missing.py"]
    derived = root_config_cli.derive_scripts(tmp_path, ["scripts/"])
    root_config_cli.check_cases(derived, {script for script, _extra in included})


@pytest.mark.parametrize("spelling", ["module", "from", "assignment", "helper"])
def test_config_read_aliases_and_helpers_are_followed(tmp_path, spelling):
    import root_config_cli

    forms = {
        "module": "import config_loader as cfg\ncfg.read(args.root)\n",
        "from": "from config_loader import read as load\nload(args.root)\n",
        "assignment": "load = config_loader.read\nload(args.root)\n",
        "helper": ("from helper import load\nload(root=args.root)\n"),
    }
    _script(tmp_path, _DECLARATION + forms[spelling])
    _script(
        tmp_path,
        "import config_loader\ndef load(root):\n"
        "    checkout = root\n    return config_loader.read(checkout)\n",
        "helper.py",
    )
    assert root_config_cli.derive_scripts(tmp_path, ["scripts/"]) == {"cli.py"}


@pytest.mark.parametrize(
    "expression", ["getattr(args, 'root')", "roots[0]", "transform(args.root)"]
)
def test_unresolved_loader_root_fails_with_file_and_line(tmp_path, expression):
    import root_config_cli

    text = _DECLARATION + "config_loader.read(%s)\n" % expression
    _script(tmp_path, text)
    with pytest.raises(AssertionError, match=r"scripts/cli\.py:7:.*root"):
        root_config_cli.derive_scripts(tmp_path, ["scripts/"])


def test_a_config_read_of_a_fixed_checkout_is_not_derived(tmp_path):
    import root_config_cli

    _script(tmp_path, _DECLARATION + "config_loader.read('/fixed/checkout')\n")
    assert root_config_cli.derive_scripts(tmp_path, ["scripts/"]) == set()


def test_structure_gate_exclusions_are_used(tmp_path):
    import root_config_cli

    _script(tmp_path, _DECLARATION + "config_loader.read(args.root)\n")
    _script(tmp_path, "not python !", "node_modules/broken.py")
    assert root_config_cli.derive_scripts(tmp_path, ["scripts/"]) == {"cli.py"}


@pytest.mark.parametrize(
    "derived,listed,fragment",
    [
        ({"new.py"}, {"old.py"}, "new.py"),
        ({"new.py"}, {"old.py"}, "old.py"),
        (set(), set(), "zero"),
        (set(), {"old.py"}, "old.py"),
    ],
)
def test_coverage_mismatch_and_zero_scripts_fail(derived, listed, fragment):
    import root_config_cli

    with pytest.raises(AssertionError, match=fragment):
        root_config_cli.check_cases(derived, listed)


def test_reasoned_nonreader_case_can_remain_parametrized():
    import root_config_cli

    root_config_cli.check_cases(
        {"reader.py"},
        {"reader.py", "own_config.py"},
        {"own_config.py": "Reads the executable checkout, independently of --root."},
    )


@pytest.mark.parametrize(
    "derived,listed,reason",
    [
        ({"reader.py", "own_config.py"}, {"reader.py", "own_config.py"}, "old rule"),
        ({"reader.py"}, {"reader.py"}, "case removed"),
        ({"reader.py"}, {"reader.py", "own_config.py"}, "  "),
    ],
)
def test_nonreader_exemptions_must_match_and_have_a_reason(derived, listed, reason):
    import root_config_cli

    with pytest.raises(AssertionError, match=r"own_config.py.*(stale|reason)"):
        root_config_cli.check_cases(derived, listed, {"own_config.py": reason})


@pytest.mark.parametrize("expression", ["args", "(args.root,)"])
def test_a_namespace_or_container_is_an_unresolved_loader_root(tmp_path, expression):
    import root_config_cli

    _script(tmp_path, _DECLARATION + "config_loader.read(%s)\n" % expression)
    with pytest.raises(AssertionError, match=r"scripts/cli\.py:7:.*root"):
        root_config_cli.derive_scripts(tmp_path, ["scripts/"])


def test_a_starred_helper_binding_fails_at_the_loader(tmp_path):
    import root_config_cli

    _script(
        tmp_path,
        _DECLARATION
        + "def load(root):\n    config_loader.read(root)\nload(*[args.root])\n",
    )
    with pytest.raises(AssertionError, match=r"scripts/cli\.py:8:.*root"):
        root_config_cli.derive_scripts(tmp_path, ["scripts/"])


def test_an_unfollowed_lambda_reader_fails_instead_of_disappearing(tmp_path):
    import root_config_cli

    _script(
        tmp_path,
        _DECLARATION
        + "load = lambda root: config_loader.read(root)\nload(args.root)\n",
    )
    with pytest.raises(AssertionError, match=r"scripts/cli\.py:7:.*root"):
        root_config_cli.derive_scripts(tmp_path, ["scripts/"])


def test_a_helper_default_can_carry_the_parsed_root(tmp_path):
    import root_config_cli

    _script(
        tmp_path,
        _DECLARATION
        + "def load(root=args.root):\n    config_loader.read(root)\nload()\n",
    )
    assert root_config_cli.derive_scripts(tmp_path, ["scripts/"]) == {"cli.py"}


def test_a_global_reader_alias_defined_after_main_is_followed(tmp_path):
    import root_config_cli

    _script(
        tmp_path,
        "import argparse\nimport config_loader\ndef main():\n"
        "    parser = argparse.ArgumentParser()\n    parser.add_argument('--root')\n"
        "    args = parser.parse_args()\n    load(args.root)\n"
        "load = config_loader.read\nmain()\n",
    )
    assert root_config_cli.derive_scripts(tmp_path, ["scripts/"]) == {"cli.py"}


def test_a_parameter_shadows_a_fixed_module_root(tmp_path):
    import root_config_cli

    _script(
        tmp_path,
        _DECLARATION + "root = '/fixed'\ndef load(root):\n"
        "    config_loader.read(root)\nload(args.root)\n",
    )
    assert root_config_cli.derive_scripts(tmp_path, ["scripts/"]) == {"cli.py"}


@pytest.mark.parametrize("arguments", ["*[args.root]", "**{'root': args.root}"])
def test_an_expanded_loader_binding_fails_with_file_and_line(tmp_path, arguments):
    import root_config_cli

    _script(tmp_path, _DECLARATION + "config_loader.read(%s)\n" % arguments)
    with pytest.raises(AssertionError, match=r"scripts/cli\.py:7:.*root"):
        root_config_cli.derive_scripts(tmp_path, ["scripts/"])
