"""
title: Integration — the docs show the lines the config loader writes
kind: tests
layer: n/a
summary: The settings reference and the limits guide quote what scripts/config_loader.py writes to stderr, and this test holds them to it. The lines come from the loader itself, run in a fresh process (its default line prints once per process) over an empty config and an empty environment: a `[using default]` line for each KEYS row with a default, a `[not set]` line for each row without one. config/project.json `doc_drift.settings_reference` must hold, in a row for each defaulted key (the key's own row, or a row under it), the line's `[using default] <key> = <value>` part as a code span. config/project.json `doc_drift.limits_guide` must hold both line shapes as code spans with `<key>`, `<value>` and `<config file>` in place of a real row's text, and each other code span there that opens `[using default] ` or `[not set] ` must be a line, or a line's part before its reason, the loader writes for a real row; at least one of each kind is required. A table with no defaulted row, no required row or no quoted example is a failure, never a pass.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))

from child_env import build_child_env  # noqa: E402

pytestmark = pytest.mark.integration

_DEFAULT_OPENER = "[using default] "
_NOT_SET_OPENER = "[not set] "
_SPAN = re.compile(r"`([^`\n]+)`")
# The loader's line is "<fact>  (<reason>)": two spaces part the fact from why.
_REASON_BREAK = "  ("
_KEY, _VALUE, _WHERE = "<key>", "<value>", "<config file>"

# Run in a child so each default line prints: the loader announces a default
# once per process, and this test must not reach into that private record.
_PROBE = r"""
import io, json, sys
sys.path.insert(0, "scripts")
import config_loader as cl
out = {"defaults": [], "not_set": []}
for key in cl.KEYS:
    where = key.file or cl.CONFIG_FILE
    if key.required:
        try:
            cl.resolve({}, [key], where, environ={}, stream=io.StringIO())
        except cl.NotSet as exc:
            out["not_set"].append(
                {"key": ".".join(key.path), "file": key.file, "line": exc.lines[0]}
            )
        continue
    buf = io.StringIO()
    values = cl.resolve({}, [key], where, environ={}, stream=buf)
    out["defaults"].append(
        {
            "key": ".".join(key.path),
            "file": key.file,
            "line": buf.getvalue().rstrip("\n"),
            "value": values[key.path],
        }
    )
json.dump(out, sys.stdout)
"""


@pytest.fixture(scope="module")
def written():
    done = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=str(_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        env=build_child_env(),
    )
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout)
    assert out["defaults"], "no KEYS row has a default -- zero items"
    assert out["not_set"], "no KEYS row is required -- zero items"
    return out


@pytest.fixture(scope="module")
def docs():
    manifest = json.loads((_ROOT / "config" / "project.json").read_text("utf-8"))
    block = manifest["doc_drift"]
    return {
        name: (block[name], (_ROOT / block[name]).read_text("utf-8"))
        for name in ("settings_reference", "limits_guide")
    }


def _fact(line):
    return line.split(_REASON_BREAK)[0]


def _key_cell(row):
    cells = row.split("|")
    return cells[1].strip().strip("`") if len(cells) > 2 else None


def settings_findings(where, text, defaults):
    """One line per defaulted key no settings row of its own states."""
    rows = [r for r in text.split("\n") if r.startswith("| `")]
    out = []
    for entry in defaults:
        key = entry["key"]
        span = "`%s`" % _fact(entry["line"])
        mine = [
            r
            for r in rows
            if _key_cell(r) == key or (_key_cell(r) or "").startswith(key + ".")
        ]
        if not mine:
            out.append("%s: no row names %s; add one" % (where, key))
        elif not any(span in r for r in mine):
            out.append(
                "%s: no row for %s states its default as %s; add it to the row"
                % (where, key, span)
            )
    return out


def shapes(written):
    """The two line shapes, derived from a real file row of each kind."""
    default = next(e for e in written["defaults"] if e["file"])
    not_set = next(e for e in written["not_set"] if e["file"])
    line = default["line"].replace(default["file"], _WHERE)
    line = line.replace(default["key"], _KEY)
    # The value is the first copy of its JSON text after the key, so the
    # shape follows the loader's wording rather than restating it.
    value = json.dumps(default["value"], sort_keys=True)
    at = line.index(value, line.index(_KEY) + len(_KEY))
    default_shape = line[:at] + _VALUE + line[at + len(value) :]
    not_set_shape = (
        not_set["line"].replace(not_set["file"], _WHERE).replace(not_set["key"], _KEY)
    )
    return default_shape, not_set_shape


def guide_findings(where, text, written):
    """One line per missing shape, stale example, or kind with no example."""
    default_shape, not_set_shape = shapes(written)
    spans = _SPAN.findall(text)
    out = [
        "%s: does not show the line shape `%s`; add it" % (where, shape)
        for shape in (default_shape, not_set_shape)
        if shape not in spans
    ]
    real = set()
    for entry in written["defaults"] + written["not_set"]:
        real.update((entry["line"], _fact(entry["line"])))
    for opener in (_DEFAULT_OPENER, _NOT_SET_OPENER):
        examples = [
            s
            for s in spans
            if s.startswith(opener) and s not in (default_shape, not_set_shape)
        ]
        if not examples:
            out.append(
                "%s: quotes no real `%s...` line -- zero items; add one the "
                "loader writes" % (where, opener)
            )
        out.extend(
            "%s: `%s` is no line scripts/config_loader.py writes; copy it from "
            "the loader's output" % (where, s)
            for s in examples
            if s not in real
        )
    return out


def test_every_declared_default_is_stated_with_its_line(written, docs):
    where, text = docs["settings_reference"]
    findings = settings_findings(where, text, written["defaults"])
    assert not findings, "\n".join(findings)


def test_the_limits_guide_shows_the_lines_the_loader_writes(written, docs):
    where, text = docs["limits_guide"]
    findings = guide_findings(where, text, written)
    assert not findings, "\n".join(findings)


def test_a_dropped_default_or_a_stale_example_is_red(written, docs):
    where, text = docs["settings_reference"]
    first = written["defaults"][0]
    planted = text.replace("`%s`" % _fact(first["line"]), "")
    assert any(first["key"] in f for f in settings_findings(where, planted, [first]))
    where, text = docs["limits_guide"]
    stale = text + "\n`%s`\n" % (_fact(first["line"]) + " (stale)")
    assert any("(stale)" in f for f in guide_findings(where, stale, written))
