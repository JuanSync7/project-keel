"""
title: Integration — derive checkout-config CLI coverage from Python syntax
kind: tests
layer: n/a
summary: Scratch scripts prove root/config discovery, import and assignment aliases, helper calls and loud refusal of root expressions the rule cannot follow. Coverage comparisons fail missing, stale and empty cases.
"""

import sys
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


def test_missing_listed_script_fails_in_the_template(tmp_path):
    import root_config_cli

    (tmp_path / "copier.yml").write_text("", encoding="utf-8")
    _script(tmp_path, _DECLARATION + "config_loader.read(args.root)\n")
    cases = [("cli.py", []), ("jobs/missing.py", ["probe"])]
    with pytest.raises(AssertionError, match=r"scripts/jobs/missing\.py.*missing"):
        root_config_cli.select_cases(tmp_path, cases)


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
