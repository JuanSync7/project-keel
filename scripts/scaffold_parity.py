#!/usr/bin/env python3
"""
scaffold_parity.py - prove the copier template loses nothing vs scripts/scaffold.py.

Generates the skeleton BOTH ways and compares them:
  * scaffold.py  -> a full skeleton (all stacks, all transports, hardcoded name).
  * copier       -> react-vite and astro projects (name=project_keel); their union
                    covers every stack the scaffold emits.

A **coverage GAP** — a path scaffold.py emits that copier does NOT reproduce — is a
real loss and fails the check (exit 1). **Content differences** are expected and are
reported for review, never failed on: copier ships keel's CURRENT tracked files,
while scaffold.py reconstructs them from its own (possibly stale) string literals —
so a diff means keel has evolved past the literal, i.e. copier is the more current
of the two. This is the evidence gate for retiring scaffold.py.

Not a pre-commit gate (it runs copier, which needs the project interpreter); run it
via `make scaffold-parity` or the mirror test tests/integration/test_copier_parity.py.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _entries(root):
    """Every file + symlink under root (relative paths), skipping .git."""
    out = set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in filenames:
            out.add(os.path.relpath(os.path.join(dirpath, name), root))
        for name in dirnames:                       # symlinked dirs (rare) count too
            p = os.path.join(dirpath, name)
            if os.path.islink(p):
                out.add(os.path.relpath(p, root))
    return out


def _scaffold(dest):
    subprocess.run([sys.executable, "scripts/scaffold.py", dest],
                   cwd=_ROOT, check=True, capture_output=True, text=True)


def _copier(dest, stack):
    import copier  # optional 'template' extra
    copier.run_copy(_ROOT, dest,
                    data={"project_name": "project_keel", "frontend_stack": stack},
                    defaults=True, vcs_ref="HEAD", unsafe=False, quiet=True)


def _read(path):
    if os.path.islink(path):
        return b"symlink:" + os.readlink(path).encode("utf-8")
    with open(path, "rb") as fh:
        return fh.read()


def _pick(rel, roots):
    for r in roots:
        p = os.path.join(r, rel)
        if os.path.lexists(p):
            return p
    return None


def compute_parity():
    """Return a dict describing scaffold-vs-copier parity (no side effects on the repo)."""
    tmp = tempfile.mkdtemp(prefix="keel_parity_")
    a_dir = os.path.join(tmp, "scaffold")
    br_dir = os.path.join(tmp, "copier_react")
    ba_dir = os.path.join(tmp, "copier_astro")
    os.makedirs(a_dir)
    _scaffold(a_dir)
    _copier(br_dir, "react-vite")
    _copier(ba_dir, "astro")

    a = _entries(a_dir)
    copier_roots = [br_dir, ba_dir]
    b = _entries(br_dir) | _entries(ba_dir)

    gaps = []
    for rel in sorted(a - b):
        # a `.keep` whose directory exists (with real content) in copier is not a loss.
        if os.path.basename(rel) == ".keep":
            d = os.path.dirname(rel)
            if any(x == d or x.startswith(d + os.sep) for x in b):
                continue
        gaps.append(rel)

    content_diffs = []
    for rel in sorted(a & b):
        bp = _pick(rel, copier_roots)
        if bp is None:
            continue
        try:
            if _read(os.path.join(a_dir, rel)) != _read(bp):
                content_diffs.append(rel)
        except OSError:
            pass

    return {
        "scaffold_files": len(a),
        "copier_files": len(b),
        "gaps": gaps,                       # real losses -> must be empty
        "content_diffs": content_diffs,     # expected (copier is keel's current tree)
        "copier_extra": len(b - a),         # files copier ships that scaffold doesn't
        "tmp": tmp,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--json", action="store_true", help="emit the report as JSON")
    args = ap.parse_args(argv)

    try:
        import copier  # noqa: F401
    except ImportError:
        sys.stderr.write("scaffold_parity: copier not installed "
                         "(pip install '.[template]'); cannot compare.\n")
        return 2

    r = compute_parity()
    if args.json:
        import json
        r2 = {k: v for k, v in r.items() if k != "tmp"}
        json.dump(r2, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(
            "scaffold_parity: scaffold=%d files, copier=%d files (+%d extra)\n"
            % (r["scaffold_files"], r["copier_files"], r["copier_extra"]))
        sys.stdout.write("  coverage gaps (losses): %d\n" % len(r["gaps"]))
        for g in r["gaps"]:
            sys.stdout.write("    LOSS: %s\n" % g)
        sys.stdout.write("  content diffs (expected — copier ships keel's current files): %d\n"
                         % len(r["content_diffs"]))
        if r["gaps"]:
            sys.stdout.write("RESULT: copier is MISSING artifacts scaffold.py emits — do NOT retire.\n")
        else:
            sys.stdout.write("RESULT: no losses — copier reproduces every scaffold.py artifact.\n")
    return 1 if r["gaps"] else 0


if __name__ == "__main__":
    sys.exit(main())
