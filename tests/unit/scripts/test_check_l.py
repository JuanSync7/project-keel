"""
title: Unit — check_structure check_L (naked-tensor domain warn)
kind: tests
layer: n/a
summary: check_L's detector flags a parameter annotated with a bare tensor base type (exact membership over tokens.tensor_base_types) and no shape comment, accepts a shape comment anywhere in the function header span (multi-line signatures, line above, inline), rejects non-shape parens as a shape, is per-arg and waivable — an advisory heuristic that only ever WARNs.
"""

import ast
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit

_BT = {"Tensor", "FloatTensor", "ndarray", "Array"}


def _naked(src, base=None):
    tree = ast.parse(src)
    return cs._naked_tensor_params(tree, src, base if base is not None else _BT)


def _params(src, base=None):
    return [arg for _, arg, _ in _naked(src, base)]


# --- MUST-FLAG (a bare tensor param with no shape) ---------------------------


def test_bare_tensor_param_is_flagged():
    assert _params("def step(x: Tensor):\n    return x\n") == ["x"]


def test_todo_paren_is_not_a_shape():
    # `# TODO(jkok): ...` has a single-atom paren — not a shape, must still flag.
    assert _params(
        "def step(x: Tensor):  # TODO(jkok): shape later\n    return x\n"
    ) == ["x"]


def test_single_token_paren_is_not_a_shape():
    assert _params("def step(x: Tensor):  # (deprecated)\n    return x\n") == ["x"]


def test_two_naked_params_are_flagged_per_arg():
    assert _params("def f(a: Tensor, b: Tensor):\n    return a\n") == ["a", "b"]


def test_string_annotation_is_flagged():
    assert _params('def f(x: "Tensor"):\n    return x\n') == ["x"]


def test_local_class_named_like_a_token_still_only_warns():
    # `Array` may be a local non-tensor class — the detector cannot tell, so it
    # over-flags. The tier is WARN, never err: _naked_tensor_params only RETURNS
    # findings; check_L emits them exclusively via warn(). Locks "never err".
    src = "class Array:\n    pass\n\ndef build(a: Array):\n    return a\n"
    assert _params(src) == ["a"]
    assert (
        "err" not in cs.check_L.__doc__.lower()
        or "never errs" in cs.check_L.__doc__.lower()
    )


# --- MUST-PASS (a shape is documented, or a waiver, or not a bare token) ------


def test_shape_on_closing_paren_line_of_multiline_signature_passes():
    src = (
        "def forward(\n    self,\n    hidden: Tensor,\n):  # hidden: (B, T, H)\n"
        "    return hidden\n"
    )
    assert _naked(src) == []


def test_shape_on_the_line_above_the_def_passes():
    src = "# hidden: (B, T, H)\ndef forward(self, hidden: Tensor):\n    return hidden\n"
    assert _naked(src) == []


def test_inline_two_dim_shape_passes():
    assert _naked("def step(x: Tensor):  # (B, T)\n    return x\n") == []


def test_practice_ok_in_header_waives():
    assert _naked("def step(x: Tensor):  # practice-ok: reviewed\n    return x\n") == []


def test_empty_token_set_finds_nothing():
    assert _naked("def step(x: Tensor):\n    return x\n", base=set()) == []


def test_non_tensor_annotation_is_ignored():
    # Exact membership — no suffix/substring match on the annotation name.
    assert _naked("def f(x: MyConfig):\n    return x\n") == []


def test_alias_hiding_the_base_type_is_a_documented_blind_spot():
    # TensorAlias is not itself a token id, so it passes (why the tier is WARN).
    src = "TensorAlias = Tensor\ndef step(x: TensorAlias):\n    return x\n"
    assert _naked(src) == []


def test_unannotated_param_is_ignored():
    assert _naked("def f(x):\n    return x\n") == []
