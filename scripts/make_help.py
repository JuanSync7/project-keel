#!/usr/bin/env python3
"""
title: make help — targets grouped and labelled by effect
kind: script
layer: n/a
summary: Renders `make help`. Reads the help recipe's `grep -H` lines (`file:target: ## [label] text`) on stdin and the makefiles on the command line, groups targets by `##@` area header (by makefile when there is none), and shows each target's effect label with a legend. `--effect <word>` keeps the targets whose label holds that word, `--area <name>` one area; a value outside the vocabulary, or an area filter with no area headers, exits 2 naming the valid values rather than listing nothing. An unlabelled target shows `[?]`, never vanishes. Stdlib, 3.6-safe; the label grammar and its meanings are check_structure's.
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_structure  # noqa: E402 — the one owner of the label vocabulary

_GREP_LINE = re.compile(r"^([^:]+):([A-Za-z0-9_.-]+):.*?##\s(.*)$")
_ROW = "  %-22s %-12s %s"
_UNLABELLED = "?"


def _area_of(headers):
    """{makefile: (area, about)} from (makefile, line) pairs; a makefile's first
    `##@ name  about` line names its area."""
    out = {}
    for relpath, line in headers:
        m = check_structure.AREA_HEADER.match(line.rstrip("\n"))
        if m and relpath not in out:
            out[relpath] = (m.group(1), (m.group(2) or "").strip())
    return out


def group(grep_lines, headers, area, effect):
    """[{"area", "about", "targets": [{"target", "effect", "text"}]}] in the
    order targets first appear. effect is "" (all) or one vocabulary word; area
    is "" (all) or a declared `##@` area. Raises ValueError naming the valid
    values for an unknown effect or area, or an area filter with no areas."""
    if effect and effect not in check_structure.EFFECT_LABELS:
        raise ValueError(
            "EFFECT=%s is not an effect label -- use one of %s"
            % (effect, ", ".join(check_structure.EFFECT_LABELS))
        )
    areas = _area_of(headers)
    if area:
        declared = sorted({name for name, _ in areas.values()})
        if not declared:
            raise ValueError(
                "AREA=%s: no areas -- no makefile carries a `##@ <area>` header "
                "(config/project.json make_targets.area_dir is off)" % area
            )
        if area not in declared:
            raise ValueError(
                "AREA=%s is not an area -- the areas are %s"
                % (area, ", ".join(declared))
            )
    groups, order = {}, []
    for line in grep_lines:
        m = _GREP_LINE.match(line.rstrip("\n"))
        if not m:
            continue
        relpath, target, help_ = m.group(1), m.group(2), m.group(3).strip()
        name, about = areas.get(relpath, (relpath, ""))
        if area and name != area:
            continue
        labels, text, why = check_structure.parse_effect_labels(help_)
        if effect and (labels is None or effect not in labels):
            continue
        row = {
            "target": target,
            "effect": _UNLABELLED if why else ",".join(labels),
            "text": help_ if why else text,
        }
        if name not in groups:
            groups[name] = {"area": name, "about": about, "targets": []}
            order.append(name)
        groups[name]["targets"].append(row)
    return [groups[name] for name in order]


def render(groups):
    """The help text: one block per group, each row `target [label] text`,
    then the legend."""
    out = ["Usage: make <target>   (EFFECT=<word> or AREA=<area> filters the list)"]
    for g in groups:
        out.append("")
        out.append(g["area"] + ("  -- " + g["about"] if g["about"] else ""))
        out.extend(
            _ROW % (row["target"], "[%s]" % row["effect"], row["text"])
            for row in g["targets"]
        )
    out.append("")
    out.append("Effect labels (docs/adr/0011-make-target-effect-labels.md):")
    out.extend(
        "  [%s] %s" % (word, meaning)
        for word, meaning in check_structure.EFFECT_MEANINGS
    )
    return "\n".join(out) + "\n"


def _headers(makefiles):
    pairs = []
    for relpath in makefiles:
        with open(relpath, encoding="utf-8") as fh:
            pairs.extend((relpath, line) for line in fh if line.startswith("##@"))
    return pairs


def main(argv=None):
    """CLI: exit 0 with the help text, 2 on an unknown filter or unreadable makefile."""
    ap = argparse.ArgumentParser(
        description="Render `make help` from grep -H lines on stdin."
    )
    ap.add_argument(
        "--effect", default="", help="keep targets whose label holds this word"
    )
    ap.add_argument("--area", default="", help="keep one `##@` area")
    ap.add_argument(
        "makefiles", nargs="*", help="$(MAKEFILE_LIST), for the area headers"
    )
    args = ap.parse_args(argv)
    try:
        headers = _headers(args.makefiles)
        groups = group(
            sys.stdin.readlines(), headers, args.area.strip(), args.effect.strip()
        )
    except (OSError, ValueError) as exc:
        sys.stderr.write("make help: %s\n" % exc)
        return 2
    sys.stdout.write(render(groups))
    return 0


if __name__ == "__main__":
    sys.exit(main())
