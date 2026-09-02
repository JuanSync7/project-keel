"""
title: Unit — check_structure practice gates
kind: tests
layer: n/a
summary: check_J flags a third-party exception raised across a library boundary (a foreign-imported exception type), and leaves builtins, stdlib, owned (local/relative) errors, bare re-raises, and pragma-suppressed raises alone — a general rule, not a name-suffix heuristic.
"""

import ast
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit

# Owned = a local top-level package or a relative import; foreign = anything else
# that is neither local nor a declared stdlib module.
_LOCAL = {"backend", "runtimes", "models", "agents", "app"}
_STDLIB = {"json", "urllib", "socket"}


def _foreign(src, pragma=None):
    return cs._foreign_exception_raises(ast.parse(src), _LOCAL, _STDLIB, pragma or {})


def test_flags_raise_of_a_third_party_imported_exception():
    src = "from vendorsdk import VendorError\ndef f():\n    raise VendorError('x')\n"
    assert [name for _, name in _foreign(src)] == ["VendorError"]


def test_flags_attribute_raise_of_a_third_party_module():
    src = "import vendorsdk\ndef f():\n    raise vendorsdk.VendorError('x')\n"
    assert _foreign(src), "raising vendorsdk.VendorError leaks a foreign type"


def test_builtin_exception_is_not_flagged():
    # Builtins are not imported, so they never enter the candidate set.
    assert _foreign("def f():\n    raise ValueError('x')\n") == []


def test_stdlib_imported_exception_is_not_flagged():
    src = "from json import JSONDecodeError\ndef f():\n    raise JSONDecodeError('x', 'y', 0)\n"
    assert _foreign(src) == []


def test_owned_error_from_a_local_package_is_not_flagged():
    src = (
        "from backend.errors import DomainError\ndef f():\n    raise DomainError('x')\n"
    )
    assert _foreign(src) == []


def test_relative_import_is_local_and_not_flagged():
    src = "from .contracts import Pause\ndef f():\n    raise Pause('x')\n"
    assert _foreign(src) == []


def test_bare_reraise_is_not_flagged():
    src = (
        "from vendorsdk import VendorError\ndef f():\n    try:\n"
        "        pass\n    except VendorError:\n        raise\n"
    )
    assert _foreign(src) == []


def test_reraising_the_caught_instance_is_not_flagged():
    # `raise e` re-raises a local variable, not a foreign TYPE — allowed.
    src = (
        "from vendorsdk import VendorError\ndef f():\n    try:\n"
        "        pass\n    except VendorError as e:\n        raise e\n"
    )
    assert _foreign(src) == []


def test_practice_ok_pragma_suppresses_the_finding():
    src = "from vendorsdk import VendorError\ndef f():\n    raise VendorError('x')\n"
    assert _foreign(src, pragma={3: "adapter edge"}) == []


def test_helper_reads_owned_set_from_imports_not_name_suffix():
    """An exception whose NAME ends in neither Error/Exception is still flagged
    when foreign-imported — the rule is 'foreign import', not a suffix heuristic
    (the §18 specimen-fit trap the design avoids)."""
    src = "from vendorsdk import Boom\ndef f():\n    raise Boom('x')\n"
    assert [name for _, name in _foreign(src)] == ["Boom"]
