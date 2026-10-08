"""
title: Integration — a copied Makefile carries every makefile it includes
kind: tests
layer: n/a
summary: tests/makefile_copy.py copy_makefiles copies a project's root Makefile and the include closure scripts/check_structure.py walk_makefiles returns (what make lists in $(MAKEFILE_LIST)), each include at its own relative path, so a fixture that runs make on a copy works in a project whose Makefile includes an area makefile. Driven through real make on synthetic trees: an area target runs from the copy where a Makefile-only copy stops on the missing include; keel's write guard still refuses a [write] target in a copy of a Makefile with an area; a renamed root keeps its includes at their paths; a required include named through a variable or wildcard, an optional wildcard that matches a file, and an include outside the root each raise naming it, while an absent `-include`, an optional variable include, and a required include naming no file (guarded by a false conditional or not) give make on the copy the verdict make gives on the source; and a second copy into the same destination changes no byte.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

import makefile_copy

_ROOT = Path(__file__).resolve().parents[2]

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("make") is None, reason="make not installed"),
]

_AREA = "##@ a\na-hello: ## [local] x\n\t@echo from-a\n"
_ROOT_MK = "include mk/a.mk\nhello: ## [local] x\n\t@echo root\n"
# make hands its command-line variables to every child through these, so a
# suite run under the gate runner would otherwise reach this test's make.
_MAKE_INHERITANCE = ("MAKEFLAGS", "MFLAGS", "MAKELEVEL", "MAKEOVERRIDES", "RALPH", "CI")


def _tree(base, files):
    for rel, text in files.items():
        path = base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return base


def _make(cwd, *args):
    env = {k: v for k, v in os.environ.items() if k not in _MAKE_INHERITANCE}
    return subprocess.run(
        ["make", "-s"] + list(args),
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )


def _snapshot(base):
    out = {}
    for dirpath, _dirs, files in os.walk(str(base)):
        for name in files:
            full = os.path.join(dirpath, name)
            with open(full, "rb") as fh:
                out[os.path.relpath(full, str(base))] = fh.read()
    return out


def test_a_copied_makefile_keeps_every_include_at_its_path(tmp_path):
    src = _tree(tmp_path / "src", {"Makefile": _ROOT_MK, "mk/a.mk": _AREA})
    dest = tmp_path / "dest"
    dest.mkdir()
    assert makefile_copy.copy_makefiles(dest, src) == ["Makefile", "mk/a.mk"]
    r = _make(dest, "a-hello")
    assert r.returncode == 0 and r.stdout.strip() == "from-a", r.stdout + r.stderr
    # The control: the Makefile alone is today's downstream failure.
    alone = tmp_path / "alone"
    alone.mkdir()
    shutil.copyfile(str(src / "Makefile"), str(alone / "Makefile"))
    r = _make(alone, "a-hello")
    assert r.returncode != 0 and "mk/a.mk: No such file or directory" in r.stderr, (
        r.stderr
    )


def test_the_write_guard_survives_a_copy_of_a_project_with_an_area(tmp_path):
    # This project's own makefiles (with any area it already has), plus one
    # more area: the source must hold for keel and for a project alike.
    src = tmp_path / "src"
    src.mkdir()
    makefile_copy.copy_makefiles(src, _ROOT)
    with (src / "Makefile").open("a", encoding="utf-8") as fh:
        fh.write("\ninclude mk/x-area.mk\n")
    _tree(src, {"mk/x-area.mk": "##@ x\nx-hello: ## [local] x\n\t@echo x\n"})
    dest = tmp_path / "dest"
    dest.mkdir()
    makefile_copy.copy_makefiles(dest, src)
    (dest / "demo.mk").write_text(
        "include Makefile\n\ndemo-apply: ## [write] A demo\n"
        "\t$(WRITE_GUARD)\n\t@echo applied > applied.txt\n",
        encoding="utf-8",
    )
    r = _make(dest, "-f", "demo.mk", "demo-apply", "RALPH=1")
    assert r.returncode == 2, r.stdout + r.stderr
    assert "refusing 'demo-apply'" in r.stderr, r.stderr
    assert not (dest / "applied.txt").exists()


def test_the_root_is_renamed_and_the_includes_are_not(tmp_path):
    src = _tree(tmp_path / "src", {"Makefile": _ROOT_MK, "mk/a.mk": _AREA})
    dest = tmp_path / "dest"
    dest.mkdir()
    makefile_copy.copy_makefiles(dest, src, as_name="keel.mk")
    assert (dest / "keel.mk").read_text(encoding="utf-8") == _ROOT_MK
    assert (dest / "mk" / "a.mk").read_text(encoding="utf-8") == _AREA
    assert not (dest / "Makefile").exists()


@pytest.mark.parametrize(
    "line, named",
    [
        ("include $(X).mk", "$(X).mk"),
        ("include mk/*.mk", "mk/*.mk"),
        ("include ../out.mk", "../out.mk"),
    ],
    ids=["variable", "wildcard", "escapes-root"],
)
def test_an_include_it_cannot_resolve_raises(tmp_path, line, named):
    _tree(tmp_path, {"out.mk": "out:\n\t@true\n"})
    src = _tree(tmp_path / "src", {"Makefile": line + "\nall:\n\t@true\n"})
    dest = tmp_path / "dest"
    dest.mkdir()
    with pytest.raises(AssertionError) as info:
        makefile_copy.copy_makefiles(dest, src)
    assert named in str(info.value), str(info.value)


@pytest.mark.parametrize(
    "makefile",
    [
        "ENV_FILE ?= local.env\n-include $(ENV_FILE)\nall:\n\t@echo ok\n",
        "-include mk/*.mk\nall:\n\t@echo ok\n",
        "ifneq (,$(wildcard .env))\ninclude .env\nendif\nall:\n\t@echo ok\n",
        "include nope.mk\nall:\n\t@echo ok\n",
    ],
    ids=[
        "optional-variable",
        "optional-wildcard",
        "guarded-required",
        "missing-required",
    ],
)
def test_a_copy_gives_make_the_verdict_the_source_gives(tmp_path, makefile):
    """An include the gate only WARNs about is copied as make sees it, not
    raised: an optional include through a variable or wildcard is make's own
    'if present', and a required include naming no file is absent from the
    source too -- behind a false conditional make never reads it, and
    otherwise make stops on the source exactly as on the copy."""
    src = _tree(tmp_path / "src", {"Makefile": makefile})
    dest = tmp_path / "dest"
    dest.mkdir()
    assert makefile_copy.copy_makefiles(dest, src) == ["Makefile"]
    on_src, on_copy = _make(src, "all"), _make(dest, "all")
    assert (on_copy.returncode, on_copy.stdout) == (on_src.returncode, on_src.stdout), (
        on_src.stderr + on_copy.stderr
    )


def test_an_optional_wildcard_that_matches_a_file_raises(tmp_path):
    """make reads the matched makefile, which this helper does not follow, so
    a silent copy would run without it."""
    src = _tree(
        tmp_path / "src",
        {"Makefile": "-include mk/*.mk\nall:\n\t@true\n", "mk/a.mk": _AREA},
    )
    dest = tmp_path / "dest"
    dest.mkdir()
    with pytest.raises(AssertionError, match=r"mk/\*\.mk"):
        makefile_copy.copy_makefiles(dest, src)
    assert os.listdir(str(dest)) == []


def test_an_absent_optional_include_is_silent(tmp_path):
    src = _tree(tmp_path / "src", {"Makefile": "-include absent.mk\nall:\n\t@true\n"})
    dest = tmp_path / "dest"
    dest.mkdir()
    assert makefile_copy.copy_makefiles(dest, src) == ["Makefile"]
    assert sorted(os.listdir(str(dest))) == ["Makefile"]


def test_a_root_without_a_makefile_raises(tmp_path):
    (tmp_path / "src").mkdir()
    with pytest.raises(AssertionError):
        makefile_copy.copy_makefiles(tmp_path, tmp_path / "src")


def test_a_second_copy_changes_nothing(tmp_path):
    src = _tree(tmp_path / "src", {"Makefile": _ROOT_MK, "mk/a.mk": _AREA})
    dest = tmp_path / "dest"
    dest.mkdir()
    first = makefile_copy.copy_makefiles(dest, src)
    before = _snapshot(dest)
    assert makefile_copy.copy_makefiles(dest, src) == first
    assert _snapshot(dest) == before and len(before) == 2, sorted(before)
