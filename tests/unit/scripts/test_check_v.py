"""
title: Unit — check_structure check_V (a writer declares how it behaves on a second run)
kind: tests
layer: n/a
summary: A module that writes to the filesystem must say so in its gated header (`effect:`) and say what a second run does (`rerun:`), and a `rerun: fixed-point` claim must name a proof that resolves. Pins the detector against the false positive that makes this checkable at all — `text.replace(...)` is not `os.replace(...)` — and against the silent-green case a naive version would ship: an undeclared write is an ERROR naming the line, while a declaration with no write it can see is a WARN saying unverified, never a pass.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_structure as cs  # noqa: E402

pytestmark = pytest.mark.unit

_S = "§"  # spelled as an escape: check_Q reads this file's source too

_LETTERS = {"O", "V"}
_TREE = {"tests/integration/test_idempotence.py", "docs/guides/idempotency.md"}
_TARGETS = {"verify", "site-data"}


def _sites(src):
    """Write sites the detector finds in *src*, as `(lineno, what)` pairs."""
    import ast

    return cs._write_sites(ast.parse(src))


def _what(src):
    return [w for _lineno, w in _sites(src)]


# --- the detector: what counts as a filesystem write ----------------------------


def test_open_for_writing_is_a_write():
    assert _what("open(p, 'w')") == ["open('w')"]


def test_open_for_reading_is_not_a_write():
    assert _what("open(p)") == []
    assert _what("open(p, 'r')") == []
    assert _what("open(p, encoding='utf-8')") == []


def test_every_mutating_mode_is_a_write():
    for mode in ("w", "a", "x", "wb", "r+", "w+b"):
        assert _what("open(p, %r)" % mode) == ["open(%r)" % mode], mode


def test_mode_passed_by_keyword_is_read():
    assert _what("open(p, mode='a')") == ["open('a')"]


def test_a_mode_the_check_cannot_read_counts_as_a_write():
    """Conservative on purpose: a computed mode MIGHT write, and a check that
    guesses 'read' there goes dark on exactly the case it exists to catch. Costs
    nothing today — no module in the tree opens with a non-literal mode."""
    assert _what("open(p, mode)") == ["open(<computed>)"]


def test_a_string_replace_is_not_a_filesystem_write():
    """The false positive that decides whether this can be a gate at all: a naive
    detector keyed on the method NAME reports `str.replace` and flags half the
    repo, which is why the base of the call is resolved before it counts."""
    assert _what("text.replace('a', 'b')") == []
    assert _what("'x'.replace('a', 'b')") == []


def test_qualified_os_calls_are_writes():
    assert _what("os.replace(a, b)") == ["os.replace"]
    assert _what("os.makedirs(d, exist_ok=True)") == ["os.makedirs"]
    assert _what("os.remove(p)") == ["os.remove"]
    assert _what("shutil.rmtree(p)") == ["shutil.rmtree"]


def test_reading_os_calls_are_not_writes():
    assert _what("os.path.join(a, b)") == []
    assert _what("os.listdir(d)") == []
    assert _what("os.walk(d)") == []


def test_pathlib_writes_are_writes():
    assert _what("Path(p).write_text(s)") == ["Path().write_text"]
    assert _what("out.write_bytes(b)") == []  # an unqualified name: not provably a Path


def test_line_numbers_are_reported_so_the_fix_is_findable():
    src = "import os\n\n\nos.remove(p)\n"
    assert _sites(src) == [(4, "os.remove")]


# --- the declaration rules ------------------------------------------------------


def _find(modules):
    """modules: {relpath: source} -> (errors, warnings)."""
    return cs._effect_declaration_findings(
        modules, _LETTERS, _TREE, _TARGETS, lambda p: None
    )


def _header(**keys):
    """A module docstring carrying the gated header plus whatever keys are given."""
    body = "".join("%s: %s\n" % (k, v) for k, v in keys.items())
    return '"""\ntitle: T\nsummary: S\n%s"""\n' % body


_PROOF = "test:tests/integration/test_idempotence.py"


def test_a_declared_fixed_point_writer_passes():
    src = _header(effect="writes", rerun="fixed-point", rerun_proof=_PROOF)
    src += "import os\nos.makedirs(d, exist_ok=True)\n"
    assert _find({"scripts/w.py": src}) == ([], [])


def test_an_undeclared_writer_errors_naming_the_line():
    src = _header() + "open(p, 'w')\n"
    errs, _warns = _find({"scripts/w.py": src})
    assert len(errs) == 1, errs
    assert "scripts/w.py" in errs[0] and "effect: writes" in errs[0]
    assert ":5:" in errs[0], errs[0]  # the header is four lines; the write is the fifth


def test_a_module_declaring_read_only_while_writing_errors():
    src = _header(effect="read-only") + "open(p, 'w')\n"
    errs, _warns = _find({"scripts/w.py": src})
    assert len(errs) == 1 and "read-only" in errs[0], errs


def test_an_effect_outside_the_closed_set_errors():
    src = _header(effect="mutates") + "open(p, 'w')\n"
    errs, _warns = _find({"scripts/w.py": src})
    assert len(errs) == 1 and "mutates" in errs[0], errs


def test_a_writer_with_no_rerun_key_errors():
    src = _header(effect="writes") + "open(p, 'w')\n"
    errs, _warns = _find({"scripts/w.py": src})
    assert len(errs) == 1 and "rerun:" in errs[0], errs


def test_a_rerun_outside_the_closed_set_errors():
    src = _header(effect="writes", rerun="idempotent") + "open(p, 'w')\n"
    errs, _warns = _find({"scripts/w.py": src})
    assert len(errs) == 1 and "idempotent" in errs[0], errs


def test_a_fixed_point_claim_with_no_proof_errors():
    src = _header(effect="writes", rerun="fixed-point") + "open(p, 'w')\n"
    errs, _warns = _find({"scripts/w.py": src})
    assert len(errs) == 1 and "rerun_proof:" in errs[0], errs


def test_a_proof_that_does_not_resolve_errors():
    src = _header(
        effect="writes", rerun="fixed-point", rerun_proof="test:tests/nope.py"
    )
    src += "open(p, 'w')\n"
    errs, _warns = _find({"scripts/w.py": src})
    assert len(errs) == 1 and "tests/nope.py" in errs[0], errs


def test_a_proof_outside_the_mechanism_grammar_errors():
    """The same closed grammar check_T holds `enforced_by` to — one grammar for
    'name the thing that proves this', wherever the claim is made."""
    src = _header(effect="writes", rerun="fixed-point", rerun_proof="vibes")
    src += "open(p, 'w')\n"
    errs, _warns = _find({"scripts/w.py": src})
    assert len(errs) == 1 and "grammar" in errs[0], errs


def test_the_other_rerun_values_need_no_proof():
    """`append-only` and `unsafe` are admissions, not claims: there is nothing to
    prove, and requiring a proof would push an honest author toward the
    unprovable claim instead."""
    for value in ("append-only", "unsafe"):
        src = _header(effect="writes", rerun=value) + "open(p, 'w')\n"
        assert _find({"scripts/w.py": src}) == ([], []), value


def test_a_declared_writer_with_no_visible_write_warns_unverified():
    """It may shell out, or the write may have been removed and the header left
    behind. Either way the claim is unproven, and an unproven claim is never a
    silent pass."""
    src = _header(effect="writes", rerun="fixed-point", rerun_proof=_PROOF)
    src += "print('hello')\n"
    errs, warns = _find({"scripts/w.py": src})
    assert errs == [], errs
    assert len(warns) == 1 and "unverified" in warns[0], warns


def test_a_rerun_key_without_a_writes_effect_errors():
    """A declaration about nothing: the reader is told how re-running behaves by a
    module that never claimed to write."""
    src = _header(rerun="fixed-point", rerun_proof=_PROOF) + "print('hi')\n"
    errs, _warns = _find({"scripts/w.py": src})
    assert len(errs) == 1 and "effect: writes" in errs[0], errs


def test_a_module_with_neither_a_write_nor_a_declaration_passes():
    assert _find({"scripts/r.py": _header() + "open(p).read()\n"}) == ([], [])


def test_an_unparseable_module_is_left_to_the_check_that_owns_it():
    """check_D already warns over the same roots; a second report here is noise."""
    assert _find({"scripts/broken.py": "def (\n"}) == ([], [])


def test_a_module_without_a_docstring_is_left_to_check_O():
    assert _find({"scripts/w.py": "open(p, 'w')\n"}) == ([], [])


def test_findings_are_sorted_by_path():
    mods = {
        "scripts/b.py": _header() + "open(p, 'w')\n",
        "scripts/a.py": _header() + "open(p, 'w')\n",
    }
    errs, _warns = _find(mods)
    assert [e.split(":")[0] for e in errs] == ["scripts/a.py", "scripts/b.py"], errs


# --- every proof form the grammar allows ----------------------------------------


@pytest.mark.parametrize(
    "proof",
    [
        "test:tests/integration/test_idempotence.py",
        "check:V",
        "make:site-data",
        "doc:docs/guides/idempotency.md",
    ],
)
def test_each_mechanism_form_resolves_as_a_proof(proof):
    src = _header(effect="writes", rerun="fixed-point", rerun_proof=proof)
    src += "open(p, 'w')\n"
    assert _find({"scripts/w.py": src}) == ([], []), proof


# --- through the gate (module-global err/warn plumbing) -------------------------


@pytest.fixture()
def gate(tmp_path, monkeypatch):
    """A minimal repo the gate walks: patched ROOT/WRITER_ROOTS, clean lists."""
    monkeypatch.setattr(cs, "ROOT", str(tmp_path))
    monkeypatch.setattr(cs, "WRITER_ROOTS", ["scripts"])
    monkeypatch.setattr(cs, "errors", [])
    monkeypatch.setattr(cs, "warnings", [])
    (tmp_path / "scripts").mkdir()
    return tmp_path


def test_check_v_reports_through_the_gate(gate):
    (gate / "scripts" / "bad.py").write_text(
        _header() + "import os\nos.remove(p)\n", encoding="utf-8"
    )
    (gate / "scripts" / "good.py").write_text(
        _header(effect="writes", rerun="fixed-point", rerun_proof="check:V")
        + "import os\nos.remove(p)\n",
        encoding="utf-8",
    )
    cs.check_V()
    assert any("bad.py" in e for e in cs.errors), cs.errors
    assert not any("good.py" in e for e in cs.errors), cs.errors


def test_check_v_does_not_read_the_test_suite(gate, monkeypatch):
    """Tests write scratch trees by design; holding every fixture to a writer's
    declaration would make the rule noise and teach authors to ignore it."""
    monkeypatch.setattr(cs, "WRITER_ROOTS", ["scripts"])
    (gate / "tests").mkdir()
    (gate / "tests" / "test_x.py").write_text(
        _header() + "open(p, 'w')\n", encoding="utf-8"
    )
    cs.check_V()
    assert cs.errors == [], cs.errors
