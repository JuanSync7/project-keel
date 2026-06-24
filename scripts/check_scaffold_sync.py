#!/usr/bin/env python3
"""
check_scaffold_sync.py - guard that scaffold.py's embedded scripts stay in sync.

scripts/scaffold.py regenerates the project skeleton, and it ships several
support scripts as embedded raw-string constants, e.g.

    w("scripts/check_structure.py", _CHECK_STRUCTURE_SRC)
    ...
    _CHECK_STRUCTURE_SRC = r<TRI>...<TRI>      # <TRI> = three single quotes

CONVENTIONS.md (section 6) requires the live `scripts/check_structure.py` and
its embedded copy to stay *byte-identical*; the same must hold for every other
script the scaffold embeds, or a freshly scaffolded project ships tooling that
has silently diverged from the one this repo runs in CI.

This script makes that machine-checked for ALL embedded scripts (it discovers
them by parsing the `w("path", _NAME_SRC)` pairs), not just one:

  --check   (default) exit 1 if any embed differs from its live file; prints diffs.
  --write             rewrite every embed from its live file (the fix).

If scripts/scaffold.py is absent (e.g. a derived project that didn't keep the
generator), there is nothing to guard, so this is a no-op exit 0 -- the same
graceful-skip pattern cdmon_sync.py and the AAD schema check use.

A doer, not a trigger (CONVENTIONS section 7). Stdlib only; runs on Python 3.6+.
"""
import argparse
import difflib
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAFFOLD = os.path.join(ROOT, "scripts", "scaffold.py")
TRI = "'" * 3  # built at runtime so THIS file embeds cleanly (no literal triple-quote)

# scaffold emits an embedded script as:  w("relpath", _NAME_SRC)
_W_RE = re.compile(r'w\(\s*"([^"]+)"\s*,\s*(_[A-Z0-9_]+_SRC)\s*\)')


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _embeds(scaffold_text):
    """Yield (relpath, const_name, embedded_source) for each embedded script.

    Deduped by constant: an example `w("...", _NAME_SRC)` inside an embedded
    docstring must not double-count a real embed. A constant is an embed only
    if it has a real top-level `_NAME_SRC = r<TRI>...<TRI>` definition.
    """
    seen = set()
    for relpath, const in _W_RE.findall(scaffold_text):
        if const in seen:
            continue
        m = re.search(re.escape(const) + r" = r" + TRI + r"(.*?)" + TRI,
                      scaffold_text, re.DOTALL)
        if m:
            seen.add(const)
            yield relpath, const, m.group(1)


def check():
    """Return 0 when every embed matches its live file, else 1 (prints diffs)."""
    if not os.path.isfile(SCAFFOLD):
        print("check_scaffold_sync: no scripts/scaffold.py; nothing to guard (skip)")
        return 0
    pairs = list(_embeds(_read(SCAFFOLD)))
    if not pairs:
        sys.stderr.write("ERROR check_scaffold_sync: found no embedded scripts "
                         "(w(\"...\", _NAME_SRC)) in scripts/scaffold.py\n")
        return 1
    bad = 0
    for relpath, const, embedded in pairs:
        live_path = os.path.join(ROOT, relpath)
        try:
            live = _read(live_path)
        except OSError:
            sys.stderr.write("ERROR check_scaffold_sync: %s embeds %s but the "
                             "live file is missing\n" % (const, relpath))
            bad += 1
            continue
        if embedded == live:
            continue
        bad += 1
        sys.stderr.write(
            "ERROR check_scaffold_sync: %s (embed %s) has drifted from the live "
            "file. Run `python3 scripts/check_scaffold_sync.py --write` to "
            "resync (CONVENTIONS section 6).\n\n" % (relpath, const))
        diff = difflib.unified_diff(
            live.splitlines(), embedded.splitlines(),
            "%s (live)" % relpath, "scaffold.py:%s (embedded)" % const, lineterm="")
        for i, line in enumerate(diff):
            sys.stderr.write(line + "\n")
            if i > 120:
                sys.stderr.write("... (diff truncated)\n")
                break
        sys.stderr.write("\n")
    if bad:
        return 1
    print("check_scaffold_sync: %d embedded script(s) match their live files"
          % len(pairs))
    return 0


def write():
    """Rewrite every embed in scaffold.py from its live file. Returns 0/1."""
    if not os.path.isfile(SCAFFOLD):
        print("check_scaffold_sync: no scripts/scaffold.py; nothing to write (skip)")
        return 0
    text = _read(SCAFFOLD)
    pairs = list(_embeds(text))
    if not pairs:
        sys.stderr.write("ERROR check_scaffold_sync: no embedded scripts to "
                         "rewrite in scripts/scaffold.py\n")
        return 1
    changed = 0
    for relpath, const, _embedded in pairs:
        live = _read(os.path.join(ROOT, relpath))
        if TRI in live:
            sys.stderr.write("ERROR check_scaffold_sync: %s contains a "
                             "triple-single-quote sequence, which would break "
                             "its raw-string embed. Remove it.\n" % relpath)
            return 1
        pat = re.compile(re.escape(const) + r" = r" + TRI + r".*?" + TRI, re.DOTALL)
        repl = const + " = r" + TRI + live + TRI
        new = pat.sub(lambda _m: repl, text, count=1)
        if new != text:
            changed += 1
            text = new
    with open(SCAFFOLD, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("check_scaffold_sync: resynced %d embedded script(s) in scripts/scaffold.py"
          % changed)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Keep scaffold.py's embedded scripts byte-identical to their "
                    "live files (CONVENTIONS section 6).")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", default=True,
                   help="fail if any embed differs (default)")
    g.add_argument("--write", action="store_true",
                   help="rewrite every embed from its live file")
    args = ap.parse_args(argv)
    return write() if args.write else check()


if __name__ == "__main__":
    sys.exit(main())
