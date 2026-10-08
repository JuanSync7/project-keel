"""
title: Test helper — copy a Makefile with every makefile it includes
kind: tests
layer: n/a
summary: copy_makefiles copies a project's root Makefile into a test's scratch directory together with every makefile it includes -- the closure scripts/check_structure.py walk_makefiles returns, which is what make lists in $(MAKEFILE_LIST) -- each include at its own relative path, because make resolves an include against its working directory, not against the including file. A fixture that runs make on a copy then works in a project whose Makefile includes an area makefile (config/project.json `make_targets.area_dir`) or any other makefile. It reproduces what make sees and fails closed only where it cannot: a required `include` named through a variable or wildcard, an optional one through a wildcard that matches a file, an unreadable makefile, an include outside the root and a root with no Makefile each raise, naming the include. A required include naming no file is absent from the source too, so it is left absent (behind a false conditional make never reads it; otherwise make stops on the copy as on the source), and an optional include through a variable is left out, as the gate only WARNs on both; the residual is an optional variable include that names a file present in the source, which the copy runs without. It copies makefiles only: the scripts and config a recipe needs are the calling test's to copy.
effect: writes
rerun: fixed-point
rerun_proof: tests/integration/test_makefile_copy.py
"""

import glob
import os
import posixpath
import shutil
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS = os.path.join(_ROOT, "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import check_structure as cs  # noqa: E402


def copy_makefiles(dest, root, as_name="Makefile"):
    """Copy root's Makefile, as *as_name*, and every makefile it includes, at
    its relative path, into *dest*. -> the relative paths written, in the order
    make reads them (the root under *as_name*).

    Each file is a whole-file overwrite, so a second call into the same *dest*
    writes the same bytes. Raises AssertionError naming every include it cannot
    reproduce under *dest*, before writing anything. An include the gate only
    WARNs about is not raised for unless the copy would differ from the source
    in a way this helper can see."""
    root, dest = str(root), str(dest)
    problems = []
    # walk_makefiles' warnings are the gate's advisory grade; the ones a copy
    # cannot reproduce are re-derived below, so they are not fatal here.
    walked = cs.walk_makefiles(root, lambda _msg: None, problems.append)
    if not walked:
        problems.append("%s has no Makefile to copy" % root)
    for relpath, text in walked:
        if posixpath.isabs(relpath) or posixpath.normpath(relpath).startswith(".."):
            problems.append(
                "`%s` lies outside %s, so a copy under %s cannot reproduce it"
                % (relpath, root, dest)
            )
        problems.extend(_opaque_include_problems(root, relpath, text))
    if problems:
        raise AssertionError(
            "cannot copy the include closure of %s/Makefile: %s"
            % (root, "; ".join(problems))
        )
    written = []
    for relpath, _text in walked:
        out_rel = as_name if relpath == "Makefile" else relpath
        target = os.path.join(dest, *out_rel.split("/"))
        parent = os.path.dirname(target)
        if not os.path.isdir(parent):
            os.makedirs(parent)
        shutil.copyfile(os.path.join(root, *relpath.split("/")), target)
        written.append(out_rel)
    return written


def _opaque_include_problems(root, relpath, text):
    """The includes in *text* named through a variable or wildcard that a copy
    cannot reproduce -> messages. A required one may name a makefile make
    needs; an optional wildcard that matches a file names one make reads. An
    optional variable include stays silent: which file it names is unknowable
    without make, and make tolerates its absence."""
    out = []
    for directive, name in cs._includes(text):
        has_var = "$" in name
        if not has_var and not any(ch in name for ch in "*?["):
            continue
        if directive == "include":
            out.append(
                "%s: `include %s` names a makefile make requires through a "
                "variable or wildcard this helper does not expand, so a copy "
                "may lack it" % (relpath, name)
            )
        elif not has_var and glob.glob(os.path.join(root, name)):
            out.append(
                "%s: `%s %s` matches makefiles this helper does not follow, so "
                "a copy would run without them" % (relpath, directive, name)
            )
    return out
