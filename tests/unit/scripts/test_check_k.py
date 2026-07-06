"""
title: Unit — check_structure check_K (frozen-config gate)
kind: tests
layer: n/a
summary: check_K flags a class DECLARED frozen-config by the exact marker that is not provably immutable, keyed on the author-written marker (never a *Config name suffix, §18); it resolves aliased dataclass/NamedTuple/attrs-frozen, honours the 3.6-vs-3.8 class-line model, rejects substring/cross-class marker bleed, and is waivable — a general rule, not a name heuristic.
"""
import ast
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit

_MARKER = "practice: frozen-config"


def _viol(src, marker=_MARKER):
    """Class-kw lines flagged for `src` (marked-but-not-provably-immutable)."""
    tree = ast.parse(src)
    return cs._frozen_config_violations(tree, src, marker, cs._practice_ok_lines(src))


def _names(src, marker=_MARKER):
    return [name for _, name in _viol(src, marker)]


# --- MUST-FLAG (a declared-frozen class that is not provably immutable) --------

def test_plain_marked_mutable_class_is_flagged():
    src = "# practice: frozen-config\nclass Settings:\n    host = 'h'\n"
    assert _names(src) == ["Settings"]


def test_attr_s_without_frozen_is_flagged():
    src = ("import attr\n# practice: frozen-config\n@attr.s\n"
           "class Settings:\n    host = attr.ib()\n")
    assert _names(src) == ["Settings"]


def test_dataclass_without_frozen_true_is_flagged():
    src = ("from dataclasses import dataclass\n# practice: frozen-config\n"
           "@dataclass\nclass Settings:\n    host: str\n")
    assert _names(src) == ["Settings"]


def test_marker_above_a_decorated_class_pins_the_class_line():
    # The reported line is the `class` keyword line (5), not the decorator line —
    # stable across 3.6 (ClassDef.lineno == decorator) and 3.8+ (== class).
    src = ("from dataclasses import dataclass\n\n# practice: frozen-config\n"
           "@dataclass\nclass Settings:\n    host: str\n")
    viol = _viol(src)
    assert [n for _, n in viol] == ["Settings"]
    assert [ln for ln, _ in viol] == [5]


def test_trailing_marker_on_decorated_class_line_is_flagged():
    # Marker as a trailing comment on the actual `class` line of a decorated class
    # (would be MISSED on 3.6 by an unnormalized window; the header span includes
    # the class-kw line).
    src = ("from dataclasses import dataclass\n@dataclass\n"
           "class Settings:  # practice: frozen-config\n    host: str\n")
    assert _names(src) == ["Settings"]


# --- MUST-PASS (provably immutable, or simply not marked) ---------------------

def test_frozen_dataclass_passes():
    src = ("from dataclasses import dataclass\n# practice: frozen-config\n"
           "@dataclass(frozen=True)\nclass Settings:\n    host: str\n")
    assert _viol(src) == []


def test_aliased_frozen_dataclass_passes():
    src = ("from dataclasses import dataclass as dc\n# practice: frozen-config\n"
           "@dc(frozen=True)\nclass Settings:\n    host: str\n")
    assert _viol(src) == []


def test_aliased_namedtuple_passes():
    src = ("from typing import NamedTuple as NT\n# practice: frozen-config\n"
           "class Settings(NT):\n    host: str\n")
    assert _viol(src) == []


def test_attrs_frozen_bare_and_call_forms_pass():
    bare = ("import attrs\n# practice: frozen-config\n@attrs.frozen\n"
            "class Settings:\n    host: str\n")
    call = ("import attrs\n# practice: frozen-config\n@attrs.frozen()\n"
            "class Settings:\n    host: str\n")
    assert _viol(bare) == [] and _viol(call) == []


def test_attr_s_with_frozen_true_passes():
    src = ("import attr\n# practice: frozen-config\n@attr.s(frozen=True)\n"
           "class Settings:\n    host = attr.ib()\n")
    assert _viol(src) == []


def test_name_suffix_without_marker_is_not_flagged():
    # §18: the gate keys on the marker, never on a *Config name.
    src = "class DatabaseConfig:\n    host = 'h'\n"
    assert _viol(src) == []


def test_substring_mention_is_not_a_marker():
    src = ("# NOTE: this class is intentionally NOT practice: frozen-config\n"
           "class Settings:\n    host = 'h'\n")
    assert _viol(src) == []


def test_indented_marker_does_not_bleed_onto_the_next_class():
    # Marker indented inside Alpha's body must not mark the following Beta.
    # Neither is flagged: the marker is misplaced (not on a class header), so it
    # declares nothing — and critically it does NOT false-flag the mutable Beta.
    src = ("class Alpha:\n    x = 1\n    # practice: frozen-config\n"
           "class Beta:\n    y = 2\n")
    assert _viol(src) == []


def test_waiver_on_decorated_class_line_is_honoured():
    # `# practice-ok` on the visual class line of a decorated class must waive
    # (pins the 3.6 waiver-placement bug: pragma line != ClassDef.lineno).
    src = ("from dataclasses import dataclass\n# practice: frozen-config\n"
           "@dataclass\nclass Settings:  # practice-ok: legacy mutable\n"
           "    host: str\n")
    assert _viol(src) == []


def test_registry_marker_override_retires_the_old_literal():
    # Data-driven: with a different declared marker, the old literal marks nothing.
    src = "# practice: frozen-config\nclass Settings:\n    host = 'h'\n"
    assert _viol(src, marker="practice: immutable-config") == []


def test_no_marker_anywhere_is_silent():
    src = ("from dataclasses import dataclass\n@dataclass\n"
           "class Settings:\n    host: str\n")
    assert _viol(src) == []
